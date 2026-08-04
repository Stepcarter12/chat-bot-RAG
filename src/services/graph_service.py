import os
import re
from typing import Annotated, Union

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_groq import ChatGroq
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from pydantic import SecretStr
from typing_extensions import TypedDict

from src.core.utils import get_logger
from src.retrieval.vector_store import retrieve_context

load_dotenv()

_logger = get_logger(__name__)

# Khởi tạo Groq LLM một lần duy nhất
_llm = ChatGroq(
    model=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
    api_key=SecretStr(os.getenv("GROQ_API_KEY") or ""),
)

# ── Prompt chính: trả lời với context RAG ────────────────────────────────────
_prompt = ChatPromptTemplate.from_messages([
    (
        "system",
        # Nhân vật sale điện tử — Messenger không render markdown
        "Bạn là Hân, nhân viên tư vấn bán hàng của cửa hàng điện tử. "
        "Trả lời qua Facebook Messenger, ngắn gọn, thân thiện, dùng 'bạn/mình'.\n\n"

        "QUY TRÌNH TƯ VẤN:\n"
        "1. Hỏi 1-2 câu để hiểu nhu cầu: dùng để làm gì, ngân sách bao nhiêu.\n"
        "2. Tư vấn sản phẩm phù hợp từ [Context] — nêu 2-3 điểm nổi bật, giá, ưu đãi.\n"
        "3. Khi khách hỏi cách mua, đặt hàng, hoặc tỏ ý muốn mua "
        "→ hỏi: 'Để nhân viên liên hệ xác nhận đơn cho bạn, "
        "bạn cho mình biết tên và số điện thoại nhé?'\n"
        "4. Sau khi có tên + SĐT → xác nhận: 'Mình đã ghi nhận. "
        "Nhân viên sẽ liên hệ bạn trong vòng 30 phút nhé!'\n\n"

        "XỬ LÝ TỪ CHỐI:\n"
        "- Giá cao quá → Nêu ưu đãi hiện có hoặc đề xuất sản phẩm tầm giá thấp hơn.\n"
        "- Để tôi nghĩ thêm → 'Bạn cứ thoải mái, mình sẵn sàng tư vấn thêm nhé!'\n"
        "- Bên khác rẻ hơn → Nêu điểm khác biệt: bảo hành, chính hãng, hậu mãi.\n\n"

        "QUY TẮC BẮT BUỘC — VI PHẠM LÀ SAI:\n"
        "1. CHỈ được nhắc đến sản phẩm có trong [Context] bên dưới — không dùng kiến thức bên ngoài.\n"
        "   Khi khách hỏi sản phẩm không có trong kho nhưng [Context] có sản phẩm TƯƠNG TỰ "
        "(ví dụ: khách hỏi 'iPhone 14', kho có 'iPhone 14 Pro') → KHÔNG nói 'không có', "
        "thay vào đó giới thiệu NGAY sản phẩm tương tự một cách tự nhiên: "
        "'Cửa hàng mình hiện đang có iPhone 14 Pro 128GB, đây là phiên bản cao cấp hơn với...' "
        "rồi tư vấn điểm nổi bật và hỏi nhu cầu.\n"
        "   Chỉ nói 'chưa có sản phẩm phù hợp' khi [Context] HOÀN TOÀN không có gì liên quan. "
        "Trong trường hợp đó: 'Bạn để lại SĐT để nhân viên tư vấn thêm nhé?'\n"
        "2. Nếu [Context] bắt đầu bằng '<<NODOCS>>' → hỏi SĐT để nhân viên hỗ trợ.\n"
        "3. Nếu [Context] rỗng → trả lời bình thường (chào hỏi, câu hỏi đơn giản).\n"
        "4. KHÔNG dùng Markdown. Không dùng *, #, backtick. Chỉ plain text.\n"
        "5. Danh sách dùng dấu gạch (-) hoặc số (1. 2. 3.).\n\n"

        "[Context]\n{context}",
    ),
    ("placeholder", "{messages}"),
])

# ── Prompt phân loại: chỉ trả lời yes/no ─────────────────────────────────────
_classifier_prompt = ChatPromptTemplate.from_messages([
    (
        "system",
        "Determine if the following question requires looking up information from documents. "
        "Answer with exactly one word: 'yes' or 'no'.\n"
        "Answer 'yes' for: summarize document, explain concept, questions about specific "
        "content, definitions, examples, product info, policies, data lookup.\n"
        "Answer 'no' for: greetings, simple math, questions clearly unrelated to any document.",
    ),
    ("human", "{query}"),
])

