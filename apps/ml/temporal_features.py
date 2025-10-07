# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2025 Joshua Vlantis

import math
from typing import Dict, List, Optional

import numpy as np
import pandas as pd


# ---------- Datetime / index helpers ----------
def _ensure_time_index(s: pd.Series) -> pd.Series:
    """Ensure a time-sorted DateTimeIndex (dropping NaT-indexed rows)."""
    s = s.copy()
    if not isinstance(s.index, pd.DatetimeIndex):
        s.index = pd.to_datetime(s.index, errors="coerce")
    if s.index.hasnans:
        s = s[~s.index.isna()]
    return s.sort_index()


def _hours_between(t1: pd.Timestamp, t2: pd.Timestamp) -> float:
    """Return (t1 - t2) in hours."""
    return float((pd.Timestamp(t1) - pd.Timestamp(t2)) / pd.Timedelta(hours=1))


def _median_dt_hours(s: pd.Series) -> float:
    """Median sampling interval in hours for a time-indexed series; fallback 1.0h."""
    s = _ensure_time_index(s)
    if len(s) < 2:
        return 1.0
    diffs = s.index.to_series().diff().dropna()
    if diffs.empty:
        return 1.0
    return float(diffs.median() / pd.Timedelta(hours=1))


# ---------- Circular helpers ----------
def _to_rad(deg: pd.Series) -> np.ndarray:
    return np.deg2rad(deg.astype(float).values)


def circular_mean(degrees: pd.Series) -> float:
    """Circular mean of angles in degrees, NaN-safe (range 0..360)."""
    if degrees is None or len(degrees) == 0:
        return np.nan
    arr = degrees.astype(float).to_numpy(dtype=float)
    arr = arr[~np.isnan(arr)]
    if arr.size == 0:
        return np.nan
    vec = np.exp(1j * np.deg2rad(arr))
    mean_angle = np.angle(np.nanmean(vec))
    return float(np.rad2deg(mean_angle)) % 360.0


# ---------- Trend / event features (24h) ----------
def _slope_per_hour(series: pd.Series) -> float:
    """Linear slope (units/hour) via polyfit using the series timestamp index."""
    s = _ensure_time_index(series).dropna()
    if s.size < 3:
        return np.nan
    t0 = s.index[0]
    x = ((s.index - t0) / pd.Timedelta(hours=1)).to_numpy(dtype=float)
    try:
        m, b = np.polyfit(x, s.values.astype(float), 1)
        return float(m)
    except Exception:
        return np.nan


def extract_trend_features(series: pd.Series, name: str) -> Dict[str, float]:
    """Basic 24h trend descriptors: slope/hour, last value, and mean."""
    out: Dict[str, float] = {}
    s = _ensure_time_index(series).dropna()
    if s.size == 0:
        out[f"{name}_slope_24h"] = np.nan
        out[f"{name}_last"] = np.nan
        out[f"{name}_mean_24h"] = np.nan
        return out

    out[f"{name}_slope_24h"] = _slope_per_hour(s)
    out[f"{name}_last"] = float(s.iloc[-1])
    out[f"{name}_mean_24h"] = float(s.mean())
    return out


def extract_event_timing_features(series: pd.Series, name: str) -> Dict[str, float]:
    """
    Hours since last max/min in the 24h window and duration above/below the mean.
    """
    out: Dict[str, float] = {}
    s = _ensure_time_index(series).dropna()
    if s.size < 2:
        out[f"{name}_hrs_since_max_24h"] = np.nan
        out[f"{name}_hrs_since_min_24h"] = np.nan
        out[f"{name}_hrs_above_mean_24h"] = np.nan
        out[f"{name}_hrs_below_mean_24h"] = np.nan
        return out

    mean_val = float(s.mean())
    idx_max = s.idxmax()
    idx_min = s.idxmin()
    end_t = s.index.max()

    out[f"{name}_hrs_since_max_24h"] = _hours_between(end_t, idx_max)
    out[f"{name}_hrs_since_min_24h"] = _hours_between(end_t, idx_min)

    # Consecutive-sample durations above/below mean (approximate via median dt)
    dt_hours = _median_dt_hours(s)
    above = (s >= mean_val).astype(int)
    below = 1 - above
    out[f"{name}_hrs_above_mean_24h"] = float(above.sum() * dt_hours)
    out[f"{name}_hrs_below_mean_24h"] = float(below.sum() * dt_hours)
    return out


def extract_circular_trend(series_deg: pd.Series, name: str) -> Dict[str, float]:
    """24h circular mean (deg) and naive std (linear) for continuity/compatibility."""
    out: Dict[str, float] = {}
    s = _ensure_time_index(series_deg).dropna()
    if s.size == 0:
        out[f"{name}_circ_mean_24h"] = np.nan
        out[f"{name}_std_24h"] = np.nan
        return out
    out[f"{name}_circ_mean_24h"] = circular_mean(s)
    out[f"{name}_std_24h"] = float(s.std())
    return out


