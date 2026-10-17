# Server Runbook — Windows VPS (Plesk + IIS)

How the live app at **dashboard.encalmhospitality.com** runs, how to update
it, and what to do when something goes wrong. Run PowerShell commands in an
**administrator** PowerShell on the VPS (via RDP).

---

## 1. How it runs

```
Browser ──HTTPS──▶ IIS (Plesk site, ARR reverse proxy) ──▶ http://localhost:8501
                                                             Streamlit (python.exe)
                                                             C:\encalm\Home.py
                                                             C:\encalm\data\revenue_analytics.db  (SQLite)
```

| Item | Value |
|---|---|
| App folder | `C:\encalm` — a git clone of `digitalintern123/Revenue-Dashboard` |
| Branch | `claude/tender-euler-pliacn` (switch to `main` once merged) |
| Python | `C:\Users\encalmit\AppData\Local\Python\bin\python.exe` |
| Start script | `C:\encalm\start_app.bat` (local file, not in git) — runs `python -m streamlit run C:\encalm\Home.py --server.port 8501 --server.headless true` |
| Database | `C:\encalm\data\revenue_analytics.db` (no `DATABASE_URL` is set) |
| Logins | `C:\encalm\.streamlit\secrets.toml` (not in git) |

### Scheduled tasks

| Task | Runs | Purpose |
|---|---|---|
| `EncalmAnalytics` | as configured (and on demand) | `C:\encalm\start_app.bat` — the app itself |
| `EncalmWatchdog` | every 3 minutes | `powershell.exe -NonInteractive -ExecutionPolicy Bypass -File C:\encalm\watchdog.ps1` — first runs `deploy_sync.ps1` (updates), then restarts the app if port 8501 is not listening, and alerts if the newest backup is over 26 hours old |
| `EncalmBackup` | daily 02:00 | `backup_db.ps1` — SQLite backup, checked, copied off the server (§4) |

### Files that exist only on the server (never in git)

`data\` (database and its daily copies), `.streamlit\secrets.toml`,
`start_app.bat`, `backup.bat`, `backups\`, `exports\`, `logs\`, and the
settings files `alert_webhook.txt` (§5), `backup_offsite.txt` (§4) and
`deploy_source.txt` (§2a). Updates never touch them.

### Logs

| File | Written by |
|---|---|
| `C:\encalm\logs\watchdog.log` | watchdog — "App healthy" every 3 minutes, or restarts |
| `C:\encalm\logs\deploy.log` | deploy_sync — updates applied, pip installs, restarts |
| `C:\encalm\logs\backup.log` | backup_db.ps1 — each backup, its checks and off-server copy |
| `C:\encalm\logs\alerts.log` | every alert raised (also sent to the webhook, §5) |
| `C:\encalm\logs\` (app log) | the app's error log (`modules/app_logger.py`) |

> **PowerShell scripts must be plain ASCII.** Windows PowerShell 5.1 reads a
> long dash (—) inside a string as a quote mark and the whole script fails
> (this stopped the watchdog from 10 Sep to 15 Oct 2026).

---

## 2. Updating the app

### 2a. Automatic: Plesk Git (set up once)

1. Plesk → **Websites & Domains → dashboard.encalmhospitality.com → Git →
   Add Repository**.
2. **Repository URL:** `git@github.com:digitalintern123/Revenue-Dashboard.git`
   (SSH, because the repository is private).
3. Copy the **Deploy key public part** Plesk shows → GitHub → repository →
   **Settings → Deploy keys → Add deploy key** (title "Plesk VPS", *Allow write
   access* unticked).
4. **Repository name:** `Revenue-Dashboard`. **Deployment mode:** Automatic.
   **Deployment directory:** `\encalm-deploy` (never `\httpdocs` — that would
   publish the code). **Post-deployment actions:** off.
5. After creating it, set **Branch** to `main` and click **Pull now**.
   (Until Oct 2026 the server followed `claude/tender-euler-pliacn`; see §2c.)
6. Optional: copy the repository's **Webhook URL** → GitHub → **Settings →
   Webhooks → Add webhook** (content type `application/json`, push event only)
   so every push is pulled automatically.

How an update then goes live:

1. A push reaches GitHub → Plesk pulls it (webhook or **Pull now**) into its
   copy at `C:\Inetpub\vhosts\<domain>\git\Revenue-Dashboard*.git`.
2. Within 3 minutes the watchdog runs `deploy_sync.ps1`, which fetches the new
   commits from that copy into `C:\encalm` (fast-forward only), runs
   `pip install -r requirements.txt` if it changed, and restarts the app.
3. `C:\encalm\logs\deploy.log` records `updated <old> -> <new>` and
   `app restarted on port 8501`.

If the Plesk copy is somewhere else, put its full path in
`C:\encalm\deploy_source.txt`.

An update stops (logged as "local changes in the way", and alerted as
"Update NOT applied") if it touches a file that was changed on the server.
`git -C C:\encalm status` shows which; keep a copy of it, then
`git -C C:\encalm checkout -- <file>` and the next watchdog run applies the
update.

### 2b. Manual update

```powershell
cd C:\encalm
git pull
Remove-Item C:\encalm\pages -Recurse -Force -ErrorAction SilentlyContinue   # leftover from older versions
Stop-ScheduledTask -TaskName "EncalmAnalytics"
Get-NetTCPConnection -LocalPort 8501 -State Listen -ErrorAction SilentlyContinue |
    ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
