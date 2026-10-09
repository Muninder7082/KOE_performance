import { FormEvent, ReactNode, useEffect, useState } from "react";
import { post, put, get } from "../api";
import { setCsrfToken } from "../api";
import { useAuth } from "../auth";
import { useToast } from "../components/feedback";
import { ErrorState, LoadingBlock, PageHeader, Pill, Spinner } from "../components/ui";
import { fmtDateTime, setAppTimezone } from "../format";
import { useAsync } from "../hooks";
import { AppSettings, FREQUENCIES, SettingsResponse, WEEKDAYS } from "../types";

function Section({ title, description, children }: { title: string; description?: string; children: ReactNode }) {
  return (
    <section className="card p-5">
      <h2 className="text-sm font-semibold text-slate-900">{title}</h2>
      {description && <p className="mt-0.5 text-xs text-slate-500">{description}</p>}
      <div className="mt-4">{children}</div>
    </section>
  );
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5 border-b border-slate-100 py-2 text-sm last:border-0 sm:flex-row sm:gap-4">
      <dt className="w-44 shrink-0 text-slate-500">{label}</dt>
      <dd className="min-w-0 break-words text-slate-800">{children}</dd>
    </div>
  );
}

const splitEmails = (s: string) => s.split(/[\s,;]+/).map((x) => x.trim()).filter(Boolean);

