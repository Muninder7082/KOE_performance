import { createContext, ReactNode, useCallback, useContext, useRef, useState } from "react";
import { cx, Modal } from "./ui";

// ---- Toasts --------------------------------------------------------------------
type Toast = { id: number; kind: "success" | "error" | "info"; message: string };
type ToastApi = { success: (m: string) => void; error: (m: string) => void; info: (m: string) => void };

const ToastContext = createContext<ToastApi | null>(null);

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast outside provider");
  return ctx;
}

// ---- Confirm dialog --------------------------------------------------------------
type ConfirmOptions = { title: string; message: ReactNode; confirmLabel?: string; danger?: boolean };
const ConfirmContext = createContext<((o: ConfirmOptions) => Promise<boolean>) | null>(null);

export function useConfirm() {
  const ctx = useContext(ConfirmContext);
  if (!ctx) throw new Error("useConfirm outside provider");
  return ctx;
}

export function FeedbackProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const seq = useRef(0);
  const push = useCallback((kind: Toast["kind"], message: string) => {
    const id = ++seq.current;
    setToasts((t) => [...t.slice(-3), { id, kind, message }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), kind === "error" ? 7000 : 4000);
  }, []);
  const toastApi = useRef<ToastApi>({
    success: (m) => push("success", m),
    error: (m) => push("error", m),
    info: (m) => push("info", m),
  }).current;

  const [confirmState, setConfirmState] = useState<(ConfirmOptions & { resolve: (v: boolean) => void }) | null>(null);
  const confirm = useCallback((o: ConfirmOptions) => new Promise<boolean>((resolve) => setConfirmState({ ...o, resolve })), []);
  const close = (v: boolean) => {
    confirmState?.resolve(v);
    setConfirmState(null);
  };

  return (
    <ToastContext.Provider value={toastApi}>
      <ConfirmContext.Provider value={confirm}>
        {children}
        <Modal
          open={!!confirmState}
          title={confirmState?.title ?? ""}
          onClose={() => close(false)}
          footer={
            <>
              <button className="btn-secondary" onClick={() => close(false)}>Cancel</button>
              <button className={confirmState?.danger ? "btn-danger" : "btn-primary"} onClick={() => close(true)}>
                {confirmState?.confirmLabel ?? "Confirm"}
              </button>
            </>
          }
        >
          <div className="text-sm text-slate-600">{confirmState?.message}</div>
        </Modal>
        <div className="pointer-events-none fixed bottom-4 right-4 z-[60] flex w-[calc(100%-2rem)] max-w-sm flex-col gap-2" aria-live="polite">
          {toasts.map((t) => (
            <div
              key={t.id}
              className={cx(
                "pointer-events-auto rounded-lg border px-4 py-3 text-sm shadow-lg",
                t.kind === "success" && "border-emerald-200 bg-emerald-50 text-emerald-800",
                t.kind === "error" && "border-red-200 bg-red-50 text-red-800",
                t.kind === "info" && "border-slate-200 bg-white text-slate-700",
              )}
            >
              {t.message}
            </div>
          ))}
        </div>
      </ConfirmContext.Provider>
    </ToastContext.Provider>
  );
}
