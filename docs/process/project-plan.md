# Tổng kết Dự án AI Chatbot — Phase 1 → 10

## Trạng thái tổng quan

| Phase | Tên | Trạng thái |
|-------|-----|-----------|
| Phase 1 | Nền tảng & Khung API | ✅ Hoàn thành |
| Phase 2 | LangGraph & Bộ nhớ | ✅ Hoàn thành |
| Phase 3 | RAG & Conditional Edges | ✅ Hoàn thành |
| Phase 4 | Optimization & Hooks | ✅ Hoàn thành |
| Phase 5 | Frontend & RAG Production Fixes | ✅ Hoàn thành |
| Phase 6 | RAG Management — Chunk UI & Ingest API | ✅ Hoàn thành |
| Phase 7 | Multi-Embedding (Tiếng Anh / Tiếng Việt) | ✅ Hoàn thành |
| Phase 8 | Document Management — Quản lý File API | ✅ Hoàn thành |
| Phase 9 | Docker + Celery + Facebook Messenger + PostgreSQL | ✅ Hoàn thành |
| Phase 10 | Advanced RAG — Semantic Chunking, Hybrid Search, HyDE, Rerank, MMR | ✅ Hoàn thành |
| Phase 11 | Bot Sale Điện Tử — System Prompt, Lead Capture, Google Sheets | ✅ Hoàn thành |
| Phase 12 | Security, Performance & Code Quality Audit | ✅ Hoàn thành |
| Phase 13 | Production Hardening — Dedup, Rate Limit, Health Check, Env Vars | ✅ Hoàn thành |
| Phase 14 | HTTPS & Deploy Production — nginx, Let's Encrypt | ✅ Hoàn thành |
| Phase 15 | Automated Tests — pytest webhook, HMAC, deduplication | ⏳ Chưa thực hiện |
| Phase 16 | Admin UI — Conversation History, Messenger Monitor | ⏳ Chưa thực hiện |

---

## ✅ Phase 1 — Nền Tảng & Khung API

**Mục tiêu:** Thiết lập cấu trúc dự án chuẩn, khởi tạo môi trường, xây dựng máy chủ FastAPI.

| Việc đã làm | File | Chi tiết |
|-------------|------|---------|
| Cấu trúc thư mục AI-friendly | `docs/`, `ops/`, `src/` | Theo chuẩn 3-directory |
| Môi trường ảo Python | `venv/` | Cô lập dependencies |
| Biến môi trường | `.env` | `GROQ_API_KEY` |
| FastAPI app + CORS | `src/main.py` | Prefix `/api/v1`, health check |
| Endpoint chat | `src/api/routes.py` | `POST /api/v1/chat` nhận `query` + `thread_id` |
| Quy ước dự án | `CLAUDE.md` | Import `src.`, comment tiếng Việt, type hints |
| Tài liệu kiến trúc | `docs/project/dify-logic-mapping.md` | Ánh xạ từ Dify sang LangGraph |

```
Client → POST /api/v1/chat { query, thread_id } → FastAPI → [placeholder]
```

---

## ✅ Phase 2 — LangGraph & Bộ Nhớ

**Mục tiêu:** Thay thế mock response bằng LangGraph StateGraph + MemorySaver.

| Việc đã làm | File | Chi tiết |
|-------------|------|---------|
| `ChatbotState` TypedDict | `graph_service.py` | `messages`, `context`, `needs_retrieval` |
| `add_messages` reducer | `graph_service.py` | Tự động append tin nhắn, không ghi đè |
| LLM Node | `graph_service.py` | `call_llm_node()` → Groq `llama-3.1-8b-instant` |
| MemorySaver | `graph_service.py` | Lưu State theo `thread_id` qua SQLite in-memory |
| Kết nối FastAPI | `routes.py` | `graph_app.invoke()` với `RunnableConfig` |

```
POST /api/v1/chat → graph_app.invoke → call_llm_node → AIMessage → MemorySaver
```

---

## ✅ Phase 3 — RAG & Conditional Edges

**Mục tiêu:** Pipeline RAG với ChromaDB, phân loại câu hỏi thông minh.

| Việc đã làm | File | Chi tiết |
|-------------|------|---------|
| ChromaDB + HuggingFace | `vector_store.py` | Embedding model theo `embedding_type`, persist theo thư mục riêng |
| `question_classifier_node` | `graph_service.py` | LLM phân loại yes/no có cần RAG |
| `route_after_classifier` | `graph_service.py` | Router function cho conditional edges |
| `retrieval_node` | `graph_service.py` | Truy xuất top-5 chunks từ ChromaDB |
| `run_ingestion()` | `src/retrieval/ingest.py` | Load, chunk, embed, lưu vào ChromaDB |
| Thư mục tài liệu | `docs/data/` | Nơi bỏ file tài liệu thô |

```
START → question_classifier_node
    → [yes] → retrieval_node → call_llm_node → END
    → [no]                  → call_llm_node → END
```

---

## ✅ Phase 4 — Optimization & Hooks

**Mục tiêu:** Logging, linting, type safety, Claude Code Hooks.

| Việc đã làm | File | Chi tiết |
|-------------|------|---------|
| Logger dùng chung | `src/core/utils.py` | `get_logger()` chuẩn cho toàn dự án |
| Logging trong nodes | `graph_service.py`, `routes.py` | Log classifier, retrieval, request/response |
| Linting config | `setup.cfg` | flake8 max-line=100, mypy python 3.10 |
| Claude Code Hooks | `.claude/settings.json` | Auto flake8 sau mỗi Write/Edit |
| Health check nâng cấp | `src/main.py` | Trả về version, model, vector_store |
| Fix mypy namespace | `src/__init__.py` | `explicit_package_bases = True` |

---

## ✅ Phase 5 — Frontend & RAG Production Fixes

### 5.1 — Frontend Streamlit

| Việc đã làm | File | Chi tiết |
|-------------|------|---------|
| Chat UI | `src/frontend/app.py` | `st.chat_message`, lịch sử hội thoại trong `session_state` |
| Thread ID sidebar | `app.py` | Đổi session để test memory |
| Upload tài liệu từ web | `app.py` | `st.file_uploader` → lưu vào `docs/data/` → ingest |
| Error handling | `app.py` | Bắt `ConnectionError`, `Timeout`, lỗi chung |

