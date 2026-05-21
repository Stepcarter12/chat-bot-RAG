import sys
from pathlib import Path

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

# Tính đường dẫn tuyệt đối từ vị trí file, không phụ thuộc vào thư mục gọi lệnh
_PROJECT_ROOT = Path(__file__).parent.parent.parent
_DOCS_DATA_DIR = str(_PROJECT_ROOT / "docs" / "data")
_CHROMA_DIR = str(_PROJECT_ROOT / "chroma_data")

# Cấu hình từng loại file: glob pattern → (loader class, kwargs)
_LOADERS: dict = {
    "**/*.txt":  (TextLoader,     {"encoding": "utf-8"}),
    "**/*.pdf":  (PyPDFLoader,    {}),
    "**/*.docx": (Docx2txtLoader, {}),
    "**/*.csv":  (CSVLoader,      {"encoding": "utf-8"}),
}


def _load_excel(file_path: Path) -> list[Document]:
    """Đọc file Excel, chuyển từng sheet thành một Document."""
    dfs: dict = pd.read_excel(file_path, sheet_name=None, engine="openpyxl")
    docs = []
    for sheet_name, df in dfs.items():
        content = df.to_string(index=False)
        docs.append(Document(
            page_content=content,
            metadata={"source": str(file_path), "sheet": sheet_name},
        ))
    return docs


def ingest_documents(docs_dir: str = _DOCS_DATA_DIR) -> None:
    """Nạp tài liệu từ docs/data (txt, pdf, docx, csv, xlsx) vào ChromaDB."""
    data_path = Path(docs_dir)
    all_documents: list[Document] = []

    # Nạp txt, pdf, docx, csv qua DirectoryLoader
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
        print(f"Không tìm thấy tài liệu nào trong '{docs_dir}'.")
        return

    print(f"Tìm thấy {len(all_documents)} tài liệu thô. Đang chunk...")
    splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
    chunks = splitter.split_documents(all_documents)

    embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")

    # Xóa collection cũ trước khi nạp lại để tránh duplicate
    _old = Chroma(
        collection_name="knowledge_base",
        embedding_function=embeddings,
        persist_directory=_CHROMA_DIR,
    )
    _old.delete_collection()

    Chroma.from_documents(
        documents=chunks,
        embedding=embeddings,
        collection_name="knowledge_base",
        persist_directory=_CHROMA_DIR,
    )

    print(f"Đã nạp thành công {len(chunks)} chunks vào ChromaDB.")


if __name__ == "__main__":
    ingest_documents()
