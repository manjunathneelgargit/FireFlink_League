# FireFlink 4.0 – Go Beyond – Ee Sala Market Namde!
### Admin-only League Tracker

A scoreboard-style web app for the FireFlink 4.0 sales league (1 Nov – 20 Dec 2026, 7 BDs).
It tracks qualified demos, the daily target and carry-forward rules, the 45-demo F2F challenge,
revenue, POCs, and the four award races. It includes a full-screen **League Arena** for the office TV.

- **Backend:** FastAPI + SQLAlchemy. SQLite by default; set `DATABASE_URL` to use PostgreSQL.
- **Frontend:** React + TypeScript (Vite), Framer Motion, Recharts. Styled after fireflink.com: Poppins, the FireFlink purple palette, light pages with dark-purple feature cards and a top navigation bar. The League Arena uses the dark-purple style for TV readability.
- **Excel:** openpyxl. The database is the source of truth; Excel is used only to import and export.

---

## Quick start (local, single admin)

```bash
./start.sh            # builds the frontend if needed and serves everything on http://127.0.0.1:8000
```

First-time setup (only once):

```bash
cd backend
python3 -m venv .venv && .venv/bin/pip install fastapi "uvicorn[standard]" sqlalchemy openpyxl pydantic python-multipart tzdata pytest httpx
.venv/bin/python manage.py create-admin admin                 # creates the admin, or resets its password (min 10 chars)
.venv/bin/python manage.py import-workbook ../data/source_workbook_2026-11-03.xlsx   # optional: seed from the workbook
cd ../frontend && npm install && npm run build
```

You can also import from the UI: **Reports & Settings → Import workbook**.

### Development mode
```bash
cd backend && .venv/bin/uvicorn app.main:app --reload --port 8000
cd frontend && npm run dev        # http://localhost:5173 (proxies /api to :8000)
```

### Hosted / multi-device deployment
- Use PostgreSQL: `DATABASE_URL=postgresql+psycopg://user:pass@host/db` (and `pip install psycopg[binary]`).
- Serve over HTTPS and set `COOKIE_SECURE=1`. The session cookie is HttpOnly and SameSite=Lax.
- Run with `uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2` behind a reverse proxy.
- `SESSION_HOURS` (default 12) controls how long a sign-in lasts.
- Back up the database daily. For SQLite, copy the file with `sqlite3 league.db ".backup backup.db"`, not with `cp`.

### Docker (frontend + backend as separate images)

Images are built separately; Compose wires them together. Nginx (frontend) serves the SPA and proxies `/api` to the backend so cookies stay same-origin.

```bash
cp .env.example .env          # set ADMIN_PASSWORD (min 10 chars)
docker compose up -d --build
```

- App: http://localhost:8080  
- API docs: http://localhost:8000/api/docs  

Useful commands:

```bash
docker compose logs -f                  # both services
docker compose logs -f backend
docker compose exec backend python manage.py create-admin admin   # interactive reset
docker compose down                     # stop (keeps DB volume)
docker compose down -v                  # stop and wipe SQLite volume
```

Build images alone (to copy/push to another machine):

```bash
docker build -t fireflink-league-backend:latest ./backend
docker build -t fireflink-league-frontend:latest ./frontend
docker save fireflink-league-backend:latest fireflink-league-frontend:latest \
  | gzip > fireflink-league-images.tar.gz
# on the other machine:
gunzip -c fireflink-league-images.tar.gz | docker load
docker compose up -d
```

Change `ADMIN_PASSWORD` in `.env` before first start. After the admin exists, the entrypoint leaves the password unchanged.

---

## Teams (multi-team league)

Several teams can use one installation. Each team has its own BD members, demos, revenue, leaderboards,
awards, activity feed, audit log, **Google Sheet link**, **league settings** (dates, daily target, cutoff,
prizes) and **Arena display link**. Teams never see each other's data.

- **Super admin** manages every team: **Reports & Settings → Teams & logins** creates teams and logins, and the
  selector in the top bar switches which team every screen shows. `manage.py create-admin` creates a super admin.
- **Team admin** logins see and manage only their own team (they cannot open Teams & logins).
- New teams start with the default league settings (1 Nov – 20 Dec 2026, target 1/day, 23:59 cutoff), or a copy of
  another team's. Change each team's dates under League settings, for example for a later event.
- **Sheet format rules** (per team, League settings → Live Google Sheet):
  - *Which completed demos count*: "Only Qualified = Yes" (APAC) or "Every Completed demo" (new teams; a demo
    explicitly marked Qualified = No is still excluded).
  - *F2F when Demo Type is blank*: "From Country / City" (new teams) treats a demo whose Country or City maps to
    Malaysia, Singapore or the Middle East as F2F.
  - Tabs are always `Demos_and_Pipelines` and `League_Revenue`. Required demo columns: Sl No, BD, Customer Name,
    Domain, Country **or** City, Demo On, Demo Date, Status, plus Qualified Demo and Demo Type when the rules need
    them. A column missing from the sheet never overwrites what the app already holds.
- Upgrading an existing database is automatic on start: existing data becomes the **APAC** team, existing logins
  become super admins, and a SQLite backup is written to `backend/backups/` first.
- `manage.py import-workbook <file.xlsx> [team-slug]` imports into a specific team.

## Live Google Sheet mode (on)

The app reads the Google Sheet **live**. A background worker downloads the sheet every 60 seconds (configurable,
minimum 30) and mirrors `Demos_and_Pipelines` and `League_Revenue` into the database:

- new rows are added, changed rows are updated (the sheet wins), and rows removed from the sheet move to *Deleted*.
- Rows are matched by **Sl No + Customer Name**, so changing a Demo Date updates the same demo. Rows without a Sl No
  fall back to BD + Customer + Demo Date. **Give every row a Sl No.**
