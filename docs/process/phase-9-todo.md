# Các việc cần làm tiếp theo — Hoàn chỉnh Phase 9

> **Trạng thái:** Phase 9 đã có kiến trúc cơ bản hoạt động (Docker + Celery + Messenger + PostgreSQL).
> File này liệt kê những gì **còn thiếu hoặc cần sửa** để hệ thống chạy an toàn và ổn định trong production.

---

## 🚨 PHASE 10A — Hotfix bảo mật (NGAY LẬP TỨC)

**Vấn đề:** `.env.example` đang chứa secrets thật (GROQ key, FB App Secret, FB Page Token).
Nếu file này bị push lên GitHub → credentials lộ hoàn toàn.

- [x] **10A-1** — Xóa toàn bộ giá trị thật trong `.env.example`, thay bằng placeholder:
  ```
  GROQ_API_KEY=gsk_xxxxxxxxxxxxxxxxxxxx
  FB_APP_SECRET=your_facebook_app_secret_here
  FB_PAGE_ACCESS_TOKEN=EAAxxxxxxxxxxxxx
  FB_VERIFY_TOKEN=your_custom_verify_token
  ```
- [x] **10A-2** — Kiểm tra `.gitignore` đã có `.env` (không phải `.env.example`):
  ```
  .env          ← phải có dòng này
  # .env.example ← KHÔNG gitignore — file example là public
  ```
- [x] **10A-3** — Chạy `git log --all -- .env` để chắc chắn `.env` thật chưa bao giờ được commit.

---

## 🤖 PHASE 10B — Messenger UX cơ bản

**Vấn đề:** Bot nhận tin nhắn nhưng user không biết bot đang xử lý, và nếu lỗi thì user không nhận được gì.

### 10B-1 — Typing indicator + Mark as seen
File sửa: `src/api/messenger.py` và `src/services/celery_app.py`

Khi nhận tin nhắn từ Facebook, **ngay lập tức** (trong API thread, không phải Celery):
```python
# Trong _handle_messaging_event() — sau khi verify, TRƯỚC khi enqueue
_send_sender_action(sender_psid, "mark_seen")     # ✓ đã đọc
_send_sender_action(sender_psid, "typing_on")     # đang gõ...
process_messenger_message.delay(...)               # enqueue async
```

Thêm hàm `_send_sender_action()` vào `celery_app.py`:
```python
def _send_sender_action(recipient_psid: str, action: str) -> None:
    """Gửi sender_action: mark_seen | typing_on | typing_off"""
    page_token = os.getenv("FB_PAGE_ACCESS_TOKEN", "")
    url = f"https://graph.facebook.com/{FB_API_VERSION}/me/messages"
    payload = {
        "recipient": {"id": recipient_psid},
        "sender_action": action,
    }
    with httpx.Client(timeout=5.0) as client:
        client.post(url, params={"access_token": page_token}, json=payload)
```

- [x] Thêm `_send_facebook_action()` async vào `messenger.py` (dùng AsyncClient)
- [x] Gọi `mark_seen` + `typing_on` từ `messenger.py` trước khi enqueue

### 10B-2 — Split reply dài thay vì truncate
File sửa: `src/services/celery_app.py:142`

Hiện tại: `truncated_text = text[:2000]` → cắt mất nội dung.
Cần sửa thành split thành nhiều messages:

```python
def _split_message(text: str, limit: int = 2000) -> list[str]:
    """Chia text dài thành nhiều phần ≤ limit ký tự, ưu tiên cắt tại dấu xuống dòng."""
    if len(text) <= limit:
        return [text]
    parts = []
    while text:
        if len(text) <= limit:
            parts.append(text)
            break
        cut = text.rfind("\n", 0, limit)
        if cut == -1:
            cut = limit
        parts.append(text[:cut])
        text = text[cut:].lstrip("\n")
    return parts
```

Trong `_send_messenger_reply()`, gửi từng phần với delay nhỏ:
```python
for part in _split_message(text):
    _send_single_message(recipient_psid, part)
    time.sleep(0.5)   # tránh rate limit Facebook
```

- [x] Thêm hàm `_split_message()` vào `celery_app.py`
- [x] Refactor `_send_messenger_reply()` để gửi nhiều messages

### 10B-3 — Error fallback reply khi tất cả retries đều fail
File sửa: `src/services/celery_app.py`

Hiện tại: khi `max_retries=3` bị vượt → task raise exception → user nhận **im lặng hoàn toàn**.
Cần thêm Celery `on_failure` callback:

