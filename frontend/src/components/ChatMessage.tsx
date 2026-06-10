import {
  ChatMessageContent,
  extractPageReferences,
} from "./ChatMessageContent";

interface Props {
  role: "user" | "assistant";
  content: string;
  responseTime?: number;
  isError?: boolean;
}

export function ChatMessageBubble({
  role,
  content,
  responseTime,
  isError,
}: Props) {
  const label = role === "user" ? "You" : isError ? "Agent error" : "Agent";
  const pageReferences =
    role === "assistant" && !isError ? extractPageReferences(content) : [];
  const showFooter =
    role === "assistant" &&
    !isError &&
    (responseTime !== undefined || pageReferences.length > 0);

  return (
    <div className={`chat-row ${role}`}>
      <div
        className={`chat-bubble ${role}${isError ? " error" : ""}`}
      >
        <div className="chat-label">{label}</div>
        {role === "assistant" && !isError ? (
          <ChatMessageContent content={content} />
        ) : (
          content
        )}
        {showFooter && (
          <>
            <hr className="response-timing-divider" />
            <div className="response-meta">
              {responseTime !== undefined && (
                <span className="response-timing">
                  Response time: {responseTime.toFixed(1)}s
                </span>
              )}
              {pageReferences.length > 0 && (
                <div className="response-references">
                  {pageReferences.map((page) => (
                    <span key={page} className="chat-citation">
                      p. {page}
                    </span>
                  ))}
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}

export function ThinkingBubble() {
  return (
    <div className="chat-row assistant">
      <div className="chat-bubble assistant thinking">
        <div className="chat-label">Agent</div>
        Searching documents and reasoning…
      </div>
    </div>
  );
}
