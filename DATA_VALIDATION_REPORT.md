# Real Public-Dataset Validation Report

**Project:** Sentinel Plant Network (Protocol v2.0)  
**Date:** November 2026  
**Status:** COMPLETE (Corrected Rerun Executed on Original Datasets)  
**Output Reports Directory:** `results/real_data_validation/`  
**Figures Directory:** `figures/real_data_validation/`  

---

## 1. Overview and Validation Objectives

Protocol v2.0 relies on three core empirical assumptions:
1. **Shallow root-zone soil moisture (VWC) in open-field solanaceous crops is predictable 24 hours ahead**, enabling proactive irrigation scheduling prior to stomatal closure.
2. **Nocturnal leaf wetness duration (LWD) and microclimatic disease conduciveness vary substantially across topographically complex parcels**, allowing the identification of a persistent "humid pole" that accumulates pathogen risk faster than the field mean.
3. **In real agricultural parcels, two-node telemetry exhibits spatial decoupling and sensor degradation**, necessitating continuous trailing correlation and divergence monitoring (the adaptive spatial sufficiency trigger).

To test these assumptions against genuine agricultural sensor measurements, the corrected validation pipeline was executed on the original downloaded files of three public datasets published on Mendeley Data.

> [!IMPORTANT]
> **Evidence Boundary:** These public benchmark datasets originate from Mediterranean and European agro-ecosystems (Italy and Albania). They validate the computational adapters, telemetry quality algorithms, forecasting baselines, and sufficiency triggers on genuine sensor streams. They **do not** substitute for target-field dielectric calibration, local soil hydraulic characterization, physical LoRa range testing, or pre-registered agronomic field trials in Jharkhand, India.

---

## 2. Dataset Provenance & Metadata Verification

