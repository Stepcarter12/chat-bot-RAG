import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings

from src.core.utils import get_logger

if TYPE_CHECKING:
    from rank_bm25 import BM25Okapi
    from sentence_transformers import CrossEncoder

_logger = get_logger(__name__)

_PROJECT_ROOT = Path(__file__).parent.parent.parent

# ── Cấu hình embedding model theo ngôn ngữ ───────────────────────────────────
# Format: embedding_type → (model_name, chroma_dir, collection_name)
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

# ── Cross-Encoder cho Re-ranking (Top50 → Top5) ──────────────────────────────
# Cross-Encoder ghép cặp (query, document) để cho điểm chính xác hơn Bi-Encoder
CROSS_ENCODER_CONFIGS: dict[str, str] = {
    "en": "cross-encoder/ms-marco-MiniLM-L-6-v2",
    "vi": "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1",
}

# ── HNSW Presets: đánh đổi tốc độ vs độ chính xác ───────────────────────────
# M: số cạnh tối đa mỗi node (tăng → chính xác hơn, tốn RAM hơn)
# construction_ef: độ rộng tìm kiếm lúc build index (tăng → index tốt hơn, build chậm hơn)
# search_ef: độ rộng tìm kiếm lúc query (tăng → chính xác hơn, query chậm hơn)
HNSW_PRESETS: dict[str, dict[str, object]] = {
    "fast": {
        "hnsw:M": 8,
        "hnsw:construction_ef": 100,
        "hnsw:search_ef": 50,
    },
    "balanced": {
        "hnsw:M": 16,
        "hnsw:construction_ef": 200,
        "hnsw:search_ef": 100,
    },
    "accurate": {
        "hnsw:M": 32,
        "hnsw:construction_ef": 400,
        "hnsw:search_ef": 200,
    },
}

# ── Cache embedding model (tránh tải lại mỗi lần query) ──────────────────────
_embedding_cache: dict[str, HuggingFaceEmbeddings] = {}

# ── Cache Cross-Encoder model (lazy load — tải lần đầu khi cần) ─────────────
_cross_encoder_cache: dict[str, "CrossEncoder"] = {}

# ── Cache BM25 index (rebuild tốn ~100-500ms, cache theo chroma_dir) ─────────
_bm25_cache: dict[str, "BM25Okapi"] = {}


def _get_embeddings(embedding_type: str) -> HuggingFaceEmbeddings:
    """Khởi tạo embedding model một lần rồi cache lại theo loại ngôn ngữ."""
    if embedding_type not in _embedding_cache:
        model_name, _, _ = EMBEDDING_CONFIGS[embedding_type]
        _embedding_cache[embedding_type] = HuggingFaceEmbeddings(model_name=model_name)
    return _embedding_cache[embedding_type]


def _get_cross_encoder(embedding_type: str) -> "CrossEncoder":
    """
    Lazy load và cache Cross-Encoder model theo ngôn ngữ.
    Import nằm trong hàm để tránh load nặng lúc khởi động server.
    """
    if embedding_type not in _cross_encoder_cache:
        from sentence_transformers import CrossEncoder  # noqa: PLC0415
        model_name = CROSS_ENCODER_CONFIGS.get(embedding_type, CROSS_ENCODER_CONFIGS["en"])
        _logger.info("Đang tải Cross-Encoder model: %s", model_name)
        _cross_encoder_cache[embedding_type] = CrossEncoder(model_name)
        _logger.info("Tải Cross-Encoder xong: %s", model_name)
    return _cross_encoder_cache[embedding_type]


# ── Helpers BM25: lưu/đọc chunk texts ────────────────────────────────────────

def _get_chunks_path(chroma_dir: str) -> Path:
    """Trả về đường dẫn file JSON lưu chunk texts cho BM25."""
    return Path(chroma_dir) / "chunks.json"


def save_chunks_for_bm25(texts: list[str], chroma_dir: str) -> None:
    """
    Ghi danh sách chunk texts xuống file JSON sau mỗi lần ingest.
    BM25 cần corpus văn bản gốc (không phải vector) để tính điểm.
    """
    path = _get_chunks_path(chroma_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(texts, ensure_ascii=False), encoding="utf-8")
    _logger.info("Đã lưu %d chunk texts vào %s", len(texts), path)


