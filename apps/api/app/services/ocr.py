"""OCR local con Tesseract.

Motor primario de extracción de texto para evidencia (imagenes). Es
rapido, gratuito y corre sin salir a internet. Cuando el resultado no
es confiable (poca confianza, poco texto), evidence_analysis.py hace
fallback a AI Vision (ver app/services/ai_vision.py).

Requiere el binario de sistema `tesseract-ocr` (ver Dockerfile) ademas
del paquete de Python `pytesseract`.
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass, field

import pytesseract
from PIL import Image, ImageFilter, ImageOps

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class OcrOutcome:
    text: str
    confidence: float  # 0.0 - 100.0, promedio de confianza por palabra
    word_count: int = field(init=False)
    error: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "word_count", len(self.text.split()))

    @property
    def success(self) -> bool:
        return self.error is None and self.word_count > 0


class TesseractUnavailableError(Exception):
    """El binario de tesseract no esta instalado o no esta en el PATH."""


def _preprocess(image: Image.Image) -> Image.Image:
    """Preprocesamiento ligero para mejorar precision: escala de grises,
    autocontraste, y un desenfoque minimo para reducir ruido de scan."""
    grayscale = ImageOps.grayscale(image)
    contrasted = ImageOps.autocontrast(grayscale, cutoff=2)
    return contrasted.filter(ImageFilter.MedianFilter(size=3))


def run_tesseract_ocr(
    image_bytes: bytes,
    *,
    lang: str = "spa+eng",
) -> OcrOutcome:
    """Corre Tesseract sobre bytes de imagen (jpeg/png/webp) y devuelve
    texto + confianza promedio. No lanza excepciones por errores de
    contenido: siempre devuelve un OcrOutcome, con `error` seteado si
    algo salio mal, para que el llamador decida si hace fallback."""
    try:
        image = Image.open(io.BytesIO(image_bytes))
        image.load()
    except Exception as exc:  # imagen corrupta / formato no soportado por PIL
        logger.warning("No se pudo abrir la imagen para OCR: %s", exc)
        return OcrOutcome(text="", confidence=0.0, error=f"invalid_image: {exc}")

    try:
        processed = _preprocess(image)
        data = pytesseract.image_to_data(
            processed, lang=lang, output_type=pytesseract.Output.DICT
        )
    except pytesseract.TesseractNotFoundError as exc:
        raise TesseractUnavailableError(
            "tesseract-ocr no esta instalado en el sistema. "
            "Instalalo con: apt-get install tesseract-ocr tesseract-ocr-spa"
        ) from exc
    except Exception as exc:
        logger.exception("Error inesperado corriendo tesseract: %s", exc)
        return OcrOutcome(text="", confidence=0.0, error=str(exc))

    words: list[str] = []
    confidences: list[float] = []
    for word, conf_raw in zip(data.get("text", []), data.get("conf", [])):
        word = word.strip()
        try:
            conf = float(conf_raw)
        except (TypeError, ValueError):
            continue
        if word and conf > 0:
            words.append(word)
            confidences.append(conf)

    avg_confidence = round(sum(confidences) / len(confidences), 2) if confidences else 0.0
    return OcrOutcome(text=" ".join(words), confidence=avg_confidence)


def is_ocr_result_reliable(
    outcome: OcrOutcome,
    *,
    min_confidence: float,
    min_word_count: int,
) -> bool:
    """Criterio central que usa evidence_analysis.py para decidir si el
    resultado de Tesseract alcanza o si hace falta escalar a AI Vision."""
    return (
        outcome.success
        and outcome.confidence >= min_confidence
        and outcome.word_count >= min_word_count
    )