### 5.2 — Mở rộng Ingest (Multi-format)

| Định dạng | Loader | Package |
|---|---|---|
| `.txt` | `TextLoader` | có sẵn |
| `.pdf` | `PyPDFLoader` | `pypdf` |
| `.docx` | `Docx2txtLoader` | `docx2txt` |
| `.csv` | `CSVLoader` | có sẵn |
| `.xlsx` / `.xls` | `pandas` + `openpyxl` | `pandas`, `openpyxl` |

### 5.3 — RAG Bugfixes (Production)

| Bug | Root Cause | Fix |
|---|---|---|
| `ModuleNotFoundError: langchain_community` | Package thiếu | Cài `langchain-community` |
| `DeprecationWarning: Chroma` | `langchain_community.Chroma` deprecated | Đổi sang `langchain_chroma.Chroma` |
| `UnicodeEncodeError` khi ingest | Windows console dùng `cp1252` | `sys.stdout.reconfigure(encoding='utf-8')` |
| RAG trả về rỗng sau ingest | Stale `_vector_store` reference | Tạo fresh `Chroma` connection mỗi lần `retrieve_context()` |
| Path không nhất quán | `vector_store.py` dùng relative path | Đổi sang absolute path từ `Path(__file__)` |
| Score filtering loại bỏ hết kết quả | `all-MiniLM-L6-v2` cho điểm thấp với tiếng Việt | Bỏ score threshold, dùng `similarity_search()` top-k |

### 5.4 — Các fix khác

| Vấn đề | Fix |
|---|---|
| `llama3-8b-8192` decommissioned | Đổi sang `llama-3.1-8b-instant` |
| `WinError 10013` port 8000 | Đổi sang port `8080` |
| Classifier bỏ sót câu hỏi tiếng Anh | Viết lại classifier prompt bằng tiếng Anh |
| LLM trả lời cứng tiếng Việt | Thêm `"Always respond in the same language as the user's question"` |

---

## ✅ Phase 6 — RAG Management (Chunk UI & Ingest API)

**Mục tiêu:** Cho phép người dùng tùy chỉnh kích thước chunk và xem trước kết quả ngay trên Streamlit.

| Việc đã làm | File | Chi tiết |
|-------------|------|---------|
| Refactor `run_ingestion()` | `src/retrieval/ingest.py` | Hàm nhận `chunk_size`, `chunk_overlap`, `embedding_type`; trả về `list[str]` (text các chunk) |
| `POST /api/v1/ingest` | `src/api/routes.py` | Nhận `IngestRequest`, chạy trong thread pool (`asyncio.to_thread`), trả `IngestResponse{chunks, total}` |
| UI Quản lý Cơ sở dữ liệu | `src/frontend/app.py` | `st.expander("⚙️ Quản lý Cơ sở dữ liệu")`: `number_input` cho chunk_size/overlap, nút preview toàn bộ chunks |
| Fix `ModuleNotFoundError: src` khi subprocess | `src/retrieval/ingest.py` | Thêm `sys.path.insert(0, project_root)` ở đầu file để hoạt động cả khi chạy trực tiếp |

**Luồng mới:**
```
UI → POST /api/v1/ingest { chunk_size, chunk_overlap, embedding_type }
   → asyncio.to_thread(run_ingestion) → ChromaDB
   → trả về list[str] chunks để hiển thị preview
```

---

## ✅ Phase 7 — Multi-Embedding (Tiếng Anh / Tiếng Việt)

**Mục tiêu:** Hỗ trợ 2 mô hình nhúng, lưu tách biệt vào ChromaDB riêng, chọn ngay từ UI.

### Cấu hình 2 mô hình

| Loại (`embedding_type`) | Model | Thư mục ChromaDB | Collection |
|---|---|---|---|
| `"en"` (mặc định) | `sentence-transformers/all-MiniLM-L6-v2` | `chroma_data_en/` | `knowledge_base_en` |
| `"vi"` | `intfloat/multilingual-e5-small` | `chroma_data_vi/` | `knowledge_base_vi` |

### Thay đổi từng file

| File | Thay đổi |
|---|---|
| `src/retrieval/vector_store.py` | Định nghĩa `EMBEDDING_CONFIGS` dict, cache embedding model theo loại (`_embedding_cache`), `retrieve_context(query, k, embedding_type)` |
| `src/retrieval/ingest.py` | Import `EMBEDDING_CONFIGS` từ `vector_store`, dùng đúng model/dir/collection theo `embedding_type` |
| `src/services/graph_service.py` | Thêm `embedding_type: str` vào `ChatbotState`; `retrieval_node` đọc `state["embedding_type"]` → truyền vào `retrieve_context` |
| `src/api/routes.py` | `ChatRequest` + `IngestRequest` thêm `embedding_type: str = "en"`; truyền vào `initial_state` và `run_ingestion` |
| `src/frontend/app.py` | `st.selectbox` chọn ngôn ngữ → map ra `"en"/"vi"` → đính kèm `embedding_type` trong mọi API call |

**Lưu ý quan trọng:** Tài liệu tiếng Việt phải được ingest với `embedding_type="vi"` và chat cũng phải chọn `"vi"` — hai bên phải khớp nhau.

---

## ✅ Phase 8 — Document Management (Quản lý File API)

**Mục tiêu:** Xem, upload, xóa file trong `docs/data/` trực tiếp từ Streamlit — không cần thao tác filesystem thủ công.

### Endpoints mới

| Method | Path | Mô tả |
|--------|------|-------|
| `GET` | `/api/v1/files` | Liệt kê tất cả file trong `docs/data/` |
| `POST` | `/api/v1/files` | Upload file (`multipart/form-data`) vào `docs/data/` |
| `DELETE` | `/api/v1/files/{filename}` | Xóa file, trả 404 nếu không tồn tại |

Cả POST lẫn DELETE đều dùng `Path(filename).name` để chống **path traversal**.

### Frontend

| Thành phần | Chi tiết |
|---|---|
| `st.expander("📁 Quản lý File Tài Liệu")` | Trong sidebar, riêng biệt với RAG management |
| `st.file_uploader` (`.txt`, `.md`) | Tự động gọi `POST /api/v1/files` khi chọn file mới; dùng `session_state["_uploaded_doc"]` để tránh re-upload |
| Danh sách file | Gọi `GET /api/v1/files` mỗi lần render; hiển thị từng file với nút `🗑️` riêng biệt |
| Xóa file | Gọi `DELETE /api/v1/files/{filename}` → `st.rerun()` để cập nhật danh sách ngay |