# ── Prompt HyDE: tạo tài liệu giả thuyết ─────────────────────────────────────
# HyDE (Hypothetical Document Embeddings): thay vì embed câu hỏi ngắn,
# ta embed một đoạn văn giả thuyết → vector gần hơn với tài liệu thực
_hyde_prompt = ChatPromptTemplate.from_messages([
    (
        "system",
        "Given the following question, write a short hypothetical document passage "
        "(2-4 sentences) that would directly answer it. "
        "Be factual and specific. Output only the passage, no preamble or explanation.",
    ),
    ("human", "{query}"),
])

# ── Prompt Query Decomposition: phân rã câu hỏi phức tạp ─────────────────────
# Dùng cho câu hỏi so sánh, tổng hợp nhiều khía cạnh → tìm kiếm toàn diện hơn
_decompose_prompt = ChatPromptTemplate.from_messages([
    (
        "system",
        "Break the following complex question into 2-4 simpler sub-questions. "
        "Output each sub-question on its own numbered line (1. ..., 2. ...). "
        "If the question is already simple, output it as-is on one numbered line.",
    ),
    ("human", "{query}"),
])


# ── LangGraph State ───────────────────────────────────────────────────────────

class ChatbotState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]  # lịch sử hội thoại
    context: str            # context từ ChromaDB (chỉ khi needs_retrieval=True)
    needs_retrieval: bool   # kết quả phân loại câu hỏi
    embedding_type: str     # "en" hoặc "vi" — xác định model và collection ChromaDB
    # ── Advanced RAG fields ──────────────────────────────────────────────────
    use_hyde: bool          # True → tạo hypothetical document trước khi retrieval
    hyde_query: str         # Nội dung hypothetical document do LLM tạo ra
    use_decomposition: bool # True → phân rã câu hỏi thành sub-queries
    sub_queries: list[str]  # Danh sách sub-queries sau khi phân rã
    use_hybrid: bool        # True → Hybrid Search (BM25 + Vector + RRF)
    use_rerank: bool        # True → Cross-Encoder rerank Top-50 → Top-5
    retrieval_mode: str     # "similarity" (mặc định) | "mmr" (đa dạng hóa)


# ── Helper: lấy tin nhắn HumanMessage cuối cùng ──────────────────────────────

def _get_last_human(state: ChatbotState) -> HumanMessage | None:
    """Trả về HumanMessage mới nhất trong lịch sử hội thoại."""
    return next(
        (m for m in reversed(state["messages"]) if isinstance(m, HumanMessage)),
        None,
    )


def _build_retrieval_query(state: ChatbotState) -> str:
    """
    Xây dựng query kết hợp ngữ cảnh 3 lượt hội thoại gần nhất.
    Tránh trường hợp user nói "mua cái đó đi" mà retrieval không biết "cái đó" là gì.
    """
    messages = state["messages"]
    recent = messages[-6:] if len(messages) > 6 else messages
    parts: list[str] = []
    for msg in recent:
        if isinstance(msg, HumanMessage):
            parts.append(str(msg.content))
        elif isinstance(msg, AIMessage):
            # Chỉ lấy 120 ký tự đầu của AI reply để không làm loãng query
            preview = str(msg.content)[:120].strip()
            if preview:
                parts.append(preview)
    return " ".join(parts)


# ── Nodes ─────────────────────────────────────────────────────────────────────

def question_classifier_node(state: ChatbotState) -> dict:
    """Bot bán hàng — luôn cần xem catalog sản phẩm, bỏ qua classifier."""
    return {"needs_retrieval": True}


def hyde_node(state: ChatbotState) -> dict:
    """
    Tạo Hypothetical Document Embedding (HyDE) để nâng cao chất lượng retrieval.

    Thay vì embed câu hỏi ngắn (ít thông tin ngữ nghĩa), ta embed một đoạn văn
    giả thuyết dài hơn → vector gần với tài liệu thực hơn → recall tốt hơn.
    Kết quả lưu vào state['hyde_query'] để retrieval_node dùng thay cho original query.
    """
    last_human = _get_last_human(state)
    if last_human is None:
        return {"hyde_query": ""}

    # Cảnh báo nếu dùng cả HyDE lẫn Decomposition (tương tác không tối ưu)
    if state.get("use_decomposition", False) and state.get("sub_queries", []):
        _logger.warning(
            "HyDE + Decomposition cùng bật: retrieval_node sẽ ưu tiên sub_queries, "
            "hyde_query có thể không được dùng."
        )

    chain = _hyde_prompt | _llm
    result = chain.invoke({"query": last_human.content})
    hyde_query = str(result.content).strip()
    _logger.info("HyDE tạo hypothetical document: %d ký tự", len(hyde_query))
    return {"hyde_query": hyde_query}


