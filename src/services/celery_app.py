"""
Celery application và task definitions cho async message processing.

Giải quyết bài toán webhook timeout của Facebook Messenger:
- Facebook yêu cầu server trả về HTTP 200 OK trong 10 giây
- RAG pipeline (embedding + ChromaDB + LLM) có thể mất 14+ giây
- Giải pháp: FastAPI nhận webhook → enqueue task → trả 200 OK ngay lập tức
             Celery worker xử lý RAG độc lập, sau đó gửi reply qua Graph API

⚠️  Lazy import trong task: KHÔNG import graph_service ở module level.
    Lý do: PostgresSaver tạo connection pool khi module được load.
    Nếu pool tạo trong main process rồi fork sang worker → connection corrupt.
    Lazy import đảm bảo pool chỉ được tạo trong worker process.
"""
import os
import re
from typing import Any

import httpx
from celery import Celery
from celery.exceptions import SoftTimeLimitExceeded

from src.core.utils import get_logger

_logger = get_logger(__name__)

# Singleton httpx client — tránh tạo lại connection mỗi lần gửi reply
_http_client: httpx.Client | None = None

# Danh sách brand để trích xuất tên sản phẩm từ lịch sử hội thoại
_PRODUCT_BRANDS: list[str] = [
    "iphone", "samsung galaxy", "xiaomi", "oppo", "vivo", "realme",
    "macbook", "ipad", "airpods", "lenovo", "dell", "asus", "acer",
]

# Facebook Graph API version — đọc từ env, mặc định v21.0 (stable 2025)
_FB_GRAPH_VERSION = os.getenv("FB_GRAPH_API_VERSION", "v21.0")
_FB_MESSAGES_URL = f"https://graph.facebook.com/{_FB_GRAPH_VERSION}/me/messages"

# ── Khởi tạo Celery instance ─────────────────────────────────────────────────
celery_app = Celery(
    "chatbot_worker",
    broker=os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0"),
    backend=os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/1"),
)

celery_app.conf.update(
    # Sử dụng JSON để serialize (an toàn, dễ debug)
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],

    # Múi giờ Việt Nam
    timezone="Asia/Ho_Chi_Minh",
    enable_utc=True,

    # Chỉ ack task sau khi hoàn thành (không mất task nếu worker crash giữa chừng)
    task_acks_late=True,

    # Giới hạn retry tránh vòng lặp vô tận
    task_max_retries=3,
)


def _get_http_client() -> httpx.Client:
    """Trả về httpx.Client singleton — tránh tạo connection mới mỗi request."""
    global _http_client
    if _http_client is None:
        _http_client = httpx.Client(timeout=10.0)
    return _http_client


def _extract_product(messages: list) -> str:
    """Tìm tên sản phẩm được nhắc gần nhất trong các tin nhắn của bot."""
    from langchain_core.messages import AIMessage

    for msg in reversed(messages):
        if not isinstance(msg, AIMessage):
            continue
        content = str(msg.content)
        content_lower = content.lower()
        for brand in _PRODUCT_BRANDS:
            idx = content_lower.find(brand)
            if idx == -1:
                continue
            snippet = content[idx:idx + 50]
            snippet = re.split(r"\s+với\s+giá|\s+với\s+mức|[,\.!\n]", snippet)[0].strip()
            if snippet:
                return snippet
    return ""


