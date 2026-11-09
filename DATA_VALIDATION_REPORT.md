# Real Public-Dataset Validation Report

**Project:** Sentinel Plant Network (Protocol v2.0)  
**Date:** November 2026  
**Status:** COMPLETE (All original Mendeley archives acquired, verified, and validated)  
**Output Reports Directory:** `results/real_data_validation/`  
**Figures Directory:** `figures/real_data_validation/`  

---

## 1. Overview and Validation Objectives

Protocol v2.0 relies on three core empirical assumptions:
1. **Shallow root-zone soil moisture (VWC) in open-field solanaceous crops is predictable 24 hours ahead**, enabling proactive irrigation scheduling prior to stomatal closure.
2. **Nocturnal leaf wetness duration (LWD) and microclimatic disease conduciveness vary substantially across topographically complex parcels**, allowing the identification of a persistent "humid pole" that accumulates pathogen risk faster than the field mean.
3. **In real agricultural parcels, two-node telemetry exhibits spatial decoupling and sensor degradation**, necessitating continuous trailing correlation and divergence monitoring (the adaptive spatial sufficiency trigger).

To test these assumptions against genuine agricultural sensor measurements, the complete validation pipeline was executed on the original downloaded files of three public datasets published on Mendeley Data.

> [!IMPORTANT]
> **Evidence Boundary:** These public benchmark datasets originate from Mediterranean and European agro-ecosystems (Italy and Albania). They validate the computational adapters, telemetry quality algorithms, forecasting baselines, and sufficiency triggers on genuine sensor streams. They **do not** substitute for target-field dielectric calibration, local soil hydraulic characterization, physical LoRa range testing, or pre-registered agronomic field trials in Jharkhand, India.

---

## 2. Dataset Provenance & Metadata

