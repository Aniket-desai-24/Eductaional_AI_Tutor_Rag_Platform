import type { Citation, Document, Course, MemoryProfile, Analytics } from "../types";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

function getToken(): string | null {
  return localStorage.getItem("edu_rag_token");
}

async function apiFetch<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(options.headers as Record<string, string> || {}),
  };

  const response = await fetch(`${API_BASE}${path}`, { ...options, headers });

  if (response.status === 401) {
    localStorage.removeItem("edu_rag_token");
    localStorage.removeItem("edu_rag_user");
    window.location.href = "/login";
    throw new Error("Unauthorized");
  }

  if (!response.ok) {
    const err = await response.json().catch(() => ({ detail: "Request failed" }));
    throw new Error(err.detail || "Request failed");
  }

  return response.json();
}

// ── Auth ──────────────────────────────────────────────────────────────────────
export const authApi = {
  login: (email: string, password: string) =>
    apiFetch<{ access_token: string; user_id: string; email: string; full_name: string; role: string }>(
      "/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }
    ),
  register: (email: string, password: string, full_name: string) =>
    apiFetch<{ access_token: string; user_id: string; email: string; full_name: string; role: string }>(
      "/auth/register", { method: "POST", body: JSON.stringify({ email, password, full_name }) }
    ),
  me: () => apiFetch<{ id: string; email: string; full_name: string; role: string }>("/auth/me"),
};

// ── Query ─────────────────────────────────────────────────────────────────────
export function streamQuery(
  question: string,
  sessionId: string,
  namespace?: string,
  callbacks: {
    onStatus?: (msg: string) => void;
    onCitations?: (citations: Citation[]) => void;
    onToken?: (token: string) => void;
    onDone?: (data: { query_log_id: string; latency_ms: number }) => void;
    onError?: (msg: string) => void;
  } = {}
): () => void {
  const token = getToken();
  const controller = new AbortController();

  const body = JSON.stringify({ question, session_id: sessionId, namespace });

  fetch(`${API_BASE}/query`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body,
    signal: controller.signal,
  }).then(async (response) => {
    if (!response.ok) {
      callbacks.onError?.("Failed to connect to the server");
      return;
    }

    const reader = response.body!.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    const dispatchEventBlock = (block: string) => {
      const lines = block.split("\n");
      let eventType = "";
      let dataStr = "";

      for (const rawLine of lines) {
        const line = rawLine.trimEnd();
        if (line.startsWith("event:")) {
          eventType = line.slice(6).trim();
        } else if (line.startsWith("data:")) {
          dataStr += line.slice(5).trim();
        }
      }

      if (!eventType || !dataStr) return;

      try {
        const data = JSON.parse(dataStr);
        if (eventType === "status") callbacks.onStatus?.(data.message);
        else if (eventType === "citations") callbacks.onCitations?.(data.citations);
        else if (eventType === "token") callbacks.onToken?.(data.content);
        else if (eventType === "done") callbacks.onDone?.(data);
        else if (eventType === "error") callbacks.onError?.(data.message);
      } catch {
        // Ignore malformed SSE payloads and keep stream alive.
      }
    };

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const blocks = buffer.split("\n\n");
      buffer = blocks.pop() || "";
      for (const block of blocks) {
        dispatchEventBlock(block);
      }
    }

    // Handle any final complete event block left after stream completion.
    if (buffer.trim()) {
      dispatchEventBlock(buffer);
    }
  }).catch((err) => {
    if (err.name !== "AbortError") callbacks.onError?.(err.message);
  });

  return () => controller.abort();
}

export const queryApi = {
  getHistory: (sessionId: string) =>
    apiFetch<{ session_id: string; turns: Array<{ role: string; content: string }> }>(
      `/query/history?session_id=${sessionId}`
    ),
  clearHistory: (sessionId: string) =>
    apiFetch(`/query/history?session_id=${sessionId}`, { method: "DELETE" }),
  submitFeedback: (queryLogId: string, feedback: 1 | -1) =>
    apiFetch("/query/feedback", {
      method: "POST",
      body: JSON.stringify({ query_log_id: queryLogId, feedback }),
    }),
};

// ── Memory ────────────────────────────────────────────────────────────────────
export const memoryApi = {
  getProfile: () => apiFetch<MemoryProfile>("/memory/profile"),
  deleteProfile: () => apiFetch("/memory/profile", { method: "DELETE" }),
};

// ── Admin ─────────────────────────────────────────────────────────────────────
export const adminApi = {
  listDocuments: () => apiFetch<Document[]>("/admin/documents"),
  getDocument: (id: string) => apiFetch<Document>(`/admin/documents/${id}`),
  listCourses: () => apiFetch<Course[]>("/admin/courses"),
  createCourse: (name: string, description?: string) =>
    apiFetch<Course>("/admin/courses", { method: "POST", body: JSON.stringify({ name, description }) }),
  getAnalytics: () => apiFetch<Analytics>("/admin/analytics"),
  listUsers: () => apiFetch<Array<{ id: string; email: string; full_name: string; role: string }>>("/admin/users"),
  enrollUser: (courseId: string, userId: string) =>
    apiFetch(`/admin/courses/${courseId}/enroll/${userId}`, { method: "POST" }),
  ingestDocument: (formData: FormData) =>
    fetch(`${API_BASE}/admin/ingest`, {
      method: "POST",
      headers: { Authorization: `Bearer ${getToken()}` },
      body: formData,
    }).then((r) => r.json()),
};
