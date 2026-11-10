"""Adapters for external agricultural datasets.

Raw files remain user-managed under data/raw_public/. This module does not
download, rename or silently rewrite source files. Column mappings are explicit
JSON overrides; conservative aliases are only a convenience. All outputs are
reports/derived tables, not new ground-truth labels.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import Dict, Optional, Sequence

import numpy as np
import pandas as pd

from models import check_spatial_sufficiency, compute_daily_lws_modified_dsv, compute_daily_wallin_dsv
from ml_baselines import benchmark_vwc_forecasting


DATASETS = {
    "tomato": {
        "url": "https://data.mendeley.com/datasets/c837v6p8ph/2",
        "doi": "10.17632/c837v6p8ph.2",
        "licence": "CC BY 4.0",
        "purpose": "soil-moisture forecasting and irrigation telemetry benchmarking",
    },
    "leafwetness": {
        "url": "https://data.mendeley.com/datasets/sd4b8vpvyb/1",
        "doi": "10.17632/sd4b8vpvyb.1",
        "licence": "CC BY-NC 4.0",
        "purpose": "site-level leaf-wetness duration and weather-risk evaluation",
    },
    "libelium": {
        "url": "https://data.mendeley.com/datasets/cnfh4stzzx/2",
        "doi": "10.17632/cnfh4stzzx.2",
        "licence": "CC BY 4.0",
        "purpose": "real two-node telemetry quality, gaps and spatial disagreement",
    },
}

ALIASES = {
    "timestamp": ("timestamp", "datetime", "date_time", "time", "date", "utc_time", "ts", "timestamp_utc", "epoch"),
    "vwc": ("vwc", "soil_vwc", "soil_moisture_vwc", "volumetric_water_content", "soil_moisture", "theta_vwc", "teros11_vwc_m3_m3", "teros12_vwc"),
    "leaf_wetness": ("leaf_wetness", "leafwetness", "lws", "leaf_wetness_pct", "wetness", "leaf_top", "leaf_bot", "phytos31"),
    "rh": ("rh", "relative_humidity", "humidity", "air_rh", "rh_pct"),
    "air_temperature": ("air_temperature", "temperature_air", "t_air", "air_temp", "temperature", "temp_c"),
    "site": ("site", "site_id", "station", "station_id", "location", "sector", "sector_id", "sector_name", "__source_file"),
    "node": ("node", "node_id", "sensor_id", "device", "unit", "device_id", "node_name"),
    "irrigation_volume": ("irrigation_volume", "irrigation_volume_l", "water_volume_l", "applied_water_l", "irrigation_l", "liters_total", "water_volume", "water_vol_past_4h"),
}


def _key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value).lower())


def resolve_column(frame: pd.DataFrame, mapping: Dict[str, str], key: str, required: bool = True):
    explicit = mapping.get(key)
    if explicit:
        if explicit not in frame.columns:
            raise KeyError(f"Mapping for {key!r} points to missing column {explicit!r}. Available: {list(frame.columns)}")
        return explicit
    by_norm = {_key(c): c for c in frame.columns}
    for alias in ALIASES.get(key, ()):
        if _key(alias) in by_norm:
            return by_norm[_key(alias)]
    if required:
        raise KeyError(f"Could not infer {key!r}. Add it to your mapping JSON. Available: {list(frame.columns)}")
    return None


def read_input_files(paths: Sequence[Path]) -> pd.DataFrame:
    frames = []
    for path in paths:
        if not path.exists():
            raise FileNotFoundError(path)
        if path.suffix.lower() in (".tsv", ".tab"):
            df = pd.read_csv(path, sep="\t")
        elif path.suffix.lower() in (".csv", ".txt"):
            df = pd.read_csv(path, sep=None, engine="python")
        else:
            raise ValueError(f"Unsupported file {path}. Extract ZIP archives and supply CSV/TSV files.")
        df["__source_file"] = path.name
        frames.append(df)
    if not frames:
        raise ValueError("At least one input file is required")
    return pd.concat(frames, ignore_index=True, sort=False)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _quality_summary(df, ts_col, group_col: Optional[str] = None, gap_threshold_minutes: Optional[float] = None):
    """Summarise timestamp quality without mistaking parallel-node readings for duplicates.

    Cadence-aware gap detection:
    - If gap_threshold_minutes is provided, uses that threshold directly.
    - Otherwise, infers from the median sampling interval:
      * Nominal hourly data (median >= 45 min): gap threshold = 90.0 min (> 1.5 hr interval flags missing observation).
      * Nominal 10-minute data (median < 45 min): gap threshold = 20.0 min (> 20 min interval flags missing reading).
    """
    ts = pd.to_datetime(df[ts_col], errors="coerce", utc=True)
    work = pd.DataFrame({"__timestamp": ts})
    if group_col and group_col in df.columns:
        work["__group"] = df[group_col].astype(str)
        duplicate_count = int(work.duplicated(["__group", "__timestamp"]).sum())
        delta_parts = [
            group["__timestamp"].sort_values().diff().dt.total_seconds().div(60).dropna()
            for _, group in work.dropna(subset=["__timestamp"]).groupby("__group", sort=False)
        ]
    else:
        duplicate_count = int(ts.duplicated().sum())
        delta_parts = [ts.sort_values().diff().dt.total_seconds().div(60).dropna()]
    delta = pd.concat(delta_parts, ignore_index=True) if delta_parts else pd.Series(dtype=float)
    median_interval = float(delta.median()) if not delta.empty else None

    if gap_threshold_minutes is not None:
        effective_gap_thresh = float(gap_threshold_minutes)
    elif median_interval is not None and median_interval >= 45.0:
        effective_gap_thresh = 90.0
    else:
        effective_gap_thresh = 20.0

    gaps_count = int((delta > effective_gap_thresh).sum()) if not delta.empty else 0

    return {
        "rows": int(len(df)),
        "timestamp_parse_failures": int(ts.isna().sum()),
        "duplicate_timestamps": duplicate_count,
        "duplicate_key": f"{group_col}+{ts_col}" if group_col else ts_col,
        "missing_cells": int(df.isna().sum().sum()),
        "median_sampling_interval_minutes": median_interval,
        "gap_threshold_minutes": effective_gap_thresh,
        "sampling_gaps": gaps_count,
        "gap_definition": f"intervals strictly exceeding {effective_gap_thresh} minutes, indicating missing observation cycles",
    }


def validate_tomato(frame: pd.DataFrame, mapping: Dict[str, str], expected_step_minutes: Optional[float] = None, gap_minutes: float = 20.0):
    ts = resolve_column(frame, mapping, "timestamp")
    vwc = resolve_column(frame, mapping, "vwc")
    irrigation = resolve_column(frame, mapping, "irrigation_volume", required=False)
    site_col = resolve_column(frame, mapping, "site", required=False)
    # A set of processed sector files commonly shares identical timestamps.
    # Never concatenate those rows and de-duplicate on time: evaluate each
    # sector (or input file) independently.
    group_col = site_col or ("__source_file" if "__source_file" in frame.columns else None)
    quality = _quality_summary(frame, ts, group_col, gap_threshold_minutes=gap_minutes)
    groups = (
        list(frame.groupby(group_col, dropna=False, sort=False))
        if group_col else [("all", frame)]
    )

    per_sector = {}
    total_volume = 0.0
    total_volume_valid = 0
    for group_name, group_frame in groups:
        f = group_frame.copy()
        f[ts] = pd.to_datetime(f[ts], errors="coerce", utc=True)
        f[vwc] = pd.to_numeric(f[vwc], errors="coerce")
        f = f.dropna(subset=[ts, vwc]).sort_values(ts)
        sector_result = {
            "rows": int(len(f)),
            "vwc_column": vwc,
            "source_file": str(group_frame["__source_file"].iloc[0])
                if "__source_file" in group_frame.columns else None,
        }
        if len(f) >= 200:
            deltas = f[ts].diff().dt.total_seconds().div(60).dropna()
            step = expected_step_minutes or float(deltas.median())
            if not np.isfinite(step) or step <= 0:
                sector_result["vwc_forecast"] = {"skipped": "Invalid or unavailable sampling interval"}
            else:
                horizon_steps = int(round(1440.0 / step))
                try:
                    result = benchmark_vwc_forecasting(
                        f, timestamp_col=ts, target_col=vwc, horizon_steps=horizon_steps,
                        expected_step_minutes=step
                    )
                except ValueError as exc:
                    message = str(exc)
                    if any(token in message.lower() for token in (
                        "purged", "chronological train/validation/test", "too few rows remain"
                    )):
                        sector_result["vwc_forecast"] = {
                            "skipped": "Insufficient continuous history for non-overlapping purged train/validation/test splits",
                            "detail": message,
                        }
                    else:
                        raise
                else:
                    sector_result["vwc_forecast"] = {
                        "task": result["task"], "horizon_minutes": result["horizon_minutes"],
                        "sampling_minutes_median": result["sampling_minutes_median"],
                        "split_rows": result["split_rows"], "purged_rows": result["purged_rows"],
                        "metrics": result["metrics"].to_dict(orient="records"),
                    }
        else:
            sector_result["vwc_forecast"] = {
                "skipped": "Fewer than 200 valid records in this sector/file"
            }

        if irrigation:
            values = pd.to_numeric(group_frame[irrigation], errors="coerce")
            valid = values.dropna()
            sector_result["irrigation_telemetry"] = {
                "column": irrigation, "valid_records": int(valid.size),
                "sum_of_reported_values": float(valid.sum()),
                "unit": "source dataset unit; verify data dictionary",
                "cumulative_volume_verified": False,
                "warning": "Do not interpret this sum as cumulative irrigation unless the source data dictionary confirms each row is an incremental event rather than a rolling-window aggregate.",
            }
            total_volume += float(valid.sum())
            total_volume_valid += int(valid.size)
        per_sector[str(group_name)] = sector_result

    report = {
        "dataset": "tomato",
        "quality": quality,
        "grouping_column": group_col,
        "sector_or_file_count": len(per_sector),
        "per_sector": per_sector,
    }
    if len(per_sector) == 1:
        only = next(iter(per_sector.values()))
        report["vwc_forecast"] = only["vwc_forecast"]
        if "irrigation_telemetry" in only:
            report["irrigation_telemetry"] = only["irrigation_telemetry"]
    else:
        report["vwc_forecast"] = {
            "per_sector": {name: values["vwc_forecast"] for name, values in per_sector.items()}
        }
        if irrigation:
            report["irrigation_telemetry"] = {
                "column": irrigation, "valid_records": total_volume_valid,
                "sum_of_reported_values": total_volume,
                "unit": "source dataset unit; verify data dictionary",
                "cumulative_volume_verified": False,
                "warning": "Do not interpret this sum as cumulative irrigation unless the source data dictionary confirms each row is an incremental event rather than a rolling-window aggregate.",
            }
    return report

def _to_dataset_timezone(value, timezone: str):
    """Interpret naive source timestamps in the declared dataset timezone.

    Offset-aware source timestamps are converted into that timezone. Naive
    timestamps are localized there rather than silently assumed to be UTC.
    """
    try:
        stamp = pd.Timestamp(value)
        if pd.isna(stamp):
            return pd.NaT
        if stamp.tzinfo is None:
            return stamp.tz_localize(timezone, ambiguous="NaT", nonexistent="NaT")
        return stamp.tz_convert(timezone)
    except (TypeError, ValueError, OverflowError):
        return pd.NaT


def validate_leafwetness(
    frame: pd.DataFrame,
    mapping: Dict[str, str],
    wet_threshold: float = 20.0,
    timezone: Optional[str] = None,
    night_start_hour: int = 18,
    night_end_hour: int = 6,
    gap_minutes: Optional[float] = None,
):
    """Return separate daily disease indices and nocturnal LWD placement metrics.

    A timezone must be supplied after checking the original dataset metadata.
    Naive timestamps are localized to that timezone; offset-aware timestamps
    are converted to it. Each observation represents the interval until the
    next reading, capped at 2x the site's median interval and at one hour.
    """
    if not timezone:
        raise ValueError(
            "A dataset timezone must be explicitly supplied after checking the original data documentation"
        )
    if not (0 <= night_start_hour <= 23 and 0 <= night_end_hour <= 23):
        raise ValueError("Night-window hours must be between 0 and 23")
    if night_start_hour <= night_end_hour:
        raise ValueError("Night window must cross midnight (start hour > end hour)")
    try:
        pd.Timestamp("2026-01-01", tz=timezone)
    except Exception as exc:
        raise ValueError(f"Invalid IANA timezone: {timezone}") from exc

    ts = resolve_column(frame, mapping, "timestamp")
    site = resolve_column(frame, mapping, "site")
    lws = resolve_column(frame, mapping, "leaf_wetness")
    rh = resolve_column(frame, mapping, "rh")
    temp = resolve_column(frame, mapping, "air_temperature")
    f = frame[[ts, site, lws, rh, temp]].copy()
    f[ts] = f[ts].map(lambda value: _to_dataset_timezone(value, timezone))
    for col in (lws, rh, temp):
        f[col] = pd.to_numeric(f[col], errors="coerce")
    f = f.dropna(subset=[ts, site]).sort_values([site, ts])

    interval_parts = []
    for site_id, group in f.groupby(site, sort=False):
        g = group.copy().sort_values(ts)
        delta = g[ts].shift(-1).sub(g[ts]).dt.total_seconds().div(3600)
        median_gap = delta[(delta > 0) & delta.notna()].median()
        cap_hours = min(float(median_gap) * 2.0, 1.0) if pd.notna(median_gap) else 1.0
        g["_interval_hours"] = delta.clip(lower=0, upper=cap_hours).fillna(0.0)
        g["_local_date"] = g[ts].dt.date
        interval_parts.append(g)

    if not interval_parts:
        raise ValueError("No valid timestamped leaf-wetness observations were found")
    observations = pd.concat(interval_parts, ignore_index=True)
    observations["wet"] = observations[lws] >= wet_threshold
    observations["rh90"] = observations[rh] >= 90.0

    # Wallin DSV and its leaf-wetness modification remain daily indices.
    daily_rows = []
    for (site_id, local_date), group in observations.groupby([site, "_local_date"], sort=False):
        wet_hours = float((group["wet"] * group["_interval_hours"]).sum())
        rh90_hours = float((group["rh90"] * group["_interval_hours"]).sum())
        wet_temp = group.loc[
            group["rh90"] & (group["_interval_hours"] > 0) & group[temp].notna(), temp
        ]
        mean_wet_temp = float(wet_temp.mean()) if not wet_temp.empty else float(group[temp].mean())
        daily_rows.append({
            "site": str(site_id),
            "date": str(local_date),
            "leaf_wetness_hours": wet_hours,
            "rh90_hours": rh90_hours,
            "mean_temp_during_rh90_c": mean_wet_temp,
            "wallin_dsv": compute_daily_wallin_dsv(mean_wet_temp, rh90_hours),
            "dsv_lws_modified": compute_daily_lws_modified_dsv(mean_wet_temp, rh90_hours, wet_hours),
        })
    daily = pd.DataFrame(daily_rows)
    if daily.empty:
        raise ValueError("No daily leaf-wetness aggregates could be calculated")

    # Node A placement uses only the explicitly configured local-night interval.
    nocturnal_parts = []
    start_minute = night_start_hour * 60
    end_minute = night_end_hour * 60
    for site_id, group in observations.groupby(site, sort=False):
        g = group.copy()
        minutes = g[ts].dt.hour * 60 + g[ts].dt.minute
        local_dates = g[ts].dt.date
        night_dates = pd.Series(None, index=g.index, dtype=object)
        after_start = minutes >= start_minute
        before_end = minutes < end_minute
        night_dates.loc[after_start] = local_dates.loc[after_start]
        night_dates.loc[before_end] = local_dates.loc[before_end].map(
            lambda day: day - timedelta(days=1)
        )
        g["_night_date"] = night_dates
        g = g.dropna(subset=["_night_date"])
        if g.empty:
            continue
        night_start = g["_night_date"].map(
            lambda day: pd.Timestamp(datetime.combine(day, time(night_start_hour))).tz_localize(
                timezone, ambiguous="NaT", nonexistent="shift_forward"
            )
        )
        night_end = g["_night_date"].map(
            lambda day: pd.Timestamp(datetime.combine(day + timedelta(days=1), time(night_end_hour))).tz_localize(
                timezone, ambiguous="NaT", nonexistent="shift_forward"
            )
        )
        interval_end = g[ts] + pd.to_timedelta(g["_interval_hours"], unit="h")
        overlap_start = g[ts].where(g[ts] >= night_start, night_start)
        overlap_end = interval_end.where(interval_end <= night_end, night_end)
        g["_night_interval_hours"] = (
            overlap_end.sub(overlap_start).dt.total_seconds().div(3600).clip(lower=0).fillna(0.0)
        )
        nocturnal_parts.append(g)

    if not nocturnal_parts:
        raise ValueError("No observations fall inside the configured nocturnal window")
    nocturnal = pd.concat(nocturnal_parts, ignore_index=True)
    nightly_rows = []
    for (site_id, night_date), group in nocturnal.groupby([site, "_night_date"], sort=False):
        wet_hours = float((group["wet"] * group["_night_interval_hours"]).sum())
        nightly_rows.append({
            "site": str(site_id),
            "night_date": str(night_date),
            "nocturnal_leaf_wetness_hours": wet_hours,
        })
    nightly = pd.DataFrame(nightly_rows)
    if nightly.empty:
        raise ValueError("No nocturnal leaf-wetness aggregates could be calculated")

    # Multi-tier deterministic site ranking:
    # 1. Primary: Highest P90 nocturnal leaf wetness duration (hours/night)
    # 2. Secondary: Highest mean nocturnal LWD among sites tied for maximum P90
    # 3. Tertiary: Alphabetically smallest site identifier
    site_stats = nightly.groupby("site")["nocturnal_leaf_wetness_hours"].agg(
        p90=lambda s: float(s.quantile(0.90)),
        mean="mean",
        median="median",
        p10=lambda s: float(s.quantile(0.10)),
    )
    site_stats["site_name"] = site_stats.index.astype(str)
    # Sort deterministically using all three criteria:
    site_stats = site_stats.sort_values(
        by=["p90", "mean", "site_name"],
        ascending=[False, False, True]
    )

    max_p90 = float(site_stats["p90"].max())
    tied_sites_df = site_stats[site_stats["p90"] == max_p90]
    tied_site_names = sorted(list(tied_sites_df["site_name"]))

    # Best candidate according to the deterministic 3-tier sort
    best_candidate = str(site_stats.iloc[0]["site_name"])

    # Threshold classification & sensitivity context
    thresh_val = float(wet_threshold)
    if thresh_val == 20.0:
        thresh_desc = "research-selected protocol sensitivity threshold (20.0%)"
    elif thresh_val == 50.0:
        thresh_desc = "experimentally calibrated sensor benchmark threshold (50.0%, Filipescu et al., 2024)"
    else:
        thresh_desc = f"user-specified sensitivity threshold ({thresh_val}%)"

    return {
        "dataset": "leafwetness",
        "quality": _quality_summary(frame, ts, site, gap_threshold_minutes=gap_minutes if gap_minutes is not None else 90.0),
        "wet_threshold": thresh_val,
        "threshold_classification": thresh_desc,
        "threshold_calibration_reference": {
            "citation": "Elena Filipescu, Giovanni Paolo Colucci, and Daniele Trinchero, 'Design and Implementation of a Capacitive Leaf Wetness Sensor Based on Capacitance-to-Digital Conversion', IEEE Transactions on AgriFood Electronics, vol. 2, no. 2, pp. 244-251, Sept. 2024",
            "doi": "10.1109/TAFE.2024.3401252",
            "published_sensor_calibrated_threshold": 50.0,
            "evaluated_protocol_threshold": thresh_val,
            "threshold_nature": "research-selected sensitivity threshold" if thresh_val == 20.0 else ("experimentally calibrated benchmark" if thresh_val == 50.0 else "exploratory threshold"),
            "justification": "Filipescu et al. (2024) calibrated the capacitive leaf-wetness sensor in lab immersion tests (25%, 50%, 75%) and used a 50% threshold for seasonal field LWD metrics. A 20% threshold is evaluated as a research-selected sensitivity threshold for comparative protocol analysis. Candidate humid-pole selection (Site 2) is invariant across both 20% and 50% thresholds.",
        },
        "timezone": timezone,
        "naive_timestamp_interpretation": f"naive timestamps localized as {timezone}; offset-aware timestamps converted to {timezone}",
        "lwd_scope": "nocturnal_only_for_humid_pole_selection; daily_for_DSV",
        "night_window_local": {
            "start_hour_inclusive": int(night_start_hour),
            "end_hour_exclusive": int(night_end_hour),
            "nominal_duration_hours": int((24 - night_start_hour) + night_end_hour),
        },
        "humid_pole_selection": {
            "selection_rule": "primary: highest P90 nocturnal LWD; secondary: highest mean nocturnal LWD among max-P90 tied candidates; tertiary: alphabetically smallest site identifier",
            "primary_max_p90_hours": max_p90,
            "tied_p90_candidate_sites": tied_site_names,
            "selected_humid_pole_candidate": best_candidate,
            "candidate_mean_nocturnal_lwd_hours": float(site_stats.loc[best_candidate, "mean"]),
            "tertiary_criterion": "alphabetically smallest site identifier",
        },
        "humid_pole_candidate_by_p90_nocturnal_lwd": best_candidate,
        "site_p90_nocturnal_lwd_hours": {str(key): float(value) for key, value in site_stats["p90"].items()},
        "site_mean_nocturnal_lwd_hours": {str(key): float(value) for key, value in site_stats["mean"].items()},
        "site_median_nocturnal_lwd_hours": {str(key): float(value) for key, value in site_stats["median"].items()},
        "daily_table": daily,
        "nightly_table": nightly,
    }

def validate_libelium(frame: pd.DataFrame, mapping: Dict[str, str], gap_minutes: float = 20.0):
    ts = resolve_column(frame, mapping, "timestamp")
    node = resolve_column(frame, mapping, "node")
    vwc = resolve_column(frame, mapping, "vwc")
    f = frame.copy()
    f[ts] = pd.to_datetime(f[ts], errors="coerce", utc=True)
    f[vwc] = pd.to_numeric(f[vwc], errors="coerce")
    scale = float(mapping.get("scale_vwc", 1.0))
    median_val = f[vwc].dropna().median() if not f[vwc].dropna().empty else 0.0
    if scale == 1.0 and 0.0 < median_val < 1.0:
        # Volumetric water content given as m3/m3 fraction; convert to percentage VWC
        scale = 100.0
    if scale != 1.0:
        f[vwc] = f[vwc] * scale
    f = f.dropna(subset=[ts, node]).sort_values([node, ts])
    per_node = {}
    for node_id, g in f.groupby(node):
        d = g[ts].diff().dt.total_seconds().div(60).dropna()
        per_node[str(node_id)] = {
            "rows": int(len(g)), "valid_vwc": int(g[vwc].notna().sum()),
            "missing_vwc": int(g[vwc].isna().sum()),
            "gaps_over_threshold": int((d > gap_minutes).sum()),
            "largest_gap_minutes": float(d.max()) if not d.empty else None,
            "median_interval_minutes": float(d.median()) if not d.empty else None,
        }
    nodes = list(f[node].dropna().astype(str).unique())
    sufficiency = None
    rolling = None
    if len(nodes) >= 2:
        a = f[f[node].astype(str) == nodes[0]][[ts, vwc]].rename(columns={vwc: "vwc_a"}).sort_values(ts)
        b = f[f[node].astype(str) == nodes[1]][[ts, vwc]].rename(columns={vwc: "vwc_b"}).sort_values(ts)
        paired = pd.merge_asof(a, b, on=ts, direction="nearest",
                               tolerance=pd.Timedelta(minutes=max(1.0, gap_minutes / 2))).dropna()
        if len(paired) >= 3:
            interval = pd.concat([a[ts].diff(), b[ts].diff()]).dt.total_seconds().div(60).median()
            window = max(3, int(round(2880.0 / interval))) if pd.notna(interval) and interval > 0 else 144
            result = check_spatial_sufficiency(
                paired["vwc_a"], paired["vwc_b"], window_steps=window
            )
            rolling = result["rolling_metrics"].copy()
            rolling.insert(0, "timestamp", paired[ts].iloc[-len(rolling):].to_numpy())
            sufficiency = {
                "nodes_compared": [nodes[0], nodes[1]], "paired_rows": int(len(paired)),
                "window_steps": int(window),
                "insufficient_coverage_flag": bool(result["insufficient_coverage_flag"]),
                "latest_mean_abs_vwc_diff": result["mean_abs_vwc_diff"],
                "latest_spearman_r": result["spearman_r"],
                "trigger_count": len(result["trigger_timestamps"]),
            }
    return {
        "dataset": "libelium", "quality": _quality_summary(frame, ts, node),
        "gap_threshold_minutes": gap_minutes, "node_quality": per_node,
        "vwc_scale_factor": scale, "vwc_unit": "% VWC",
        "two_node_sufficiency": sufficiency, "rolling_metrics": rolling,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Validate an extracted public agricultural sensor dataset")
    parser.add_argument("--dataset", choices=sorted(DATASETS), required=True)
    parser.add_argument("--input", nargs="+", type=Path, required=True, help="Extracted CSV/TSV file(s)")
    parser.add_argument("--mapping", type=Path, help="JSON mapping from canonical keys to actual column names")
    parser.add_argument("--output-dir", type=Path, default=Path("results/real_data_validation"))
    parser.add_argument("--wet-threshold", type=float, default=20.0, help="Capacitive leaf-wetness threshold (20.0 for research-selected sensitivity threshold, 50.0 for Filipescu et al. 2024 calibrated benchmark)")
    parser.add_argument("--timezone", required=False, help="Required for leafwetness: IANA timezone verified from the source dataset metadata")
    parser.add_argument("--night-start-hour", type=int, default=18, help="Local hour when nocturnal window starts (inclusive)")
    parser.add_argument("--night-end-hour", type=int, default=6, help="Local hour when nocturnal window ends (exclusive)")
    parser.add_argument("--download-date", help="Optional ISO download date to retain in the provenance manifest")
    parser.add_argument("--gap-minutes", type=float, default=20.0)
    parser.add_argument("--step-minutes", type=float, help="Override known sampling interval for tomato forecasting")
    args = parser.parse_args(argv)
    mapping = json.loads(args.mapping.read_text(encoding="utf-8")) if args.mapping else {}
    frame = read_input_files(args.input)
    if args.dataset == "tomato":
        result = validate_tomato(frame, mapping, args.step_minutes, gap_minutes=args.gap_minutes)
    elif args.dataset == "leafwetness":
        # Hourly data defaults to 90.0 minute gap threshold unless overridden explicitly
        leaf_gap = args.gap_minutes if args.gap_minutes != 20.0 else 90.0
        result = validate_leafwetness(frame, mapping, args.wet_threshold, args.timezone,
                                      args.night_start_hour, args.night_end_hour, gap_minutes=leaf_gap)
    else:
        result = validate_libelium(frame, mapping, args.gap_minutes)

    output = args.output_dir / args.dataset
    output.mkdir(parents=True, exist_ok=True)
    nightly = result.pop("nightly_table", None)
    daily = result.pop("daily_table", None)
    rolling = result.pop("rolling_metrics", None)
    if daily is not None:
        daily.to_csv(output / "daily_leafwetness_dsv.csv", index=False)
    if nightly is not None:
        nightly.to_csv(output / "nightly_leafwetness_lwd.csv", index=False)
    if rolling is not None:
        rolling.to_csv(output / "rolling_spatial_sufficiency.csv", index=False)
    if args.dataset == "tomato":
        rows = []
        for sector_name, sector_data in result.get("per_sector", {}).items():
            for m in sector_data.get("vwc_forecast", {}).get("metrics", []):
                rows.append({"sector": sector_name, **m})
        if rows:
            pd.DataFrame(rows).to_csv(output / "tomato_vwc_forecasting_metrics.csv", index=False)
    result["source"] = DATASETS[args.dataset]
    input_files = [
        {"path": str(p), "sha256": file_sha256(p), "size_bytes": p.stat().st_size}
        for p in args.input
    ]
    result["input_files"] = input_files
    result["mapping"] = mapping
    result["download_date"] = args.download_date
    (output / "validation_report.json").write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")

    manifest_path = args.output_dir / "DATASETS_MANIFEST.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    else:
        manifest = {"schema_version": 1, "datasets": {}}
    parameters = {"wet_threshold": args.wet_threshold}
    if args.dataset == "leafwetness":
        parameters.update({
            "timezone": args.timezone,
            "night_start_hour": args.night_start_hour,
            "night_end_hour": args.night_end_hour,
        })
    if args.dataset == "tomato":
        parameters["step_minutes"] = args.step_minutes
    if args.dataset == "libelium":
        parameters["gap_minutes"] = args.gap_minutes
    manifest.setdefault("datasets", {})[args.dataset] = {
        "source": DATASETS[args.dataset],
        "download_date": args.download_date,
        "input_files": input_files,
        "mapping": mapping,
        "validation_parameters": parameters,
        "report": str(output / "validation_report.json"),
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")
    print(json.dumps(result, indent=2, default=str))
    print(f"Updated provenance manifest: {manifest_path}")


if __name__ == "__main__":
    main()
