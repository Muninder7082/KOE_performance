import { FormEvent, useEffect, useState } from "react";
import { get, patch, post } from "../api";
import type { SettingsResponse, Website } from "../types";
import { useToast } from "./feedback";
import { Modal, Spinner } from "./ui";

type FormState = {
  name: string;
  url: string;
  is_active: boolean;
  threshold: number;
  notes: string;
};

function validUrl(u: string) {
  try {
    const p = new URL(u.trim());
    return (p.protocol === "http:" || p.protocol === "https:") && p.hostname.includes(".");
  } catch {
    return false;
  }
}

export default function WebsiteForm({ open, website, onClose, onSaved }: { open: boolean; website?: Website | null; onClose: () => void; onSaved: (w: Website) => void }) {
  const toast = useToast();
  const [form, setForm] = useState<FormState | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open) return;
    setErrors({});
    if (website) {
      setForm({ name: website.name, url: website.url, is_active: website.is_active, threshold: website.threshold, notes: website.notes ?? "" });
      return;
    }
    setForm(null);
    get<SettingsResponse>("/api/settings")
      .then((s) => setForm({ name: "", url: "", is_active: true, threshold: s.settings.default_threshold, notes: "" }))
      .catch(() => setForm({ name: "", url: "", is_active: true, threshold: 90, notes: "" }));
  }, [open, website]);

  const set = <K extends keyof FormState>(k: K, v: FormState[K]) => setForm((f) => (f ? { ...f, [k]: v } : f));

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!form) return;
    const errs: Record<string, string> = {};
    if (!form.name.trim()) errs.name = "Website name is required";
    if (!validUrl(form.url)) errs.url = "Enter a full public URL, e.g. https://www.example.com/";
    if (!(form.threshold >= 1 && form.threshold <= 100)) errs.threshold = "Threshold must be between 1 and 100";
    setErrors(errs);
    if (Object.keys(errs).length) return;
    setBusy(true);
    const body = { ...form, name: form.name.trim(), url: form.url.trim(), notes: form.notes.trim() || null };
    try {
      const saved = website ? await patch<Website>(`/api/websites/${website.id}`, body) : await post<Website>("/api/websites", body);
      toast.success(website ? "Page updated" : "Page added");
      onSaved(saved);
      onClose();
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Save failed";
      if (/url/i.test(msg)) setErrors({ url: msg });
      else toast.error(msg);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      open={open}
      wide
      title={website ? "Edit page" : "Add page"}
      onClose={onClose}
      footer={
        <>
          <button type="button" className="btn-secondary" onClick={onClose}>Cancel</button>
          <button type="submit" form="website-form" className="btn-primary" disabled={busy || !form}>
            {busy && <Spinner />} {website ? "Save changes" : "Add page"}
          </button>
        </>
      }
    >
      {!form ? (
        <div className="flex justify-center py-10"><Spinner className="h-5 w-5" /></div>
      ) : (
        <form id="website-form" onSubmit={submit} className="grid grid-cols-1 gap-4 sm:grid-cols-2" noValidate>
          <div className="sm:col-span-1">
            <label className="label" htmlFor="wf-name">Page name</label>
            <input id="wf-name" className="input" maxLength={200} value={form.name} onChange={(e) => set("name", e.target.value)} placeholder="Homepage" />
            {errors.name && <p className="mt-1 text-xs text-red-600">{errors.name}</p>}
          </div>
          <div className="sm:col-span-1">
            <label className="label" htmlFor="wf-url">URL</label>
            <input id="wf-url" className="input" type="url" maxLength={2048} value={form.url} onChange={(e) => set("url", e.target.value)} placeholder="https://www.example.com/" />
            {errors.url && <p className="mt-1 text-xs text-red-600">{errors.url}</p>}
          </div>
          <div>
            <label className="label" htmlFor="wf-th">Performance threshold</label>
            <input id="wf-th" className="input" type="number" min={1} max={100} value={form.threshold} onChange={(e) => set("threshold", Number(e.target.value))} />
            {errors.threshold ? <p className="mt-1 text-xs text-red-600">{errors.threshold}</p> : <p className="hint">Alert when Desktop or Mobile score is below this.</p>}
          </div>
          <div className="flex items-center gap-2 sm:col-span-2">
            <input id="wf-active" type="checkbox" className="h-4 w-4 rounded border-slate-300" checked={form.is_active} onChange={(e) => set("is_active", e.target.checked)} />
            <label htmlFor="wf-active" className="text-sm text-slate-700">Monitoring enabled</label>
          </div>
          <p className="text-xs text-slate-500 sm:col-span-2">Every page is tested at the common time set in <strong>Settings → Schedule</strong>.</p>
          <div className="sm:col-span-2">
            <label className="label" htmlFor="wf-notes">Notes</label>
            <textarea id="wf-notes" className="input" rows={3} maxLength={2000} value={form.notes} onChange={(e) => set("notes", e.target.value)} />
          </div>
        </form>
      )}
    </Modal>
  );
}
