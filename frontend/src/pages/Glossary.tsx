import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";
import type { Glossary, GlossaryDetail, Term } from "../types";
import { Button, Card, Empty, Field } from "../components/ui";
import { formatTime } from "../lib/format";

export function GlossaryPage() {
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [source, setSource] = useState("en");
  const [target, setTarget] = useState("zh-CN");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const glossaries = useQuery({
    queryKey: ["glossaries"],
    queryFn: () => api<{ glossaries: Glossary[] }>("/api/glossaries"),
  });

  async function create() {
    if (!name.trim()) {
      setError("请填写名称");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await api<Glossary>("/api/glossaries", {
        method: "POST",
        body: JSON.stringify({ name: name.trim(), source_language: source, target_language: target }),
      });
      setName("");
      await queryClient.invalidateQueries({ queryKey: ["glossaries"] });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-5">
      <Card title="新建术语库">
        <div className="grid gap-3 sm:grid-cols-4">
          <Field label="名称">
            <input className="input" value={name} onChange={(event) => setName(event.target.value)} placeholder="例如：产品术语" />
          </Field>
          <Field label="源语言">
            <select className="input" value={source} onChange={(event) => setSource(event.target.value)}>
              <option value="en">English</option>
              <option value="zh-CN">简体中文</option>
              <option value="ja">日本語</option>
            </select>
          </Field>
          <Field label="目标语言">
            <select className="input" value={target} onChange={(event) => setTarget(event.target.value)}>
              <option value="zh-CN">简体中文</option>
              <option value="en">English</option>
              <option value="ja">日本語</option>
            </select>
          </Field>
          <div className="flex items-end">
            <Button onClick={create} disabled={busy}>
              创建
            </Button>
          </div>
        </div>
        {error && <div className="mt-2 text-sm text-red-300">{error}</div>}
      </Card>

      <Card title="全部术语库">
        {!glossaries.data ? (
          <Empty>加载中…</Empty>
        ) : glossaries.data.glossaries.length === 0 ? (
          <Empty>还没有术语库</Empty>
        ) : (
          <div className="space-y-2">
            {glossaries.data.glossaries.map((glossary) => (
              <Link
                key={glossary.id}
                to={"/glossary/" + glossary.id}
                className="flex items-center justify-between rounded-lg border border-line px-3 py-2 hover:border-accent/50"
              >
                <div>
                  <div className="text-sm">{glossary.name}</div>
                  <div className="text-xs text-slate-500">
                    {glossary.source_language} → {glossary.target_language} · {glossary.term_count} 条 ·{" "}
                    {formatTime(glossary.created_at)}
                  </div>
                </div>
                <span className="text-xs text-slate-500">查看</span>
              </Link>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}

export function GlossaryDetailPage() {
  const { id } = useParams();
  const queryClient = useQueryClient();
  const [source, setSource] = useState("");
  const [target, setTarget] = useState("");
  const [importText, setImportText] = useState("");
  const [message, setMessage] = useState<string | null>(null);

  const detail = useQuery({
    queryKey: ["glossary", id],
    queryFn: () => api<GlossaryDetail>("/api/glossaries/" + id),
    enabled: !!id,
  });

  if (!id) return null;
  if (!detail.data) return <Empty>加载中…</Empty>;

  async function addTerm() {
    if (!source.trim() || !target.trim()) return;
    await api("/api/glossaries/" + id + "/terms", {
      method: "POST",
      body: JSON.stringify({ source: source.trim(), target: target.trim() }),
    });
    setSource("");
    setTarget("");
    await queryClient.invalidateQueries({ queryKey: ["glossary", id] });
    await queryClient.invalidateQueries({ queryKey: ["glossaries"] });
  }

  async function removeTerm(term: Term) {
    await api("/api/glossaries/" + id + "/terms/" + term.id, { method: "DELETE" });
    await queryClient.invalidateQueries({ queryKey: ["glossary", id] });
    await queryClient.invalidateQueries({ queryKey: ["glossaries"] });
  }

  async function importTerms() {
    if (!importText.trim()) return;
    const result = await api<{ imported: number }>("/api/glossaries/" + id + "/import", {
      method: "POST",
      body: JSON.stringify({ text: importText }),
    });
    setMessage("导入 " + result.imported + " 条");
    setImportText("");
    await queryClient.invalidateQueries({ queryKey: ["glossary", id] });
    await queryClient.invalidateQueries({ queryKey: ["glossaries"] });
  }

  async function removeGlossary() {
    await api("/api/glossaries/" + id, { method: "DELETE" });
    await queryClient.invalidateQueries({ queryKey: ["glossaries"] });
    window.location.href = "/glossary";
  }

  return (
    <div className="space-y-5">
      <Card
        title={detail.data.name}
        actions={
          <div className="flex items-center gap-3 text-xs">
            <a className="text-blue-300 hover:underline" href={"/api/glossaries/" + id + "/export.csv"}>
              导出 CSV
            </a>
            <button className="text-red-300 hover:underline" onClick={removeGlossary}>
              删除术语库
            </button>
          </div>
        }
      >
        <div className="text-xs text-slate-500">
          {detail.data.source_language} → {detail.data.target_language} · {detail.data.terms.length} 条
        </div>
        <div className="mt-4 grid gap-3 sm:grid-cols-[1fr_1fr_auto]">
          <Field label="源词">
            <input className="input" value={source} onChange={(event) => setSource(event.target.value)} />
          </Field>
          <Field label="译词">
            <input className="input" value={target} onChange={(event) => setTarget(event.target.value)} />
          </Field>
          <div className="flex items-end">
            <Button onClick={addTerm}>添加</Button>
          </div>
        </div>

        <div className="mt-4">
          <Field label="批量导入（每行：源词,译词 或 源词 => 译词）">
            <textarea className="input min-h-24" value={importText} onChange={(event) => setImportText(event.target.value)} />
          </Field>
          <div className="mt-2 flex items-center gap-3">
            <Button variant="ghost" onClick={importTerms}>
              导入
            </Button>
            {message && <span className="text-xs text-emerald-300">{message}</span>}
          </div>
        </div>
      </Card>

      <Card title="术语">
        {detail.data.terms.length === 0 ? (
          <Empty>还没有术语</Empty>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-slate-500">
                  <th className="py-2 pr-3">源词</th>
                  <th className="py-2 pr-3">译词</th>
                  <th className="py-2">操作</th>
                </tr>
              </thead>
              <tbody>
                {detail.data.terms.map((term) => (
                  <tr key={term.id} className="border-t border-line">
                    <td className="py-2 pr-3">{term.source_term}</td>
                    <td className="py-2 pr-3">{term.target_term}</td>
                    <td className="py-2">
                      <button className="text-xs text-red-300 hover:underline" onClick={() => removeTerm(term)}>
                        删除
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
