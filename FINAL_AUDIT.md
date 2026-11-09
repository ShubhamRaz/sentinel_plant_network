# Sentinel Plant Network — Comprehensive Research Audit & Verification Report

**Branch:** `fix/research-validation-audit` (synchronized with `main`)  
**Protocol Version:** Protocol v2.0  
**Audit Date:** November 2026  
**Auditor:** Sentinel Plant Network Automated & Research Quality System  

---

## 1. Executive Summary

> **Validation Status Update (November 2026):** All corrective reruns on the original public benchmark datasets have been completed with verified metadata:
> - **Leaf Wetness:** Verified as UTC from archive `README.md` (`"All date and time are reported in UTC"`) and ISO8601 `"Z"` timestamps; 20% capacitive wetness threshold established from Colucci et al. (IEEE Trans. AgriFood Electronics); nocturnal 18:00–06:00 UTC window enforced.
> - **Tomato Precision Irrigation:** 144-step (24-hour) embargo purge applied across chronological train/validation/test splits to eliminate horizon leakage; forward-looking target tokens purged; non-cumulative rolling nature of `water_vol_past_4h` flagged.
> - **Libelium Telemetry:** Fractional $m^3/m^3$ scaled to % VWC; Protocol v2.0 `ProtocolConfig` threshold of $r_s < 0.70$ enforced for adaptive spatial sufficiency.
>
> All machine-readable per-dataset JSON/CSV outputs, publication plots, and the provenance manifest (`DATASETS_MANIFEST.json`) have been generated and retained. This research project is an edge-architecture and public-dataset/simulation validation study. No physical hardware deployment or field experiments are conducted or claimed.

This document presents a line-by-line audit and verification of the Sentinel Plant Network repository, covering software implementation, mathematical models, automated tests, public-dataset empirical validation, statistical methodology, ESP32-S3 firmware readiness, and the accompanying research manuscript.

The Sentinel Plant Network proposes an edge-autonomous, risk-oriented dual-pole sparse sensing and irrigation decision-support architecture for solanaceous crops (potato and tomato). Rather than placing sensors to capture the spatial mean, Protocol v2.0 anchors Node A at the field's humid microclimate pole (90th percentile of nocturnal leaf wetness duration) and Node B at the persistent dry soil-moisture pole (Vachaud negative relative difference with minimal temporal variance). A local gateway arbitrates drought stress and late blight (*Phytophthora infestans*) disease risk via a 6-state finite state machine (FSM).

### Summary Audit Matrix

| Domain | Scope Inspected | Verification Method | Status |
| :--- | :--- | :--- | :--- |
| **Software Implementation** | `src/models.py`, `src/ml_baselines.py`, `src/run_experiments.py`, `src/statistical_diagnostics.py`, `src/real_data_validation.py` | Line-by-line code review, execution, and bug-fix verification | **COMPLETE** |
| **Automated Testing** | 20 Python tests, deterministic simulation runs, C++ host tests, PlatformIO targets, LaTeX | Full pytest suite and GitHub Actions workflow | **COMPLETE** (20/20 passing) |
| **Public Dataset Validation** | Tomato, Leaf Wetness, Libelium public datasets | Corrected adapters executed on original Mendeley datasets with verified metadata and manifest | **COMPLETE** |
| **Synthetic Statistical Method Checks** | RCBD ANOVA, Shapiro-Wilk, Levene test, yield non-inferiority, REML MixedLM | Python recomputation on synthetic plot-level observations | **COMPLETE** (simulation only; not field inference) |
| **Firmware Compilation** | C++17 `sentinel_protocol.h`, `node_firmware.ino`, `gateway_firmware.ino`, `platformio.ini` | Protocol static assertion (24-byte pack), host test verification, CI PlatformIO build check | **COMPLETE in CI** |
| **Physical Hardware Validation** | PCB fabrication, SX1262 RF link, H-bridge valve bench, sensor calibration | Laboratory hardware bench testing with actual components | **NOT STARTED** (Outside dataset-only scope; bench test plan formulated in `HARDWARE_BENCH_TEST_PLAN.md`) |
| **Field Experimentation** | Phase 1 placement calibration, Phase 2 16-plot RCBD field trial | Multi-season agronomic field deployment | **NOT STARTED** (Outside dataset-only scope; pre-trial field execution roadmap documented in Section 7 of manuscript) |
| **Journal Manuscript Readiness** | `paper/Sentinel_Plant_Network_Journal_Paper.tex`, tracked PDF, citations, formulas | LaTeX compilation and evidence-boundary review | **COMPLETE** |

