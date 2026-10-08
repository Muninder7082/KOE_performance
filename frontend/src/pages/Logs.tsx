import { useState } from "react";
import { Link } from "react-router-dom";
import { get } from "../api";
import { EmptyState, ErrorState, LoadingBlock, PageHeader, Pagination, PsiScore, StatusBadge } from "../components/ui";
import { fmtDateTime, fmtDuration } from "../format";
import { useAsync, useDebounced } from "../hooks";
import type { PageOf, Result, Website } from "../types";

export default function LogsPage() {
  const [websiteId, setWebsiteId] = useState("");
  const [strategy, setStrategy] = useState("");
  const [status, setStatus] = useState("");
  const [trigger, setTrigger] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const q = useDebounced(search);
  const sites = useAsync(() => get<PageOf<Website>>("/api/websites", { page_size: 200 }), []);
  const { data, error, loading, reload } = useAsync(
    () => get<PageOf<Result>>("/api/results", { website_id: websiteId, strategy, status, trigger, date_from: from, date_to: to, search: q, page, page_size: 25 }),
    [websiteId, strategy, status, trigger, from, to, q, page],
  );
  const reset = (fn: () => void) => { fn(); setPage(1); };

  return (
    <>
      <PageHeader title="Monitoring Logs" description="Every PageSpeed test (manual and scheduled), including failures." />
      <div className="card overflow-hidden">
        <div className="grid grid-cols-2 gap-2 border-b border-slate-200 p-3 md:grid-cols-4 xl:grid-cols-7">
          <input className="input col-span-2 md:col-span-1" placeholder="Search" value={search} onChange={(e) => reset(() => setSearch(e.target.value))} />
          <select className="input" value={websiteId} onChange={(e) => reset(() => setWebsiteId(e.target.value))} aria-label="Website">
            <option value="">All websites</option>
            {sites.data?.items.map((w) => <option key={w.id} value={w.id}>{w.name}</option>)}
          </select>
          <select className="input" value={strategy} onChange={(e) => reset(() => setStrategy(e.target.value))} aria-label="Device">
            <option value="">All devices</option><option value="desktop">Desktop</option><option value="mobile">Mobile</option>
          </select>
          <select className="input" value={status} onChange={(e) => reset(() => setStatus(e.target.value))} aria-label="Status">
            <option value="">All statuses</option><option value="good">Good</option><option value="attention">Attention</option>
            <option value="failed">Failed</option><option value="success">Successful</option>
          </select>
          <select className="input" value={trigger} onChange={(e) => reset(() => setTrigger(e.target.value))} aria-label="Trigger">
            <option value="">Manual & scheduled</option><option value="manual">Manual</option><option value="scheduled">Scheduled</option>
          </select>
          <input type="date" className="input" value={from} onChange={(e) => reset(() => setFrom(e.target.value))} aria-label="From date" />
          <input type="date" className="input" value={to} min={from} onChange={(e) => reset(() => setTo(e.target.value))} aria-label="To date" />
        </div>
        {loading && !data ? <LoadingBlock /> : error ? <ErrorState message={error} onRetry={() => reload()} /> : data && data.items.length === 0 ? (
          <EmptyState title="No tests found" description="Adjust the filters or run a test." />
        ) : data && (
          <>
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-slate-200">
                <thead className="bg-slate-50"><tr>
                  <th className="table-th">Website</th><th className="table-th">Device</th><th className="table-th">Started</th>
                  <th className="table-th">Completed</th><th className="table-th">Duration</th><th className="table-th">Score</th>
                  <th className="table-th">Status</th><th className="table-th">Error</th></tr></thead>
                <tbody className="divide-y divide-slate-100 bg-white">
                  {data.items.map((r) => (
                    <tr key={r.id}>
                      <td className="table-td max-w-[16rem]">
                        {r.website_id ? <Link className="font-medium hover:text-brand-600" to={`/websites/${r.website_id}`}>{r.website_name}</Link> : <span className="font-medium">{r.website_name}</span>}
                        <span className="block truncate text-xs text-slate-500" title={r.requested_url}>{r.requested_url}</span>
                      </td>
                      <td className="table-td capitalize">{r.strategy}<span className="block text-xs text-slate-400">{r.trigger}</span></td>
                      <td className="table-td text-xs">{fmtDateTime(r.started_at)}</td>
                      <td className="table-td text-xs">{fmtDateTime(r.completed_at)}</td>
                      <td className="table-td text-xs">{fmtDuration(r.duration_ms)}</td>
                      <td className="table-td"><PsiScore url={r.requested_url} strategy={r.strategy} resultId={r.id} hasReport={r.has_report} score={r.performance_score} threshold={r.threshold} failed={r.status === "failed"} /></td>
                      <td className="table-td"><StatusBadge status={r.health} /></td>
                      <td className="table-td max-w-[20rem] whitespace-normal text-xs text-red-700">
                        {r.error_code && <><strong>{r.error_code}</strong> {r.error_message}</>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Pagination page={data.page} pageSize={data.page_size} total={data.total} onPage={setPage} />
          </>
        )}
      </div>
    </>
  );
}
