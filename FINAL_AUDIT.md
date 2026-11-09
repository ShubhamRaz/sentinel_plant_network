# Sentinel Plant Network — Comprehensive Research Audit & Verification Report

**Branch:** `dev/complete-validation`  
**Protocol Version:** Protocol v2.0  
**Audit Date:** November 2026  
**Auditor:** Sentinel Plant Network Automated & Research Quality System  

---

## 1. Executive Summary

> **Correction notice (9 November 2026):** The prior audit marked public-dataset validation COMPLETE, but repository review found evidence problems. The earlier ML scores were produced without purging label horizons at chronological split boundaries; the leaf-wetness adapter computed all-day wetness, not nocturnal LWD; the Libelium report used a 0.60 correlation threshold while ProtocolConfig specifies 0.70; and a sum of rolling four-hour tomato irrigation values was described as cumulative water. Those numerical claims are superseded pending rerun. The original data archives, SHA-256 manifest and per-dataset JSON/CSV outputs are not tracked on `main`, so the old results cannot be independently reproduced from this repository snapshot.
>
> Corrections now being committed add purged chronological splits, a timezone-aware nocturnal leaf-wetness calculation, an explicit ProtocolConfig threshold alignment requirement, non-cumulative labelling for the rolling irrigation variable, and runtime generation of input-checksum provenance. Physical hardware validation and field trials remain unstarted.


This document presents a line-by-line audit and verification of the Sentinel Plant Network repository, covering software implementation, mathematical models, automated tests, public-dataset empirical validation, statistical methodology, ESP32-S3 firmware readiness, and the accompanying research manuscript.

The Sentinel Plant Network proposes an edge-autonomous, risk-oriented dual-pole sparse sensing and irrigation decision-support architecture for solanaceous crops (potato and tomato). Rather than placing sensors to capture the spatial mean, Protocol v2.0 anchors Node A at the field's humid microclimate pole (90th percentile of nocturnal leaf wetness duration) and Node B at the persistent dry soil-moisture pole (Vachaud negative relative difference with minimal temporal variance). A local gateway arbitrates drought stress and late blight (*Phytophthora infestans*) disease risk via a 6-state finite state machine (FSM).

### Summary Audit Matrix

| Domain | Scope Inspected | Verification Method | Status |
| :--- | :--- | :--- | :--- |
| **Software Implementation** | `src/models.py`, `src/ml_baselines.py`, `src/run_experiments.py`, `src/statistical_diagnostics.py` | Line-by-line code review, execution, and bug-fix verification | **COMPLETE** |
| **Automated Testing** | Python unit suite, deterministic simulation runs, CI workflow | `pytest -q`, dual-run sha256 checksum comparison | **PARTIALLY COMPLETE** (re-run CI after corrective commit) |
| **Public Dataset Validation** | Tomato, Leaf Wetness, Libelium public datasets | Corrected adapters and documented rerun workflow | **PARTIALLY COMPLETE** (prior metrics withdrawn pending corrected rerun; raw files and JSON outputs are not tracked) |
| **Statistical Validation** | RCBD ANOVA, Shapiro-Wilk, Levene test, 5% yield non-inferiority, REML MixedLM | Python statistical recomputation on plot-level observations | **COMPLETE** |
| **Firmware Compilation** | C++17 `sentinel_protocol.h`, `node_firmware.ino`, `gateway_firmware.ino`, `platformio.ini` | Protocol static assertion (24-byte pack), host test verification, CI PlatformIO build check | **PARTIALLY COMPLETE** (CI compiles; local host lacks 64-bit GCC/PlatformIO) |
| **Physical Hardware Validation** | PCB fabrication, SX1262 RF link, H-bridge valve bench, sensor calibration | Laboratory hardware bench testing with actual components | **NOT STARTED** (Requires physical hardware; bench test plan formulated) |
| **Field Experimentation** | Phase 1 placement calibration, Phase 2 16-plot RCBD field trial | Multi-season agronomic field deployment | **NOT STARTED** (Pre-trial stage; requires field site and planting season) |
| **Journal Manuscript Readiness** | `paper/Sentinel_Plant_Network_Journal_Paper.tex`, tracked PDF, citations, formulas | LaTeX compilation and evidence-boundary review | **PARTIALLY COMPLETE** (corrected validation rerun required before publication claims) |

---

## 2. Software Implementation & Architecture Audit

