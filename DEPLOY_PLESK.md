# Deploying on a VPS with Plesk (Git + PostgreSQL)

The app runs as a background service (systemd) on the VPS, PostgreSQL runs on
the same VPS, and Plesk's nginx serves your domain over HTTPS and forwards it
to the app. Every `git push` is deployed by Plesk's Git extension.

```
Browser ──HTTPS──▶ Plesk nginx ──▶ 127.0.0.1:8501 Streamlit (encalm.service) ──▶ PostgreSQL (localhost)
                                        ▲
              Plesk Git deploy ─ deploy/post_deploy.sh ─ restart via encalm-restart.path
```

Files used (all in `deploy/`): `encalm.service`, `encalm-restart.path`,
`encalm-restart.service`, `encalm.env.example`, `nginx-plesk.conf`,
`post_deploy.sh`, `backup_postgres.sh`.

In the commands below replace:

| Placeholder | Meaning | Example |
|---|---|---|
| `YOUR-DOMAIN.COM` | the domain/subdomain in Plesk | `analytics.encalm.com` |
| `SYSUSER` | the domain's system user (Plesk → Websites & Domains → domain → *Hosting & DNS → Hosting* → "System user") | `encalm_xyz` |

You need **SSH access as root** (or a sudo user) for steps 1, 2 and 5.

---

## 1. Install system packages (once)

Ubuntu/Debian:

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip postgresql rsync
python3 --version     # 3.10 or newer
```

## 2. Create the PostgreSQL database (once)

Pick a strong password and use it in step 3.

```bash
sudo -u postgres psql <<'SQL'
CREATE ROLE encalm LOGIN PASSWORD 'CHANGE-THIS-PASSWORD';
CREATE DATABASE encalm OWNER encalm;
SQL
```

PostgreSQL only listens on localhost by default — leave it that way. The app
creates its tables itself on first start.

## 3. Private settings (once, never in git)

```bash
D=/var/www/vhosts/YOUR-DOMAIN.COM
sudo mkdir -p $D/private
# database connection
sudo cp deploy/encalm.env.example $D/private/encalm.env       # or create it by hand
sudo nano $D/private/encalm.env                                # set the real password
# logins (same file you used on Render; generate with: python create_secrets.py)
sudo nano $D/private/secrets.toml
sudo chown SYSUSER:psacln $D/private/encalm.env $D/private/secrets.toml
sudo chmod 600 $D/private/encalm.env $D/private/secrets.toml
```

`encalm.env` needs just:

```
DATABASE_URL=postgresql://encalm:CHANGE-THIS-PASSWORD@127.0.0.1:5432/encalm
```

`secrets.toml` holds the `[auth.users]` / `[auth.admins]` sections. Do **not**
put a `DATABASE_URL` line in it (it would override `encalm.env`).

## 4. Connect the Git repository in Plesk

1. Plesk → **Websites & Domains → YOUR-DOMAIN.COM → Git**.
2. **Remote repository**: `git@github.com:digitalintern123/Revenue-Dashboard.git`.
   Plesk shows an **SSH public key** — add it in GitHub → repo → *Settings →
   Deploy keys* (read-only).
3. **Repository branch**: the branch you deploy (`main` once this branch is merged).
4. **Deployment mode**: Automatic. **Deployment path**: `encalm-app`
   (→ `/var/www/vhosts/YOUR-DOMAIN.COM/encalm-app`, *not* `httpdocs`).
5. **Repository settings → Enable additional deployment actions**:
   ```
   bash deploy/post_deploy.sh
   ```
6. Press **Pull now / Deploy now** once. The first run creates the Python
   environment (`venv/`, ~1 minute) and copies `secrets.toml` into place.

For automatic deploys on every push, copy the **Webhook URL** Plesk shows into
GitHub → *Settings → Webhooks*.

## 5. Install the app service (once, as root)

```bash
cd /var/www/vhosts/YOUR-DOMAIN.COM/encalm-app
# fill in the placeholders, then install
sudo sed -e 's/YOUR-DOMAIN.COM/your.real.domain/g' -e 's/SYSUSER/real_sysuser/g' \
     deploy/encalm.service         | sudo tee /etc/systemd/system/encalm.service >/dev/null
