# Sentinel Plant Network — Supplementary Research Materials Package

**Manuscript Title:** Risk-Oriented Dual-Pole Sparse Sensing and Uncertainty-Aware Irrigation Decision Support for Solanaceous Crops: Architecture, Synthetic Digital-Twin Benchmarks, and External Validation Protocol  
**Protocol Version:** Protocol v2.0  
**Research Group:** Sentinel Plant Network Research Group  
**Repository Branch:** `release/journal-supplementary-package`  

---

## 1. Overview and Purpose of this Package

This directory contains the complete supplementary data, tables, figures, metadata justifications, statistical diagnostics, and reproducible outputs supporting the Sentinel Plant Network journal publication.

All reported empirical metrics, spatial sufficiency triggers, and machine-learning forecasting scores are directly generated from the evaluated open-access benchmark datasets and can be independently verified using the checksums and scripts provided herein.

---

## 2. Directory Structure

```
supplementary_materials/
├── README.md                                  # This master index and guide
├── S1_DATASET_PROVENANCE_AND_ATTRIBUTION.md  # Dataset citations, DOIs, licenses, metadata, and timezone/threshold justifications
├── S2_EXPERIMENTAL_METHODOLOGY_AND_CLEANING.md # Telemetry ingestion, timestamp alignment, sensor scaling, and QC filters
├── S3_ML_FORECASTING_AND_EMBARGO_PROTOCOL.md # Chronological splits, 144-step embargo purge, feature engineering, and model metrics
├── S4_STATISTICAL_DIAGNOSTICS_REPORT.md      # RCBD ANOVA, Shapiro-Wilk, Levene test, 5% non-inferiority, and REML MixedLM
├── S5_REPRODUCIBILITY_AND_ENVIRONMENT.md     # Execution instructions, Python environment, dependencies, and CI workflow
├── CHECKSUMS_SHA256.txt                      # Cryptographic SHA-256 checksums for all supplementary files
├── datasets_manifest.json                    # Machine-readable input file provenance manifest with SHA-256 hashes
├── dataset_catalog.json                      # Authoritative dataset catalog recording scope and metadata
├── tables/                                   # Empirical and simulation tabular outputs (CSV & JSON)
│   ├── tomato_vwc_forecasting_metrics.csv    # 24h VWC forecast metrics across models and zones (held-out test split)
│   ├── leafwetness_nightly_lwd.csv           # 348 nights of nocturnal LWD across 7 microclimate stations
│   ├── leafwetness_daily_dsv.csv             # Daily Wallin vs. LWS-modified Disease Severity Values
│   ├── libelium_rolling_sufficiency.csv      # 1,340 trailing 48h rolling evaluation windows
│   ├── phase1_topology_comparison.csv        # Placement strategy comparison across 10-node network
│   ├── phase1_vachaud_stability_table.csv    # Vachaud mean relative difference and temporal stability ranking
│   ├── phase2_rcbd_16plots_summary.csv       # Plot-level responses (yield, water, LWD, AUDPC) across 16 RCBD plots
│   ├── statistical_analysis_summary.json     # ANOVA, Fisher LSD, non-inferiority, and REML MixedLM summary
│   ├── statistical_diagnostics.json          # Residual Shapiro-Wilk and Levene homoscedasticity diagnostics
│   └── gateway_fault_and_state_verification.csv # Controller state machine transitions across 9 fault scenarios
└── figures/                                  # High-resolution vector (PDF) and raster (PNG) publication figures
    ├── tomato_vwc_forecasting_benchmark.png  # Test RMSE and MAE across forecasting baselines
    ├── leafwetness_microclimate_dsv_ranking.png # P90 nocturnal LWD bar chart and daily DSV boxplot
    ├── libelium_two_node_spatial_sufficiency.png # Trailing 48h divergence and Spearman rs with active trigger shading
    ├── fig1_vachaud_and_pole_selection.pdf & .png # Vachaud ranking and dual-pole extreme placement
    ├── fig2_phase1_topology_benchmark.pdf & .png  # Spatial sampling topology comparison
    ├── fig3_t4_seasonal_controller_trace.pdf & .png # 90-day T4 controller telemetry trace
    ├── fig4_phase2_rcbd_outcomes.pdf & .png       # Yield, water, and pathology RCBD distributions
    └── fig5_autonomy_and_sufficiency.pdf & .png   # LiFePO4 battery blackout trajectory and emitter clog trigger
```

---

## 3. Dataset Attribution and Verification Summary

