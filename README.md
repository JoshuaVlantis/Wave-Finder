# Wave Finder

Clean, fast tools for South African marine recreation:

- Static website with a Leaflet map, wind overlay, MPA data, blog, limits, and records
- Minimal Node.js API (Express + MariaDB) for spots and records
- Python ML scripts to train and predict underwater visibility (in meters)


## Repository layout

```
.
├── apps/
│   ├── api/                 # Express API (MariaDB-backed)
│   │   ├── spots-api.js     # Server entry
│   │   ├── package.json
│   │   └── .env.example     # Example env (copy to .env; keep secrets out of git)
│   ├── web/                 # Static site (served by any static host)
│   │   ├── index.html       # Map and wind overlay UI
│   │   ├── blog.html, post.html, about.html, limits.html, records.html
│   │   ├── data/            # JSON/GeoJSON used by the site
│   │   ├── content/posts/   # Blog markdown sources
│   │   ├── docs/            # Public docs (e.g., Linefishing PDF)
│   │   └── static/          # Shared assets (css/js/images/fonts)
│   └── ml/                  # ML training & prediction utilities
│       ├── temporal_features.py
│       ├── train_model_from_db.py
│       ├── predict_visibility_from_db.py
│       ├── config.example.ini
│       ├── models/          # Saved models (.pkl + .meta.json)
│       ├── predictions/     # Latest predictions (txt)
│       └── data/            # Debug feature vectors
├── LICENSE
├── README.md                # You are here
└── .gitignore               # Ignores env files, configs, artifacts, etc.
```


## Quick start

Prereqs
- Node.js 18+ for the API
- Python 3.10+ for ML scripts (optional)
- MariaDB instance with your data (for API/ML)

Clone and install API deps
```powershell
cd apps\api
npm install
# Copy example env and set your values
Copy-Item .env.example .env
# Edit .env: DB_HOST, DB_USER, DB_PASS, DB_NAME
npm start  # if you add a start script, or run: node spots-api.js
```

Open the static web
```powershell
# Open files directly (static hosting recommended)
# For local dev with a quick server:
cd ..\web
npx serve .  # or use any static server; optional
```

ML environment (optional)
```powershell
cd ..\ml
python -m venv .venv; . .venv\Scripts\Activate.ps1
pip install -U pip
# Install project packages (pandas, numpy, scikit-learn, pymysql, joblib; optional: xgboost, lightgbm, shap)
# Copy example config and set DB values
Copy-Item config.example.ini config.ini
```


## Running the API

`apps/api/spots-api.js` exposes:
- GET `/api/spots`  → active dive spots from MariaDB `locations`
- GET `/api/records` → top 3 records per species (grouped)
- GET `/health` → liveness

Environment variables (see `.env.example`):
- `PORT` (default 3001), `DB_HOST`, `DB_USER`, `DB_PASS`, `DB_NAME`, `DB_POOL` (optional)

Security: the server requires all DB vars to be present and has no hardcoded credentials.


## Static website

Located in `apps/web/` and deployable on any static host or CDN.
- Data from: `apps/web/data/*` (e.g., `mpa_boundaries.geojson`, `blog_posts.json`)
- Blog posts: `apps/web/content/posts/*.md`
- Shared assets: `apps/web/static/*` (includes `wf-header.css/js`)
- Limits page links the PDF under `apps/web/docs/`

Pages
- `index.html` main map (Leaflet + optional wind overlay via Leaflet-Velocity)
- `blog.html` + `post.html` markdown-based blog
- `limits.html` size & bag limits UI
- `records.html` fetches `/api/records` and exports PDF via jsPDF
- `about.html` project info


## ML: train and predict visibility (meters)

Scripts live under `apps/ml/`. They read from MariaDB tables you maintain and emit models/predictions locally.

1) Configure DB access
```ini
# apps/ml/config.ini (not committed)
[db]
host = 127.0.0.1
port = 3306
user = your_user
password = your_password
database = wavefinder
```

2) Train
```powershell
python train_model_from_db.py "Bay Side"
```

3) Predict nowcast
```powershell
python predict_visibility_from_db.py "Bay Side"
```

Outputs
- `models/` saved pipelines (.pkl) with `.meta.json`
- `predictions/visibility_prediction_<loc>__<model>.txt`
- `data/debug_input_features_<loc>__multiwindow.csv`


## Secrets and hygiene

- Keep secrets out of git. Root `.gitignore` excludes:
	- `.env`, `.env.*`, `apps/api/.env`, `apps/ml/.env`
	- `apps/ml/config.ini`
	- ML artifacts (`*.pkl`, `*.meta.json`, `apps/ml/predictions/`, `apps/ml/data/debug_input_features_*.csv`)
- API uses only environment variables; no hardcoded DB credentials.
- Before pushing public, you can run a quick local scan for common secrets:
```powershell
git --no-pager grep -InE "(password|passwd|pwd|secret|apikey|api[_-]?key|token|bearer|authorization|client[_-]?secret|BEGIN [A-Z ]+ PRIVATE KEY|aws_access_key_id|aws_secret_access_key|DATABASE_URL|MONGODB_URI|POSTGRES_|MYSQL_|MARIADB_)"
```


## Deployment notes

- Web: host `apps/web/` on a static host/CDN (Cloudflare, Netlify, etc.). Keep only HTML in the web root; assets under `static/`, data under `data/`.
- API: deploy `apps/api/` to your Node host (Docker/VM/Service). Provide env vars securely.
- ML: run on a job/VM; keep `config.ini` off-repo and out of images. Persist `models/` and `predictions/` if needed.


## License

This repository is licensed under the GNU Affero General Public License (AGPL-3.0). See `LICENSE`.

Data sources: Open‑Meteo (Marine + Weather). Respect their terms.