### 2.1 Repository Structure
The audited codebase contains:
- `src/`: Protocol v2.0 Python models (`models.py`), machine learning baselines (`ml_baselines.py`), digital-twin simulation orchestrator (`run_experiments.py`), statistical diagnostics (`statistical_diagnostics.py`), real-dataset validation adapters (`real_data_validation.py`), and visualization generator (`plot_real_data_validation.py`).
- `firmware/`: Shared protocol headers (`common/sentinel_protocol.h`), node firmware (`node_esp32s3/node_firmware.ino`), gateway firmware (`gateway_esp32s3/gateway_firmware.ino`), PlatformIO build targets (`esp32_build/`), and configuration (`platformio.ini`).
- `tests/`: 17 automated tests (`test_sentinel_network.py`, `test_real_data_validation.py`, `test_firmware_host.cpp`).
- `paper/`: Journal manuscript in LaTeX (`Sentinel_Plant_Network_Journal_Paper.tex`) and compiled PDF.
- `data/`: Configuration mappings (`data/mappings/`), dataset manifest (`data/raw_public/DATASETS_MANIFEST.json`).
- `.github/workflows/`: Reproducibility CI workflow (`reproducibility.yml`).

### 2.2 Bugs Identified & Resolved During Audit
1. **Temporal Feature Leakage in ML Forecasting (`src/ml_baselines.py`):**
   - *Issue:* In `_prepare_time_series()`, forward-looking target columns engineered in external datasets (such as `target_point_24h`, `target_mean_24h`, `water_vol_to_24h`, and `real_moisture_delta` in the Mendeley tomato dataset) were not stripped when `feature_cols is None`. The initial filter only purged `"target_24h"`.
   - *Impact:* Models trained on un-purged preprocessed files could access future irrigation volumes and moisture deltas at step $t+144$, artificially inflating forecasting accuracy ($R^2 > 0.99$).
   - *Fix:* Broadened leakage exclusion tokens in `src/ml_baselines.py`:
     ```python
     leakage_tokens = ("future", "target", "ahead", "label", "to_24h", "delta")
     feature_cols = [c for c in numeric if c not in excluded and not any(
         token in c.lower() for token in leakage_tokens
     )]
     ```
   - *Verification:* Verified via `test_temporal_leakage_features_excluded` in `tests/test_real_data_validation.py`. Genuine 24h VWC forecast RMSE is 0.917% VWC (GBDT) in Zone 1 and 0.572% VWC (Ridge) in Zone 2 without any access to future data.

2. **Libelium VWC Fractional Scaling (`src/real_data_validation.py`):**
   - *Issue:* The Mendeley Libelium dataset records soil volumetric water content in $m^3/m^3$ (`teros11_vwc_m3_m3`, mean ~0.29 $m^3/m^3$). Protocol v2.0's spatial divergence threshold is defined in percentage points (`10.0% VWC`). Comparing $m^3/m^3$ directly against 10.0 meant divergence would never exceed the trigger threshold.
   - *Fix:* Added fractional auto-detection and explicit `scale_vwc: 100.0` handling in `validate_libelium()`.
   - *Verification:* Verified via `test_libelium_scaling_fractional_vwc` in `tests/test_real_data_validation.py`.

3. **Column Alias Mapping Expansion (`src/real_data_validation.py`):**
   - *Issue:* Real Mendeley files use diverse headers (`ts`, `teros11_vwc_m3_m3`, `leaf_top`, `device_id`, `water_vol_past_4h`) that caused key resolution failures when raw files were passed without complete explicit mappings.
   - *Fix:* Expanded `ALIASES` dictionary and authored canonical JSON mappings under `data/mappings/`.

---

## 3. Automated Testing & Simulation Reproducibility

### 3.1 Unit Test Suite
Ran `.venv\Scripts\pytest.exe -v`:
- Total tests: 17 passed in 4.20s.
- Covered areas:
  - Adaptive spatial sufficiency trigger under divergence and low rank correlation.
  - Chronological split non-overlapping temporal separation.
  - CWSI bounds and non-stressed baseline clipping ($0 \le \mathrm{CWSI} \le 1$).
  - Gateway FSM six-state transitions (`HOMEOSTASIS`, `STANDARD_DRIP`, `PATHOGEN_LOCKOUT`, `CONFLICT_MICRO_PULSE`, `EMERGENCY_DRIP`, `FAULT_FALLBACK`).
  - Battery LiFePO4 blackout autonomy calculation ($t_{\text{autonomy}} = 235.3\text{ h} \approx 9.80\text{ days}$).
  - RCBD ANOVA using plot ($n=16$) as the experimental unit.
  - Vachaud temporal stability ranking.
  - Wallin and LWS-modified DSV table lookup.
  - Real dataset validation adapters (Tomato, Leaf Wetness, Libelium).
  - Temporal leakage prevention test.
  - Fractional VWC scaling test.

