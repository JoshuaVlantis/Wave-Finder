# WaveFinder – Ocean Visibility Prediction (Meters)

Predict **underwater visibility (in meters)** for spearfishing/diving using open ocean + weather data, engineered temporal features, and a suite of regression models. The system trains *multiple models and multiple time‑window variants*, evaluates them on a chronological hold‑out set, and saves both the artifacts and a summary so you can pick what performs best at your spot.

> **Key points**
> - **Target**: `Visibility_Rating` in **meters** (e.g., “8” means ~8 m visibility). No star/ordinal scales.
> - **Sources**: Open‑Meteo ([Marine](https://open-meteo.com/en/docs/marine-weather-api) + [Weather](https://open-meteo.com/en/docs)) → stored in **MariaDB**.
> - **Features**: windowed aggregates (24/48/72 h), short‑term trends, event‑timing features, directional (circular) statistics.
> - **Models**: Linear/Ridge/ElasticNet/KNN/RandomForest/HGBDT (+ XGBoost/LightGBM if installed).
> - **Scripts**: `train_model_from_db.py` (train & compare) and `predict_visibility_from_db.py` (nowcast).


---

## 1) Data flow & sources

### 1.1 Ocean (Marine) data
Data like `wave_height`, `swell_wave_height/period/direction`, `wind_wave_*`, `sea_surface_temperature`, `sea_level_height_msl`, `ocean_current_direction/velocity`, etc., are fetched from Open‑Meteo’s Marine API and written to `LiveOceanData` in MariaDB.

**Example query (for illustration only):**
```
https://marine-api.open-meteo.com/v1/marine?latitude=-33.93366864887999&longitude=25.796067117552017&current=wave_height,wave_direction,wave_period,wind_wave_height,wind_wave_direction,wind_wave_period,wind_wave_peak_period,swell_wave_peak_period,swell_wave_period,swell_wave_direction,swell_wave_height,sea_surface_temperature,sea_level_height_msl,ocean_current_direction,ocean_current_velocity&timezone=Africa%2FCairo&past_days=14&forecast_days=1
```

### 1.2 Weather (atmospheric) data
Atmospheric variables such as `wind_speed_10m`, `wind_direction_10m`, `temperature_2m`, `pressure_msl`, `cloud_cover`, `rain`, `wind_gusts_10m`, etc., are fetched from Open‑Meteo’s Weather API and written to `LiveWeatherData`.

**Example query (for illustration only):**
```
https://api.open-meteo.com/v1/forecast?latitude=-34.10481122642272&longitude=25.61881774371224&current=temperature_2m,precipitation,weather_code,wind_speed_10m,wind_direction_10m,cloud_cover,rain,apparent_temperature,showers,pressure_msl,wind_gusts_10m,relative_humidity_2m,surface_pressure,snowfall,is_day&timezone=Africa%2FCairo&past_days=14&forecast_days=1
```

> Data is sourced from **https://open-meteo.com**. You control the collection cadence and DB writing (outside this repo). This project **reads** from MariaDB for training/prediction.


---

## 2) Database expectations (MariaDB)

Two tables are expected:

- **`LiveOceanData`**
  - `site_timestamp` (datetime)
  - `location` (text)
  - `Visibility_Rating` (float, meters) — **label**, present only on rows that have a known visibility at that time
  - Ocean columns used by features:  
    `wave_height`, `wave_direction`, `wave_period`,  
    `wind_wave_height`, `wind_wave_direction`, `wind_wave_period`,  
    `swell_wave_height`, `swell_wave_direction`, `swell_wave_period`,  
    `sea_surface_temperature`, `sea_level_height_msl`,  
    `ocean_current_direction`, `ocean_current_velocity`

- **`LiveWeatherData`**
  - `site_timestamp` (datetime)
  - `location` (text)
  - Weather columns used by features:  
    `wind_speed_10m`, `wind_direction_10m`, `rain`, `cloud_cover`, `pressure_msl`,  
    `temperature_2m`, `relative_humidity_2m`, `wind_gusts_10m`, `apparent_temperature`

> **Timestamps:** scripts assume rows can be filtered by `site_timestamp` and that a single `location` string (e.g., “Bay Side”) is consistent across both tables.


---

## 3) Project layout

```
.
├── models/                         # Saved .pkl models and .meta.json descriptors
├── predictions/                    # Latest predictions (txts) per model
├── data/
│   └── debug_input_features_*.csv  # Feature vector used for last prediction
├── temporal_features.py            # Feature-engineering helpers
├── train_model_from_db.py          # Train/evaluate/save models
├── predict_visibility_from_db.py   # Build features for 'now' and predict
└── config.ini                      # DB credentials (not committed)
```

**`config.ini`** (keep out of git; add to `.gitignore`):
```ini
[db]
host = 127.0.0.1
port = 3306
user = your_user
password = your_password
database = wavefinder
```


---

## 4) Installation

```bash
python -m venv .venv
# Windows PowerShell may require: Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
source .venv/bin/activate   # or .venv\Scripts\activate on Windows
pip install -U pip
pip install -r requirements.txt  # create one with the packages below
```

**Core packages**
- `pandas`, `numpy`, `pymysql`, `joblib`
- `scikit-learn`

**Optional**
- `xgboost` (adds the XGBoost model)
- `lightgbm` (adds the LightGBM model)
- `shap` (optional explanations during prediction; best‑effort text output)


---

## 5) Feature engineering (how we quantify “conditions moving”)

For each **label timestamp** (during training) or **now** (during prediction), we create **three time windows** ending at that time: **24 h**, **48 h**, and **72 h**. For each window we compute:

1. **Base aggregates** (per variable)
   - e.g., mean, std, max for
     - Ocean: `wave_height`, `swell_wave_height`, `swell_wave_period`, `wind_wave_height`, `ocean_current_velocity`, `sea_surface_temperature`, `sea_level_height_msl` (mean/std)
     - Directions: keep **circular mean** (see below) + linear std for `wave_direction`, `wind_wave_direction`, `swell_wave_direction`, `ocean_current_direction`
     - Weather: `wind_speed_10m` (mean), `wind_direction_10m` (circular mean & std), `rain` (sum), `cloud_cover` (mean), `pressure_msl` (mean), `temperature_2m` (mean), `relative_humidity_2m` (mean), `wind_gusts_10m` (max), `apparent_temperature` (mean)

2. **Short‑term trends** (how it’s moving)
   - Linear **slope per hour** over the last 24 h for key drivers, via simple `polyfit` with time as X:
     - `swell_wave_height_slope_24h`
     - `wave_height_slope_24h`
     - `wind_speed_10m_slope_24h`
     - `temperature_2m_slope_24h`
   - Also record last value and mean over 24 h (e.g., `*_last`, `*_mean_24h`).

3. **Event‑timing features** (how long since extremes; time above/below “typical”)
   - **Hours since last max/min** in the last 24 h (e.g., `wave_height_hrs_since_max_24h`)
   - **Hours above/below mean** in the last 24 h, approximated by counting samples relative to the median sampling interval.

4. **Circular (directional) statistics**
   - For directions (0–360°), we compute **circular means** using vector averaging (unit complex numbers), which avoids wrap‑around errors (e.g., mean of 350° and 10° becomes 0°, not 180°). We also keep a naive linear std for continuity with some models.

All of the above are computed **separately for each window (24/48/72 h)** and prefixed as `w24__*`, `w48__*`, `w72__*`. This gives models a way to see short, medium, and slightly longer context simultaneously, which often matters for visibility (e.g., a spike in swell that started 36 h ago vs. one still ramping over the last 12 h).

> Internals live in `temporal_features.py` (helpers like `extract_trend_features`, `extract_event_timing_features`, `extract_circular_trend`, and `circular_mean`).


---

## 6) Training: many models, many windows

Run:
```bash
python train_model_from_db.py "Bay Side"
# or "Wild Side", etc. (must match your DB 'location' values)
```

What happens:
1. **Fetch labels:** all `LiveOceanData` rows for the location where `Visibility_Rating` (meters) is not null.
2. **For each labeled timestamp:** pull the **previous 72 h** from both tables, build the **w24/w48/w72** feature blocks, attach the target visibility in meters.
3. **Sanitize features:** drop all‑NaN/constant columns; impute missing values later inside pipelines.
4. **Time‑aware split:** chronological **80/20** train/test (to avoid leakage from the future).
5. **Model zoo training** on:
   - **Multi‑window union** (all w24, w48, w72 columns together)
   - **Per‑window subsets** (w24 only, w48 only, w72 only)
6. **Candidates** (conditionally added if available):
   - Linear, Ridge, ElasticNet, KNN
   - RandomForest, HistGradientBoosting
   - XGBoost, LightGBM (if the packages are installed)
7. **Metrics saved to JSON and a CSV summary**: MAE, RMSE, R² for the hold‑out set.  
   Artifacts go to `models/` as `.pkl` + `.meta.json` with the exact feature list used.

**How to pick the “best” model**
- Prefer the lowest **MAE** (meters) on the hold‑out set for your location. RMSE and R² are also reported.
- Compare **multi‑window** vs **per‑window** variants — sometimes a focused 24 h model wins, other times the full multi‑window context is best.
- Retrain occasionally as more labeled dives accumulate.


---

## 7) Prediction (nowcast)

Run:
```bash
python predict_visibility_from_db.py "Bay Side"
# Optionally restrict to a specific saved model name:
python predict_visibility_from_db.py "Bay Side" "RandomForest (24h)"
```

What happens:
1. **Build features for “now”:** pull last **72 h** from `LiveOceanData` and `LiveWeatherData`, then compute the same w24/w48/w72 blocks used in training.
2. **Load model(s)** from `models/`. If you don’t pass a specific name, **all** saved models for the spot are run.
3. **Outputs** (per model) written to `predictions/`:
   - `visibility_prediction_<loc>__<model>.txt` — predicted visibility in **meters** (float)
   - `visibility_confidence_<loc>__<model>.txt` — a **heuristic confidence** for tree ensembles (based on estimator agreement); “N/A” for others
   - `visibility_explanation_<loc>__<model>.txt` — SHAP‑style top features (if `shap` is installed), otherwise a short note
4. A copy of the **exact feature vector** used is saved under `data/debug_input_features_<loc>__multiwindow.csv` for audit/debug.


---

## 8) Configuration, secrets, and git hygiene

- Put DB creds in `config.ini` (see §3) and make sure it’s **git‑ignored**:
  ```gitignore
  config.ini
  *.pkl
  *.meta.json
  /predictions/
  /data/debug_input_features_*.csv
  ```
- Production tip: use deployment‑specific `config.ini` files (or env‑templated files) and keep credentials out of source control.


---

## 9) Interpreting the model

- **MAE in meters** is directly actionable: if MAE ≈ 1.5 on hold‑out, typical error is ~1.5 m for that spot.
- **Directional features** account for circular wrap‑around (e.g., 359° ~ 1°).
- **Trend & timing** features capture whether swell/wind/temperature are **rising/falling**, time since last extremes, and how persistently conditions stayed above/below their 24 h mean.
- **Confidence** (tree ensembles only) is a simple spread‑based heuristic — use it as a soft indicator, not a guarantee.


---

## 10) Practical tips

- **Consistent “location” strings** across both tables are crucial.
- **Label density** matters: more labeled timestamps → better generalization, more robust model selection.
- If you change or add variables in DB, retrain so the feature schema and models stay aligned.
- For production, consider scheduling:
  - Hourly data ingestion into DB (external to this repo)
  - Nightly `train_model_from_db.py` if you’ve added fresh labels
  - Hourly `predict_visibility_from_db.py` for your live tile/app


---

## 11) Roadmap ideas

- Add shoreline‑relative **onshore/offshore components** and **tide stage** (helpers already exist in `temporal_features.py` but are not enabled in the current training blocks).
- Cross‑validation with time‑series splits (in addition to the single 80/20 split).
- Per‑model hyper‑parameter searches.
- Quantile regression for predictive intervals (P10/P50/P90 meters).

---

## 12) License & attribution

- Weather and marine data are provided by **Open‑Meteo** — see their terms.  
- This repository’s code is under GNU AFFERO GENERAL PUBLIC LICENSE
