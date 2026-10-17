# Encalm Analytics - alert helper (dot-sourced by watchdog.ps1, deploy_sync.ps1
# and backup_db.ps1).
#
# Sends a message to a chat webhook. Put the webhook URL on the first line of
#   C:\encalm\alert_webhook.txt      (not in git - it is a secret)
# or in the machine environment variable ENCALM_ALERT_WEBHOOK.
#   - Microsoft Teams: channel > Workflows > "Post to a channel when a
#     webhook request is received" (or an old "Incoming Webhook" URL)
#   - Slack: an Incoming Webhook URL (hooks.slack.com)
# With no URL configured, alerts are only written to logs\alerts.log.
#
# The same alert (same key) is sent at most once per $AlertRepeatMinutes, so a
# long outage does not send a message every 3 minutes.

$AlertAppDir        = "C:\encalm"
$AlertLog           = Join-Path $AlertAppDir "logs\alerts.log"
$AlertState         = Join-Path $AlertAppDir "logs\alert_state.txt"
$AlertRepeatMinutes = 60

function Get-AlertWebhook {
    $file = Join-Path $AlertAppDir "alert_webhook.txt"
    if (Test-Path $file) {
        $url = (Get-Content $file -TotalCount 1).Trim()
        if ($url) { return $url }
    }
    return [Environment]::GetEnvironmentVariable("ENCALM_ALERT_WEBHOOK", "Machine")
}

function Test-AlertDue($key) {
    # True if $key was not alerted in the last $AlertRepeatMinutes; records it.
    $now = Get-Date
    $lines = @()
    if (Test-Path $AlertState) { $lines = @(Get-Content $AlertState) }
    $keep = @()
    $due = $true
    foreach ($l in $lines) {
        $parts = $l -split "`t", 2
        if ($parts.Count -ne 2) { continue }
        if ($parts[0] -eq $key) {
            $last = [datetime]::MinValue
            if ([datetime]::TryParse($parts[1], [ref]$last) -and
                ($now - $last).TotalMinutes -lt $AlertRepeatMinutes) {
                $due = $false
                $keep += $l
            }
        } else {
            $keep += $l
        }
    }
    if ($due) { $keep += ("{0}`t{1}" -f $key, $now.ToString("o")) }
    Set-Content -Path $AlertState -Value $keep
    return $due
}

function Send-EncalmAlert {
    param(
        [string]$Title,
        [string]$Text,
        [string]$Key = $Title,
        [switch]$Always          # ignore the repeat limit (e.g. "recovered")
    )
    $dir = Split-Path $AlertLog
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir | Out-Null }
    $stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    if (-not $Always -and -not (Test-AlertDue $Key)) { return }
    Add-Content -Path $AlertLog -Value ("{0} [ALERT] {1} - {2}" -f $stamp, $Title, $Text)

    $url = Get-AlertWebhook
    if (-not $url) { return }
    $message = "Encalm Analytics ($env:COMPUTERNAME): $Title`n$Text`n$stamp"
    if ($url -like "*hooks.slack.com*") {
        $body = @{ text = $message }
    } else {
        # Teams Workflows expects an Adaptive Card; old Teams webhooks read "text".
        $card = @{
            '$schema' = "http://adaptivecards.io/schemas/adaptive-card.json"
            type      = "AdaptiveCard"
            version   = "1.4"
            body      = @(
                @{ type = "TextBlock"; text = "Encalm Analytics: $Title"; weight = "Bolder"; wrap = $true },
                @{ type = "TextBlock"; text = $Text; wrap = $true },
                @{ type = "TextBlock"; text = "$env:COMPUTERNAME - $stamp"; isSubtle = $true; wrap = $true }
            )
        }
        $body = @{
            type        = "message"
            text        = $message
            attachments = @(@{ contentType = "application/vnd.microsoft.card.adaptive"; content = $card })
        }
    }
    try {
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        Invoke-RestMethod -Uri $url -Method Post -ContentType "application/json" `
            -Body ($body | ConvertTo-Json -Depth 10) -TimeoutSec 20 | Out-Null
    } catch {
        Add-Content -Path $AlertLog -Value ("{0} [ALERT] sending failed: {1}" -f $stamp, $_.Exception.Message)
    }
}
