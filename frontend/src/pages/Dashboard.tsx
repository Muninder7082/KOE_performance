import { useCallback, useState } from "react";
import { Link } from "react-router-dom";
import { get } from "../api";
import { useAuth } from "../auth";
import { useTestRunner } from "../components/TestRunner";
import WebsiteForm from "../components/WebsiteForm";
import WebsiteTable from "../components/WebsiteTable";
import { EmptyState, ErrorState, LoadingBlock, PageHeader, Pill, StatCard } from "../components/ui";
import { dayISO, fmtDateTime, getAppTimezone, todayISO } from "../format";
import { useAsync } from "../hooks";
import type { Dashboard, Website } from "../types";

type CardFilter = "all" | "active" | "today" | "attention" | "failed";
const FILTER_LABELS: Record<CardFilter, string> = {
  all: "All", active: "Active monitors", today: "Tested today", attention: "Needs attention", failed: "Failed",
};

export default function DashboardPage() {
  const { isAdmin } = useAuth();
  const { data, error, loading, reload } = useAsync(() => get<Dashboard>("/api/dashboard"), []);
  const [editing, setEditing] = useState<Website | null>(null);
  const [adding, setAdding] = useState(false);
  const refresh = useCallback(() => reload(true), [reload]);
  const runner = useTestRunner(refresh);

  const c = data?.cards;
  const [filter, setFilter] = useState<CardFilter>("all");
  const toggle = (f: CardFilter) => setFilter((cur) => (cur === f ? "all" : f));
  const today = todayISO();
  const shown = (data?.websites ?? []).filter((w) => {
    switch (filter) {
      case "active": return w.is_active;
      case "today": return !!w.last_checked_at && dayISO(w.last_checked_at) === today;
      case "attention": return w.status === "ATTENTION";
      case "failed": return w.status === "FAILED";
      default: return true;
    }
  });
  const avgTone = (v: number | null | undefined) => (v == null ? undefined : v >= 90 ? "green" : v >= 50 ? "amber" : "red");

  return (
    <>
      <PageHeader
        title="Dashboard"
        description={<>Latest Google PageSpeed Insights results · times in {getAppTimezone()}{data?.schedule && <> · Next run of all pages: <strong>{fmtDateTime(data.schedule.next_run_at)}</strong></>}{data?.scheduler_running && <span className="ml-2"><Pill tone="blue">Scheduled run in progress</Pill></span>}</>}
        actions={
          <>
            <a className="btn-secondary" href="/api/excel/download">Download Excel</a>
            {isAdmin && <button className="btn-primary" onClick={() => setAdding(true)}>Add page</button>}
          </>
        }
      />
      {loading && !data ? <LoadingBlock /> : error && !data ? <ErrorState message={error} onRetry={() => reload()} /> : c && (
        <>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-7">
            <StatCard label="Total pages" value={c.total_websites} onClick={() => setFilter("all")} hint={filter === "all" ? undefined : "Show all"} />
            <StatCard label="Active pages" value={c.active_monitors} onClick={() => toggle("active")} active={filter === "active"} />
            <StatCard label="Today's tests" value={c.tests_today} onClick={() => toggle("today")} active={filter === "today"} hint="Pages tested today" />
            <StatCard label="Next run" value={<span className="text-lg">{data.schedule ? fmtDateTime(data.schedule.next_run_at).slice(-5) : "—"}</span>}
              hint={data.schedule ? `${fmtDateTime(data.schedule.next_run_at).slice(0, 11)} · all pages` : undefined} />
            {c.lowest ? (
              <Link to={`/websites/${c.lowest.website_id}`} className="block rounded-xl transition hover:ring-2 hover:ring-brand-500/30">
                <StatCard label="Lowest score" value={c.lowest.score} tone={avgTone(c.lowest.score)}
                  hint={`${c.lowest.website_name} · ${c.lowest.device === "mobile" ? "Mobile" : "Desktop"}`} />
              </Link>
            ) : <StatCard label="Lowest score" value="—" hint="No tests yet" />}
            <StatCard label="Needs attention" value={c.attention} tone={c.attention ? "amber" : undefined} hint="Score below threshold"
              onClick={() => toggle("attention")} active={filter === "attention"} />
            <StatCard label="Failed tests" value={c.failed_tests_today} tone={c.failed_tests_today ? "red" : undefined} hint="Today"
              onClick={() => toggle("failed")} active={filter === "failed"} />
          </div>
          <div className="card mt-6 overflow-hidden">
            <div className="flex items-center justify-between border-b border-slate-200 px-4 py-3">
              <h2 className="flex flex-wrap items-center gap-2 text-sm font-semibold">
                Monitored websites
                {filter !== "all" && (
                  <span className="inline-flex items-center gap-1 rounded-full bg-brand-50 px-2.5 py-0.5 text-xs font-medium text-brand-700">
                    {FILTER_LABELS[filter]} · {shown.length}
                    <button className="ml-1 text-brand-700 hover:text-brand-900" onClick={() => setFilter("all")} aria-label="Clear filter">✕</button>
                  </span>
                )}
              </h2>
              <div className="flex items-center gap-1">
                {filter !== "all" && <button className="btn-ghost btn-sm" onClick={() => setFilter("all")}>Clear filter</button>}
                <button className="btn-ghost btn-sm" onClick={() => reload()}>Refresh</button>
              </div>
            </div>
            {data.websites.length === 0 ? (
              <EmptyState title="No websites yet" description="Add a URL to start monitoring Desktop and Mobile performance."
                action={isAdmin && <button className="btn-primary" onClick={() => setAdding(true)}>Add page</button>} />
            ) : (
              shown.length === 0 ? (
                <EmptyState title="No pages match this filter" action={<button className="btn-secondary" onClick={() => setFilter("all")}>Show all pages</button>} />
              ) : <WebsiteTable websites={shown} onChanged={refresh} onEdit={setEditing}
                onTest={(w, s) => runner.start(w.id, w.name, s)} startingId={runner.starting} />
            )}
          </div>
        </>
      )}
      <WebsiteForm open={adding || !!editing} website={editing} onClose={() => { setAdding(false); setEditing(null); }} onSaved={refresh} />
      {runner.modal}
    </>
  );
}