def query_decomposition_node(state: ChatbotState) -> dict:
    """
    Phân rã câu hỏi phức tạp thành 2-4 sub-queries đơn giản hơn.

    Dùng cho câu hỏi so sánh (A vs B), tổng hợp (tất cả thông tin về X),
    hoặc câu hỏi đa khía cạnh. Mỗi sub-query được truy xuất riêng,
    sau đó kết quả được gộp và loại trùng lặp trong retrieval_node.
    """
    last_human = _get_last_human(state)
    if last_human is None:
        return {"sub_queries": []}

    chain = _decompose_prompt | _llm
    result = chain.invoke({"query": last_human.content})

    # Parse dòng có số thứ tự: "1. ...", "2. ..." → list[str]
    sub_queries = [
        re.sub(r"^\d+\.\s*", "", line).strip()
        for line in str(result.content).splitlines()
        if line.strip()
    ]
    _logger.info("Phân rã câu hỏi thành %d sub-queries: %s", len(sub_queries), sub_queries)
    return {"sub_queries": sub_queries}


def retrieval_node(state: ChatbotState) -> dict:
    """
    Truy xuất ngữ cảnh từ ChromaDB — hỗ trợ HyDE, Sub-queries, Hybrid Search,
    Cross-Encoder Reranking và MMR.

    Ưu tiên query:
    1. sub_queries (từ Decomposition) — truy xuất từng sub-query, gộp + dedup
    2. hyde_query (từ HyDE) — dùng thay cho original query
    3. Original query
    """
    last_human = _get_last_human(state)
    if last_human is None:
        return {"context": ""}

    embedding_type = state.get("embedding_type", "en")

    # Tham số retrieval chung
    retrieval_params = {
        "k": 15,
        "embedding_type": embedding_type,
        "use_hybrid": state.get("use_hybrid", False),
        "use_rerank": state.get("use_rerank", False),
        "retrieval_mode": state.get("retrieval_mode", "similarity"),
    }

    sub_queries = state.get("sub_queries", [])

    if sub_queries:
        # ── Chế độ Sub-queries: truy xuất từng câu, gộp + dedup ─────────────
        seen: set[str] = set()
        all_chunks: list[str] = []
        for sq in sub_queries:
            ctx = retrieve_context(sq, **retrieval_params)
            for chunk in ctx.split("\n\n"):
                if chunk.strip() and chunk not in seen:
                    seen.add(chunk)
                    all_chunks.append(chunk)
        context = "\n\n".join(all_chunks)
        _logger.info(
            "Sub-query retrieval: %d sub-queries → %d chunks unique (embedding=%s)",
            len(sub_queries), len(all_chunks), embedding_type,
        )
    else:
        # ── Chế độ đơn: HyDE query hoặc original query ──────────────────────
        hyde_query = state.get("hyde_query", "")
        # Dùng query kết hợp lịch sử để retrieval hiểu ngữ cảnh hội thoại nhiều lượt
        base_query = hyde_query if hyde_query else _build_retrieval_query(state)
        context = retrieve_context(base_query, **retrieval_params)
        _logger.info(
            "Retrieval: %d ký tự context (embedding=%s, hyde=%s, hybrid=%s, rerank=%s, mode=%s)",
            len(context),
            embedding_type,
            bool(hyde_query),
            retrieval_params["use_hybrid"],
            retrieval_params["use_rerank"],
            retrieval_params["retrieval_mode"],
        )

    return {"context": context}


def call_llm_node(state: ChatbotState) -> dict:
    """Gọi Groq LLM với ngữ cảnh RAG và lịch sử hội thoại."""
    context = state.get("context", "")

    # Khi RAG được kích hoạt nhưng không tìm thấy tài liệu liên quan,
    # đặt sentinel để LLM biết không được tự bịa thay vì trả lời từ kiến thức chung
    if state.get("needs_retrieval", False) and not context.strip():
        context = "<<NODOCS>>"

    chain = _prompt | _llm
    response = chain.invoke({
        "context": context,
        "messages": state["messages"],
    })
    return {"messages": [AIMessage(content=response.content)]}


# ── Router functions ──────────────────────────────────────────────────────────