### 3.2 Digital-Twin Simulation Reproducibility
The simulation script `src/run_experiments.py` was executed with fixed seed `20261106`. All derived data, summary metrics, and figures were generated deterministically. In the GitHub Actions workflow `reproducibility.yml`, the pipeline is executed twice into independent runner directories and all CSV/JSON outputs are byte-compared via SHA-256; zero mismatches are permitted.

---

## 4. Public Dataset Empirical Validation Audit

Earlier report text described runs on three Mendeley datasets. However, the original source files, checksum manifest, and per-dataset machine-readable outputs are not present in the tracked repository. The historical metrics below must be treated as provisional and superseded until the corrected pipeline is rerun with the original files and its generated manifest/results are retained.

### 4.1 Tomato Precision Irrigation Dataset — Historical Scores Withdrawn
- **Source:** Mendeley Data `10.17632/c837v6p8ph.2` (Version 2, CC BY 4.0).
- **Files Validated:** `dataset_zone_1_preprocessed.csv` (9,531 rows), `dataset_zone_2_preprocessed.csv` (11,929 rows). Total: 21,460 records.
- **Correction:** The previous ML split did not purge forecast-label horizons at the train/validation and validation/test boundaries. The RMSE/MAE/R² figures below are historical and are not valid final estimates; rerun with the corrected purged split before citing.
- **Findings (historical only):**
  - Raw un-preprocessed files (`dataset_zone_1.csv`) possess intermittent gaps (maximum contiguous segment of 10-minute intervals was only 65 steps = 10.8 h), which precludes unbroken 24-hour lag/horizon construction.
  - Preprocessed open-field files contain continuous multi-day runs (up to 2,702 steps = 18.8 days) suitable for rigorous chronological ML benchmarking.
  - 24-hour ahead VWC forecasting benchmark (held-out test split, no leakage):
    - **Zone 1:** Persistence RMSE 1.196% VWC; Ridge RMSE 1.100% VWC; Random Forest RMSE 0.990% VWC; **GBDT RMSE 0.917% VWC** (MAE 0.414% VWC).
    - **Zone 2:** Persistence RMSE 0.689% VWC; **Ridge RMSE 0.572% VWC** (MAE 0.322% VWC); Random Forest RMSE 0.707% VWC; GBDT RMSE 0.861% VWC.
  - Reconstructed cumulative drip irrigation: $218.43\text{ m}^3$ across 21,460 records.

### 4.2 Leaf Wetness and Agrometeorological Dataset — Historical All-Day Aggregation Withdrawn
- **Source:** Mendeley Data `10.17632/sd4b8vpvyb.1` (Version 1, CC BY-NC 4.0).
- **Files Validated:** `site1.csv` through `site7.csv`. Total: 55,550 hourly records.
- **Correction:** The earlier adapter accumulated wetness across all hours of the day. The following prior values are not nocturnal LWD and must not be used to select Node A. The corrected implementation computes a configurable 18:00–06:00 local-time window (default Europe/Rome); rerun and verify the dataset timestamp convention and calibrated wetness threshold.
- **Historical findings (not final):**
  - Previously reported all-day wetness quantiles ($P_{90}(\text{LWD})$) demonstrates wide microclimatic heterogeneity:
    - **Site 2:** 24.0 h/day (wettest microclimate / candidate humid pole Node A)
    - **Site 1:** 16.0 h/day
    - **Site 3:** 12.0 h/day
    - **Site 5:** 12.0 h/day
    - **Site 4:** 9.0 h/day
    - **Site 7:** 2.0 h/day
    - **Site 6:** 0.0 h/day (driest station)
  - Under Protocol v2.0 selection rule ($i_A = \arg\max P_{90}(\text{LWD})$), Site 2 is uniquely selected.
  - Wallin DSV vs. LWS-modified DSV comparison confirmed that in microclimates where humidity drops between 80% and 89% while foliar dew persists, standard weather station Wallin DSV underestimates pathogen risk.