sudo sed -e 's/YOUR-DOMAIN.COM/your.real.domain/g' \
     deploy/encalm-restart.path    | sudo tee /etc/systemd/system/encalm-restart.path >/dev/null
sudo cp deploy/encalm-restart.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now encalm.service encalm-restart.path
systemctl status encalm.service --no-pager      # should say "active (running)"
curl -s http://127.0.0.1:8501/_stcore/health    # prints: ok
```

From now on every Git deploy runs `post_deploy.sh`, which touches
`encalm-app/.deployed`; `encalm-restart.path` sees that and restarts the app.
No sudo is needed by the Plesk user.

## 6. Domain, HTTPS and nginx (once)

1. Plesk → domain → **SSL/TLS Certificates** → install a free **Let's Encrypt**
   certificate and tick *Redirect from HTTP to HTTPS*.
2. Plesk → domain → **Apache & nginx Settings**:
   - untick **Proxy mode**;
   - paste the contents of `deploy/nginx-plesk.conf` into **Additional nginx
     directives** → **OK**.
3. Open `https://YOUR-DOMAIN.COM` → the Encalm sign-in page should appear.

## 7. Nightly backups, copied off the VPS (once, as root)

```bash
sudo cp deploy/backup_postgres.sh /usr/local/bin/encalm-backup
sudo chmod 700 /usr/local/bin/encalm-backup
```

Choose where the off-server copy goes — create `/etc/encalm-backup.conf` with **one** of:

```bash
# another server over SSH (set up an SSH key for root → that server first)
RSYNC_TARGET="backup@other-server:/backups/encalm/"
# or cloud storage via rclone (Google Drive, S3, Backblaze B2 …): apt install rclone && rclone config
RCLONE_REMOTE="gdrive:encalm-backups"
```

Test it, then schedule it for 02:15 every night:

```bash
sudo /usr/local/bin/encalm-backup
( sudo crontab -l 2>/dev/null; echo '15 2 * * * /usr/local/bin/encalm-backup >> /var/log/encalm-backup.log 2>&1' ) | sudo crontab -
```

Local copies are kept 14 days in `/var/backups/encalm` (set `KEEP_DAYS` in the
conf file to change). **Restore** (e.g. after a bad import):

```bash
sudo systemctl stop encalm
sudo -u postgres pg_restore --clean --if-exists -d encalm < /var/backups/encalm/encalm_YYYY-MM-DD_HHMM.dump
sudo systemctl start encalm
```

Also enable Plesk's own server backups (Tools & Settings → Backup Manager) for
the files and settings.

## 8. Bringing over the data from Render/Neon (optional)

To start the VPS with the data already uploaded on the Render site, copy Neon
into the VPS database once (from the VPS, before people start uploading there):

```bash
# NEON_URL = the DATABASE_URL currently set on Render
pg_dump -Fc --no-owner --no-acl "$NEON_URL" > /tmp/neon.dump
sudo -u postgres pg_restore --no-owner --role=encalm -d encalm < /tmp/neon.dump
sudo systemctl restart encalm
```

(`pg_dump` from Ubuntu's postgresql package must be the same or newer major
version than Neon's; `sudo apt install postgresql-client-17` if it complains.)

Keep the Render site running until the VPS is checked, then shut it down.

---

## Day-to-day

| Task | How |
|---|---|
| Deploy new code | `git push` (webhook) or Plesk → Git → **Deploy now** |
| Is it running? | `systemctl status encalm` |
| Live log | `journalctl -u encalm -f` |
| Restart | `sudo systemctl restart encalm` |
| Change logins | edit `private/secrets.toml`, then Plesk → Git → Deploy now |
| Backup log | `tail /var/log/encalm-backup.log` |

## Troubleshooting

| Symptom | Fix |
|---|---|
| Page stuck on "Connecting…" | the WebSocket isn't proxied — check step 6 (Proxy mode off, directives pasted) |
| 502 Bad Gateway | app not running: `systemctl status encalm`, `journalctl -u encalm -n 50` |
| "No auth users configured" | `private/secrets.toml` missing → step 3, then Deploy now |
| Database connection error | check `private/encalm.env` password; `sudo -u postgres psql -c '\l'` |
| nginx error "duplicate location /" | use the `location ~ /` block exactly as in `nginx-plesk.conf` |
| Upload fails for big files | raise `client_max_body_size` in the nginx directives |
