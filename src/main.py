import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.messenger import messenger_router
from src.api.routes import router
from src.core.utils import get_logger

_logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Tạo bảng leads khi API khởi động (idempotent)
    try:
        from src.services.lead_service import init_leads_table
        init_leads_table()
    except Exception as e:
        _logger.warning("Không thể khởi tạo bảng leads: %s", e)
    yield


app = FastAPI(
    title="AI Chatbot API",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — đọc từ env để production có thể restrict origins
# Mặc định "*" để backward-compatible với dev; production: đặt CORS_ORIGINS=https://domain.com
_ALLOWED_ORIGINS = os.getenv("CORS_ORIGINS", "*").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Gắn router REST API chuẩn
app.include_router(router, prefix="/api/v1")

# Gắn router Facebook Messenger webhook
# GET  /messenger/webhook — xác minh từ Facebook Developer Portal
# POST /messenger/webhook — nhận tin nhắn người dùng
app.include_router(messenger_router, prefix="/messenger")


@app.get("/health")
async def health_check() -> dict:
    import psycopg
    import redis as _redis_lib

    checks: dict[str, str] = {}

    # Ping PostgreSQL
    try:
        with psycopg.connect(os.getenv("DATABASE_URL", ""), connect_timeout=2):
            checks["postgres"] = "ok"
    except Exception:
        checks["postgres"] = "unreachable"

    # Ping Redis
    try:
        r = _redis_lib.from_url(os.getenv("REDIS_URL", ""), socket_timeout=2)
        r.ping()
        checks["redis"] = "ok"
    except Exception:
        checks["redis"] = "unreachable"

    overall = "ok" if all(v == "ok" for v in checks.values()) else "degraded"
    return {
        "status": overall,
        "services": checks,
        "version": "1.0.0",
        "llm_model": "llama-3.1-8b-instant",
    }
