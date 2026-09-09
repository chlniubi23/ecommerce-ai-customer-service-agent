import type { AgentTraceData } from "@/types/trace";

export type MessageRole = "user" | "assistant" | "system";
export type MessageType = "text";
export type MessageStatus = "completed";
export type MessageMetadata = Record<string, unknown>;

export interface Message {
  id: string;
  role: MessageRole;
  type: MessageType;
  content: string;
  timestamp: string;
  status: MessageStatus;
  metadata?: MessageMetadata;
}

export interface ApiErrorDetail {
  code: string;
  message: string;
  detail?: string;
}

export interface ResponseMetadata {
  trace_id: string;
  timestamp: string;
  model?: string;
  usage?: {
    prompt_tokens: number;
    completion_tokens: number;
    total_tokens: number;
  };
}

export interface ApiResponse<T> {
  success: boolean;
  data: T | null;
  error: ApiErrorDetail | null;
  metadata: ResponseMetadata;
}

export interface ChatData {
  reply: Message;
  trace?: AgentTraceData | null;
}

export interface ChatRequest {
  message: string;
  history: {
    role: MessageRole;
    content: string;
  }[];
  session_id?: string;
}

export function generateMessageId(): string {
  const array = new Uint8Array(8);
  crypto.getRandomValues(array);
  return Array.from(array, (b) => b.toString(16).padStart(2, "0")).join("");
}

export function createUserMessage(content: string): Message {
  return {
    id: generateMessageId(),
    role: "user",
    type: "text",
    content,
    timestamp: new Date().toISOString(),
    status: "completed",
  };
}