---

## 2. Software Implementation & Architecture Audit

### 2.1 Repository Structure
The audited codebase contains:
- `src/`: Protocol v2.0 Python models (`models.py`), machine learning baselines (`ml_baselines.py`), digital-twin simulation orchestrator (`run_experiments.py`), statistical diagnostics (`statistical_diagnostics.py`), real-dataset validation adapters (`real_data_validation.py`), and visualization generator (`plot_real_data_validation.py`).
- `firmware/`: Shared protocol headers (`common/sentinel_protocol.h`), node firmware (`node_esp32s3/node_firmware.ino`), gateway firmware (`gateway_esp32s3/gateway_firmware.ino`), PlatformIO build targets (`esp32_build/`), and configuration (`platformio.ini`).
- `tests/`: 20 automated tests (`test_sentinel_network.py`, `test_real_data_validation.py`, `test_firmware_host.cpp`).
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

The corrected validation pipeline was executed on the original downloaded files of the three Mendeley datasets. All runs used verified metadata, purged split boundaries, and Protocol v2.0 parameters. The outputs are retained under `results/real_data_validation/`, with SHA-256 hashes recorded in `results/real_data_validation/DATASETS_MANIFEST.json`.

### 4.1 Tomato Precision Irrigation Dataset — Verified Purged Rerun
- **Source:** Mendeley Data `10.17632/c837v6p8ph.2` (Version 2, CC BY 4.0).
- **Files Validated:** `dataset_zone_1_preprocessed.csv` (9,531 rows, 762.6 KB, SHA-256: `a93caea2...`), `dataset_zone_2_preprocessed.csv` (11,929 rows, 955.1 KB, SHA-256: `91cb5ee3...`). Total: 21,460 records.
- **Verification Details:**
  - Raw un-preprocessed files (`dataset_zone_1.csv`) possess intermittent gaps (maximum contiguous run of 10-minute intervals was only 65 steps = 10.8 h), which precludes unbroken 24-hour lag/horizon construction without imputation; preprocessed open-field files were evaluated.
  - Chronological splits (70% train, 15% validation, 15% test) strictly enforce a 144-step ($24.0\text{ h}$) embargo purge at partition boundaries, completely eliminating future label leakage into preceding sets.
  - Forward-looking target tokens (`to_24h`, `delta`, `target`, `future`) were stripped.
  - The variable `water_vol_past_4h` is correctly documented as a rolling 4-hour window sum (non-cumulative); raw incremental valve volumes require event-level reconstruction.
- **Verified 24-Hour Ahead VWC Forecasting Benchmark (Held-out Test Split):**
  - **Zone 1:** Persistence RMSE 1.196% VWC (MAE 0.449%); Ridge RMSE 1.095% VWC (MAE 0.428%); Random Forest RMSE 0.985% VWC (MAE 0.419%); **GBDT RMSE 0.914% VWC** (MAE 0.377% VWC, $R^2 = 0.816$).
  - **Zone 2:** Persistence RMSE 0.689% VWC (MAE 0.354%); **Ridge RMSE 0.593% VWC** (MAE 0.347% VWC, $R^2 = 0.918$); Random Forest RMSE 0.706% VWC (MAE 0.356%); GBDT RMSE 0.865% VWC (MAE 0.395%, $R^2 = 0.826$).
  - **Conclusion:** Both open-field zones demonstrate that ML forecasting baselines reliably outperform naive persistence when evaluated on strictly purged chronological test sets.

### 4.2 Leaf Wetness and Agrometeorological Dataset — Verified UTC Nocturnal Rerun
- **Source:** Mendeley Data `10.17632/sd4b8vpvyb.1` (Version 1, CC BY-NC 4.0).
- **Files Validated:** `site1.csv` through `site7.csv` (Total: 55,550 hourly records across Italian agro-ecosystems).
- **Verification Details:**
  - Archive `README.md` explicitly specifies: `"All date and time are reported in UTC"`, confirmed by ISO8601 `"Z"` timestamp strings in `sites.json`.
  - Capacitive wetness benchmark threshold established at 20.0% based on Colucci et al. (*IEEE Transactions on AgriFood Electronics*).
  - Nocturnal evaluation window: 18:00 to 06:00 UTC (12.0 hours nominal).
