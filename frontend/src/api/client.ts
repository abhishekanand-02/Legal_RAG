import type { ConfigStatus, SessionState } from "../types";

const API_BASE = import.meta.env.VITE_API_URL ?? "";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, options);
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const detail = (body as { detail?: string }).detail ?? response.statusText;
    throw new Error(detail);
  }
  return response.json() as Promise<T>;
}

export async function getConfigStatus(): Promise<ConfigStatus> {
  return request<ConfigStatus>("/api/status");
}

export async function uploadDocument(file: File): Promise<SessionState> {
  const form = new FormData();
  form.append("file", file);
  return request<SessionState>("/api/sessions/upload", {
    method: "POST",
    body: form,
  });
}

export async function getSession(sessionId: string): Promise<SessionState> {
  return request<SessionState>(`/api/sessions/${sessionId}`);
}

export function pdfUrl(sessionId: string): string {
  return `${API_BASE}/api/sessions/${sessionId}/pdf`;
}

export async function approveDocument(sessionId: string): Promise<SessionState> {
  return request<SessionState>(`/api/sessions/${sessionId}/approve`, { method: "POST" });
}

export async function rejectDocument(sessionId: string): Promise<SessionState> {
  return request<SessionState>(`/api/sessions/${sessionId}/reject`, { method: "POST" });
}

export async function retryValidation(sessionId: string): Promise<SessionState> {
  return request<SessionState>(`/api/sessions/${sessionId}/retry-validation`, {
    method: "POST",
  });
}

export async function skipValidation(sessionId: string): Promise<SessionState> {
  return request<SessionState>(`/api/sessions/${sessionId}/skip-validation`, {
    method: "POST",
  });
}

export async function sendMessage(sessionId: string, message: string): Promise<SessionState> {
  return request<SessionState>(`/api/sessions/${sessionId}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message }),
  });
}

export async function resumeInterrupt(
  sessionId: string,
  response: string,
): Promise<SessionState> {
  return request<SessionState>(`/api/sessions/${sessionId}/resume`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ response }),
  });
}
