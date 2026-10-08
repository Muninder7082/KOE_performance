// Display helpers. Dates are shown in the app timezone (default Asia/Kolkata).
let appTimezone = "Asia/Kolkata";

export function setAppTimezone(tz: string) {
  appTimezone = tz || "Asia/Kolkata";
}

export function getAppTimezone() {
  return appTimezone;
}

export function fmtDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return new Intl.DateTimeFormat("en-GB", {
    timeZone: appTimezone, day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit", hour12: false,
  }).format(d).replace(",", "");
}

export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Intl.DateTimeFormat("en-GB", { timeZone: appTimezone, day: "2-digit", month: "short", year: "numeric" }).format(new Date(iso));
}

export function fmtShort(iso: string): string {
  return new Intl.DateTimeFormat("en-GB", { timeZone: appTimezone, day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit", hour12: false })
    .format(new Date(iso)).replace(",", "");
}

export function fmtNum(v: number | null | undefined, digits = 2, suffix = ""): string {
  if (v === null || v === undefined) return "—";
  let s = v.toFixed(digits);
  if (s.includes(".")) s = s.replace(/0+$/, "").replace(/\.$/, "");
  return `${s}${suffix}`;
}

export function fmtDuration(ms: number): string {
  if (ms < 1000) return `${ms} ms`;
  const s = ms / 1000;
  return s < 60 ? `${s.toFixed(1)} s` : `${Math.floor(s / 60)}m ${Math.round(s % 60)}s`;
}

export function to12h(hhmm: string): string {
  const [h, m] = hhmm.split(":").map(Number);
  const suffix = h >= 12 ? "PM" : "AM";
  return `${String(((h + 11) % 12) + 1).padStart(2, "0")}:${String(m).padStart(2, "0")} ${suffix}`;
}

export function todayISO(): string {
  const parts = new Intl.DateTimeFormat("en-CA", { timeZone: appTimezone, year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date());
  return parts;
}

export function psiLink(url: string, strategy: string) {
  return `https://pagespeed.web.dev/report?url=${encodeURIComponent(url)}&form_factor=${strategy}`;
}

/** Calendar day (YYYY-MM-DD) of an ISO timestamp in the app timezone. */
export function dayISO(iso: string): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: appTimezone, year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date(iso));
}