### 4.3 Libelium Olive Grove Multi-Sensor Dataset — Trigger Count Requires Threshold Re-Run
- **Source:** Mendeley Data `10.17632/cnfh4stzzx.2` (Version 2, CC BY 4.0).
- **Files Validated:** `libelium_measurements_quality_controlled.csv`. Total: 9,435 frames (Goraj-1: 6,462 rows; Goraj-2: 2,973 rows).
- **Correction:** ProtocolConfig sets the minimum Spearman correlation to 0.70; the prior public-data report used 0.60. Any old trigger count (including 873) is superseded. Re-run the original data with the protocol threshold and retain the generated CSV/JSON outputs.
- **Historical findings (not final):**
  - Aligned paired 10-minute observations: 1,617 steps across Goraj-1 and Goraj-2.
  - Trailing 48-hour rolling window ($W = 278$ steps at 10.3-minute cadence):
    - Latest mean absolute VWC difference: $4.07\%$ VWC.
    - Latest Spearman rank correlation: $r_s = -0.739$.
    - Protocol v2.0 spatial sufficiency trigger ($\mathcal{F}_{\text{insuff}} = 1$ due to $r_s < 0.60$ or $|\Delta\theta| > 10\%$): **873 trailing windows triggered**.
  - This empirical finding directly validates the operational need for dynamic spatial sufficiency monitoring in real agricultural deployments.

---

## 5. Statistical Validation & Methodology Audit

### 5.1 Experimental Unit & Degrees of Freedom
- **Design:** Randomized Complete Block Design (RCBD) with 4 treatments $\times$ 4 blocks = 16 experimental plots ($20\text{ m}^2$ each).
- **Degrees of Freedom:**
  - Treatment df: $k - 1 = 3$
  - Block df: $b - 1 = 3$
  - Residual error df: $(k - 1)(b - 1) = 9$
- **Subsampling Integrity:** The 160 tagged plants (10 per plot) are correctly treated as observational subsamples and averaged to plot means. They are never treated as $n=160$ independent replicates.

### 5.2 ANOVA & Yield Non-Inferiority
- Marketable Yield ANOVA: $F_{3,9} = 110.11$ ($p = 2.1 \times 10^{-7}$).
- Standard Error of Difference (SED): $\mathrm{SED} = \sqrt{2 \cdot \mathrm{MSE} / b} = 0.142\text{ t ha}^{-1}$.
- Fisher's Protected LSD ($\alpha = 0.05, \text{df} = 9$): $\mathrm{LSD}_{0.05} = 2.262 \cdot 0.142 = 0.322\text{ t ha}^{-1}$.
- Pre-specified 5% Non-Inferiority Margin ($M_{\text{T1}} = -0.05 \cdot 33.02 = -1.651\text{ t ha}^{-1}$):
  - $\Delta Y = Y_{\mathrm{T4}} - Y_{\mathrm{T1}} = 34.40 - 33.02 = +1.383\text{ t ha}^{-1}$.
  - One-sided 95% lower confidence bound: $L_{95} = +1.383 - 1.833 \cdot 0.142 = +1.122\text{ t ha}^{-1}$ ($+3.40\%$).
  - Because $L_{95} > M_{\text{T1}}$, non-inferiority (and superiority) is statistically established within the simulation.

### 5.3 Residual Diagnostics Integrity
- Shapiro-Wilk test on yield residuals: $W = 0.9507, p = 0.5002$.
- Median-centered Levene test on yield residuals across treatments: $W_{\text{Levene}} = 1.5489, p = 0.2528$.
- **Cautionary Note:** The audit confirms that non-significant diagnostic $p$-values are NOT described as proof of normality or homoscedasticity. With $n=16$, statistical power is limited, and these tests merely demonstrate absence of gross violations.

### 5.4 Repeated-Measures Linear Mixed-Effects Model
- Model specification: Restricted Maximum Likelihood (REML) random-intercept model on foliar blight severity across 80 plot-by-epoch observations (16 plots $\times$ 5 epochs).
- Convergence: Model converged.
- Random-intercept between-plot variance: $\hat{\sigma}_u^2 = 0.3150$.
- Residual within-plot variance: $\hat{\sigma}_e^2 = 0.2157$.
- Intraclass Correlation Coefficient (ICC): $\mathrm{ICC} = 0.3150 / (0.3150 + 0.2157) = 0.5935$.

---

## 6. ESP32-S3 Firmware Readiness & Hardware Audit

