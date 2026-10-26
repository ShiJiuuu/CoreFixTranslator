export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = "ApiError";
  }
}

async function parseError(res: Response): Promise<string> {
  try {
    const data = await res.json();
    if (typeof data.detail === "string") return data.detail;
    if (data.detail && typeof data.detail.message === "string") return data.detail.message;
    if (typeof data.error === "string") return data.error;
  } catch {
    // ignore
  }
  return res.statusText || "request failed";
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (!(init.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const res = await fetch(path, { ...init, headers });
  if (!res.ok) throw new ApiError(res.status, await parseError(res));
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export interface StreamHandlers {
  onDelta: (text: string) => void;
  onDone: (messageId?: string) => void;
  onStopped: (messageId?: string) => void;
  onError: (message: string) => void;
}

function dispatchChunk(chunk: string, handlers: StreamHandlers): void {
  let event = "message";
  let data = "";
  for (const line of chunk.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) data += line.slice(5).trim();
  }
  if (!data) return;
  let parsed: { text?: string; message_id?: string; message?: string };
  try {
    parsed = JSON.parse(data);
  } catch {
    return;
  }
  if (event === "delta" && parsed.text) handlers.onDelta(parsed.text);
  else if (event === "done") handlers.onDone(parsed.message_id);
  else if (event === "stopped") handlers.onStopped(parsed.message_id);
  else if (event === "error") handlers.onError(parsed.message || "model error");
}

export async function streamChat(
  chatId: string,
  body: { content: string; file_ids?: string[] },
  handlers: StreamHandlers,
  signal: AbortSignal,
): Promise<void> {
  const res = await fetch("/api/chats/" + chatId + "/messages/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
  if (!res.ok || !res.body) throw new ApiError(res.status, await parseError(res));
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let index = buffer.indexOf("\n\n");
    while (index >= 0) {
      const chunk = buffer.slice(0, index);
      buffer = buffer.slice(index + 2);
      dispatchChunk(chunk, handlers);
      index = buffer.indexOf("\n\n");
    }
  }
}