def load_chunks_for_bm25(chroma_dir: str) -> list[str]:
    """
    Đọc chunk texts từ file JSON.
    Trả về [] nếu file chưa tồn tại (cần ingest trước khi dùng hybrid search).
    """
    path = _get_chunks_path(chroma_dir)
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


# ── RRF: hợp nhất nhiều danh sách xếp hạng ───────────────────────────────────

def _reciprocal_rank_fusion(ranked_lists: list[list[str]], k: int = 60) -> list[str]:
    """
    Reciprocal Rank Fusion — hợp nhất kết quả từ nhiều retriever khác nhau.

    Công thức: Score(d) = Σ 1/(k + rank_i(d))
    - k=60 là hằng số tiêu chuẩn (tránh ưu tiên quá mức tài liệu xếp hạng 1)
    - rank bắt đầu từ 1 (rank_i(d) ∈ [1, N])
    - Kết quả được sắp xếp giảm dần theo tổng điểm RRF

    Ưu điểm so với dùng điểm thô (cosine / BM25):
    - Hai hệ thống dùng thang điểm khác nhau → không thể cộng trực tiếp
    - RRF chỉ dùng thứ hạng → scale-invariant, không cần normalize
    """
    scores: dict[str, float] = {}
    for ranked_list in ranked_lists:
        for rank, text in enumerate(ranked_list, start=1):
            scores[text] = scores.get(text, 0.0) + 1.0 / (k + rank)
    return sorted(scores, key=lambda t: scores[t], reverse=True)


# ── Hàm retrieval chính ───────────────────────────────────────────────────────

