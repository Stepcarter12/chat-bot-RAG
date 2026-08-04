"""
Facebook Messenger webhook endpoint.

Luồng xử lý:
  GET  /messenger/webhook → xác minh hub.verify_token → trả hub.challenge
  POST /messenger/webhook → xác minh HMAC-SHA256 → enqueue Celery task → 200 OK

Tại sao cần enqueue ngay và trả 200 OK?
  Facebook yêu cầu server phản hồi trong 10 giây.
  RAG pipeline (embedding + ChromaDB + LLM) mất 14+ giây.
  Nếu vượt 10s → Facebook retry → người dùng nhận tin nhắn trùng lặp.

⚠️  QUAN TRỌNG về HMAC verification:
  Phải đọc raw bytes TRƯỚC khi parse JSON.
  Nếu parse JSON rồi json.dumps() lại → ký tự khoảng trắng / Unicode thay đổi
  → hash bị sai → Facebook từ chối webhook.
"""
import hashlib
import hmac
import json
import os
import time

import httpx
import redis as _redis_lib
from fastapi import APIRouter, HTTPException, Request, Response

from src.core.utils import get_logger
from src.services.celery_app import process_messenger_message

_logger = get_logger(__name__)

# Facebook Graph API version — đồng bộ với celery_app.py
_FB_GRAPH_VERSION = os.getenv("FB_GRAPH_API_VERSION", "v21.0")
_FB_MESSAGES_URL = f"https://graph.facebook.com/{_FB_GRAPH_VERSION}/me/messages"

# Embedding type cho Messenger — đọc từ env thay vì hardcode
_MESSENGER_EMBEDDING_TYPE = os.getenv("MESSENGER_EMBEDDING_TYPE", "vi")

# Redis client dùng chung cho dedup và rate limiting
_redis_client = _redis_lib.from_url(
    os.getenv("REDIS_URL", "redis://localhost:6379/0"),
    decode_responses=True,
)

# Giới hạn số tin nhắn mỗi PSID trong 1 phút
_RATE_LIMIT = int(os.getenv("MESSENGER_RATE_LIMIT_PER_MIN", "10"))


def _is_duplicate(message_id: str) -> bool:
    """Kiểm tra tin nhắn đã xử lý chưa dùng Redis SET NX (TTL 24h)."""
    key = f"msg_dedup:{message_id}"
    result = _redis_client.set(key, "1", nx=True, ex=86400)
    return result is None  # None = key đã tồn tại = duplicate


def _is_rate_limited(psid: str) -> bool:
    """Kiểm tra PSID có vượt quá giới hạn tin nhắn/phút không."""
    key = f"rate:{psid}:{int(time.time() // 60)}"
    count = int(_redis_client.incr(key))
    if count == 1:
        _redis_client.expire(key, 70)  # TTL 70s > 60s để tránh edge case giữa phút
    return count > _RATE_LIMIT


async def _send_facebook_action(recipient_psid: str, sender_action: str) -> None:
    """
    Gửi sender_action tới Facebook Graph API.

    Dùng httpx.AsyncClient để không block event loop của FastAPI.
    Lỗi chỉ được log, không raise — không được làm fail toàn bộ webhook.

    Args:
        recipient_psid: Page-Scoped ID của người dùng
        sender_action:  "mark_seen" (báo đã đọc) hoặc "typing_on" (đang gõ...)
    """
    page_token = os.getenv("FB_PAGE_ACCESS_TOKEN", "")
    if not page_token:
        _logger.warning(
            "FB_PAGE_ACCESS_TOKEN chưa cấu hình — bỏ qua sender_action=%s",
            sender_action,
        )
        return

    payload = {
        "recipient": {"id": recipient_psid},
        "sender_action": sender_action,
    }
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                _FB_MESSAGES_URL,
                params={"access_token": page_token},
                json=payload,
            )
            if resp.status_code != 200:
                _logger.warning(
                    "sender_action=%s thất bại cho PSID=%s: HTTP %d",
                    sender_action, recipient_psid, resp.status_code,
                )
    except (httpx.TimeoutException, httpx.RequestError) as exc:
        # Không critical — typing indicator là nicety, không ảnh hưởng reply
        _logger.warning(
            "Bỏ qua sender_action=%s PSID=%s: %s",
            sender_action, recipient_psid, exc,
        )


