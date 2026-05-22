import logging

from fastapi import FastAPI
from app.webhook import router as webhook_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logging.getLogger().setLevel(logging.INFO)
for _name in ("app", "app.webhook", "app.transcriber", "app.parser", "app.sheets"):
    logging.getLogger(_name).setLevel(logging.INFO)

app = FastAPI(title="CarExpenses")
app.include_router(webhook_router)


@app.get("/health")
def health():
    return {"status": "ok"}