### Bugfix quan trọng — Upload qua web không đọc được tài liệu

**Root cause:** Nút "⚡ Nạp vào Knowledge Base" trước đây dùng `subprocess.run(ingest.py)` không truyền `embedding_type` → luôn ingest vào `chroma_data_en/` bất kể người dùng chọn model gì → khi chat dùng `"vi"`, truy vấn `chroma_data_vi/` trống.

**Fix:** Thay toàn bộ subprocess bằng 2 API call:
1. `POST /api/v1/files` để lưu file
2. `POST /api/v1/ingest` với đúng `embedding_type` từ selectbox

---

## Cấu trúc dự án hiện tại

```
claude bot/
├── .env                          # GROQ_API_KEY
├── .gitignore
├── CLAUDE.md                     # Quy ước dự án + quy tắc import src.
├── README.md
├── requirements.txt              # Tất cả dependencies
├── setup.cfg                     # flake8 + mypy config
├── chroma_data_en/               # ChromaDB — model tiếng Anh (tạo khi ingest lần đầu)
├── chroma_data_vi/               # ChromaDB — model tiếng Việt (tạo khi ingest lần đầu)
├── docs/
│   ├── data/                     # Tài liệu thô (txt, pdf, docx, csv, xlsx)
│   ├── project/
│   │   └── dify-logic-mapping.md
│   └── process/
│       └── project-plan.md
├── ops/
└── src/
    ├── __init__.py
    ├── main.py                   # FastAPI app, CORS, health check
    ├── api/
    │   └── routes.py             # Tất cả endpoints (chat, ingest, files CRUD)
    ├── core/
    │   └── utils.py              # get_logger()
    ├── frontend/
    │   └── app.py                # Streamlit UI (chat + RAG mgmt + file mgmt)
    ├── retrieval/
    │   ├── ingest.py             # run_ingestion(chunk_size, chunk_overlap, embedding_type)
    │   └── vector_store.py       # EMBEDDING_CONFIGS, retrieve_context(query, k, embedding_type)
    └── services/
        └── graph_service.py      # LangGraph graph, nodes, ChatbotState
```

---

## API Endpoints đầy đủ

| Method | Path | Body / Params | Mô tả |
|--------|------|---------------|-------|
| `GET` | `/health` | — | Health check |
| `POST` | `/api/v1/chat` | `{query, thread_id, embedding_type}` | Gửi câu hỏi, nhận trả lời |
| `POST` | `/api/v1/ingest` | `{chunk_size, chunk_overlap, embedding_type}` | Nạp/làm mới toàn bộ tài liệu vào ChromaDB |
| `GET` | `/api/v1/files` | — | Liệt kê file trong `docs/data/` |
| `POST` | `/api/v1/files` | `multipart: file` | Upload file vào `docs/data/` |
| `DELETE` | `/api/v1/files/{filename}` | — | Xóa file khỏi `docs/data/` |

---

## LangGraph State hiện tại

```python
class ChatbotState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]  # lịch sử hội thoại
    context: str           # context từ ChromaDB (chỉ khi needs_retrieval=True)
    needs_retrieval: bool  # kết quả phân loại câu hỏi
    embedding_type: str    # "en" hoặc "vi" — xác định model và collection ChromaDB
```

---

## Cách chạy hệ thống

```powershell
# Terminal 1 — Backend
uvicorn src.main:app --reload --port 8080

# Terminal 2 — Frontend
streamlit run src/frontend/app.py
```

**Quy trình nạp tài liệu (qua web):**
1. Mở Streamlit → chọn ngôn ngữ tài liệu (en/vi) ở selectbox
2. Upload file qua "📂 Tải lên tài liệu" → nhấn "⚡ Nạp vào Knowledge Base"
3. Hoặc dùng "⚙️ Quản lý Cơ sở dữ liệu" để tùy chỉnh chunk_size/overlap rồi nhấn "🔄 Cập nhật Database & Xem trước Chunks"

> ⚠️ Tài liệu tiếng Việt phải ingest với "Tiếng Việt" và chat cũng phải chọn "Tiếng Việt" — nếu không khớp sẽ không tìm được context.

---

## Dependencies hiện tại

```
fastapi, uvicorn, pydantic, python-dotenv
langgraph, langchain-core, langchain-groq
langchain-huggingface, langchain-community, langchain-chroma, langchain-text-splitters
chromadb, sentence-transformers
pypdf, docx2txt, pandas, openpyxl
streamlit, requests
flake8, mypy
# Phase 9
celery[redis], redis, psycopg[binary,pool], langgraph-checkpoint-postgres, httpx
```

---

## ✅ Phase 9 — Docker Compose + Celery + Facebook Messenger + PostgreSQL

**Mục tiêu:** Containerize hệ thống, giải quyết bài toán webhook timeout, tích hợp Facebook Messenger, persistent conversation state.

### Vấn đề cần giải quyết

| Vấn đề | Root Cause | Fix |
|---|---|---|
| Facebook webhook timeout | RAG mất 14+ giây, FB yêu cầu 200 OK trong 10s → retry → duplicate messages | Celery async: FastAPI nhận → enqueue → 200 OK ngay; Worker xử lý RAG độc lập |
| Mất lịch sử khi restart | MemorySaver lưu trong RAM | PostgresSaver: lưu checkpoints vào PostgreSQL |
| Khó deploy, thiếu isolation | Chạy trực tiếp trên host | Docker Compose: 6 services containerized |

### File mới / sửa

| File | Thay đổi |
|---|---|
| `requirements.txt` | Thêm celery[redis], psycopg[binary,pool], langgraph-checkpoint-postgres, httpx |
| `Dockerfile` | Image chung cho api, worker, flower, streamlit |
| `docker-compose.yml` | Orchestration: postgres, redis, api, worker, flower, streamlit |
| `.dockerignore` | Loại bỏ venv/, .env, chroma_data/ khỏi image |
| `.env.example` | Template env vars đầy đủ |
| `src/services/graph_service.py` | `_build_checkpointer()`: PostgresSaver nếu có DATABASE_URL, fallback MemorySaver |
| `src/services/celery_app.py` | Celery instance + task `process_messenger_message` + `_send_messenger_reply` |
| `src/api/messenger.py` | Webhook GET verify + POST receive (HMAC-SHA256) + enqueue Celery |
| `src/main.py` | Đăng ký `messenger_router` với prefix `/messenger` |
| `src/frontend/app.py` | Đọc `API_BASE_URL` từ env (backward-compatible) |