Start-ScheduledTask -TaskName "EncalmAnalytics"
Start-Sleep 30
netstat -ano | findstr :8501        # expect 0.0.0.0:8501 ... LISTENING
```

If `requirements.txt` changed:
`& C:\Users\encalmit\AppData\Local\Python\bin\python.exe -m pip install -r C:\encalm\requirements.txt`

Then open the site and press **Ctrl+F5**.

### 2c. One-time switch-over (Oct 2026): `main` branch, new backup, alerts

Do this once, in an **administrator PowerShell**, after the pull request
into `main` is merged on GitHub.

```powershell
cd C:\encalm
# 1. Keep the server's own backup script; the version in git replaces it
Copy-Item backup_db.ps1 backup_db.local.ps1 -ErrorAction SilentlyContinue
git checkout -- backup_db.ps1
git status                      # expect: nothing modified (untracked files are fine)

# 2. Follow main instead of the feature branch
#    (Plesk: Git -> Revenue-Dashboard -> Branch: main -> Pull now, first)
$src = (Get-ChildItem "C:\Inetpub\vhosts\*\git\*Revenue*.git" -Directory | Select-Object -First 1).FullName
if (Test-Path deploy_source.txt) { $src = (Get-Content deploy_source.txt -TotalCount 1).Trim() }
git -c safe.directory=* fetch $src main
git checkout -B main FETCH_HEAD
git branch --show-current       # expect: main

# 3. Off-server backup folder (a network share, second disk or a
#    OneDrive/SharePoint-synced folder) - see section 4
Set-Content C:\encalm\backup_offsite.txt "\\NAS\encalm-backups"

# 4. Alerts (optional but recommended) - see section 5
Set-Content C:\encalm\alert_webhook.txt "https://...webhook URL..."

# 5. Daily backup task, then run it once and check the log
schtasks /create /tn EncalmBackup /sc daily /st 02:00 /ru SYSTEM /rl HIGHEST /f `
  /tr "powershell -NoProfile -ExecutionPolicy Bypass -File C:\encalm\backup_db.ps1"
schtasks /run /tn EncalmBackup
Start-Sleep 20; Get-Content C:\encalm\logs\backup.log -Tail 3

# 6. Restart the app on the new code (section 2b) and check the version
git log --oneline -1
```