```python
@celery_app.task(
    bind=True,
    max_retries=3,
    ...
    on_failure=_on_task_failure,   # thêm dòng này
)
def process_messenger_message(...):
    ...

def _on_task_failure(self, exc, task_id, args, kwargs, einfo):
    sender_psid = kwargs.get("sender_psid") or (args[0] if args else None)
    if sender_psid:
        _send_messenger_reply(
            sender_psid,
            "Xin lỗi, hệ thống đang gặp sự cố. Vui lòng thử lại sau ít phút. 🙏"
        )
```

- [x] Thêm logic fallback trong except block (check `retries >= max_retries`)

---

## 🔁 PHASE 10C — Chống duplicate message (Deduplication)

**Vấn đề:** Facebook sẽ retry POST /messenger/webhook nếu không nhận 200 OK trong 10s (ví dụ: server load cao).
Kết quả: cùng một tin nhắn bị xử lý 2-3 lần → user nhận reply trùng lặp.

**Giải pháp:** Dùng `message.mid` (Message ID duy nhất từ Facebook) làm key trong Redis.

File sửa: `src/api/messenger.py`

```python
import redis as _redis

_redis_client = _redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))
_DEDUP_TTL = 86400  # 24 giờ

def _is_duplicate(message_id: str) -> bool:
    """Trả True nếu message đã được enqueue rồi (Facebook retry)."""
    key = f"msg_dedup:{message_id}"
    # SET key NX (chỉ set nếu chưa tồn tại) + EX TTL
    result = _redis_client.set(key, "1", nx=True, ex=_DEDUP_TTL)
    return result is None  # None = key đã tồn tại = duplicate
```

Trong `_handle_messaging_event()`:
```python
message_id = message.get("mid", "")
if message_id and _is_duplicate(message_id):
    _logger.info("Bỏ qua duplicate message mid=%s", message_id)
    return
```

- [ ] Thêm Redis client vào `messenger.py`
- [ ] Thêm hàm `_is_duplicate()` với Redis SET NX
- [ ] Gọi kiểm tra trước khi `process_messenger_message.delay()`

---

## ⚙️ PHASE 10D — Xóa hardcode, thêm env vars

**Vấn đề:** Nhiều giá trị đang hardcode trong code, khó thay đổi khi deploy.

### 10D-1 — Facebook Graph API version
File sửa: `src/services/celery_app.py:144`

Hiện tại: `url = "https://graph.facebook.com/v17.0/me/messages"` — **v17.0 đã cũ** (2023).
Version hiện tại (2025): **v21.0**.

```python
_FB_API_VERSION = os.getenv("FB_GRAPH_API_VERSION", "v21.0")
url = f"https://graph.facebook.com/{_FB_API_VERSION}/me/messages"
```

Thêm vào `.env.example`:
```
FB_GRAPH_API_VERSION=v21.0
```

- [ ] Thay `v17.0` bằng env var `FB_GRAPH_API_VERSION` (default `v21.0`)
- [ ] Áp dụng cho cả `_send_messenger_reply()` và `_send_sender_action()`

### 10D-2 — Embedding type cho Messenger
File sửa: `src/api/messenger.py:137`

Hiện tại: `embedding_type="vi"` hardcode — không linh hoạt nếu muốn đổi sang "en".

```python
_MESSENGER_EMBEDDING_TYPE = os.getenv("MESSENGER_EMBEDDING_TYPE", "vi")

process_messenger_message.delay(
    ...
    embedding_type=_MESSENGER_EMBEDDING_TYPE,
)
```

Thêm vào `.env.example`:
```
MESSENGER_EMBEDDING_TYPE=vi
```

- [ ] Đọc `MESSENGER_EMBEDDING_TYPE` từ env trong `messenger.py`

### 10D-3 — Dockerfile: sửa model cache
File sửa: `Dockerfile`

Hiện tại: pre-cache `multilingual-e5-small` + `multilingual-e5-large` — nhưng `e5-large` **không được dùng** ở đâu trong code, còn `all-MiniLM-L6-v2` (dùng cho "en") **lại không được cache**.

```dockerfile
RUN python -c "\
from sentence_transformers import SentenceTransformer; \
SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2'); \
SentenceTransformer('intfloat/multilingual-e5-small'); \
print('Models cached OK')"
```

- [ ] Xóa download `multilingual-e5-large` (không dùng → tốn ~500MB build time)
- [ ] Thêm download `all-MiniLM-L6-v2` (dùng cho embedding "en")

### 10D-4 — Bỏ `--reload` trong docker-compose api
File sửa: `docker-compose.yml:51`

`--reload` chỉ dùng cho dev (watch file changes). Trong production làm chậm startup và tốn tài nguyên.

