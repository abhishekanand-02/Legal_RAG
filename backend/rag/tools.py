import json

from langchain_core.documents import Document
from langchain_core.tools import tool
from langgraph.types import interrupt

from rag.context import (
    MAX_ASK_HUMAN_CALLS,
    MAX_INDEX_CALLS,
    MAX_SEARCH_CALLS,
    MAX_VALIDATE_CALLS,
    AgentContext,
)
from rag.ingest import ingest_pdf
from rag.pdf_utils import extract_text_sample
from rag.validation import validate_document as run_validation


def _format_search_results(docs: list[Document]) -> str:
    if not docs:
        return "No relevant passages found."

    sections: list[str] = []
    for doc in docs:
        page = doc.metadata.get("page")
        label = f"[Page {page}]" if page is not None else "[Page unknown]"
        sections.append(f"{label}\n{doc.page_content}")
    return "\n\n".join(sections)


def create_agent_tools(context: AgentContext) -> list:
    @tool
    def validate_document() -> str:
        """Classify the uploaded PDF as legal, investigation, criminal, or other. Call at most once per validation attempt."""
        if context.validate_count >= MAX_VALIDATE_CALLS:
            return json.dumps(
                {
                    "error": "validate_document limit reached",
                    "message": (
                        "Do not call validate_document again. Use ask_human, "
                        "index_document, or reject_document to finish."
                    ),
                }
            )

        context.validate_count += 1
        try:
            sample = extract_text_sample(context.pdf_bytes)
            result = run_validation(sample)
            context.validation_info = result
            return json.dumps(result)
        except Exception as exc:
            return json.dumps(
                {
                    "error": "validation_failed",
                    "message": str(exc),
                }
            )

    @tool
    def index_document() -> str:
        """Index the uploaded PDF into the search store and enable chat. Call at most once after validation or user approval."""
        if context.indexed:
            return json.dumps(
                {
                    "status": "already_indexed",
                    "message": "Document is already indexed. Do not call again.",
                }
            )
        if context.index_count >= MAX_INDEX_CALLS:
            return json.dumps(
                {
                    "error": "index_document limit reached",
                    "message": "Do not call index_document again.",
                }
            )

        context.index_count += 1
        try:
            retriever, namespace = ingest_pdf(context.pdf_bytes)
            context.retriever = retriever
            context.indexed = True
            context.index_error = None
            if context.validation_info and not context.validation_info.get("is_valid"):
                context.approved_by_user = True
            return json.dumps({"status": "indexed", "namespace": namespace})
        except Exception as exc:
            context.index_count -= 1
            context.index_error = str(exc)
            return json.dumps({"status": "error", "message": str(exc)})

    @tool
    def reject_document(reason: str = "User declined to index this document.") -> str:
        """Reject the document and disable chat. Use when the user declines indexing."""
        if context.rejected:
            return json.dumps(
                {
                    "status": "already_rejected",
                    "message": "Document is already rejected.",
                }
            )
        context.rejected = True
        return json.dumps({"status": "rejected", "reason": reason})

    @tool
    def search_documents(query: str) -> str:
        """Search the indexed document for passages relevant to a query. Requires index_document first."""
        if context.retriever is None:
            return "Document is not indexed yet. Call index_document before searching."

        if context.search_count >= MAX_SEARCH_CALLS:
            return (
                f"Search limit reached ({MAX_SEARCH_CALLS} calls). "
                "Answer with the best information you have using answer_user."
            )

        context.search_count += 1
        docs = context.retriever.invoke(query)
        return _format_search_results(docs)

    @tool
    def ask_human(question: str) -> str:
        """Ask the user a clarifying question or request approval. Execution pauses until they respond."""
        if context.ask_human_count >= MAX_ASK_HUMAN_CALLS:
            return (
                "ask_human limit reached. Decide using index_document or reject_document "
                "based on the latest user message."
            )

        context.ask_human_count += 1
        response = interrupt({"type": "ask_human", "question": question})
        if isinstance(response, dict):
            return str(response.get("response", response))
        return str(response)

    @tool
    def answer_user(answer: str) -> str:
        """Deliver the final answer to the user during chat. Always use this to finish a chat turn."""
        return answer

    return [
        validate_document,
        index_document,
        reject_document,
        search_documents,
        ask_human,
        answer_user,
    ]
