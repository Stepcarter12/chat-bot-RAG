import sys
from pathlib import Path

# Khi chạy trực tiếp qua subprocess, project root chưa có trong sys.path —
# thêm vào để 'src.' import hoạt động đúng
_PROJECT_ROOT_INIT = Path(__file__).parent.parent.parent
if str(_PROJECT_ROOT_INIT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT_INIT))

# Buộc stdout dùng UTF-8 để tránh UnicodeEncodeError trên Windows (cp1252)
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

import pandas as pd
from langchain_chroma import Chroma
from langchain_community.document_loaders import (
    CSVLoader,
    DirectoryLoader,
    Docx2txtLoader,
    PyPDFLoader,
    TextLoader,
)
from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

from src.core.utils import get_logger
from src.retrieval.vector_store import EMBEDDING_CONFIGS, HNSW_PRESETS, save_chunks_for_bm25

_logger = get_logger(__name__)

# Tính đường dẫn tuyệt đối từ vị trí file, không phụ thuộc vào thư mục gọi lệnh
_PROJECT_ROOT = Path(__file__).parent.parent.parent
_DOCS_DATA_DIR = str(_PROJECT_ROOT / "docs" / "data")

# Cấu hình từng loại file: glob pattern → (loader class, kwargs)
_LOADERS: dict = {
    "**/*.txt":  (TextLoader,     {"encoding": "utf-8"}),
    "**/*.pdf":  (PyPDFLoader,    {}),
    "**/*.docx": (Docx2txtLoader, {}),
    "**/*.csv":  (CSVLoader,      {"encoding": "utf-8"}),
}


def _load_excel(file_path: Path) -> list[Document]:
    """
    Đọc file Excel, chuyển từng hàng thành một Document riêng.
    Mỗi hàng = 1 sản phẩm → retrieval chính xác hơn so với dump cả sheet.
    Tự động bỏ qua hàng tổng/footer (Tổng cộng, Total, Grand Total, v.v.)
    Thêm "Loại sản phẩm" vào chunk để vector search phân biệt danh mục.
    """
    # Từ khóa nhận diện hàng tổng/footer — case-insensitive
    _SKIP_KEYWORDS = {"tổng", "tổng cộng", "total", "grand total", "subtotal", "cộng"}

    dfs: dict = pd.read_excel(file_path, sheet_name=None, engine="openpyxl")
    docs = []
    for sheet_name, df in dfs.items():
        # Xóa hàng hoàn toàn trống
        df = df.dropna(how="all")
        # Tìm cột "Loại sản phẩm" trong Excel
        loai_col = next((c for c in df.columns if "loại" in c.lower() or "loai" in c.lower()
                         or "danh mục" in c.lower() or "category" in c.lower()), None)

        for row_idx, row in df.iterrows():
            # Chuyển từng cặp (cột: giá trị) thành dòng text có nghĩa
            lines = []
            is_summary_row = False
            for col in df.columns:
                val = row[col]
                if pd.notna(val) and str(val).strip():
                    val_str = str(val).strip()
                    # Bỏ qua hàng tổng/footer dựa trên giá trị cột đầu tiên
                    if not lines and val_str.lower() in _SKIP_KEYWORDS:
                        is_summary_row = True
                        break
                    lines.append(f"{col}: {val_str}")
            if not lines or is_summary_row:
                continue

            # Đọc category từ cột "Loại sản phẩm" trong Excel
            if loai_col and pd.notna(row.get(loai_col)) and str(row[loai_col]).strip():
                category = str(row[loai_col]).strip()
            else:
                category = "Sản phẩm công nghệ"

            # Thêm "Loại sản phẩm" đầu chunk để embedding capture được danh mục
            lines.insert(0, f"Loại sản phẩm: {category}")

            content = "\n".join(lines)
            docs.append(Document(
                page_content=content,
                metadata={
                    "source": str(file_path),
                    "sheet": sheet_name,
                    "row": int(row_idx) + 2,
                    "category": category,  # dùng cho ChromaDB metadata filter
                },
            ))
    return docs