The SYSTEM account must be able to write to the off-server folder; for a
network share, run the task as a domain/service user with access instead
(`/ru <user> /rp <password>`).

---

## 3. Everyday operations

| Task | Command |
|---|---|
| Is it running? | `netstat -ano \| findstr :8501` (a `LISTENING` line) |
| Restart | the Stop / Stop-Process / Start lines from §2b |
| Watchdog health | `Get-Content C:\encalm\logs\watchdog.log -Tail 5` |
| Watchdog task state | `Get-ScheduledTaskInfo -TaskName EncalmWatchdog \| Format-List LastRunTime, LastTaskResult` (`0` = OK) |
| Recent updates | `Get-Content C:\encalm\logs\deploy.log -Tail 10` |
| Which version is live | `git -C C:\encalm log --oneline -1` |

### Changing logins

```powershell
cd C:\encalm
& C:\Users\encalmit\AppData\Local\Python\bin\python.exe create_secrets.py
```

This writes `.streamlit\secrets.toml` with a hashed password. Admins are
listed under `[auth.admins]`. Restart the app afterwards.

---

## 4. Backups and restore

| Copy | Where | Kept |
|---|---|---|
| `EncalmBackup` task, daily 02:00 (`backup_db.ps1` → `scripts/backup_sqlite.py`) | `C:\encalm\backups\revenue_analytics_YYYY-MM-DD_HHMM.db` | newest 30 |
| Same backup, **off the server** | folder on the first line of `C:\encalm\backup_offsite.txt` | newest 90 |
| App's own daily copy (first visit each day) | `C:\encalm\data\backups\revenue_analytics_YYYY-MM-DD.db` | newest 7 |

Each backup is made with SQLite's online backup API (safe while the app runs),
checked (`PRAGMA integrity_check`, row counts) and only then copied off the
server. A failed backup, a missing off-server folder, or no backup for 26
hours raises an alert (§5). The result of every run is in `logs\backup.log`.

**Restore test** (do it once a quarter, on any copy — it does not touch the
live database):

```powershell
& C:\Users\encalmit\AppData\Local\Python\bin\python.exe C:\encalm\scripts\backup_sqlite.py `
    --verify "\\NAS\encalm-backups\revenue_analytics_YYYY-MM-DD_HHMM.db"
# OK {"integrity": "ok", "rows": {"revenue_master": ...}, "latest_revenue_date": "..."}
```

### Restore the database

```powershell
Stop-ScheduledTask -TaskName "EncalmAnalytics"
Disable-ScheduledTask -TaskName "EncalmWatchdog" | Out-Null
Get-NetTCPConnection -LocalPort 8501 -State Listen -ErrorAction SilentlyContinue |
    ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
