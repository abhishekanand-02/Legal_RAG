import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.errors import GraphRecursionError
from langgraph.types import Command

from rag.agent import build_agent_graph, extract_final_answer
from rag.context import AgentContext

logger = logging.getLogger("legal_rag.session")

MAX_API_ATTEMPTS = 3  # initial attempt + 2 retries
AGENT_RECURSION_LIMIT = 20

TRANSIENT_ERROR_MARKERS = (
    "429",
    "503",
    "resource exhausted",
    "rate limit",
    "unavailable",
    "high demand",
    "temporarily",
    "overloaded",
)

AGENT_FAILURE_PREFIXES = (
    "something went wrong:",
    "gemini api rate limit",
)

UPLOAD_PROMPT = (
    'A new PDF "{name}" was uploaded. Validate it with validate_document. '
    "If valid, index it with index_document. If invalid, ask the user for "
    "approval with ask_human before indexing. Do not use answer_user."
)

RETRY_VALIDATION_PROMPT = (
    "Please call validate_document again to re-classify this document, then "
    "follow the same rules: index if valid, otherwise ask_human for approval."
)

SKIP_VALIDATION_PROMPT = (
    "The user chose to skip validation. Index the document with index_document "
    "so chat can begin."
)


@dataclass
class SessionState:
    session_id: str
    messages: list[dict[str, Any]] = field(default_factory=list)
    pdf_bytes: bytes | None = None
    pdf_name: str | None = None
    agent_graph: Any = None
    agent_context: AgentContext | None = None
    thread_id: str | None = None
    checkpointer: MemorySaver | None = None
    agent_interrupt: dict | None = None
    ready: bool = False
    doc_status: str = "idle"
    validation_info: dict | None = None
    validation_error: str | None = None
    approved_by_user: bool = False


