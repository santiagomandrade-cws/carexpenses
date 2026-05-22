from fastapi import APIRouter, Request

router = APIRouter()


@router.post("/webhook")
async def receive_webhook(request: Request):
    """Receive and route incoming messages from Evolution API."""
    # TODO: Etapa 6
    pass
