import { useState } from "react";
import { get } from "../api";
import { EmptyState, ErrorState, LoadingBlock, PageHeader, Pagination, Pill } from "../components/ui";
import { fmtDate, fmtDateTime } from "../format";
import { useAsync, useDebounced } from "../hooks";
import type { EmailLog, PageOf } from "../types";

const TYPES: Record<string, string> = {
  daily_report: "Daily Report",
  performance_alert: "Performance Alert",
  recovery_notification: "Recovery Notification",
  test_email: "Test Email",
};

export default function EmailLogsPage() {
  const [type, setType] = useState("");
  const [status, setStatus] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const q = useDebounced(search);
  const { data, error, loading, reload } = useAsync(
    () => get<PageOf<EmailLog>>("/api/email-logs", { email_type: type, status, date_from: from, date_to: to, search: q, page, page_size: 25 }),
    [type, status, from, to, q, page],
  );
  const reset = (fn: () => void) => { fn(); setPage(1); };

  return (
    <>
      <PageHeader title="Email Logs" description="Every report, alert, recovery and test e-mail with its delivery result." />
      <div className="card overflow-hidden">
        <div className="grid grid-cols-2 gap-2 border-b border-slate-200 p-3 md:grid-cols-5">
          <input className="input col-span-2 md:col-span-1" placeholder="Search recipient / subject" value={search} onChange={(e) => reset(() => setSearch(e.target.value))} />
          <select className="input" value={type} onChange={(e) => reset(() => setType(e.target.value))} aria-label="Type">
            <option value="">All types</option>
            {Object.entries(TYPES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
          <select className="input" value={status} onChange={(e) => reset(() => setStatus(e.target.value))} aria-label="Status">
            <option value="">All statuses</option><option value="sent">Sent</option><option value="failed">Failed</option><option value="pending">Pending</option>
          </select>
          <input type="date" className="input" value={from} onChange={(e) => reset(() => setFrom(e.target.value))} aria-label="From date" />
          <input type="date" className="input" value={to} min={from} onChange={(e) => reset(() => setTo(e.target.value))} aria-label="To date" />
        </div>
        {loading && !data ? <LoadingBlock /> : error ? <ErrorState message={error} onRetry={() => reload()} /> : data && data.items.length === 0 ? (
          <EmptyState title="No e-mails yet" description="Reports and alerts will appear here once sent." />
        ) : data && (
          <>
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-slate-200">
                <thead className="bg-slate-50"><tr>
                  <th className="table-th">Date</th><th className="table-th">Email type</th><th className="table-th">Recipient</th>
                  <th className="table-th">Website</th><th className="table-th">Status</th><th className="table-th">Error</th><th className="table-th">Sent at</th></tr></thead>
                <tbody className="divide-y divide-slate-100 bg-white">
                  {data.items.map((m) => (
                    <tr key={m.id}>
                      <td className="table-td text-xs">{fmtDate(m.created_at)}</td>
                      <td className="table-td">{TYPES[m.email_type] ?? m.email_type}{m.has_attachment && <span className="ml-1 text-xs text-slate-400" title="Excel attached">📎</span>}
                        <span className="block max-w-[18rem] truncate text-xs text-slate-500" title={m.subject}>{m.subject}</span></td>
                      <td className="table-td max-w-[14rem] truncate text-xs" title={m.recipients}>{m.recipients || "—"}</td>
                      <td className="table-td text-xs">{m.website_name ?? "—"}</td>
                      <td className="table-td">{m.status === "sent" ? <Pill tone="green">Sent</Pill> : m.status === "failed" ? <Pill tone="red">Failed</Pill> : <Pill>Pending</Pill>}</td>
                      <td className="table-td max-w-[22rem] whitespace-normal text-xs text-red-700">{m.error}</td>
                      <td className="table-td text-xs">{fmtDateTime(m.sent_at)}</td>
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