# ---------- Multi-window aggregation (24/48/72h) ----------
def _window_idx(df: pd.DataFrame, end_time: pd.Timestamp, hours: int) -> pd.Index:
    if not isinstance(df.index, pd.DatetimeIndex):
        df = df.copy()
        df.index = pd.to_datetime(df.index, errors="coerce")
        df = df[~df.index.isna()]
    df = df.sort_index()
    start = pd.Timestamp(end_time) - pd.Timedelta(hours=hours)
    return df.index[(df.index > start) & (df.index <= pd.Timestamp(end_time))]


def _nanmean(series: pd.Series) -> float:
    return float(np.nanmean(series.values)) if series.size else np.nan


def _nanstd(series: pd.Series) -> float:
    return float(np.nanstd(series.values)) if series.size else np.nan


def _nanmax(series: pd.Series) -> float:
    return float(np.nanmax(series.values)) if series.size else np.nan


def _nanmin(series: pd.Series) -> float:
    return float(np.nanmin(series.values)) if series.size else np.nan


def _sea_level_slope_per_hour(df: pd.DataFrame, end_time: pd.Timestamp, hours: int) -> float:
    """Slope of sea level height over a window (units/hour)."""
    if "sea_level_height_msl" not in df.columns:
        return np.nan
    idx = _window_idx(df, end_time, hours)
    s = df.loc[idx, "sea_level_height_msl"].dropna()
    if s.size < 3:
        return np.nan
    return _slope_per_hour(s)


def _tide_stage_sign(df: pd.DataFrame, end_time: pd.Timestamp, hours: int = 3) -> float:
    """Short-term tide stage near label time: +1 rising, -1 falling, 0 flat/unknown."""
    if "sea_level_height_msl" not in df.columns:
        return np.nan
    idx = _window_idx(df, end_time, hours)
    s = df.loc[idx, "sea_level_height_msl"].dropna()
    if s.size < 3:
        return np.nan
    slope = _slope_per_hour(s)
    if np.isnan(slope) or abs(slope) < 1e-6:
        return 0.0
    return 1.0 if slope > 0 else -1.0


def _cmean(series_deg: pd.Series) -> float:
    return circular_mean(series_deg)


def _onshore_mean(mag: pd.Series, dir_deg: pd.Series, shore_deg: Optional[float]) -> float:
    """Average onshore component: mean(magnitude * cos(direction - shoreline azimuth))."""
    if shore_deg is None or mag is None or dir_deg is None:
        return np.nan
    m = mag.astype(float).to_numpy()
    d = dir_deg.astype(float).to_numpy()
    mask = ~np.isnan(m) & ~np.isnan(d)
    if mask.sum() == 0:
        return np.nan
    ang = np.deg2rad(d[mask] - float(shore_deg))
    comp = m[mask] * np.cos(ang)
    return float(np.nanmean(comp))


def _aggregate_windowed_features(
    ocean_df: pd.DataFrame,
    weather_df: pd.DataFrame,
    end_time: pd.Timestamp,
    windows: List[int],
    shore_deg: Optional[float],
) -> Dict[str, float]:
    """Compute multi-window (24/48/72h) aggregates and onshore components."""
    out: Dict[str, float] = {}

    for W in windows:
        # Slice to window
        o_idx = _window_idx(ocean_df, end_time, W)
        w_idx = _window_idx(weather_df, end_time, W)
        o = ocean_df.loc[o_idx]
        w = weather_df.loc[w_idx]

        suffix = f"_{W}h"

        # --- Ocean base ---
        for (col, name, fn) in [
            ("wave_height", "wave_height_avg", _nanmean),
            ("wave_height", "wave_height_std", _nanstd),
            ("swell_wave_height", "swell_wave_height_avg", _nanmean),
            ("swell_wave_period", "swell_wave_period_avg", _nanmean),
            ("wind_wave_height", "wind_wave_height_avg", _nanmean),
            ("ocean_current_velocity", "ocean_current_velocity_avg", _nanmean),
            ("sea_surface_temperature", "sea_surface_temp_avg", _nanmean),
            ("sea_level_height_msl", "sea_level_mean", _nanmean),
            ("sea_level_height_msl", "sea_level_std", _nanstd),
        ]:
            out[name + suffix] = fn(o[col]) if col in o.columns else np.nan

        # Tide rate-of-change
        out["sea_level_roc_per_hr" + suffix] = _sea_level_slope_per_hour(ocean_df, end_time, W)

        # --- Directions (circular mean + naive std) ---
        for (col, base) in [
            ("wave_direction", "wave_direction"),
            ("wind_wave_direction", "wind_wave_direction"),
            ("swell_wave_direction", "swell_wave_direction"),
            ("ocean_current_direction", "ocean_current_direction"),
        ]:
            if col in o.columns and o[col].size:
                out[f"{base}_mean" + suffix] = _cmean(o[col])
                out[f"{base}_std" + suffix] = _nanstd(o[col])
            else:
                out[f"{base}_mean" + suffix] = np.nan
                out[f"{base}_std" + suffix] = np.nan

        # --- Weather ---
        for (col, name, fn) in [
            ("wind_speed_10m", "wind_speed_avg", _nanmean),
            ("wind_direction_10m", "wind_direction_std", _nanstd),
            ("wind_direction_10m", "wind_direction_mean", _cmean),
            ("rain", "rain_total", lambda s: float(np.nansum(s.values)) if s.size else np.nan),
            ("cloud_cover", "cloud_cover_avg", _nanmean),
            ("pressure_msl", "pressure_avg", _nanmean),
            ("temperature_2m", "temperature_avg", _nanmean),
            ("relative_humidity_2m", "relative_humidity_avg", _nanmean),
            ("wind_gusts_10m", "wind_gusts_max", _nanmax),
            ("apparent_temperature", "apparent_temperature_avg", _nanmean),
        ]:
            out[name + suffix] = fn(w[col]) if col in w.columns else np.nan

        # --- Onshore components (requires shoreline azimuth) ---
        out["onshore_wind_speed_avg" + suffix] = _onshore_mean(
            w["wind_speed_10m"] if "wind_speed_10m" in w else None,
            w["wind_direction_10m"] if "wind_direction_10m" in w else None,
            shore_deg,
        )
        out["onshore_wave_height_avg" + suffix] = _onshore_mean(
            o["wave_height"] if "wave_height" in o else None,
            o["wave_direction"] if "wave_direction" in o else None,
            shore_deg,
        )
        out["onshore_swell_height_avg" + suffix] = _onshore_mean(
            o["swell_wave_height"] if "swell_wave_height" in o else None,
            o["swell_wave_direction"] if "swell_wave_direction" in o else None,
            shore_deg,
        )
        out["onshore_wind_wave_height_avg" + suffix] = _onshore_mean(
            o["wind_wave_height"] if "wind_wave_height" in o else None,
            o["wind_wave_direction"] if "wind_wave_direction" in o else None,
            shore_deg,
        )

    # Tide stage near label
    out["tide_stage_sign_last3h"] = _tide_stage_sign(ocean_df, end_time, hours=3)
    return out


