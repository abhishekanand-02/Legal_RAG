"""Minimal retrieve-then-generate pipeline used for RAGAS evaluation."""

from langchain_core.messages import HumanMessage, SystemMessage

import config
from rag.ingest import ingest_pdf
from rag.llm import get_llm

RAG_SYSTEM_PROMPT = """You answer questions using only the provided document excerpts.
Cite page numbers when they appear in the excerpts, e.g. {reference: pageNumber: 3}.
If the excerpts do not contain enough information, say so clearly. Do not invent facts."""


def index_pdf(pdf_bytes: bytes):
    """Index a PDF and return a retriever backed by Pinecone."""
    retriever, namespace = ingest_pdf(pdf_bytes)
    return retriever, namespace


def run_rag_query(retriever, question: str) -> tuple[str, list[str]]:
    """Retrieve top-k chunks and generate an answer with the app LLM."""
    docs = retriever.invoke(question)
    contexts = [doc.page_content for doc in docs]

    if not contexts:
        return "No relevant passages were retrieved from the document.", []

    context_block = "\n\n---\n\n".join(contexts)
    llm = get_llm()
    response = llm.invoke(
        [
            SystemMessage(content=RAG_SYSTEM_PROMPT),
            HumanMessage(
                content=(
                    f"Document excerpts:\n\n{context_block}\n\n"
                    f"Question: {question}"
                )
            ),
        ]
    )
    answer = response.content
    if isinstance(answer, list):
        answer = "\n".join(
            block if isinstance(block, str) else block.get("text", "")
            for block in answer
        )
    return str(answer), contexts
