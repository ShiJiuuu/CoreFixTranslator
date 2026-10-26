import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import type { ChatSummary, Job } from "../types";
import { Card, Empty, Progress, StatusPill } from "../components/ui";
import { formatTime } from "../lib/format";

export default function Workbench() {
  const jobs = useQuery({
    queryKey: ["jobs", "recent"],
    queryFn: () => api<{ jobs: Job[] }>("/api/jobs?limit=6"),
    refetchInterval: 5000,
  });
  const chats = useQuery({
    queryKey: ["chats", "recent"],
    queryFn: () => api<{ chats: ChatSummary[] }>("/api/chats?limit=5"),
    refetchInterval: 10000,
  });

  const active = (jobs.data?.jobs || []).filter((job) =>
    ["queued", "parsing", "translating", "rebuilding"].includes(job.status),
  );

  return (
    <div className="space-y-5">
      <div className="grid gap-4 sm:grid-cols-3">
        <Link to="/translate" className="card transition hover:border-accent/60">
          <div className="text-sm font-semibold">新建翻译</div>
          <div className="mt-1 text-xs text-slate-500">上传 Word / Excel / PDF / 文本</div>
        </Link>
        <Link to="/chat" className="card transition hover:border-accent/60">
          <div className="text-sm font-semibold">开始对话</div>
          <div className="mt-1 text-xs text-slate-500">和本地模型聊天，可附文件</div>
        </Link>
        <Link to="/glossary" className="card transition hover:border-accent/60">
          <div className="text-sm font-semibold">管理术语</div>
          <div className="mt-1 text-xs text-slate-500">统一专有名词译法</div>
        </Link>
      </div>

      <Card
        title="正在处理"
        actions={
          <Link to="/jobs" className="text-xs text-blue-600 hover:underline">
            全部任务
          </Link>
        }
      >
        {active.length === 0 ? (
          <Empty>当前没有运行中的任务</Empty>
        ) : (
          <div className="space-y-3">
            {active.map((job) => (
              <Link key={job.id} to={"/jobs/" + job.id} className="block rounded-lg border border-line px-3 py-2 hover:border-accent/50">
                <div className="flex items-center justify-between gap-3">
                  <span className="truncate text-sm">{job.file_name || job.id}</span>
                  <StatusPill status={job.status} />
                </div>
                <div className="mt-2">
                  <Progress value={job.progress} />
                </div>
              </Link>
            ))}
          </div>
        )}
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="最近任务">
          {!jobs.data || jobs.data.jobs.length === 0 ? (
            <Empty>还没有任务</Empty>
          ) : (
            <ul className="space-y-2">
              {jobs.data.jobs.map((job) => (
                <li key={job.id} className="flex items-center justify-between gap-3 text-sm">
                  <Link to={"/jobs/" + job.id} className="truncate hover:text-blue-600">
                    {job.file_name || job.id}
                  </Link>
                  <span className="shrink-0 text-xs text-slate-500">{formatTime(job.created_at)}</span>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card
          title="最近对话"
          actions={
            <Link to="/chat" className="text-xs text-blue-600 hover:underline">
              全部对话
            </Link>
          }
        >
          {!chats.data || chats.data.chats.length === 0 ? (
            <Empty>还没有对话</Empty>
          ) : (
            <ul className="space-y-2">
              {chats.data.chats.map((chat) => (
                <li key={chat.id} className="flex items-center justify-between gap-3 text-sm">
                  <Link to={"/chat/" + chat.id} className="truncate hover:text-blue-600">
                    {chat.title}
                  </Link>
                  <span className="shrink-0 text-xs text-slate-500">{chat.message_count} 条</span>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </div>
  );
}