messenger_router = APIRouter()


# ── GET /webhook — Xác minh webhook khi cấu hình trên Facebook Developer ──────
@messenger_router.get("/webhook")
async def verify_webhook(request: Request) -> Response:
    """
    Facebook gọi endpoint này một lần khi admin cấu hình webhook trong
    Meta App Dashboard. Server phải trả về giá trị hub.challenge nếu
    hub.verify_token khớp với giá trị đã đặt trong .env.

    Trả về plain text (không phải JSON) — nếu trả JSON, verification thất bại.
    """
    params = dict(request.query_params)
    mode: str = params.get("hub.mode", "")
    token: str = params.get("hub.verify_token", "")
    challenge: str = params.get("hub.challenge", "")

    if mode == "subscribe" and token == os.getenv("FB_VERIFY_TOKEN", ""):
        _logger.info("Webhook verified thành công từ Facebook")
        # Trả về plain text — bắt buộc theo yêu cầu của Facebook
        return Response(content=challenge, media_type="text/plain")

    _logger.warning(
        "Webhook verification thất bại: mode=%s, token_match=%s",
        mode,
        token == os.getenv("FB_VERIFY_TOKEN", ""),
    )
    raise HTTPException(status_code=403, detail="Verify token không hợp lệ")


# ── POST /webhook — Nhận tin nhắn từ người dùng ─────────────────────────────
@messenger_router.post("/webhook")
async def receive_message(request: Request) -> dict:
    """
    Nhận webhook payload từ Facebook khi người dùng gửi tin nhắn.

    Thứ tự xử lý bắt buộc:
      1. Đọc raw bytes  ← PHẢI làm trước verify HMAC
      2. Verify HMAC-SHA256
      3. Parse JSON     ← Chỉ parse SAU khi đã verify
      4. Enqueue Celery task (non-blocking)
      5. Trả 200 OK ngay lập tức
    """
    # Bước 1: Đọc raw bytes — BẮT BUỘC trước khi làm bất cứ điều gì khác
    raw_body: bytes = await request.body()

    # Bước 2: Verify chữ ký HMAC-SHA256
    signature_header = request.headers.get("X-Hub-Signature-256", "")
    _verify_signature(raw_body, signature_header)

    # Bước 3: Parse JSON SAU khi đã xác minh
    try:
        payload: dict = json.loads(raw_body)
    except json.JSONDecodeError:
        _logger.error("Payload không phải JSON hợp lệ")
        raise HTTPException(status_code=400, detail="Payload JSON không hợp lệ")

    # Bước 4: Xử lý từng messaging event
    # Facebook có thể batch nhiều events trong một request
    if payload.get("object") == "page":
        for entry in payload.get("entry", []):
            for event in entry.get("messaging", []):
                await _handle_messaging_event(event)

    # Bước 5: Trả 200 OK ngay lập tức (bắt buộc trong 10 giây)
    return {"status": "EVENT_RECEIVED"}


