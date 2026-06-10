from typing import Any

from pydantic import BaseModel, Field


class ConfigStatusResponse(BaseModel):
    ready: bool
    missing_keys: list[str]


class ChatMessageRequest(BaseModel):
    message: str = Field(min_length=1)


class ResumeRequest(BaseModel):
    response: str = Field(min_length=1)


class SessionResponse(BaseModel):
    session_id: str
    pdf_name: str | None = None
    doc_status: str
    validation_info: dict[str, Any] | None = None
    validation_error: str | None = None
    agent_interrupt: dict[str, Any] | None = None
    ready: bool
    messages: list[dict[str, Any]]
    chat_enabled: bool
    approved_by_user: bool = False