# ---------- Unified feature builder ----------
def build_visibility_features(
    ocean_df: pd.DataFrame,
    weather_df: pd.DataFrame,
    end_time: pd.Timestamp,
    shore_deg: Optional[float] = None,
) -> Dict[str, float]:
    """
    Build the full feature dictionary used by both training and prediction.

    Includes:
      - Multi-window (24/48/72h) aggregates & onshore components
      - Sea-level rate-of-change and simple tide stage
      - 24h trend & event-timing features for core drivers
      - 24h circular trend features
    """
    # Ensure datetime index sorted
    for df in (ocean_df, weather_df):
        if "site_timestamp" in df.columns:
            df = df.copy()
            df["site_timestamp"] = pd.to_datetime(df["site_timestamp"])
            df.set_index("site_timestamp", inplace=True, drop=True)
        df.sort_index(inplace=True)

    out: Dict[str, float] = {}

    # Multi-window aggregates
    out.update(
        _aggregate_windowed_features(
            ocean_df, weather_df, pd.to_datetime(end_time), windows=[24, 48, 72], shore_deg=shore_deg
        )
    )

    # 24h slices for temporal/circular trend
    idx24_o = _window_idx(ocean_df, pd.to_datetime(end_time), 24)
    idx24_w = _window_idx(weather_df, pd.to_datetime(end_time), 24)
    o24 = ocean_df.loc[idx24_o]
    w24 = weather_df.loc[idx24_w]

    # Temporal trends
    out.update(extract_trend_features(o24.get("swell_wave_height", pd.Series(dtype=float)), "swell_wave_height"))
    out.update(extract_trend_features(o24.get("wave_height", pd.Series(dtype=float)), "wave_height"))
    out.update(extract_trend_features(w24.get("wind_speed_10m", pd.Series(dtype=float)), "wind_speed_10m"))
    out.update(extract_trend_features(w24.get("temperature_2m", pd.Series(dtype=float)), "temperature_2m"))

    # Event timing
    out.update(extract_event_timing_features(o24.get("swell_wave_height", pd.Series(dtype=float)), "swell_wave_height"))
    out.update(extract_event_timing_features(o24.get("wave_height", pd.Series(dtype=float)), "wave_height"))
    out.update(extract_event_timing_features(w24.get("wind_speed_10m", pd.Series(dtype=float)), "wind_speed_10m"))
    out.update(extract_event_timing_features(w24.get("temperature_2m", pd.Series(dtype=float)), "temperature_2m"))

    # Circular trends
    out.update(extract_circular_trend(o24.get("wave_direction", pd.Series(dtype=float)), "wave_direction"))
    out.update(extract_circular_trend(o24.get("wind_wave_direction", pd.Series(dtype=float)), "wind_wave_direction"))
    out.update(extract_circular_trend(o24.get("swell_wave_direction", pd.Series(dtype=float)), "swell_wave_direction"))
    out.update(extract_circular_trend(o24.get("ocean_current_direction", pd.Series(dtype=float)), "ocean_current_direction"))
    out.update(extract_circular_trend(w24.get("wind_direction_10m", pd.Series(dtype=float)), "wind_direction_10m"))

    return out