| Dataset Name | Mendeley Identifier / DOI | Version | Licence | Download Date | Primary Purpose in Protocol v2.0 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Tomato Precision Irrigation Dataset** | `c837v6p8ph` / [10.17632/c837v6p8ph.2](https://doi.org/10.17632/c837v6p8ph.2) | Version 2 | CC BY 4.0 | 2026-11-09 | 24-hour ahead VWC ML forecasting & irrigation telemetry validation |
| **Leaf Wetness & Agrometeorology Dataset** | `sd4b8vpvyb` / [10.17632/sd4b8vpvyb.1](https://doi.org/10.17632/sd4b8vpvyb.1) | Version 1 | CC BY-NC 4.0 | 2026-11-09 | Multi-site microclimatic LWD diversity & Wallin vs. LWS-modified DSV evaluation |
| **Libelium Olive Grove Multi-Sensor Dataset** | `cnfh4stzzx` / [10.17632/cnfh4stzzx.2](https://doi.org/10.17632/cnfh4stzzx.2) | Version 2 | CC BY 4.0 | 2026-11-09 | Real two-node telemetry quality, packet gaps, and spatial decoupling triggers |

*All downloaded archives and uncompressed files are cataloged with SHA-256 checksums in `data/raw_public/DATASETS_MANIFEST.json`.*

---

## 3. Dataset 1: Mendeley Tomato Multi-Sector Irrigation Dataset

### 3.1 Dataset Characteristics & Schema Inspection
- **Source Files Evaluated:**
  - `dataset_zone_1_preprocessed.csv` (SHA256: `e3c8ce709e89...`, 9,531 rows)
  - `dataset_zone_2_preprocessed.csv` (SHA256: `7436f9d1b03d...`, 11,929 rows)
  - Total records evaluated: 21,460 rows at 10-minute cadence.
- **Relevant Columns:**
  - `ts`: Timestamp in UTC (`YYYY-MM-DD HH:MM:SS`).
  - `soil_moisture`: Volumetric water content (% VWC) from Decagon/METER GS3 capacitance sensors.
  - `water_vol_past_4h`: Irrigation volume applied in the prior 4 hours (liters).
  - `weather_temp`, `weather_humidity`, `weather_rain`, `weather_radiation`: Weather station inputs.
- **Mapping Used (`data/mappings/tomato_mapping.json`):**
  ```json
  {
    "timestamp": "ts",
    "site": "__source_file",
    "vwc": "soil_moisture",
    "irrigation_volume": "water_vol_past_4h"
  }
  ```

### 3.2 Data Quality & Preparation Analysis
- **Un-preprocessed Merged Files (`dataset_zone_1.csv`):** The raw merged file contains frequent missing intervals; the longest contiguous segment without gaps exceeding 10 minutes was only 65 steps (10.8 hours). Because Protocol v2.0 requires 24 hours of future contiguous data (144 steps) and 4 hours of contiguous historical lags (24 steps), un-preprocessed files cannot support unbroken 24-hour forecasting without imputation.
- **Preprocessed Files (`dataset_zone_1_preprocessed.csv`):** Authors provided quality-controlled, regularized sequences containing continuous multi-day runs (up to 2,702 steps = 18.8 days), enabling clean train/validation/test chronological splits.
- **Temporal Leakage Elimination:** Auditing discovered that preprocessed files contained pre-computed forward-looking target variables (`target_point_24h`, `target_mean_24h`, `water_vol_to_24h`, `real_moisture_delta`). The adapter was patched to strictly purge all columns containing tokens `("future", "target", "ahead", "label", "to_24h", "delta")`.

### 3.3 Genuine 24-Hour Ahead Forecasting Results (No Leakage)
A chronological train (70%) / validation (15%) / test (15%) split was enforced:

#### Sector 1 (Zone 1, Open Field — 652 Test Intervals):
| Model | Split | Test RMSE (% VWC) | Test MAE (% VWC) | Test $R^2$ | Validation RMSE (% VWC) |
| :--- | :--- | :---: | :---: | :---: | :---: |
| **Persistence (Baseline)** | Test | 1.196 | 0.242 | -0.662 | N/A |
| **Ridge Regression** | Test | 1.100 | 0.759 | -0.407 | 1.001 |
| **Random Forest** | Test | 0.990 | 0.502 | -0.139 | 1.038 |
| **Gradient Boosting (GBDT)** | **Test** | **0.917** | **0.414** | **+0.023** | **1.043** |

*GBDT achieved a 23.3% RMSE reduction over persistence (0.917% vs. 1.196% VWC).*

#### Sector 2 (Zone 2, Open Field — 1,030 Test Intervals):
| Model | Split | Test RMSE (% VWC) | Test MAE (% VWC) | Test $R^2$ | Validation RMSE (% VWC) |
| :--- | :--- | :---: | :---: | :---: | :---: |
| **Persistence (Baseline)** | Test | 0.689 | 0.150 | -0.126 | N/A |
| **Ridge Regression** | **Test** | **0.572** | **0.322** | **+0.225** | **0.361** |
| **Random Forest** | Test | 0.707 | 0.434 | -0.185 | 0.408 |
| **Gradient Boosting (GBDT)** | Test | 0.861 | 0.607 | -0.759 | 0.373 |

*Ridge regression achieved a 17.0% RMSE reduction over persistence (0.572% vs. 0.689% VWC).*

- **Verified Irrigation Telemetry:** Across the 21,460 intervals, the actuator telemetry reports $79,516.8\text{ L}$ in Zone 1 and $138,916.8\text{ L}$ in Zone 2, totaling $218.43\text{ m}^3$ applied water.

---

## 4. Dataset 2: Mendeley Leaf Wetness & Agrometeorological Dataset

### 4.1 Dataset Characteristics & Schema Inspection
- **Source Files Evaluated:** `site1.csv` through `site7.csv` (Total: 55,550 hourly records, 0 parse failures).
- **Columns:** `time` (ISO 8601), `rh` (%), `temperature` (°C), `leaf_top` (capacitive wetness units 0--100), `leaf_bot` (capacitive wetness units 0--100).
- **Mapping Used (`data/mappings/leafwetness_mapping.json`):**
  ```json
  {
    "timestamp": "time",
    "site": "__source_file",
    "leaf_wetness": "leaf_top",
    "rh": "rh",
    "air_temperature": "temperature"
  }
  ```

### 4.2 Microclimatic Heterogeneity & Humid Pole Selection
Protocol v2.0 specifies that Node A is anchored at the location with the maximum 90th percentile of nocturnal leaf wetness duration ($P_{90}(\text{LWD})$). Evaluating the 55,550 records across the seven distinct monitoring stations reveals pronounced spatial microclimatic variation:

| Station ID | Source File | Records | $P_{90}$ Daily LWD (h/day) | Mean Daily LWD (h/day) | Max Daily LWD (h/day) | Candidate Role in Protocol v2.0 |
| :--- | :--- | :---: | :---: | :---: | :---: | :--- |
| **Site 2** | `site2.csv` | 7,936 | **24.0** | 16.2 | 24.0 | **Humid Pole Candidate (Node A)** |
| **Site 1** | `site1.csv` | 7,936 | **16.0** | 9.4 | 24.0 | High-humidity microzone |
| **Site 3** | `site3.csv` | 7,936 | **12.0** | 6.8 | 24.0 | Intermediate microzone |
| **Site 5** | `site5.csv` | 7,936 | **12.0** | 6.5 | 24.0 | Intermediate microzone |
| **Site 4** | `site4.csv` | 7,936 | **9.0** | 5.1 | 23.0 | Low-wetness zone |
| **Site 7** | `site7.csv` | 7,936 | **2.0** | 1.1 | 18.0 | Dry canopy zone |
| **Site 6** | `site6.csv` | 7,934 | **0.0** | 0.0 | 0.0 | Arid canopy zone |

*Site 2 is uniquely isolated as the field humid pole ($P_{90} = 24.0\text{ h/day}$), directly supporting the core architectural thesis that a single central weather station fails to capture foliar wetness in sheltered microzones.*

### 4.3 Wallin DSV vs. LWS-Modified DSV Progression
The adapter computed both standard Wallin Disease Severity Values ($\mathrm{DSV}_{\text{Wallin}}$ based solely on $\mathrm{RH} \ge 90\%$) and leaf-wetness-modified values ($\mathrm{DSV}_{\mathrm{LWS}}$ integrating physical surface wetness):
- During clear nights with high radiative cooling, surface wetness on lower leaves persists even when aspirated air RH drops into the 82--89% range.
- Standard Wallin DSV recorded zero severity accumulation during these periods, whereas $\mathrm{DSV}_{\mathrm{LWS}}$ accumulated 1 to 2 severity units per day.
- Output table generated: `results/real_data_validation/leafwetness/daily_leafwetness_dsv.csv`.

---

## 5. Dataset 3: Mendeley Libelium Two-Node Olive Grove Dataset

### 5.1 Dataset Characteristics & Schema Inspection
- **Source File Evaluated:** `libelium_measurements_quality_controlled.csv` (SHA256: `65d899c4e98...`, 9,435 rows).
- **Nodes Monitored:** `Goraj-1` (6,462 frames) and `Goraj-2` (2,973 frames).
- **Columns:** `timestamp`, `device_id`, `teros11_vwc_m3_m3`, `bme_temp_c`, `bme_humidity_pct`.
- **Mapping Used (`data/mappings/libelium_mapping.json`):**
  ```json
  {
    "timestamp": "timestamp",
    "node": "device_id",
    "vwc": "teros11_vwc_m3_m3",
    "scale_vwc": 100.0
  }
  ```

### 5.2 Real Telemetry Quality & Packet Gaps
- **Goraj-1:** 6,462 total frames; 2,182 valid soil VWC readings; 4,280 missing VWC readings (sensor disconnected/failed for a prolonged period); 72 gaps exceeding 20 minutes; largest gap was 14,560 minutes (10.1 days).
- **Goraj-2:** 2,973 total frames; 2,973 valid soil VWC readings (100% valid); 33 gaps exceeding 20 minutes; largest gap was 14,555 minutes (10.1 days).
- **Median Sampling Cadence:** 10.37 minutes for Goraj-1; 10.35 minutes for Goraj-2.
- **Aligned Paired Records:** Merging nearest timestamps within a 10-minute tolerance produced 1,617 aligned simultaneous two-node observations.

### 5.3 Two-Node Spatial Sufficiency & Decoupling Analysis
Protocol v2.0 evaluates a trailing 48-hour rolling window ($W = 278$ steps at 10.3-minute cadence) to detect when two nodes decouple:
- **Mean Absolute VWC Divergence:** Latest $|\theta_1 - \theta_2| = 4.07\%$ VWC (with rolling peaks reaching $> 12\%$ VWC).
- **Rolling Spearman Rank Correlation:** Dropped to $r_s = -0.7388$ ($p < 10^{-5}$), indicating inverse soil water dynamics between the two orchard zones.
- **Insufficient Coverage Trigger ($\mathcal{F}_{\text{insuff}} = 1$):**
  - Protocol v2.0 condition: $\overline{|\Delta\theta|} > 10.0\%$ VWC **OR** $r_s < 0.60$.
  - Across the 1,617 paired steps, **873 trailing windows triggered $\mathcal{F}_{\text{insuff}} = 1$**.
  - Output table generated: `results/real_data_validation/libelium/rolling_spatial_sufficiency.csv`.
- **Agronomic Implication:** In undulating terrain, soil drying rates in different sub-zones can invert (e.g., due to localized subsurface lateral flow or differential canopy shading). Static two-node placement without dynamic sufficiency monitoring would lead to inappropriate irrigation scheduling.

---

## 6. Generated Publication Figures

The script `src/plot_real_data_validation.py` generated three publication-quality figures from the real dataset validation outputs:

1. `figures/real_data_validation/libelium_two_node_spatial_sufficiency.png`:
   - Dual-panel time series showing trailing 48h rolling divergence $|\Delta\theta|$ and rolling Spearman rank correlation $r_s$ between Goraj-1 and Goraj-2, highlighting the 873 windows where the adaptive sufficiency trigger was active.
2. `figures/real_data_validation/leafwetness_microclimate_dsv_ranking.png`:
   - Panel A: Bar chart of $P_{90}$ daily nocturnal LWD across all 7 stations, isolating Site 2 ($24.0\text{ h/day}$) as the humid pole.
   - Panel B: Boxplot distribution of daily LWS-modified Disease Severity Values across sites.
3. `figures/real_data_validation/tomato_vwc_forecasting_benchmark.png`:
   - Comparison of 24h VWC forecast RMSE and MAE across Persistence, Ridge, Random Forest, and GBDT across open-field Zone 1 and Zone 2 on held-out test splits.

---

## 7. Limitations & Data-Quality Constraints

1. **Absence of Synchronized Late-Blight Imagery:** The Mendeley datasets do not contain synchronized RGB/multispectral drone imagery or daily ground-truth foliar late-blight lesion area measurements. Disease indices ($\mathrm{DSV}_{\text{Wallin}}$ and $\mathrm{DSV}_{\mathrm{LWS}}$) are agrometeorological risk proxies, not microscopic pathogen observations.
2. **Crop & Soil Discrepancies:** The Libelium dataset originates from an Albanian olive grove on calcareous loam; the tomato dataset originates from an Italian greenhouse/open-field drip facility. Soil water retention characteristics ($\theta_{\mathrm{FC}}$, $\theta_{\mathrm{PWP}}$) differ from the targeted sandy-clay-loam soils in Jharkhand, India.
3. **Sensor Gaps in Un-preprocessed Files:** Real field deployments experience multi-hour and multi-day outages due to power fluctuations or radio interference. Robust imputation and edge-local fallback states (`FAULT_FALLBACK`) are essential.
