import logging

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import Response

import config
from api.schemas import (
    ChatMessageRequest,
    ConfigStatusResponse,
    ResumeRequest,
    SessionResponse,
)
from services.session_manager import session_manager

logger = logging.getLogger("legal_rag.api")
router = APIRouter(prefix="/api")


def _missing_keys() -> list[str]:
    missing = []
    if not config.GOOGLE_API_KEY:
        missing.append("GOOGLE_API_KEY")
    if not config.PINECONE_API_KEY:
        missing.append("PINECONE_API_KEY")
    return missing


def _session_response(session) -> SessionResponse:
    return SessionResponse(**session_manager.to_response(session))


@router.get("/status", response_model=ConfigStatusResponse)
def config_status() -> ConfigStatusResponse:
    missing = _missing_keys()
    return ConfigStatusResponse(ready=len(missing) == 0, missing_keys=missing)


@router.post("/sessions/upload", response_model=SessionResponse)
async def upload_document(file: UploadFile = File(...)) -> SessionResponse:
    missing = _missing_keys()
    if missing:
        raise HTTPException(
            status_code=503,
            detail=f"Missing API keys: {', '.join(missing)}",
        )

    if file.content_type not in ("application/pdf", "application/octet-stream"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    pdf_bytes = await file.read()
    if not pdf_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    logger.info("Uploading document: %s (%d bytes)", file.filename, len(pdf_bytes))
    session = session_manager.upload_pdf(pdf_bytes, file.filename or "document.pdf")
    return _session_response(session)


@router.get("/sessions/{session_id}", response_model=SessionResponse)
def get_session(session_id: str) -> SessionResponse:
    session = session_manager.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found.")
    return _session_response(session)


@router.get("/sessions/{session_id}/pdf")
def get_pdf(session_id: str) -> Response:
    session = session_manager.get(session_id)
    if session is None or session.pdf_bytes is None:
        raise HTTPException(status_code=404, detail="PDF not found.")
    return Response(
        content=session.pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{session.pdf_name}"'},
    )


@router.post("/sessions/{session_id}/approve", response_model=SessionResponse)
def approve_document(session_id: str) -> SessionResponse:
    try:
        session = session_manager.approve_document(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Session not found.") from None
    return _session_response(session)


@router.post("/sessions/{session_id}/reject", response_model=SessionResponse)
def reject_document(session_id: str) -> SessionResponse:
    try:
        session = session_manager.reject_document(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Session not found.") from None
    return _session_response(session)


@router.post("/sessions/{session_id}/retry-validation", response_model=SessionResponse)
def retry_validation(session_id: str) -> SessionResponse:
    try:
        session = session_manager.retry_validation(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Session not found.") from None
    return _session_response(session)


@router.post("/sessions/{session_id}/skip-validation", response_model=SessionResponse)
def skip_validation(session_id: str) -> SessionResponse:
    try:
        session = session_manager.skip_validation(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Session not found.") from None
    return _session_response(session)


@router.post("/sessions/{session_id}/chat", response_model=SessionResponse)
def send_chat_message(session_id: str, body: ChatMessageRequest) -> SessionResponse:
    session = session_manager.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found.")
    if session.doc_status not in ("valid", "approved"):
        raise HTTPException(status_code=400, detail="Chat is not enabled for this document.")
    if session.agent_interrupt:
        raise HTTPException(status_code=400, detail="Respond to the agent question first.")

    session = session_manager.send_message(session_id, body.message.strip())
    return _session_response(session)


@router.post("/sessions/{session_id}/resume", response_model=SessionResponse)
def resume_interrupt(session_id: str, body: ResumeRequest) -> SessionResponse:
    session = session_manager.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found.")
    if not session.agent_interrupt:
        raise HTTPException(status_code=400, detail="No pending agent question.")

    session = session_manager.resume_interrupt(session_id, body.response)
    return _session_response(session)
