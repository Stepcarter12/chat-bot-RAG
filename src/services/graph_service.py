import os
from typing import Annotated

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_groq import ChatGroq
from langgraph.checkpoint.memory import MemorySaver
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
    model="llama-3.1-8b-instant",
    api_key=SecretStr(os.getenv("GROQ_API_KEY") or ""),
)

_prompt = ChatPromptTemplate.from_messages([
    (
        "system",
        "You are a smart assistant. "
        "Use the content in [Context] to answer the question. "
        "If the information is not in [Context], answer based on general knowledge but be honest.\n"
        "Always respond in the same language as the user's question.\n\n"
        "[Context]\n{context}",
    ),
    ("placeholder", "{messages}"),
])

# Prompt phân loại: chỉ trả lời yes/no
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


class ChatbotState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    context: str
    needs_retrieval: bool
    embedding_type: str


def question_classifier_node(state: ChatbotState) -> dict:
    """Phân loại câu hỏi có cần RAG hay không."""
    last_human = next(
        (m for m in reversed(state["messages"]) if isinstance(m, HumanMessage)),
        None,
    )
    if last_human is None:
        return {"needs_retrieval": False}
    chain = _classifier_prompt | _llm
    result = chain.invoke({"query": last_human.content})
    needs = str(result.content).strip().lower() == "yes"
    _logger.info("Phân loại câu hỏi: needs_retrieval=%s", needs)
    return {"needs_retrieval": needs}


def route_after_classifier(state: ChatbotState) -> str:
    """Hàm router: chọn node tiếp theo dựa trên kết quả phân loại."""
    if state.get("needs_retrieval", False):
        return "retrieval_node"
    return "call_llm_node"


def retrieval_node(state: ChatbotState) -> dict:
    """Truy xuất ngữ cảnh từ ChromaDB dựa trên câu hỏi mới nhất."""
    last_human = next(
        (m for m in reversed(state["messages"]) if isinstance(m, HumanMessage)),
        None,
    )
    if last_human is None:
        return {"context": ""}
    embedding_type = state.get("embedding_type", "en")
    context = retrieve_context(str(last_human.content), embedding_type=embedding_type)
    _logger.info("Truy xuất context: %d ký tự (embedding_type=%s)", len(context), embedding_type)
    return {"context": context}


def call_llm_node(state: ChatbotState) -> dict:
    """Gọi Groq LLM với ngữ cảnh RAG và lịch sử hội thoại."""
    chain = _prompt | _llm
    response = chain.invoke({
        "context": state.get("context", ""),
        "messages": state["messages"],
    })
    return {"messages": [AIMessage(content=response.content)]}


# Xây dựng đồ thị: START → question_classifier → (RAG?) → call_llm_node → END
_graph = StateGraph(ChatbotState)
_graph.add_node("question_classifier_node", question_classifier_node)
_graph.add_node("retrieval_node", retrieval_node)
_graph.add_node("call_llm_node", call_llm_node)

_graph.add_edge(START, "question_classifier_node")
_graph.add_conditional_edges(
    "question_classifier_node",
    route_after_classifier,
    {"retrieval_node": "retrieval_node", "call_llm_node": "call_llm_node"},
)
_graph.add_edge("retrieval_node", "call_llm_node")
_graph.add_edge("call_llm_node", END)

# Biên dịch với MemorySaver để lưu lịch sử hội thoại theo thread_id
app = _graph.compile(checkpointer=MemorySaver())
