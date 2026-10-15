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
| `EncalmWatchdog` | every 3 minutes | `powershell.exe -NonInteractive -ExecutionPolicy Bypass -File C:\encalm\watchdog.ps1` — first runs `deploy_sync.ps1` (updates), then restarts the app if port 8501 is not listening |
| `EncalmBackup` | daily 02:00 | the server's own `backup_db.ps1` (see §5) |

### Files that exist only on the server (never in git)

`data\` (database and its daily copies), `.streamlit\secrets.toml`,
`start_app.bat`, `backup.bat`, `backups\`, `exports\`, `logs\`.
Updates never touch them.

### Logs

| File | Written by |
|---|---|
| `C:\encalm\logs\watchdog.log` | watchdog — "App healthy" every 3 minutes, or restarts |
| `C:\encalm\logs\deploy.log` | deploy_sync — updates applied, pip installs, restarts |
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
5. After creating it, set **Branch** to `claude/tender-euler-pliacn` and click
   **Pull now**.
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

An update stops (logged as "local changes in the way") if it touches a file
that was changed on the server — today only `backup_db.ps1` (see §5). Then:
`cd C:\encalm; git stash; git pull; git stash pop`.

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

Two independent copies are made:

| Copy | Where | Kept |
|---|---|---|
| App's daily copy (first visit each day, SQLite online backup) | `C:\encalm\data\backups\revenue_analytics_YYYY-MM-DD.db` | newest 7 |
| `EncalmBackup` task (server's own `backup_db.ps1`) | `C:\encalm\backups\` | per that script |

Copy a backup off the server regularly (another machine or cloud storage).

### Restore the database

```powershell
Stop-ScheduledTask -TaskName "EncalmAnalytics"
Disable-ScheduledTask -TaskName "EncalmWatchdog" | Out-Null
Get-NetTCPConnection -LocalPort 8501 -State Listen -ErrorAction SilentlyContinue |
    ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
cd C:\encalm\data
Copy-Item revenue_analytics.db "revenue_analytics_before_restore_$(Get-Date -Format yyyyMMdd_HHmm).db"
Remove-Item revenue_analytics.db-wal, revenue_analytics.db-shm -ErrorAction SilentlyContinue
Copy-Item .\backups\revenue_analytics_YYYY-MM-DD.db .\revenue_analytics.db -Force
Start-ScheduledTask -TaskName "EncalmAnalytics"
Enable-ScheduledTask -TaskName "EncalmWatchdog" | Out-Null
```

### Roll back the code

`git -C C:\encalm log --oneline -10` shows recent versions;
`git -C C:\encalm checkout <commit>` then restart (§2b). Return to the
latest with `git -C C:\encalm checkout claude/tender-euler-pliacn`.
A full copy of the server from 15 Oct 2026 is in `C:\encalm_old` and
`C:\encalm_backup_20261015_0439` (delete once no longer needed).

---

## 5. Notes on `backup_db.ps1`

The `backup_db.ps1` in git is a **PostgreSQL** `pg_dump` script; this server
uses SQLite and keeps **its own local version** of the file (restored after
each pull). The git version contains a hard-coded database password — change
that password if PostgreSQL is ever used, and keep real passwords out of git.

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