### Kiến trúc Docker Compose

```
postgres (port 5432)  ←── LangGraph checkpoint storage
redis    (port 6379)  ←── Celery broker + result backend
api      (port 8080)  ←── FastAPI: REST API + Facebook webhook
worker               ←── Celery: RAG processing + send Messenger reply
flower   (port 5555)  ←── Celery monitoring dashboard
streamlit(port 8501)  ←── Frontend UI
```

### Luồng xử lý Facebook Messenger

```
1. User gửi tin nhắn trên Facebook Messenger
2. Facebook POST → /messenger/webhook  (10s timeout)
3. FastAPI: verify HMAC-SHA256 (raw bytes) → enqueue Celery → 200 OK (< 1s)
4. Redis: lưu task vào queue
5. Celery Worker: RAG pipeline → PostgreSQL checkpoint → gửi reply
6. Facebook Graph API → user nhận reply
```

### Điểm kỹ thuật quan trọng

- **`autocommit=True` + `row_factory=dict_row`** trong PostgresSaver: thiếu một trong hai → crash
- **Lazy import** trong Celery task: tránh PostgreSQL connection pool fork corruption
- **Raw bytes cho HMAC**: phải đọc `await request.body()` trước khi parse JSON
- **Celery trên Windows**: dùng `--pool=solo` nếu test ngoài Docker

### Cách khởi động

```powershell
# Sao chép env template
cp .env.example .env
# Điền GROQ_API_KEY, FB_VERIFY_TOKEN, FB_APP_SECRET, FB_PAGE_ACCESS_TOKEN

# Build và khởi động toàn bộ stack
docker compose up --build

# Monitoring Celery tasks
# Mở http://localhost:5555

# Frontend
# Mở http://localhost:8501
```

### Endpoints mới

| Method | Path | Mô tả |
|--------|------|-------|
| `GET` | `/messenger/webhook` | Facebook webhook verification (hub.challenge) |
| `POST` | `/messenger/webhook` | Nhận tin nhắn Messenger, enqueue Celery task |

---

### ✅ Kết quả triển khai thực tế (2026-05-24)

**Tất cả 6 services đang chạy:**

| Service | Port | Status |
|---|---|---|
| FastAPI API | 8080 | ✅ Running |
| Streamlit | 8501 | ✅ Running |
| PostgreSQL | 5432 | ✅ Healthy |
| Redis | 6379 | ✅ Healthy |
| Celery Worker | — | ✅ Ready |
| Flower Dashboard | 5555 | ✅ Running |

**Đã xác nhận end-to-end:**
- Facebook gửi tin → API nhận webhook → enqueue Celery → 200 OK trong < 1s
- Worker xử lý RAG → gửi reply qua Facebook Graph API thành công
- PostgresSaver kết nối `postgres:5432/chatbot_db` — lịch sử hội thoại persistent

---

### Các vấn đề gặp phải và cách giải quyết

| Vấn đề | Nguyên nhân | Fix |
|---|---|---|
| `OSError: [Errno 5] Input/output error` khi build | `sentence-transformers → torch` kéo CUDA ~1.5GB, WSL2 disk bị đầy | Thêm bước cài `torch --index-url https://download.pytorch.org/whl/cpu` trước requirements.txt |
| `psycopg==3.1.19` conflict | `langgraph-checkpoint-postgres` yêu cầu `psycopg>=3.2.0` | Đổi pin version thành `>=` thay vì `==` |
| Docker WSL2 `input/output error` khi unpack layer | C: drive chỉ còn 3.4 GB trống, `docker_data.vhdx` phình 10+ GB | Chuyển Docker data sang D: (`CustomWslDistroDir=D:\Docker\DockerDesktopWSL`) — D: còn 260 GB |
| `flower` service crash: `No such command 'flower'` | Celery 5.x tách `flower` thành package riêng | Thêm `flower>=2.0.0` vào `requirements.txt` |
| Bot chỉ trả lời câu đầu, câu sau mất 58 giây | Worker tải `intfloat/multilingual-e5-small` từ HuggingFace lúc runtime | Thêm bước pre-download model vào Dockerfile lúc build |
| Facebook không gửi webhook dù đã subscribe events | Chỉ subscribe event type ở App level, chưa subscribe App vào Page cụ thể | Gọi `POST /{page-id}/subscribed_apps?subscribed_fields=messages` |

---

### Cấu hình Docker (đã áp dụng)

**Docker Desktop lưu data tại D: (không phải C:)**
- Settings: `CustomWslDistroDir = D:\Docker\DockerDesktopWSL`
- Lý do: C: chỉ có ~14 GB trống, build image cần 8-10 GB

**Dockerfile tối ưu:**
```dockerfile
ENV PYTHONDONTWRITEBYTECODE=1          # Không tạo .pyc → giảm số file
ENV HF_HOME=/app/.cache/huggingface    # Cache model trong image
RUN pip install torch --index-url https://download.pytorch.org/whl/cpu  # CPU-only ~192MB
RUN pip install --no-compile -r requirements.txt
RUN python -c "SentenceTransformer('intfloat/multilingual-e5-small')"   # Pre-cache model
```

**Tốc độ xử lý sau optimize:**
- Tin nhắn thường (không cần RAG): ~3-5 giây
- Tin nhắn cần RAG (tóm tắt, tra cứu): ~5-10 giây (trước optimize: 58 giây)

---

### Cấu trúc dự án sau Phase 9

```
claude bot/
├── Dockerfile                        # Image chung api/worker/flower/streamlit
├── docker-compose.yml                # 6 services
├── .dockerignore
├── .env.example
├── requirements.txt                  # + celery, redis, flower, psycopg, httpx
└── src/
    ├── api/
    │   ├── routes.py
    │   └── messenger.py              # NEW: Facebook webhook
    └── services/
        ├── graph_service.py          # PostgresSaver + MemorySaver fallback
        ├── celery_app.py             # NEW: Celery tasks
        └── ...
```

---

