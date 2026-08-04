# src

Chứa toàn bộ **mã nguồn sản phẩm** — điểm trung tâm duy nhất cho code.

## Nội dung hiện tại

- `main.py` — Entrypoint FastAPI: khởi tạo app, CORS, gắn router, `GET /health`
- `api/` — `routes.py` (REST API: chat, ingest, files, leads), `messenger.py` (webhook Facebook Messenger)
- `core/` — Tiện ích dùng chung (logger `get_logger()`, ...)
- `frontend/` — `app.py`, giao diện Streamlit (chat thử, quản lý tài liệu RAG, xem lead)
- `retrieval/` — `ingest.py` (nạp tài liệu vào ChromaDB), `vector_store.py` (RAG: similarity/MMR/Hybrid Search + rerank)
- `services/` — `graph_service.py` (pipeline LangGraph + LLM), `celery_app.py` (worker xử lý Messenger bất đồng bộ), `lead_service.py` (lưu lead vào Google Sheets)

## Dành cho AI Agent

Mọi code sản phẩm đều nằm ở đây — agent không cần đoán mò vị trí file, giảm thiểu sai sót và tăng tốc độ làm việc. Xem [`../README.md`](../README.md) để biết roadmap và kiến trúc tổng thể.
