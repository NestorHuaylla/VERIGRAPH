"""AI Vision usando la API de Anthropic (Claude).

Se usa en dos casos, ambos orquestados desde evidence_analysis.py:
  1. Fallback automatico cuando Tesseract no logra un resultado
     confiable (imagen borrosa, manuscrita, con ruido).
  2. Motor primario cuando el usuario pide explicitamente `prefer_ai=true`
     en el endpoint de analisis, o cuando el contenido es un PDF (Claude
     puede leer PDFs directamente como documento visual, sin necesidad
     de convertirlos a imagen primero).

Requiere ANTHROPIC_API_KEY configurada (ver app/core/config.py). Nunca
hardcodear la key en el codigo.
"""

from __future__ import annotations

import base64
import logging
from dataclasses import dataclass, field

import anthropic

logger = logging.getLogger(__name__)

_IMAGE_MEDIA_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
_PDF_MEDIA_TYPE = "application/pdf"

_EXTRACT_TEXT_PROMPT = (
    "Transcribe EXACTAMENTE todo el texto visible en este archivo, "
    "palabra por palabra, preservando saltos de linea cuando sea "
    "relevante (tablas, listas, parrafos, capturas de chat). No agregues "
    "comentarios, explicaciones ni encabezados propios. Si no hay texto "
    "legible, responde unicamente con: [SIN_TEXTO]"
)


@dataclass(frozen=True)
class VisionOutcome:
    text: str
    model: str
    word_count: int = field(init=False)
    error: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "word_count", len(self.text.split()))

    @property
    def success(self) -> bool:
        return self.error is None and self.word_count > 0


class ClaudeVisionUnavailableError(Exception):
    """Falta configurar ANTHROPIC_API_KEY."""


def _build_content_block(content_type: str, data_b64: str) -> dict:
    normalized = content_type.lower()
    if normalized == _PDF_MEDIA_TYPE:
        return {
            "type": "document",
            "source": {"type": "base64", "media_type": normalized, "data": data_b64},
        }
    if normalized in _IMAGE_MEDIA_TYPES:
        return {
            "type": "image",
            "source": {"type": "base64", "media_type": normalized, "data": data_b64},
        }
    raise ValueError(f"Tipo de contenido no soportado por AI Vision: {content_type}")


def run_claude_vision_ocr(
    file_bytes: bytes,
    *,
    content_type: str,
    api_key: str,
    model: str,
    max_tokens: int = 2048,
) -> VisionOutcome:
    """Envia la imagen o PDF a Claude y devuelve el texto transcrito.

    No lanza excepciones por errores de la API o de contenido: siempre
    devuelve un VisionOutcome, con `error` seteado si algo salio mal.
    """
    if not api_key:
        raise ClaudeVisionUnavailableError(
            "Falta ANTHROPIC_API_KEY. Configurala en el .env antes de "
            "usar el motor de AI Vision."
        )

    try:
        data_b64 = base64.standard_b64encode(file_bytes).decode("utf-8")
        content_block = _build_content_block(content_type, data_b64)
    except ValueError as exc:
        return VisionOutcome(text="", model=model, error=str(exc))

    try:
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            messages=[
                {
                    "role": "user",
                    "content": [content_block, {"type": "text", "text": _EXTRACT_TEXT_PROMPT}],
                }
            ],
        )
    except anthropic.APIError as exc:
        logger.error("Error de la API de Anthropic durante AI Vision: %s", exc)
        return VisionOutcome(text="", model=model, error=str(exc))
    except Exception as exc:
        logger.exception("Error inesperado llamando a Claude Vision: %s", exc)
        return VisionOutcome(text="", model=model, error=str(exc))

    raw_text = "".join(
        block.text for block in message.content if getattr(block, "type", None) == "text"
    ).strip()
    text = "" if raw_text == "[SIN_TEXTO]" else raw_text
    return VisionOutcome(text=text, model=model)
