import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import type { Glossary, Job, Meta, UploadedFile } from "../types";
import { Button, Card, Field, Progress, StatusPill } from "../components/ui";

export default function Translate() {
  const [params] = useSearchParams();
  const presetFileId = params.get("file");
  const [presetName, setPresetName] = useState<string | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [source, setSource] = useState("auto");
  const [target, setTarget] = useState("zh-CN");
  const [style, setStyle] = useState("natural");
  const [domain, setDomain] = useState("general");
  const [glossaryId, setGlossaryId] = useState("");
  const [headers, setHeaders] = useState(false);
  const [glossaryText, setGlossaryText] = useState("");
  const [jobId, setJobId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const meta = useQuery({ queryKey: ["meta"], queryFn: () => api<Meta>("/api/meta") });
  const glossaries = useQuery({ queryKey: ["glossaries"], queryFn: () => api<{ glossaries: Glossary[] }>("/api/glossaries") });
  const job = useQuery({
    queryKey: ["job", jobId],
    queryFn: () => api<Job>("/api/jobs/" + jobId),
    enabled: !!jobId,
    refetchInterval: (query) => {
      const data = query.state.data;
      if (!data) return 1500;
      return ["completed", "failed", "cancelled"].includes(data.status) ? false : 1500;
    },
  });

  useEffect(() => {
    if (meta.data && !presetFileId) setTarget(meta.data.default_target_language);
  }, [meta.data, presetFileId]);

  useEffect(() => {
    if (!presetFileId) return;
    let cancelled = false;
    api<{ id: string; filename: string; size_bytes: number }>("/api/files/" + presetFileId)
      .then((record) => {
        if (!cancelled) setPresetName(record.filename);
      })
      .catch(() => {
        if (!cancelled) setPresetName(null);
      });
    return () => {
      cancelled = true;
    };
  }, [presetFileId]);

  async function start() {
    setError(null);
    setBusy(true);
    try {
      let fileId = presetFileId;
      if (!fileId) {
        if (!file) {
          setError("请选择文件");
          return;
        }
        const form = new FormData();
        form.append("file", file);
        const uploaded = await api<UploadedFile>("/api/files", { method: "POST", body: form });
        fileId = uploaded.id;
      }
      const created = await api<Job>("/api/jobs", {
        method: "POST",
        body: JSON.stringify({
          file_id: fileId,
          source_language: source,
          target_language: target,
          style,
          domain,
          glossary_id: glossaryId || null,
          glossary_text: glossaryText,
          translate_headers: headers,
        }),
      });
      setJobId(created.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  const current = job.data;
  const done = current ? ["completed", "failed", "cancelled"].includes(current.status) : false;

  return (
    <div className="space-y-5">
      <Card title="新建翻译">
        <div className="grid gap-4">
          {presetFileId ? (
            <div className="rounded-lg border border-line px-3 py-2 text-sm">
              已选附件：<span className="text-slate-800">{presetName || presetFileId}</span>
            </div>
          ) : (
            <Field label="文件（docx / xlsx / xlsm / pdf / txt / md）">
              <input
                type="file"
                accept=".docx,.xlsx,.xlsm,.pdf,.txt,.md"
                className="input file:mr-3 file:rounded-md file:border-0 file:bg-blue-50 file:px-3 file:py-1 file:text-blue-700"
                onChange={(event) => setFile(event.target.files ? event.target.files[0] : null)}
              />
              {file && file.name.toLowerCase().endsWith(".pdf") && (
                <div className="mt-1 text-xs text-amber-600">
                  PDF 输出纯译文重排（保留标题/段落结构，不保留原版面）；需要 LibreOffice 转 PDF，或设置 PDF_RENDER=docx。
                </div>
              )}
            </Field>
          )}

          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="源语言">
              <select className="input" value={source} onChange={(event) => setSource(event.target.value)}>
                <option value="auto">自动检测</option>
                <option value="en">English</option>
                <option value="zh-CN">简体中文</option>
                <option value="ja">日本語</option>
                <option value="ko">한국어</option>
                <option value="fr">Français</option>
                <option value="de">Deutsch</option>
                <option value="es">Español</option>
                <option value="ru">Русский</option>
              </select>
            </Field>
            <Field label="目标语言">
              <select className="input" value={target} onChange={(event) => setTarget(event.target.value)}>
                {(meta.data?.target_languages || []).map((item) => (
                  <option key={item.code} value={item.code}>
                    {item.label}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="风格">
              <select className="input" value={style} onChange={(event) => setStyle(event.target.value)}>
                {(meta.data?.styles || []).map((item) => (
                  <option key={item.code} value={item.code}>
                    {item.label}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="领域">
              <select className="input" value={domain} onChange={(event) => setDomain(event.target.value)}>
                {(meta.data?.domains || []).map((item) => (
                  <option key={item.code} value={item.code}>
                    {item.label}
                  </option>
                ))}
              </select>
            </Field>
          </div>

          <Field label="术语库（可选）">
            <select className="input" value={glossaryId} onChange={(event) => setGlossaryId(event.target.value)}>
              <option value="">不使用</option>
              {(glossaries.data?.glossaries || []).map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}（{item.term_count} 条）
                </option>
              ))}
            </select>
          </Field>

          <Field label="临时术语（可选，每行：源词 => 译词）">
            <textarea className="input min-h-24" value={glossaryText} onChange={(event) => setGlossaryText(event.target.value)} />
          </Field>

          <label className="flex items-center gap-2 text-sm text-slate-500">
            <input type="checkbox" checked={headers} onChange={(event) => setHeaders(event.target.checked)} />
            同时翻译 Word 页眉页脚
          </label>

          <div className="flex items-center gap-3">
            <Button onClick={start} disabled={busy}>
              {busy ? "提交中…" : "开始翻译"}
            </Button>
            {error && <span className="text-sm text-red-600">{error}</span>}
          </div>
        </div>
      </Card>

      {current && (
        <Card
          title="任务进度"
          actions={
            <Link to={"/jobs/" + current.id} className="text-xs text-blue-600 hover:underline">
              任务详情
            </Link>
          }
        >
          <div className="flex items-center justify-between gap-3">
            <div className="truncate text-sm">{current.file_name || current.id}</div>
            <StatusPill status={current.status} />
          </div>
          <div className="mt-3">
            <Progress value={current.progress} tone={current.status === "failed" ? "err" : undefined} />
          </div>
          <div className="mt-2 text-xs text-slate-500">
            {current.progress}%
            {current.total_units ? " · " + (current.done_units || 0) + "/" + current.total_units + " 段" : ""}
          </div>
          {current.error_summary && <div className="mt-2 text-sm text-red-600">{current.error_summary}</div>}
          {done && current.status === "completed" && (
            <div className="mt-3 flex gap-4 text-sm">
              <a className="text-blue-600 hover:underline" href={"/api/jobs/" + current.id + "/download"}>
                下载译文
              </a>
              <a className="text-blue-600 hover:underline" href={"/api/jobs/" + current.id + "/download?kind=report"}>
                质量报告
              </a>
              <a className="text-blue-600 hover:underline" href={"/api/jobs/" + current.id + "/download?kind=source"}>
                原文件
              </a>
            </div>
          )}
          {done && current.status !== "completed" && (
            <div className="mt-3">
              <Button
                variant="ghost"
                onClick={async () => {
                  await api<Job>("/api/jobs/" + current.id + "/retry", { method: "POST" });
                  setJobId(current.id);
                }}
              >
                重试
              </Button>
            </div>
          )}
        </Card>
      )}
    </div>
  );
}
