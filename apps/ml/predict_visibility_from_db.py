import sys
import os
import json
import pandas as pd
import numpy as np
import joblib
import pymysql
import warnings
from datetime import datetime, timedelta
from pathlib import Path
import configparser

from temporal_features import (
    extract_trend_features,
    extract_event_timing_features,
    extract_circular_trend,
    circular_mean
)

# Quiet down noisy libraries that aren't relevant for CLI usage
warnings.filterwarnings("ignore", category=UserWarning)

# Utilities
def slugify(s: str) -> str:
    """Lowercase, keep alnum + underscore; replace spaces; good for filenames."""
    return "".join(ch for ch in s.lower() if ch.isalnum() or ch in ("_",)).replace(" ", "")


def ensure_time_index(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy indexed by DateTimeIndex (site_timestamp if present), sorted ascending."""
    if "site_timestamp" in df.columns:
        df = df.copy()
        df["site_timestamp"] = pd.to_datetime(df["site_timestamp"])
        df = df.sort_values("site_timestamp")
        df = df.set_index("site_timestamp")
    else:
        df = df.copy()
        df.index = pd.to_datetime(df.index)
        df = df.sort_index()
    return df


def build_window_block(ocean_df: pd.DataFrame, weather_df: pd.DataFrame) -> dict:
    """Compute base, temporal, and circular features for an already-sliced window."""
    features = {
        'wave_height_avg': ocean_df['wave_height'].mean(),
        'wave_height_std': ocean_df['wave_height'].std(),
        'swell_wave_height_avg': ocean_df['swell_wave_height'].mean(),
        'swell_wave_period_avg': ocean_df['swell_wave_period'].mean(),
        'wind_wave_height_avg': ocean_df['wind_wave_height'].mean(),
        'ocean_current_velocity_avg': ocean_df['ocean_current_velocity'].mean(),
        'sea_surface_temp_avg': ocean_df['sea_surface_temperature'].mean(),
        'sea_level_std': ocean_df['sea_level_height_msl'].std(),

        'wave_direction_std': ocean_df['wave_direction'].std(),
        'wave_direction_mean': circular_mean(ocean_df['wave_direction']),
        'wind_wave_direction_std': ocean_df['wind_wave_direction'].std(),
        'wind_wave_direction_mean': circular_mean(ocean_df['wind_wave_direction']),
        'wind_wave_period_avg': ocean_df['wind_wave_period'].mean(),
        'swell_wave_direction_std': ocean_df['swell_wave_direction'].std(),
        'swell_wave_direction_mean': circular_mean(ocean_df['swell_wave_direction']),
        'ocean_current_direction_std': ocean_df['ocean_current_direction'].std(),
        'ocean_current_direction_mean': circular_mean(ocean_df['ocean_current_direction']),

        'wind_speed_avg': weather_df['wind_speed_10m'].mean(),
        'wind_direction_std': weather_df['wind_direction_10m'].std(),
        'wind_direction_mean': circular_mean(weather_df['wind_direction_10m']),
        'rain_total': weather_df['rain'].sum(),
        'cloud_cover_avg': weather_df['cloud_cover'].mean(),
        'pressure_avg': weather_df['pressure_msl'].mean(),
        'temperature_avg': weather_df['temperature_2m'].mean(),
        'relative_humidity_avg': weather_df['relative_humidity_2m'].mean(),
        'wind_gusts_max': weather_df['wind_gusts_10m'].max(),
        'apparent_temperature_avg': weather_df['apparent_temperature'].mean(),
    }

    features.update(extract_trend_features(ocean_df['swell_wave_height'], 'swell_wave_height'))
    features.update(extract_trend_features(ocean_df['wave_height'], 'wave_height'))
    features.update(extract_trend_features(weather_df['wind_speed_10m'], 'wind_speed_10m'))
    features.update(extract_trend_features(weather_df['temperature_2m'], 'temperature_2m'))

    features.update(extract_event_timing_features(ocean_df['swell_wave_height'], 'swell_wave_height'))
    features.update(extract_event_timing_features(ocean_df['wave_height'], 'wave_height'))
    features.update(extract_event_timing_features(weather_df['wind_speed_10m'], 'wind_speed_10m'))
    features.update(extract_event_timing_features(weather_df['temperature_2m'], 'temperature_2m'))

    features.update(extract_circular_trend(ocean_df['wave_direction'], 'wave_direction'))
    features.update(extract_circular_trend(ocean_df['wind_wave_direction'], 'wind_wave_direction'))
    features.update(extract_circular_trend(ocean_df['swell_wave_direction'], 'swell_wave_direction'))
    features.update(extract_circular_trend(ocean_df['ocean_current_direction'], 'ocean_current_direction'))
    features.update(extract_circular_trend(weather_df['wind_direction_10m'], 'wind_direction_10m'))

    return features


def build_multiwindow_features_for_now(cursor, location):
    """Pull last 72h of data for the location and build 24/48/72h feature blocks."""
    now = datetime.now()
    start72 = now - timedelta(hours=72)

    cursor.execute("""
        SELECT * FROM LiveOceanData
        WHERE site_timestamp BETWEEN %s AND %s AND location = %s
        ORDER BY site_timestamp ASC
    """, (start72, now, location))
    ocean_df = pd.DataFrame(cursor.fetchall())

    cursor.execute("""
        SELECT * FROM LiveWeatherData
        WHERE site_timestamp BETWEEN %s AND %s AND location = %s
        ORDER BY site_timestamp ASC
    """, (start72, now, location))
    weather_df = pd.DataFrame(cursor.fetchall())

    if ocean_df.empty or weather_df.empty:
        return None, None, now

    ocean_df = ensure_time_index(ocean_df)
    weather_df = ensure_time_index(weather_df)

    out = {}
    for hours in (24, 48, 72):
        start = now - timedelta(hours=hours)
        oc = ocean_df.loc[start:now]
        we = weather_df.loc[start:now]
        if len(oc) == 0 or len(we) == 0:
            block = {}
        else:
            block = build_window_block(oc, we)
        pref = f"w{hours}__"
        out.update({pref + k: v for k, v in block.items()})

    return pd.DataFrame([out]), {"now": now}, now


def list_available_models(models_dir: Path, safe_loc: str):
    """Return {display_name: (pkl_path, meta_path)} for all saved artifacts for a spot."""
    found = {}
    for meta_path in models_dir.glob(f"visibility_model_{safe_loc}__*.meta.json"):
        mslug = meta_path.stem.split("__", 1)[1].replace(".meta", "")
        pkl_path = models_dir / f"{meta_path.stem.replace('.meta','')}.pkl"
        if pkl_path.exists():
            with open(meta_path, "r") as f:
                meta = json.load(f)
            display = meta.get("display_name") or meta.get("model_name") or mslug
            found[display] = (pkl_path, meta_path)
    return found

def write_text(path: Path, text: str):
    """Create parent dirs and write a small text file with UTF-8 encoding."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


# CLI entry
if len(sys.argv) < 2:
    print('❌ Usage: python predict_visibility_from_db.py "Wild Side"')
    sys.exit(1)

location = sys.argv[1]
SCRIPT_DIR = Path(os.path.abspath(os.path.dirname(__file__)))
DATA_DIR = SCRIPT_DIR / "data"
MODELS_DIR = SCRIPT_DIR / "models"
PRED_DIR = SCRIPT_DIR / "predictions"

safe_loc = slugify(location)
print(f"📍 Predicting visibility for: {location}")

# --- Database pull (credentials from config.ini) ---
# Always look for config.ini in the same directory as this script
CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.ini")
cfg = configparser.ConfigParser()
if not cfg.read(CONFIG_PATH):
    raise RuntimeError(f"config.ini not found at {CONFIG_PATH}")

db = cfg['db']

db_config = {
    'host': db.get('host'),
    'port': db.getint('port'),
    'user': db.get('user'),
    'password': db.get('password'),
    'database': db.get('database'),
}
conn = pymysql.connect(**db_config, cursorclass=pymysql.cursors.DictCursor)
cursor = conn.cursor()

features_df_full, meta_time, now = build_multiwindow_features_for_now(cursor, location)
conn.close()

if features_df_full is None or features_df_full.empty:
    print("⚠️ Not enough data to predict (need at least some rows in last 72h)." )
    sys.exit(0)

# Persist the feature vector used (for debugging/inspection)
DATA_DIR.mkdir(parents=True, exist_ok=True)
features_df_full.to_csv(DATA_DIR / f"debug_input_features_{safe_loc}__multiwindow.csv", index=False)

# --- Decide which models to run ---
available = list_available_models(MODELS_DIR, safe_loc)
if not available:
    print(f"❌ No trained models found for {location} in {MODELS_DIR}")
    sys.exit(1)

run_models = available  # Always run all available models for the location

# --- Run predictions and write outputs ---
PRED_DIR.mkdir(parents=True, exist_ok=True)


# Collect predictions in a dictionary
predictions = {}
for name, (pkl_path, meta_path) in sorted(run_models.items()):
    with open(meta_path, "r") as f:
        meta = json.load(f)
    feat_cols = meta["feature_cols"]
    display = meta.get("display_name", name)

    # Align features to training schema
    X = features_df_full.copy()
    for col in feat_cols:
        if col not in X.columns:
            X[col] = np.nan
    X = X[feat_cols]

    model = joblib.load(pkl_path)
    pred = float(model.predict(X)[0])

    base_slug = slugify(display)
    write_text(PRED_DIR / f"visibility_prediction_{safe_loc}__{base_slug}.txt", f"{pred:.2f}")
    predictions[display] = pred

print("\nAll predictions:")
for model_name, pred_value in predictions.items():
    print(f"{model_name}: {pred_value:.2f}")

print("\n" + "★"*40)
print(f" FINAL VISIBILITY for {location.upper()} for ALL MODELS (combined + per-window) written to predictions/")
print("★"*40)

# Write all predictions to database for logging
try:
    conn = pymysql.connect(**db_config, cursorclass=pymysql.cursors.DictCursor)
    cursor = conn.cursor()


    # Insert all predictions into the database
    for model_name in predictions:
        pred_value = predictions[model_name]
        
        cursor.execute(
            "INSERT INTO visibility_predictions_dev (area, prediction, model_name) VALUES (%s, %s, %s)",
            (location, pred_value, model_name)
        )

    conn.commit()
    print("✅ Predictions successfully written to the database.")
except Exception as e:
    print(f"❌ Failed to write predictions to the database: {e}")