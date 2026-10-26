import type { ReactNode } from "react";
import { STATUS_LABEL, cx } from "../lib/format";

export function Button({
  children,
  onClick,
  variant = "primary",
  disabled,
  type = "button",
  className,
}: {
  children: ReactNode;
  onClick?: () => void;
  variant?: "primary" | "ghost" | "danger";
  disabled?: boolean;
  type?: "button" | "submit";
  className?: string;
}) {
  const base = "inline-flex items-center justify-center rounded-lg px-4 py-2 text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-50";
  const styles = {
    primary: "bg-accent text-slate-950 hover:bg-blue-400",
    ghost: "border border-line text-slate-200 hover:border-slate-500",
    danger: "border border-red-500/40 text-red-300 hover:bg-red-500/10",
  } as const;
  return (
    <button type={type} onClick={onClick} disabled={disabled} className={cx(base, styles[variant], className)}>
      {children}
    </button>
  );
}

export function Card({ title, actions, children }: { title?: ReactNode; actions?: ReactNode; children: ReactNode }) {
  return (
    <section className="rounded-xl border border-line bg-panel p-4">
      {(title || actions) && (
        <header className="mb-4 flex items-center justify-between gap-3">
          {title ? <h2 className="text-sm font-semibold text-slate-200">{title}</h2> : <span />}
          {actions}
        </header>
      )}
      {children}
    </section>
  );
}

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="label">{label}</span>
      {children}
    </label>
  );
}

export function Progress({ value, tone }: { value: number; tone?: "ok" | "err" }) {
  const width = Math.max(0, Math.min(100, value));
  return (
    <div className="h-2 w-full overflow-hidden rounded-full border border-line bg-[#0e1015]">
      <div
        className={cx("h-full transition-all", tone === "err" ? "bg-red-400" : "bg-accent")}
        style={{ width: width + "%" }}
      />
    </div>
  );
}

export function StatusPill({ status }: { status: string }) {
  const tone =
    status === "completed"
      ? "text-emerald-300 border-emerald-400/30"
      : status === "failed"
        ? "text-red-300 border-red-400/30"
        : status === "cancelled"
          ? "text-slate-400 border-line"
          : "text-blue-300 border-blue-400/30";
  return (
    <span className={cx("inline-flex rounded-full border px-2 py-0.5 text-xs", tone)}>
      {STATUS_LABEL[status] || status}
    </span>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="py-10 text-center text-sm text-slate-500">{children}</div>;
}