| Dataset | Mendeley DOI | Version | License | Primary Purpose | Verified Metadata |
| :--- | :--- | :---: | :---: | :--- | :--- |
| **Tomato Precision Irrigation** | [10.17632/c837v6p8ph.2](https://doi.org/10.17632/c837v6p8ph.2) | V2 | CC BY 4.0 | 24h VWC forecasting & irrigation telemetry | 10-min cadence; 144-step embargo purge; forward-looking target tokens stripped; `water_vol_past_4h` flagged as non-cumulative. |
| **Seven-Site Leaf Wetness** | [10.17632/sd4b8vpvyb.1](https://doi.org/10.17632/sd4b8vpvyb.1) | V1 | CC BY-NC 4.0 | Microclimatic LWD diversity & Wallin vs. LWS DSV | Timestamps verified as **UTC**; sensor calibrated benchmark is **50.0%** (Filipescu et al., 2024, IEEE Trans. AgriFood Electronics, DOI: 10.1109/TAFE.2024.3401252); protocol dew-onset early-warning threshold evaluated at **20.0%**; nocturnal 18:00–06:00 UTC window enforced; exactly 153 missing hourly observation gaps detected across all 7 sites. |
| **Libelium Two-Node Olive Grove** | [10.17632/cnfh4stzzx.2](https://doi.org/10.17632/cnfh4stzzx.2) | V2 | CC BY 4.0 | Two-node telemetry quality & spatial decoupling | VWC converted from $\text{m}^3/\text{m}^3$ to % VWC; ProtocolConfig $r_s < 0.70$ threshold yields 873 triggers (65.1%). |

---

## 4. Key Verified Research Findings

1. **Purged Chronological 24h VWC Forecasting & Metric Trade-Offs:**
   - On strictly non-overlapping, 144-step embargoed test partitions, **GBDT achieves 0.914% VWC RMSE (MAE 0.377% VWC, $R^2 = +0.028$) in Zone 1**, reducing RMSE by 23.6% over naive persistence (1.196% VWC).
   - In Zone 2, **Ridge regression achieves 0.593% VWC RMSE (MAE 0.347% VWC, $R^2 = +0.165$)**, reducing RMSE by 13.9% over persistence (0.689% VWC).
   - *Absence of General ML Superiority:* Because supervised models optimize squared error ($L_2$ loss), they smooth predictions and reduce peak excursions, but exhibit higher MAE than naive persistence (0.242% in Zone 1; 0.150% in Zone 2), which incurs near-zero absolute deviation during quiet dry-down periods. Test $R^2$ values are modest (+0.028 and +0.165), and the 100% drought recall is an artifact of all test instances remaining below 22% VWC during the evaluated late-season partition.
2. **Microclimatic Humid-Pole Selection & Tie Handling:**
   - Nocturnal leaf-wetness duration (18:00–06:00 UTC, 20% protocol threshold) identifies five candidate sites reaching the 12-hour saturation ceiling ($P_{90} = 12.0\text{ h/night}$).
   - Applying a secondary selection criterion (highest mean nocturnal LWD among max-$P_{90}$ candidates) deterministically isolates **Site 2 as candidate Node A** (seasonal mean 11.23 h/night at 20%; 9.49 h/night at 50%), whereas high-elevation Site 6 exhibits mean nocturnal wetness of only 0.98 h/night. Candidate selection is invariant to the threshold (20% vs. 50%) and input file order.
   - Physical leaf-wetness sensor integration ($\mathrm{DSV}_{\mathrm{LWS}}$) captures extended nocturnal dew when ambient relative humidity drops into the 80–89% range, where standard weather station $\mathrm{DSV}_{\text{Wallin}}$ ($\text{RH} \ge 90\%$) records zero risk accumulation.
3. **Adaptive Two-Node Spatial Sufficiency:**
   - Across 1,617 aligned observations in an Albanian olive grove, trailing 48-hour Spearman rank correlation dropped to $r_s = -0.739$ with a mean absolute divergence of 4.07% VWC.
   - Under Protocol v2.0's $r_s < 0.70$ threshold, **873 trailing windows triggered $\mathcal{F}_{\text{insuff}} = 1$ (65.1%)**, demonstrating that natural topographical heterogeneity causes frequent micro-zone decoupling and confirming the operational necessity of adaptive spatial sufficiency monitoring.
4. **Digital-Twin Statistical Power:**
   - In the 16-plot RCBD simulation, T4 achieves a 25.8% simulated water reduction (247.8 mm vs. 334.0 mm for full $\text{ET}_c$) and non-inferior marketable yield ($\Delta Y = +1.383\text{ t ha}^{-1}$, 95% lower confidence bound $L_{95} = +1.122\text{ t ha}^{-1} > M_{\text{T1}} = -1.651\text{ t ha}^{-1}$, $p = 2.55 \times 10^{-9}$).
   - Residual assumption tests confirm absence of gross departures (Shapiro-Wilk $p = 0.5002$, Levene $p = 0.2528$). Repeated-measures REML MixedLM confirms substantial plot clustering ($\text{ICC} = 0.5935$).

---

## 5. Evidence Boundaries

All metrics presented in this package derive from reproducible digital-twin simulations and open-access benchmark datasets from Mediterranean and European agro-ecosystems. They validate the mathematical algorithms, data pipelines, control finite state machines, and statistical methodology. They do not constitute an agronomic field trial in the target environment (Jharkhand, India). Future physical research tasks (sensor calibration, LoRa bench testing, and planting-season agronomic trials) are specified in [`HARDWARE_BENCH_TEST_PLAN.md`](../HARDWARE_BENCH_TEST_PLAN.md) and Section 7 of the manuscript.
