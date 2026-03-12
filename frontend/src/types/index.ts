export interface User {
  id: string;
  email: string;
  full_name: string;
  role: "student" | "teacher" | "admin";
  is_active: boolean;
}

export interface AuthState {
  user: User | null;
  token: string | null;
  sessionId: string;
}

export interface Citation {
  label: string;
  chunk_id: string;
  chapter?: number;
  section?: string;
  page_start?: number;
  page_end?: number;
  content_type: "text" | "image_caption" | "table" | "equation";
  image_url?: string;
  snippet: string;
  score: number;
}

export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
  query_log_id?: string;
  feedback?: 1 | -1 | null;
  timestamp: Date;
  isStreaming?: boolean;
}

export interface Document {
  id: string;
  title: string;
  namespace: string;
  status: "pending" | "processing" | "completed" | "failed";
  total_pages?: number;
  total_chunks?: number;
  created_at: string;
  error_message?: string;
}

export interface Course {
  id: string;
  name: string;
  description?: string;
}

export interface MemoryProfile {
  learning_level: string;
  subject_mastery: Record<string, number>;
  weak_areas: string[];
  strong_areas: string[];
  frequently_asked_topics: string[];
  total_queries: number;
  last_active?: string;
}

export interface Analytics {
  total_queries: number;
  total_users: number;
  total_documents: number;
  avg_latency_ms: number;
  positive_feedback: number;
  negative_feedback: number;
}
