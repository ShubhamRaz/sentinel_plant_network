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
    assert len(result["daily_table"]) == 12  # four calendar dates across 72 hours, per three sites
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


def test_humid_pole_candidate_selection_is_order_independent():
    """Verify that multi-tier humid-pole candidate selection is deterministic and invariant to input order.

    When multiple sites hit the saturation ceiling (P90 = 12.0h), the secondary criterion
    (highest mean nocturnal LWD among max-P90 tied sites) breaks the tie deterministically.
    """
    records_site_a = []
    records_site_b = []
    records_site_c = []
    ts = pd.date_range("2026-02-01 18:00", periods=72, freq="h", tz="UTC")

    for stamp in ts:
        hour = stamp.hour
        # Site A: wet during first 8 hours of night -> P90 = 12h, but lower mean
        is_night = (hour >= 18) or (hour < 6)
        wet_a = 90.0 if (is_night and hour < 2) else 10.0
        # Site B: wet during all 12 hours of night -> P90 = 12h, higher mean (~12h)
        wet_b = 95.0 if is_night else 10.0
        # Site C: rarely wet -> low P90
        wet_c = 10.0

        records_site_a.append({"timestamp": stamp, "station": "station_a", "leaf_wetness": wet_a, "relative_humidity": 90.0, "air_temperature": 15.0})
        records_site_b.append({"timestamp": stamp, "station": "station_b", "leaf_wetness": wet_b, "relative_humidity": 90.0, "air_temperature": 15.0})
        records_site_c.append({"timestamp": stamp, "station": "station_c", "leaf_wetness": wet_c, "relative_humidity": 90.0, "air_temperature": 15.0})

    df_a = pd.DataFrame(records_site_a)
    df_b = pd.DataFrame(records_site_b)
    df_c = pd.DataFrame(records_site_c)

    orderings = [
        pd.concat([df_a, df_b, df_c], ignore_index=True),
        pd.concat([df_b, df_a, df_c], ignore_index=True),
        pd.concat([df_c, df_a, df_b], ignore_index=True),
        pd.concat([df_c, df_b, df_a], ignore_index=True),
    ]

    selected_candidates = []
    for frame in orderings:
        res = validate_leafwetness(frame, {"site": "station"}, wet_threshold=20.0, timezone="UTC")
        selected_candidates.append(res["humid_pole_selection"]["selected_humid_pole_candidate"])

    # In every single ordering, station_b MUST be selected because of higher mean LWD
    assert all(c == "station_b" for c in selected_candidates), f"Got candidates: {selected_candidates}"


def test_cadence_aware_gap_detection_hourly_vs_ten_minute():
    """Verify that hourly time series uses 90-min threshold, while 10-min series uses 20-min threshold."""
    # 1. 10-minute series with one 40-minute gap (remove 3 consecutive 10-min readings)
    ts_10m = list(pd.date_range("2026-03-01 00:00", periods=50, freq="10min", tz="UTC"))
    del ts_10m[20:23]  # removes 3 steps, creating a 40-minute gap between step 19 and 20
    df_10m = pd.DataFrame({"ts": ts_10m, "val": 25.0})
    from real_data_validation import _quality_summary
    q_10m = _quality_summary(df_10m, "ts")
    assert q_10m["median_sampling_interval_minutes"] == 10.0
    assert q_10m["gap_threshold_minutes"] == 20.0
    assert q_10m["sampling_gaps"] == 1

    # 2. Hourly series (normal interval 60 min) with one 180-minute gap (remove 2 hourly readings)
    ts_1h = list(pd.date_range("2026-03-01 00:00", periods=50, freq="h", tz="UTC"))
    del ts_1h[25:27]  # removes 2 steps, creating a 3-hour (180 min) gap
    df_1h = pd.DataFrame({"time": ts_1h, "val": 15.0})
    q_1h = _quality_summary(df_1h, "time")
    assert q_1h["median_sampling_interval_minutes"] == 60.0
    assert q_1h["gap_threshold_minutes"] == 90.0
    # Crucially: normal 60-minute intervals are NOT counted as gaps
    assert q_1h["sampling_gaps"] == 1
    assert "gaps_over_20_minutes" not in q_1h
    assert "gaps_over_20_minutes" not in q_10m


