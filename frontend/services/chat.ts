import type { ApiResponse, ChatData, ChatRequest, Message } from "@/types/message";
import type { AgentTraceData } from "@/types/trace";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

async function apiRequest<T>(url: string, options?: RequestInit): Promise<ApiResponse<T>> {
  const response = await fetch(url, {
    headers: {
      "Content-Type": "application/json",
    },
    ...options,
  });

  const envelope: ApiResponse<T> = await response.json();

  if (!envelope.success) {
    const error = new Error(envelope.error?.message || "Request failed");
    (error as Error & { code?: string }).code = envelope.error?.code;
    throw error;
  }

  return envelope;
}

export interface ChatResult {
  message: Message;
  trace: AgentTraceData | null;
}

export async function sendChatMessage(request: ChatRequest): Promise<ChatResult> {
  const envelope = await apiRequest<ChatData>(`${API_BASE_URL}/api/v1/chat`, {
    method: "POST",
    body: JSON.stringify(request),
  });

  return {
    message: envelope.data!.reply,
    trace: envelope.data!.trace || null,
  };
}

export interface ChatStreamHandlers {
  /** 每收到一段 LLM 文本增量时回调（真流式，非打字机动画）。 */
  onDelta?: (text: string) => void;
  signal?: AbortSignal;
}

type StreamEvent =
  | { type: "start" }
  | { type: "delta"; text: string }
  | { type: "done"; data: ApiResponse<ChatData> }
  | { type: "error"; message: string };

/**
 * SSE 流式聊天：POST /api/v1/chat/stream。
 * 逐帧解析 `data: {...}` 事件，delta 走 onDelta 回调，done 返回与非流式
 * 完全一致的 ChatResult（含 trace / pending 卡片元数据）。
 */
export async function sendChatMessageStream(
  request: ChatRequest,
  handlers: ChatStreamHandlers = {},
): Promise<ChatResult> {
  const response = await fetch(`${API_BASE_URL}/api/v1/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
    signal: handlers.signal,
  });

  if (!response.ok || !response.body) {
    throw new Error("Stream request failed");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let result: ChatResult | null = null;

  const handleFrame = (frame: string) => {
    const dataLine = frame.split("\n").find((line) => line.startsWith("data: "));
    if (!dataLine) return;
    const event = JSON.parse(dataLine.slice("data: ".length)) as StreamEvent;
    if (event.type === "delta") {
      handlers.onDelta?.(event.text);
    } else if (event.type === "done") {
      result = {
        message: event.data.data!.reply,
        trace: event.data.data!.trace || null,
      };
    } else if (event.type === "error") {
      throw new Error(event.message);
    }
  };

  let streamError: unknown = null;
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let frameEnd = buffer.indexOf("\n\n");
      while (frameEnd >= 0) {
        try {
          handleFrame(buffer.slice(0, frameEnd));
        } catch (err) {
          streamError = err;
        }
        buffer = buffer.slice(frameEnd + 2);
        frameEnd = buffer.indexOf("\n\n");
      }
      if (streamError) break;
    }
  } finally {
    reader.releaseLock();
  }

  if (streamError) throw streamError;
  if (!result) throw new Error("流式响应未返回结果");
  return result;
}
