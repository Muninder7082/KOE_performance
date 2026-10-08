import { Link } from "react-router-dom";
import { del, patch } from "../api";
import { useAuth } from "../auth";
import { fmtDateTime } from "../format";
import type { Strategy, Website } from "../types";
import { useConfirm, useToast } from "./feedback";
import { PsiScore, Spinner, StatusBadge } from "./ui";

export default function WebsiteTable({ websites, onChanged, onEdit, onTest, startingId }: {
  websites: Website[];
  onChanged: () => void;
  onEdit: (w: Website) => void;
  onTest: (w: Website, strategies: Strategy[]) => void;
  startingId: number | null;
}) {
  const { isAdmin } = useAuth();
  const confirm = useConfirm();
  const toast = useToast();

  const toggle = async (w: Website) => {
    try {
      await patch(`/api/websites/${w.id}`, { is_active: !w.is_active });
      toast.success(w.is_active ? `Monitoring disabled for ${w.name}` : `Monitoring enabled for ${w.name}`);
      onChanged();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Update failed");
    }
  };

  const remove = async (w: Website) => {
    const ok = await confirm({
      title: "Delete website?",
      message: <>Stop monitoring <strong>{w.name}</strong>? Its historical results stay in the database and in the Excel workbook.</>,
      confirmLabel: "Delete", danger: true,
    });
    if (!ok) return;
    try {
      await del(`/api/websites/${w.id}`);
      toast.success("Website deleted");
      onChanged();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Delete failed");
    }
  };

  return (
    <div className="overflow-x-auto">
      <table className="min-w-full divide-y divide-slate-200">
        <thead className="bg-slate-50">
          <tr>
            <th className="table-th">Website</th>
            <th className="table-th">Desktop</th>
            <th className="table-th">Mobile</th>
            <th className="table-th">Monitoring</th>
            <th className="table-th">Last checked</th>
            <th className="table-th">Status</th>
            <th className="table-th text-right">Actions</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100 bg-white">
          {websites.map((w) => {
            const d = w.latest.desktop, m = w.latest.mobile;
            const busy = w.test_running || startingId === w.id;
            return (
              <tr key={w.id} className="hover:bg-slate-50/60">
                <td className="table-td max-w-[18rem]">
                  <Link to={`/websites/${w.id}`} className="font-medium text-slate-900 hover:text-brand-600">{w.name}</Link>
                  <a href={w.url} target="_blank" rel="noreferrer noopener" className="block truncate text-xs text-slate-500 hover:underline" title={w.url}>{w.url}</a>
                </td>
                <td className="table-td"><PsiScore url={w.url} strategy="desktop" resultId={d?.id} hasReport={d?.has_report} score={d?.performance_score} threshold={w.threshold} failed={d?.status === "failed"} /></td>
                <td className="table-td"><PsiScore url={w.url} strategy="mobile" resultId={m?.id} hasReport={m?.has_report} score={m?.performance_score} threshold={w.threshold} failed={m?.status === "failed"} /></td>
                <td className="table-td text-xs text-slate-500">
                  {w.is_active ? <span className="text-emerald-700">On</span> : <span className="text-slate-400">Disabled</span>}
                </td>
                <td className="table-td text-xs">{fmtDateTime(w.last_checked_at)}</td>
                <td className="table-td"><StatusBadge status={w.status} /></td>
                <td className="table-td text-right">
                  <div className="flex justify-end gap-1">
                    <Link to={`/websites/${w.id}`} className="btn-ghost btn-sm">View</Link>
                    {isAdmin && (
                      <>
                        <button className="btn-secondary btn-sm" disabled={busy} onClick={() => onTest(w, ["desktop", "mobile"])} title="Run Desktop + Mobile test">
                          {busy ? <Spinner className="h-3 w-3" /> : null} {busy ? "Testing" : "Test"}
                        </button>
                        <button className="btn-ghost btn-sm" onClick={() => onEdit(w)}>Edit</button>
                        <button className="btn-ghost btn-sm" onClick={() => toggle(w)}>{w.is_active ? "Disable" : "Enable"}</button>
                        <button className="btn-ghost btn-sm text-red-600 hover:bg-red-50" onClick={() => remove(w)}>Delete</button>
                      </>
                    )}
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
