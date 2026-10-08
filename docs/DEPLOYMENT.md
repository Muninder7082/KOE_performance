# Deploying to Hugging Face Spaces

This guide takes you from an empty Hugging Face account to a running monitor that tests your URLs every
day, writes the Excel workbook and sends e-mails without your computer being on.

Before you start you need:

- a Hugging Face account,
- a PostgreSQL database (a free Neon or Supabase project is enough),
- a Google Cloud project (for the PageSpeed Insights API key),
- an e-mail account or provider for sending (Gmail/Outlook/company SMTP, or SendGrid/Resend).

---

## 1. Create the Docker Space

1. Go to <https://huggingface.co/new-space>.
2. Choose a name, e.g. `website-monitor`. Set visibility to **Private** (recommended — the app has its own
   login, but private Spaces also hide the URL).
3. **Space SDK: Docker** → template **Blank**.
4. Hardware: **CPU basic** is sufficient (the work is done by Google's PageSpeed servers).
5. Create the Space.

The app URL is `https://<your-username>-<space-name>.hf.space`. Use this direct URL (not the
huggingface.co/spaces page) to sign in — see step 15 notes on cookies.

## 2. Upload the repository

The repository root must contain `README.md` (with the `sdk: docker` / `app_port: 7860` header), the
`Dockerfile`, `backend/` and `frontend/`.

```bash
git clone https://huggingface.co/spaces/<your-username>/<space-name>
cd <space-name>
# copy the contents of this project folder here (keep the folder structure)
git add .
git commit -m "Website Performance Monitor"
git push
```

(Or use **Files → Add file → Upload files** in the Space UI and upload the folders.)
Do **not** upload `.env`, `.venv`, `node_modules`, `data/` or any `.xlsx` files.

The Space starts building immediately; the first build takes a few minutes. It will fail to start
until the secrets below are set — that is expected.

## 3. Configure Secrets

Space → **Settings → Variables and secrets**. Add each **secret** with **New secret** and plain
settings with **New variable**. Secrets are encrypted and never sent to the browser.

| Name | Type | Value |
|---|---|---|
| `DATABASE_URL` | Secret | PostgreSQL URL (step 4) |
| `SECRET_KEY` | Secret | random 48+ characters |
| `SCHEDULER_TOKEN` | Secret | a *different* random 48+ characters |
| `PAGESPEED_API_KEY` | Secret | step 5 |
| `ADMIN_EMAIL` | Variable | your login e-mail |
| `ADMIN_PASSWORD` | Secret | at least 10 characters (only used to create the first admin) |
| `PUBLIC_BASE_URL` | Variable | `https://<your-username>-<space-name>.hf.space` |
| `APP_TIMEZONE` | Variable | `Asia/Kolkata` (default) |

Generate random values with:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

E-mail and storage variables are covered in steps 6 and 7. The full list is in `.env.example`.
After changing secrets, use **Settings → Factory rebuild** or **Restart this Space**.

## 4. Configure PostgreSQL

Any PostgreSQL 13+ works. Example with **Neon** (free tier):

1. <https://neon.tech> → create a project (pick a region close to the Space, e.g. AWS US-East).
2. Copy the connection string, e.g.
   `postgresql://user:password@ep-xxx.us-east-2.aws.neon.tech/neondb?sslmode=require`
3. Paste it as the `DATABASE_URL` secret. `sslmode=require` and `channel_binding` parameters are handled
   automatically.

Supabase: Project settings → Database → Connection string (URI). Prefer the **session pooler**
(port 5432) URL.

Tables are created automatically on start-up by Alembic migrations; nothing to run by hand. The database is
the system of record, so it survives Space restarts, rebuilds and moves.

## 5. Configure the PageSpeed API key

1. <https://console.cloud.google.com/> → select or create a project.
2. **APIs & Services → Library** → search **PageSpeed Insights API** → **Enable**.
3. **APIs & Services → Credentials → Create credentials → API key**.
4. Recommended: **Edit API key → API restrictions → Restrict key → PageSpeed Insights API**.
   (Do not add an HTTP-referrer restriction — calls come from the server, not a browser.)
5. Save the key as the `PAGESPEED_API_KEY` secret.

Quota: 25,000 requests/day and 400 per 100 seconds by default. 100 URLs × 2 devices daily = 200 requests.
The app sends the key in a request header only, never in URLs, logs or the frontend.

## 6. Configure e-mail

### SMTP (default)

| Variable | Example |
|---|---|
| `EMAIL_PROVIDER` | `smtp` |
| `SMTP_HOST` | `smtp.gmail.com` / `smtp.office365.com` / your server |
| `SMTP_PORT` | `587` (STARTTLS) or `465` (SSL) |
| `SMTP_SECURITY` | `starttls` or `ssl` |
| `SMTP_USERNAME` | the mailbox login |
| `SMTP_PASSWORD` (secret) | password / **app password** (Gmail and Microsoft 365 require an app password with MFA) |
| `EMAIL_FROM` | sender address, usually the same mailbox |
| `REPORT_EMAILS` | default report recipients, comma separated (editable later in Settings) |
| `ALERT_EMAILS` | default alert recipients |

### If SMTP times out on Hugging Face

Hugging Face may block outgoing SMTP ports for some Spaces. If **Send Test Email** fails with a timeout or
connection error, use an HTTPS e-mail API instead (port 443):

- **Resend**: `EMAIL_PROVIDER=resend`, `RESEND_API_KEY=...`, `EMAIL_FROM` on a domain verified in Resend.
- **SendGrid**: `EMAIL_PROVIDER=sendgrid`, `SENDGRID_API_KEY=...`, `EMAIL_FROM` = a verified sender.

Every e-mail attempt (including failures with the exact error) is listed on the **Email Logs** page.

## 7. Configure persistent Excel storage

The workbook must not live on the container's temporary disk. Choose **one**:

### Option A — Hugging Face persistent storage (simplest)

1. Space → **Settings → Persistent storage** → choose a tier (Small is plenty). This mounts a disk at `/data`.
2. Keep the defaults `STORAGE_BACKEND=local` and `LOCAL_STORAGE_DIR=/data`.

The previous version is always kept as `website-performance.xlsx.bak`.

### Option B — private Hugging Face dataset (free)

1. Create a **private dataset**: <https://huggingface.co/new-dataset> (e.g. `website-performance-data`).
2. Create a token with **Write** access: <https://huggingface.co/settings/tokens> (a fine-grained token
   limited to that dataset is best).
