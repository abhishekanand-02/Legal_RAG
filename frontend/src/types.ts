export type LoadingAction =
  | "upload"
  | "approve"
  | "reject"
  | "retry"
  | "skip"
  | "chat"
  | "interrupt"
  | null;

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  response_time?: number;
  is_error?: boolean;
}

export interface ValidationInfo {
  is_valid?: boolean;
  category?: string;
  reason?: string;
}

export interface AgentInterrupt {
  type?: string;
  question?: string;
}

export interface SessionState {
  session_id: string;
  pdf_name: string | null;
  doc_status: string;
  validation_info: ValidationInfo | null;
  validation_error: string | null;
  agent_interrupt: AgentInterrupt | null;
  ready: boolean;
  messages: ChatMessage[];
  chat_enabled: boolean;
  approved_by_user?: boolean;
}

export interface ConfigStatus {
  ready: boolean;
  missing_keys: string[];
}

export function agentActivityLabel(
  loading: boolean,
  action: LoadingAction,
  docStatus: string,
): string | null {
  if (!loading) return null;

  switch (action) {
    case "upload":
      return "Validating document classification…";
    case "approve":
      return "Indexing document for search and chat…";
    case "reject":
      return "Recording your decision…";
    case "retry":
      return "Re-running document validation…";
    case "skip":
      return "Indexing document without validation…";
    case "chat":
      return "Searching document and generating response…";
    case "interrupt":
      return "Processing your response…";
    default:
      if (docStatus === "pending_approval") {
        return "Processing…";
      }
      return "Processing…";
  }
}
