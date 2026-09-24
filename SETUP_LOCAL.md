# Running Locally (VS Code) or on VPS

## Quick Start

```bash
pip install -r requirements.txt
python create_secrets.py    # set your password — run once
streamlit run Home.py
```

Open **http://localhost:8501** and log in with the credentials you set.

## Default credentials (fresh zip only)
| Username | Password  |
|----------|-----------|
| admin    | admin123  |

**Change immediately** after first login by running `python create_secrets.py`.

---

## VPS Deployment (Windows Server)

### 1. Place the app folder
```
C:\encalm\          ← recommended path
```
Update `watchdog.ps1` → change `C:\encalm\` references if you use a different path.

### 2. Set credentials
```powershell
cd C:\encalm
python create_secrets.py
```

### 3. Set PostgreSQL (if using existing DB)
Add to `.streamlit\secrets.toml`:
```toml
DATABASE_URL = "postgresql://user:password@host:5432/dbname?sslmode=disable"
```
Without this, the app uses SQLite (local file `data/revenue_analytics.db`).

### 4. Create Windows Task Scheduler task
- Program: `streamlit`
- Arguments: `run Home.py --server.port 8501`
- Start in: `C:\encalm`
- Run whether user logged on or not

### 5. Set up watchdog (optional but recommended)
Schedule `watchdog.ps1` to run every 3 minutes via Task Scheduler.
Update `$LogFile` path if your app is not in `C:\encalm\`.

### 6. IIS Reverse Proxy
Point IIS ARR to `http://localhost:8501`.

---

## Navigation
```
Home  |  Previous Uploads  |  EHPL  |  Encalm Eats  |  Sky Plates
```

## Data Upload
- **Revenue PDFs / Excel** → Home page
- **Encalm Eats DSR** → Encalm Eats → Upload DSR tab
- **AOP targets** → Home page
- **Traffic data** → Home page

## Session timeout
Users are auto-logged out after **30 minutes of inactivity**.
