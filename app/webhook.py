import asyncio
import logging

import httpx
from fastapi import APIRouter, Header, HTTPException, Request

from app.config import EVOLUTION_API_KEY, EVOLUTION_API_URL, EVOLUTION_INSTANCE, GROUP_JID, NOTIFY_JID, WEBHOOK_SECRET
from app.parser import parse_message
from app.sheets import append_expense
from app.transcriber import transcribe_audio

logger = logging.getLogger(__name__)
router = APIRouter()


def _extract_text(data: dict) -> str | None:
    msg = data.get("message", {})
    return (
        msg.get("conversation")
        or msg.get("extendedTextMessage", {}).get("text")
    )


def _is_audio(data: dict) -> bool:
    return data.get("messageType") == "audioMessage"


def _should_ignore(data: dict) -> bool:
    if data.get("key", {}).get("fromMe"):
        return True
    if GROUP_JID and data.get("key", {}).get("remoteJid") != GROUP_JID:
        return True
    return False


def _fmt_expense(expense) -> str:
    valor = f"R$ {expense.value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"✅ {valor} registrado em {expense.date} — {expense.description}"


async def _send_reply(to_jid: str, text: str) -> None:
    url = f"{EVOLUTION_API_URL}/message/sendText/{EVOLUTION_INSTANCE}"
    headers = {"apikey": EVOLUTION_API_KEY}
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            await client.post(url, json={"number": to_jid, "textMessage": {"text": text}}, headers=headers)
        except Exception as e:
            logger.error("Erro ao enviar resposta WhatsApp: %s", e)


async def _download_audio(message_data: dict) -> bytes:
    """Baixa o áudio via Evolution API e retorna os bytes raw."""
    import base64
    url = f"{EVOLUTION_API_URL}/chat/getBase64FromMediaMessage/{EVOLUTION_INSTANCE}"
    headers = {"apikey": EVOLUTION_API_KEY}
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(url, json={"message": message_data}, headers=headers)
        r.raise_for_status()
        data = r.json()
        b64 = data.get("base64", "")
        return base64.b64decode(b64)


async def _handle_audio(data: dict, jid: str) -> dict:
    try:
        audio_bytes = await _download_audio(data)
        loop = asyncio.get_event_loop()
        text = await loop.run_in_executor(None, transcribe_audio, audio_bytes)
    except Exception as e:
        logger.error("Erro ao processar áudio: %s", e)
        await _send_reply(jid, f"Não consegui processar o áudio. Erro: {e}")
        return {"status": "audio_error", "detail": str(e)}

    if not text:
        await _send_reply(jid, "Não consegui entender o áudio.")
        return {"status": "audio_empty"}

    expense = parse_message(text)
    if not expense:
        logger.info("Áudio transcrito sem valor identificável: %s", text)
        await _send_reply(jid, f"Não encontrei nenhum valor no áudio.\nTranscrição: _{text}_")
        return {"status": "no_expense_found", "transcription": text}

    append_expense(expense)
    logger.info("Gasto por áudio registrado: %s", expense)
    await _send_reply(jid, _fmt_expense(expense))
    return {"status": "ok", "transcription": text, "expense": {
        "value": expense.value,
        "description": expense.description,
        "date": expense.date,
        "time": expense.time,
    }}


@router.post("/webhook")
async def receive_webhook(
    request: Request,
    x_webhook_secret: str | None = Header(default=None),
):
    if WEBHOOK_SECRET and x_webhook_secret != WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="token inválido")

    body = await request.json()
    data = body.get("data", {})

    if _should_ignore(data):
        return {"status": "ignored"}

    remote_jid = data.get("key", {}).get("remoteJid", "")
    jid = NOTIFY_JID if NOTIFY_JID else remote_jid

    if _is_audio(data):
        return await _handle_audio(data, jid)

    text = _extract_text(data)
    if not text:
        return {"status": "ignored"}

    expense = parse_message(text)
    if not expense:
        logger.info("Mensagem sem valor identificável: %s", text)
        await _send_reply(jid, f"Não encontrei nenhum valor na mensagem: _{text}_")
        return {"status": "no_expense_found"}

    append_expense(expense)
    logger.info("Gasto registrado: %s", expense)
    await _send_reply(jid, _fmt_expense(expense))
    return {"status": "ok", "expense": {
        "value": expense.value,
        "description": expense.description,
        "date": expense.date,
        "time": expense.time,
    }}
