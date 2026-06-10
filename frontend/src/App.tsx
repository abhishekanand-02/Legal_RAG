import { useCallback, useEffect, useRef, useState } from "react";
import "./App.css";
import * as api from "./api/client";
import type { LoadingAction, SessionState } from "./types";
import { DocumentPanel } from "./components/DocumentPanel";
import { ChatPanel } from "./components/ChatPanel";
import { ToastContainer } from "./components/Toast";

interface ToastItem {
  id: number;
  message: string;
  type: "success" | "warning" | "error";
}

type ConfigError = "connection" | "missing_keys";

async function loadConfigStatus(retries = 5, delayMs = 2000) {
  let lastError: unknown;
  for (let attempt = 0; attempt < retries; attempt += 1) {
    try {
      return await api.getConfigStatus();
    } catch (err) {
      lastError = err;
      if (attempt < retries - 1) {
        await new Promise((resolve) => window.setTimeout(resolve, delayMs));
      }
    }
  }
  throw lastError;
}

export default function App() {
  const [configReady, setConfigReady] = useState<boolean | null>(null);
  const [configError, setConfigError] = useState<ConfigError | null>(null);
  const [missingKeys, setMissingKeys] = useState<string[]>([]);
  const [session, setSession] = useState<SessionState | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadingAction, setLoadingAction] = useState<LoadingAction>(null);
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const toastId = useRef(0);

  const addToast = useCallback(
    (message: string, type: ToastItem["type"] = "success") => {
      const id = ++toastId.current;
      setToasts((prev) => [...prev, { id, message, type }]);
    },
    [],
  );

  const dismissToast = useCallback((id: number) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  useEffect(() => {
    loadConfigStatus()
      .then((status) => {
        if (status.ready) {
          setConfigReady(true);
          setConfigError(null);
          setMissingKeys([]);
          return;
        }
        setConfigReady(false);
        setConfigError("missing_keys");
        setMissingKeys(status.missing_keys);
      })
      .catch(() => {
        setConfigReady(false);
        setConfigError("connection");
        setMissingKeys([]);
      });
  }, []);

  const withLoading = async (
    action: LoadingAction,
    fn: () => Promise<SessionState>,
    options?: {
      successToast?: { message: string; type?: ToastItem["type"] };
      errorIf?: (result: SessionState) => string | null;
    },
  ) => {
    setLoading(true);
    setLoadingAction(action);
    try {
      const result = await fn();
      setSession(result);

      const errorMessage = options?.errorIf?.(result);
      if (errorMessage) {
        addToast(errorMessage, "error");
        return;
      }

      if (options?.successToast) {
        addToast(options.successToast.message, options.successToast.type ?? "success");
      }
    } catch (err) {
      addToast(err instanceof Error ? err.message : "Request failed", "error");
    } finally {
      setLoading(false);
      setLoadingAction(null);
    }
  };

  const handleUpload = async (file: File) => {
    setLoading(true);
    setLoadingAction("upload");
    try {
      const result = await api.uploadDocument(file);
      setSession(result);
      if (result.doc_status === "validation_error") {
        addToast(result.validation_error ?? "Validation failed", "error");
      } else if (result.doc_status === "valid") {
        addToast("Document validated successfully.");
      } else if (result.doc_status === "pending_approval") {
        addToast("Document classified — your review is required before indexing.", "warning");
      }
    } catch (err) {
      addToast(err instanceof Error ? err.message : "Upload failed", "error");
    } finally {
      setLoading(false);
      setLoadingAction(null);
    }
  };

  const handleApprove = () =>
    withLoading(
      "approve",
      () => api.approveDocument(session!.session_id),
      {
        successToast: { message: "Document approved. Chat is enabled." },
        errorIf: (result) =>
          result.doc_status === "pending_approval" && result.validation_error
            ? result.validation_error
            : null,
      },
    );

  const handleReject = () =>
    withLoading("reject", () => api.rejectDocument(session!.session_id), {
      successToast: {
        message: "Document rejected. Chat disabled.",
        type: "warning",
      },
    });

  const handleRetryValidation = () =>
    withLoading("retry", () => api.retryValidation(session!.session_id), {
      errorIf: (result) =>
        result.doc_status === "validation_error"
          ? result.validation_error ?? "Validation failed"
          : null,
    });

  const handleSkipValidation = () =>
    withLoading("skip", () => api.skipValidation(session!.session_id), {
      successToast: {
        message: "Document indexed without validation.",
        type: "warning",
      },
    });

  const handleSendMessage = async (message: string) => {
    if (!session) return;

    setSession({
      ...session,
      messages: [...session.messages, { role: "user", content: message }],
    });
    setLoading(true);
    setLoadingAction("chat");

    try {
      const result = await api.sendMessage(session.session_id, message);
      setSession(result);
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : "Request failed";
      setSession((prev) =>
        prev
          ? {
              ...prev,
              messages: [
                ...prev.messages,
                {
                  role: "assistant",
                  content: errorMessage,
                  is_error: true,
                },
              ],
            }
          : prev,
      );
      addToast(errorMessage, "error");
    } finally {
      setLoading(false);
      setLoadingAction(null);
    }
  };

  const handleResumeInterrupt = (response: string) =>
    withLoading("interrupt", () =>
      api.resumeInterrupt(session!.session_id, response),
    );

  if (configReady === null) {
    return (
      <div className="app">
        <div
          className="spinner-overlay"
          style={{ justifyContent: "center", marginTop: "2rem" }}
        >
          <span className="spinner" />
          Loading...
        </div>
      </div>
    );
  }

  if (!configReady) {
    return (
      <div className="config-error">
        <div className="alert alert-error">
          {configError === "connection" ? (
            <>
              <strong>Cannot reach the backend API.</strong>
              <br />
              <br />
              The frontend could not connect to <code>/api/status</code>. Your
              .env keys may be fine — start the backend first, then reload.
              <br />
              <br />
              With Docker: <code>docker compose up --build</code>
              <br />
              Dev mode: backend on port <code>8000</code>, frontend on{" "}
              <code>5173</code> or <code>3000</code>.
            </>
          ) : (
            <>
              <strong>Missing API keys in .env:</strong>{" "}
              {missingKeys.join(", ")}. Copy <code>.env.example</code> to{" "}
              <code>.env</code> and add your keys.
            </>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="app">
      <header className="app-header">
        <div className="app-header-text">
          <h1 className="app-title">PageTalk</h1>
          <p className="app-subtitle">
            The ultimate chat interface for your PDFs. <b>Fact-checked</b>, <b>fast</b>, and <b>completely secure</b>.
          </p>
        </div>
        <div className="app-header-actions">
          <span className="api-status api-connected" role="status">
            <span className="api-status-dot" aria-hidden="true" />
            API Connected
          </span>
        </div>
      </header>

      <div className="layout">
        <DocumentPanel
          session={session}
          loading={loading}
          loadingAction={loadingAction}
          onUpload={handleUpload}
          onApprove={handleApprove}
          onReject={handleReject}
          onRetryValidation={handleRetryValidation}
          onSkipValidation={handleSkipValidation}
        />
        <ChatPanel
          session={session}
          loading={loading}
          loadingAction={loadingAction}
          onSendMessage={handleSendMessage}
          onResumeInterrupt={handleResumeInterrupt}
        />
      </div>

      <footer className="app-footer">
        Observability and tool traces are available in{" "}
        <a
          href="https://smith.langchain.com"
          target="_blank"
          rel="noopener noreferrer"
        >
          LangSmith
        </a>
        .
      </footer>

      <ToastContainer toasts={toasts} onDismiss={dismissToast} />
    </div>
  );
}
