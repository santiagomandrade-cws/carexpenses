import asyncio
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
from fastapi import APIRouter, Header, HTTPException, Request

from app.config import EVOLUTION_API_KEY, EVOLUTION_API_URL, EVOLUTION_INSTANCE, GROUP_JID, NOTIFY_JID, WEBHOOK_SECRET
from app.parser import parse_message
from app.sheets import append_expense, get_monthly_summary
from app.transcriber import transcribe_audio

_TZ = ZoneInfo("America/Sao_Paulo")
_MONTHS_PT = ["jan", "fev", "mar", "abr", "mai", "jun",
               "jul", "ago", "set", "out", "nov", "dez"]

_COMMANDS_TOTAL = {"total", "gastos", "gastei", "quanto gastei"}
_COMMANDS_RESUMO = {"resumo", "relatório", "relatorio"}

logger = logging.getLogger(__name__)
router = APIRouter()


def _detect_command(text: str) -> str | None:
    normalized = text.strip().lower()
    if normalized in _COMMANDS_TOTAL or any(normalized.startswith(c + " ") for c in _COMMANDS_TOTAL):
        return "total"
    if normalized in _COMMANDS_RESUMO or any(normalized.startswith(c + " ") for c in _COMMANDS_RESUMO):
        return "resumo"
    return None


def _fmt_currency(value: float) -> str:
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


async def _handle_command(command: str, jid: str) -> dict:
    now = datetime.now(tz=_TZ)
    summary = get_monthly_summary(now.year, now.month)
    total = summary["total"]
    count = summary["count"]
    expenses = summary["expenses"]
    month_label = f"{_MONTHS_PT[now.month - 1]}/{now.year}"
    plural = "s" if count != 1 else ""

    if command == "total":
        msg = (
            f"🚗 *CarExpenses*\n"
            f"📊 *Total {month_label}*\n"
            f"💰 {_fmt_currency(total)}\n"
            f"📋 {count} lançamento{plural}"
        )
    else:
        lines = [
            f"🚗 *CarExpenses*",
            f"📊 *Resumo {month_label}*",
            f"💰 {_fmt_currency(total)} — {count} lançamento{plural}",
        ]
        if expenses:
            lines.append("")
            lines.append("*Últimos lançamentos:*")
            for e in reversed(expenses[-5:]):
                date_short = e.get("Data", "")[:5]
                desc = e.get("Descrição", "sem descrição")
                val = _fmt_currency(float(e.get("Valor (R$)", 0) or 0))
                lines.append(f"• {date_short} – {desc} – {val}")
        msg = "\n".join(lines)

    await _send_reply(jid, msg)
    logger.info("Comando '%s' respondido: total=%s count=%d", command, total, count)
    return {"status": "ok", "command": command, "total": total, "count": count}


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
    return f"🚗 *CarExpenses*\n✅ {valor} registrado em {expense.date}\n_{expense.description}_"


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

    command = _detect_command(text)
    if command:
        return await _handle_command(command, jid)

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
