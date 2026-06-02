from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass
from pathlib import Path


IMAGE_CONTENT_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
RIFF_HEADER_SIZE = 12
JPEG_SOI = b"\xff\xd8"
JPEG_SOS = 0xDA
JPEG_EOI = 0xD9
JPEG_METADATA_MARKERS = {0xE1, 0xED, 0xFE}
JPEG_STANDALONE_MARKERS = set(range(0xD0, 0xDA)) | {0x01}
PNG_METADATA_CHUNKS = {b"eXIf", b"iTXt", b"tEXt", b"zTXt"}
WEBP_METADATA_CHUNKS = {b"EXIF", b"XMP "}


class ExifStripError(Exception):
    pass


@dataclass(frozen=True)
class ExifStripResult:
    status: str
    content_type: str
    metadata_removed: bool
    original_size_bytes: int
    stripped_size_bytes: int


def strip_exif_from_file(path: Path, *, content_type: str) -> ExifStripResult:
    normalized_content_type = content_type.strip().lower()
    original = path.read_bytes()

    if normalized_content_type not in IMAGE_CONTENT_TYPES:
        return build_result("skipped", normalized_content_type, original, original, metadata_removed=False)

    if normalized_content_type == "image/jpeg":
        stripped = strip_jpeg_metadata(original)
    elif normalized_content_type == "image/png":
        stripped = strip_png_metadata(original)
    elif normalized_content_type == "image/webp":
        stripped = strip_webp_metadata(original)
    else:
        stripped = original

    metadata_removed = stripped != original
    if metadata_removed:
        path.write_bytes(stripped)

    return build_result(
        "stripped" if metadata_removed else "clean",
        normalized_content_type,
        original,
        stripped,
        metadata_removed=metadata_removed,
    )


async def strip_exif_from_upload(object_key: str) -> dict[str, str]:
    return {"object_key": object_key, "status": "handled_during_upload"}


def strip_jpeg_metadata(data: bytes) -> bytes:
    if not data.startswith(JPEG_SOI):
        raise ExifStripError("JPEG evidence does not start with SOI marker.")

    output = bytearray(JPEG_SOI)
    index = 2
    length = len(data)

    while index < length:
        if data[index] != 0xFF:
            output.extend(data[index:])
            break

        marker_start = index
        while index < length and data[index] == 0xFF:
            index += 1
        if index >= length:
            output.extend(data[marker_start:])
            break

        marker = data[index]
        index += 1

        if marker in JPEG_STANDALONE_MARKERS:
            output.extend([0xFF, marker])
            continue

        if marker in {JPEG_SOS, JPEG_EOI}:
            output.extend(data[marker_start:])
            break

        if index + 2 > length:
            raise ExifStripError("JPEG segment length is truncated.")

        segment_length = int.from_bytes(data[index : index + 2], "big")
        if segment_length < 2:
            raise ExifStripError("JPEG segment length is invalid.")

        segment_end = index + segment_length
        if segment_end > length:
            raise ExifStripError("JPEG segment extends beyond the file.")

        segment_payload = data[index + 2 : segment_end]
        should_remove = marker in JPEG_METADATA_MARKERS and is_jpeg_metadata_payload(marker, segment_payload)
        if not should_remove:
            output.extend([0xFF, marker])
            output.extend(data[index:segment_end])
        index = segment_end

    return bytes(output)


def is_jpeg_metadata_payload(marker: int, payload: bytes) -> bool:
    if marker == 0xFE:
        return True
    if marker == 0xED:
        return True
    if marker == 0xE1:
        return payload.startswith(b"Exif\x00\x00") or payload.startswith(b"http://ns.adobe.com/xap/1.0/\x00")
    return False


def strip_png_metadata(data: bytes) -> bytes:
    if not data.startswith(PNG_SIGNATURE):
        raise ExifStripError("PNG evidence does not start with PNG signature.")

    output = bytearray(PNG_SIGNATURE)
    index = len(PNG_SIGNATURE)
    metadata_removed = False

    while index < len(data):
        if index + 12 > len(data):
            raise ExifStripError("PNG chunk is truncated.")

        chunk_length = int.from_bytes(data[index : index + 4], "big")
        chunk_type = data[index + 4 : index + 8]
        chunk_data_start = index + 8
        chunk_data_end = chunk_data_start + chunk_length
        chunk_end = chunk_data_end + 4
        if chunk_end > len(data):
            raise ExifStripError("PNG chunk extends beyond the file.")

        if chunk_type in PNG_METADATA_CHUNKS:
            metadata_removed = True
        else:
            output.extend(data[index:chunk_end])

        index = chunk_end
        if chunk_type == b"IEND":
            break

    if not metadata_removed:
        return data
    return bytes(output)


def build_png_chunk(chunk_type: bytes, chunk_data: bytes) -> bytes:
    crc = zlib.crc32(chunk_type)
    crc = zlib.crc32(chunk_data, crc) & 0xFFFFFFFF
    return len(chunk_data).to_bytes(4, "big") + chunk_type + chunk_data + crc.to_bytes(4, "big")


def strip_webp_metadata(data: bytes) -> bytes:
    if len(data) < RIFF_HEADER_SIZE or data[:4] != b"RIFF" or data[8:12] != b"WEBP":
        raise ExifStripError("WebP evidence does not start with RIFF WEBP header.")

    output = bytearray(b"RIFF\x00\x00\x00\x00WEBP")
    index = RIFF_HEADER_SIZE
    metadata_removed = False

    while index + 8 <= len(data):
        chunk_type = data[index : index + 4]
        chunk_size = struct.unpack("<I", data[index + 4 : index + 8])[0]
        chunk_data_start = index + 8
        chunk_data_end = chunk_data_start + chunk_size
        padded_end = chunk_data_end + (chunk_size % 2)
        if padded_end > len(data):
            raise ExifStripError("WebP chunk extends beyond the file.")

        if chunk_type in WEBP_METADATA_CHUNKS:
            metadata_removed = True
        else:
            output.extend(data[index:padded_end])

        index = padded_end

    if not metadata_removed:
        return data

    riff_size = len(output) - 8
    output[4:8] = struct.pack("<I", riff_size)
    return bytes(output)


def build_result(
    status: str,
    content_type: str,
    original: bytes,
    stripped: bytes,
    *,
    metadata_removed: bool,
) -> ExifStripResult:
    return ExifStripResult(
        status=status,
        content_type=content_type,
        metadata_removed=metadata_removed,
        original_size_bytes=len(original),
        stripped_size_bytes=len(stripped),
    )
