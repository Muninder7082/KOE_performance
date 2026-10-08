# Connecting an external scheduler

All scheduled monitoring and the daily report run when this endpoint is called:

```
POST /api/internal/run-scheduled-checks
Authorization: Bearer <SCHEDULER_TOKEN>        (or header  X-Scheduler-Token: <SCHEDULER_TOKEN>)
```

On each call the server:

1. authenticates the token (constant-time comparison; 30 calls/min/IP rate limit),
2. finds active websites whose scheduled time has arrived (each website's own frequency, time and timezone),
3. tests each one on Desktop and Mobile (controlled concurrency, retries with backoff),
4. stores the results in PostgreSQL,
5. appends the rows to the Excel workbook,
6. checks the threshold and sends attention / recovery e-mails (deduplicated),
7. sends the daily report (with the complete workbook) if its time has arrived,
8. records the run on the **Scheduler Runs** page.

The call returns immediately (`{"status": "started", "websites_due": N, ...}`) and the work continues in the
background, because most cron services time out after ~30 seconds. Add `?wait=true` to block until the run
finishes and get the full summary (useful in GitHub Actions).

### How often to call it

**Every 1 minute** is best (cron-job.org supports it); every 5 minutes is fine too. A call when nothing is due only reads the database — it uses no PageSpeed quota. Calling often is harmless:

- each scheduled occurrence (e.g. "today 08:40") runs **once**, however many calls arrive,
- a call while a run is in progress returns `{"status": "already_running"}` (database lease lock),
- if the Space was asleep at 08:40, the first call after it wakes runs today's check, as long as it is
  within `SCHEDULE_CATCHUP_HOURS` (default 6). Older missed runs are skipped rather than replayed.

With a 1-minute interval a website scheduled for 08:40 starts testing by 08:41; with 10 minutes, by 08:50.

---

## Option 1 — cron-job.org (free, no code)

1. Sign up at <https://cron-job.org> and click **Create cronjob**.
2. **URL:** `https://<your-username>-<space-name>.hf.space/api/internal/run-scheduled-checks`
3. **Execution schedule:** *Every 1 minute* (or every 5 minutes).
4. **Advanced → Request method:** `POST`.
5. **Advanced → Headers:** add `Authorization` = `Bearer <your SCHEDULER_TOKEN>`.
6. **Advanced → Timeout:** 30 seconds. Enable failure notifications.
7. Save, then **Test run**. Expect HTTP 200 with `"status":"started"` (or `"already_running"`).

## Option 2 — GitHub Actions

Create a (private) GitHub repository, add repository secrets **Settings → Secrets and variables → Actions**:
`MONITOR_URL` = `https://<your-username>-<space-name>.hf.space` and `SCHEDULER_TOKEN`
(plus `HF_TOKEN` for a private Space). Then add `.github/workflows/monitor.yml` — a ready file is in
[examples/github-actions-scheduler.yml](examples/github-actions-scheduler.yml).

GitHub's scheduled workflows can start several minutes late under load; with the catch-up window this only
delays a check, it never skips it.

## Option 3 — any server with cron

```cron
*/10 * * * * curl -fsS -m 30 -X POST -H "Authorization: Bearer $SCHEDULER_TOKEN" https://<your-username>-<space-name>.hf.space/api/internal/run-scheduled-checks >/dev/null
```

Windows Task Scheduler (PowerShell action, repeat every 10 minutes):

```powershell
Invoke-RestMethod -Method Post -Uri "https://<your-username>-<space-name>.hf.space/api/internal/run-scheduled-checks" -Headers @{ Authorization = "Bearer <SCHEDULER_TOKEN>" }
```

(This option needs that machine to be on; options 1 and 2 do not.)

---

## Private Spaces

A **private** Space only accepts requests carrying a Hugging Face token that can read it. Send both headers:

```
Authorization: Bearer <HF read token>
X-Scheduler-Token: <SCHEDULER_TOKEN>
```

The app accepts the scheduler token from `X-Scheduler-Token` precisely so that `Authorization` stays free for
Hugging Face. Create a fine-grained read token at <https://huggingface.co/settings/tokens>.
In cron-job.org add both headers; in GitHub Actions use the commented variant in the example workflow.

## Checking status

```bash
curl -s -H "X-Scheduler-Token: $SCHEDULER_TOKEN" https://<space-url>/api/internal/scheduler-status
# {"running": false, "websites_due": 0, "report_due": false, "server_time": "..."}
```

The **Scheduler Runs** page shows every run: trigger, websites due, tests succeeded/failed, duration and errors.

## Security

- Use a long random `SCHEDULER_TOKEN` (48+ characters) that differs from `SECRET_KEY`.
- Never put the token in a URL query string; send it in a header.
- Rotate it by changing the Space secret and the scheduler configuration together.