def test_humid_pole_ranking_p90_tie_broken_by_mean():
    """When sites genuinely tie on P90 nocturnal LWD, the secondary criterion (highest mean) selects the winner."""
    n_nights = 40
    # 40 calendar days of hourly data (960 hours)
    ts = pd.date_range("2026-03-01 12:00", periods=n_nights * 24, freq="h", tz="UTC")

    records = []
    for stamp in ts:
        hour = stamp.hour
        is_night = (hour >= 18) or (hour < 6)
        # Night date: if hour >= 18, belongs to stamp.date(); if hour < 6, belongs to stamp.date() - 1 day
        night_idx = (stamp.date() - pd.Timestamp("2026-03-01").date()).days
        if hour < 6:
            night_idx -= 1

        # station_alpha (alphabetically earlier): wet for 12h on 6 nights out of 40 (15% > 10% -> P90 = 12.0h, Mean = 1.8h)
        wet_alpha = 90.0 if (is_night and 0 <= night_idx < 6) else 10.0
        # station_beta (alphabetically later): wet for 12h on 30 nights out of 40 (75% -> P90 = 12.0h, Mean = 9.0h)
        wet_beta = 90.0 if (is_night and 0 <= night_idx < 30) else 10.0

        records.append({"timestamp": stamp, "station": "station_alpha", "leaf_wetness": wet_alpha, "relative_humidity": 90.0, "air_temperature": 15.0})
        records.append({"timestamp": stamp, "station": "station_beta", "leaf_wetness": wet_beta, "relative_humidity": 90.0, "air_temperature": 15.0})

    df = pd.DataFrame(records)
    res = validate_leafwetness(df, {"site": "station"}, wet_threshold=20.0, timezone="UTC")

    p90_alpha = res["site_p90_nocturnal_lwd_hours"]["station_alpha"]
    p90_beta = res["site_p90_nocturnal_lwd_hours"]["station_beta"]
    mean_alpha = res["site_mean_nocturnal_lwd_hours"]["station_alpha"]
    mean_beta = res["site_mean_nocturnal_lwd_hours"]["station_beta"]

    # 1. Independently verify that both stations have an exact P90 tie at the 12-hour saturation ceiling
    assert p90_alpha == pytest.approx(12.0), f"Expected P90=12.0 for station_alpha, got {p90_alpha}"
    assert p90_beta == pytest.approx(12.0), f"Expected P90=12.0 for station_beta, got {p90_beta}"
    assert p90_alpha == p90_beta, "Test design error: P90 values must be genuinely identical"

    # 2. Verify that their mean nocturnal LWD values differ substantially
    assert mean_beta == pytest.approx(9.0), f"Expected Mean=9.0 for station_beta, got {mean_beta}"
    assert mean_alpha == pytest.approx(1.8), f"Expected Mean=1.8 for station_alpha, got {mean_alpha}"
    assert mean_beta > mean_alpha, "station_beta must have higher mean than station_alpha"

    # 3. Verify that the higher-mean station is selected
    assert res["humid_pole_selection"]["selected_humid_pole_candidate"] == "station_beta"
    assert res["humid_pole_selection"]["primary_max_p90_hours"] == 12.0
    assert set(res["humid_pole_selection"]["tied_p90_candidate_sites"]) == {"station_alpha", "station_beta"}

    # 4. Demonstrate selection occurs because of secondary criterion (mean), not tertiary (which would pick station_alpha)
    assert "station_alpha" < "station_beta", "Alphabetical order must favor station_alpha"
    assert res["humid_pole_selection"]["selected_humid_pole_candidate"] != "station_alpha", (
        "station_alpha was wrongly selected by alphabetical order instead of higher mean!"
    )


def test_humid_pole_ranking_p90_and_mean_tie_broken_by_alphabetical():
    """When sites tie on both P90 and mean nocturnal LWD, the tertiary criterion (alphabetically smallest) selects the winner."""
    records = []
    ts = pd.date_range("2026-02-01 18:00", periods=72, freq="h", tz="UTC")
    for stamp in ts:
        hour = stamp.hour
        is_night = (hour >= 18) or (hour < 6)
        # Identical wetness profiles for site_zeta and site_alpha
        wet = 95.0 if is_night else 10.0
        records.append({"timestamp": stamp, "station": "site_zeta", "leaf_wetness": wet, "relative_humidity": 90.0, "air_temperature": 15.0})
        records.append({"timestamp": stamp, "station": "site_alpha", "leaf_wetness": wet, "relative_humidity": 90.0, "air_temperature": 15.0})

    df = pd.DataFrame(records)
    res = validate_leafwetness(df, {"site": "station"}, wet_threshold=20.0, timezone="UTC")
    assert res["site_p90_nocturnal_lwd_hours"]["site_zeta"] == res["site_p90_nocturnal_lwd_hours"]["site_alpha"]
    assert res["site_mean_nocturnal_lwd_hours"]["site_zeta"] == res["site_mean_nocturnal_lwd_hours"]["site_alpha"]
    assert res["humid_pole_selection"]["selected_humid_pole_candidate"] == "site_alpha"
    assert res["humid_pole_selection"]["tertiary_criterion"] == "alphabetically smallest site identifier"


def test_humid_pole_ranking_row_and_file_shuffling_permutation_invariance():
    """Permuting row order and station file concatenation order preserves deterministic 3-tier candidate selection."""
    records_alpha = []
    records_beta = []
    records_gamma = []
    ts = pd.date_range("2026-02-01 18:00", periods=72, freq="h", tz="UTC")
    for stamp in ts:
        hour = stamp.hour
        is_night = (hour >= 18) or (hour < 6)
        # alpha and beta tie on P90 (12h) and mean (12h); gamma has lower mean
        records_alpha.append({"timestamp": stamp, "station": "station_alpha", "leaf_wetness": 95.0 if is_night else 10.0, "relative_humidity": 90.0, "air_temperature": 15.0})
        records_beta.append({"timestamp": stamp, "station": "station_beta", "leaf_wetness": 95.0 if is_night else 10.0, "relative_humidity": 90.0, "air_temperature": 15.0})
        records_gamma.append({"timestamp": stamp, "station": "station_gamma", "leaf_wetness": 90.0 if (is_night and hour < 2) else 10.0, "relative_humidity": 90.0, "air_temperature": 15.0})

    df_a = pd.DataFrame(records_alpha)
    df_b = pd.DataFrame(records_beta)
    df_g = pd.DataFrame(records_gamma)

    # Test multiple row and file permutations
    combined = pd.concat([df_b, df_g, df_a], ignore_index=True)
    for seed in [42, 123, 999, 2026]:
        shuffled = combined.sample(frac=1.0, random_state=seed).reset_index(drop=True)
        res = validate_leafwetness(shuffled, {"site": "station"}, wet_threshold=20.0, timezone="UTC")
        assert res["humid_pole_selection"]["selected_humid_pole_candidate"] == "station_alpha", (
            f"Failed on seed {seed}: got {res['humid_pole_selection']['selected_humid_pole_candidate']}"
        )