class SessionManager:
    def __init__(self) -> None:
        self._sessions: dict[str, SessionState] = {}

    def create_session(self) -> SessionState:
        session_id = str(uuid.uuid4())
        session = SessionState(session_id=session_id)
        self._sessions[session_id] = session
        logger.info("Created session %s", session_id)
        return session

    def get(self, session_id: str) -> SessionState | None:
        return self._sessions.get(session_id)

    def _agent_config(self, session: SessionState) -> dict:
        return {
            "configurable": {"thread_id": session.thread_id},
            "recursion_limit": AGENT_RECURSION_LIMIT,
        }

    @staticmethod
    def _is_transient_api_error(error: str) -> bool:
        lower = error.lower()
        return any(marker in lower for marker in TRANSIENT_ERROR_MARKERS)

    @staticmethod
    def _is_agent_failure(answer: str | None) -> bool:
        if not answer:
            return False
        lower = answer.lower().strip()
        return any(lower.startswith(prefix) for prefix in AGENT_FAILURE_PREFIXES)

    @staticmethod
    def _friendly_agent_error(answer: str | None) -> str:
        if not answer:
            return "The agent could not complete this step. Please try again."

        text = answer.strip()
        if text.lower().startswith("something went wrong:"):
            text = text.split(":", 1)[1].strip()

        lower = text.lower()
        if "503" in lower or "high demand" in lower or "unavailable" in lower:
            return (
                "The AI model is temporarily overloaded (503). "
                "Wait a moment and try again."
            )
        if "429" in lower or "rate limit" in lower or "resource exhausted" in lower:
            return (
                "Gemini API rate limit reached. Wait 30–60 seconds and try again."
            )
        return text

    def _init_agent(self, session: SessionState) -> None:
        if session.agent_graph is not None:
            return
        if session.pdf_bytes is None:
            raise ValueError("Cannot initialize agent without PDF bytes.")

        checkpointer = MemorySaver()
        session.checkpointer = checkpointer
        session.thread_id = str(uuid.uuid4())
        session.agent_context = AgentContext(
            pdf_bytes=session.pdf_bytes,
            pdf_name=session.pdf_name or "document.pdf",
        )
        session.agent_graph = build_agent_graph(
            session.agent_context,
            checkpointer=checkpointer,
        )

    def _invoke_agent(
        self,
        session: SessionState,
        user_input: str | Command,
    ) -> tuple[str | None, float, dict | None]:
        if session.agent_graph is None:
            raise RuntimeError("Agent is not initialized for this session.")

        graph = session.agent_graph
        agent_config = self._agent_config(session)
        start = time.perf_counter()

        if isinstance(user_input, Command):
            payload: str | Command = user_input
        else:
            payload = {"messages": [HumanMessage(content=user_input)]}

        last_error = None
        for attempt in range(MAX_API_ATTEMPTS):
            try:
                graph.invoke(payload, agent_config)
                elapsed = time.perf_counter() - start
                snapshot = graph.get_state(agent_config)

                if snapshot.interrupts:
                    interrupt = snapshot.interrupts[0]
                    value = interrupt.value
                    if isinstance(value, dict):
                        return None, elapsed, value
                    return None, elapsed, {"type": "ask_human", "question": str(value)}

                answer = extract_final_answer(snapshot.values["messages"])
                return answer, elapsed, None
            except GraphRecursionError as exc:
                logger.warning(
                    "Agent hit recursion limit for session %s: %s",
                    session.session_id,
                    exc,
                )
                elapsed = time.perf_counter() - start
                return (
                    "The agent reached its step limit and stopped to avoid looping. "
                    "Please try again or use Retry validation.",
                    elapsed,
                    None,
                )
            except Exception as exc:
                last_error = exc
                error = str(exc)
                if self._is_transient_api_error(error):
                    wait = min(2 ** attempt, 16)
                    logger.warning(
                        "Transient API error for session %s (attempt %d/%d): %s",
                        session.session_id,
                        attempt + 1,
                        MAX_API_ATTEMPTS,
                        error[:200],
                    )
                    time.sleep(wait)
                    continue
                logger.exception("Agent invoke failed for session %s", session.session_id)
                break

        elapsed = time.perf_counter() - start
        error = str(last_error) if last_error else ""
        if self._is_transient_api_error(error):
            return (
                self._friendly_agent_error(f"Something went wrong: {error}"),
                elapsed,
                None,
            )
        return f"Something went wrong: {last_error}", elapsed, None

    def _sync_session_from_context(self, session: SessionState) -> None:
        ctx = session.agent_context
        if ctx is None:
            return

        if ctx.validation_info is not None:
            session.validation_info = ctx.validation_info

        if ctx.rejected:
            session.doc_status = "rejected"
            session.ready = False
            session.approved_by_user = False
            session.agent_interrupt = None
            session.validation_error = None
            return

        if ctx.indexed:
            session.ready = True
            session.validation_error = None
            session.agent_interrupt = None
            if ctx.approved_by_user:
                session.doc_status = "approved"
                session.approved_by_user = True
            else:
                session.doc_status = "valid"
                session.approved_by_user = False
            return

        if ctx.index_error:
            session.doc_status = "validation_error"
            session.validation_error = ctx.index_error
            session.ready = False

    def _apply_validation_agent_result(
        self,
        session: SessionState,
        answer: str | None,
        interrupt: dict | None,
    ) -> None:
        ctx = session.agent_context

        if interrupt:
            session.agent_interrupt = interrupt
            session.doc_status = "pending_approval"
            session.validation_error = None
            if ctx and ctx.validation_info is not None:
                session.validation_info = ctx.validation_info
            logger.info("Session %s awaiting human approval via agent", session.session_id)
            return

        self._sync_session_from_context(session)

        if session.doc_status in ("valid", "approved", "rejected"):
            logger.info(
                "Session %s validation workflow finished with status=%s",
                session.session_id,
                session.doc_status,
            )
            return

        if ctx and ctx.validation_info and not ctx.indexed and not ctx.rejected:
            session.doc_status = "pending_approval"
            session.validation_error = None
            return

        session.doc_status = "validation_error"
        session.validation_error = self._friendly_agent_error(
            answer or "The agent did not complete the validation workflow."
        )
        session.ready = False
        logger.warning(
            "Session %s validation workflow incomplete: %s",
            session.session_id,
            session.validation_error,
        )

    def _run_validation_agent(
        self,
        session: SessionState,
        prompt: str,
    ) -> None:
        session.approved_by_user = False
        session.agent_interrupt = None
        session.ready = False
        session.validation_error = None

        self._init_agent(session)
        answer, _, interrupt = self._invoke_agent(session, prompt)
        self._apply_validation_agent_result(session, answer, interrupt)

    def upload_pdf(self, pdf_bytes: bytes, pdf_name: str) -> SessionState:
        session = self.create_session()
        session.pdf_bytes = pdf_bytes
        session.pdf_name = pdf_name

        try:
            prompt = UPLOAD_PROMPT.format(name=pdf_name or "document.pdf")
            self._run_validation_agent(session, prompt)
        except Exception as exc:
            logger.exception("Validation failed for session %s", session.session_id)
            session.doc_status = "validation_error"
            session.validation_error = str(exc)
            session.ready = False

        return session

    def approve_document(self, session_id: str) -> SessionState:
        session = self._require_session(session_id)
        if session.doc_status != "pending_approval":
            logger.warning("Session %s approve called without pending approval", session_id)
            return session

        answer, _, interrupt = self._invoke_agent(
            session,
            Command(resume="Yes, proceed with indexing and enable chat."),
        )
        self._apply_validation_agent_result(session, answer, interrupt)
        logger.info("Session %s approved document via agent", session_id)
        return session

    def reject_document(self, session_id: str) -> SessionState:
        session = self._require_session(session_id)
        if session.doc_status != "pending_approval":
            logger.warning("Session %s reject called without pending approval", session_id)
            return session

        answer, _, interrupt = self._invoke_agent(
            session,
            Command(resume="No, do not index this document."),
        )
        self._apply_validation_agent_result(session, answer, interrupt)
        logger.info("Session %s rejected document via agent", session_id)
        return session

    def retry_validation(self, session_id: str) -> SessionState:
        session = self._require_session(session_id)
        try:
            if session.agent_context:
                session.agent_context.reset_validation_attempt()
            self._run_validation_agent(session, RETRY_VALIDATION_PROMPT)
        except Exception as exc:
            session.doc_status = "validation_error"
            session.validation_error = str(exc)
            logger.exception("Retry validation failed for session %s", session_id)
        return session

    def skip_validation(self, session_id: str) -> SessionState:
        session = self._require_session(session_id)
        try:
            self._init_agent(session)
            if session.agent_context:
                session.agent_context.validation_info = {
                    "is_valid": True,
                    "category": "skipped",
                    "reason": "Validation skipped at user request.",
                }
            answer, _, interrupt = self._invoke_agent(session, SKIP_VALIDATION_PROMPT)
            self._apply_validation_agent_result(session, answer, interrupt)
            if session.doc_status in ("valid", "approved") and session.agent_context:
                session.agent_context.approved_by_user = True
                session.doc_status = "approved"
                session.approved_by_user = True
            logger.info("Session %s skipped validation via agent", session_id)
        except Exception as exc:
            session.doc_status = "validation_error"
            session.validation_error = str(exc)
            logger.exception("Skip validation failed for session %s", session_id)
        return session

    def send_message(self, session_id: str, message: str) -> SessionState:
        session = self._require_session(session_id)
        session.messages.append({"role": "user", "content": message})

        if session.agent_context:
            session.agent_context.search_count = 0

        answer, elapsed, new_interrupt = self._invoke_agent(session, message)
        if new_interrupt:
            session.agent_interrupt = new_interrupt
            return session

        session.agent_interrupt = None
        is_error = self._is_agent_failure(answer)
        session.messages.append(
            {
                "role": "assistant",
                "content": (
                    self._friendly_agent_error(answer)
                    if is_error
                    else (answer or "No answer was generated.")
                ),
                "response_time": elapsed,
                "is_error": is_error,
            }
        )
        logger.info("Session %s chat message processed (%.1fs)", session_id, elapsed)
        return session

    def resume_interrupt(self, session_id: str, response: str) -> SessionState:
        session = self._require_session(session_id)
        validation_flow = session.doc_status == "pending_approval"

        answer, elapsed, new_interrupt = self._invoke_agent(
            session,
            Command(resume=response.strip()),
        )

        if validation_flow:
            self._apply_validation_agent_result(session, answer, new_interrupt)
            logger.info("Session %s validation interrupt resumed", session_id)
            return session

        if new_interrupt:
            session.agent_interrupt = new_interrupt
            return session

        session.agent_interrupt = None
        if answer:
            is_error = self._is_agent_failure(answer)
            session.messages.append(
                {
                    "role": "assistant",
                    "content": (
                        self._friendly_agent_error(answer)
                        if is_error
                        else answer
                    ),
                    "response_time": elapsed,
                    "is_error": is_error,
                }
            )
        logger.info("Session %s chat interrupt resumed", session_id)
        return session

    def _require_session(self, session_id: str) -> SessionState:
        session = self.get(session_id)
        if session is None:
            raise KeyError(f"Session {session_id} not found")
        return session

    @staticmethod
    def to_response(session: SessionState) -> dict[str, Any]:
        return {
            "session_id": session.session_id,
            "pdf_name": session.pdf_name,
            "doc_status": session.doc_status,
            "validation_info": session.validation_info,
            "validation_error": session.validation_error,
            "agent_interrupt": session.agent_interrupt,
            "ready": session.ready,
            "messages": session.messages,
            "chat_enabled": session.doc_status in ("valid", "approved"),
            "approved_by_user": session.approved_by_user,
        }


session_manager = SessionManager()
