import logging
import os
import tempfile

import whisper

logger = logging.getLogger(__name__)

_model = None


def _get_model() -> whisper.Whisper:
    global _model
    if _model is None:
        logger.info("Carregando modelo Whisper tiny...")
        _model = whisper.load_model("small")
        logger.info("Modelo Whisper pronto.")
    return _model


def transcribe_audio(audio_bytes: bytes, suffix: str = ".ogg") -> str:
    """Transcreve bytes de áudio para texto usando Whisper tiny."""
    model = _get_model()

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        f.write(audio_bytes)
        tmp_path = f.name

    try:
        result = model.transcribe(tmp_path, language="pt", fp16=False)
        text = result["text"].strip()
        logger.info("Transcrição: %s", text)
        return text
    finally:
        os.unlink(tmp_path)