def route_after_classifier(state: ChatbotState) -> str:
    """
    Router sau question_classifier_node:
    - Không cần RAG → thẳng call_llm_node
    - Cần RAG + Decomposition → query_decomposition_node trước
    - Cần RAG + HyDE → hyde_node trước
    - Cần RAG thuần → thẳng retrieval_node
    """
    if not state.get("needs_retrieval", False):
        return "call_llm_node"
    if state.get("use_decomposition", False):
        return "query_decomposition_node"
    if state.get("use_hyde", False):
        return "hyde_node"
    return "retrieval_node"


def route_after_decomposition(state: ChatbotState) -> str:
    """
    Router sau query_decomposition_node:
    - HyDE bật → hyde_node (tạo hypothetical doc cho original query)
    - Ngược lại → thẳng retrieval_node
    """
    if state.get("use_hyde", False):
        return "hyde_node"
    return "retrieval_node"


# ── Checkpointer ──────────────────────────────────────────────────────────────

def _build_checkpointer() -> Union["PostgresSaver", "MemorySaver"]:  # type: ignore[name-defined]
    """
    Tạo checkpointer phù hợp với môi trường:
    - Nếu DATABASE_URL có trong env → PostgresSaver (persistent, dùng trong Docker)
    - Ngược lại → fallback MemorySaver (dev local không cần DB)

    ⚠️  autocommit=True và row_factory=dict_row là BẮT BUỘC cho PostgresSaver:
        - Thiếu autocommit → setup() không commit → mất bảng sau khi tiến trình kết thúc
        - Thiếu row_factory=dict_row → TypeError: tuple indices must be integers
    """
    db_url = os.getenv("DATABASE_URL")
    if db_url:
        # Lazy import để tránh ImportError khi chạy local không cài psycopg
        from langgraph.checkpoint.postgres import PostgresSaver  # type: ignore[import-untyped]
        from psycopg.rows import dict_row
        from psycopg_pool import ConnectionPool

        pool = ConnectionPool(
            conninfo=db_url,
            min_size=0,   # không eager-connect khi khởi động — tạo connection khi cần
            max_size=20,
            kwargs={"autocommit": True, "row_factory": dict_row},
        )
        saver = PostgresSaver(pool)
        # idempotent: chỉ tạo bảng checkpoints nếu chưa có
        saver.setup()
        _logger.info("Đã kết nối PostgresSaver tới %s", db_url.split("@")[-1])
        return saver

    # Fallback: không có DATABASE_URL → dùng RAM (mất khi restart)
    from langgraph.checkpoint.memory import MemorySaver

    _logger.warning(
        "DATABASE_URL không có — dùng MemorySaver (lịch sử mất khi restart). "
        "Thêm DATABASE_URL vào .env để dùng PostgresSaver."
    )
    return MemorySaver()


# ── Xây dựng đồ thị LangGraph ────────────────────────────────────────────────
#
# Luồng đầy đủ:
#   START → classifier
#     ├─[no RAG]──────────────────────────→ call_llm → END
#     ├─[decomp]→ decomposition_node
#     │             ├─[+hyde]→ hyde_node → retrieval_node → call_llm → END
#     │             └─[plain]──────────→ retrieval_node → call_llm → END
#     ├─[hyde]──→ hyde_node ──────────→ retrieval_node → call_llm → END
#     └─[plain]──────────────────────→ retrieval_node → call_llm → END

_graph = StateGraph(ChatbotState)

# Đăng ký nodes
_graph.add_node("question_classifier_node", question_classifier_node)
_graph.add_node("query_decomposition_node", query_decomposition_node)
_graph.add_node("hyde_node", hyde_node)
_graph.add_node("retrieval_node", retrieval_node)
_graph.add_node("call_llm_node", call_llm_node)

# Edges cố định
_graph.add_edge(START, "question_classifier_node")
_graph.add_edge("hyde_node", "retrieval_node")
_graph.add_edge("retrieval_node", "call_llm_node")
_graph.add_edge("call_llm_node", END)

# Conditional edges — router quyết định nhánh tại runtime
_graph.add_conditional_edges(
    "question_classifier_node",
    route_after_classifier,
    {
        "call_llm_node": "call_llm_node",
        "query_decomposition_node": "query_decomposition_node",
        "hyde_node": "hyde_node",
        "retrieval_node": "retrieval_node",
    },
)

_graph.add_conditional_edges(
    "query_decomposition_node",
    route_after_decomposition,
    {
        "hyde_node": "hyde_node",
        "retrieval_node": "retrieval_node",
    },
)

# Biên dịch graph với checkpointer phù hợp (PostgreSQL hoặc in-memory)
app = _graph.compile(checkpointer=_build_checkpointer())
