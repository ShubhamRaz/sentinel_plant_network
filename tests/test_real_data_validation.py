import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from ml_baselines import _prepare_time_series, purged_chronological_indices
from real_data_validation import (
    validate_libelium,
    validate_leafwetness,
    validate_tomato,
)


def test_tomato_adapter_reports_quality_and_forecast():
    n = 1800
    ts = pd.date_range("2026-01-01", periods=n, freq="10min", tz="UTC")
    vwc = 28.0 - np.linspace(0, 7, n) + 0.8 * np.sin(np.arange(n) / 15)
    frame = pd.DataFrame({
        "when": ts,
        "theta": vwc,
        "irrigation_l": np.where(np.arange(n) % 72 == 0, 1.5, 0.0),
        "air_c": 25 + np.sin(np.arange(n) / 30),
    })
    result = validate_tomato(
        frame,
        {"timestamp": "when", "vwc": "theta", "irrigation_volume": "irrigation_l"},
    )
    assert result["quality"]["rows"] == n
    assert result["vwc_forecast"]["horizon_minutes"] == pytest.approx(1440)
    assert len(result["vwc_forecast"]["metrics"]) >= 4
    assert result["irrigation_telemetry"]["valid_records"] == n


def test_tomato_adapter_keeps_parallel_sector_timeseries_separate():
    n = 1800
    timestamps = pd.date_range("2026-04-01", periods=n, freq="10min", tz="UTC")
    frames = []
    for sector, offset in (("open_field_a", 0.0), ("open_field_b", 1.5)):
        frames.append(pd.DataFrame({
            "timestamp": timestamps,
            "sector": sector,
            "vwc": 28.0 + offset - np.linspace(0, 4, n) + 0.2 * np.sin(np.arange(n) / 8),
            "water_l": np.where(np.arange(n) % 70 == 0, 0.8, 0.0),
        }))
    frame = pd.concat(frames, ignore_index=True)
    result = validate_tomato(
        frame,
        {"site": "sector", "vwc": "vwc", "irrigation_volume": "water_l"},
    )
    assert result["sector_or_file_count"] == 2
    assert result["quality"]["duplicate_timestamps"] == 0
    assert set(result["per_sector"]) == {"open_field_a", "open_field_b"}
    assert all(
        len(entry["vwc_forecast"]["metrics"]) >= 4
        for entry in result["per_sector"].values()
    )


def test_leaf_wetness_adapter_computes_daily_duration_and_site_ranking():
    records = []
    for site_idx, site in enumerate(("site_a", "site_b", "site_c")):
        ts = pd.date_range("2026-02-01 18:00", periods=72, freq="h", tz="Europe/Rome")
        for i, stamp in enumerate(ts):
            hour = stamp.hour
            wet = 80.0 if (hour < 3 + site_idx * 2 or (site_idx == 2 and hour >= 20)) else 15.0
            rh = 94.0 if wet > 50 else 65.0
            records.append({
                "timestamp": stamp, "station": site, "leaf_wetness": wet,
                "relative_humidity": rh, "air_temperature": 16.0 + site_idx,
            })
    result = validate_leafwetness(
        pd.DataFrame(records),
        {"site": "station"},
        timezone="Europe/Rome",
    )
    assert result["humid_pole_candidate_by_p90_nocturnal_lwd"] == "site_c"
    assert result["quality"]["duplicate_timestamps"] == 0
    assert len(result["daily_table"]) == 9
    assert len(result["nightly_table"]) == 9
    assert result["lwd_scope"] == "nocturnal_only_for_humid_pole_selection; daily_for_DSV"
    assert result["timezone"] == "Europe/Rome"
    assert result["nightly_table"]["nocturnal_leaf_wetness_hours"].between(0, 12).all()
    assert result["daily_table"]["leaf_wetness_hours"].between(0, 24).all()


def test_forecasting_supervised_rows_do_not_bridge_missing_timestamps():
    n = 420
    timestamps = pd.date_range("2026-05-01", periods=n, freq="10min", tz="UTC")
    values = 29.0 - np.linspace(0, 5, n) + 0.3 * np.sin(np.arange(n) / 8)
    continuous = pd.DataFrame({"timestamp": timestamps, "vwc": values})
    broken = continuous.drop(index=180).reset_index(drop=True)

    complete_rows, _ = _prepare_time_series(
        continuous, "timestamp", "vwc", horizon_steps=144
    )
    broken_rows, _ = _prepare_time_series(
        broken, "timestamp", "vwc", horizon_steps=144
    )
    assert len(broken_rows) < len(complete_rows)
    assert (complete_rows["__timestamp"].diff().dropna().dt.total_seconds() > 0).all()


def test_libelium_adapter_detects_gap_and_computes_two_node_sufficiency():
    base = pd.date_range("2026-03-01", periods=180, freq="10min", tz="UTC")
    rows = []
    for node, offset in (("Goraj-1", 3.0), ("Goraj-2", -2.0)):
        stamps = list(base)
        if node == "Goraj-2":
            stamps.pop(80)
            stamps.pop(80)
        for i, stamp in enumerate(stamps):
            rows.append({
                "timestamp": stamp, "device": node,
                "soil_vwc": 27.0 + offset + 2.0 * np.sin(i / 12),
            })
    frame = pd.DataFrame(rows)
    result = validate_libelium(frame, {"node": "device", "vwc": "soil_vwc"})
    assert set(result["node_quality"]) == {"Goraj-1", "Goraj-2"}
    assert result["two_node_sufficiency"] is not None
    assert result["two_node_sufficiency"]["paired_rows"] > 100
    assert result["quality"]["duplicate_timestamps"] == 0  # identical times across nodes are not duplicates
    assert result["node_quality"]["Goraj-2"]["gaps_over_threshold"] >= 1