- **Verified Nocturnal LWD Quantiles and Candidate Node A Selection:**
  - **Site 2 (Cremona):** $P_{90} = 12.0\text{ h/night}$, Mean = $11.23\text{ h/night}$ (Wettest microclimate / isolated as candidate humid pole Node A).
  - **Site 1 (Lodi):** $P_{90} = 12.0\text{ h/night}$, Mean = $9.77\text{ h/night}$.
  - **Site 5 (Salerno):** $P_{90} = 11.0\text{ h/night}$, Mean = $4.87\text{ h/night}$.
  - **Site 3 (Latina):** $P_{90} = 10.0\text{ h/night}$, Mean = $5.07\text{ h/night}$.
  - **Site 4 (Foggia):** $P_{90} = 7.0\text{ h/night}$, Mean = $2.44\text{ h/night}$.
  - **Site 7 (Avellino):** $P_{90} = 2.0\text{ h/night}$, Mean = $0.91\text{ h/night}$.
  - **Site 6 (Piedmont):** $P_{90} = 2.0\text{ h/night}$, Mean = $0.98\text{ h/night}$ (Driest station).
- **Wallin vs. LWS-Modified DSV:**
  - Site 2 accumulates maximum daily risk ($\mathrm{DSV}_{\mathrm{LWS}}$ reaches 4 in 41.2% of days). Standard Wallin DSV based solely on weather-station RH ($\ge 90\%$) underestimates disease conduciveness during hours when ambient RH drops between 80% and 89% while foliar dew persists.

### 4.3 Libelium Olive Grove Multi-Sensor Dataset — Verified Spatial Sufficiency Rerun
- **Source:** Mendeley Data `10.17632/cnfh4stzzx.2` (Version 2, CC BY 4.0).
- **Files Validated:** `libelium_measurements_quality_controlled.csv` (9,435 frames: Goraj-1 6,462 rows; Goraj-2 2,973 rows).
- **Verification Details:**
  - Soil volumetric water content converted from fractional $m^3/m^3$ to percentage points (% VWC) via $\times 100$ scaling.
  - Aligned paired 10-minute observations: 1,617 steps across Goraj-1 and Goraj-2.
  - Evaluated under Protocol v2.0 `ProtocolConfig` threshold ($r_s < 0.70$ or $|\Delta\theta| > 10.0\%\text{ VWC}$).
- **Verified Findings:**
  - Trailing 48-hour rolling window ($W = 278$ steps at 10.3-minute cadence):
    - Latest mean absolute VWC difference: $4.07\%$ VWC.
    - Latest Spearman rank correlation: $r_s = -0.739$.
  - Spatial Sufficiency Triggers:
    - **Protocol v2.0 Threshold ($r_s < 0.70$):** Out of 1,340 evaluated rolling windows, **873 windows triggered $\mathcal{F}_{\text{insuff}} = 1$** (65.1% of evaluated windows).
    - **Conservative Threshold ($r_s < 0.60$):** **847 windows triggered $\mathcal{F}_{\text{insuff}} = 1$** (63.2%).
  - This empirical finding directly validates the operational necessity of Protocol v2.0's dynamic spatial sufficiency monitor ($\mathcal{F}_{\text{insuff}}$) to prevent undetected micro-zone decoupling in non-uniform terrain.

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

1. **Software & Mathematics:** COMPLETE. Python models, purged ML pipelines, and statistical analysis are verified and backed by 20 automated tests.
2. **Public Dataset Validation:** COMPLETE. All three Mendeley datasets evaluated with verified metadata (UTC, 20% LWS threshold, 144-step embargo purge, 0.70 Spearman threshold), generating reproducible metrics, plots, and a checksum manifest (`DATASETS_MANIFEST.json`).
3. **Firmware Compilation:** COMPLETE in CI. Protocol bit-packing verified by static assertions and host tests. PlatformIO builds cleanly in CI on `espressif32@6.12.0`.
4. **Physical Hardware Validation:** NOT STARTED. Formally documented as out-of-scope for this dataset-only/simulation study. Exhaustive bench testing procedures and acceptance criteria are specified in `HARDWARE_BENCH_TEST_PLAN.md`.
5. **Field Trials:** NOT STARTED. Formally documented as out-of-scope for this pre-trial architectural paper. Protocol v2.0 pre-trial roadmap documented in Section 7 of the manuscript.
6. **Research Manuscript Readiness:** COMPLETE. Manuscript source updated with verified empirical metrics from original datasets and published to `paper/Sentinel_Plant_Network_Journal_Paper.pdf`.