export default function SettingsPage() {
  const { isAdmin } = useAuth();
  const toast = useToast();
  const { data, error, loading, reload } = useAsync(() => get<SettingsResponse>("/api/settings"), []);
  const [form, setForm] = useState<(AppSettings & { report_emails_text: string; alert_emails_text: string }) | null>(null);
  const [saving, setSaving] = useState(false);
  const [psiBusy, setPsiBusy] = useState(false);
  const [psiUrl, setPsiUrl] = useState("");
  const [psiResult, setPsiResult] = useState<string | null>(null);
  const [mailBusy, setMailBusy] = useState(false);
  const [testTo, setTestTo] = useState("");
  const [pw, setPw] = useState({ current: "", next: "" });

  useEffect(() => {
    if (data) setForm({ ...data.settings, report_emails_text: data.settings.report_emails.join(", "), alert_emails_text: data.settings.alert_emails.join(", ") });
  }, [data]);

  if (loading && !data) return <LoadingBlock />;
  if (error || !data) return <ErrorState message={error ?? "Failed to load"} onRetry={() => reload()} />;
  const i = data.integrations;

  const save = async (e: FormEvent) => {
    e.preventDefault();
    if (!form) return;
    setSaving(true);
    try {
      const { report_emails_text, alert_emails_text, ...rest } = form;
      const body = { ...rest, report_emails: splitEmails(report_emails_text), alert_emails: splitEmails(alert_emails_text) };
      const res = await put<{ settings: AppSettings; wakeup?: { configured: boolean; ok: boolean | null; message: string | null } }>("/api/settings", body);
      setAppTimezone(res.settings.timezone);
      toast.success("Settings saved");
      if (res.wakeup?.configured) {
        if (res.wakeup.ok) toast.info("Server wake-up moved with the new schedule");
        else toast.error(res.wakeup.message ?? "Could not update the cron-job.org wake-up job");
      }
      reload(true);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  };

  const testPsi = async () => {
    setPsiBusy(true);
    setPsiResult(null);
    try {
      const r = await post<{ ok: boolean; result?: { performance_score: number; final_url: string }; code?: string; message?: string }>(
        "/api/settings/test-pagespeed", { url: psiUrl || null, strategy: "mobile" });
      setPsiResult(r.ok ? `✓ API working — mobile score ${r.result?.performance_score} for ${r.result?.final_url}` : `✕ ${r.code}: ${r.message}`);
    } catch (err) {
      setPsiResult(`✕ ${err instanceof Error ? err.message : "Request failed"}`);
    } finally {
      setPsiBusy(false);
    }
  };

  const testMail = async () => {
    setMailBusy(true);
    try {
      const r = await post<{ ok: boolean; recipients: string[] }>("/api/settings/test-email", { to: testTo || null });
      if (r.ok) toast.success(`Test e-mail sent to ${r.recipients.join(", ")}`);
      else toast.error("Test e-mail failed — see Email Logs for the error.");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Request failed");
    } finally {
      setMailBusy(false);
    }
  };

  const sendReport = async () => {
    try {
      const r = await post<{ message: string }>("/api/reports/daily/send");
      toast.info(r.message);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Request failed");
    }
  };

  const syncExcel = async () => {
    try {
      const r = await post<{ appended: number; total_rows: number; rebuilt: boolean }>("/api/excel/sync");
      toast.success(`Excel updated: ${r.appended} new row(s), ${r.total_rows} total${r.rebuilt ? " (rebuilt from database)" : ""}`);
      reload(true);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Excel update failed");
    }
  };

  const changePassword = async (e: FormEvent) => {
    e.preventDefault();
    try {
      const r = await post<{ csrf_token: string }>("/api/auth/change-password", { current_password: pw.current, new_password: pw.next });
      setCsrfToken(r.csrf_token);
      setPw({ current: "", next: "" });
      toast.success("Password changed. Other sessions were signed out.");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Password change failed");
    }
  };

  const f = form;
  const setF = <K extends keyof NonNullable<typeof form>>(k: K, v: NonNullable<typeof form>[K]) => setForm((x) => (x ? { ...x, [k]: v } : x));

  return (
    <>
      <PageHeader title="Settings" description="Secrets (API keys, passwords, tokens) are set as server environment variables (Render / Hugging Face) and are never shown here." />
      <div className="grid gap-5 xl:grid-cols-2">
        <Section title="Integrations" description="Status of server-side configuration.">
          <dl>
            <Row label="PageSpeed API">{i.pagespeed.configured ? <Pill tone="green">Configured</Pill> : <Pill tone="red">PAGESPEED_API_KEY missing</Pill>}
              <span className="ml-2 text-xs text-slate-500">concurrency {i.pagespeed.concurrency}</span></Row>
            <Row label="E-mail">
              {i.email.configured ? <Pill tone="green">{i.email.provider.toUpperCase()} configured</Pill> : <Pill tone="red">{i.email.provider === "disabled" ? "Disabled" : `Missing: ${i.email.missing.join(", ")}`}</Pill>}
              {i.email.from && <span className="ml-2 text-xs text-slate-500">from {i.email.from}</span>}
              {i.email.smtp_host && <span className="block text-xs text-slate-500">{i.email.smtp_host}:{i.email.smtp_port} ({i.email.smtp_security})</span>}
            </Row>
            <Row label="Database">{i.database.engine === "postgresql" ? <Pill tone="green">PostgreSQL</Pill> : <Pill tone="amber">{i.database.engine}</Pill>}</Row>
            <Row label="Excel storage">
              <Pill tone={i.storage.persistent ? "green" : "red"}>{i.storage.backend}{i.storage.persistent ? " · persistent" : " · NOT persistent"}</Pill>
              <span className="mt-1 block break-all text-xs text-slate-500">{i.storage.location}</span>
              {i.storage.warning && <span className="mt-1 block text-xs text-red-600">{i.storage.warning}</span>}
            </Row>
            <Row label="Excel workbook">
              <span className="text-xs">Last updated {fmtDateTime(i.excel.last_updated_at)} {i.excel.last_status === "error" && <Pill tone="red">error</Pill>}</span>
              {i.excel.last_message && <span className="block text-xs text-slate-500">{i.excel.last_message}</span>}
              {i.excel.pending_rows && <span className="block text-xs text-amber-700">Some results are waiting to be written (retried on the next update).</span>}
            </Row>
            <Row label="Scheduler">
              <span className="text-xs">Endpoint <code className="rounded bg-slate-100 px-1">POST {i.scheduler.endpoint}</code></span>
              <span className="block text-xs text-slate-500">Token {i.scheduler.token_configured ? "configured" : "missing"} · catch-up {i.scheduler.catchup_hours} h ·
                built-in timer {i.scheduler.internal_enabled ? `every ${Math.round(i.scheduler.internal_interval_seconds / 60)} min while the server is awake` : "off"}</span>
            </Row>
            <Row label="Server wake-up">
              {i.wakeup.configured ? (
                i.wakeup.last_sync_ok === false ? <Pill tone="red">cron-job.org sync failed</Pill> : <Pill tone="green">Automatic (cron-job.org synced)</Pill>
              ) : <Pill tone="amber">Manual</Pill>}
              <span className="mt-1 block text-xs text-slate-600">Wakes {i.wakeup.plan}; stays awake until the report is e-mailed, then sleeps.</span>
              {!i.wakeup.configured && <span className="block text-xs text-amber-700">Set CRONJOB_API_KEY and CRONJOB_JOB_ID so the cron-job.org job follows this schedule automatically; otherwise set the job to the times above by hand.</span>}
              {i.wakeup.message && i.wakeup.last_sync_ok === false && <span className="block text-xs text-red-600">{i.wakeup.message}</span>}
              {!i.wakeup.keep_alive && <span className="block text-xs text-amber-700">PUBLIC_BASE_URL is not set, so the server cannot keep itself awake during long runs.</span>}
            </Row>
            <Row label="Last report">
              <span className="text-xs">Last occurrence {fmtDateTime(i.daily_report.last_sent_occurrence)} {i.daily_report.last_status && <Pill tone={i.daily_report.last_status === "sent" ? "green" : "red"}>{i.daily_report.last_status}</Pill>}</span>
            </Row>
          </dl>
          {isAdmin && (
            <div className="mt-5 space-y-4 border-t border-slate-100 pt-4">
              <div>
                <label className="label" htmlFor="psi-url">Test PageSpeed API</label>
                <div className="flex gap-2">
                  <input id="psi-url" className="input" placeholder="https://www.google.com/ (optional)" value={psiUrl} onChange={(e) => setPsiUrl(e.target.value)} />
                  <button className="btn-secondary shrink-0" disabled={psiBusy} onClick={testPsi}>{psiBusy && <Spinner />} Test API</button>
                </div>
                {psiResult && <p className={`mt-2 text-xs ${psiResult.startsWith("✓") ? "text-emerald-700" : "text-red-700"}`}>{psiResult}</p>}
              </div>
              <div>
                <label className="label" htmlFor="mail-to">Send Test Email</label>
                <div className="flex gap-2">
                  <input id="mail-to" className="input" type="email" placeholder="Defaults to report recipients" value={testTo} onChange={(e) => setTestTo(e.target.value)} />
                  <button className="btn-secondary shrink-0" disabled={mailBusy} onClick={testMail}>{mailBusy && <Spinner />} Send</button>
                </div>
              </div>
              <div className="flex flex-wrap gap-2">
                <button className="btn-secondary" onClick={sendReport}>Send daily report now</button>
                <button className="btn-secondary" onClick={syncExcel}>Update Excel now</button>
                <a className="btn-secondary" href="/api/excel/download">Download Excel</a>
              </div>
            </div>
          )}
        </Section>

        {f && (
          <Section title="Monitoring & notifications" description="One schedule for every page. Each page can still have its own alert threshold.">
            <form onSubmit={save} className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <fieldset disabled={!isAdmin} className="contents">
                <div className="sm:col-span-2">
                  <label className="label" htmlFor="s-report">Report e-mail recipients</label>
                  <input id="s-report" className="input" value={f.report_emails_text} onChange={(e) => setF("report_emails_text", e.target.value)} placeholder="ops@example.com, lead@example.com" />
                  <p className="hint">Multiple addresses allowed — separate with commas.</p>
                </div>
                <div className="sm:col-span-2">
                  <label className="label" htmlFor="s-alert">Alert e-mail recipients</label>
                  <input id="s-alert" className="input" value={f.alert_emails_text} onChange={(e) => setF("alert_emails_text", e.target.value)} placeholder="you@example.com, developer@example.com" />
                  <p className="hint">Multiple addresses allowed — separate with commas.</p>
                </div>
                <div className="rounded-lg border border-brand-100 bg-brand-50/60 p-4 sm:col-span-2">
                  <p className="text-sm font-semibold text-slate-900">Schedule — all pages</p>
                  <p className="mb-3 text-xs text-slate-600">At this time every active page is tested (Desktop + Mobile, a few at a time).
                    When the whole run is finished the report is e-mailed automatically with the Excel file.</p>
                  <div className="grid gap-3 sm:grid-cols-2">
                    <div>
                      <label className="label" htmlFor="s-time">Start time</label>
                      <input id="s-time" className="input" type="time" value={f.default_monitor_time} onChange={(e) => setF("default_monitor_time", e.target.value)} />
                    </div>
                    <div>
                      <label className="label" htmlFor="s-freq">Frequency</label>
                      <select id="s-freq" className="input" value={f.default_frequency} onChange={(e) => setF("default_frequency", e.target.value)}>
                        {FREQUENCIES.map((x) => <option key={x.value} value={x.value}>{x.label}</option>)}
                      </select>
                    </div>
                    {f.default_frequency === "weekly" && (
                      <div>
                        <label className="label" htmlFor="s-dow">Day of week</label>
                        <select id="s-dow" className="input" value={f.monitor_day_of_week} onChange={(e) => setF("monitor_day_of_week", Number(e.target.value))}>
                          {WEEKDAYS.map((d, i) => <option key={d} value={i}>{d}</option>)}
                        </select>
                      </div>
                    )}
                    <div>
                      <label className="label" htmlFor="s-tz">Timezone</label>
                      <input id="s-tz" className="input" value={f.timezone} onChange={(e) => setF("timezone", e.target.value)} />
                    </div>
                    <label className="flex items-center gap-2 text-sm text-slate-700 sm:col-span-2">
                      <input type="checkbox" className="h-4 w-4 rounded border-slate-300" checked={f.daily_report_enabled} onChange={(e) => setF("daily_report_enabled", e.target.checked)} />
                      E-mail the report automatically when all pages have been tested
                    </label>
                  </div>
                  <p className="mt-3 text-xs text-slate-600">Next run: <strong>{fmtDateTime(i.schedule.next_run_at)}</strong> · {i.schedule.description}</p>
                </div>
                <div>
                  <label className="label" htmlFor="s-th">Default threshold (new pages)</label>
                  <input id="s-th" className="input" type="number" min={1} max={100} value={f.default_threshold} onChange={(e) => setF("default_threshold", Number(e.target.value))} />
                </div>
                <div>
                  <label className="label" htmlFor="s-mode">Alert frequency</label>
                  <select id="s-mode" className="input" value={f.alert_mode} onChange={(e) => setF("alert_mode", e.target.value as AppSettings["alert_mode"])}>
                    <option value="once_until_recovered">Once until recovered</option>
                    <option value="daily">At most daily</option>
                    <option value="every_occurrence">Every occurrence</option>
                  </select>
                </div>
                <label className="flex items-center gap-2 text-sm text-slate-700">
                  <input type="checkbox" className="h-4 w-4 rounded border-slate-300" checked={f.send_recovery_emails} onChange={(e) => setF("send_recovery_emails", e.target.checked)} />
                  Send recovery e-mails
                </label>
                {isAdmin && (
                  <div className="sm:col-span-2">
                    <button className="btn-primary" disabled={saving}>{saving && <Spinner />} Save settings</button>
                  </div>
                )}
              </fieldset>
            </form>
          </Section>
        )}

        <Section title="Your account">
          <form onSubmit={changePassword} className="grid gap-3 sm:grid-cols-2">
            <div>
              <label className="label" htmlFor="pw-cur">Current password</label>
              <input id="pw-cur" className="input" type="password" autoComplete="current-password" required value={pw.current} onChange={(e) => setPw({ ...pw, current: e.target.value })} />
            </div>
            <div>
              <label className="label" htmlFor="pw-new">New password</label>
              <input id="pw-new" className="input" type="password" autoComplete="new-password" minLength={10} maxLength={72} required value={pw.next} onChange={(e) => setPw({ ...pw, next: e.target.value })} />
              <p className="hint">At least 10 characters.</p>
            </div>
            <div className="sm:col-span-2"><button className="btn-secondary">Change password</button></div>
          </form>
        </Section>
      </div>
    </>
  );
}
