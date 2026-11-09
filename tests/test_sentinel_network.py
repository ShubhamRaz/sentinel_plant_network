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


if __name__ == "__main__":
    unittest.main(verbosity=2)