@celery_app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=5,  # giây giữa các lần retry
    soft_time_limit=25,     # raise SoftTimeLimitExceeded sau 25s → fallback graceful
    time_limit=30,          # force kill process sau 30s → tránh zombie worker
    name="src.services.celery_app.process_messenger_message",
)
def process_messenger_message(
    self,
    sender_psid: str,
    message_text: str,
    thread_id: str,
    embedding_type: str = "vi",
) -> dict[str, Any]:
    """
    Task async: nhận tin nhắn Messenger → chạy RAG pipeline → gửi reply.

    Args:
        sender_psid:    Page-Scoped ID của người dùng Facebook
        message_text:   Nội dung tin nhắn người dùng gửi
        thread_id:      ID luồng hội thoại cho LangGraph (thường là "messenger_{psid}")
        embedding_type: "en" hoặc "vi" — chọn ChromaDB collection phù hợp

    Returns:
        dict với status và sender_psid khi thành công
    """
    # Lazy import để tránh connection pool fork corruption (xem docstring module)
    from langchain_core.messages import HumanMessage
    from langchain_core.runnables import RunnableConfig

    from src.services.graph_service import ChatbotState
    from src.services.graph_service import app as graph_app
    from src.services.lead_service import init_leads_table, save_lead_if_new

    init_leads_table()

    try:
        # Cấu hình thread_id cho LangGraph checkpointer (PostgresSaver)
        config: RunnableConfig = {"configurable": {"thread_id": thread_id}}

        # Khởi tạo state ban đầu cho luồng hội thoại
        # ⚠️ Messenger có timeout 10s từ Facebook — không bật Advanced RAG mặc định
        # vì Cross-Encoder cold-start ~15s sẽ làm timeout toàn bộ session
        initial_state: ChatbotState = {
            "messages": [HumanMessage(content=message_text)],
            "context": "",
            "needs_retrieval": False,
            "embedding_type": embedding_type,
            # Advanced RAG — tắt mặc định cho Messenger (tốc độ ưu tiên hơn accuracy)
            "use_hyde": False,
            "hyde_query": "",
            "use_decomposition": False,
            "sub_queries": [],
            "use_hybrid": False,
            "use_rerank": False,
            "retrieval_mode": "similarity",
        }

        _logger.info(
            "Bắt đầu xử lý RAG cho PSID=%s, thread=%s, embedding=%s",
            sender_psid,
            thread_id,
            embedding_type,
        )

        # Chạy LangGraph: classifier → (retrieval?) → LLM → trả lời
        result = graph_app.invoke(initial_state, config=config)
        raw_answer = str(result["messages"][-1].content)
        # Xóa markdown vì Messenger không render *bold*, #header, v.v.
        answer = _strip_markdown(raw_answer)

        # Trích xuất tên sản phẩm khách đang quan tâm từ lịch sử hội thoại
        product = _extract_product(result["messages"])

        # Kiểm tra tin nhắn khách có chứa SĐT không → lưu lead vào Google Sheet
        if save_lead_if_new(sender_psid, thread_id, message_text, product=product):
            _logger.info(
                "Lead mới từ PSID=%s: %s - SP: %s", sender_psid, message_text[:80], product
            )

        _logger.info(
            "Đã tạo reply cho PSID=%s (%d ký tự, sau strip_markdown)",
            sender_psid,
            len(answer),
        )

        # Gửi reply về Messenger qua Graph API
        _send_messenger_reply(sender_psid, answer)

        return {"status": "ok", "sender_psid": sender_psid}

    except SoftTimeLimitExceeded:
        # Task chạy quá 25 giây (thường do LLM hoặc ChromaDB treo)
        _logger.error("Task timeout (25s) cho PSID=%s — gửi fallback", sender_psid)
        _send_messenger_reply(
            sender_psid,
            "Xin lỗi, hệ thống đang bận. Vui lòng nhắn lại sau ít phút. 🙏",
        )
        return {"status": "timeout", "sender_psid": sender_psid}

    except Exception as exc:
        _logger.error(
            "Lỗi khi xử lý tin nhắn PSID=%s (lần thử %d/%d): %s",
            sender_psid,
            self.request.retries + 1,
            self.max_retries + 1,
            exc,
        )
        # Đã hết retry → gửi fallback thay vì để user chờ mãi không có phản hồi
        # self.request.retries=3 >= self.max_retries=3 → đây là lần retry cuối cùng
        if self.request.retries >= self.max_retries:
            _logger.warning("Đã hết retry cho PSID=%s — gửi fallback message", sender_psid)
            _send_messenger_reply(
                sender_psid,
                "Xin lỗi, hệ thống đang gặp sự cố. Vui lòng thử lại sau ít phút. 🙏",
            )
            return {"status": "failed_with_fallback", "sender_psid": sender_psid}
        # Còn retry → thử lại sau 5 giây
        raise self.retry(exc=exc)