cd C:\encalm\data
Copy-Item revenue_analytics.db "revenue_analytics_before_restore_$(Get-Date -Format yyyyMMdd_HHmm).db"
Remove-Item revenue_analytics.db-wal, revenue_analytics.db-shm -ErrorAction SilentlyContinue
Copy-Item C:\encalm\backups\revenue_analytics_YYYY-MM-DD_HHMM.db .\revenue_analytics.db -Force
Start-ScheduledTask -TaskName "EncalmAnalytics"
Enable-ScheduledTask -TaskName "EncalmWatchdog" | Out-Null
```

### Roll back the code

`git -C C:\encalm log --oneline -10` shows recent versions;
`git -C C:\encalm checkout <commit>` then restart (§2b). Return to the
latest with `git -C C:\encalm checkout main`.
A full copy of the server from 15 Oct 2026 is in `C:\encalm_old` and
`C:\encalm_backup_20261015_0439` (delete once no longer needed).

---

## 5. Alerts

`notify.ps1` sends an alert to a chat webhook. Used by:

| Alert | Raised by |
|---|---|
| App was down — restarted / App is DOWN | `watchdog.ps1` |
| Database backup FAILED / out of date / no off-server copy | `backup_db.ps1`, `watchdog.ps1` |
| Update NOT applied / App did not start after update / Update check failed | `deploy_sync.ps1` |

Set up once: put the webhook URL on the first line of
`C:\encalm\alert_webhook.txt` (a secret — never in git).
- **Microsoft Teams:** channel → **⋯ → Workflows → "Post to a channel when a
  webhook request is received"** → copy the URL.
- **Slack:** an Incoming Webhook URL (`hooks.slack.com/...`).

The same alert is repeated at most once an hour. Without a URL, alerts are
only written to `logs\alerts.log`. Test it:

```powershell
. C:\encalm\notify.ps1; Send-EncalmAlert -Title "Test alert" -Text "Hello from the server" -Always
```

### Passwords that were in git (change them)

Old versions in git history contain the PostgreSQL password `Encalm@2026`
(`backup_db.ps1`, `secrets.toml.example`). Other credentials were exposed in
chat during setup. Change all of them; removing them from history is not
enough once they have been seen:
- the Neon (PostgreSQL) database password, if that database still exists —
  or delete the Neon project;
- every app login in `.streamlit\secrets.toml` (`python create_secrets.py`,
  §3 *Changing logins*), the admin login first;
- `Encalm@2026` anywhere it is still used (PostgreSQL, Windows, Plesk).

---

## 6. IIS / reverse proxy

IIS (Application Request Routing) forwards the site to `http://localhost:8501`.
Streamlit needs **WebSockets**, and large uploads need long timeouts.

1. IIS Manager → server node → **Application Request Routing Cache** →
   **Server Proxy Settings** → **Request timeout** `300` → Apply.
2. In the site's `web.config`:

   ```xml
   <system.webServer>
     <proxy enabled="true" timeout="00:05:00" responseBufferLimit="0" />
     <webSocket enabled="true" receiveBufferSize="65536" sendBufferSize="65536"
                pingInterval="00:00:30" />
   </system.webServer>
   ```
3. The **WebSocket Protocol** Windows feature must be installed
   (Server Manager → Web Server → Application Development).

App upload limit: 300 MB (`.streamlit/config.toml`, `maxUploadSize`).

### Firewall

Port 8501 is blocked from the internet so users can only reach the app
through IIS/HTTPS:

```powershell
New-NetFirewallRule -DisplayName "Block Streamlit 8501 external" -Direction Inbound `
    -LocalPort 8501 -Protocol TCP -Action Block -RemoteAddress Internet
```

---

## 7. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| Site down, nothing on 8501 | Restart (§2b). If it does not come up, run the start command by hand in PowerShell to see the error: `cd C:\encalm; & <python> -m streamlit run C:\encalm\Home.py --server.port 8501 --server.headless true` |
| Watchdog log not updating | `LastTaskResult` ≠ 0: check the task action includes `-ExecutionPolicy Bypass` and the script is ASCII-only |
| Page unstyled (beige sidebar, plain list "Home, EHPL, …", "Page not found") | A `pages` folder exists in `C:\encalm` — delete it and restart. Page files live in `views\` |
| Stuck on "Connecting…" / page loads then freezes | IIS is not passing WebSockets — §6 |
| 502 on large uploads | ARR timeout — §6 |
| Update not applied | `deploy.log`; check Plesk shows the new commit (Pull now); "local changes in the way" → §2a |
| "No auth users configured" | `.streamlit\secrets.toml` missing — §3 Changing logins |
| Streamlit prints "Local URL … :8501" while started with another port | Only the printed text (`browser.serverPort` in config.toml); the real port is the one passed |

---

## Appendix — Linux alternative

`deploy/` contains a Linux/Plesk setup (systemd service, path-unit restart on
deploy, nginx directives, `post_deploy.sh`, PostgreSQL backup script) for
running the app on a Linux VPS with PostgreSQL. It is not used by the current
Windows server.
