import { useCallback, useEffect, useRef, useState } from "react";
import { get, post } from "../api";
import type { Job, Strategy } from "../types";
import { useToast } from "./feedback";
import { cx, Modal, Spinner } from "./ui";

const STEPS = ["Testing...", "Fetching PageSpeed data...", "Processing results...", "Updating Excel...", "Completed."];

/** Starts a manual PageSpeed test and shows its progress. */
export function useTestRunner(onFinished: () => void) {
  const toast = useToast();
  const [job, setJob] = useState<Job | null>(null);
  const [label, setLabel] = useState("");
  const [starting, setStarting] = useState<number | null>(null);
  const timer = useRef<number | null>(null);

  const stop = () => {
    if (timer.current) window.clearTimeout(timer.current);
    timer.current = null;
  };
  useEffect(() => stop, []);

  const poll = useCallback((id: string) => {
    const tick = async () => {
      try {
        const j = await get<Job>(`/api/jobs/${id}`);
        setJob(j);
        if (j.status === "completed" || j.status === "failed") {
          stop();
          if (j.status === "completed") {
            if (j.failed) toast.error(`Test finished: ${j.succeeded} succeeded, ${j.failed} failed. See Monitoring Logs.`);
            else toast.success("Test completed");
            if (j.warning) toast.error(j.warning);
          } else toast.error(j.error ?? "Test failed");
          onFinished();
          return;
        }
      } catch {
        /* transient; keep polling */
      }
      timer.current = window.setTimeout(tick, 1500);
    };
    tick();
  }, [onFinished, toast]);

  const start = async (websiteId: number, websiteName: string, strategies: Strategy[]) => {
    if (starting !== null || (job && (job.status === "queued" || job.status === "running"))) return;
    setStarting(websiteId);
    try {
      const j = await post<Job>(`/api/websites/${websiteId}/test`, { strategies });
      setLabel(`${websiteName} — ${strategies.map((s) => s[0].toUpperCase() + s.slice(1)).join(" + ")}`);
      setJob(j);
      poll(j.id);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not start test");
    } finally {
      setStarting(null);
    }
  };

  const running = !!job && (job.status === "queued" || job.status === "running");
  const modal = (
    <Modal open={!!job} title="Manual PageSpeed test" onClose={() => !running && setJob(null)}
      footer={<button className="btn-secondary" disabled={running} onClick={() => setJob(null)}>{running ? "Running..." : "Close"}</button>}>
      {job && (
        <div>
          <p className="mb-4 text-sm font-medium text-slate-800">{label}</p>
          <ol className="space-y-2.5">
            {STEPS.map((step) => {
              const reached = job.stages.includes(step);
              const current = job.stage === step && running;
              const failedHere = job.status === "failed" && step === "Completed.";
              return (
                <li key={step} className="flex items-center gap-3 text-sm">
                  <span className={cx("flex h-5 w-5 items-center justify-center rounded-full text-[11px]",
                    failedHere ? "bg-red-100 text-red-700" : reached && !current ? "bg-emerald-100 text-emerald-700" : current ? "bg-brand-100 text-brand-700" : "bg-slate-100 text-slate-400")}>
                    {current ? <Spinner className="h-3 w-3" /> : failedHere ? "✕" : reached ? "✓" : "•"}
                  </span>
                  <span className={reached || current ? "text-slate-800" : "text-slate-400"}>{failedHere ? "Failed." : step}</span>
                </li>
              );
            })}
          </ol>
          {running && <p className="mt-4 text-xs text-slate-500">PageSpeed tests usually take 20–60 seconds per device.</p>}
          {job.status === "completed" && <p className="mt-4 text-sm text-slate-700">{job.succeeded} succeeded, {job.failed} failed.</p>}
          {job.error && <p className="mt-4 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">{job.error}</p>}
          {job.warning && <p className="mt-4 rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-800">{job.warning}</p>}
        </div>
      )}
    </Modal>
  );
  return { start, running, starting, modal };
}
