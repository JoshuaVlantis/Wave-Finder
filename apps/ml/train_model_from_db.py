import sys
import os
import json
import pandas as pd
import numpy as np
import joblib
import pymysql
from datetime import timedelta
from pathlib import Path
import configparser


# sklearn
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LinearRegression, Ridge, ElasticNet
from sklearn.neighbors import KNeighborsRegressor
from sklearn.ensemble import RandomForestRegressor, HistGradientBoostingRegressor
from sklearn.base import clone  # NEW: to avoid estimator reuse across windows


# Optional gradient-boosting libs (graceful if missing)
XGBRegressor = None
lgb = None
try:
    from xgboost import XGBRegressor as _XGBRegressor
    XGBRegressor = _XGBRegressor
except Exception as e:
    print(f"⚠️ Skipping XGBoost: {e}")
try:
    import lightgbm as _lgb
    lgb = _lgb
except Exception as e:
    print(f"⚠️ Skipping LightGBM: {e}")

from temporal_features import (
    extract_trend_features,
    extract_event_timing_features,
    extract_circular_trend,
    circular_mean
)

# Pipeline helpers
def pipe(estimator, scale=False):
    """Create a sklearn Pipeline with median imputation (+ optional scaling)."""
    steps = [("imputer", SimpleImputer(strategy="median"))]
    if scale:
        steps.append(("scaler", StandardScaler()))
    steps.append(("est", estimator))
    return Pipeline(steps)


def model_zoo():
    """Return a dict of candidate regressors (conditionally includes XGBoost/LightGBM)."""
    zoo = {
        "Linear":        pipe(LinearRegression(), scale=True),
        "Ridge":         pipe(Ridge(alpha=1.0, random_state=42), scale=True),
        "ElasticNet":    pipe(ElasticNet(alpha=0.01, l1_ratio=0.1, random_state=42), scale=True),
        "KNN":           pipe(KNeighborsRegressor(n_neighbors=10, weights="distance"), scale=True),
        "RandomForest":  pipe(RandomForestRegressor(n_estimators=400, random_state=42, n_jobs=-1)),
        "HGBDT":         pipe(HistGradientBoostingRegressor(learning_rate=0.06, max_depth=8, max_bins=255, random_state=42)),
    }
    if XGBRegressor is not None:
        zoo["XGBoost"] = pipe(XGBRegressor(
            n_estimators=800, max_depth=6, learning_rate=0.05,
            subsample=0.9, colsample_bytree=0.9, reg_lambda=1.0,
            tree_method="hist", random_state=42, n_estimators_per_tree=None
        ))
    if lgb is not None:
        zoo["LightGBM"] = pipe(lgb.LGBMRegressor(
            n_estimators=1400, learning_rate=0.03, subsample=0.9,
            colsample_bytree=0.9, reg_lambda=1.0, random_state=42, n_jobs=1,
            verbose=-1
        ))
    return zoo


def slugify(s: str) -> str:
    """Lowercase, keep alnum + underscore; replace spaces; good for filenames."""
    return "".join(ch for ch in s.lower() if ch.isalnum() or ch in ("_",)).replace(" ", "")


def ensure_time_index(df: pd.DataFrame) -> pd.DataFrame:
    """Sort by site_timestamp and set it as a DateTimeIndex (or coerce existing index)."""
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
    """Compute base+temporal+circular features from an already-sliced window."""
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

    # trends / timing / circular trends (use time index inside helpers)
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


def build_multiwindow_features(ocean72: pd.DataFrame, weather72: pd.DataFrame, end_time) -> dict:
    """Build feature dict with prefixes w24__*, w48__*, w72__*, using the given end_time."""
    out = {'label_timestamp': end_time}
    for hours in (24, 48, 72):
        start = end_time - timedelta(hours=hours)
        oc = ocean72.loc[start:end_time]
        we = weather72.loc[start:end_time]
        if len(oc) == 0 or len(we) == 0:
            # Create empty block (imputer will handle later)
            block = {}
        else:
            block = build_window_block(oc, we)
        pref = f"w{hours}__"
        out.update({pref + k: v for k, v in block.items()})
    return out


# Args & paths
print("📍 Checking arguments...")
if len(sys.argv) < 2:
    print("❌ Usage: python train_model_from_db.py 'Bay Side'  (or 'Wild Side')")
    sys.exit(1)
