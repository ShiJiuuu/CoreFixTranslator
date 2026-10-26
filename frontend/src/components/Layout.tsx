import { NavLink, Outlet } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import { cx } from "../lib/format";

const LINKS = [
  { to: "/", label: "工作台", end: true },
  { to: "/translate", label: "翻译", end: false },
  { to: "/jobs", label: "任务", end: false },
  { to: "/chat", label: "对话", end: false },
  { to: "/glossary", label: "术语库", end: false },
  { to: "/settings", label: "设置", end: false },
];

interface Health {
  status: string;
  model_reachable: boolean;
  root: string;
}

export default function Layout() {
  const health = useQuery({
    queryKey: ["health"],
    queryFn: () => api<Health>("/api/health"),
    refetchInterval: 20000,
  });

  const reachable = health.data?.model_reachable;

  return (
    <div className="min-h-full md:flex">
      <aside className="border-b border-line md:w-56 md:border-b-0 md:border-r md:min-h-screen md:sticky md:top-0">
        <div className="px-4 py-4">
          <div className="text-base font-semibold tracking-wide">文档翻译器</div>
          <div className="mt-1 flex items-center gap-2 text-xs text-slate-500">
            <span
              className={cx(
                "inline-block h-2 w-2 rounded-full",
                reachable === true ? "bg-emerald-400" : reachable === false ? "bg-red-400" : "bg-slate-600",
              )}
            />
            {reachable === true ? "模型已连接" : reachable === false ? "模型未就绪" : "检查中…"}
          </div>
        </div>
        <nav className="flex gap-1 overflow-x-auto px-2 pb-2 md:flex-col md:pb-4">
          {LINKS.map((link) => (
            <NavLink
              key={link.to}
              to={link.to}
              end={link.end}
              className={({ isActive }) =>
                cx(
                  "whitespace-nowrap rounded-lg px-3 py-2 text-sm",
                  isActive ? "bg-blue-50 text-blue-700" : "text-slate-500 hover:text-slate-800",
                )
              }
            >
              {link.label}
            </NavLink>
          ))}
        </nav>
      </aside>
      <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-5 md:px-8 md:py-8">
        <Outlet />
      </main>
    </div>
  );
}
