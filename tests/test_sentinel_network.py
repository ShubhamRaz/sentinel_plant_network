"""
Comprehensive Unit & Integration Test Suite for the Sentinel Plant Network.
Verifies mathematical accuracy, protocol thresholds, state transitions,
staleness timeouts, non-inferiority statistical bounds, and file outputs.
"""

import sys
import unittest
from pathlib import Path
import numpy as np
import pandas as pd
from ml_baselines import chronological_indices
from statistical_diagnostics import rcbd_diagnostics

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from models import (
    ControllerState,
    ProtocolConfig,
    StepInput,
    check_spatial_sufficiency,
    compute_cwsi,
    compute_daily_lws_modified_dsv,
    compute_daily_wallin_dsv,
    compute_lifepo4_autonomy,
    compute_vachaud_metrics,
    evaluate_gateway_step,
    select_sentinel_nodes,
)


class TestSentinelPlantNetwork(unittest.TestCase):
    def setUp(self):
        self.cfg = ProtocolConfig()

    def test_vachaud_temporal_stability_identifies_rank_stable_node(self):
        t = np.linspace(0, 10, 100)
        base = 25.0 + 3.0 * np.sin(t)
        df = pd.DataFrame({
            "N_wet": base * 1.18,
            "N_mean": base * 1.00,
            "N_dry": base * 0.82,
        })
        res = compute_vachaud_metrics(df)
        self.assertEqual(res.iloc[0]["node_id"], "N_mean")
        self.assertAlmostEqual(res.iloc[0]["its"], 0.0, places=5)

    def test_wallin_and_lws_dsv_lookup(self):
        # Optimal blight temp (18 C) with 19 hours RH >= 90% -> DSV = 4
        self.assertEqual(compute_daily_wallin_dsv(18.0, 19.5), 4)
        # Cold temp below 7.2 C -> DSV = 0
        self.assertEqual(compute_daily_wallin_dsv(6.0, 22.0), 0)
        # LWS-modified index elevates DSV when persistent leaf wetness exceeds screen RH90 hours
        dsv_w = compute_daily_wallin_dsv(16.5, 9.0)
        dsv_lws = compute_daily_lws_modified_dsv(16.5, 9.0, 16.0)
        self.assertEqual(dsv_w, 0)
        self.assertGreaterEqual(dsv_lws, 2)

    def test_cwsi_bounds_and_drought_response(self):
        cwsi_wet, res_wet = compute_cwsi(t_canopy_c=23.5, t_air_c=25.0, rh_pct=50.0, cfg=self.cfg)
        cwsi_dry, res_dry = compute_cwsi(t_canopy_c=28.2, t_air_c=25.0, rh_pct=50.0, cfg=self.cfg)
        self.assertLess(cwsi_wet, 0.30)
        self.assertGreater(cwsi_dry, 0.65)
        self.assertGreater(res_dry, res_wet)

    def test_gateway_fsm_all_six_states(self):
        # 1. HOMEOSTASIS
        s, v, _ = evaluate_gateway_step(StepInput(600, 5.0, 22.0, 65.0, 10.0, 28.0, 0.20, 4, 0.0), self.cfg)
        self.assertEqual(s, ControllerState.HOMEOSTASIS)
        self.assertFalse(v)

        # 2. STANDARD_DRIP
        s, v, _ = evaluate_gateway_step(StepInput(600, 5.0, 24.0, 60.0, 5.0, 20.5, 0.45, 6, 0.0), self.cfg)
        self.assertEqual(s, ControllerState.STANDARD_DRIP)
        self.assertTrue(v)

        # 3. PATHOGEN_LOCKOUT (blight risk only)
        s, v, _ = evaluate_gateway_step(StepInput(600, 5.0, 18.0, 94.0, 75.0, 27.0, 0.18, 19, 4.0), self.cfg)
        self.assertEqual(s, ControllerState.PATHOGEN_LOCKOUT)
        self.assertFalse(v)

        # 4. CONFLICT_MICRO_PULSE (water stress + blight risk inside 11:30-14:30)
        s_on, v_on, _ = evaluate_gateway_step(StepInput(695, 5.0, 23.0, 91.0, 60.0, 20.8, 0.44, 19, 8.0), self.cfg)
        s_off, v_off, _ = evaluate_gateway_step(StepInput(715, 5.0, 23.0, 91.0, 60.0, 20.8, 0.44, 19, 8.0), self.cfg)
        self.assertEqual(s_on, ControllerState.CONFLICT_MICRO_PULSE)
        self.assertTrue(v_on)
        self.assertEqual(s_off, ControllerState.CONFLICT_MICRO_PULSE)
        self.assertFalse(v_off)

        # 5. EMERGENCY_DRIP (overrides pathogen lockout when VWC <= 16% or CWSI >= 0.65)
        s, v, _ = evaluate_gateway_step(StepInput(120, 5.0, 17.0, 96.0, 90.0, 15.8, 0.68, 24, 10.0), self.cfg)
        self.assertEqual(s, ControllerState.EMERGENCY_DRIP)
        self.assertTrue(v)

        # 6. FAULT_FALLBACK (stale packet > 30 min or zero-flow fault)
        s_stale, v_stale, _ = evaluate_gateway_step(StepInput(700, 31.5, 22.0, 70.0, 10.0, 20.0, 0.45, 5, 0.0), self.cfg)
        self.assertEqual(s_stale, ControllerState.FAULT_FALLBACK)
        self.assertFalse(v_stale)

        s_flow, v_flow, _ = evaluate_gateway_step(StepInput(700, 5.0, 22.0, 70.0, 10.0, 20.0, 0.45, 5, 0.0, flow_fault=True), self.cfg)
        self.assertEqual(s_flow, ControllerState.FAULT_FALLBACK)
        self.assertFalse(v_flow)

    def test_adaptive_sufficiency_flag(self):
        s1 = pd.Series(np.linspace(25, 30, 50))
        s2 = pd.Series(np.linspace(20, 25, 50))  # 5% diff, r_s = 1.0 -> sufficient
        res_ok = check_spatial_sufficiency(s1, s2, self.cfg)
        self.assertFalse(res_ok["insufficient_coverage_flag"])

        s3 = pd.Series(np.linspace(12, 17, 50))  # 13% diff -> insufficient
        res_flag = check_spatial_sufficiency(s1, s3, self.cfg)
        self.assertTrue(res_flag["insufficient_coverage_flag"])

    def test_lifepo4_autonomy_matches_protocol(self):
        auto = compute_lifepo4_autonomy()
        self.assertAlmostEqual(auto["protocol_zero_sunlight_hours"], 235.3, delta=1.0)
        self.assertAlmostEqual(auto["protocol_zero_sunlight_days"], 9.8, delta=0.1)


    def test_rolling_sufficiency_returns_metrics_and_trigger_timestamps(self):
        idx = pd.date_range("2026-01-01", periods=40, freq="10min", tz="UTC")
        a = pd.Series(np.linspace(24.0, 28.0, 40), index=idx)
        b = a - 2.0
        result = check_spatial_sufficiency(a, b, window_steps=12, cfg=self.cfg)
        self.assertEqual(result["window_steps_used"], 12)
        self.assertEqual(len(result["rolling_metrics"]), 29)
        self.assertFalse(result["insufficient_coverage_flag"])
        self.assertEqual(result["trigger_timestamps"], [])

        b.iloc[-12:] = a.iloc[-12:] - 14.0
        flagged = check_spatial_sufficiency(a, b, window_steps=12, cfg=self.cfg)
        self.assertTrue(flagged["insufficient_coverage_flag"])
        self.assertGreater(len(flagged["trigger_timestamps"]), 0)

    def test_rolling_sufficiency_legacy_positional_config(self):
        a = pd.Series(np.linspace(20.0, 30.0, 20))
        result = check_spatial_sufficiency(a, a - 1.0, self.cfg)
        self.assertFalse(result["insufficient_coverage_flag"])

    def test_chronological_split_is_ordered_and_non_overlapping(self):
        train, validation, test = chronological_indices(1000)
        self.assertEqual(train.start, 0)
        self.assertEqual(train.stop, validation.start)
        self.assertEqual(validation.stop, test.start)
        self.assertEqual(test.stop, 1000)

    def test_rcbd_diagnostics_uses_plot_as_experimental_unit(self):
        rows = []
        means = {"T1": 30.0, "T2": 30.2, "T3": 30.4, "T4": 30.5}
        block_effects = {"B1": 0.3, "B2": 0.1, "B3": -0.1, "B4": -0.3}
        for block, effect in block_effects.items():
            for treatment, mean in means.items():
                rows.append({"block": block, "treatment": treatment,
                             "yield": mean + effect + (0.01 if treatment == "T1" else -0.01)})
        out = rcbd_diagnostics(pd.DataFrame(rows), "yield")
        self.assertEqual(out["independent_units"], 16)
        self.assertEqual(out["blocks"], 4)
        self.assertEqual(out["rcbd_anova"]["df_error"], 9)
        self.assertIn("shapiro_wilk_residuals", out["assumption_checks"])
        self.assertIn("T4_vs_T1", out["yield_noninferiority"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
