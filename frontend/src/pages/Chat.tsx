import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, streamChat } from "../lib/api";
import type { ChatDetail, ChatSummary, UploadedFile } from "../types";
import { Button, Empty } from "../components/ui";
import { cx, formatBytes } from "../lib/format";

const TRANSLATABLE = [".docx", ".xlsx", ".xlsm", ".pdf", ".txt", ".md"];

export default function Chat() {
  const { id } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [input, setInput] = useState("");
  const [pendingFiles, setPendingFiles] = useState<UploadedFile[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [streamText, setStreamText] = useState("");
  const [localUser, setLocalUser] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const fileRef = useRef<HTMLInputElement | null>(null);

  const chats = useQuery({
    queryKey: ["chats"],
    queryFn: () => api<{ chats: ChatSummary[] }>("/api/chats"),
    refetchInterval: 8000,
  });
  const detail = useQuery({
    queryKey: ["chat", id],
    queryFn: () => api<ChatDetail>("/api/chats/" + id),
    enabled: !!id,
  });

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [detail.data?.messages.length, streamText, localUser]);

  async function createChat() {
    const chat = await api<{ id: string; title: string }>("/api/chats", { method: "POST", body: JSON.stringify({}) });
    await queryClient.invalidateQueries({ queryKey: ["chats"] });
    navigate("/chat/" + chat.id);
  }

  async function removeChat(chatId: string) {
    await api("/api/chats/" + chatId, { method: "DELETE" });
    await queryClient.invalidateQueries({ queryKey: ["chats"] });
    if (chatId === id) navigate("/chat");
  }

  async function attach(file: File) {
    const form = new FormData();
    form.append("file", file);
    try {
      const uploaded = await api<UploadedFile>("/api/files", { method: "POST", body: form });
      setPendingFiles((prev) => [...prev, uploaded]);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function send() {
    if (!id || streaming) return;
    const content = input.trim();
    if (!content) return;
    const fileIds = pendingFiles.map((file) => file.id);
    setInput("");
    setPendingFiles([]);
    setLocalUser(content);
    setStreaming(true);
    setStreamText("");
    setError(null);
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      await streamChat(
        id,
        { content, file_ids: fileIds },
        {
          onDelta: (text) => setStreamText((prev) => prev + text),
          onDone: () => undefined,
          onStopped: () => undefined,
          onError: (message) => setError(message),
        },
        controller.signal,
      );
    } catch (err) {
      const error = err as Error;
      if (error.name !== "AbortError") setError(error.message);
    } finally {
      setStreaming(false);
      abortRef.current = null;
      await queryClient.refetchQueries({ queryKey: ["chat", id] });
      await queryClient.invalidateQueries({ queryKey: ["chats"] });
      setStreamText("");
      setLocalUser(null);
    }
  }

  const messages = detail.data?.messages || [];

  return (
    <div className="md:grid md:grid-cols-[240px_1fr] md:gap-5">
      <aside className={cx("mb-4 md:mb-0", id ? "hidden md:block" : "")}>
        <div className="mb-3 flex items-center gap-2">
          <Button onClick={createChat}>新对话</Button>
          {!id && <span className="text-xs text-slate-500">选择或新建一个对话</span>}
        </div>
        <div className="space-y-1">
          {(chats.data?.chats || []).map((chat) => (
            <div
              key={chat.id}
              className={cx(
                "group flex items-center justify-between gap-2 rounded-lg px-2 py-2 text-sm",
                chat.id === id ? "bg-blue-50 text-blue-700" : "text-slate-500 hover:bg-slate-100",
              )}
            >
              <Link to={"/chat/" + chat.id} className="min-w-0 flex-1 truncate">
                {chat.title}
              </Link>
              <button
                className="hidden text-xs text-slate-500 hover:text-red-600 group-hover:block"
                onClick={() => removeChat(chat.id)}
                aria-label="删除对话"
              >
                删除
              </button>
            </div>
          ))}
          {chats.data && chats.data.chats.length === 0 && <div className="text-xs text-slate-500">还没有对话</div>}
        </div>
      </aside>

      <section className="flex min-h-[70vh] flex-col rounded-xl border border-line bg-panel">
        {!id ? (
          <div className="flex flex-1 items-center justify-center">
            <Empty>新建一个对话开始聊天</Empty>
          </div>
        ) : (
          <>
            <header className="flex items-center justify-between gap-3 border-b border-line px-4 py-3">
              <div className="min-w-0">
                <Link to="/chat" className="mr-2 text-xs text-slate-500 hover:text-slate-600 md:hidden">
                  ← 返回
                </Link>
                <span className="text-sm font-medium">{detail.data?.title || "对话"}</span>
              </div>
              <button
                className="text-xs text-slate-500 hover:text-red-600"
                onClick={() => removeChat(id)}
              >
                删除对话
              </button>
            </header>

            <div className="flex-1 space-y-4 overflow-y-auto px-4 py-4" style={{ maxHeight: "58vh" }}>
              {messages.map((message) => (
                <div key={message.id} className={cx("flex", message.role === "user" ? "justify-end" : "justify-start")}>
                  <div
                    className={cx(
                      "max-w-[85%] rounded-xl px-3 py-2 text-sm",
                      message.role === "user" ? "bg-accent text-white" : "bg-slate-100 text-slate-800",
                    )}
                  >
                    <div className="whitespace-pre-wrap break-words">{message.content}</div>
                    {message.attachments.length > 0 && (
                      <div className="mt-2 flex flex-wrap gap-2">
                        {message.attachments.map((file) => (
                          <span
                            key={file.id}
                            className={
                              message.role === "user"
                                ? "rounded-md border border-white/40 px-2 py-1 text-xs text-blue-50"
                                : "rounded-md border border-line px-2 py-1 text-xs text-slate-500"
                            }
                          >
                            {file.original_filename}（{formatBytes(file.size_bytes)}）
                          </span>
                        ))}
                      </div>
                    )}
                    {message.role === "assistant" && message.status !== "complete" && (
                      <div className="mt-1 text-xs text-amber-600">
                        {message.status === "stopped" ? "已停止生成" : "生成出错"}
                      </div>
                    )}
                  </div>
                </div>
              ))}

              {localUser && (
                <div className="flex justify-end">
                  <div className="max-w-[85%] rounded-xl bg-accent px-3 py-2 text-sm text-white whitespace-pre-wrap">{localUser}</div>
                </div>
              )}
              {streaming && (
                <div className="flex justify-start">
                  <div className="max-w-[85%] rounded-xl bg-slate-100 px-3 py-2 text-sm whitespace-pre-wrap">
                    {streamText || "…"}
                  </div>
                </div>
              )}
              <div ref={bottomRef} />
            </div>

            {error && <div className="border-t border-red-400/20 bg-red-50 px-4 py-2 text-xs text-red-700">{error}</div>}

            <div className="border-t border-line p-3">
              {pendingFiles.length > 0 && (
                <div className="mb-1 text-xs text-slate-400">附件正文会作为文本提供给模型（过长会截断）。</div>
              )}
              {pendingFiles.length > 0 && (
                <div className="mb-2 flex flex-wrap gap-2">
                  {pendingFiles.map((file) => (
                    <span key={file.id} className="flex items-center gap-2 rounded-md border border-line px-2 py-1 text-xs text-slate-500">
                      {file.filename}
                      {TRANSLATABLE.some((ext) => file.filename.toLowerCase().endsWith(ext)) && (
                        <Link to={"/translate?file=" + file.id} className="text-blue-600 hover:underline">
                          翻译
                        </Link>
                      )}
                      <button
                        className="text-slate-500 hover:text-red-600"
                        onClick={() => setPendingFiles((prev) => prev.filter((item) => item.id !== file.id))}
                      >
                        ×
                      </button>
                    </span>
                  ))}
                </div>
              )}
              <div className="flex items-end gap-2">
                <button
                  className="rounded-lg border border-line px-3 py-2 text-sm text-slate-500 hover:text-slate-800"
                  onClick={() => fileRef.current?.click()}
                  aria-label="添加附件"
                >
                  +
                </button>
                <input
                  ref={fileRef}
                  type="file"
                  className="hidden"
                  onChange={(event) => {
                    const file = event.target.files ? event.target.files[0] : null;
                    if (file) attach(file);
                    event.target.value = "";
                  }}
                />
                <textarea
                  className="input max-h-40 min-h-[42px] flex-1 resize-none"
                  placeholder="输入消息，Enter 发送，Shift+Enter 换行"
                  value={input}
                  onChange={(event) => setInput(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" && !event.shiftKey) {
                      event.preventDefault();
                      send();
                    }
                  }}
                />
                {streaming ? (
                  <Button variant="danger" onClick={() => abortRef.current?.abort()}>
                    停止
                  </Button>
                ) : (
                  <Button onClick={send} disabled={!input.trim()}>
                    发送
                  </Button>
                )}
              </div>
            </div>
          </>
        )}
      </section>
    </div>
  );
}
