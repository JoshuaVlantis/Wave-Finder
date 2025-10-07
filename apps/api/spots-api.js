/*
  SPDX-License-Identifier: AGPL-3.0-or-later
  Copyright (C) 2025 Joshua Vlantis
*/
// Wave Finder API

const express  = require('express');
const mariadb  = require('mariadb');
const app      = express();

// Allow the website to call the API from the browser
app.use((req, res, next) => {
  const o = req.headers.origin;
  if (o === 'https://wavefinder.org' || o === 'https://www.wavefinder.org') {
    res.setHeader('Access-Control-Allow-Origin', o);
    res.setHeader('Vary', 'Origin');
  }
  // Advertise source (AGPL network notice convenience)
  res.setHeader('Link', ['<https://github.com/JoshuaVlantis/Wave-Finder>; rel="source"', '<https://www.gnu.org/licenses/agpl-3.0.html>; rel="license"'].join(', '));
  // Expose the Link header to browsers
  res.setHeader('Access-Control-Expose-Headers', 'Link');
  next();
});

const PORT = Number(process.env.PORT || 3001);
const HOST = '0.0.0.0';

// MariaDB connection pool (requires env vars)
const REQUIRED_ENV = ['DB_HOST', 'DB_USER', 'DB_PASS', 'DB_NAME'];
const missing = REQUIRED_ENV.filter(k => !process.env[k]);
if (missing.length) {
  console.error(`Missing required environment variables: ${missing.join(', ')}`);
  process.exit(1);
}

const pool = mariadb.createPool({
  host: process.env.DB_HOST,
  user: process.env.DB_USER,
  password: process.env.DB_PASS,
  database: process.env.DB_NAME,
  connectionLimit: Number(process.env.DB_POOL || 5)
});



// Health endpoints (no DB touch)
app.get('/health', (_req, res) => res.status(200).send('ok'));
app.head('/health', (_req, res) => res.sendStatus(200));

// GET /api/spots
app.get('/api/spots', async (req, res) => {
  let conn;
  try {
    conn = await pool.getConnection();
    const rows = await conn.query(`
      SELECT
        location_id, name, latitude, longitude, description,
        min_depth, max_depth, site_type, entry_method,
        difficulty, wildlife, hazards, img
      FROM locations
      WHERE is_active = 1
    `);
    res.json(rows);
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: 'DB error' });
  } finally {
    if (conn) conn.release();
  }
});

// GET /api/records (top 3 per species)
app.get('/api/records', async (req, res) => {
  let conn;
  try {
    conn = await pool.getConnection();
    const rows = await conn.query(`
      SELECT species, diver, weight, date
      FROM records
      ORDER BY species, weight DESC
    `);

    const grouped = {};
    for (const r of rows) {
      if (!grouped[r.species]) grouped[r.species] = [];
      if (grouped[r.species].length < 3) {
        grouped[r.species].push({
          diver:  r.diver,
          weight: `${parseFloat(r.weight).toFixed(2)} kg`,
          date:   new Date(r.date).toLocaleDateString('en-GB')
        });
      }
    }
    const out = Object.entries(grouped).map(([species, entries]) => ({ species, entries }));
    res.json(out);
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: 'DB error' });
  } finally {
    if (conn) conn.release();
  }
});

// Wind helpers
const ERDDAP = 'https://pae-paha.pacioos.hawaii.edu/erddap/griddap/ncep_global.json';
const snap05 = v => Math.round(v * 2) / 2;
const to360  = lon => (lon < 0 ? lon + 360 : lon);
const clamp  = (v, lo, hi) => Math.max(lo, Math.min(hi, v));

function current3hISO() {
  const now = new Date();
  const rhr = Math.floor(now.getUTCHours() / 3) * 3;
  const t   = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate(), rhr));
  return t.toISOString().replace(/\.\d{3}Z$/, 'Z');
}

async function fetchDataSlice(S, N, W, E, timeExpr) {
  // data variables (3-D) use time+lat+lon; TIME variable (1-D) uses time only
  const tSlice   = `[(${timeExpr})]`;
  const dataSlice= `${tSlice}[(${S}):0.5:(${N})][(${W}):0.5:(${E})]`;
  const url = `${ERDDAP}?ugrd10m${dataSlice},vgrd10m${dataSlice}`;
  const r = await fetch(encodeURI(url));
  if (!r.ok) throw new Error(`ERDDAP ${r.status}`);
  return r.json();
}

async function fetchLastTimeISO() {
  const url = `${ERDDAP}?time[(last)]`;
  const r = await fetch(url);
  if (!r.ok) throw new Error(`ERDDAP ${r.status}`);
  const j = await r.json();
  const ti = j.table.columnNames.indexOf('time');
  return new Date(j.table.rows[0][ti]).toISOString();
}

