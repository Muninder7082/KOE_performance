import { useState } from "react";
import { Link } from "react-router-dom";
import { get } from "../api";
import { EmptyState, ErrorState, LoadingBlock, PageHeader, Pagination, Pill } from "../components/ui";
import { fmtDateTime, psiLink } from "../format";
import { useAsync } from "../hooks";
import type { Alert, PageOf } from "../types";

export default function AlertsPage() {
  const [state, setState] = useState("");
  const [page, setPage] = useState(1);
  const { data, error, loading, reload } = useAsync(() => get<PageOf<Alert>>("/api/alerts", { state, page, page_size: 25 }), [state, page]);

  return (
    <>
      <PageHeader title="Alerts" description="Performance threshold breaches. Default mode: one e-mail per issue until it recovers." />
      <div className="card overflow-hidden">
        <div className="border-b border-slate-200 p-3">
          <select className="input sm:w-48" value={state} onChange={(e) => { setState(e.target.value); setPage(1); }} aria-label="State">
            <option value="">All alerts</option><option value="open">Open</option><option value="recovered">Recovered</option><option value="closed">Closed (website deleted)</option>
          </select>
        </div>
        {loading && !data ? <LoadingBlock /> : error ? <ErrorState message={error} onRetry={() => reload()} /> : data && data.items.length === 0 ? (
          <EmptyState title="No alerts" description="Every monitored page is at or above its threshold." />
        ) : data && (
          <>
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-slate-200">
                <thead className="bg-slate-50"><tr>
                  <th className="table-th">Website</th><th className="table-th">Device</th><th className="table-th">State</th>
                  <th className="table-th">Score</th><th className="table-th">First detected</th><th className="table-th">Last detected</th>
                  <th className="table-th">Last e-mailed</th><th className="table-th">Recovered</th><th className="table-th"></th></tr></thead>
                <tbody className="divide-y divide-slate-100 bg-white">
                  {data.items.map((a) => (
                    <tr key={a.id}>
                      <td className="table-td max-w-[16rem]">
                        {a.website_id ? <Link className="font-medium hover:text-brand-600" to={`/websites/${a.website_id}`}>{a.website_name}</Link> : a.website_name}
                        <span className="block truncate text-xs text-slate-500">{a.url}</span>
                      </td>
                      <td className="table-td capitalize">{a.strategy}</td>
                      <td className="table-td">{a.state === "open" ? <Pill tone="amber">Open</Pill> : a.state === "closed" ? <Pill>Closed</Pill> : <Pill tone="green">Recovered</Pill>}</td>
                      <td className="table-td">{a.score ?? "—"} <span className="text-xs text-slate-400">/ {a.threshold}</span></td>
                      <td className="table-td text-xs">{fmtDateTime(a.first_detected_at)}</td>
                      <td className="table-td text-xs">{fmtDateTime(a.last_detected_at)}</td>
                      <td className="table-td text-xs">{a.last_notified_at ? `${fmtDateTime(a.last_notified_at)} (${a.notify_count})` : <span className="text-red-600">Not sent</span>}</td>
                      <td className="table-td text-xs">{a.recovered_at ? `${fmtDateTime(a.recovered_at)} · ${a.recovered_score}` : "—"}</td>
                      <td className="table-td"><a className="text-xs text-brand-600 hover:underline" href={psiLink(a.url, a.strategy)} target="_blank" rel="noreferrer noopener">PSI ↗</a></td>
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