## ✅ Phase 10 — Advanced RAG (Semantic Chunking, Hybrid Search, HyDE, Rerank, MMR)

**Mục tiêu:** Nâng cấp toàn bộ pipeline RAG từ mức cơ bản (~5%) lên chuẩn production theo 4 lớp: Indexing → Query Transformation → Retrieval → Re-ranking.

### Đánh giá trước/sau

| Kỹ thuật | Trước | Sau |
|---|---|---|
| Chunking | RecursiveCharacter (cố định) | SemanticChunker + Recursive (chọn được) |
| Vector Index | HNSW mặc định | HNSW preset: fast/balanced/accurate |
| Query | Original query | HyDE + Query Decomposition (tùy bật) |
| Retrieval | Vector-only | Hybrid (BM25 + Vector + RRF) hoặc MMR |
| Re-ranking | Không có | Cross-Encoder Top-50 → Top-5 |

### Thay đổi từng file

| File | Thay đổi |
|---|---|
| `requirements.txt` | + `langchain-experimental`, + `rank-bm25` |
| `src/retrieval/vector_store.py` | `HNSW_PRESETS`, `CROSS_ENCODER_CONFIGS`, `save/load_chunks_for_bm25()`, `_reciprocal_rank_fusion()`, mở rộng `retrieve_context(use_hybrid, use_rerank, retrieval_mode)` |
| `src/retrieval/ingest.py` | `chunking_strategy`, `breakpoint_threshold_type/amount`, `hnsw_preset` params; lưu `chunks.json` cho BM25 |
| `src/services/graph_service.py` | `ChatbotState` 7 fields mới; `hyde_node`, `query_decomposition_node`; 2 router functions; graph 5 nodes + conditional edges |
| `src/api/routes.py` | `ChatRequest` + `IngestRequest` mở rộng với tất cả advanced params |
| `src/services/celery_app.py` | `initial_state` thêm 7 fields mới (tất cả disabled — Messenger ưu tiên tốc độ) |
| `src/frontend/app.py` | Expander "🔬 Cài đặt RAG nâng cao" với 5 controls; Expander "⚙️ Quản lý CSDL" với chunking strategy + HNSW preset |

### LangGraph Graph mới (Phase 10)

```
START → question_classifier_node
  ├─[no RAG]──────────────────────────→ call_llm_node → END
  ├─[decomp]→ query_decomposition_node
  │             ├─[+hyde]→ hyde_node → retrieval_node → call_llm_node → END
  │             └─[plain]──────────→ retrieval_node → call_llm_node → END
  ├─[hyde]──→ hyde_node ──────────→ retrieval_node → call_llm_node → END
  └─[plain]──────────────────────→ retrieval_node → call_llm_node → END
```

### ChatbotState sau Phase 10

```python
class ChatbotState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    context: str
    needs_retrieval: bool
    embedding_type: str        # "en" | "vi"
    use_hyde: bool             # bật HyDE
    hyde_query: str            # hypothetical document do LLM tạo
    use_decomposition: bool    # bật Query Decomposition
    sub_queries: list[str]     # danh sách sub-queries sau phân rã
    use_hybrid: bool           # bật Hybrid Search (BM25+Vector+RRF)
    use_rerank: bool           # bật Cross-Encoder reranking
    retrieval_mode: str        # "similarity" | "mmr"
```

### Điểm kỹ thuật quan trọng

- **chunks.json** lưu trong `chroma_data_*/chunks.json` — phải ingest lại để kích hoạt Hybrid Search
- **Cross-Encoder cold start** ~15s khi tải lần đầu — sau đó được cache
- **MMR + Rerank** không dùng cùng lúc — MMR tối ưu diversity, Rerank phá vỡ diversity
- **HyDE + Decomposition** cùng bật: sub_queries được ưu tiên, hyde_query không được dùng — có warning trong UI và log
- **Celery (Messenger):** tất cả advanced features disabled mặc định — Facebook có timeout 10s, Cross-Encoder sẽ làm timeout

### API Endpoints mở rộng

| Endpoint | Fields mới |
|---|---|
| `POST /api/v1/chat` | `use_hyde`, `use_decomposition`, `use_hybrid`, `use_rerank`, `retrieval_mode` |
| `POST /api/v1/ingest` | `chunking_strategy`, `breakpoint_threshold_type`, `breakpoint_threshold_amount`, `hnsw_preset` |

---

## ✅ Phase 11 — Bot Sale Điện Tử & Lead Generation

**Mục tiêu:** Biến bot thành nhân viên tư vấn bán hàng điện tử có nhân vật, tự động thu thập thông tin khách hàng tiềm năng (lead) và lưu vào Google Sheets.

### 11A — System Prompt Sales Persona

Thay toàn bộ prompt generic thành nhân vật **Hân** — nhân viên tư vấn cửa hàng điện tử.

| Tính năng | Chi tiết |
|---|---|
| Quy trình tư vấn 4 bước | Hỏi nhu cầu → Tư vấn sản phẩm → Xin SĐT → Xác nhận đơn |
| Xử lý từ chối | "Giá cao quá", "Để nghĩ thêm", "Bên khác rẻ hơn" — bot phản hồi đúng từng tình huống |
| Flexible product matching | Khi khách hỏi "iPhone 14" nhưng kho có "iPhone 14 Pro" → bot giới thiệu ngay thay vì nói "không có" |
| Không dùng Markdown | Messenger không render `*bold*`, `#header` → chỉ dùng plain text |

**File:** `src/services/graph_service.py` — system prompt trong `_prompt`

### 11B — Typing Indicator & Message Split (Phase 10B)

| Tính năng | Chi tiết |
|---|---|
| Typing indicator | Gửi `sender_action: "typing_on"` trước khi RAG pipeline chạy → khách thấy bot đang nhập |
| Mark seen | `sender_action: "mark_seen"` — xác nhận đã đọc tin nhắn |
| Split message | Reply > 2000 ký tự → tự động chia thành nhiều phần, gửi tuần tự với delay 0.5s |
| Fallback message | Khi hết retry → gửi "Xin lỗi, hệ thống đang gặp sự cố..." thay vì im lặng |

**File:** `src/services/celery_app.py` — `_send_messenger_reply()`, `_split_message()`

### 11C — Multi-turn Retrieval Context Fix

