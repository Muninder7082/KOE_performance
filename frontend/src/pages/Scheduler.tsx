import { useState } from "react";
import { get } from "../api";
import { EmptyState, ErrorState, LoadingBlock, PageHeader, Pagination, Pill } from "../components/ui";
import { fmtDateTime, fmtDuration } from "../format";
import { useAsync } from "../hooks";
import type { PageOf, TaskRun } from "../types";

export default function SchedulerPage() {
  const [page, setPage] = useState(1);
  const { data, error, loading, reload } = useAsync(() => get<PageOf<TaskRun>>("/api/task-runs", { page, page_size: 25 }), [page]);

  return (
    <>
      <PageHeader title="Scheduler Runs"
        description="Each call to the scheduled-checks endpoint (external cron or the built-in timer) and what it did."
        actions={<button className="btn-secondary" onClick={() => reload()}>Refresh</button>} />
      <div className="card overflow-hidden">
        {loading && !data ? <LoadingBlock /> : error ? <ErrorState message={error} onRetry={() => reload()} /> : data && data.items.length === 0 ? (
          <EmptyState title="No scheduled runs yet" description="Connect an external scheduler to POST /api/internal/run-scheduled-checks (see Settings → Scheduler)." />
        ) : data && (
          <>
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-slate-200">
                <thead className="bg-slate-50"><tr>
                  <th className="table-th">Started</th><th className="table-th">Trigger</th><th className="table-th">Status</th>
                  <th className="table-th">Websites due</th><th className="table-th">Tests OK</th><th className="table-th">Tests failed</th>
                  <th className="table-th">Duration</th><th className="table-th">Message</th></tr></thead>
                <tbody className="divide-y divide-slate-100 bg-white">
                  {data.items.map((r) => (
                    <tr key={r.id}>
                      <td className="table-td text-xs">{fmtDateTime(r.started_at)}</td>
                      <td className="table-td text-xs">{r.trigger}</td>
                      <td className="table-td">{r.status === "completed" ? <Pill tone="green">Completed</Pill> : r.status === "running" ? <Pill tone="blue">Running</Pill> : <Pill tone="red">{r.status}</Pill>}</td>
                      <td className="table-td">{r.websites_due}</td>
                      <td className="table-td">{r.tests_succeeded}</td>
                      <td className="table-td">{r.tests_failed ? <span className="text-red-600">{r.tests_failed}</span> : 0}</td>
                      <td className="table-td text-xs">{r.completed_at ? fmtDuration(new Date(r.completed_at).getTime() - new Date(r.started_at).getTime()) : "—"}</td>
                      <td className="table-td max-w-[26rem] whitespace-normal text-xs text-slate-600">{r.message}</td>
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
