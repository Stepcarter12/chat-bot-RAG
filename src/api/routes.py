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


# ── Schema đầu vào / đầu ra ───────────────────────────────────────────────────

class ChatRequest(BaseModel):
    query: str                      # câu hỏi của người dùng
    thread_id: str                  # định danh phiên để quản lý bộ nhớ
    embedding_type: str = "en"      # loại mô hình nhúng: "en" hoặc "vi"
    # ── Advanced RAG controls ─────────────────────────────────────────────────
    use_hyde: bool = False          # HyDE: tạo hypothetical doc trước retrieval
    use_decomposition: bool = False # Phân rã câu hỏi phức tạp thành sub-queries
    use_hybrid: bool = False        # Hybrid Search: BM25 + Vector + RRF
    use_rerank: bool = False        # Cross-Encoder rerank Top-50 → Top-5
    retrieval_mode: str = "similarity"  # "similarity" | "mmr"


class ChatResponse(BaseModel):
    answer: str
    thread_id: str


class IngestRequest(BaseModel):
    chunk_size: int = 500
    chunk_overlap: int = 50
    embedding_type: str = "en"      # loại mô hình nhúng: "en" hoặc "vi"
    # ── Advanced Indexing controls ────────────────────────────────────────────
    chunking_strategy: str = "recursive"            # "recursive" | "semantic"
    breakpoint_threshold_type: str = "percentile"   # loại ngưỡng cho SemanticChunker
    breakpoint_threshold_amount: float = 95.0       # giá trị ngưỡng
    hnsw_preset: str = "balanced"                   # "fast" | "balanced" | "accurate"


class IngestResponse(BaseModel):
    chunks: list[str]
    total: int


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    _logger.info(
        "Nhận request: thread_id=%s, query='%s', hyde=%s, decomp=%s, hybrid=%s, rerank=%s, mode=%s",
        request.thread_id, request.query,
        request.use_hyde, request.use_decomposition,
        request.use_hybrid, request.use_rerank, request.retrieval_mode,
    )
    config: RunnableConfig = {"configurable": {"thread_id": request.thread_id}}

    # Khởi tạo toàn bộ ChatbotState — bao gồm tất cả Advanced RAG fields
    initial_state: ChatbotState = {
        "messages": [HumanMessage(content=request.query)],
        "context": "",
        "needs_retrieval": False,
        "embedding_type": request.embedding_type,
        # Advanced RAG
        "use_hyde": request.use_hyde,
        "hyde_query": "",
        "use_decomposition": request.use_decomposition,
        "sub_queries": [],
        "use_hybrid": request.use_hybrid,
        "use_rerank": request.use_rerank,
        "retrieval_mode": request.retrieval_mode,
    }

    result = graph_app.invoke(initial_state, config=config)
    answer = result["messages"][-1].content
    _logger.info("Trả lời xong: thread_id=%s", request.thread_id)
    return ChatResponse(answer=answer, thread_id=request.thread_id)


@router.post("/ingest", response_model=IngestResponse)
async def ingest(request: IngestRequest) -> IngestResponse:
    _logger.info(
        "Bắt đầu ingest: chunk_size=%d, overlap=%d, embedding=%s, strategy=%s, hnsw=%s",
        request.chunk_size, request.chunk_overlap,
        request.embedding_type, request.chunking_strategy, request.hnsw_preset,
    )
    try:
        # Chạy blocking I/O trong thread pool để không block event loop
        chunks = await asyncio.to_thread(
            run_ingestion,
            request.chunk_size,
            request.chunk_overlap,
            embedding_type=request.embedding_type,
            chunking_strategy=request.chunking_strategy,
            breakpoint_threshold_type=request.breakpoint_threshold_type,
            breakpoint_threshold_amount=request.breakpoint_threshold_amount,
            hnsw_preset=request.hnsw_preset,
        )
    except Exception as e:
        _logger.error("Lỗi khi ingest: %s", e)
        raise HTTPException(status_code=500, detail="Lỗi hệ thống khi ingest, vui lòng thử lại.")
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
    content = await file.read()
    # Dùng thread pool để không block event loop khi ghi file lớn
    await asyncio.to_thread(dest.write_bytes, content)
    _logger.info("Đã lưu file: %s (%d bytes)", safe_name, len(content))
    return {"filename": safe_name}


@router.get("/leads")
async def get_leads() -> dict:
    """Trả về danh sách lead thu thập từ Messenger (lưu trong Google Sheets)."""
    try:
        from src.services.lead_service import get_all_leads
        rows = await asyncio.to_thread(get_all_leads)
    except Exception as e:
        _logger.error("Lỗi khi đọc leads: %s", e)
        raise HTTPException(status_code=500, detail="Lỗi hệ thống khi đọc leads, vui lòng thử lại.")
    return {"leads": rows, "total": len(rows)}


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
