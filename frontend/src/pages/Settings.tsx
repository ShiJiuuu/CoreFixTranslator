import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";
import type { SettingsPayload } from "../types";
import { Button, Card, Field } from "../components/ui";

type FieldType = "text" | "number" | "select";

interface FieldDef {
  key: string;
  label: string;
  type: FieldType;
  step?: string;
  options?: { value: string; label: string }[];
}

const GROUPS: { title: string; fields: FieldDef[] }[] = [
  {
    title: "模型连接",
    fields: [
      { key: "model_root_url", label: "llama.cpp 根地址", type: "text" },
      { key: "model_base_url", label: "/v1 地址", type: "text" },
      { key: "model_alias", label: "模型名", type: "text" },
      { key: "model_timeout_seconds", label: "超时（秒）", type: "number" },
      {
        key: "json_mode",
        label: "JSON 模式",
        type: "select",
        options: [
          { value: "auto", label: "auto" },
          { value: "json_object", label: "json_object" },
          { value: "none", label: "none" },
        ],
      },
      {
        key: "enable_thinking",
        label: "思考模式",
        type: "select",
        options: [
          { value: "false", label: "关闭" },
          { value: "true", label: "开启" },
        ],
      },
    ],
  },
  {
    title: "翻译采样",
    fields: [
      { key: "temperature_translate", label: "temperature", type: "number", step: "0.05" },
      { key: "top_p", label: "top_p", type: "number", step: "0.05" },
      { key: "top_k", label: "top_k", type: "number" },
      { key: "repeat_penalty", label: "repeat_penalty", type: "number", step: "0.01" },
      { key: "seed", label: "随机种子", type: "number" },
    ],
  },
  {
    title: "批预算",
    fields: [
      { key: "max_output_tokens", label: "输出上限", type: "number" },
      { key: "target_output_tokens", label: "目标输出", type: "number" },
      { key: "token_expansion", label: "扩展比", type: "number", step: "0.05" },
      { key: "prompt_overhead_tokens", label: "提示开销", type: "number" },
      { key: "max_units_per_batch", label: "每批单元数", type: "number" },
    ],
  },
  {
    title: "对话",
    fields: [
      { key: "temperature_chat", label: "temperature", type: "number", step: "0.05" },
      { key: "chat_context_ratio", label: "上下文占比", type: "number", step: "0.05" },
      { key: "chat_max_history_turns", label: "最多轮数", type: "number" },
      { key: "chat_max_output_tokens", label: "输出上限", type: "number" },
    ],
  },
  {
    title: "上传",
    fields: [
      { key: "max_upload_mb", label: "上传上限（MB）", type: "number" },
      { key: "default_target_language", label: "默认目标语言", type: "text" },
    ],
  },
];

export default function Settings() {
  const queryClient = useQueryClient();
  const settings = useQuery({ queryKey: ["settings"], queryFn: () => api<SettingsPayload>("/api/settings") });
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [message, setMessage] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!settings.data) return;
    const next: Record<string, string> = {};
    for (const group of GROUPS) {
      for (const field of group.fields) {
        const value = settings.data.values[field.key];
        next[field.key] = typeof value === "boolean" ? String(value) : String(value ?? "");
      }
    }
    setDraft(next);
  }, [settings.data]);

  async function save() {
    setBusy(true);
    setMessage(null);
    try {
      const patch: Record<string, string | number | boolean> = {};
      for (const group of GROUPS) {
        for (const field of group.fields) {
          const raw = draft[field.key] ?? "";
          if (field.type === "number") patch[field.key] = Number(raw);
          else if (field.key === "enable_thinking") patch[field.key] = raw === "true";
          else patch[field.key] = raw;
        }
      }
      await api<{ values: Record<string, string | number | boolean> }>("/api/settings", {
        method: "PATCH",
        body: JSON.stringify(patch),
      });
      setMessage("已保存，立即生效");
      await queryClient.invalidateQueries({ queryKey: ["settings"] });
      await queryClient.invalidateQueries({ queryKey: ["health"] });
    } catch (err) {
      setMessage(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function testModel() {
    setTestResult("测试中…");
    try {
      const data = await api<{ ok: boolean; latency_ms?: number; info?: { total_slots?: number; slot_ctx?: number } }>(
        "/api/model/test",
        { method: "POST" },
      );
      if (!data.ok) {
        setTestResult("模型未就绪");
        return;
      }
      const info = data.info || {};
      setTestResult(
        "连接正常 · " + (data.latency_ms || 0) + "ms · 槽位 " + (info.total_slots ?? "?") + " · 上下文 " + (info.slot_ctx ?? "?"),
      );
    } catch (err) {
      setTestResult(err instanceof Error ? err.message : String(err));
    }
  }

  return (
    <div className="space-y-5">
      {GROUPS.map((group) => (
        <Card key={group.title} title={group.title}>
          <div className="grid gap-3 sm:grid-cols-2">
            {group.fields.map((field) => (
              <Field key={field.key} label={field.label}>
                {field.type === "select" ? (
                  <select
                    className="input"
                    value={draft[field.key] ?? ""}
                    onChange={(event) => setDraft((prev) => ({ ...prev, [field.key]: event.target.value }))}
                  >
                    {(field.options || []).map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                ) : (
                  <input
                    className="input"
                    type={field.type}
                    step={field.step}
                    value={draft[field.key] ?? ""}
                    onChange={(event) => setDraft((prev) => ({ ...prev, [field.key]: event.target.value }))}
                  />
                )}
              </Field>
            ))}
          </div>
        </Card>
      ))}

      <div className="flex flex-wrap items-center gap-3">
        <Button onClick={save} disabled={busy || !settings.data}>
          {busy ? "保存中…" : "保存设置"}
        </Button>
        <Button variant="ghost" onClick={testModel}>
          测试连接
        </Button>
        {message && <span className="text-sm text-slate-500">{message}</span>}
        {testResult && <span className="text-sm text-slate-500">{testResult}</span>}
      </div>
    </div>
  );
}