def run_ingestion(
    chunk_size: int = 500,
    chunk_overlap: int = 50,
    docs_dir: str = _DOCS_DATA_DIR,
    embedding_type: str = "en",
    chunking_strategy: str = "recursive",
    breakpoint_threshold_type: str = "percentile",
    breakpoint_threshold_amount: float = 95.0,
    hnsw_preset: str = "balanced",
) -> list[str]:
    """
    Nạp tài liệu từ docs/data vào ChromaDB và trả về danh sách text của các chunks.

    Args:
        chunk_size:                 Kích thước chunk (chỉ dùng khi chunking_strategy="recursive")
        chunk_overlap:              Độ chồng lấn chunk (chỉ dùng khi chunking_strategy="recursive")
        docs_dir:                   Thư mục chứa tài liệu nguồn
        embedding_type:             "en" hoặc "vi" — chọn embedding model và ChromaDB collection
        chunking_strategy:          "recursive" (mặc định) hoặc "semantic"
        breakpoint_threshold_type:  Loại ngưỡng cho SemanticChunker:
                                    "percentile" | "standard_deviation" | "interquartile"
        breakpoint_threshold_amount: Giá trị ngưỡng (mặc định 95.0 cho percentile)
        hnsw_preset:                Cấu hình HNSW: "fast" | "balanced" | "accurate"

    Returns:
        Danh sách text của các chunks đã nạp vào ChromaDB.
    """
    if embedding_type not in EMBEDDING_CONFIGS:
        raise ValueError(
            f"embedding_type không hợp lệ: '{embedding_type}'. Chọn: {list(EMBEDDING_CONFIGS)}"
        )
    if hnsw_preset not in HNSW_PRESETS:
        raise ValueError(
            f"hnsw_preset không hợp lệ: '{hnsw_preset}'. Chọn: {list(HNSW_PRESETS)}"
        )

    model_name, chroma_dir, collection_name = EMBEDDING_CONFIGS[embedding_type]
    data_path = Path(docs_dir)
    all_documents: list[Document] = []

    # ── 1. Load tài liệu từ nhiều định dạng ─────────────────────────────────
    for glob, (loader_cls, kwargs) in _LOADERS.items():
        loader = DirectoryLoader(
            docs_dir,
            glob=glob,
            loader_cls=loader_cls,
            loader_kwargs=kwargs,
            silent_errors=True,
        )
        all_documents.extend(loader.load())

    # Nạp Excel (.xlsx, .xls) riêng qua pandas
    for ext in ("**/*.xlsx", "**/*.xls"):
        for excel_file in data_path.glob(ext):
            all_documents.extend(_load_excel(excel_file))

    if not all_documents:
        _logger.warning("Không tìm thấy tài liệu nào trong '%s'.", docs_dir)
        return []

    # ── 2. Khởi tạo embedding model (cần trước khi SemanticChunker dùng) ────
    _logger.info("Tìm thấy %d tài liệu thô. Đang khởi tạo embedding model '%s'...", len(all_documents), model_name)
    embeddings = HuggingFaceEmbeddings(model_name=model_name)

    # ── 3. Chunking theo chiến lược được chọn ────────────────────────────────
    if chunking_strategy == "semantic":
        # SemanticChunker phân tích ngữ nghĩa để tìm điểm ngắt tự nhiên giữa các chủ đề
        # ⚠️ Chậm hơn recursive vì gọi embedding API nhiều lần trong quá trình splitting
        from langchain_experimental.text_splitter import SemanticChunker  # noqa: PLC0415

        splitter = SemanticChunker(
            embeddings=embeddings,
            breakpoint_threshold_type=breakpoint_threshold_type,
            breakpoint_threshold_amount=breakpoint_threshold_amount,
        )
        _logger.info(
            "Dùng SemanticChunker (threshold_type=%s, amount=%s)...",
            breakpoint_threshold_type, breakpoint_threshold_amount,
        )
        _logger.warning("SemanticChunker gọi embedding API nhiều lần — có thể mất vài phút cho tài liệu lớn.")
    else:
        # RecursiveCharacterTextSplitter: cắt theo kích thước cố định, nhanh hơn
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size, chunk_overlap=chunk_overlap
        )
        _logger.info(
            "Dùng RecursiveCharacterTextSplitter (size=%d, overlap=%d)...",
            chunk_size, chunk_overlap,
        )

    chunks = splitter.split_documents(all_documents)
    _logger.info("Tạo được %d chunks.", len(chunks))

    # ── 4. Xóa collection cũ để tránh duplicate ──────────────────────────────
    _old = Chroma(
        collection_name=collection_name,
        embedding_function=embeddings,
        persist_directory=chroma_dir,
    )
    _old.delete_collection()

    # ── 5. Tạo collection mới với HNSW preset ────────────────────────────────
    # HNSW params chỉ áp dụng lúc collection được tạo lần đầu
    # Việc delete_collection() + from_documents() đảm bảo preset luôn được áp dụng
    collection_metadata = HNSW_PRESETS[hnsw_preset]
    _logger.info("Tạo ChromaDB collection '%s' với HNSW preset='%s': %s", collection_name, hnsw_preset, collection_metadata)

    Chroma.from_documents(
        documents=chunks,
        embedding=embeddings,
        collection_name=collection_name,
        persist_directory=chroma_dir,
        collection_metadata=collection_metadata,
    )

    # ── 6. Lưu chunk texts xuống JSON để BM25 dùng khi Hybrid Search ─────────
    # Bước này PHẢI sau khi Chroma.from_documents() thành công
    # Lý do: tránh để chunks.json lệch với vector store nếu có lỗi giữa chừng
    chunk_texts = [chunk.page_content for chunk in chunks]
    save_chunks_for_bm25(chunk_texts, chroma_dir)

    _logger.info("Đã nạp thành công %d chunks vào ChromaDB (%s).", len(chunks), collection_name)
    return chunk_texts


if __name__ == "__main__":
    run_ingestion()