// GET /api/wind (GFS via ERDDAP)
app.get('/api/wind', async (req, res) => {
  try {
    // bounds
    const q = Object.fromEntries(Object.entries(req.query).map(([k,v]) => [k, +v]));
    if (![q.west, q.south, q.east, q.north].every(Number.isFinite)) {
      return res.status(400).json({ error: 'Invalid bounds' });
    }

    let W = snap05(q.west), E = snap05(q.east), S = snap05(q.south), N = snap05(q.north);
    if (S > N) [S, N] = [N, S];
    if (S === N) N = Math.min(S + 0.5, 90);

    // dataset lon 0..359.5; handle wrap
    let W360 = clamp(to360(W), 0, 359.5);
    let E360 = clamp(to360(E), 0, 359.5);

    const tISO = current3hISO();
    let parts, refTime = tISO;

    async function getParts(timeExpr) {
      if (W360 <= E360) {
        return [await fetchDataSlice(S, N, W360, E360, timeExpr)];
      } else {
        return [await fetchDataSlice(S, N, W360, 359.5, timeExpr),
                await fetchDataSlice(S, N, 0,    E360,  timeExpr)];
      }
    }

    try {
      parts = await getParts(tISO);
    } catch {
      parts = await getParts('last');
      refTime = await fetchLastTimeISO(); // actual model time used
    }

    // pack into Leaflet-Velocity format; emit lon in −180..180
    const remapLon = L => (L > 180 ? L - 360 : L);
    const cols = parts[0].table.columnNames;
    const latI = cols.indexOf('latitude');
    const lonI = cols.indexOf('longitude');
    const uI   = cols.indexOf('ugrd10m');
    const vI   = cols.indexOf('vgrd10m');

    const lats = [...new Set(parts[0].table.rows.map(r => r[latI]))].sort((a,b) => b - a);
    const ny = lats.length, rowOf = new Map(lats.map((v,i)=>[v,i]));

    const lonsRaw  = parts.flatMap(p => [...new Set(p.table.rows.map(r => r[lonI]))]);
    const lonsUniq = [...new Set(lonsRaw.map(remapLon))].sort((a,b) => a - b);
    const nx = lonsUniq.length, colOf = new Map(lonsUniq.map((v,i)=>[v,i]));

    const U = new Array(nx * ny).fill(null);
    const V = new Array(nx * ny).fill(null);

    for (const p of parts) {
      for (const r of p.table.rows) {
        const rr = rowOf.get(r[latI]);
        const cc = colOf.get(remapLon(r[lonI]));
        if (rr == null || cc == null) continue;
        const k = rr * nx + cc;
        U[k] = r[uI];
        V[k] = r[vI];
      }
    }

    const headerBase = {
      parameterCategory: 2,
      lo1: lonsUniq[0], la1: lats[0],
      lo2: lonsUniq[lonsUniq.length - 1],
      la2: lats[lats.length - 1],
      nx, ny,
      dx: nx > 1 ? (lonsUniq[1] - lonsUniq[0]) : 0.5,
      dy: ny > 1 ? (lats[0] - lats[1])        : 0.5,
      refTime
    };

    res.json([
      { header: { ...headerBase, parameterNumber: 2 }, data: U },
      { header: { ...headerBase, parameterNumber: 3 }, data: V }
    ]);
  } catch (e) {
    console.error('wind fetch failed:', e);
    res.status(502).json({ error: 'wind fetch failed' });
  }
});

// GET /api/wind/debug (single point check)
app.get('/api/wind/debug', async (req, res) => {
  try {
    const lat = +req.query.lat, lon = +req.query.lon;
    if (![lat, lon].every(Number.isFinite)) return res.status(400).json({ error: 'lat/lon required' });

    const S = snap05(lat), N = Math.min(S + 0.5, 90);
    let   W = snap05(lon), E = Math.min(W + 0.5, 359.5);

    // build time (rounded 3h) and fall back to last
    const tISO = current3hISO();
    const W360 = clamp(to360(W), 0, 359.5);
    const E360 = clamp(to360(E), 0, 359.5);

    let j, model_time_iso = tISO;
    try {
      j = await fetchDataSlice(S, N, W360, E360, tISO);
    } catch {
      j = await fetchDataSlice(S, N, W360, E360, 'last');
      model_time_iso = await fetchLastTimeISO();
    }

    const cols = j.table.columnNames;
    const latI = cols.indexOf('latitude'), lonI = cols.indexOf('longitude');
    const uI = cols.indexOf('ugrd10m'), vI = cols.indexOf('vgrd10m');
    const row = j.table.rows[0];

    const U = row[uI], V = row[vI];
    const speed_ms  = Math.hypot(U, V);
    const speed_kmh = speed_ms * 3.6;
    const bearing_to = (Math.atan2(U, V) * 180 / Math.PI + 360) % 360; // to-direction
    const meteo_from = (bearing_to + 180) % 360;

    res.json({
      model_time_iso,
      grid_lat: row[latI], grid_lon: row[lonI],
      U_ms: U, V_ms: V, speed_ms, speed_kmh, meteo_from_deg: meteo_from
    });
  } catch (e) {
    res.status(502).json({ error: 'debug failed' });
  }
});

// Start server
app.listen(PORT, HOST, () => console.log(`WaveFinder API listening on http://${HOST}:${PORT}`));