| Dataset Name | Mendeley Identifier / DOI | Version | Licence | Download Date | Primary Purpose in Protocol v2.0 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Tomato Precision Irrigation Dataset** | `c837v6p8ph` / [10.17632/c837v6p8ph.2](https://doi.org/10.17632/c837v6p8ph.2) | Version 2 | CC BY 4.0 | 2026-11-09 | 24-hour ahead VWC ML forecasting & irrigation telemetry validation |
| **Leaf Wetness & Agrometeorology Dataset** | `sd4b8vpvyb` / [10.17632/sd4b8vpvyb.1](https://doi.org/10.17632/sd4b8vpvyb.1) | Version 1 | CC BY-NC 4.0 | 2026-11-09 | Multi-site microclimatic LWD diversity & Wallin vs. LWS-modified DSV evaluation |
| **Libelium Olive Grove Multi-Sensor Dataset** | `cnfh4stzzx` / [10.17632/cnfh4stzzx.2](https://doi.org/10.17632/cnfh4stzzx.2) | Version 2 | CC BY 4.0 | 2026-11-09 | Real two-node telemetry quality, packet gaps, and spatial decoupling triggers |

*All downloaded archives and uncompressed files are cataloged with SHA-256 checksums in `results/real_data_validation/DATASETS_MANIFEST.json` and `data/raw_public/DATASET_CATALOG.json`.*

### Metadata Verification Summary:
1. **Leaf-Wetness Dataset (`sd4b8vpvyb/1`):**
   - **Timezone:** Authoritatively established as **UTC**. The dataset `README.md` explicitly states: `All date and time are reported in UTC.` Furthermore, `sites.json` specifies timestamps with trailing `"Z"` (ISO 8601 UTC).
   - **Measurement Units:** Sensor readings are dimensionless normalized percentages ($0$--$100$) from custom double-sided capacitive PCB sensors measuring upper (`leaf_top`) and lower (`leaf_bot`) foliar wetness.
   - **Authoritative Publication & Threshold Justification:** Associated authoritative sensor publication: Filipescu, E., Colucci, G. P., & Trinchero, D. (2024). *Design and Implementation of a Capacitive Leaf Wetness Sensor Based on Capacitance-to-Digital Conversion*. IEEE Transactions on AgriFood Electronics, vol. 2, no. 2, pp. 244–251, doi: 10.1109/TAFE.2024.3401252. The publication reported seasonal leaf-wetness comparisons using a **50.0%** analysis cutoff alongside sensor immersion tests, without establishing an experimentally validated wet/dry classification boundary for the separate seven-site dataset. In our research protocol, **20.0%** is evaluated as a research-selected sensitivity threshold for comparative protocol analysis. Under the 12-hour nocturnal window, five stations (Sites 1–5) tie at the 12.0 h/night $P_{90}$ saturation ceiling; Site 2 is selected by the secondary criterion (highest seasonal nocturnal mean: 11.23 h/night at 20% and 9.49 h/night at 50%). Candidate selection is invariant across both 20% and 50% thresholds.
   - **Cadence-Aware Gap Detection:** The sampling cadence is nominal 60.0 minutes (hourly). Using a cadence-aware gap threshold of 90.0 minutes (> 1.5 hr interval flags missing observation), exactly 153 missing observation gaps were detected across all 7 sites (Site 1: 5, Site 2: 23, Site 3: 35, Site 4: 71, Site 5: 12, Site 6: 2, Site 7: 5). The earlier reported count of 55,543 was an artifact of applying a 20-minute gap threshold to 60-minute data.
   - **Nocturnal 18:00–06:00 Window:** The nominal nocturnal duration is 12 hours. Because the seven stations are located in Italy (latitudes 38.987°N to 45.559°N, longitudes 7.835°E to 13.746°E), nocturnal wetness was computed strictly within the 18:00–06:00 window.
   - **Multi-Year Asynchrony:** `sites.json` documents that stations were monitored across different years (Sites 1, 3, 5 in 2022; Sites 2, 4 in 2023; Sites 6, 7 in 2024). They represent regional microclimates rather than simultaneous within-field nodes.
2. **Tomato Dataset (`c837v6p8ph/2`):**
   - **Timezone:** Authoritatively documented in `DATA_DICTIONARY.md` as naive local time (`Europe/Rome`).
   - **Units:** Soil moisture reported in relative probe output percentage ($0$--$100\%$). Irrigation actuator reported in minutes of valve opening (`irrigation_duration_minutes`) and water volume over preceding 4 hours (`water_vol_past_4h`, liters).
   - **Leakage Prohibition:** The dataset authors explicitly state in `DATA_DICTIONARY.md`: `water_vol_to_24h: DROP THIS for a purely predictive benchmark` and `real_moisture_delta: Never use as a feature`.
3. **Libelium Dataset (`cnfh4stzzx/2`):**
   - **Timezone:** Raw timestamps retained as recorded by Waspmote Plug & Sense units in Goraj, Albania (`Europe/Tirane`, CET/CEST). Both nodes share the same receiver clock.
   - **Units:** TEROS 11 soil moisture is recorded in $m^3/m^3$ fraction (`teros11_vwc_m3_m3`). Scaled by $100.0$ to convert to $\% \text{ VWC}$ to evaluate divergence against the Protocol v2.0 10.0% VWC threshold.

---

## 3. Dataset 1: Mendeley Tomato Multi-Sector Irrigation Dataset

### 3.1 Dataset Characteristics & Schema Inspection
- **Source Files Evaluated:**
  - `dataset_zone_1_preprocessed.csv` (SHA256: `e3c8ce709e89d1a7944bfbcfc0120a2f0166b4198cdf390efad659fd3acb9a89`, 1,760,164 bytes, 9,531 rows)
  - `dataset_zone_2_preprocessed.csv` (SHA256: `7436f9d1b03da0dd4a76cf2005e9ded38881d88d6b85c7f20cf7a3dc561ee5ac`, 2,164,170 bytes, 11,929 rows)
  - Total records evaluated: 21,460 rows at 10-minute cadence.
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
- **Un-preprocessed Merged Files (`dataset_zone_1.csv`):** The raw merged file contains intermittent missing intervals; the longest contiguous segment without gaps exceeding 10 minutes was only 65 steps (10.8 hours). Because Protocol v2.0 requires 24 hours of future contiguous data (144 steps) and 4 hours of contiguous historical lags (24 steps), un-preprocessed files cannot support unbroken 24-hour forecasting without imputation.
- **Preprocessed Files (`dataset_zone_1_preprocessed.csv`):** Authors provided quality-controlled, regularized sequences containing continuous multi-day runs (up to 2,702 steps = 18.8 days), enabling clean train/validation/test chronological splits.
- **Purged Chronological Splitting with Embargo:** To prevent forecast-label leakage across chronological partitions, `purged_chronological_indices()` enforced an embargo window of 144 steps (24 hours). Training rows whose forecast targets fell within the validation period were purged (144 rows purged); validation rows whose forecast targets fell within the test period were purged (144 rows purged).
- **Leakage Feature Elimination:** Explicit rejection was enforced for forward-looking tokens `("future", "target", "ahead", "label", "to_24h", "delta")`. Features are built strictly from past and present observations.

### 3.3 Verified 24-Hour Ahead Forecasting Results (Purged Chronological Split)

#### Sector 1 (Zone 1, Open Field — Test $n=652$; Purged Train $n=2894$; Purged Val $n=507$):
| Model | Split | Test RMSE (% VWC) | Test MAE (% VWC) | Test $R^2$ | Validation RMSE (% VWC) |
| :--- | :--- | :---: | :---: | :---: | :---: |
| **Persistence (Baseline)** | Test | 1.196 | 0.242 | -0.662 | N/A |
| **Ridge Regression** | Test | 1.068 | 0.707 | -0.326 | 1.070 |
| **Random Forest** | Test | 0.972 | 0.451 | -0.098 | 1.149 |
| **Gradient Boosting (GBDT)** | **Test** | **0.914** | **0.377** | **+0.028** | **1.185** |

*Performance Interpretation & Metric Trade-Offs:*
- **RMSE vs. MAE Trade-off:** GBDT achieved a 23.6% RMSE reduction over persistence (0.914% vs. 1.196% VWC) on strictly embargoed test data, and Ridge achieved a 13.9% RMSE reduction in Zone 2 (0.593% vs. 0.689% VWC). However, naive persistence achieves lower MAE than the ML models (0.242% vs. 0.377% in Zone 1; 0.150% vs. 0.347% in Zone 2). This occurs because squared-error minimization ($L_2$ loss) compresses large prediction spikes, whereas persistence incurs near-zero absolute error ($L_1$ loss) during quiet, quiescent dry-downs. General ML superiority is therefore NOT claimed.
- **Low Positive $R^2$:** Test $R^2$ values are modest (+0.028 in Zone 1, +0.165 in Zone 2), explaining 2.8% to 16.5% of variance beyond the test set mean. This reflects the genuine difficulty of 24-hour ahead horizon soil moisture forecasting under open-field conditions without explicit future irrigation schedule knowledge.
- **Artifactual Drought Recall:** The 100% drought-crossing recall is an artifact of class imbalance under the arbitrary 22.0% VWC threshold, because during the held-out test periods (which occur in later dry stages of the crop season), 100% of the actual VWC measurements (652/652 in Zone 1, 1,030/1,030 in Zone 2) were already below 22.0% VWC.
- **Irrigation Telemetry Volume Assessment:** In the preprocessed tables, `water_vol_past_4h` represents a rolling 4-hour window sum. Across all 21,460 records, the sum of reported values is $218,433.6\text{ L}$ ($79,516.8\text{ L}$ in Zone 1; $138,916.8\text{ L}$ in Zone 2). As documented, this value is an integral over a rolling variable and is flagged with `cumulative_volume_verified: false` to avoid double-counting.

---

## 4. Dataset 2: Mendeley Leaf Wetness & Agrometeorological Dataset

### 4.1 Dataset Characteristics & Schema Inspection
- **Source Files Evaluated:** `site1.csv` through `site7.csv` (Total: 55,550 hourly records, 0 parse failures).
- **Timezone:** Verified as UTC from dataset `README.md` (line 17) and ISO 8601 `"Z"` suffix in `sites.json`.
- **Sampling Interval & Gaps:** Nominal cadence is 60.0 minutes (hourly). Using a 90-minute gap threshold, exactly 153 missing observation gaps were detected across all 7 sites (Site 1: 5, Site 2: 23, Site 3: 35, Site 4: 71, Site 5: 12, Site 6: 2, Site 7: 5).
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

### 4.2 Nocturnal Leaf Wetness Duration & Humid Pole Selection
Protocol v2.0 selects Node A using nocturnal leaf-wetness duration ($\text{LWD}_{\text{noct}}$), evaluated strictly during the 18:00–06:00 UTC window (nominal 12 hours).

#### Sensitivity Analysis Across Wetness Thresholds (18:00–06:00 Nocturnal Window):
| Station ID | Location / Terrain | Records | $P_{90}$ LWD at 20% (h/night)* | $P_{90}$ LWD at 30% (h/night) | $P_{90}$ LWD at 40% (h/night) | $P_{90}$ LWD at 50% (h/night)** | Mean LWD at 20% (h/night) | Mean LWD at 50% (h/night) |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Site 2** | Sardinia (Plain, 33m) | 8,278 | **12.0** | 12.0 | 12.0 | **12.0** | **11.23** | **9.49** |
| **Site 1** | Sardinia (Hill, 125m) | 8,244 | **12.0** | 12.0 | 12.0 | **12.0** | **8.58** | 5.65 |
| **Site 3** | Tuscany (Hill, 242m) | 7,854 | **12.0** | 12.0 | 11.0 | 10.0 | **5.98** | 3.66 |
| **Site 5** | Piedmont (Hill, 187m) | 7,331 | **12.0** | 12.0 | 11.0 | 10.0 | **4.69** | 2.61 |
| **Site 4** | Marche (Hill, 258m) | 6,874 | **12.0** | 11.0 | 11.0 | 9.0 | **3.87** | 2.44 |
| **Site 7** | Piedmont (High, 418m) | 8,538 | **10.2** | 6.0 | 2.0 | 0.0 | **2.43** | 0.28 |
| **Site 6** | Piedmont (High, 434m) | 8,431 | **3.8** | 1.0 | 0.0 | 0.0 | **0.98** | 0.15 |

*\*20% threshold is evaluated as a research-selected sensitivity threshold for comparative protocol analysis.*  
*\*\*50% threshold is the published leaf-wetness analysis cutoff reported by Filipescu, Colucci, and Trinchero (IEEE Transactions on AgriFood Electronics, 2024), evaluated alongside immersion tests without establishing an experimental wet/dry classification boundary for the seven-site dataset.*

- **Humid Pole Candidate Selection & Tie-Break Rule:**
  - *Primary Criterion:* 90th percentile nocturnal LWD ($P_{90}$). Under the 12-hour nocturnal window, five sites (Sites 1, 2, 3, 4, 5) reach the saturation ceiling of $P_{90} = 12.0\text{ h/night}$.
  - *Secondary Criterion:* Highest mean nocturnal LWD among max-$P_{90}$ tied candidates decisively isolates **Site 2** (seasonal mean 11.23 h/night at 20%; 9.49 h/night at 50%), far exceeding Site 1 (8.58 h/night) and Site 3 (5.98 h/night).
  - *Tertiary Criterion:* Deterministic alphabetical site name ordering applied if both $P_{90}$ and mean tie.
  - *Order Independence:* Candidate selection is 100% deterministic and invariant to input file ordering.
- **Microclimatic Contrast:** In contrast to the humid Sardinian plain, high-elevation Piedmont stations (Sites 6 and 7) exhibit mean nocturnal LWD of only 0.98 and 2.43 h/night, demonstrating pronounced multi-station microclimatic diversity.

### 4.3 Daily Wallin DSV vs. LWS-Modified DSV Progression
The adapter computed daily Wallin Disease Severity Values ($\mathrm{DSV}_{\text{Wallin}}$ based solely on $\mathrm{RH} \ge 90\%$) and leaf-wetness-modified values ($\mathrm{DSV}_{\mathrm{LWS}}$ integrating physical surface wetness):
- During clear nights with radiative cooling, surface wetness on lower leaves persists even when aspirated air RH drops into the 80--89% range.
- Standard Wallin DSV recorded zero severity accumulation during these periods, whereas $\mathrm{DSV}_{\mathrm{LWS}}$ accumulated 1 to 2 severity units per day.
- Output tables retained: `results/real_data_validation/leafwetness/nightly_leafwetness_lwd.csv` and `results/real_data_validation/leafwetness/daily_leafwetness_dsv.csv`.

---

## 5. Dataset 3: Mendeley Libelium Two-Node Olive Grove Dataset

### 5.1 Dataset Characteristics & Schema Inspection
- **Source File Evaluated:** `libelium_measurements_quality_controlled.csv` (SHA256: `65d899c4e98b5d08c954da332b937ada81a25bca3265f2cc7fab43929acf307d`, 3,596,067 bytes, 9,435 rows).
- **Nodes Monitored:** `Goraj-1` (6,462 frames) and `Goraj-2` (2,973 frames).
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
- **Median Sampling Cadence:** 10.38 minutes for Goraj-1; 10.35 minutes for Goraj-2.
- **Aligned Paired Records:** Merging nearest timestamps within a 10-minute tolerance produced 1,617 aligned simultaneous two-node observations (1,340 trailing rolling windows of size $W = 278$ steps).

### 5.3 Two-Node Spatial Sufficiency & Decoupling Analysis
Protocol v2.0 evaluates a trailing 48-hour rolling window ($W = 278$ steps at 10.3-minute cadence) to detect when two nodes decouple:
- **Mean Absolute VWC Divergence:** Latest $|\theta_1 - \theta_2| = 4.07\%$ VWC.
- **Rolling Spearman Rank Correlation:** Dropped to $r_s = -0.7388$ ($p < 10^{-5}$), demonstrating inverse soil water dynamics between the two orchard zones.
- **Insufficient Coverage Trigger ($\mathcal{F}_{\text{insuff}} = 1$):**
  - **ProtocolConfig Condition:** $\overline{|\Delta\theta|} > 10.0\%$ VWC **OR** $r_s < 0.70$.
    - Out of 1,340 rolling windows, **873 windows triggered $\mathcal{F}_{\text{insuff}} = 1$** (65.1% of evaluated windows).
  - **Conservative Condition ($r_s < 0.60$):**
    - Out of 1,340 rolling windows, **847 windows triggered $\mathcal{F}_{\text{insuff}} = 1$** (63.2% of evaluated windows).
  - Output table retained: `results/real_data_validation/libelium/rolling_spatial_sufficiency.csv`.
- **Agronomic Implication:** In undulating terrain, soil drying rates in different sub-zones can decouple due to subsurface lateral flow and differential canopy cover. Dynamic spatial sufficiency monitoring is mandatory to safeguard against silent micro-zone decoupling.

---

## 6. Publication Figures

The script `src/plot_real_data_validation.py` generated three publication-quality figures from the verified rerun outputs:

1. `figures/real_data_validation/tomato_vwc_forecasting_benchmark.png`:
   - Comparison of 24h VWC forecast RMSE and MAE across Persistence, Ridge, Random Forest, and GBDT across open-field Zone 1 and Zone 2 on strictly purged test splits.
2. `figures/real_data_validation/leafwetness_microclimate_dsv_ranking.png`:
   - Panel A: Bar chart of $P_{90}$ nocturnal LWD across all 7 stations, isolating Site 1 and Site 2 ($12.0\text{ h/night}$) as humid poles.
   - Panel B: Boxplot distribution of daily LWS-modified Disease Severity Values across sites.
3. `figures/real_data_validation/libelium_two_node_spatial_sufficiency.png`:
   - Dual-panel time series showing trailing 48h rolling divergence $|\Delta\theta|$ and rolling Spearman rank correlation $r_s$ between Goraj-1 and Goraj-2, highlighting the 873 windows where the adaptive sufficiency trigger was active.

---

## 7. Limitations & Scientifically Skipped Experiments

1. **Raw Un-preprocessed Tomato 24h Forecasting:** Skipped because raw files contain frequent missing data intervals (max contiguous run of 65 steps = 10.8 hours), precluding an unbroken 24-hour ahead horizon (144 steps) without imputation. Preprocessed tables were evaluated instead.
2. **Tomato Greenhouse Sectors (Zones 3, 4, 5):** Skipped because the Sentinel Plant Network targets open-field solanaceous crops; greenhouse/polytunnel microclimates do not match open-field ET dynamics.
3. **Cumulative Tomato Irrigation Volume:** Summing `water_vol_past_4h` row-by-row was flagged as non-cumulative because it is a rolling 4-hour window sum; raw incremental valve volumes require event-level reconstruction.
4. **Synchronous Single-Field Network in Leaf Wetness:** The seven agrometeorological stations were deployed in different Italian regions across different calendar years (2022--2024); they validate regional microclimatic LWD diversity, not a concurrent 7-node parcel network.
5. **Absence of Ground-Truth Pathogen Imagery:** Public datasets contain agrometeorological risk proxies ($\mathrm{DSV}$), not daily photographic potato late-blight lesion area measurements.
6. **Calibration Transfer to Target Parcel:** Mediterranean soils (calcareous loam in Albania, Italian clay-loam) differ from the targeted sandy-clay-loam soils in Jharkhand, India. External data validation does not replace in-situ dielectric probe calibration or physical field trials.
