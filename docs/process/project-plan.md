# Tổng kết Dự án AI Chatbot — Phase 1 → 8

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
```