```yaml
# dev:
command: uvicorn src.main:app --host 0.0.0.0 --port 8080 --reload
# production:
command: uvicorn src.main:app --host 0.0.0.0 --port 8080 --workers 2
```

- [ ] Xóa `--reload`, thêm `--workers 2` cho production

---

## 🔒 PHASE 10E — Bảo mật & Ổn định production

### 10E-1 — CORS restrict origins
File sửa: `src/main.py:13`

Hiện tại: `allow_origins=["*"]` — bất kỳ domain nào cũng gọi được API.

```python
_ALLOWED_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:8501").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    ...
)
```

Thêm vào `.env.example`:
```
CORS_ORIGINS=http://localhost:8501,http://localhost:3000
```

- [ ] Thay `["*"]` bằng env var `CORS_ORIGINS`

### 10E-2 — Health check kiểm tra Postgres + Redis thực sự
File sửa: `src/main.py`

Hiện tại: `/health` luôn trả `"status": "ok"` dù DB down.

```python
@app.get("/health")
async def health_check() -> dict:
    checks = {}
    # Kiểm tra PostgreSQL
    try:
        import psycopg
        with psycopg.connect(os.getenv("DATABASE_URL", ""), connect_timeout=2):
            checks["postgres"] = "ok"
    except Exception:
        checks["postgres"] = "unreachable"

    # Kiểm tra Redis
    try:
        import redis
        r = redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"), socket_timeout=2)
        r.ping()
        checks["redis"] = "ok"
    except Exception:
        checks["redis"] = "unreachable"

    overall = "ok" if all(v == "ok" for v in checks.values()) else "degraded"
    return {"status": overall, "services": checks, "version": "1.0.0"}
```

- [ ] Thêm probe Postgres và Redis vào `/health` endpoint

### 10E-3 — Rate limiting per PSID
File sửa: `src/api/messenger.py`

Nếu user gửi 50 tin nhắn liên tiếp → 50 Celery tasks xếp hàng → worker bị nghẽn.

```python
_RATE_LIMIT = int(os.getenv("MESSENGER_RATE_LIMIT_PER_MIN", "10"))

def _is_rate_limited(psid: str) -> bool:
    key = f"rate:{psid}:{int(time.time() // 60)}"   # window 1 phút
    count = _redis_client.incr(key)
    if count == 1:
        _redis_client.expire(key, 70)  # TTL hơn 1 phút một chút
    return count > _RATE_LIMIT
```

- [ ] Thêm `_is_rate_limited()` với Redis counter
- [ ] Gọi trước khi enqueue, trả 200 (không enqueue) nếu bị giới hạn

### 10E-4 — Worker memory leak prevention
File sửa: `docker-compose.yml:71`

Sau nhiều requests nặng (embedding + ChromaDB), worker process có thể bị memory leak.

```yaml
worker:
  command: celery -A src.services.celery_app worker
           --loglevel=info
           --concurrency=2
           --max-tasks-per-child=100   # restart worker process sau 100 tasks
```

- [ ] Thêm `--max-tasks-per-child=100` vào worker command

---

## 🌐 PHASE 10F — HTTPS & Production Deploy

**Vấn đề:** Facebook **bắt buộc** HTTPS cho webhook URL. Không có SSL → không thể cấu hình webhook.

### 10F-1 — Dev: ngrok (đã hoạt động nhưng chưa có script)
Tạo file `scripts/ngrok_start.sh`:
```bash
#!/bin/bash
# Khởi động ngrok và in webhook URL để cấu hình Facebook
ngrok http 8080 --log=stdout | tee /tmp/ngrok.log &
sleep 3
NGROK_URL=$(curl -s http://localhost:4040/api/tunnels | python3 -c "
import sys, json
data = json.load(sys.stdin)
print(data['tunnels'][0]['public_url'])
")
echo ""
echo "✅ Webhook URL: ${NGROK_URL}/messenger/webhook"
echo "Dán URL này vào Facebook Developer Portal → Messenger → Webhooks"
```

- [ ] Tạo `scripts/ngrok_start.sh`

### 10F-2 — Production: nginx reverse proxy
Tạo file `nginx/default.conf`:
```nginx
server {
    listen 80;
    server_name yourdomain.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    server_name yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;

    location / {
        proxy_pass http://api:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 30s;
    }
}
```

Thêm service `nginx` vào `docker-compose.yml` và tạo `docker-compose.prod.yml`.

- [ ] Tạo `nginx/default.conf`
- [ ] Tạo `docker-compose.prod.yml` với nginx + certbot service
- [ ] Hướng dẫn `certbot` lấy SSL certificate