async def _handle_messaging_event(event: dict) -> None:
    """
    Phân tích một messaging event, gửi typing indicator, enqueue Celery task.

    Thứ tự xử lý:
      1. Lọc: bỏ qua echo, tin nhắn không có text, event thiếu sender PSID
      2. mark_seen  — báo Facebook đã đọc tin nhắn
      3. typing_on  — hiển thị "đang gõ..." cho người dùng
      4. Enqueue Celery task (non-blocking) — worker xử lý RAG và gửi reply

    Bước 2-3 dùng httpx.AsyncClient (không block event loop).
    Typing indicator tự tắt sau 20s phía Facebook nếu reply đến muộn hơn.
    """
    sender_psid: str = event.get("sender", {}).get("id", "")
    message: dict = event.get("message", {})
    message_text: str = message.get("text", "")

    # Bỏ qua tin nhắn echo (bot tự gửi) và tin nhắn không có text
    if not message_text or message.get("is_echo", False):
        return

    if not sender_psid:
        _logger.warning("Event không có sender PSID, bỏ qua")
        return

    # Deduplication: bỏ qua nếu đã xử lý tin nhắn này (Facebook retry)
    mid = message.get("mid", "")
    if mid and _is_duplicate(mid):
        _logger.info("Bỏ qua tin nhắn trùng lặp mid=%s PSID=%s", mid, sender_psid)
        return

    # Rate limiting: bỏ qua nếu PSID gửi quá nhiều tin trong 1 phút
    if _is_rate_limited(sender_psid):
        _logger.warning(
            "Rate limit vượt quá (%d msg/phút) cho PSID=%s — bỏ qua",
            _RATE_LIMIT,
            sender_psid,
        )
        return

    # Báo đã đọc + hiển thị "đang gõ..." TRƯỚC khi enqueue
    await _send_facebook_action(sender_psid, "mark_seen")
    await _send_facebook_action(sender_psid, "typing_on")

    # thread_id = "messenger_{psid}" để mỗi người dùng có luồng hội thoại riêng
    thread_id = f"messenger_{sender_psid}"

    _logger.info(
        "Enqueue task cho PSID=%s, thread=%s, text='%s...'",
        sender_psid,
        thread_id,
        message_text[:50],
    )

    # Enqueue Celery task — NON-BLOCKING, trả về ngay
    # Celery worker sẽ xử lý RAG và gửi reply độc lập
    process_messenger_message.delay(
        sender_psid=sender_psid,
        message_text=message_text,
        thread_id=thread_id,
        embedding_type=_MESSENGER_EMBEDDING_TYPE,
    )


def _verify_signature(raw_body: bytes, signature_header: str) -> None:
    """
    Xác minh chữ ký X-Hub-Signature-256 từ Facebook.

    Facebook tính HMAC-SHA256(App Secret, raw request body) và gửi trong header.
    Server phải tính lại và so sánh để đảm bảo request đến từ Facebook thật.

    ⚠️  Dùng hmac.compare_digest() để tránh timing attack
        (so sánh từng byte thay vì dừng sớm khi tìm thấy khác biệt)

    Args:
        raw_body:         Nội dung request body dạng bytes thô
        signature_header: Giá trị header X-Hub-Signature-256 (dạng "sha256=<hex>")

    Raises:
        HTTPException 403: Nếu thiếu header hoặc signature không khớp
    """
    if not signature_header:
        _logger.warning("Thiếu X-Hub-Signature-256 header — từ chối request")
        raise HTTPException(
            status_code=403,
            detail="Thiếu X-Hub-Signature-256 header",
        )

    app_secret = os.getenv("FB_APP_SECRET", "")
    if not app_secret:
        _logger.error("FB_APP_SECRET chưa được cấu hình trong .env")
        raise HTTPException(
            status_code=500,
            detail="Server chưa cấu hình FB_APP_SECRET",
        )

    # Tính HMAC-SHA256 từ raw bytes + App Secret
    expected_signature = "sha256=" + hmac.new(
        app_secret.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()

    # compare_digest: so sánh constant-time, tránh timing attack
    if not hmac.compare_digest(signature_header, expected_signature):
        _logger.error(
            "Signature không hợp lệ. Received=%s Expected=%s",
            signature_header[:20] + "...",
            expected_signature[:20] + "...",
        )
        raise HTTPException(
            status_code=403,
            detail="X-Hub-Signature-256 không hợp lệ",
        )
