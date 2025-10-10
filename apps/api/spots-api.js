/*
  SPDX-License-Identifier: AGPL-3.0-or-later
  Copyright (C) 2025 Joshua Vlantis
*/
// Wave Finder API

const express  = require('express');
const mariadb  = require('mariadb');
const app      = express();

// Allow any origin to call the API from the browser
app.use((req, res, next) => {
  const origin = req.headers.origin;
  if (origin) {
    res.setHeader('Access-Control-Allow-Origin', origin); // reflect origin dynamically
    res.setHeader('Vary', 'Origin');
    res.setHeader('Access-Control-Allow-Methods', 'GET,POST,OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
  }
  
// Allow the website to call the API from the browser
/* Removed for now and replaced with the above */
/*
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
*/

  // Advertise source (AGPL network notice convenience)
  res.setHeader(
    'Link',
    [
      '<https://github.com/JoshuaVlantis/Wave-Finder>; rel="source"',
      '<https://www.gnu.org/licenses/agpl-3.0.html>; rel="license"'
    ].join(', ')
  );

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

// Start server
app.listen(PORT, HOST, () => console.log(`WaveFinder API listening on http://${HOST}:${PORT}`));
