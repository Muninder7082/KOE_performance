export type Health = "GOOD" | "ATTENTION" | "FAILED" | "PENDING";
export type Strategy = "desktop" | "mobile";

export interface User {
  id: number;
  email: string;
  role: "admin" | "viewer";
  is_active: boolean;
  created_at: string;
  last_login_at: string | null;
}

export interface Result {
  id: number;
  website_id: number | null;
  website_name: string;
  requested_url: string;
  final_url: string | null;
  strategy: Strategy;
  trigger: "manual" | "scheduled";
  status: "success" | "failed";
  api_status: string | null;
  performance_score: number | null;
  accessibility_score: number | null;
  best_practices_score: number | null;
  seo_score: number | null;
  fcp_s: number | null;
  lcp_s: number | null;
  tbt_ms: number | null;
  cls: number | null;
  speed_index_s: number | null;
  threshold: number;
  error_code: string | null;
  error_message: string | null;
  started_at: string;
  completed_at: string;
  duration_ms: number;
  tested_at: string;
  excel_appended: boolean;
  has_report: boolean;
  health: Health;
}

export interface Website {
  id: number;
  name: string;
  url: string;
  is_active: boolean;
  frequency: string;
  monitor_time: string;
  day_of_week: number | null;
  timezone: string;
  threshold: number;
  notes: string | null;
  created_at: string;
  updated_at: string;
  last_checked_at: string | null;
  schedule_description: string;
  next_run_at: string | null;
  status: Health;
  latest: { desktop: Result | null; mobile: Result | null };
  test_running: boolean;
}

export interface PageOf<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface Alert {
  id: number;
  website_id: number | null;
  website_name: string;
  url: string;
  strategy: Strategy;
  state: "open" | "recovered" | "closed";
  score: number | null;
  threshold: number;
  first_detected_at: string;
  last_detected_at: string;
  last_notified_at: string | null;
  notify_count: number;
  recovered_at: string | null;
  recovered_score: number | null;
}

export interface EmailLog {
  id: number;
  email_type: string;
  recipients: string;
  subject: string;
  website_id: number | null;
  website_name: string | null;
  status: "pending" | "sent" | "failed";
  error: string | null;
  has_attachment: boolean;
  created_at: string;
  sent_at: string | null;
}

export interface TaskRun {
  id: number;
  run_id: string;
  task: string;
  trigger: string;
  status: string;
  started_at: string;
  completed_at: string | null;
  websites_due: number;
  tests_succeeded: number;
  tests_failed: number;
  message: string | null;
}

export interface Job {
  id: string;
  website_id: number;
  strategies: Strategy[];
  status: "queued" | "running" | "completed" | "failed";
  stage: string;
  stages: string[];
  result_ids: number[];
  succeeded: number;
  failed: number;
  error: string | null;
  warning: string | null;
}

export interface AppSettings {
  report_emails: string[];
  alert_emails: string[];
  default_threshold: number;
  default_monitor_time: string;
  default_frequency: string;
  timezone: string;
  alert_mode: "once_until_recovered" | "every_occurrence" | "daily";
  send_recovery_emails: boolean;
  daily_report_enabled: boolean;
  monitor_day_of_week: number;
}

export interface SettingsResponse {
  settings: AppSettings;
  integrations: {
    pagespeed: { configured: boolean; concurrency: number };
    email: { provider: string; configured: boolean; missing: string[]; from: string | null; smtp_host: string | null; smtp_port: number | null; smtp_security: string | null };
    storage: { backend: string; location: string; persistent: boolean; warning: string | null };
    excel: { last_updated_at: string | null; last_status: string | null; last_message: string | null; pending_rows: boolean };
    database: { engine: string };
    scheduler: { internal_enabled: boolean; internal_interval_seconds: number; endpoint: string; catchup_hours: number; token_configured: boolean };
    schedule: { description: string; next_run_at: string };
    wakeup: { configured: boolean; plan: string; last_sync_ok: boolean | null; last_sync_at: string | null; message: string | null; keep_alive: boolean; server_awake_needed: boolean };
    daily_report: { last_sent_occurrence: string | null; last_status: string | null };
  };
}

export interface Dashboard {
  cards: {
    total_websites: number;
    active_monitors: number;
    tests_today: number;
    avg_desktop: number | null;
    avg_mobile: number | null;
    attention: number;
    failed_tests_today: number;
    failing_websites: number;
    lowest: { score: number; website_id: number; website_name: string; device: string; threshold: number } | null;
  };
  websites: Website[];
  scheduler_running: boolean;
  schedule: { description: string; next_run_at: string };
}

export const FREQUENCIES: { value: string; label: string }[] = [
  { value: "daily", label: "Daily" },
  { value: "weekly", label: "Weekly" },
  { value: "every_12_hours", label: "Every 12 hours" },
  { value: "every_6_hours", label: "Every 6 hours" },
  { value: "every_3_hours", label: "Every 3 hours" },
  { value: "hourly", label: "Every hour" },
];

export const WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