def _strip_markdown(text: str) -> str:
    """
    Xóa Markdown formatting khỏi text trước khi gửi lên Messenger.

    Facebook Messenger không render markdown — nếu để nguyên, người dùng sẽ thấy
    các ký tự *asterisk*, #hashtag thô thay vì text được định dạng.

    Thứ tự xử lý quan trọng: xử lý **bold** trước *italic* để tránh regex conflict.
    """
    # **bold** → plain (phải xử lý trước *italic*)
    text = re.sub(r"\*\*([^*\n]+)\*\*", r"\1", text)
    # *italic* → plain
    text = re.sub(r"\*([^*\n]+)\*", r"\1", text)
    # # Tiêu đề / ## Tiêu đề → Tiêu đề (xóa ký tự # đầu dòng)
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    # * bullet item → - bullet item
    text = re.sub(r"^\*\s+", "- ", text, flags=re.MULTILINE)
    # `inline code` → plain
    text = re.sub(r"`([^`]+)`", r"\1", text)
    # ~~gạch ngang~~ → plain
    text = re.sub(r"~~([^~]+)~~", r"\1", text)
    # --- / *** / ___ horizontal rules → xóa dòng
    text = re.sub(r"^[-*_]{3,}\s*$", "", text, flags=re.MULTILINE)
    # Dọn dẹp khoảng trắng thừa
    return text.strip()


def _split_message(text: str, limit: int = 2000) -> list[str]:
    """
    Chia text thành các phần, mỗi phần tối đa `limit` ký tự.

    Ưu tiên cắt tại ký tự xuống dòng cuối cùng trong giới hạn để giữ
    nguyên cấu trúc đoạn văn. Nếu không tìm thấy newline thì cắt cứng.

    Args:
        text:  Nội dung cần chia
        limit: Số ký tự tối đa mỗi phần (mặc định 2000 — giới hạn Messenger)

    Returns:
        List các chuỗi, mỗi chuỗi <= limit ký tự. Luôn có ít nhất 1 phần.
    """
    if len(text) <= limit:
        return [text]

    parts: list[str] = []
    while text:
        if len(text) <= limit:
            parts.append(text)
            break
        # Ưu tiên cắt tại newline cuối cùng trong giới hạn
        cut_pos = text.rfind("\n", 0, limit)
        if cut_pos == -1:
            # Không có newline → cắt cứng tại limit
            cut_pos = limit
        else:
            # Giữ ký tự \n vào phần hiện tại để tránh khoảng trắng đầu phần sau
            cut_pos += 1
        parts.append(text[:cut_pos])
        text = text[cut_pos:]

    return parts


def _send_messenger_reply(recipient_psid: str, text: str) -> None:
    """
    Gửi reply về Facebook Messenger qua Graph API.

    Nếu text dài hơn 2000 ký tự (giới hạn Messenger), tự động chia thành
    nhiều phần và gửi tuần tự với khoảng dừng 0.5s giữa mỗi phần
    để tránh rate limit của Facebook.

    Args:
        recipient_psid: Page-Scoped ID của người nhận
        text:           Nội dung tin nhắn (tự động split nếu > 2000 ký tự)
    """
    import time  # stdlib, đặt trong function để nhất quán với lazy import pattern

    page_token = os.getenv("FB_PAGE_ACCESS_TOKEN", "")
    if not page_token:
        _logger.error("FB_PAGE_ACCESS_TOKEN chưa được cấu hình trong .env")
        return

    parts = _split_message(text, limit=2000)
    _logger.info(
        "Gửi reply tới PSID=%s: %d phần, tổng %d ký tự",
        recipient_psid,
        len(parts),
        len(text),
    )

    client = _get_http_client()
    for i, part in enumerate(parts):
        payload = {
            "recipient": {"id": recipient_psid},
            "message": {"text": part},
            # RESPONSE: reply cho tin nhắn người dùng gửi trong 24h
            "messaging_type": "RESPONSE",
        }
        try:
            resp = client.post(
                _FB_MESSAGES_URL,
                params={"access_token": page_token},
                json=payload,
            )
            if resp.status_code == 200:
                _logger.info(
                    "Đã gửi phần %d/%d tới PSID=%s",
                    i + 1, len(parts), recipient_psid,
                )
            else:
                _logger.error(
                    "Facebook Graph API lỗi phần %d/%d PSID=%s: HTTP %d — %s",
                    i + 1, len(parts), recipient_psid, resp.status_code, resp.text,
                )
        except httpx.TimeoutException:
            _logger.error(
                "Timeout khi gửi phần %d/%d tới PSID=%s",
                i + 1, len(parts), recipient_psid,
            )
        except httpx.RequestError as exc:
            _logger.error(
                "Lỗi kết nối Facebook API phần %d/%d PSID=%s: %s",
                i + 1, len(parts), recipient_psid, exc,
            )

        # Tránh rate limit Facebook khi gửi nhiều phần liên tiếp
        if i < len(parts) - 1:
            time.sleep(0.5)