3. Set `STORAGE_BACKEND=hf_dataset`, `HF_DATASET_REPO=<user>/website-performance-data`, secret `HF_TOKEN`.

Every update is a commit, so the Hub keeps the full version history of the workbook.

### Option C — S3-compatible storage (AWS S3, Cloudflare R2, Backblaze B2, MinIO)

Set `STORAGE_BACKEND=s3`, `S3_BUCKET`, optional `S3_PREFIX`, `S3_REGION`, `S3_ENDPOINT_URL`
(R2: `https://<account>.r2.cloudflarestorage.com`) and secrets `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`.
Enable bucket versioning for extra safety.

**How the workbook is protected:** rows are only ever appended to *Performance History*; every result is
also in PostgreSQL. If the file is missing it is rebuilt from the database with the complete history. An
unreadable file is never overwritten — it is kept as `website-performance.corrupt-<time>.xlsx` and a
complete replacement is rebuilt. A new version is saved only after it has been re-opened and verified to have
at least as many rows as before.

The Settings page shows the storage location and warns in red if it is not persistent.

## 8. Configure the scheduler

Hugging Face does not guarantee that a Space runs forever (free Spaces sleep after ~48 h without traffic).
Scheduled work is therefore triggered from outside:

```
POST https://<your-username>-<space-name>.hf.space/api/internal/run-scheduled-checks
Authorization: Bearer <SCHEDULER_TOKEN>
```

