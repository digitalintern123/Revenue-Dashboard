# IIS / ARR Configuration for Encalm Analytics v2

## Fix 502 Errors on Large File Uploads

The DB3.xlsx file (53K rows) takes longer than IIS ARR's default 30-second timeout.
Increase the timeout to 300 seconds:

### Step 1 — IIS Manager → Application Request Routing
1. Open IIS Manager on the VPS
2. Click the server root node (not a site)
3. Double-click **Application Request Routing Cache**
4. Click **Server Proxy Settings** in the right panel
5. Set **Request timeout (seconds)** to `300`
6. Click **Apply**

### Step 2 — web.config timeout (Plesk)
Add to your site's `web.config`:

```xml
<system.webServer>
  <proxy enabled="true"
         timeout="00:05:00"
         responseBufferLimit="0" />
  <webSocket enabled="true"
             receiveBufferSize="65536"
             sendBufferSize="65536"
             pingInterval="00:00:30" />
</system.webServer>
```

### Step 3 — Caddy / Reverse Proxy (if using Caddy)
In your Caddyfile:
```
dashboard.encalmhospitality.com {
    reverse_proxy localhost:8501 {
        transport http {
            read_timeout  300s
            write_timeout 300s
        }
    }
}
```

## Register Watchdog in Task Scheduler

```powershell
schtasks /create /tn "EncalmWatchdog" /tr "powershell.exe -File C:\encalm\watchdog.ps1" /sc minute /mo 3 /ru SYSTEM /f
```

## Register Daily Backup in Task Scheduler

```powershell
schtasks /create /tn "EncalmBackup" /tr "powershell.exe -File C:\encalm\backup_db.ps1" /sc daily /st 02:00 /ru SYSTEM /f
```

## Verify Setup

```powershell
# Check app is running
netstat -an | findstr 8501

# Check watchdog is scheduled
schtasks /query /tn "EncalmWatchdog"

# Check backup is scheduled
schtasks /query /tn "EncalmBackup"

# Check latest log
Get-Content C:\encalm\logs\watchdog.log -Tail 10
```