**Vấn đề:** Bot quên sản phẩm đã tư vấn khi khách nói "mua cái đó đi" — `retrieval_node` chỉ dùng câu hỏi hiện tại làm query, không có ngữ cảnh hội thoại.

**Fix:** Thêm `_build_retrieval_query()` kết hợp 6 tin nhắn gần nhất (HumanMessage đầy đủ, AIMessage giới hạn 120 ký tự đầu) → query phong phú hơn, ChromaDB tìm đúng sản phẩm đang thảo luận.

**File:** `src/services/graph_service.py` — `_build_retrieval_query()`, `retrieval_node`

### 11D — Lead Capture Service

**Vấn đề:** Cần lưu thông tin khách hàng có SĐT và tên sản phẩm quan tâm để nhân viên follow up.

| Thành phần | Chi tiết |
|---|---|
| Phone detection | Regex `(?<!\d)(0[3-9]\d{8}\|\+84[3-9]\d{8})(?!\d)` — khớp SĐT Việt Nam chuẩn |
| Deduplication | Không lưu lại nếu đã có `psid + phone` trong sheet |
| Product extraction | `_extract_product()` scan ngược AIMessages tìm brand name → trích snippet tên sản phẩm |
| Brand list | `_PRODUCT_BRANDS` module-level constant: iphone, samsung galaxy, xiaomi, oppo... |

**Files:** `src/services/lead_service.py`, `src/services/celery_app.py`

### 11E — Google Sheets Integration (Thay thế PostgreSQL leads)

**Lý do:** PostgreSQL lead table bất tiện quản lý — Google Sheets dễ chia sẻ và theo dõi hơn.

| Thành phần | Chi tiết |
|---|---|
| Service Account | Google Cloud service account key → `google_credentials.json` (KHÔNG commit) |
| Columns | STT \| Thời gian \| PSID \| Tên sản phẩm \| Số điện thoại \| Tin nhắn |
| Singleton client | `_sheet_instance` module-level — khởi tạo 1 lần, tái dùng mọi call |
| Auto header | `init_leads_table()` tạo header row nếu sheet trống |
| Lead API | `GET /api/v1/leads` → đọc từ Sheet → Streamlit Leads page hiển thị |

**Files:** `src/services/lead_service.py`, `src/api/routes.py`, `src/frontend/app.py`

**Dependencies mới:** `gspread>=6.0.0`, `google-auth>=2.0.0`

**Env vars mới:**
```
GOOGLE_SHEET_ID=<sheet_id_from_url>
GOOGLE_CREDENTIALS_PATH=/app/google_credentials.json
```

### 11F — Facebook Messenger Live

| Bước | Chi tiết |
|---|---|
| ngrok tunnel | `ngrok http 8081` → HTTPS URL expose container API ra internet |
| Webhook URL | Facebook App Dashboard → Webhook → `https://<ngrok-url>/messenger/webhook` |
| Verify Token | `duong_24032006` — khớp với `FB_VERIFY_TOKEN` trong `.env` |
| Port conflict | Windows `AgentService` chiếm port 8080 → đổi host port `8081:8080` trong `docker-compose.yml` |
| Subscribed events | `messages` — đã subscribe App vào Page |

### Các vấn đề gặp phải (Phase 11)

| Vấn đề | Root Cause | Fix |
|---|---|---|
| Bot quên sản phẩm khi hỏi "mua cái đó" | `retrieval_node` chỉ dùng current message | `_build_retrieval_query()` gộp 6 messages gần nhất |
| Bot nói "không có iPhone 14" dù có 14 Pro | System prompt yêu cầu tên nguyên văn quá cứng | Sửa quy tắc: tự nhiên giới thiệu sản phẩm tương tự |
| Leads page 500 error | `init_leads_table()` chỉ chạy ở worker, chưa chạy lúc API khởi động | Thêm `lifespan` event trong `main.py` |
| `ModuleNotFoundError: psycopg2` | Container chỉ có psycopg v3 | Rewrite `lead_service.py` dùng `gspread` (bỏ PostgreSQL hoàn toàn) |
| ngrok custom domain lỗi | Free plan không hỗ trợ custom subdomain | Chạy `ngrok http 8081` không có flag `--domain` |
| `_extract_product not defined` linter | Hàm định nghĩa sau chỗ gọi | Đưa hàm lên trước task definition |

---

## ✅ Phase 12 — Security, Performance & Code Quality Audit

**Mục tiêu:** Quét toàn bộ codebase, sửa 9 vấn đề thực tế — không phá vỡ logic hiện tại.

### Bảo mật (3 fix)

| Fix | File | Vấn đề | Thay đổi |
|-----|------|---------|----------|
| S1 | `src/main.py` | `allow_origins=["*"]` + `allow_credentials=True` vi phạm CORS spec | Đổi `allow_credentials=False` |
| S2 | `src/api/routes.py` | `str(e)` trong HTTP 500 lộ stack trace, credential path | Log server-side, trả về message chung |
| S3 | `docker-compose.yml`, `.env.example` | Flower dashboard port 5555 không có auth — lộ task args (SĐT khách) | `--basic_auth=${FLOWER_USER}:${FLOWER_PASSWORD}` |

### Hiệu suất (3 fix)

| Fix | File | Vấn đề | Thay đổi |
|-----|------|---------|----------|
| P1 | `src/services/lead_service.py` | Google Sheets client tạo mới mỗi call (3 I/O ops: auth + authorize + open) | Module-level `_sheet_instance` singleton |
| P2 | `src/retrieval/vector_store.py` | BM25Okapi rebuild từ đầu mỗi hybrid search query (~100-500ms) | `_bm25_cache` dict, cache theo `chroma_dir` |
| P3 | `src/services/celery_app.py` | `httpx.Client(timeout=10.0)` tạo TCP connection mới mỗi Messenger reply | `_get_http_client()` singleton |

### Chất lượng code (3 fix)

| Fix | File | Vấn đề | Thay đổi |
|-----|------|---------|----------|
| Q1 | `src/retrieval/ingest.py` | 8 `print()` không kiểm soát được log level | Thay bằng `_logger.info/warning()` |
| Q2 | `src/retrieval/vector_store.py` | `logging.getLogger()` thay vì `get_logger()` chuẩn dự án | Đổi sang `from src.core.utils import get_logger` |
| Q3 | `src/services/celery_app.py` | `_BRANDS` list khởi tạo lại mỗi lần `_extract_product()` chạy | Module-level `_PRODUCT_BRANDS: list[str]` constant |