Call it **every 1 minute** (or every 5 minutes). Each call tests only the websites whose time has arrived (each scheduled
occurrence runs once, no matter how often the endpoint is called) and sends the daily report when due.
The calls also keep the Space awake.

Step-by-step setup for cron-job.org and GitHub Actions: **[SCHEDULER.md](SCHEDULER.md)**.

The built-in timer (`ENABLE_INTERNAL_SCHEDULER=true`, every 5 minutes) also runs while the Space is awake;
both can be active at the same time safely.

**Private Space:** requests must also carry a Hugging Face token. See SCHEDULER.md → *Private Spaces*.

## 9. Test the API

1. Open `https://<your-username>-<space-name>.hf.space` and sign in with `ADMIN_EMAIL` / `ADMIN_PASSWORD`.
2. **Settings → Integrations** should show *PageSpeed API: Configured*, *PostgreSQL*, and your storage as
   *persistent*.
3. **Test PageSpeed API → Test API**. Expect `✓ API working — mobile score NN`.
   - `api_key_invalid` / `api_not_enabled` → recheck step 5.
   - `quota_exceeded` → wait for the daily reset or raise the quota in Google Cloud.

## 10. Test e-mail

**Settings → Send Test Email → Send**, then check the inbox and **Email Logs** (status *Sent* or the exact
error).

## 11. Add the first website

**Websites → Add website** (or the Dashboard button). Enter a name and the full URL
(`https://www.example.com/`). All pages follow the one schedule in **Settings → Schedule** (default daily 08:40 AM, Asia/Kolkata);
each page has its own threshold (default 90). Duplicates and non-public URLs are rejected.

## 12. Run a manual test

Click **Test** in the table, or open the website and use **Run Desktop Test / Run Mobile Test / Run Both**.
The dialog shows *Testing… → Fetching PageSpeed data… → Processing results… → Updating Excel… → Completed.*
Each device usually takes 20–60 seconds.

## 13. Verify the Excel update

**Download Excel** (Dashboard, website page or Settings). *Performance History* has one Desktop row and one
Mobile row per test, with the date and time in your timezone. Run another test and download again: the
earlier rows are still there and the new rows are appended below.

## 14. Verify an alert

Add a page you expect to score below 90 on Mobile (or temporarily set a website's threshold to 100) and run a
test. You receive *"Performance Attention Required - {Website}"* with the metrics and a PageSpeed Insights link.
Run it again: no duplicate e-mail (mode *once until recovered*). Lower the threshold so the next test passes:
the alert is marked *Recovered* (and a recovery e-mail is sent if enabled). See the **Alerts** page.

## 15. Verify the daily report

**Settings → Send daily report now** sends *"Daily Website Performance Report - {date}"* immediately with
`website-performance.xlsx` (all history) attached. The automatic report is sent as soon as the scheduled run
(Settings → Schedule, default 08:40 Asia/Kolkata) has tested every page, so it always contains that run's scores. Check **Scheduler Runs** for every call and its
result.

### Notes

- **Cookies / sign-in inside huggingface.co:** browsers block cookies in the embedded Space iframe. Open the
  direct `*.hf.space` URL. If you must use the embedded view, set `COOKIE_SAMESITE=none` (the cookie is then
  sent as Secure + Partitioned).
- **Restarts:** all state is in PostgreSQL and the workbook is in persistent storage, so restarts, rebuilds and
  hardware changes lose nothing. A scheduled run interrupted by a restart is resumed by the next scheduler call
  (websites not yet processed are still due within the catch-up window, default 6 h).
- **Scaling:** tested design target is 100+ URLs. PageSpeed calls run with controlled concurrency
  (`PAGESPEED_CONCURRENCY=3`) and retry with exponential backoff on timeouts, rate limits and 5xx errors.
  100 URLs at the same time take roughly 30–45 minutes; spreading monitoring times shortens each run.
- **Users:** create more accounts on the **Users** page. *Viewers* can see everything and download Excel but
  cannot change websites or settings.
