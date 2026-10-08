import React, { ReactNode, useEffect, useRef } from "react";
import { psiLink } from "../format";
import type { Health } from "../types";

export function cx(...parts: (string | false | null | undefined)[]) {
  return parts.filter(Boolean).join(" ");
}

const HEALTH_STYLES: Record<Health, string> = {
  GOOD: "bg-emerald-50 text-emerald-700 ring-emerald-600/20",
  ATTENTION: "bg-amber-50 text-amber-800 ring-amber-600/25",
  FAILED: "bg-red-50 text-red-700 ring-red-600/20",
  PENDING: "bg-slate-100 text-slate-600 ring-slate-500/20",
};

export function StatusBadge({ status }: { status: Health }) {
  return (
    <span className={cx("inline-flex items-center rounded-md px-2 py-0.5 text-xs font-semibold ring-1 ring-inset", HEALTH_STYLES[status])}>
      {status}
    </span>
  );
}

export function Pill({ children, tone = "slate" }: { children: ReactNode; tone?: "slate" | "green" | "red" | "amber" | "blue" }) {
  const tones = {
    slate: "bg-slate-100 text-slate-700",
    green: "bg-emerald-50 text-emerald-700",
    red: "bg-red-50 text-red-700",
    amber: "bg-amber-50 text-amber-800",
    blue: "bg-brand-50 text-brand-700",
  };
  return <span className={cx("inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium", tones[tone])}>{children}</span>;
}

export function scoreColor(score: number | null | undefined, threshold = 90) {
  if (score === null || score === undefined) return "text-slate-400";
  if (score >= threshold) return "text-emerald-600";
  if (score >= 50) return "text-amber-600";
  return "text-red-600";
}

export function Score({ score, threshold = 90, failed, size = "md" }: { score: number | null | undefined; threshold?: number; failed?: boolean; size?: "md" | "lg" }) {
  if (failed) return <span className="text-sm font-semibold text-red-600">ERR</span>;
  return (
    <span className={cx("font-semibold tabular-nums", size === "lg" ? "text-3xl" : "text-sm", scoreColor(score, threshold))}>
      {score ?? "—"}
    </span>
  );
}

/** Opens the saved report straight on googlechrome.github.io/lighthouse/viewer (no local page in between). */
function openGoogleViewer(e: React.MouseEvent, resultId: number) {
  if (e.ctrlKey || e.metaKey || e.shiftKey || e.button !== 0) return; // let the browser handle new-tab clicks
  e.preventDefault();
  const win = window.open("about:blank", "_blank"); // opened synchronously so popup blockers allow it
  fetch(`/api/results/${resultId}/viewer-url`, { credentials: "same-origin" })
    .then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
    .then((d: { url: string }) => {
      if (win) {
        win.opener = null;
        win.location.replace(d.url);
      } else window.location.href = d.url;
    })
    .catch(() => {
      if (win) win.location.replace(`/api/results/${resultId}/report`);
    });
}

/** Score that opens the saved report of that exact test (or PageSpeed Insights if none was stored). */
export function PsiScore({ url, strategy, score, threshold = 90, failed, resultId, hasReport }: { url: string; strategy: string; score: number | null | undefined; threshold?: number; failed?: boolean; resultId?: number; hasReport?: boolean }) {
  // Always open our own report page for a stored test; it explains when no saved report exists
  // instead of silently starting a new PageSpeed analysis.
  const saved = !!resultId;
  if (score === null || score === undefined) {
    if (!failed) return <Score score={score} threshold={threshold} />;
  }
  return (
    <a
      href={saved ? `/api/results/${resultId}/${hasReport ? "viewer" : "report"}` : psiLink(url, strategy)}
      onClick={saved && hasReport ? (e) => openGoogleViewer(e, resultId!) : undefined}
      target="_blank"
      rel="noreferrer noopener"
      title={saved ? (hasReport ? `Open the saved ${strategy} report on Google Lighthouse Viewer` : "No saved report for this test (run a new test to capture one)") : `Open PageSpeed Insights (${strategy}) — runs a fresh analysis`}
      className="group inline-flex items-center gap-1 rounded px-1 -mx-1 hover:bg-slate-100"
    >
      <Score score={score} threshold={threshold} failed={failed} />
      <svg className="h-3 w-3 text-slate-400 group-hover:text-brand-600" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
        <path d="M11 3h6v6h-2V6.41l-6.29 6.3-1.42-1.42L13.59 5H11V3z" /><path d="M5 5h4v2H5v8h8v-4h2v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2z" />
      </svg>
      <span className="sr-only">PageSpeed report</span>
    </a>
  );
}

