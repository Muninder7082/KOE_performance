import { ReactNode, useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { useAuth } from "../auth";
import { cx } from "./ui";

const icon = (d: string) => (
  <svg className="h-[18px] w-[18px] shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8} aria-hidden="true">
    <path strokeLinecap="round" strokeLinejoin="round" d={d} />
  </svg>
);

const NAV: { to: string; label: string; icon: ReactNode; admin?: boolean }[] = [
  { to: "/", label: "Dashboard", icon: icon("M4 13h6V4H4v9zm0 7h6v-5H4v5zm10 0h6v-9h-6v9zm0-16v5h6V4h-6z") },
  { to: "/websites", label: "Websites", icon: icon("M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zm-9-9h18M12 3c2.5 2.5 3.8 5.5 3.8 9s-1.3 6.5-3.8 9c-2.5-2.5-3.8-5.5-3.8-9S9.5 5.5 12 3z") },
  { to: "/logs", label: "Monitoring Logs", icon: icon("M4 6h16M4 12h16M4 18h10") },
  { to: "/alerts", label: "Alerts", icon: icon("M12 9v4m0 4h.01M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z") },
  { to: "/emails", label: "Email Logs", icon: icon("M4 6h16v12H4V6zm0 0 8 7 8-7") },
  { to: "/scheduler", label: "Scheduler Runs", icon: icon("M12 7v5l3 2m6-2a9 9 0 1 1-18 0 9 9 0 0 1 18 0z") },
  { to: "/settings", label: "Settings", icon: icon("M10.3 4.3a1.7 1.7 0 0 1 3.4 0l.2.9a1.7 1.7 0 0 0 2.5 1l.8-.5a1.7 1.7 0 0 1 2.4 2.4l-.5.8a1.7 1.7 0 0 0 1 2.5l.9.2a1.7 1.7 0 0 1 0 3.4l-.9.2a1.7 1.7 0 0 0-1 2.5l.5.8a1.7 1.7 0 0 1-2.4 2.4l-.8-.5a1.7 1.7 0 0 0-2.5 1l-.2.9a1.7 1.7 0 0 1-3.4 0l-.2-.9a1.7 1.7 0 0 0-2.5-1l-.8.5a1.7 1.7 0 0 1-2.4-2.4l.5-.8a1.7 1.7 0 0 0-1-2.5l-.9-.2a1.7 1.7 0 0 1 0-3.4l.9-.2a1.7 1.7 0 0 0 1-2.5l-.5-.8a1.7 1.7 0 0 1 2.4-2.4l.8.5a1.7 1.7 0 0 0 2.5-1l.2-.9zM12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z") },
  { to: "/users", label: "Users", admin: true, icon: icon("M17 20v-2a4 4 0 0 0-4-4H7a4 4 0 0 0-4 4v2m18 0v-2a4 4 0 0 0-3-3.9M14 3.1a4 4 0 0 1 0 7.8M10 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0z") },
];

export default function Layout() {
  const { user, isAdmin, logout } = useAuth();
  const [open, setOpen] = useState(false);

  const nav = (
    <nav className="flex flex-1 flex-col gap-0.5 px-3 py-4">
      {NAV.filter((n) => !n.admin || isAdmin).map((n) => (
        <NavLink
          key={n.to}
          to={n.to}
          end={n.to === "/"}
          onClick={() => setOpen(false)}
          className={({ isActive }) =>
            cx("flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition",
              isActive ? "bg-white/10 text-white" : "text-slate-300 hover:bg-white/5 hover:text-white")
          }
        >
          {n.icon}
          {n.label}
        </NavLink>
      ))}
    </nav>
  );

  const brand = (
    <div className="flex items-center gap-2.5 px-5 py-5">
      <img src="/favicon.svg" alt="" className="h-8 w-8" />
      <div className="leading-tight">
        <p className="text-sm font-semibold text-white">PageSpeed Monitor</p>
        <p className="text-[11px] text-slate-400">Website performance</p>
      </div>
    </div>
  );

  const footer = (
    <div className="border-t border-white/10 px-5 py-4 text-xs text-slate-400">
      <p className="truncate text-slate-200" title={user?.email}>{user?.email}</p>
      <p className="mb-2 capitalize">{user?.role}</p>
      <button className="text-slate-300 underline-offset-2 hover:text-white hover:underline" onClick={logout}>Sign out</button>
    </div>
  );

  return (
    <div className="min-h-screen lg:pl-60">
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-60 flex-col bg-brand-900 lg:flex">
        {brand}
        {nav}
        {footer}
      </aside>
      {open && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-slate-900/50" onClick={() => setOpen(false)} />
          <aside className="absolute inset-y-0 left-0 flex w-64 flex-col bg-brand-900">{brand}{nav}{footer}</aside>
        </div>
      )}
      <header className="sticky top-0 z-20 flex items-center gap-3 border-b border-slate-200 bg-white/90 px-4 py-3 backdrop-blur lg:hidden">
        <button className="btn-ghost btn-sm" onClick={() => setOpen(true)} aria-label="Open navigation">
          <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path d="M4 6h16M4 12h16M4 18h16" strokeLinecap="round" /></svg>
        </button>
        <span className="text-sm font-semibold">PageSpeed Monitor</span>
      </header>
      <main className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
        <Outlet />
      </main>
    </div>
  );
}
