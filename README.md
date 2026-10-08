---
title: Website Performance Monitor
emoji: 📈
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
---

# Website Performance Monitor

Monitors any number of URLs with the official **Google PageSpeed Insights API v5** (Desktop **and** Mobile),
keeps the complete history in **PostgreSQL** and in one continuously growing Excel workbook
(**website-performance.xlsx**), and e-mails a **daily report** (with the full workbook attached) plus
**attention alerts** whenever a Performance score drops below the threshold (default 90).

Everything runs on the server. Your PC, a browser tab or a logged-in dashboard are **not** required:
an external scheduler (or the built-in timer while the Space is awake) calls a token-protected endpoint.

| | |
|---|---|
| Backend | Python 3.11, FastAPI, SQLAlchemy 2 (async) + Alembic, httpx, openpyxl |
| Frontend | React 18, TypeScript, Tailwind CSS, Recharts (built into the image, served by FastAPI) |
| Database | PostgreSQL (any provider — Neon, Supabase, Render, RDS…) |
| Excel storage | Hugging Face persistent storage (`/data`), a private HF dataset repo, or S3-compatible storage |
| E-mail | SMTP, or SendGrid / Resend over HTTPS |
| Hosting | Hugging Face Docker Space on `0.0.0.0:7860` |

## Features

- Add / edit / delete / enable / disable websites; URL validation and duplicate prevention
- One schedule for all pages, set in Settings (default **daily 08:40 Asia/Kolkata**): every active page is tested in a queue and the report is e-mailed as soon as the whole run finishes; each page keeps its own alert threshold
- Desktop + Mobile test per run; Performance, Accessibility, Best Practices, SEO, FCP, LCP, TBT, CLS, Speed Index
- Manual tests (Desktop / Mobile / Both) with live progress and protection against repeated API calls
- Excel workbook — **Performance History** (append-only, never rewritten), **Latest Status**, **Attention Required**, **Monitoring Summary**
- Daily report e-mail (default 08:40) with the latest complete workbook attached
- Attention e-mails with deduplication: *once until recovered* (default), *daily*, or *every occurrence*; optional recovery e-mails
- Dashboard, website detail with 7 / 30 / 90-day or custom-range charts, monitoring logs, alert history, e-mail logs, scheduler runs
- Users with admin / viewer roles; cookie sessions with CSRF protection; rate limiting; strict security headers

## Documentation

- **[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)** — step-by-step Hugging Face deployment (secrets, PostgreSQL, PageSpeed key, SMTP, storage, scheduler, verification)
- **[docs/SCHEDULER.md](docs/SCHEDULER.md)** — connecting cron-job.org, GitHub Actions or any cron to the scheduled-checks endpoint
- **[.env.example](.env.example)** — every configuration variable

## Local development

```bash
# Option A — everything in Docker
cp .env.example .env            # set PAGESPEED_API_KEY, SECRET_KEY, SCHEDULER_TOKEN, ADMIN_*
docker compose up --build       # http://localhost:7860

# Option B — hot reload
docker compose up -d db
cd backend && python -m venv .venv && . .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
export DATABASE_URL=postgresql://monitor:monitor@localhost:5432/monitor SECRET_KEY=... SCHEDULER_TOKEN=... \
       PAGESPEED_API_KEY=... ADMIN_EMAIL=you@example.com ADMIN_PASSWORD=... \
       LOCAL_STORAGE_DIR=../data STORAGE_LOCAL_IS_PERSISTENT=true COOKIE_SECURE=false ENVIRONMENT=development
uvicorn app.main:app --reload --port 7860
cd ../frontend && npm install && npm run dev                   # http://localhost:5173 (proxies /api)
```

API docs are at `/api/docs` when `ENVIRONMENT=development`.

## Tests

```bash
cd backend
pip install -r requirements-dev.txt
pytest                                             # SQLite
PT_TEST_DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/test_db pytest   # PostgreSQL (schema is wiped)
```

The suite (62 tests) includes the full end-to-end workflow: add website → manual Desktop + Mobile test →
database rows → Excel rows → attention e-mail → scheduled run through the secured endpoint → daily report
with the complete workbook attached → application restart → next day's run appending rows without
removing any. PageSpeed responses are mocked **only inside the tests**; the application itself always
calls the real API.

## Project layout

```
backend/
  app/
    api/            FastAPI routes (thin; no business logic)
    services/       PageSpeedService, PerformanceMonitoringService, ExcelReportService, EmailService,
                    AlertService, SchedulerService, StorageService, ReportService, JobManager
    repositories.py query construction (data access)
    models.py       users, monitored_websites, performance_results, alert_events, scheduled_tasks,
                    task_runs, email_logs, system_settings
    schedule.py     pure schedule arithmetic (unit tested)
  alembic/          database migrations (run automatically at startup)
  tests/
frontend/           React + TypeScript + Tailwind + Recharts
Dockerfile          multi-stage build, listens on 7860
docker-compose.yml  local PostgreSQL + app
```