- Invalid rows (for example a Demo Type of "Online", or an unknown BD) are listed under Settings → Live Google Sheet. The stored record is left unchanged and is never deleted because of a typo.
- Safety check: if one sync would remove more than 25% of the records, nothing is deleted and an alert is shown.
- While live mode is on, demo and revenue fields are read-only in the app. Edit them in the sheet. POC start date and remarks, and the record-specific exchange rate, stay editable in the app because the sheet has no columns for them.
- **Sync now** is on the Dashboard, Demo Tracker and Revenue Tracker. The sheet must stay shared as "Anyone with the link can view".
- Run **one** server process. With several workers, set `DISABLE_GSHEET_SYNC=1` on all but one.
- To turn it off, go to Reports & Settings → League settings → Live Google Sheet → Off. Manual import and editing then work again.

## Screens

| Menu | What it does |
|---|---|
| **Dashboard** | League header and countdown, KPIs, Today's BD performance board (with **Close day now**), the animated overall leaderboard, the F2F 45 ring, the revenue race, the four awards, the activity feed and motivational messages |
| **BD Performance** | Per-BD season stats, badges, streaks, the daily target ledger, weekly ranks, charts, POCs, revenue and activity |
| **Demo Tracker** | All demos with inline Status, Qualified and Demo Type editing, live time remaining, the **POC tracker** tab, and **Deleted** (restore) |
| **Revenue Tracker** | Revenue records, breakdowns by BD, country, domain and status, **Exchange rates**, and Deleted |
| **Awards & Leaderboards** | Official standings for all four awards, week-by-week results, and finalisation |
| **Reports & Settings** | Filtered reports and export, workbook import wizard, exports, league settings, BD members, audit log |
| **League Arena** (`/arena`) | Read-only full-screen TV view that refreshes itself. Use an admin session or a display link created in Settings |

---

## Business rules as implemented

All calculations live in one module, `backend/app/services/league.py`. The dashboard, reports, exports and awards all call it.

- A demo counts only when **Status = Completed and Qualified Demo = Yes**, and its Demo Date (the completion date) falls between 1 Nov and 20 Dec 2026.
- Moving a completed, qualified demo into a POC status keeps its achievement. A sticky `demo_completed` flag records this. POC status changes never add a demo.
- **Daily target:** working days are Monday to Saturday. `Required = 1 + pending` and `pending' = max(0, pending + 1 − done)`. Each BD is calculated separately, and pending carries across Sunday. A day is finalised only at the configured cutoff (default 23:59 IST) or when you close it manually. An open day is never marked missed. Nothing is generated after 20 Dec.
- **Carry-forward never inflates the official demo count.**
- **F2F challenge and F2F Champion:** qualified completed F2F demos whose Country maps to Malaysia, Singapore or the Middle East (Dubai, Abu Dhabi and all GCC), on **any league date**. The travel windows are shown for information only (your decision of 3 Nov 2026). Country aliases such as `Malasia` and `Soudi` can be edited in Settings. Scheduled F2F demos appear only as pipeline.
- **Weeks:** Monday to Sunday by default (configurable). Sunday 1 Nov is folded into Week 1 (1–8 Nov). That gives 7 weeks, each labelled with its exact dates.
- **Revenue:** Signed uses the Contract Signed Date and Amount Credited uses the Amount Credited Date. Each record is one opportunity, and changing Signed to Amount Credited updates that record. Revenue below ₹10 lakh still appears in totals. The award requires at least ₹10 lakh, and a tie splits ₹1,00,000 equally.
- **Currencies:** non-INR records use the latest **configured** rate effective on or before the record's eligibility date, or a rate set on the record itself. With neither, the record is marked *pending conversion* and left out of INR rankings. Rates are never invented.
- **Ties:** F2F Champion and Champion of the League ties are flagged for your review. The Weekly Demo Champion tie is also flagged.
- **Filters** on the Reports page are analytical only. Official standings always use the complete league data.

## Import / export
- Import reads `Demos_and_Pipelines` (the 13 tracked columns, matched by header name) and `League_Revenue` (the 13 finalised columns). Other worksheets are listed but not imported. The six extra demo columns (Links, Discovery, Customer Asks, Comments, Follow Up On, Follow Up In) are deliberately not tracked, per your decision.
- Matching uses BD + customer + demo date for demos, and BD + customer + opportunity for revenue. **Row numbers and Sl No are never used.** Ambiguous matches go to review. Updates are applied only when you tick them. Blank cells in the file never erase stored values. Re-importing the same file changes nothing, and the full history is kept.
- Exports keep the worksheet names, column order and dropdowns. The demo sheet includes the live Time Remaining formula. An exported workbook re-imports with no duplicates.

## Audit & safety
- Every create, update, status or qualification change, delete or restore, import, export, settings change, rate change, day closure, award finalisation and login is written to the audit log with the user and time.
- Deletes are soft deletes with a confirmation prompt and can be restored.
- Passwords are hashed with scrypt. Sessions are server-side. Mutating requests require a CSRF header. Failed logins are throttled.

## Data notes from the workbook (3 Nov 2026)
- The BDs (read from the workbook dropdown) are Abhirami, Harsh, Jitendra, Nandini, Nikhita, Pratha and Samiksha.
- `Demo Type` and `Qualified Demo` were blank in all 43 rows. Until they're filled in, nothing counts. Use **Demo Tracker → Needs attention**.
- 15 October demos are Completed with no Demo Date. They were imported and kept, but they're before the league and can't count.
- `League_Revenue` had no data rows.

## Tests
```bash
cd backend && .venv/bin/python -m pytest -v
```
See `TEST_REPORT.md`.