location = sys.argv[1]
print(f"📍 Training multi-window + per-window models for location: {location}")

BASE_DIR = Path(os.path.abspath(os.path.dirname(__file__)))
MODELS_DIR = BASE_DIR / "models"
MODELS_DIR.mkdir(parents=True, exist_ok=True)
safe_loc = slugify(location)

# Database
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

print("🔌 Connecting to database…")
conn = pymysql.connect(**db_config, cursorclass=pymysql.cursors.DictCursor)
cursor = conn.cursor()
print("✅ Connected.")

# Pull all labeled rows for this spot
cursor.execute("""
    SELECT site_timestamp, location, Visibility_Rating
    FROM LiveOceanData
    WHERE Visibility_Rating IS NOT NULL AND location = %s
    ORDER BY site_timestamp ASC
""", (location,))
labeled_rows = pd.DataFrame(cursor.fetchall())
print(f"🧽 Found {len(labeled_rows)} ratings for {location}")

def extract_features_for_rating(row):
    """For a single label timestamp, fetch 72h context and build windowed features."""
    end_time = pd.to_datetime(row['site_timestamp'])
    start_time = end_time - timedelta(hours=72)

    # Pull 72h of raw data once per label
    cursor.execute("""
        SELECT * FROM LiveOceanData
        WHERE site_timestamp BETWEEN %s AND %s AND location = %s
        ORDER BY site_timestamp ASC
    """, (start_time, end_time, location))
    ocean_df = pd.DataFrame(cursor.fetchall())

    cursor.execute("""
        SELECT * FROM LiveWeatherData
        WHERE site_timestamp BETWEEN %s AND %s AND location = %s
        ORDER BY site_timestamp ASC
    """, (start_time, end_time, location))
    weather_df = pd.DataFrame(cursor.fetchall())

    if ocean_df.empty or weather_df.empty:
        return None

    # Ensure time index for consistent windowing
    ocean_df = ensure_time_index(ocean_df)
    weather_df = ensure_time_index(weather_df)

    feats = build_multiwindow_features(ocean_df, weather_df, end_time)
    feats['visibility_rating'] = row['Visibility_Rating']
    return feats

print("🔍 Extracting features (multi-window 24/48/72)…")
all_features = []
for _, row in labeled_rows.iterrows():
    result = extract_features_for_rating(row)
    if result:
        all_features.append(result)

conn.close()
print("✅ DB connection closed.")

if not all_features:
    print(f"❌ No valid training samples for {location}")
    sys.exit(1)

df = pd.DataFrame(all_features)
df = df.sort_values("label_timestamp").reset_index(drop=True)
df = df.dropna(subset=["visibility_rating"])

# Column selection
drop_cols = {"label_timestamp", "visibility_rating"}
feature_cols = [c for c in df.columns if c not in drop_cols]

# Sanitize features
X_all = df[feature_cols].copy().replace([np.inf, -np.inf], np.nan)
y_all = df["visibility_rating"].astype(float).values

# Drop all-NaN or constant columns
nunique = X_all.nunique(dropna=True)
keep_cols = [c for c in X_all.columns if X_all[c].notna().any() and nunique[c] > 1]
dropped = sorted(set(X_all.columns) - set(keep_cols))
if dropped:
    print(f"🧹 Dropping {len(dropped)} non-informative columns.")
X_all = X_all[keep_cols]
feature_cols = keep_cols

# Time-aware split (chronological 80/20)
n = len(df)
cut = int(n * 0.8)
X_train, X_test = X_all.iloc[:cut], X_all.iloc[cut:]
y_train, y_test = y_all[:cut], y_all[cut:]
print(f"📊 Dataset: total={n}, train={len(X_train)}, test={len(X_test)}")
if len(X_test) == 0:
    print("⚠️ Not enough data for a holdout test. Training on all data.")
    X_train, y_train = X_all, y_all
    X_test = X_all.iloc[0:0]
    y_test = np.array([])

# Feature groups
cols_w24 = [c for c in feature_cols if c.startswith("w24__")]
cols_w48 = [c for c in feature_cols if c.startswith("w48__")]
cols_w72 = [c for c in feature_cols if c.startswith("w72__")]
cols_multi = sorted(set(cols_w24 + cols_w48 + cols_w72))

