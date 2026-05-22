from pathlib import Path

from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings

_PROJECT_ROOT = Path(__file__).parent.parent.parent

# Cấu hình mô hình nhúng: embedding_type → (model_name, chroma_dir, collection_name)
EMBEDDING_CONFIGS: dict[str, tuple[str, str, str]] = {
    "en": (
        "sentence-transformers/all-MiniLM-L6-v2",
        str(_PROJECT_ROOT / "chroma_data_en"),
        "knowledge_base_en",
    ),
    "vi": (
        "intfloat/multilingual-e5-small",
        str(_PROJECT_ROOT / "chroma_data_vi"),
        "knowledge_base_vi",
    ),
}

# Cache từng embedding model theo loại ngôn ngữ để tránh tải lại nhiều lần
_embedding_cache: dict[str, HuggingFaceEmbeddings] = {}


def _get_embeddings(embedding_type: str) -> HuggingFaceEmbeddings:
    """Khởi tạo embedding model một lần rồi cache lại theo loại ngôn ngữ."""
    if embedding_type not in _embedding_cache:
        model_name, _, _ = EMBEDDING_CONFIGS[embedding_type]
        _embedding_cache[embedding_type] = HuggingFaceEmbeddings(model_name=model_name)
    return _embedding_cache[embedding_type]


def retrieve_context(query: str, k: int = 5, embedding_type: str = "en") -> str:
    """Tạo fresh Chroma connection mỗi lần để đọc data mới nhất sau ingest."""
    _, chroma_dir, collection_name = EMBEDDING_CONFIGS[embedding_type]
    embeddings = _get_embeddings(embedding_type)
    store = Chroma(
        collection_name=collection_name,
        embedding_function=embeddings,
        persist_directory=chroma_dir,
    )
    docs = store.similarity_search(query, k=k)
    if not docs:
        return ""
    return "\n\n".join(doc.page_content for doc in docs)