def retrieve_context(
    query: str,
    k: int = 15,
    embedding_type: str = "en",
    use_hybrid: bool = False,
    use_rerank: bool = False,
    retrieval_mode: str = "similarity",
    where_filter: dict | None = None,
) -> str:
    """
    Truy xuất ngữ cảnh từ ChromaDB, hỗ trợ nhiều chế độ nâng cao.

    Args:
        query:          Câu hỏi hoặc hypothetical document (từ HyDE)
        k:              Số chunk trả về cuối cùng
        embedding_type: "en" hoặc "vi" — xác định model và ChromaDB collection
        use_hybrid:     True → kết hợp BM25 (sparse) + Vector (dense) + RRF
        use_rerank:     True → dùng Cross-Encoder xếp hạng lại Top-50 → Top-k
        retrieval_mode: "similarity" (mặc định) | "mmr" (đa dạng hóa kết quả)

    Returns:
        Chuỗi các chunk ghép bằng "\\n\\n", hoặc "" nếu không tìm được gì.

    Lưu ý:
        - MMR và rerank không dùng chung (MMR tối ưu diversity, rerank tối ưu relevance)
        - Hybrid search yêu cầu chunks.json tồn tại (chạy ingest trước)
    """
    if embedding_type not in EMBEDDING_CONFIGS:
        raise ValueError(
            f"embedding_type không hợp lệ: '{embedding_type}'. Chọn: {list(EMBEDDING_CONFIGS)}"
        )

    _, chroma_dir, collection_name = EMBEDDING_CONFIGS[embedding_type]
    embeddings = _get_embeddings(embedding_type)

    # Tạo fresh Chroma connection để đọc data mới nhất sau mỗi lần ingest
    store = Chroma(
        collection_name=collection_name,
        embedding_function=embeddings,
        persist_directory=chroma_dir,
    )

    # ── Chế độ MMR: tối ưu diversity thay vì chỉ relevance ──────────────────
    if retrieval_mode == "mmr":
        # fetch_k=50: lấy 50 ứng viên từ vector search
        # lambda_mult=0.7: 70% relevance + 30% diversity (0=diversity, 1=relevance)
        docs = store.max_marginal_relevance_search(
            query, k=k, fetch_k=50, lambda_mult=0.7, filter=where_filter
        )
        if not docs:
            return ""
        _logger.info(
            "MMR retrieval: %d chunks (embedding=%s)", len(docs), embedding_type
        )
        return "\n\n".join(doc.page_content for doc in docs)

    # ── Chế độ Hybrid Search: BM25 + Vector + RRF ────────────────────────────
    if use_hybrid:
        corpus = load_chunks_for_bm25(chroma_dir)

        if not corpus:
            # Graceful fallback: chunks.json chưa có → pure vector
            _logger.warning(
                "chunks.json chưa tồn tại trong '%s'. "
                "Hãy ingest lại để kích hoạt Hybrid Search. "
                "Fallback: pure vector search.",
                chroma_dir,
            )
            docs = store.similarity_search(query, k=k)
            if not docs:
                return ""
            return "\n\n".join(doc.page_content for doc in docs)

        # ── BM25 side (sparse retrieval) ─────────────────────────────────────
        if chroma_dir not in _bm25_cache:
            from rank_bm25 import BM25Okapi  # noqa: PLC0415
            # Tokenize đơn giản bằng whitespace — nhất quán giữa index time và query time
            # Vietnamese dùng space-delimited syllables → split() hoạt động được
            tokenized_corpus = [text.lower().split() for text in corpus]
            _bm25_cache[chroma_dir] = BM25Okapi(tokenized_corpus)
            _logger.info("Đã build BM25 index cho %s (%d chunks)", chroma_dir, len(corpus))
        bm25 = _bm25_cache[chroma_dir]
        bm25_scores = bm25.get_scores(query.lower().split())

        # Lấy top-50 indices theo điểm BM25 giảm dần
        top50_indices = sorted(
            range(len(bm25_scores)), key=lambda i: bm25_scores[i], reverse=True
        )[:50]
        bm25_top_texts = [corpus[i] for i in top50_indices]

        # ── Vector side (dense retrieval) ────────────────────────────────────
        vector_docs = store.similarity_search(query, k=50)
        vector_top_texts = [doc.page_content for doc in vector_docs]

        # ── RRF fusion ───────────────────────────────────────────────────────
        # Kết hợp hai danh sách xếp hạng bằng RRF, lấy top-50 tốt nhất
        candidates = _reciprocal_rank_fusion([bm25_top_texts, vector_top_texts])[:50]

        _logger.info(
            "Hybrid search: BM25=%d + Vector=%d → RRF=%d candidates (embedding=%s)",
            len(bm25_top_texts), len(vector_top_texts), len(candidates), embedding_type,
        )

        # ── Cross-Encoder re-ranking (nếu bật) ───────────────────────────────
        if use_rerank and candidates:
            cross_encoder = _get_cross_encoder(embedding_type)
            pairs = [[query, text] for text in candidates]
            ce_scores = cross_encoder.predict(pairs)
            # Sắp xếp theo điểm Cross-Encoder giảm dần, lấy top-k
            ranked = sorted(
                zip(candidates, ce_scores), key=lambda x: x[1], reverse=True
            )
            final_texts = [text for text, _ in ranked[:k]]
            _logger.info(
                "Cross-Encoder rerank: %d → %d chunks", len(candidates), len(final_texts)
            )
        else:
            final_texts = candidates[:k]

        return "\n\n".join(final_texts) if final_texts else ""

    # ── Chế độ Pure Vector Search ─────────────────────────────────────────────
    # Nếu rerank: lấy top-50 trước, sau đó Cross-Encoder lọc → top-k
    fetch_k = 50 if use_rerank else k
    docs = store.similarity_search(query, k=fetch_k, filter=where_filter)

    if not docs:
        return ""

    if use_rerank:
        cross_encoder = _get_cross_encoder(embedding_type)
        pairs = [[query, doc.page_content] for doc in docs]
        ce_scores = cross_encoder.predict(pairs)
        ranked = sorted(
            zip(docs, ce_scores), key=lambda x: x[1], reverse=True
        )
        final_docs = [doc for doc, _ in ranked[:k]]
        _logger.info(
            "Vector + Cross-Encoder rerank: %d → %d chunks (embedding=%s)",
            len(docs), len(final_docs), embedding_type,
        )
        return "\n\n".join(doc.page_content for doc in final_docs)

    _logger.info(
        "Pure vector search: %d chunks (embedding=%s)", len(docs), embedding_type
    )
    return "\n\n".join(doc.page_content for doc in docs)
