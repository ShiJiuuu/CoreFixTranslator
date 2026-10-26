import { Link, useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";
import type { Job, Report } from "../types";
import { Button, Card, Empty, Progress, StatusPill } from "../components/ui";
import { formatTime } from "../lib/format";

export function Jobs() {
  const queryClient = useQueryClient();
  const jobs = useQuery({
    queryKey: ["jobs"],
    queryFn: () => api<{ jobs: Job[] }>("/api/jobs"),
    refetchInterval: 3000,
  });

  async function act(path: string) {
    await api(path, { method: "POST" });
    queryClient.invalidateQueries({ queryKey: ["jobs"] });
  }

  return (
    <Card title="任务列表">
      {!jobs.data ? (
        <Empty>加载中…</Empty>
      ) : jobs.data.jobs.length === 0 ? (
        <Empty>还没有任务</Empty>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-slate-500">
                <th className="py-2 pr-3">文件</th>
                <th className="py-2 pr-3">状态</th>
                <th className="py-2 pr-3">进度</th>
                <th className="hidden py-2 pr-3 sm:table-cell">时间</th>
                <th className="py-2">操作</th>
              </tr>
            </thead>
            <tbody>
              {jobs.data.jobs.map((job) => (
                <tr key={job.id} className="border-t border-line">
                  <td className="max-w-[220px] truncate py-3 pr-3">
                    <Link to={"/jobs/" + job.id} className="hover:text-blue-600">
                      {job.file_name || job.id}
                    </Link>
                  </td>
                  <td className="py-3 pr-3">
                    <StatusPill status={job.status} />
                  </td>
                  <td className="w-40 py-3 pr-3">
                    <Progress value={job.progress} tone={job.status === "failed" ? "err" : undefined} />
                    <span className="text-xs text-slate-500">{job.progress}%</span>
                  </td>
                  <td className="hidden py-3 pr-3 text-xs text-slate-500 sm:table-cell">{formatTime(job.created_at)}</td>
                  <td className="space-x-3 py-3 text-xs">
                    {job.status === "completed" && (
                      <a className="text-blue-600 hover:underline" href={"/api/jobs/" + job.id + "/download"}>
                        下载
                      </a>
                    )}
                    {(job.status === "failed" || job.status === "cancelled") && (
                      <button className="text-blue-600 hover:underline" onClick={() => act("/api/jobs/" + job.id + "/retry")}>
                        重试
                      </button>
                    )}
                    {["queued", "parsing", "translating", "rebuilding"].includes(job.status) && (
                      <button className="text-red-600 hover:underline" onClick={() => act("/api/jobs/" + job.id + "/cancel")}>
                        取消
                      </button>
                    )}
                    {job.status === "completed" && (
                      <a className="text-slate-500 hover:underline" href={"/api/jobs/" + job.id + "/download?kind=report"}>
                        报告
                      </a>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}

export function JobDetail() {
  const { id } = useParams();
  const queryClient = useQueryClient();
  const job = useQuery({
    queryKey: ["job", id],
    queryFn: () => api<Job>("/api/jobs/" + id),
    enabled: !!id,
    refetchInterval: (query) => {
      const data = query.state.data;
      if (!data) return 1500;
      return ["completed", "failed", "cancelled"].includes(data.status) ? false : 1500;
    },
  });
  const report = useQuery({
    queryKey: ["report", id],
    queryFn: () => api<Report>("/api/jobs/" + id + "/report"),
    enabled: !!id && !!job.data && job.data.status === "completed",
    retry: 0,
  });

  if (!id) return null;
  if (!job.data) return <Empty>加载中…</Empty>;
  const current = job.data;

  async function act(path: string) {
    await api(path, { method: "POST" });
    queryClient.invalidateQueries({ queryKey: ["job", id] });
  }

  return (
    <div className="space-y-5">
      <Card
        title={current.file_name || current.id}
        actions={<StatusPill status={current.status} />}
      >
        <Progress value={current.progress} tone={current.status === "failed" ? "err" : undefined} />
        <div className="mt-3 grid gap-2 text-sm text-slate-500 sm:grid-cols-2">
          <div>进度：{current.progress}%</div>
          <div>阶段：{current.stage || "-"}</div>
          <div>单元：{current.done_units || 0}/{current.total_units || "-"}</div>
          <div>创建：{formatTime(current.created_at)}</div>
        </div>
        {current.error_summary && (
          <div className="mt-3 rounded-lg border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-700">
            {current.error_code}: {current.error_summary}
          </div>
        )}
        {current.file_name?.toLowerCase().endsWith(".pdf") && current.status === "completed" && (
          <div className="mt-3 rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-700">
            PDF 译文是重建后的 DOCX 文件，下载后用 Word 打开；原 PDF 的逐页版式不会保留。
          </div>
        )}
        <div className="mt-4 flex flex-wrap gap-3 text-sm">
          {current.status === "completed" && (
            <>
              <a className="text-blue-600 hover:underline" href={"/api/jobs/" + current.id + "/download"}>
                下载译文
              </a>
              <a className="text-blue-600 hover:underline" href={"/api/jobs/" + current.id + "/download?kind=report"}>
                下载报告
              </a>
            </>
          )}
          <a className="text-slate-500 hover:underline" href={"/api/jobs/" + current.id + "/download?kind=source"}>
            原文件
          </a>
          {(current.status === "failed" || current.status === "cancelled") && (
            <Button variant="ghost" onClick={() => act("/api/jobs/" + current.id + "/retry")}>
              重试
            </Button>
          )}
          {["queued", "parsing", "translating", "rebuilding"].includes(current.status) && (
            <Button variant="danger" onClick={() => act("/api/jobs/" + current.id + "/cancel")}>
              取消
            </Button>
          )}
        </div>
      </Card>

      {report.data && (
        <Card title="质量检查">
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="text-sm text-slate-500">单元总数：{report.data.units}</div>
            <div className="text-sm text-slate-500">已翻译：{report.data.translated}</div>
            <div className="text-sm text-slate-500">耗时：{report.data.duration_seconds}s</div>
            <div className="text-sm text-slate-500">
              结构检查：{report.data.hard_checks_ok ? "通过" : "存在问题"}
            </div>
          </div>
          <div className="mt-4 space-y-1 text-xs text-slate-500">
            {report.data.checks.map((check, index) => (
              <div key={index} className={check.ok ? "text-slate-500" : "text-red-600"}>
                {check.check}: {check.ok ? "OK" : "FAIL"}
              </div>
            ))}
          </div>
          <div className="mt-4 grid gap-1 text-xs text-slate-500 sm:grid-cols-2">
            {Object.entries(report.data.quality.ratios || {}).map(([key, value]) => (
              <div key={key}>
                {key}: {(value * 100).toFixed(1)}%
              </div>
            ))}
          </div>
          {report.data.failed.length > 0 && (
            <div className="mt-3 text-xs text-amber-600">未拿到译文的单元：{report.data.failed.length} 个</div>
          )}
        </Card>
      )}
    </div>
  );
}
