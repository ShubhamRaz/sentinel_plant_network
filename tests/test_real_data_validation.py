import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from real_data_validation import (
    validate_libelium,
    validate_leafwetness,
    validate_tomato,
)


def test_tomato_adapter_reports_quality_and_forecast():
    n = 450
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


def test_leaf_wetness_adapter_computes_daily_duration_and_site_ranking():
    records = []
    for site_idx, site in enumerate(("site_a", "site_b", "site_c")):
        ts = pd.date_range("2026-02-01", periods=72, freq="h", tz="UTC")
        for i, stamp in enumerate(ts):
            wet = 80.0 if (i % 24) < 8 + site_idx * 3 else 15.0
            rh = 94.0 if wet > 50 else 65.0
            records.append({
                "timestamp": stamp, "station": site, "leaf_wetness": wet,
                "relative_humidity": rh, "air_temperature": 16.0 + site_idx,
            })
    result = validate_leafwetness(
        pd.DataFrame(records),
        {"site": "station"},
    )
    assert result["humid_pole_candidate_by_p90_daily_lwd"] == "site_c"
    assert result["quality"]["duplicate_timestamps"] == 0
    assert len(result["daily_table"]) == 9
    assert result["daily_table"]["leaf_wetness_hours"].between(0, 24).all()


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