export function Spinner({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <svg className={cx("animate-spin text-current", className)} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" className="opacity-25" />
      <path d="M22 12a10 10 0 0 0-10-10" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
    </svg>
  );
}

export function LoadingBlock({ label = "Loading..." }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-2 py-16 text-sm text-slate-500">
      <Spinner /> {label}
    </div>
  );
}

export function EmptyState({ title, description, action }: { title: string; description?: string; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center px-6 py-14 text-center">
      <div className="mb-3 rounded-full bg-slate-100 p-3 text-slate-400">
        <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}><path d="M3 12h4l3 8 4-16 3 8h4" strokeLinecap="round" strokeLinejoin="round" /></svg>
      </div>
      <p className="text-sm font-semibold text-slate-800">{title}</p>
      {description && <p className="mt-1 max-w-md text-sm text-slate-500">{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="m-4 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800">
      <p className="font-medium">Something went wrong</p>
      <p className="mt-1">{message}</p>
      {onRetry && <button className="btn-secondary btn-sm mt-3" onClick={onRetry}>Try again</button>}
    </div>
  );
}

export function PageHeader({ title, description, actions }: { title: string; description?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
      <div className="min-w-0">
        <h1 className="text-xl font-semibold tracking-tight text-slate-900">{title}</h1>
        {description && <div className="mt-1 text-sm text-slate-500">{description}</div>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function Pagination({ page, pageSize, total, onPage }: { page: number; pageSize: number; total: number; onPage: (p: number) => void }) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  if (total <= pageSize) return total ? <div className="px-4 py-3 text-xs text-slate-500">{total} record{total === 1 ? "" : "s"}</div> : null;
  const from = (page - 1) * pageSize + 1;
  const to = Math.min(total, page * pageSize);
  return (
    <div className="flex items-center justify-between border-t border-slate-200 px-4 py-3 text-sm">
      <span className="text-xs text-slate-500">{from}–{to} of {total}</span>
      <div className="flex items-center gap-1">
        <button className="btn-secondary btn-sm" disabled={page <= 1} onClick={() => onPage(page - 1)}>Previous</button>
        <span className="px-2 text-xs text-slate-600">Page {page} / {pages}</span>
        <button className="btn-secondary btn-sm" disabled={page >= pages} onClick={() => onPage(page + 1)}>Next</button>
      </div>
    </div>
  );
}

export function Modal({ open, title, onClose, children, footer, wide }: { open: boolean; title: string; onClose: () => void; children: ReactNode; footer?: ReactNode; wide?: boolean }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    ref.current?.querySelector<HTMLElement>("input,select,textarea,button")?.focus();
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-slate-900/40 p-0 sm:items-center sm:p-4" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div ref={ref} role="dialog" aria-modal="true" aria-label={title} className={cx("max-h-[92vh] w-full overflow-y-auto rounded-t-2xl bg-white shadow-xl sm:rounded-2xl", wide ? "sm:max-w-2xl" : "sm:max-w-md")}>
        <div className="flex items-center justify-between border-b border-slate-200 px-5 py-4">
          <h2 className="text-base font-semibold">{title}</h2>
          <button className="btn-ghost btn-sm" onClick={onClose} aria-label="Close">✕</button>
        </div>
        <div className="px-5 py-4">{children}</div>
        {footer && <div className="flex justify-end gap-2 border-t border-slate-200 bg-slate-50 px-5 py-3">{footer}</div>}
      </div>
    </div>
  );
}

export function StatCard({ label, value, hint, tone, onClick, active }: { label: string; value: ReactNode; hint?: string; tone?: "red" | "amber" | "green"; onClick?: () => void; active?: boolean }) {
  const toneCls = tone === "red" ? "text-red-600" : tone === "amber" ? "text-amber-600" : tone === "green" ? "text-emerald-600" : "text-slate-900";
  const body = (
    <>
      <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</p>
      <p className={cx("mt-2 text-2xl font-semibold tabular-nums", toneCls)}>{value}</p>
      {hint && <p className="mt-1 text-xs text-slate-500">{hint}</p>}
    </>
  );
  if (!onClick) return <div className="card p-4">{body}</div>;
  return (
    <button type="button" onClick={onClick} aria-pressed={active} title={active ? "Click to clear this filter" : "Click to filter the table"}
      className={cx("card w-full p-4 text-left transition hover:border-brand-500/50 hover:shadow-md focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500",
        active && "border-brand-500 bg-brand-50 ring-2 ring-brand-500/30")}>
      {body}
    </button>
  );
}
