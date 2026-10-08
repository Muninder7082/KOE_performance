import { FormEvent, useState } from "react";
import { del, get, patch, post } from "../api";
import { useAuth } from "../auth";
import { useConfirm, useToast } from "../components/feedback";
import { ErrorState, LoadingBlock, Modal, PageHeader, Pill } from "../components/ui";
import { fmtDateTime } from "../format";
import { useAsync } from "../hooks";
import type { User } from "../types";

export default function UsersPage() {
  const { user: me } = useAuth();
  const toast = useToast();
  const confirm = useConfirm();
  const { data, error, loading, reload } = useAsync(() => get<{ items: User[] }>("/api/users"), []);
  const [adding, setAdding] = useState(false);
  const [form, setForm] = useState({ email: "", password: "", role: "viewer" as "admin" | "viewer" });

  const create = async (e: FormEvent) => {
    e.preventDefault();
    try {
      await post("/api/users", form);
      toast.success("User created");
      setAdding(false);
      setForm({ email: "", password: "", role: "viewer" });
      reload(true);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Create failed");
    }
  };

  const update = async (u: User, body: Partial<User>) => {
    try {
      await patch(`/api/users/${u.id}`, body);
      toast.success("User updated");
      reload(true);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Update failed");
    }
  };

  const remove = async (u: User) => {
    if (!(await confirm({ title: "Delete user?", message: <>Remove <strong>{u.email}</strong>?</>, confirmLabel: "Delete", danger: true }))) return;
    try {
      await del(`/api/users/${u.id}`);
      toast.success("User deleted");
      reload(true);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Delete failed");
    }
  };

  return (
    <>
      <PageHeader title="Users" description="Admins manage websites and settings; viewers have read-only access."
        actions={<button className="btn-primary" onClick={() => setAdding(true)}>Add user</button>} />
      <div className="card overflow-hidden">
        {loading && !data ? <LoadingBlock /> : error ? <ErrorState message={error} onRetry={() => reload()} /> : (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-slate-200">
              <thead className="bg-slate-50"><tr>
                <th className="table-th">E-mail</th><th className="table-th">Role</th><th className="table-th">Status</th>
                <th className="table-th">Last login</th><th className="table-th text-right">Actions</th></tr></thead>
              <tbody className="divide-y divide-slate-100 bg-white">
                {data?.items.map((u) => (
                  <tr key={u.id}>
                    <td className="table-td font-medium">{u.email}{u.id === me?.id && <span className="ml-2 text-xs text-slate-400">(you)</span>}</td>
                    <td className="table-td capitalize">{u.role}</td>
                    <td className="table-td">{u.is_active ? <Pill tone="green">Active</Pill> : <Pill>Disabled</Pill>}</td>
                    <td className="table-td text-xs">{fmtDateTime(u.last_login_at)}</td>
                    <td className="table-td text-right">
                      {u.id !== me?.id && (
                        <div className="flex justify-end gap-1">
                          <button className="btn-ghost btn-sm" onClick={() => update(u, { role: u.role === "admin" ? "viewer" : "admin" })}>Make {u.role === "admin" ? "viewer" : "admin"}</button>
                          <button className="btn-ghost btn-sm" onClick={() => update(u, { is_active: !u.is_active })}>{u.is_active ? "Disable" : "Enable"}</button>
                          <button className="btn-ghost btn-sm text-red-600 hover:bg-red-50" onClick={() => remove(u)}>Delete</button>
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
      <Modal open={adding} title="Add user" onClose={() => setAdding(false)}
        footer={<><button className="btn-secondary" onClick={() => setAdding(false)}>Cancel</button><button className="btn-primary" form="user-form">Create</button></>}>
        <form id="user-form" onSubmit={create} className="space-y-3">
          <div><label className="label" htmlFor="u-email">E-mail</label>
            <input id="u-email" className="input" type="email" required value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></div>
          <div><label className="label" htmlFor="u-pw">Temporary password</label>
            <input id="u-pw" className="input" type="password" minLength={10} maxLength={72} required value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
            <p className="hint">At least 10 characters.</p></div>
          <div><label className="label" htmlFor="u-role">Role</label>
            <select id="u-role" className="input" value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value as "admin" | "viewer" })}>
              <option value="viewer">Viewer (read-only)</option><option value="admin">Administrator</option>
            </select></div>
        </form>
      </Modal>
    </>
  );
}
