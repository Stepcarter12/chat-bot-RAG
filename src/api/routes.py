import asyncio
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel

from src.core.utils import get_logger
from src.retrieval.ingest import run_ingestion
from src.services.graph_service import ChatbotState, app as graph_app

router = APIRouter()
_logger = get_logger(__name__)

_DOCS_DATA_DIR = Path(__file__).parent.parent.parent / "docs" / "data"


# Schema đầu vào - ánh xạ từ Start Node trong dify-logic-mapping.md
class ChatRequest(BaseModel):
    query: str                    # câu hỏi của người dùng
    thread_id: str                # định danh phiên để quản lý bộ nhớ
    embedding_type: str = "en"   # loại mô hình nhúng: "en" hoặc "vi"


# Schema đầu ra
class ChatResponse(BaseModel):
    answer: str
    thread_id: str


# Schema cho endpoint ingest
class IngestRequest(BaseModel):
    chunk_size: int = 500
    chunk_overlap: int = 50
    embedding_type: str = "en"   # loại mô hình nhúng: "en" hoặc "vi"


class IngestResponse(BaseModel):
    chunks: list[str]
    total: int


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    _logger.info("Nhận request: thread_id=%s, query='%s'", request.thread_id, request.query)
    config: RunnableConfig = {"configurable": {"thread_id": request.thread_id}}
    initial_state: ChatbotState = {
        "messages": [HumanMessage(content=request.query)],
        "context": "",
        "needs_retrieval": False,
        "embedding_type": request.embedding_type,
    }
    result = graph_app.invoke(initial_state, config=config)
    answer = result["messages"][-1].content
    _logger.info("Trả lời xong: thread_id=%s", request.thread_id)
    return ChatResponse(answer=answer, thread_id=request.thread_id)


@router.post("/ingest", response_model=IngestResponse)
async def ingest(request: IngestRequest) -> IngestResponse:
    _logger.info("Bắt đầu ingest: chunk_size=%d, chunk_overlap=%d", request.chunk_size, request.chunk_overlap)
    try:
        # Chạy blocking I/O trong thread pool để không block event loop
        chunks = await asyncio.to_thread(
            run_ingestion,
            request.chunk_size,
            request.chunk_overlap,
            embedding_type=request.embedding_type,
        )
    except Exception as e:
        _logger.error("Lỗi khi ingest: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
    _logger.info("Ingest xong: %d chunks", len(chunks))
    return IngestResponse(chunks=chunks, total=len(chunks))


@router.get("/files")
async def list_files() -> dict:
    """Liệt kê tất cả file trong docs/data/."""
    _DOCS_DATA_DIR.mkdir(parents=True, exist_ok=True)
    files = [f.name for f in sorted(_DOCS_DATA_DIR.iterdir()) if f.is_file()]
    return {"files": files}


@router.post("/files", status_code=201)
async def upload_file(file: UploadFile = File(...)) -> dict:
    """Lưu file upload vào docs/data/."""
    _DOCS_DATA_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = Path(file.filename or "upload").name  # chống path traversal
    dest = _DOCS_DATA_DIR / safe_name
    dest.write_bytes(await file.read())
    _logger.info("Đã lưu file: %s", safe_name)
    return {"filename": safe_name}


@router.delete("/files/{filename}")
async def delete_file(filename: str) -> dict:
    """Xóa file khỏi docs/data/."""
    safe_name = Path(filename).name  # chống path traversal
    target = _DOCS_DATA_DIR / safe_name
    if not target.exists():
        raise HTTPException(status_code=404, detail=f"File '{safe_name}' không tồn tại.")
    try:
        target.unlink()
        _logger.info("Đã xóa file: %s", safe_name)
    except OSError as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"deleted": safe_name}
