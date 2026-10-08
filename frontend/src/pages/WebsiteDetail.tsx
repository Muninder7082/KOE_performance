import { useCallback, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { get } from "../api";
import { useAuth } from "../auth";
import { useTestRunner } from "../components/TestRunner";
import WebsiteForm from "../components/WebsiteForm";
import { cx, EmptyState, ErrorState, LoadingBlock, PageHeader, Pagination, Pill, PsiScore, Score, Spinner, StatusBadge } from "../components/ui";
import { fmtDateTime, fmtDuration, fmtNum, fmtShort, psiLink, todayISO } from "../format";
import { useAsync } from "../hooks";
import type { Alert, PageOf, Result, Website } from "../types";

const METRICS: { key: keyof Result; label: string; unit: string; digits: number; good?: number }[] = [
  { key: "performance_score", label: "Performance", unit: "", digits: 0 },
  { key: "lcp_s", label: "LCP", unit: " s", digits: 2, good: 2.5 },
  { key: "cls", label: "CLS", unit: "", digits: 3, good: 0.1 },
  { key: "tbt_ms", label: "TBT", unit: " ms", digits: 0, good: 200 },
  { key: "fcp_s", label: "FCP", unit: " s", digits: 2, good: 1.8 },
  { key: "speed_index_s", label: "Speed Index", unit: " s", digits: 2, good: 3.4 },
];

function Vitals({ title, r, threshold }: { title: string; r: Result | null; threshold: number }) {
  return (
    <div className="card p-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-slate-700">{title}</h3>
        {r && <StatusBadge status={r.health} />}
      </div>
      {!r ? <p className="mt-6 text-sm text-slate-500">Not tested yet.</p> : r.status === "failed" ? (
        <div className="mt-3 rounded-md bg-red-50 p-3 text-sm text-red-800">
          <p className="font-medium">{r.error_code}</p>
          <p className="mt-1 break-words text-xs">{r.error_message}</p>
          <p className="mt-2 text-xs text-red-700">{fmtDateTime(r.tested_at)}</p>
        </div>
      ) : (
        <>
          <div className="mt-2 flex items-end gap-2">
            <Score score={r.performance_score} threshold={threshold} size="lg" />
            <span className="mb-1 text-xs text-slate-500">/ 100 · threshold {threshold}</span>
          </div>
          <dl className="mt-4 grid grid-cols-3 gap-3 text-sm">
            {METRICS.slice(1).map((m) => (
              <div key={m.key}>
                <dt className="text-xs text-slate-500">{m.label}</dt>
                <dd className={cx("font-semibold tabular-nums", m.good !== undefined && (r[m.key] as number | null) != null && (r[m.key] as number) > m.good ? "text-amber-600" : "text-slate-800")}>
                  {fmtNum(r[m.key] as number | null, m.digits, m.unit)}
                </dd>
              </div>
            ))}
            <div><dt className="text-xs text-slate-500">Accessibility</dt><dd className="font-semibold">{r.accessibility_score ?? "—"}</dd></div>
            <div><dt className="text-xs text-slate-500">Best practices</dt><dd className="font-semibold">{r.best_practices_score ?? "—"}</dd></div>
            <div><dt className="text-xs text-slate-500">SEO</dt><dd className="font-semibold">{r.seo_score ?? "—"}</dd></div>
          </dl>
          <div className="mt-4 flex items-center justify-between text-xs text-slate-500">
            <span>{fmtDateTime(r.tested_at)}</span>
            <span className="flex gap-3">
              {r.has_report && <a className="font-medium text-brand-600 hover:underline" href={`/api/results/${r.id}/report`} target="_blank" rel="noreferrer noopener" title="Saved report with Mobile / Desktop tabs">View full report ↗</a>}
              {r.has_report && <a className="text-slate-500 hover:underline" href={`/api/results/${r.id}/viewer`} target="_blank" rel="noreferrer noopener" title="Same saved report on Google Lighthouse Viewer">Google Viewer ↗</a>}
              <a className="text-slate-500 hover:underline" href={psiLink(r.requested_url, r.strategy)} target="_blank" rel="noreferrer noopener" title="Runs a new analysis on pagespeed.web.dev">Fresh run ↗</a>
            </span>
          </div>
        </>
      )}
    </div>
  );
}

function HistoryChart({ title, data, metric, threshold }: { title: string; data: Result[]; metric: (typeof METRICS)[number]; threshold: number }) {
  const points = data.filter((r) => r.status === "success" && r[metric.key] != null)
    .map((r) => ({ t: new Date(r.tested_at).getTime(), v: r[metric.key] as number }));
  return (
    <div className="card p-4">
      <h3 className="mb-3 text-sm font-semibold text-slate-700">{title} · {metric.label}</h3>
      {points.length === 0 ? <p className="py-16 text-center text-sm text-slate-500">No successful tests in this range.</p> : (
        <div className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={points} margin={{ top: 5, right: 12, left: -12, bottom: 0 }}>
              <CartesianGrid stroke="#e2e8f0" strokeDasharray="3 3" />
              <XAxis dataKey="t" type="number" domain={["dataMin", "dataMax"]} scale="time" tick={{ fontSize: 11, fill: "#64748b" }}
                tickFormatter={(t) => fmtShort(new Date(t).toISOString()).slice(0, 6)} />
              <YAxis tick={{ fontSize: 11, fill: "#64748b" }} domain={metric.key === "performance_score" ? [0, 100] : ["auto", "auto"]} />
              <Tooltip labelFormatter={(t) => fmtDateTime(new Date(t as number).toISOString())}
                formatter={(v: number) => [fmtNum(v, metric.digits, metric.unit), metric.label]} />
              {metric.key === "performance_score" && <ReferenceLine y={threshold} stroke="#f59e0b" strokeDasharray="4 4" />}
              {metric.good !== undefined && <ReferenceLine y={metric.good} stroke="#10b981" strokeDasharray="4 4" />}
              <Line type="monotone" dataKey="v" stroke="#1d4ed8" strokeWidth={2} dot={{ r: 2.5 }} isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}

export default function WebsiteDetailPage() {
  const { id } = useParams();
  const { isAdmin } = useAuth();
  const site = useAsync(() => get<Website>(`/api/websites/${id}`), [id]);
  const [range, setRange] = useState<"7" | "30" | "90" | "custom">("30");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState(todayISO());
  const [metricIdx, setMetricIdx] = useState(0);
  const [resultsPage, setResultsPage] = useState(1);
  const [alertsPage, setAlertsPage] = useState(1);
  const [editing, setEditing] = useState(false);

  const histQuery = range === "custom" ? (from ? { date_from: from, date_to: to || undefined } : null) : { days: Number(range) };
  const history = useAsync(
    () => (histQuery ? get<{ items: Result[] }>(`/api/websites/${id}/history`, histQuery) : Promise.resolve({ items: [] as Result[] })),
    [id, range, from, to],
  );
  const results = useAsync(() => get<PageOf<Result>>(`/api/websites/${id}/results`, { page: resultsPage, page_size: 10 }), [id, resultsPage]);
  const alerts = useAsync(() => get<PageOf<Alert>>(`/api/websites/${id}/alerts`, { page: alertsPage, page_size: 10 }), [id, alertsPage]);

  const refreshAll = useCallback(() => { site.reload(true); history.reload(true); results.reload(true); alerts.reload(true); },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [site.reload, history.reload, results.reload, alerts.reload]);
  const runner = useTestRunner(refreshAll);

  const byDevice = useMemo(() => {
    const items = history.data?.items ?? [];
    return { desktop: items.filter((r) => r.strategy === "desktop"), mobile: items.filter((r) => r.strategy === "mobile") };
  }, [history.data]);

  if (site.loading && !site.data) return <LoadingBlock />;
  if (site.error || !site.data) return <ErrorState message={site.error ?? "Website not found"} onRetry={() => site.reload()} />;
  const w = site.data;
  const busy = w.test_running || runner.running || runner.starting !== null;
  const metric = METRICS[metricIdx];

  return (
    <>
      <div className="mb-2 text-sm"><Link to="/websites" className="text-slate-500 hover:text-slate-800">← Websites</Link></div>
      <PageHeader
        title={w.name}
        description={
          <div className="flex flex-wrap items-center gap-2">
            <a href={w.url} target="_blank" rel="noreferrer noopener" className="break-all text-brand-600 hover:underline">{w.url}</a>
            <StatusBadge status={w.status} />
            {!w.is_active && <Pill tone="slate">Monitoring disabled</Pill>}
          </div>
        }
        actions={
          <>
            {isAdmin && (
              <>
                <button className="btn-secondary" disabled={busy} onClick={() => runner.start(w.id, w.name, ["desktop"])}>Run Desktop Test</button>
                <button className="btn-secondary" disabled={busy} onClick={() => runner.start(w.id, w.name, ["mobile"])}>Run Mobile Test</button>
                <button className="btn-primary" disabled={busy} onClick={() => runner.start(w.id, w.name, ["desktop", "mobile"])}>
                  {busy && <Spinner />} Run Both
                </button>
              </>
            )}
            <a className="btn-secondary" href="/api/excel/download">Download Excel</a>
            {isAdmin && <button className="btn-ghost" onClick={() => setEditing(true)}>Edit Website</button>}
          </>
        }
      />

      <div className="mb-6 grid gap-3 text-sm sm:grid-cols-3">
        <div className="card p-4"><p className="text-xs uppercase tracking-wide text-slate-500">Monitoring schedule (all pages)</p>
          <p className="mt-1 font-medium">{w.is_active ? w.schedule_description : "Disabled"}</p>
          {w.is_active && <p className="mt-0.5 text-xs text-slate-500">Next run: {fmtDateTime(w.next_run_at)}</p>}</div>
        <div className="card p-4"><p className="text-xs uppercase tracking-wide text-slate-500">Threshold</p>
          <p className="mt-1 font-medium">{w.threshold}</p></div>
        <div className="card p-4"><p className="text-xs uppercase tracking-wide text-slate-500">Last checked</p>
          <p className="mt-1 font-medium">{fmtDateTime(w.last_checked_at)}</p>
          {w.notes && <p className="mt-0.5 truncate text-xs text-slate-500" title={w.notes}>{w.notes}</p>}</div>
      </div>

      <h2 className="mb-3 text-sm font-semibold text-slate-700">Core Web Vitals (latest)</h2>
      <div className="grid gap-4 lg:grid-cols-2">
        <Vitals title="Desktop" r={w.latest.desktop} threshold={w.threshold} />
        <Vitals title="Mobile" r={w.latest.mobile} threshold={w.threshold} />
      </div>

      <div className="mb-3 mt-8 flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <h2 className="text-sm font-semibold text-slate-700">Historical performance</h2>
        <div className="flex flex-wrap items-center gap-2">
          <div className="inline-flex rounded-lg border border-slate-300 bg-white p-0.5">
            {(["7", "30", "90", "custom"] as const).map((r) => (
              <button key={r} onClick={() => setRange(r)} className={cx("rounded-md px-3 py-1 text-xs font-medium", range === r ? "bg-brand-600 text-white" : "text-slate-600 hover:bg-slate-100")}>
                {r === "custom" ? "Custom" : `Last ${r} days`}
              </button>
            ))}
          </div>
          {range === "custom" && (
            <>
              <input type="date" className="input w-auto py-1" value={from} max={to} onChange={(e) => setFrom(e.target.value)} aria-label="From date" />
              <span className="text-xs text-slate-500">to</span>
              <input type="date" className="input w-auto py-1" value={to} min={from} onChange={(e) => setTo(e.target.value)} aria-label="To date" />
            </>
          )}
          <select className="input w-auto py-1" value={metricIdx} onChange={(e) => setMetricIdx(Number(e.target.value))} aria-label="Metric">
            {METRICS.map((m, i) => <option key={m.key} value={i}>{m.label}</option>)}
          </select>
        </div>
      </div>
      {range === "custom" && !from ? <div className="card"><EmptyState title="Choose a start date" description="Pick a date range to load history." /></div>
        : history.loading && !history.data ? <LoadingBlock /> : history.error ? <ErrorState message={history.error} onRetry={() => history.reload()} /> : (
          <div className="grid gap-4 lg:grid-cols-2">
            <HistoryChart title="Desktop" data={byDevice.desktop} metric={metric} threshold={w.threshold} />
            <HistoryChart title="Mobile" data={byDevice.mobile} metric={metric} threshold={w.threshold} />
          </div>
        )}

      <h2 className="mb-3 mt-8 text-sm font-semibold text-slate-700">Recent tests</h2>
      <div className="card overflow-hidden">
        {results.data && results.data.items.length === 0 ? <EmptyState title="No tests yet" description="Run a manual test or wait for the schedule." /> : (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-slate-200">
              <thead className="bg-slate-50"><tr>
                <th className="table-th">Tested</th><th className="table-th">Device</th><th className="table-th">Score</th>
                <th className="table-th">LCP</th><th className="table-th">CLS</th><th className="table-th">TBT</th><th className="table-th">FCP</th>
                <th className="table-th">SI</th><th className="table-th">Trigger</th><th className="table-th">Status</th></tr></thead>
              <tbody className="divide-y divide-slate-100">
                {results.data?.items.map((r) => (
                  <tr key={r.id}>
                    <td className="table-td text-xs">{fmtDateTime(r.tested_at)}</td>
                    <td className="table-td capitalize">{r.strategy}</td>
                    <td className="table-td"><PsiScore url={r.requested_url} strategy={r.strategy} resultId={r.id} hasReport={r.has_report} score={r.performance_score} threshold={r.threshold} failed={r.status === "failed"} /></td>
                    <td className="table-td">{fmtNum(r.lcp_s, 2, " s")}</td>
                    <td className="table-td">{fmtNum(r.cls, 3)}</td>
                    <td className="table-td">{fmtNum(r.tbt_ms, 0, " ms")}</td>
                    <td className="table-td">{fmtNum(r.fcp_s, 2, " s")}</td>
                    <td className="table-td">{fmtNum(r.speed_index_s, 2, " s")}</td>
                    <td className="table-td text-xs"><span className="capitalize">{r.trigger}</span> · {fmtDuration(r.duration_ms)}</td>
                    <td className="table-td"><StatusBadge status={r.health} />{r.error_code && <span className="ml-2 text-xs text-red-600" title={r.error_message ?? ""}>{r.error_code}</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {results.data && <Pagination page={results.data.page} pageSize={results.data.page_size} total={results.data.total} onPage={setResultsPage} />}
      </div>

      <h2 className="mb-3 mt-8 text-sm font-semibold text-slate-700">Alert history</h2>
      <div className="card overflow-hidden">
        {alerts.data && alerts.data.items.length === 0 ? <EmptyState title="No alerts" description={`An alert is raised when a score drops below ${w.threshold}.`} /> : (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-slate-200">
              <thead className="bg-slate-50"><tr>
                <th className="table-th">Device</th><th className="table-th">State</th><th className="table-th">Score</th><th className="table-th">First detected</th>
                <th className="table-th">Last detected</th><th className="table-th">E-mails</th><th className="table-th">Recovered</th></tr></thead>
              <tbody className="divide-y divide-slate-100">
                {alerts.data?.items.map((a) => (
                  <tr key={a.id}>
                    <td className="table-td capitalize">{a.strategy}</td>
                    <td className="table-td">{a.state === "open" ? <Pill tone="amber">Open</Pill> : <Pill tone="green">Recovered</Pill>}</td>
                    <td className="table-td">{a.score ?? "—"} / {a.threshold}</td>
                    <td className="table-td text-xs">{fmtDateTime(a.first_detected_at)}</td>
                    <td className="table-td text-xs">{fmtDateTime(a.last_detected_at)}</td>
                    <td className="table-td">{a.notify_count}</td>
                    <td className="table-td text-xs">{a.recovered_at ? `${fmtDateTime(a.recovered_at)} (${a.recovered_score})` : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {alerts.data && <Pagination page={alerts.data.page} pageSize={alerts.data.page_size} total={alerts.data.total} onPage={setAlertsPage} />}
      </div>

      <WebsiteForm open={editing} website={w} onClose={() => setEditing(false)} onSaved={() => site.reload(true)} />
      {runner.modal}
    </>
  );
}
