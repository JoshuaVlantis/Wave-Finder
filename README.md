<p align="center">
  <img src="apps/web/static/og-image.jpg" alt="Wave Finder banner" width="820" />
</p>

<h1 align="center">Wave Finder</h1>

<p align="center">
  Clean, fast tools for South African marine recreation — maps, wind overlays, MPAs, regs, records, and visibility ML.
  <br />
  <a href="https://wavefinder.org"><strong>wavefinder.org »</strong></a>
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
- ️ Web app
- 🤖 ML: docs coming soon
- 🧰 Dev tips & hygiene
- ☁️ Deploy locally (Coolify)
- 📄 License & data sources

## 🚀 Features

- Static web: Leaflet map, wind overlay (Leaflet‑Velocity), MPA outlines, blog, size & bag limits, records
- API: Express + MariaDB for spots, records, and wind proxy
- ML: Python feature engineering + model zoo to predict underwater visibility (m)

## 🌐 Live + repo layout

- Live site: https://wavefinder.org
- Source map: https://github.com/JoshuaVlantis/Wave-Finder

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

Prereqs: Linux (Ubuntu/Debian), sudo.

1) Install Docker, Git, Coolify

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y curl git ca-certificates
curl -fsSL https://get.docker.com | sudo bash
sudo usermod -aG docker $USER
curl -fsSL https://cdn.coollabs.io/coolify/install.sh | sudo bash
```

2) Fork + clone this repo

```bash
git clone https://github.com/<your-gh-username>/Wave-Finder.git
cd Wave-Finder
```

3) In Coolify: create a Project → Add Resource → Docker Image `nginx:alpine`

4) Networking: expose `80`, map host `18080:80`

5) Storage: add file mount `/etc/nginx/conf.d/default.conf` with this config:

```nginx
server {
  listen 80;
  server_name _;
  root /usr/share/nginx/web;
  index index.html;
  resolver 127.0.0.11 ipv6=off valid=10s;

  location = /api { return 301 /api/; }
  location ^~ /api/ {
    proxy_http_version 1.1;
    proxy_set_header Host api.wavefinder.org;
    proxy_ssl_server_name on;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-Host $host;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection $connection_upgrade;
    proxy_pass https://api.wavefinder.org/;
    proxy_connect_timeout 5s; proxy_send_timeout 60s; proxy_read_timeout 60s; proxy_redirect off;
  }

  location / {
    sub_filter_once off;
    sub_filter_types text/html application/javascript;
    sub_filter "https://api.wavefinder.org" "/api";
    try_files $uri /index.html;
  }

  location ~* \.(js|css|png|jpg|jpeg|gif|svg|ico|woff2?)$ { expires 7d; access_log off; }
}

map $http_upgrade $connection_upgrade { default upgrade; '' close; }
```

6) Storage: add directory mount → host path to `apps/web` → container `/usr/share/nginx/web`

7) Deploy → open http://127.0.0.1:18080

Use your own API by changing `proxy_pass` to your API origin.

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
