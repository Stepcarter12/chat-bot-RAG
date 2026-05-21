from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings

# Khởi tạo embedding model một lần duy nhất
_embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")

# Kết nối tới ChromaDB lưu trên đĩa
_vector_store = Chroma(
    collection_name="knowledge_base",
    embedding_function=_embeddings,
    persist_directory="./chroma_data",
)


def retrieve_context(query: str, k: int = 5) -> str:
    """Tìm kiếm và trả về top-k đoạn văn bản liên quan nhất.

    Không lọc theo score vì model all-MiniLM-L6-v2 cho điểm thấp với
    văn bản tiếng Việt nhưng vẫn tìm đúng nội dung.
    """
    docs = _vector_store.similarity_search(query, k=k)
    if not docs:
        return ""
    return "\n\n".join(doc.page_content for doc in docs)
