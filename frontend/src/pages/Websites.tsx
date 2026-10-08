import { useCallback, useState } from "react";
import { get } from "../api";
import { useAuth } from "../auth";
import { useTestRunner } from "../components/TestRunner";
import WebsiteForm from "../components/WebsiteForm";
import WebsiteTable from "../components/WebsiteTable";
import { EmptyState, ErrorState, LoadingBlock, PageHeader, Pagination } from "../components/ui";
import { useAsync, useDebounced } from "../hooks";
import type { PageOf, Website } from "../types";

export default function WebsitesPage() {
  const { isAdmin } = useAuth();
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [active, setActive] = useState("");
  const [page, setPage] = useState(1);
  const q = useDebounced(search);
  const { data, error, loading, reload } = useAsync(
    () => get<PageOf<Website>>("/api/websites", { search: q, status, active, page, page_size: 25 }),
    [q, status, active, page],
  );
  const [editing, setEditing] = useState<Website | null>(null);
  const [adding, setAdding] = useState(false);
  const refresh = useCallback(() => reload(true), [reload]);
  const runner = useTestRunner(refresh);

  return (
    <>
      <PageHeader title="Websites" description="Manage monitored URLs, schedules and thresholds."
        actions={isAdmin && <button className="btn-primary" onClick={() => setAdding(true)}>Add page</button>} />
      <div className="card overflow-hidden">
        <div className="flex flex-col gap-2 border-b border-slate-200 p-3 sm:flex-row">
          <input className="input sm:max-w-xs" placeholder="Search name or URL" value={search} onChange={(e) => { setSearch(e.target.value); setPage(1); }} />
          <select className="input sm:w-40" value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }}>
            <option value="">All statuses</option>
            <option value="GOOD">Good</option>
            <option value="ATTENTION">Attention</option>
            <option value="FAILED">Failed</option>
            <option value="PENDING">Not tested</option>
          </select>
          <select className="input sm:w-40" value={active} onChange={(e) => { setActive(e.target.value); setPage(1); }}>
            <option value="">Active & inactive</option>
            <option value="true">Active only</option>
            <option value="false">Inactive only</option>
          </select>
        </div>
        {loading && !data ? <LoadingBlock /> : error ? <ErrorState message={error} onRetry={() => reload()} /> : data && data.items.length === 0 ? (
          <EmptyState title={q || status || active ? "No matching websites" : "No websites yet"}
            description={q || status || active ? "Try a different search or filter." : "Add your first URL to start monitoring."}
            action={isAdmin && !q && !status && !active && <button className="btn-primary" onClick={() => setAdding(true)}>Add page</button>} />
        ) : data && (
          <>
            <WebsiteTable websites={data.items} onChanged={refresh} onEdit={setEditing}
              onTest={(w, s) => runner.start(w.id, w.name, s)} startingId={runner.starting} />
            <Pagination page={data.page} pageSize={data.page_size} total={data.total} onPage={setPage} />
          </>
        )}
      </div>
      <WebsiteForm open={adding || !!editing} website={editing} onClose={() => { setAdding(false); setEditing(null); }} onSaved={refresh} />
      {runner.modal}
    </>
  );
}
