# Licensing overview

This repository contains multiple kinds of artifacts. To make reuse clear and simple, we apply different licenses to different folders:

- Software (server, web app, ML code): AGPL-3.0-or-later
  - apps/api/**
  - apps/web/** (HTML/CSS/JS)
  - apps/ml/** (Python code)
- Content and media: Creative Commons Attribution 4.0 International (CC BY 4.0)
  - apps/web/content/posts/** (blog posts)
  - apps/web/static/** (images and other media under this repo)
  - apps/web/docs/** (documentation you authored)
- Third-party assets and services: Their original licenses/terms apply
  - Esri basemap tiles: attribution required and subject to Esri terms of use
  - Google Fonts (Outfit): SIL Open Font License 1.1 (fonts) and Apache-2.0 (stylesheet delivery)
  - Leaflet: BSD-2-Clause; Leaflet-Velocity: MIT
  - Any embedded PDFs or datasets with external provenance must keep their own license/terms.

If you contribute, please include an SPDX header at the top of source files where practical, e.g.:

- For AGPL-licensed source files:
  - SPDX-License-Identifier: AGPL-3.0-or-later
- For CC BY 4.0 content files (Markdown, etc.):
  - SPDX-License-Identifier: CC-BY-4.0

See also: LICENSE (AGPL-3.0) and NOTICE for attributions.