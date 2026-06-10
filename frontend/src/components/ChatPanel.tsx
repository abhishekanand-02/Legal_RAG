import { useEffect, useRef, useState } from "react";
import type { LoadingAction, SessionState } from "../types";
import { ChatMessageBubble, ThinkingBubble } from "./ChatMessage";
import { AgentActivityBar } from "./AgentActivityBar";

interface Props {
  session: SessionState | null;
  loading: boolean;
  loadingAction: LoadingAction;
  onSendMessage: (message: string) => void;
  onResumeInterrupt: (response: string) => void;
}

export function ChatPanel({
  session,
  loading,
  loadingAction,
  onSendMessage,
  onResumeInterrupt,
}: Props) {
  const [input, setInput] = useState("");
  const [interruptInput, setInterruptInput] = useState("");
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const status = session?.doc_status ?? "idle";
  const chatEnabled = session?.chat_enabled ?? false;
  const interrupt = session?.agent_interrupt;

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [session?.messages, loading]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = input.trim();
    if (!trimmed || loading || interrupt) return;
    setInput("");
    onSendMessage(trimmed);
  };

  const handleInterruptSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = interruptInput.trim();
    if (!trimmed || loading) return;
    setInterruptInput("");
    onResumeInterrupt(trimmed);
  };

  return (
    <div className="panel">
      <h2 className="section-title">Chat</h2>

      <AgentActivityBar
        loading={loading && (loadingAction === "chat" || loadingAction === "interrupt")}
        action={loadingAction}
        docStatus={status}
      />

      {status === "idle" && (
        <div className="alert alert-info">
          Upload a PDF to start. The agent will validate it before chat opens.
        </div>
      )}

      {status === "pending_approval" && (
        <div className="alert alert-info">
          Waiting for your decision in the Document panel. The agent paused until
          you approve or reject.
        </div>
      )}

      {status === "validation_error" && (
        <div className="alert alert-warning">
          Validation failed. Use Retry validation in the Document panel.
        </div>
      )}

      {status === "rejected" && (
        <div className="alert alert-error">
          Chat is disabled for this document. Upload a different PDF to continue.
        </div>
      )}

      {session && chatEnabled && interrupt && (
        <>
          <div className="alert alert-info">
            <strong>Agent asks:</strong> {interrupt.question}
          </div>
          <form className="chat-form" onSubmit={handleInterruptSubmit}>
            <input
              value={interruptInput}
              onChange={(e) => setInterruptInput(e.target.value)}
              placeholder="Type your answer..."
              disabled={loading}
            />
            <button
              type="submit"
              className="btn btn-primary"
              disabled={loading || !interruptInput.trim()}
            >
              Reply to agent
            </button>
          </form>
        </>
      )}

      {session && chatEnabled && !interrupt && (
        <>
          <div className="chat-messages">
            {session.messages.length === 0 && !loading && (
              <div className="chat-empty">
                Ask a question about the uploaded document. The agent will search
                indexed passages before answering.
              </div>
            )}
            {session.messages.map((msg, i) => (
              <ChatMessageBubble
                key={i}
                role={msg.role}
                content={msg.content}
                responseTime={msg.response_time}
                isError={msg.is_error}
              />
            ))}
            {loading && loadingAction === "chat" && <ThinkingBubble />}
            <div ref={messagesEndRef} />
          </div>

          <form className="chat-form" onSubmit={handleSubmit}>
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Ask about the document..."
              disabled={loading}
            />
            <button
              type="submit"
              className="btn btn-primary"
              disabled={loading || !input.trim()}
            >
              Send
            </button>
          </form>
        </>
      )}

      {session &&
        !chatEnabled &&
        status !== "idle" &&
        status !== "pending_approval" &&
        status !== "validation_error" &&
        status !== "rejected" && (
          <div className="alert alert-info">Document is not ready for chat yet.</div>
        )}
    </div>
  );
}
