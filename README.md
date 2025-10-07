<p align="center">
  <img src="https://wavefinder.org/Images/LogoName.png" alt="Wave Finder banner" width="100" />
</p>

<h1 align="center">Wave Finder</h1>

<p align="center">
  Clean, fast tools for South African marine recreation — maps, wind overlays, MPAs, regs, records, and visibility ML.
  <br />
  <a href="https://wavefinder.org"><strong>wavefinder.org</strong></a>
</p>

<p align="center">
  <a href="https://wavefinder.org"><img alt="Website" src="https://img.shields.io/badge/website-live-2ea043?logo=google-chrome" /></a>
  <a href="https://github.com/JoshuaVlantis/Wave-Finder/blob/main/LICENSE"><img alt="License" src="https://img.shields.io/badge/AGPL-3.0--or--later-0a7ea4" /></a>
  <a href="apps/web/content/posts/LICENSE"><img alt="Content License" src="https://img.shields.io/badge/Content-CC%20BY%204.0-7a5ea7" /></a>
  <img alt="Node" src="https://img.shields.io/badge/Node-%E2%89%A518-43853d?logo=node.js&logoColor=white" />
  <img alt="Python" src="https://img.shields.io/badge/Python-%E2%89%A53.10-3670A0?logo=python&logoColor=white" />
  <img alt="MariaDB" src="https://img.shields.io/badge/MariaDB-supported-003545?logo=mariadb" />
  <a href="https://github.com/JoshuaVlantis/Wave-Finder/issues"><img alt="PRs Welcome" src="https://img.shields.io/badge/PRs-welcome-ff9800" /></a>
</p>

## Table of contents

- 🚀 Features
- 🌐 Live + repo layout
- 🗺️ Web app
- 🤖 ML: docs coming soon
- ☁️ Deploy locally (Coolify)
- 📄 License & data sources

## 🚀 Features

- Static web: Leaflet map, wind overlay (Leaflet‑Velocity), MPA outlines, blog, size & bag limits, records
- API: Express + MariaDB for spots, records, and wind proxy
- ML: Python feature engineering + model zoo to predict underwater visibility (m)

## 🌐 Live + repo layout

- Live site: https://wavefinder.org
- Source repo: https://github.com/JoshuaVlantis/Wave-Finder

Monorepo layout
```
apps/
  api/   # Express API (MariaDB-backed)
  web/   # Static site (any CDN/static host)
  ml/    # Training + prediction utilities
LICENSES.md, NOTICE, LICENSE
```

## 🗺️ Web app

Best‑supported: run via Docker with Coolify (see [Deploy locally (Coolify)](https://github.com/JoshuaVlantis/Wave-Finder?tab=readme-ov-file#%EF%B8%8F-deploy-locally-coolify) below).

You can also deploy the static site directly from `apps/web/` on any CDN/static host, but official docs currently cover Coolify.

Contents of the web app:
- Data: `apps/web/data/*` (e.g., `mpa_boundaries.geojson`, `blog_posts.json`)
- Blog: `apps/web/content/posts/*.md`
- Assets: `apps/web/static/*` (shared CSS/JS/images/fonts)
- Pages: `index.html`, `blog.html`, `post.html`, `about.html`, `limits.html`, `records.html`

> Tip: The UI includes a “Source (AGPL)” link for network‑use attribution.

## ☁️ Deploy locally (Coolify)

Run the website locally via Nginx with zero code changes while proxying the production API.

<details>
<summary>Show Coolify guide</summary>

### Prerequisites

- A Linux machine (tested with Ubuntu/Debian)
- Sudo access

### 1) Install Docker, Git, and Coolify

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

### 2) Open Coolify

Open your browser and go to:

- http://127.0.0.1:8000

Register your account in Coolify.

### 3) Clone the repository

Clone the code locally so you can mount the web app directory into Nginx later.

```bash
cd ~
git clone https://github.com/JoshuaVlantis/Wave-Finder.git
# or, if you forked it first:
# git clone https://github.com/<your-gh-username>/Wave-Finder.git
```

You’ll use this path in step 7 (Persistent Storage), for example:
`/home/<your-user>/Wave-Finder/apps/web`

### 4) Create a Project

In Coolify:

1. In the left sidebar, click “Projects” or visit http://127.0.0.1:8000/projects
2. Click “Add” and give it a name, e.g. “Wave Finder Development”
3. Open the new project

### 5) Add the Website Resource

1. Click “Add Resource”
2. Choose “Docker Image”
3. Enter the image: `nginx:alpine`
4. Click “Save`

### 6) Configure the Website Resource

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

### 7) Add Persistent Storage

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

### 8) Deploy and Test

1. Scroll to the top and click “Save/Deploy” (or the Deploy button)
2. Visit your site at: http://127.0.0.1:18080

You should see the site and API-driven content loading.

### Using Your Own API (Optional)

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

### Contributing

Once you’re hosting locally, you can start making changes to the files under `apps/web/`. Refresh your browser to see updates. Pull requests are welcome.

### Troubleshooting

- Blank page or 404 when visiting the site:
  - Ensure the directory mount points to the correct local path and that it contains `index.html`.
- API not loading:
  - Confirm the file mount for `/etc/nginx/conf.d/default.conf` was added and saved.
  - Open the browser DevTools Network tab and check that requests go to `/api/...` and return 200.
  - If needed, restart the resource in Coolify to reload the Nginx config.

</details>

## 🤖 API: docs coming soon

API docs are being prepared. Code lives under `apps/api/`.

## 🤖 ML: docs coming soon

Training and nowcast docs are being prepared. Code lives under `apps/ml/`.

## 📄 License & data sources

- Software (server, web, ML): AGPL‑3.0‑or‑later. See `LICENSE`.
- Content/media/data (blog, images, authored docs, data): CC BY 4.0.
  - See LICENSE files in `apps/web/content/posts/`, `apps/web/data/`, `apps/web/static/`, `apps/web/docs/`.
- Third‑party assets/services retain their own terms — see `NOTICE`.
- See also `LICENSES.md` for a folder‑by‑folder map.

Data sources: Open‑Meteo (Marine + Weather). Please respect their terms.