### Không thay đổi (lý do)

- **Chroma client không cache** — intentional: đọc data mới nhất sau mỗi lần ingest
- **Auth cho /ingest, /files** — cần phối hợp với Streamlit frontend, để phase sau
- **Function decomposition** — quá rủi ro break logic hiện tại

---

## Cấu trúc dự án hiện tại (sau Phase 12)

```
claude bot/
├── Dockerfile
├── docker-compose.yml                # 6 services, Flower basic auth
├── .dockerignore
├── .env                              # KHÔNG commit — chứa API keys
├── .env.example                      # Template đầy đủ kể cả FLOWER_USER/PASSWORD
├── .gitignore                        # bao gồm google_credentials.json
├── google_credentials.json           # Service account key — KHÔNG commit
├── CLAUDE.md
├── requirements.txt                  # + gspread, google-auth
├── setup.cfg
├── chroma_data_en/
├── chroma_data_vi/
├── docs/
│   ├── data/
│   └── process/
│       └── project-plan.md
└── src/
    ├── main.py                       # lifespan event, CORS allow_credentials=False
    ├── api/
    │   ├── routes.py                 # + /leads endpoint, error masking
    │   └── messenger.py              # Facebook webhook (HMAC-SHA256)
    ├── core/
    │   └── utils.py
    ├── frontend/
    │   └── app.py                    # + Leads page với cột Sản phẩm quan tâm
    ├── retrieval/
    │   ├── ingest.py                 # logging thay print()
    │   └── vector_store.py           # BM25 cache, get_logger()
    └── services/
        ├── graph_service.py          # Sales persona prompt, _build_retrieval_query()
        ├── celery_app.py             # httpx singleton, _PRODUCT_BRANDS, _extract_product()
        └── lead_service.py           # Google Sheets singleton, save/get leads
```

---

## Cách chạy hệ thống (hiện tại)

```powershell
# 1. Sao chép env và điền giá trị
cp .env.example .env
# Cần điền: GROQ_API_KEY, FB_VERIFY_TOKEN, FB_APP_SECRET, FB_PAGE_ACCESS_TOKEN
#           GOOGLE_SHEET_ID, FLOWER_USER, FLOWER_PASSWORD

# 2. Đặt google_credentials.json vào thư mục gốc dự án

# 3. Build và khởi động toàn bộ stack
docker compose up --build

# 4. Expose API ra internet cho Facebook webhook
ngrok http 8081
# Lấy URL https://xxx.ngrok.io → điền vào Facebook App Dashboard

# Monitoring Celery:  http://localhost:5555  (đăng nhập với FLOWER_USER/PASSWORD)
# Frontend:           http://localhost:8501
# API docs:           http://localhost:8081/docs
```

**Lưu ý port:**
- API trong Docker container: `8080` (internal)
- API từ host máy: `8081` (do Windows AgentService chiếm port 8080)
- Streamlit: `8501`
- Flower: `5555` (yêu cầu đăng nhập)

## API Endpoints đầy đủ (sau Phase 12)

| Method | Path | Mô tả |
|--------|------|-------|
| `GET` | `/health` | Health check |
| `GET` | `/messenger/webhook` | Facebook webhook verification |
| `POST` | `/messenger/webhook` | Nhận tin nhắn Messenger, enqueue Celery task |
| `POST` | `/api/v1/chat` | Chat API (+ Advanced RAG params) |
| `POST` | `/api/v1/ingest` | Nạp tài liệu vào ChromaDB |
| `GET` | `/api/v1/files` | Liệt kê file trong `docs/data/` |
| `POST` | `/api/v1/files` | Upload file vào `docs/data/` |
| `DELETE` | `/api/v1/files/{filename}` | Xóa file |
| `GET` | `/api/v1/leads` | Danh sách lead từ Google Sheets |

## Dependencies đầy đủ

```
# Core
fastapi, uvicorn, pydantic, python-dotenv

# LangChain / LangGraph
langgraph, langgraph-checkpoint-postgres
langchain-core, langchain-groq, langchain-huggingface
langchain-community, langchain-chroma, langchain-text-splitters
langchain-experimental

# Vector Store & Embeddings
chromadb, sentence-transformers, rank-bm25

# Document loaders
pypdf, docx2txt, pandas, openpyxl

# Async & Infrastructure
celery[redis], redis, flower, psycopg[binary,pool], httpx

# Google Sheets (Lead storage)
gspread>=6.0.0, google-auth>=2.0.0

# Frontend
streamlit, requests

# Dev tools
flake8, mypy
```

---

## ⏳ Phase 13 — Production Hardening

**Mục tiêu:** Làm hệ thống ổn định và an toàn thực sự cho môi trường production — xử lý các tình huống edge case của Facebook Messenger và khắc phục các cấu hình còn mang tính development.

### 13A — Message Deduplication (10C)
**File:** `src/api/messenger.py`

Facebook **tự retry** POST webhook nếu không nhận 200 OK trong 10 giây → cùng tin nhắn bị xử lý 2-3 lần → khách nhận reply trùng lặp.

**Giải pháp:** Redis SET NX với `message.mid` làm key (TTL 24 giờ).
```python
def _is_duplicate(message_id: str) -> bool:
    key = f"msg_dedup:{message_id}"
    result = _redis_client.set(key, "1", nx=True, ex=86400)
    return result is None  # None = đã tồn tại = duplicate
```
Gọi trước `process_messenger_message.delay()` trong `_handle_messaging_event()`.

### 13B — MESSENGER_EMBEDDING_TYPE env var (10D-2)
**File:** `src/api/messenger.py`

Hiện tại hardcode `embedding_type="vi"` — không thể đổi sang `"en"` mà không sửa code.

```python
_MESSENGER_EMBEDDING_TYPE = os.getenv("MESSENGER_EMBEDDING_TYPE", "vi")
process_messenger_message.delay(..., embedding_type=_MESSENGER_EMBEDDING_TYPE)
```
Thêm `MESSENGER_EMBEDDING_TYPE=vi` vào `.env.example`.

### 13C — Dockerfile model cache fix (10D-3)
**File:** `Dockerfile`