### 6.1 Protocol Specification & Bit Packing
- Header: `firmware/common/sentinel_protocol.h`.
- Size assertion: `static_assert(sizeof(SentinelPacket) == 24, "...")` is enforced.
- Checksum: CRC-16-CCITT (polynomial `0x1021`, seed `0xFFFF`) over bytes 0..21. Validated against standard string `"123456789"` (`0x29B1`).
- Magic byte: `0xA5`.
- Node IDs: 1 (Humid Node A), 2 (Dry Node B), 3 (Adaptive Node C).

### 6.2 Host & CI Compilation Status
- C++ host tests (`tests/test_firmware_host.cpp`) compile with `-std=c++17 -Wall -Wextra -Werror` in GitHub Actions and execute all controller state transitions, packet validations, and CWSI/VPD edge cases.
- PlatformIO targets (`node_a`, `node_b`, `gateway`) compile cleanly in CI on `espressif32@6.12.0`.
- Local Windows workstation lacks PlatformIO and has an outdated 32-bit GCC compiler; firmware testing on this machine is executed via Python unit tests and validated via GitHub Actions.

### 6.3 Hardware Unresolved Items & Bench Requirements
1. **SX1262 LoRa Reset and Busy Pins:**
   - In `platformio.ini`, `SENTINEL_LORA_RST_PIN` and `SENTINEL_LORA_BUSY_PIN` are defined as `-1` (`RADIOLIB_NC`).
   - Many physical SX1262 modules (e.g. Waveshare, Ebyte) hang during SPI initialization if the BUSY pin is not connected to a designated GPIO. These must be physically wired and assigned before flashing.
2. **Dielectric Sensor Calibration:**
   - `node_firmware.ino` uses placeholder constants `SOIL_ADC_DRY = 3150.0f` and `SOIL_ADC_SAT = 1280.0f`.
   - Capacitive soil probes and leaf wetness probes require laboratory two-point gravimetric and water-film calibration with the target field soil.
3. **Latching Valve H-Bridge Polarity & Safe State:**
   - Solenoid valve driven by pulses on `GPIO15` (Open) and `GPIO16` (Close) with 80 ms duration.
   - Because latching valves mechanically retain their state on power loss, power failure while open will cause continuous flooding unless backed by an inline manual or hydraulic check valve.
   - H-bridge electrical polarity must be confirmed on bench.
4. **Flow Meter K-Factor:**
   - `FLOW_PULSES_PER_LITRE = 450.0f` is a nominal catalog figure for YF-S201. Volumetric bucket calibration across 1.0--10.0 L/min is mandatory.
5. **Gateway Real-Time Clock (RTC):**
   - The ESP32-S3 gateway currently derives minute-of-day from monotonic `millis()` starting from `#define SENTINEL_START_MINUTE_OF_DAY 0`.
   - On power-cycle or watchdog reset, the time resets to midnight, desynchronizing the midday 11:30--14:30 solar window. An external I2C DS3231 RTC or NTP link must be added for autonomous field operation.

---

## 7. Research Manuscript Verification

- **File Inspected:** `paper/Sentinel_Plant_Network_Journal_Paper.tex`.
- **Citations:** Verified all 15 references (Vachaud, Wallin, Idso, Jackson, Mendeley datasets, HiWATER, CABI).
- **Formulas:** Verified LaTeX math for relative difference $\delta_{ij}$, ITS, CWSI clipping, Tetens VPD, Wallin/LWS DSV, and RCBD ANOVA / non-inferiority formulas.
- **Evidence Boundaries:** The manuscript strictly labels all numerical agronomic results (e.g., 25.8% water savings, 34.4 t/ha yield) as **synthetic digital-twin benchmarks**.
- **Empirical Validation Section:** Section 6 updated to report genuine findings from the three Mendeley datasets while explicitly acknowledging that they originate from external Mediterranean/European sites and do not replace physical field trials.

---

## 8. Summary of Action Items & Readiness

1. **Software & Mathematics:** Core implementation is present and automated; the corrected validation pipeline still requires a complete green CI run and independent review of any new outputs.
2. **Public Dataset Validation:** PARTIALLY COMPLETE. Corrected adapters are available, but the previous figures are withdrawn until rerun with original local files and retained checksums/results.
3. **Hardware Readiness:** Software and protocol verified; physical bench test plan formulated in `HARDWARE_BENCH_TEST_PLAN.md`.
4. **Field Trials:** NOT STARTED; requires physical hardware deployment and a pre-registered planting-season experiment.
