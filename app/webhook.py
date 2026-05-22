import logging

from fastapi import APIRouter, Header, HTTPException, Request

from app.config import GROUP_JID, WEBHOOK_SECRET
from app.parser import parse_message
from app.sheets import append_expense

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

    if _is_audio(data):
        logger.info("Áudio recebido — transcrição pendente (Etapa 5)")
        return {"status": "audio_pending"}

    text = _extract_text(data)
    if not text:
        return {"status": "ignored"}

    expense = parse_message(text)
    if not expense:
        logger.info("Mensagem sem valor identificável: %s", text)
        return {"status": "no_expense_found"}

    append_expense(expense)
    logger.info("Gasto registrado: %s", expense)
    return {"status": "ok", "expense": {
        "value": expense.value,
        "description": expense.description,
        "date": expense.date,
        "time": expense.time,
    }}