- Đang download `multilingual-e5-large` (~500MB) nhưng không có chỗ nào trong code dùng model này
- Chưa download `all-MiniLM-L6-v2` (dùng cho `embedding_type="en"`) → cold start ~15s khi có request đầu tiên

```dockerfile
RUN python -c "
from sentence_transformers import SentenceTransformer
print('Downloading all-MiniLM-L6-v2...')
SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')
print('Downloading multilingual-e5-small...')
SentenceTransformer('intfloat/multilingual-e5-small')
print('Models cached OK')"
```

### 13D — Bỏ --reload khỏi docker-compose (10D-4)
**File:** `docker-compose.yml`

`--reload` watch file changes → chậm startup, tốn CPU, không phù hợp production.

```yaml
# Thay:
command: uvicorn src.main:app --host 0.0.0.0 --port 8080 --reload
# Bằng:
command: uvicorn src.main:app --host 0.0.0.0 --port 8080 --workers 2
```

### 13E — CORS restrict origins từ env (10E-1)
**File:** `src/main.py`

`allow_origins=["*"]` cho phép bất kỳ domain nào gọi API.

```python
_ALLOWED_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:8501").split(",")
app.add_middleware(CORSMiddleware, allow_origins=_ALLOWED_ORIGINS, ...)
```
Thêm `CORS_ORIGINS=http://localhost:8501` vào `.env.example`.

### 13F — Real health check (10E-2)
**File:** `src/main.py`

`/health` hiện trả về static `"status": "ok"` dù Postgres hay Redis đang down.

```python
@app.get("/health")
async def health_check() -> dict:
    checks = {}
    try:
        import psycopg
        with psycopg.connect(os.getenv("DATABASE_URL",""), connect_timeout=2): pass
        checks["postgres"] = "ok"
    except Exception:
        checks["postgres"] = "unreachable"
    try:
        import redis; r = redis.from_url(os.getenv("REDIS_URL",""), socket_timeout=2)
        r.ping(); checks["redis"] = "ok"
    except Exception:
        checks["redis"] = "unreachable"
    overall = "ok" if all(v == "ok" for v in checks.values()) else "degraded"
    return {"status": overall, "services": checks, "version": "1.0.0"}
```

### 13G — Rate limiting per PSID (10E-3)
**File:** `src/api/messenger.py`

User gửi 50 tin nhắn liên tiếp → 50 Celery tasks xếp hàng → worker nghẽn.

```python
_RATE_LIMIT = int(os.getenv("MESSENGER_RATE_LIMIT_PER_MIN", "10"))

def _is_rate_limited(psid: str) -> bool:
    key = f"rate:{psid}:{int(time.time() // 60)}"
    count = _redis_client.incr(key)
    if count == 1:
        _redis_client.expire(key, 70)
    return count > _RATE_LIMIT
```

### 13H — Worker max-tasks-per-child (10E-4)
**File:** `docker-compose.yml`

Sau nhiều requests nặng (embedding + ChromaDB), worker process có thể bị memory leak.

```yaml
command: celery -A src.services.celery_app worker --loglevel=info --concurrency=2 --max-tasks-per-child=100
```

---

## ⏳ Phase 14 — HTTPS & Production Deploy

**Mục tiêu:** Chạy hệ thống với domain thật + SSL, thay thế ngrok bằng infrastructure cố định.

Facebook **bắt buộc** webhook URL phải là HTTPS — ngrok chỉ là giải pháp tạm thời cho dev.

### Các bước cần làm

| Bước | Chi tiết |
|------|----------|
| `nginx/default.conf` | Reverse proxy HTTP→HTTPS, SSL termination, `proxy_pass http://api:8080` |
| `docker-compose.prod.yml` | Thêm service `nginx` (port 80/443) + `certbot` (Let's Encrypt) |
| DNS | Trỏ domain về IP server, cấu hình A record |
| SSL | `certbot certonly` lấy certificate, auto-renew |
| Facebook webhook | Cập nhật URL từ `https://xxx.ngrok.io` → `https://yourdomain.com` |

### Cấu trúc file mới

```
claude bot/
├── nginx/
│   └── default.conf              # nginx config (HTTP → HTTPS, proxy_pass)
├── docker-compose.yml            # Dev (giữ nguyên)
└── docker-compose.prod.yml       # Production (+ nginx + certbot)
```

---

## ⏳ Phase 15 — Automated Tests

**Mục tiêu:** Đảm bảo thay đổi code không phá vỡ logic webhook + signature verification + deduplication.

### Các test cần tạo

**File:** `tests/test_messenger.py`

| Test | Mô tả | Kỳ vọng |
|------|--------|---------|
| `test_webhook_verify_success` | GET với token đúng | HTTP 200, trả về `hub.challenge` |
| `test_webhook_verify_wrong_token` | GET với token sai | HTTP 403 |
| `test_hmac_valid_signature` | POST với HMAC đúng | Không raise exception |
| `test_hmac_invalid_signature` | POST với HMAC sai | HTTP 403 |
| `test_duplicate_message_skipped` | Cùng `mid` gửi 2 lần | Celery `delay()` chỉ được gọi 1 lần |

### Cấu trúc file mới

```
tests/
├── __init__.py
├── conftest.py       # FastAPI TestClient, mock Redis, mock Celery
└── test_messenger.py
```

**Dependencies mới:** `pytest>=8.0.0`, `httpx[test]` (thêm vào `requirements.txt` hoặc `requirements-dev.txt`)

---

## ⏳ Phase 16 — Admin UI (Nice to have)

**Mục tiêu:** Cho phép xem toàn bộ lịch sử hội thoại Messenger từ Streamlit — hữu ích cho việc review chat logs và debug.

### API mới

**File:** `src/api/routes.py`

```python
@router.get("/messenger/conversations")
async def list_conversations() -> dict:
    """Liệt kê thread_id đang có trong PostgreSQL LangGraph checkpoints."""

@router.get("/messenger/conversations/{thread_id}")
async def get_conversation(thread_id: str) -> dict:
    """Lấy toàn bộ lịch sử tin nhắn của một thread."""
```

### UI mới

**File:** `src/frontend/app.py`

Thêm tab "📱 Messenger Monitor" trong Streamlit:
- Danh sách conversations (thread_id, thời gian gần nhất, số tin nhắn)
- Click vào conversation → hiển thị toàn bộ lịch sử hỏi/đáp
- Filter theo ngày, tìm kiếm theo PSID
