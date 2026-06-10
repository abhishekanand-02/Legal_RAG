from dataclasses import dataclass, field
from typing import Any

from langchain_core.vectorstores import VectorStoreRetriever

MAX_VALIDATE_CALLS = 2
MAX_INDEX_CALLS = 1
MAX_SEARCH_CALLS = 6
MAX_ASK_HUMAN_CALLS = 3


@dataclass
class AgentContext:
    pdf_bytes: bytes
    pdf_name: str = "document.pdf"
    retriever: VectorStoreRetriever | None = None
    validation_info: dict[str, Any] | None = None
    indexed: bool = False
    rejected: bool = False
    approved_by_user: bool = False
    index_error: str | None = None
    validate_count: int = 0
    index_count: int = 0
    search_count: int = 0
    ask_human_count: int = 0

    def reset_validation_attempt(self) -> None:
        self.validate_count = 0
        self.index_error = None