def test_temporal_leakage_features_excluded():
    n = 300
    ts = pd.date_range("2026-01-01", periods=n, freq="10min", tz="UTC")
    target = 25.0 + 2.0 * np.sin(np.arange(n) / 10)
    frame = pd.DataFrame({
        "timestamp": ts,
        "soil_moisture": target,
        "air_temp": 20.0 + np.sin(np.arange(n) / 20),
        "target_point_24h": np.roll(target, -144),  # future leakage
        "water_vol_to_24h": np.full(n, 50.0),       # future leakage
        "real_moisture_delta": np.full(n, -0.5),    # future leakage
    })
    prepared, step = _prepare_time_series(frame, "timestamp", "soil_moisture", horizon_steps=144)
    # Ensure no column with leakage tokens survived in prepared features
    leakage_tokens = ("future", "target", "ahead", "label", "to_24h", "delta")
    feature_cols = [c for c in prepared.columns if c not in ("__target", "__timestamp")]
    for col in feature_cols:
        if col.startswith("origin_"):
            orig = col.replace("origin_", "")
            assert not any(t in orig.lower() for t in leakage_tokens), f"Leaked column found: {orig}"


def test_libelium_scaling_fractional_vwc():
    base = pd.date_range("2026-03-01", periods=180, freq="10min", tz="UTC")
    rows = []
    # Fractional m3/m3 values (e.g. 0.28 vs 0.15)
    for node, offset in (("Goraj-1", 0.05), ("Goraj-2", -0.08)):
        for i, stamp in enumerate(base):
            rows.append({
                "timestamp": stamp, "device": node,
                "teros11_vwc_m3_m3": 0.25 + offset + 0.02 * np.sin(i / 12),
            })
    frame = pd.DataFrame(rows)
    result = validate_libelium(frame, {"node": "device", "vwc": "teros11_vwc_m3_m3"})
    assert result["vwc_scale_factor"] == 100.0
    assert result["vwc_unit"] == "% VWC"
    assert result["two_node_sufficiency"] is not None
    # Divergence should be evaluated in % VWC (~13%), exceeding the 10% threshold
    assert result["two_node_sufficiency"]["latest_mean_abs_vwc_diff"] > 10.0
    assert result["two_node_sufficiency"]["insufficient_coverage_flag"] is True




def test_leafwetness_ignores_daytime_wetness_when_selecting_humid_pole():
    timestamps = pd.date_range("2026-02-01 18:00", periods=72, freq="h", tz="Europe/Rome")
    rows = []
    for site, wet_hours in (("daytime_wet", set(range(8, 18))), ("nighttime_wet", set(range(18, 24)) | set(range(0, 6)))):
        for stamp in timestamps:
            wet = stamp.hour in wet_hours
            rows.append({
                "timestamp": stamp,
                "station": site,
                "leaf_wetness": 90.0 if wet else 10.0,
                "relative_humidity": 95.0 if wet else 60.0,
                "air_temperature": 15.0,
            })
    result = validate_leafwetness(pd.DataFrame(rows), {"site": "station"}, timezone="Europe/Rome")
    assert result["humid_pole_candidate_by_p90_nocturnal_lwd"] == "nighttime_wet"
    p90 = result["site_p90_nocturnal_lwd_hours"]
    assert p90["daytime_wet"] == pytest.approx(0.0)
    assert p90["nighttime_wet"] == pytest.approx(12.0)


def test_purged_chronological_splits_do_not_share_forecast_target_periods():
    n = 2400
    timestamps = pd.date_range("2026-01-01", periods=n, freq="10min", tz="UTC")
    values = 27.0 + np.sin(np.arange(n) / 30)
    frame = pd.DataFrame({"timestamp": timestamps, "vwc": values})
    prepared, _ = _prepare_time_series(frame, "timestamp", "vwc", horizon_steps=144)
    train, validation, test, info = purged_chronological_indices(
        prepared["__timestamp"], prepared["__target_timestamp"]
    )
    train_end_label = prepared.iloc[train]["__target_timestamp"].max()
    validation_start = prepared.iloc[validation]["__timestamp"].min()
    validation_end_label = prepared.iloc[validation]["__target_timestamp"].max()
    test_start = prepared.iloc[test]["__timestamp"].min()
    assert train_end_label < validation_start
    assert validation_end_label < test_start
    assert info["purged_train_rows"] > 0
    assert info["purged_validation_rows"] > 0



def test_explicit_future_derived_forecast_features_are_rejected():
    n = 400
    timestamps = pd.date_range("2026-07-01", periods=n, freq="10min", tz="UTC")
    frame = pd.DataFrame({
        "timestamp": timestamps,
        "vwc": 25.0 + np.sin(np.arange(n) / 12),
        "future_dsv_target": np.where(np.arange(n) % 2, 1, 0),
    })
    with pytest.raises(ValueError, match="future-derived"):
        _prepare_time_series(
            frame,
            "timestamp",
            "vwc",
            horizon_steps=144,
            feature_cols=["future_dsv_target"],
        )
