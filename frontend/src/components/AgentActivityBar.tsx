import type { LoadingAction } from "../types";
import { agentActivityLabel } from "../types";

interface Props {
  loading: boolean;
  action: LoadingAction;
  docStatus: string;
}

export function AgentActivityBar({ loading, action, docStatus }: Props) {
  const label = agentActivityLabel(loading, action, docStatus);
  if (!label) return null;

  return (
    <div className="agent-activity" role="status" aria-live="polite">
      <span className="spinner" aria-hidden="true" />
      <span>{label}</span>
    </div>
  );
}
