import struct
from pathlib import Path

from app.services.exif import (
    build_png_chunk,
    strip_exif_from_file,
    strip_jpeg_metadata,
    strip_png_metadata,
    strip_webp_metadata,
)


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def jpeg_segment(marker: int, payload: bytes) -> bytes:
    return b"\xff" + bytes([marker]) + (len(payload) + 2).to_bytes(2, "big") + payload


def webp_chunk(chunk_type: bytes, payload: bytes) -> bytes:
    padding = b"\x00" if len(payload) % 2 else b""
    return chunk_type + struct.pack("<I", len(payload)) + payload + padding


def riff_webp(*chunks: bytes) -> bytes:
    body = b"WEBP" + b"".join(chunks)
    return b"RIFF" + struct.pack("<I", len(body)) + body


def test_strip_jpeg_metadata_removes_exif_xmp_comments_and_preserves_scan() -> None:
    scan = b"\xff\xda\x00\x08scanxximage-bytes\xff\xd9"
    original = (
        b"\xff\xd8"
        + jpeg_segment(0xE1, b"Exif\x00\x00gps metadata")
        + jpeg_segment(0xE1, b"http://ns.adobe.com/xap/1.0/\x00xmp")
        + jpeg_segment(0xFE, b"camera comment")
        + jpeg_segment(0xE0, b"JFIF\x00")
        + scan
    )

    stripped = strip_jpeg_metadata(original)

    assert b"gps metadata" not in stripped
    assert b"xmp" not in stripped
    assert b"camera comment" not in stripped
    assert b"JFIF" in stripped
    assert b"image-bytes" in stripped


def test_strip_png_metadata_removes_exif_and_text_chunks() -> None:
    original = (
        PNG_SIGNATURE
        + build_png_chunk(b"IHDR", b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00")
        + build_png_chunk(b"eXIf", b"gps")
        + build_png_chunk(b"tEXt", b"comment=phone")
        + build_png_chunk(b"IDAT", b"pixels")
        + build_png_chunk(b"IEND", b"")
    )

    stripped = strip_png_metadata(original)

    assert b"eXIf" not in stripped
    assert b"tEXt" not in stripped
    assert b"gps" not in stripped
    assert b"pixels" in stripped


def test_strip_webp_metadata_removes_exif_and_xmp_chunks() -> None:
    original = riff_webp(webp_chunk(b"VP8 ", b"pixels"), webp_chunk(b"EXIF", b"gps"), webp_chunk(b"XMP ", b"xmp"))

    stripped = strip_webp_metadata(original)

    assert b"EXIF" not in stripped
    assert b"XMP " not in stripped
    assert b"gps" not in stripped
    assert b"pixels" in stripped
    assert struct.unpack("<I", stripped[4:8])[0] == len(stripped) - 8


def test_strip_exif_from_file_rewrites_image_and_reports_sizes(tmp_path: Path) -> None:
    path = tmp_path / "captura.jpg"
    original = b"\xff\xd8" + jpeg_segment(0xE1, b"Exif\x00\x00gps metadata") + b"\xff\xda\x00\x08scanxxpixels\xff\xd9"
    path.write_bytes(original)

    result = strip_exif_from_file(path, content_type="image/jpeg")

    assert result.status == "stripped"
    assert result.metadata_removed is True
    assert result.original_size_bytes == len(original)
    assert result.stripped_size_bytes == path.stat().st_size
    assert b"gps metadata" not in path.read_bytes()


def test_strip_exif_from_file_skips_non_images(tmp_path: Path) -> None:
    path = tmp_path / "evidencia.txt"
    path.write_text("sin metadata", encoding="utf-8")

    result = strip_exif_from_file(path, content_type="text/plain")

    assert result.status == "skipped"
    assert result.metadata_removed is False
    assert path.read_text(encoding="utf-8") == "sin metadata"
