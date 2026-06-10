import { useRef } from "react";
import type { LoadingAction, SessionState } from "../types";
import { pdfUrl } from "../api/client";
import { AgentActivityBar } from "./AgentActivityBar";

interface Props {
  session: SessionState | null;
  loading: boolean;
  loadingAction: LoadingAction;
  onUpload: (file: File) => void;
  onApprove: () => void;
  onReject: () => void;
  onRetryValidation: () => void;
  onSkipValidation: () => void;
}

export function DocumentPanel({
  session,
  loading,
  loadingAction,
  onUpload,
  onApprove,
  onReject,
  onRetryValidation,
  onSkipValidation,
}: Props) {
  const fileRef = useRef<HTMLInputElement>(null);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      onUpload(file);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const status = session?.doc_status ?? "idle";
  const info = session?.validation_info;
  const showAgentErrorDuringApproval =
    status === "pending_approval" && !!session?.validation_error;

  return (
    <div className="panel">
      <h2 className="section-title">Document</h2>

      <AgentActivityBar
        loading={
          loading &&
          (loadingAction === "upload" ||
            loadingAction === "approve" ||
            loadingAction === "reject" ||
            loadingAction === "retry" ||
            loadingAction === "skip")
        }
        action={loadingAction}
        docStatus={status}
      />

      <div className="file-upload">
        <input
          ref={fileRef}
          type="file"
          accept="application/pdf"
          onChange={handleFileChange}
          disabled={loading}
        />
      </div>
      {!session && !loading && (
        <div className="alert alert-info">
          Upload a PDF to begin. Documents are classified first; indexing begins
          after validation or your explicit approval.
        </div>
      )}

      {session && status === "validation_error" && (
        <>
          <div className="alert alert-error">
            <strong>Document validation could not be completed.</strong>
            <br />
            <br />
            {session.validation_error}
          </div>
          <p className="help-text">
            Scanned PDFs use Gemini OCR. Transient 503 errors usually clear after
            a short wait — try again.
          </p>
          <div className="btn-row">
            <button
              className="btn btn-primary"
              onClick={onRetryValidation}
              disabled={loading}
            >
              Retry validation
            </button>
            <button
              className="btn btn-secondary"
              onClick={onSkipValidation}
              disabled={loading}
            >
              Skip validation
            </button>
          </div>
        </>
      )}

      {session && status === "valid" && (
        <div className="alert alert-success">
          <strong>Document validated</strong> ({info?.category ?? "legal"}).
          <br />
          {info?.reason}
        </div>
      )}

      {session && status === "approved" && session.approved_by_user && (
        <div className="alert alert-warning">
          <strong>Document approved for processing</strong> despite a non-standard
          classification.
          <br />
          Category: {info?.category ?? "other"} — {info?.reason ?? "Not a valid legal document."}
        </div>
      )}

      {session && status === "approved" && !session.approved_by_user && (
        <div className="alert alert-success">
          <strong>Document ready for chat.</strong>
          {info?.reason && (
            <>
              <br />
              {info.reason}
            </>
          )}
        </div>
      )}

      {session && status === "rejected" && (
        <div className="alert alert-error">
          Document rejected. Chat is disabled for this file.
          <br />
          Reason: {info?.reason ?? "Not a valid legal document."}
        </div>
      )}

      {session && status === "pending_approval" && (
        <>
          {showAgentErrorDuringApproval && (
            <div className="alert alert-error">
              <strong>Approval could not be processed.</strong>
              <br />
              <br />
              {session.validation_error}
              <br />
              <br />
              Your approval was not saved. Try again below.
            </div>
          )}

          {!showAgentErrorDuringApproval && (
            <div className="alert alert-warning">
              <strong>Review required before indexing.</strong>
              <br />
              <br />
              {session.agent_interrupt?.question ??
                "This does not look like a legal, investigation, or criminal document. Proceed anyway?"}
              <br />
              <br />
              <strong>Category:</strong> {info?.category ?? "other"}
              <br />
              <strong>Reason:</strong> {info?.reason ?? "Unknown"}
            </div>
          )}

          <div className="btn-row">
            <button
              className="btn btn-primary"
              onClick={onApprove}
              disabled={loading}
            >
              Yes, proceed
            </button>
            <button
              className="btn btn-secondary"
              onClick={onReject}
              disabled={loading}
            >
              No, stop
            </button>
          </div>
        </>
      )}

      {session?.pdf_name && status !== "validation_error" && (
        <>
          <p className="pdf-name">{session.pdf_name}</p>
          <div className="pdf-viewer">
            <iframe title="PDF preview" src={pdfUrl(session.session_id)} />
          </div>
        </>
      )}
    </div>
  );
}
