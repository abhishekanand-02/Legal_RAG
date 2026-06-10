from typing import Annotated, Literal, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, SystemMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

from rag.context import AgentContext
from rag.llm import get_llm
from rag.tools import create_agent_tools

TERMINAL_TOOLS = frozenset({"answer_user", "index_document", "reject_document"})

AGENT_SYSTEM_PROMPT = """You are an agentic legal document assistant. You decide which tools to use on each step.

Tools:
- validate_document: classify the uploaded PDF (legal / investigation / criminal / other)
- index_document: index the PDF for search and enable chat (call at most once)
- reject_document: reject the document and disable chat
- search_documents: retrieve relevant passages (only after indexing)
- ask_human: ask the user for clarification or approval (pauses until they reply)
- answer_user: deliver the final chat response (always use this to finish a chat turn)

Upload / validation workflow:
1. Call validate_document exactly once when a document is uploaded or when asked to retry validation.
2. If is_valid is true, call index_document immediately. Do not call answer_user.
3. If is_valid is false, call ask_human once to ask whether to proceed with indexing anyway.
4. If the user approves, call index_document. If they decline, call reject_document.
5. Never repeat validate_document unless the user explicitly asks to retry validation.
6. Never call index_document more than once. Never call reject_document after indexing.

Chat workflow:
1. Call search_documents before answering. You may search again with a refined query if needed (max 6 searches).
2. Only cite page numbers that appear in search results (e.g. [Page 3]).
3. Use citation format: {reference: pageNumber: <page number>}
4. Always end each chat turn with answer_user.

Anti-loop rules:
- Do not call the same tool repeatedly with the same intent.
- If a tool returns a limit or error message, follow its instructions and move to the next step.
- After index_document or reject_document succeeds, stop immediately."""


class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]


def _route_after_agent(state: AgentState) -> Literal["tools", "__end__"]:
    last = state["messages"][-1]
    if isinstance(last, AIMessage) and last.tool_calls:
        return "tools"
    return END


def _route_after_tools(state: AgentState) -> Literal["agent", "__end__"]:
    batch: list[ToolMessage] = []
    for message in reversed(state["messages"]):
        if isinstance(message, ToolMessage):
            batch.append(message)
            continue
        if isinstance(message, AIMessage):
            break

    if any(msg.name in TERMINAL_TOOLS for msg in batch):
        return END
    return "agent"


def extract_final_answer(messages: list[BaseMessage]) -> str:
    for message in reversed(messages):
        if isinstance(message, ToolMessage) and message.name == "answer_user":
            return str(message.content)

    for message in reversed(messages):
        if isinstance(message, AIMessage) and message.content and not message.tool_calls:
            content = message.content
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                parts = []
                for block in content:
                    if isinstance(block, str):
                        parts.append(block)
                    elif isinstance(block, dict) and "text" in block:
                        parts.append(str(block["text"]))
                return "\n".join(parts)

    return "No answer was generated."


def build_agent_graph(
    context: AgentContext,
    checkpointer: MemorySaver | None = None,
):
    llm = get_llm()
    tools = create_agent_tools(context)
    llm_with_tools = llm.bind_tools(tools)
    tool_node = ToolNode(tools)

    def agent(state: AgentState) -> dict:
        response = llm_with_tools.invoke(
            [SystemMessage(content=AGENT_SYSTEM_PROMPT)] + state["messages"]
        )
        return {"messages": [response]}

    graph = StateGraph(AgentState)
    graph.add_node("agent", agent)
    graph.add_node("tools", tool_node)
    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", _route_after_agent, ["tools", END])
    graph.add_conditional_edges("tools", _route_after_tools, ["agent", END])

    if checkpointer is None:
        checkpointer = MemorySaver()

    return graph.compile(checkpointer=checkpointer)