---

## 🧪 PHASE 10G — Kiểm thử tự động

**Vấn đề:** Không có test nào cho toàn bộ code Phase 9. Thay đổi bất kỳ file nào có thể break mà không biết.

Tạo thư mục `tests/`:

### 10G-1 — Test webhook verification
Tạo `tests/test_messenger.py`:
```python
def test_webhook_verify_success(client):
    resp = client.get("/messenger/webhook", params={
        "hub.mode": "subscribe",
        "hub.verify_token": "test_token",
        "hub.challenge": "CHALLENGE123"
    })
    assert resp.status_code == 200
    assert resp.text == "CHALLENGE123"

def test_webhook_verify_wrong_token(client):
    resp = client.get("/messenger/webhook", params={
        "hub.mode": "subscribe",
        "hub.verify_token": "wrong_token",
        "hub.challenge": "CHALLENGE123"
    })
    assert resp.status_code == 403
```

### 10G-2 — Test HMAC signature verification
```python
def test_hmac_valid_signature():
    body = b'{"object":"page"}'
    secret = b"test_secret"
    sig = "sha256=" + hmac.new(secret, body, hashlib.sha256).hexdigest()
    # _verify_signature không raise = pass
    _verify_signature(body, sig)  # với FB_APP_SECRET="test_secret" trong env

def test_hmac_invalid_signature():
    with pytest.raises(HTTPException) as exc:
        _verify_signature(b"body", "sha256=wrong_hash")
    assert exc.value.status_code == 403
```

### 10G-3 — Test deduplication
```python
def test_duplicate_message_skipped(mock_celery, redis_client):
    # Gửi cùng một message_id 2 lần
    payload = build_fb_payload(mid="unique-mid-123", text="Hello")
    r1 = post_webhook(payload)
    r2 = post_webhook(payload)
    assert r1.status_code == 200
    assert r2.status_code == 200
    # Celery task chỉ được enqueue 1 lần
    assert mock_celery.delay.call_count == 1
```

- [ ] Tạo `tests/__init__.py` và `tests/conftest.py`
- [ ] Tạo `tests/test_messenger.py` với 3 nhóm test trên
- [ ] Thêm `pytest`, `httpx[test]` vào `requirements.txt` (dev deps)

---

## 📊 PHASE 10H — Admin & Monitoring (Nice to have)

### 10H-1 — API xem lịch sử hội thoại Messenger
Thêm vào `src/api/routes.py`:
```python
@router.get("/messenger/conversations")
async def list_messenger_conversations() -> dict:
    """Liệt kê các thread_id Messenger đang có trong PostgreSQL checkpoints."""
    # Query bảng checkpoints của LangGraph
    ...

@router.get("/messenger/conversations/{thread_id}")
async def get_messenger_conversation(thread_id: str) -> dict:
    """Lấy toàn bộ lịch sử hội thoại của một thread."""
    ...
```

- [ ] Thêm 2 endpoints lịch sử Messenger
- [ ] Thêm UI trong Streamlit sidebar để xem conversations

### 10H-2 — Streamlit Messenger Monitor panel
Thêm tab mới trong `src/frontend/app.py`:
```python
tab_chat, tab_messenger = st.tabs(["💬 Chat", "📱 Messenger Monitor"])

with tab_messenger:
    st.subheader("Lịch sử Messenger")
    # Gọi GET /api/v1/messenger/conversations
    # Hiển thị list conversations, click xem chi tiết
```

- [ ] Thêm tab "Messenger Monitor" vào Streamlit

---

## Tóm tắt thứ tự ưu tiên

| Phase | Mức độ | Thời gian ước tính | Ghi chú |
|-------|--------|-------------------|---------|
| **10A** — Hotfix secrets | 🔴 URGENT | 5 phút | Làm ngay trước khi push git |
| **10B** — Messenger UX | 🔴 Cao | 2-3 giờ | Typing, split, error fallback |
| **10C** — Deduplication | 🔴 Cao | 1 giờ | Chống duplicate khi FB retry |
| **10D** — Xóa hardcode | 🟡 Trung bình | 1 giờ | API version, embedding, models |
| **10E** — Bảo mật prod | 🟡 Trung bình | 2 giờ | CORS, health check, rate limit |
| **10F** — HTTPS/Deploy | 🟡 Trung bình | 3-4 giờ | Cần cho FB webhook thật |
| **10G** — Tests | 🟢 Thấp | 3-4 giờ | Quan trọng về lâu dài |
| **10H** — Admin UI | 🟢 Thấp | 4-6 giờ | Nice to have |
