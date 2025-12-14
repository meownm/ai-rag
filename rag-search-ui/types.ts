
export interface HighlightedCitation {
  source_id: number;
  doc_id: string;
  chunk_id: number;
  filename: string;
  highlighted_text: string;
  score: number;
}

export interface Filters {
  space?: string[];
  author?: string[];
  date_from?: string; // YYYY-MM-DD
  date_to?: string; // YYYY-MM-DD
  doc_type?: string[];
}

export type SearchMode = "dense" | "bm25" | "hybrid" | "graph" | "hybrid+graph";
export type ContextMode = "short" | "long";

export type UserRole = 'admin' | 'editor' | 'viewer';

export interface AnswerRequest {
  query: string;
  conversation_id?: string | null;
  stream: boolean;
  mode: SearchMode;
  context_mode: ContextMode;
  graph_depth: number;
  top_k: number;
  filters?: Filters;
  max_tokens: number;
}

export interface AnswerResponse {
  answer: string;
  conversation_id: string;
  citations: HighlightedCitation[];
  graph_context?: { content: string }[];
  graph_status: string;
  enrichment_used: boolean;
  used_chunks: number;
  used_tokens: number;
  latency_ms: number;
}

export interface StreamTextChunk {
  type: "text";
  content: string;
}

export interface StreamMetadataChunk {
  type: "metadata";
  conversation_id: string;
  citations: HighlightedCitation[];
  graph_context?: { content: string }[];
  graph_status: string;
  enrichment_used: boolean;
  used_chunks: number;
  used_tokens: number;
  latency_ms: number;
}

export type StreamChunk = StreamTextChunk | StreamMetadataChunk;

export interface ConversationInfo {
    conversation_id: string;
    user_id?: string | null;
    title?: string | null;
    created_at: string; // ISO datetime string
}

export interface UserProfile {
    id: string;
    name: string;
    email: string;
    organization: string;
    role: UserRole;
    telegramUsername?: string | null;
}

export interface AdminUser extends UserProfile {
    status: 'active' | 'invited' | 'blocked';
    lastActivity: string;
}

export interface Invite {
    id: string;
    email?: string;
    link: string;
    createdAt: string;
    invitedBy: string;
    status: 'pending' | 'accepted';
    type: 'email' | 'link';
}

export interface Message {
    id: string;
    role: 'user' | 'assistant';
    content: string;
    citations?: HighlightedCitation[];
    graph_context?: { content: string }[];
    graph_status?: string;
    enrichment_used?: boolean;
    used_chunks?: number;
    used_tokens?: number;
    latency_ms?: number;
    isLoading?: boolean;
}
