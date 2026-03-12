import { create } from "zustand";
import { persist } from "zustand/middleware";
import { v4 as uuidv4 } from "uuid";
import type { Message, User, Citation } from "../types";

// ── Auth Store ────────────────────────────────────────────────────────────────
interface AuthStore {
  user: User | null;
  token: string | null;
  sessionId: string;
  setAuth: (user: User, token: string) => void;
  logout: () => void;
  newSession: () => void;
}

export const useAuthStore = create<AuthStore>()(
  persist(
    (set) => ({
      user: null,
      token: null,
      sessionId: uuidv4(),
      setAuth: (user, token) => {
        localStorage.setItem("edu_rag_token", token);
        set({ user, token, sessionId: uuidv4() });
      },
      logout: () => {
        localStorage.removeItem("edu_rag_token");
        set({ user: null, token: null, sessionId: uuidv4() });
      },
      newSession: () => set({ sessionId: uuidv4() }),
    }),
    {
      name: "edu_rag_auth",
      partialize: (s) => ({ user: s.user, token: s.token, sessionId: s.sessionId }),
    }
  )
);

// ── Chat Store ────────────────────────────────────────────────────────────────
interface ChatStore {
  messages: Message[];
  isStreaming: boolean;
  statusMessage: string;
  selectedCitation: Citation | null;
  activeCitations: Citation[];

  addUserMessage: (content: string) => string;
  startAssistantMessage: () => string;
  appendToken: (id: string, token: string) => void;
  finishMessage: (id: string, citations: Citation[], queryLogId: string) => void;
  setFeedback: (id: string, feedback: 1 | -1) => void;
  setStatus: (msg: string) => void;
  setStreaming: (v: boolean) => void;
  setSelectedCitation: (c: Citation | null) => void;
  setActiveCitations: (c: Citation[]) => void;
  clearMessages: () => void;
}

export const useChatStore = create<ChatStore>()((set, get) => ({
  messages: [],
  isStreaming: false,
  statusMessage: "",
  selectedCitation: null,
  activeCitations: [],

  addUserMessage: (content) => {
    const id = uuidv4();
    set((s) => ({
      messages: [...s.messages, { id, role: "user", content, timestamp: new Date() }],
    }));
    return id;
  },

  startAssistantMessage: () => {
    const id = uuidv4();
    set((s) => ({
      messages: [...s.messages, {
        id, role: "assistant", content: "", timestamp: new Date(), isStreaming: true,
      }],
      isStreaming: true,
    }));
    return id;
  },

  appendToken: (id, token) =>
    set((s) => ({
      messages: s.messages.map((m) =>
        m.id === id ? { ...m, content: m.content + token } : m
      ),
    })),

  finishMessage: (id, citations, queryLogId) =>
    set((s) => ({
      messages: s.messages.map((m) =>
        m.id === id ? { ...m, isStreaming: false, citations, query_log_id: queryLogId } : m
      ),
      isStreaming: false,
      statusMessage: "",
    })),

  setFeedback: (id, feedback) =>
    set((s) => ({
      messages: s.messages.map((m) => (m.id === id ? { ...m, feedback } : m)),
    })),

  setStatus: (statusMessage) => set({ statusMessage }),
  setStreaming: (isStreaming) => set({ isStreaming }),
  setSelectedCitation: (selectedCitation) => set({ selectedCitation }),
  setActiveCitations: (activeCitations) => set({ activeCitations }),
  clearMessages: () => set({ messages: [], statusMessage: "", activeCitations: [] }),
}));
