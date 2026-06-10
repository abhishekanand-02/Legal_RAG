import hashlib

from langchain_core.documents import Document
from langchain_core.vectorstores import VectorStoreRetriever
from langchain_pinecone import PineconeVectorStore
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pinecone import Pinecone, ServerlessSpec

import config
from rag.llm import get_embeddings
from rag.pdf_utils import extract_pdf_pages


def _ensure_pinecone_index(dimension: int) -> None:
    pc = Pinecone(api_key=config.PINECONE_API_KEY)

    if not pc.has_index(config.PINECONE_INDEX_NAME):
        pc.create_index(
            name=config.PINECONE_INDEX_NAME,
            dimension=dimension,
            metric="cosine",
            spec=ServerlessSpec(
                cloud=config.PINECONE_CLOUD,
                region=config.PINECONE_REGION,
            ),
        )


def _namespace_for_pdf(pdf_bytes: bytes) -> str:
    return hashlib.sha256(pdf_bytes).hexdigest()[:16]


def _load_pdf_documents(pdf_bytes: bytes) -> list[Document]:
    return [
        Document(page_content=text, metadata={"page": page_number})
        for page_number, text in extract_pdf_pages(pdf_bytes)
    ]


def ingest_pdf(pdf_bytes: bytes) -> tuple[VectorStoreRetriever, str]:
    documents = _load_pdf_documents(pdf_bytes)
    if not documents:
        raise ValueError(
            "No text could be extracted from the PDF. "
            "The file may be blank, corrupted, or unreadable even after OCR."
        )

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=config.CHUNK_SIZE,
        chunk_overlap=config.CHUNK_OVERLAP,
    )
    chunks = splitter.split_documents(documents)

    embeddings = get_embeddings()
    _ensure_pinecone_index(config.EMBEDDING_DIMENSION)
    namespace = _namespace_for_pdf(pdf_bytes)

    vectorstore = PineconeVectorStore.from_documents(
        documents=chunks,
        embedding=embeddings,
        index_name=config.PINECONE_INDEX_NAME,
        namespace=namespace,
    )

    retriever = vectorstore.as_retriever(search_kwargs={"k": config.TOP_K})
    return retriever, namespace


def get_retriever(namespace: str) -> VectorStoreRetriever:
    embeddings = get_embeddings()
    vectorstore = PineconeVectorStore.from_existing_index(
        index_name=config.PINECONE_INDEX_NAME,
        embedding=embeddings,
        namespace=namespace,
    )
    return vectorstore.as_retriever(search_kwargs={"k": config.TOP_K})
