# Wave Finder
[Wave Finder](https://wavefinder.org)

# Wave Finder — Local Hosting with Coolify

This guide walks you through hosting the Wave Finder website locally using Coolify, while still consuming the production API. No code changes are required.

If you prefer to use your own API instead, there’s a note at the end explaining what to change.

## Prerequisites

- A Linux machine (tested with Ubuntu/Debian)
- Sudo access

## 1) Install Docker, Git, and Coolify

Run the following commands on your machine:

```bash
sudo apt update && sudo apt upgrade -y

sudo apt install -y curl git ca-certificates

# Install Docker
curl -fsSL https://get.docker.com | sudo bash
sudo usermod -aG docker $USER

# Install Coolify
curl -fsSL https://cdn.coollabs.io/coolify/install.sh | sudo bash
```

Log out and back in (or reboot) to ensure your user is in the `docker` group.

## 2) Open Coolify

Open your browser and go to:

- http://127.0.0.1:8000

Register your account in Coolify.

## 3) Create a Project

In Coolify:

1. In the left sidebar, click “Projects” or visit http://127.0.0.1:8000/projects
2. Click “Add” and give it a name, e.g. “Wave Finder Development”
3. Open the new project

## 4) Add the Website Resource

1. Click “Add Resource”
2. Choose “Docker Image”
3. Enter the image: `nginx:alpine`
4. Click “Save”

## 5) Configure the Website Resource

In the resource settings:

- General
	- Name: `Wave Finder`
	- Description: optional
	- Remove any Coolify-managed domain (not needed for local hosting)

- Networking
	- Exposes: `80`
	- Port mapping: `18080:80`
		- This maps the container’s port 80 to your host’s port 18080 (you can choose a different host port if you want)

Click “Save”.

## 6) Add Persistent Storage

You’ll add two mounts: a file mount for Nginx configuration and a directory mount for the website files.

1) File mount (Nginx config)

- Go to “Persistent Storage” → “Add” → “File Mount”
- Path inside container: `/etc/nginx/conf.d/default.conf`
- Paste the following content:

```nginx
server {
	listen 80;
	server_name _;

	root /usr/share/nginx/web;
	index index.html;

	resolver 127.0.0.11 ipv6=off valid=10s;

	# Proxy for API (strip /api/ prefix)
	location = /api { return 301 /api/; }
	location ^~ /api/ {
		proxy_http_version 1.1;

		# HTTPS upstream + correct Host/SNI
		proxy_set_header Host api.wavefinder.org;
		proxy_ssl_server_name on;

		proxy_set_header X-Real-IP $remote_addr;
		proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
		proxy_set_header X-Forwarded-Proto $scheme;
		proxy_set_header X-Forwarded-Host $host;

		# WS/SSE
		proxy_set_header Upgrade $http_upgrade;
		proxy_set_header Connection $connection_upgrade;

		# trailing slash strips /api prefix
		proxy_pass https://api.wavefinder.org/;

		proxy_connect_timeout 5s;
		proxy_send_timeout 60s;
		proxy_read_timeout 60s;
		proxy_redirect off;
	}

	# Serve app and rewrite absolute API URLs in HTML/JS at response time
	location / {
		sub_filter_once off;
		sub_filter_types text/html application/javascript;
		sub_filter "https://api.wavefinder.org" "/api";
		try_files $uri /index.html;
	}

	# Static caching
	location ~* \.(js|css|png|jpg|jpeg|gif|svg|ico|woff2?)$ {
		expires 7d; access_log off;
	}
}

# Map for Upgrade header
map $http_upgrade $connection_upgrade {
	default upgrade;
	''      close;
}
```

This lets the container proxy API requests and rewrite absolute API URLs at serve time, so the frontend can load data without any code changes.

2) Directory mount (website files)

- Click “Add” → “Directory Mount”
- Source directory (on the host running Coolify): the path to your cloned repo’s web app. For example:
	- `/home/<your-user>/Documents/GitHub/Wave-Finder/apps/web`
- Destination directory (in the container): `/usr/share/nginx/web`

Click “Save”.

## 7) Deploy and Test

1. Scroll to the top and click “Save/Deploy” (or the Deploy button)
2. Visit your site at: http://127.0.0.1:18080

You should see the site and API-driven content loading.

## Using Your Own API (Optional)

If you want to use your own API instead of the public one:

- In the Nginx config above, change:

```nginx
proxy_pass https://api.wavefinder.org/;
```

to your API endpoint, e.g.:

```nginx
proxy_pass http://192.168.0.10:3001/;
```

We’ll add a full API and database setup section later.

## Contributing

Once you’re hosting locally, you can start making changes to the files under `apps/web/`. Refresh your browser to see updates. Pull requests are welcome.

## Troubleshooting

- Blank page or 404 when visiting the site:
	- Ensure the directory mount points to the correct local path and that it contains `index.html`.
- API not loading:
	- Confirm the file mount for `/etc/nginx/conf.d/default.conf` was added and saved.
	- Open the browser DevTools Network tab and check that requests go to `/api/...` and return 200.
	- If needed, restart the resource in Coolify to reload the Nginx config.



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