def has_cols(cols): return len(cols) >= 1

zoo = model_zoo()
summary_rows = []

# ---------- Training helpers ----------
def train_suite(cols, tag, display_suffix=""):
    """Train/evaluate/save a full model suite on a specific feature subset."""
    if not has_cols(cols):
        print(f"⚠️ Skipping {tag} models: not enough features.")
        return
    Xt_all = X_all[cols]
    Xt_tr, Xt_te = Xt_all.iloc[:cut], Xt_all.iloc[cut:]
    if len(X_test) == 0:
        Xt_tr, Xt_te = Xt_all, Xt_all.iloc[0:0]

    for name, base_model in zoo.items():
        # fresh estimator per window to avoid n_features_in_ mismatches
        model = clone(base_model)
        label = f"{name}{display_suffix}"
        print(f"\n🏋️ Training {label}…")
        print("  -> Xt_tr shape:", getattr(Xt_tr, "shape", None))
        model.fit(Xt_tr, y_train)
        # Post-fit safety check for feature count if available
        est = getattr(model, "named_steps", {}).get("est", model)
        nfi = getattr(est, "n_features_in_", None)
        if nfi is not None and nfi != Xt_tr.shape[1]:
            raise ValueError(f"{label}: fitted n_features_in_={nfi} does not match Xt_tr.shape[1]={Xt_tr.shape[1]}")

        n_te = len(Xt_te)
        if n_te > 0:
            y_pred = model.predict(Xt_te)
            mae = mean_absolute_error(y_test, y_pred)
            rmse = float(np.sqrt(mean_squared_error(y_test, y_pred)))
            r2 = r2_score(y_test, y_pred)
        else:
            mae = rmse = r2 = np.nan

        # Save artifacts
        mslug = slugify(name)
        if tag == "multi":
            model_path = MODELS_DIR / f"visibility_model_{safe_loc}__{mslug}.pkl"
            meta_path  = MODELS_DIR / f"visibility_model_{safe_loc}__{mslug}.meta.json"
            display_name = name
        else:
            model_path = MODELS_DIR / f"visibility_model_{safe_loc}__{tag}__{mslug}.pkl"
            meta_path  = MODELS_DIR / f"visibility_model_{safe_loc}__{tag}__{mslug}.meta.json"
            win = {"w24":"24h","w48":"48h","w72":"72h"}[tag]
            display_name = f"{name} ({win})"

        joblib.dump(model, model_path)
        meta = {
            "location": location,
            "model_name": name,
            "display_name": display_name,
            "window_tag": tag,
            "feature_cols": cols,
            "trained_rows": int(len(Xt_tr)),
            "test_rows": int(len(Xt_te)),
            "metrics": {
                "MAE": None if pd.isna(mae) else float(mae),
                "RMSE": None if pd.isna(rmse) else float(rmse),
                "R2": None if pd.isna(r2) else float(r2)
            }
        }
        with open(meta_path, "w") as f:
            json.dump(meta, f, indent=2, default=str)

        print(f"💾 Saved: {model_path}")
        if not pd.isna(mae):
            print(f"🎯 {display_name}  MAE={mae:.3f}  RMSE={rmse:.3f}  R²={r2:.3f}")
        else:
            print("🎯 No holdout set; metrics skipped.")

        summary_rows.append({
            "location": location,
            "model": display_name,
            "window": tag,
            "rows_train": len(Xt_tr),
            "rows_test": len(Xt_te),
            "MAE": mae, "RMSE": rmse, "R2": r2
        })

# Train: multi-window + per-window
train_suite(cols_multi, tag="multi", display_suffix="")
train_suite(cols_w24, tag="w24", display_suffix=" (24h)")
train_suite(cols_w48, tag="w48", display_suffix=" (48h)")
train_suite(cols_w72, tag="w72", display_suffix=" (72h)")

# Summary CSV
summary_df = pd.DataFrame(summary_rows)
summary_csv = MODELS_DIR / f"training_summary_{safe_loc}.csv"
summary_df.to_csv(summary_csv, index=False)

print("\n" + "★"*40)
print(f"✅ TRAINED {len(summary_df)} MODEL VARIANTS for {location}")
print(f"📄 Summary: {summary_csv}")
print("★"*40)
