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


def _quality_summary(df, ts_col, group_col: Optional[str] = None):
    """Summarise timestamp quality without mistaking parallel-node readings for duplicates."""
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
    return {
        "rows": int(len(df)),
        "timestamp_parse_failures": int(ts.isna().sum()),
        "duplicate_timestamps": duplicate_count,
        "duplicate_key": f"{group_col}+{ts_col}" if group_col else ts_col,
        "missing_cells": int(df.isna().sum().sum()),
        "median_sampling_interval_minutes": float(delta.median()) if not delta.empty else None,
        "gaps_over_20_minutes": int((delta > 20).sum()) if not delta.empty else 0,
    }


def validate_tomato(frame: pd.DataFrame, mapping: Dict[str, str], expected_step_minutes: Optional[float] = None):
    ts = resolve_column(frame, mapping, "timestamp")
    vwc = resolve_column(frame, mapping, "vwc")
    irrigation = resolve_column(frame, mapping, "irrigation_volume", required=False)
    site_col = resolve_column(frame, mapping, "site", required=False)
    # A set of processed sector files commonly shares identical timestamps.
    # Never concatenate those rows and de-duplicate on time: evaluate each
    # sector (or input file) independently.
    group_col = site_col or ("__source_file" if "__source_file" in frame.columns else None)
    quality = _quality_summary(frame, ts, group_col)
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
                result = benchmark_vwc_forecasting(
                    f, timestamp_col=ts, target_col=vwc, horizon_steps=horizon_steps,
                    expected_step_minutes=step
                )
                sector_result["vwc_forecast"] = {
                    "task": result["task"], "horizon_minutes": result["horizon_minutes"],
                    "sampling_minutes_median": result["sampling_minutes_median"],
                    "split_rows": result["split_rows"],
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
                "total_reported_volume": float(valid.sum()),
                "unit": "source dataset unit; verify data dictionary",
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
                "total_reported_volume": total_volume,
                "unit": "source dataset unit; verify data dictionary",
            }
    return report

def validate_leafwetness(
    frame: pd.DataFrame, mapping: Dict[str, str], wet_threshold: float = 50.0
):
    ts = resolve_column(frame, mapping, "timestamp")
    site = resolve_column(frame, mapping, "site")
    lws = resolve_column(frame, mapping, "leaf_wetness")
    rh = resolve_column(frame, mapping, "rh")
    temp = resolve_column(frame, mapping, "air_temperature")
    f = frame[[ts, site, lws, rh, temp]].copy()
    f[ts] = pd.to_datetime(f[ts], errors="coerce", utc=True)
    for col in (lws, rh, temp):
        f[col] = pd.to_numeric(f[col], errors="coerce")
    f = f.dropna(subset=[ts, site]).sort_values([site, ts])
    f["date"] = f[ts].dt.floor("D")
    f["wet"] = f[lws] >= wet_threshold
    f["rh90"] = f[rh] >= 90.0
    interval_parts = []
    for site_id, group in f.groupby(site, sort=False):
        g = group.copy()
        delta = g[ts].shift(-1).sub(g[ts]).dt.total_seconds().div(3600)
        med = delta[(delta > 0) & delta.notna()].median()
        cap = min(float(med) * 2.0, 1.0) if pd.notna(med) else 1.0
        g["interval_h"] = delta.clip(lower=0, upper=cap).fillna(0)
        interval_parts.append(g)
    f = pd.concat(interval_parts, ignore_index=True)
    rows = []
    for (site_id, day), g in f.groupby([site, "date"]):
        wet_h = float((g["wet"] * g["interval_h"]).sum())
        rh_h = float((g["rh90"] * g["interval_h"]).sum())
        wet_temp = g.loc[g["rh90"] & g[temp].notna(), temp]
        mean_wet_temp = float(wet_temp.mean()) if not wet_temp.empty else float(g[temp].mean())
        dsv = compute_daily_wallin_dsv(mean_wet_temp, rh_h)
        dsv_lws = compute_daily_lws_modified_dsv(mean_wet_temp, rh_h, wet_h)
        rows.append({"site": str(site_id), "date": str(day), "leaf_wetness_hours": wet_h,
                     "rh90_hours": rh_h, "mean_temp_during_rh90_c": mean_wet_temp,
                     "wallin_dsv": dsv, "dsv_lws_modified": dsv_lws})
    daily = pd.DataFrame(rows)
    if daily.empty:
        raise ValueError("No daily leaf-wetness aggregates could be calculated")
    p90 = daily.groupby("site")["leaf_wetness_hours"].quantile(0.90).sort_values(ascending=False)
    return {
        "dataset": "leafwetness",
        "quality": _quality_summary(frame, ts, site),
        "wet_threshold": float(wet_threshold),
        "threshold_warning": "wet_threshold is a user-supplied sensor threshold; calibrate it using the source data dictionary and field reference measurements",
        "humid_pole_candidate_by_p90_daily_lwd": str(p90.index[0]),
        "site_p90_daily_lwd_hours": {str(k): float(v) for k, v in p90.items()},
        "daily_table": daily,
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
    parser.add_argument("--wet-threshold", type=float, default=50.0)
    parser.add_argument("--gap-minutes", type=float, default=20.0)
    parser.add_argument("--step-minutes", type=float, help="Override known sampling interval for tomato forecasting")
    args = parser.parse_args(argv)
    mapping = json.loads(args.mapping.read_text(encoding="utf-8")) if args.mapping else {}
    frame = read_input_files(args.input)
    if args.dataset == "tomato":
        result = validate_tomato(frame, mapping, args.step_minutes)
    elif args.dataset == "leafwetness":
        result = validate_leafwetness(frame, mapping, args.wet_threshold)
    else:
        result = validate_libelium(frame, mapping, args.gap_minutes)

    output = args.output_dir / args.dataset
    output.mkdir(parents=True, exist_ok=True)
    daily = result.pop("daily_table", None)
    rolling = result.pop("rolling_metrics", None)
    if daily is not None:
        daily.to_csv(output / "daily_leafwetness_dsv.csv", index=False)
    if rolling is not None:
        rolling.to_csv(output / "rolling_spatial_sufficiency.csv", index=False)
    result["source"] = DATASETS[args.dataset]
    result["input_files"] = [
        {"path": str(p), "sha256": file_sha256(p)} for p in args.input
    ]
    result["mapping"] = mapping
    (output / "validation_report.json").write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
