import { FormEvent, useState } from "react";
import { useAuth } from "../auth";
import { Spinner } from "../components/ui";

export default function LoginPage() {
  const { login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(email, password);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sign in failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-brand-900 to-slate-800 px-4">
      <form onSubmit={submit} className="w-full max-w-sm rounded-2xl bg-white p-7 shadow-xl">
        <div className="mb-6 flex items-center gap-3">
          <img src="/favicon.svg" alt="" className="h-9 w-9" />
          <div>
            <h1 className="text-base font-semibold">Website Performance Monitor</h1>
            <p className="text-xs text-slate-500">Sign in to continue</p>
          </div>
        </div>
        <label className="label" htmlFor="email">E-mail</label>
        <input id="email" className="input mb-4" type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} />
        <label className="label" htmlFor="password">Password</label>
        <input id="password" className="input" type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} />
        {error && <p className="mt-3 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}
        <button className="btn-primary mt-5 w-full" disabled={busy}>
          {busy && <Spinner />} Sign in
        </button>
      </form>
    </div>
  );
}
