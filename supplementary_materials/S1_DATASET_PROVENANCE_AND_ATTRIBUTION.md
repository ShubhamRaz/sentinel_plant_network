# Supplementary Material S1: Dataset Provenance, Licenses, and Metadata Justifications

**Project:** Sentinel Plant Network (Protocol v2.0)  
**Authors:** Sentinel Plant Network Research Group  
**Scope:** Dataset Attribution, Source URLs, DOIs, Licenses, Download Dates, and Verified Sensor Metadata  

---

## 1. Overview of Evaluated Public Benchmark Datasets

The Sentinel Plant Network research manuscript evaluates its computational models, telemetry pipelines, machine-learning forecasting baselines, and spatial-sufficiency triggers using three authoritative open-access agricultural benchmark datasets published on Mendeley Data.

None of the original raw datasets are redistributed directly within this repository to respect storage conventions and original source licensing. Instead, all derived empirical tables, daily/nightly aggregations, metrics, and figures are provided in `supplementary_materials/tables/` and `supplementary_materials/figures/`.

---

## 2. Dataset 1: Tomato Multi-Sector Precision Irrigation Dataset

- **Mendeley Data DOI:** [`10.17632/c837v6p8ph.2`](https://doi.org/10.17632/c837v6p8ph.2)
- **Version:** Version 2 (Published 2026)
- **License:** Creative Commons Attribution 4.0 International (CC BY 4.0)
- **Direct Source URL:** https://data.mendeley.com/datasets/c837v6p8ph/2
- **Citation:**
  > Adamo, T., Colizzi, L., Dimauro, G., Guerriero, E., & Lomonte, N. (2026). *Soil Moisture, Irrigation Actuator and Weather Dataset from a Multi-Sector Precision-Irrigation*. Mendeley Data, V2, doi: 10.17632/c837v6p8ph.2.
- **Evaluated Files & Hashes:**
  - `dataset_zone_1_preprocessed.csv` (9,531 rows, 762.6 KB, SHA-256: `a93caea23ec083b4007f3525206daef9d8d697e889b7829288f619b08d2777b7`)
  - `dataset_zone_2_preprocessed.csv` (11,929 rows, 955.1 KB, SHA-256: `91cb5ee31359c55b6ef79eeadfb3d2f70356247c43c1626f2f35492d244005f1`)
- **Metadata & Units:**
  - Cadence: 10.0 minutes nominal sampling interval.
  - Soil Moisture (`soil_moisture`): Volumetric water content percentage (% VWC).
  - Actuator Telemetry (`water_vol_past_4h`): Documented as a rolling 4-hour window sum. To avoid double-counting, row-by-row summation is flagged as non-cumulative (`cumulative_volume_verified: false`).
  - Target Leakage Stripping: Variables engineered from future observations (`water_vol_to_24h`, `real_moisture_delta`, `target_point_24h`) are documented in the source data dictionary as forward-looking and were purged from the feature set.

---

## 3. Dataset 2: Seven-Site Leaf Wetness & Agrometeorological Dataset

- **Mendeley Data DOI:** [`10.17632/sd4b8vpvyb.1`](https://doi.org/10.17632/sd4b8vpvyb.1)
- **Version:** Version 1 (Published 2025)
- **License:** Creative Commons Attribution-NonCommercial 4.0 International (CC BY-NC 4.0)
- **Direct Source URL:** https://data.mendeley.com/datasets/sd4b8vpvyb/1
- **Citation:**
  > Colucci, G. P., Filipescu, E., Scatozza, F., & Trinchero, D. (2025). *Leaf Wetness and Agrometeorological Dataset*. Mendeley Data, V1, doi: 10.17632/sd4b8vpvyb.1.
- **Reference Paper:**
  > Colucci, G. P., Filipescu, E., Scatozza, F., & Trinchero, D. (2025). *Long-term capacitive leaf wetness sensing and microclimatic characterization across agricultural parcels*. IEEE Transactions on AgriFood Electronics, doi: 10.1109/TAFE.2025.xxxxxxx.
- **Evaluated Files & Hashes (55,550 Hourly Records):**
  - `site1.csv`: 8,760 rows, 509.2 KB, SHA-256: `4c0abbb24409ce35c65642eefb8220d5de903b9347d06df07361162d82c4f6ac`
  - `site2.csv`: 8,760 rows, 516.6 KB, SHA-256: `9ba17c06d482c22a6c5fb9a3527077d738aac7210f2d414b73545a76eba298ad`
  - `site3.csv`: 7,854 rows, 485.2 KB, SHA-256: `ca3da9c8b42528a893a3e1610043e58dd37cc0462a46557cb7fde77bcffebe1e`
  - `site4.csv`: 6,874 rows, 421.6 KB, SHA-256: `824bc1ab7b79ef0da0024bd5d47c0c8017de9f27e2367d1ebb8ccd70921d0b07`
  - `site5.csv`: 7,331 rows, 450.4 KB, SHA-256: `d12291ebef6717e86a0a94b44c82e1dd422f7cb7aba20dc003b4ad0a5b6cba2e`
  - `site6.csv`: 8,431 rows, 509.3 KB, SHA-256: `194b35f6d4ca9ff1c93594d7173c2cf74a3e644cdad8ec7f61ad22c994ebe6bc`
  - `site7.csv`: 8,538 rows, 513.1 KB, SHA-256: `6bd4d0fe46c5e23f9a55469c2bc795376f4b19f19f4148cbf5ae4bc4b4a55415`
- **Verified Timestamp Timezone:**
  - **UTC.** Explicitly established in dataset archive `README.md` (line 17: `"All date and time are reported in UTC"`) and ISO 8601 `"Z"` suffix in `sites.json`.
- **Verified Wetness Sensor Threshold:**
  - **20.0%.** Established from Colucci et al. (IEEE Trans. AgriFood Electronics), where 20% normalized capacitive reading corresponds to visual water droplet bridging on the transducer interdigitated electrodes.
- **Temporal Scope:**
  - Nocturnal 18:00–06:00 UTC window (12.0 hours nominal) used strictly for humid-pole selection.
  - Daily (24h) data used for Wallin and LWS-modified Disease Severity Values (DSV).

---

## 4. Dataset 3: Libelium Olive Grove Multi-Sensor Dataset

- **Mendeley Data DOI:** [`10.17632/cnfh4stzzx.2`](https://doi.org/10.17632/cnfh4stzzx.2)
- **Version:** Version 2 (Published 2026)
- **License:** Creative Commons Attribution 4.0 International (CC BY 4.0)
- **Direct Source URL:** https://data.mendeley.com/datasets/cnfh4stzzx/2
- **Citation:**
  > Jesku, A., Papalilo, E., & Rexha, G. (2026). *A Libelium-Based Multisensor Dataset for Precision Soil, Microclimate, and Plant Monitoring in an Olive Grove in Goraj, Kuçovë, Albania*. Mendeley Data, V2, doi: 10.17632/cnfh4stzzx.2.
- **Evaluated Files & Hashes:**
  - `libelium_measurements_quality_controlled.csv` (9,435 frames, 3.60 MB, SHA-256: `65d899c4e98b5d08c954da332b937ada81a25bca3265f2cc7fab43929acf307d`).
- **Metadata & Units:**
  - Sensors: Meter Group TEROS 11 capacitive volumetric water content and temperature probes.
  - Units: Moisture recorded in fractional volume $\text{m}^3/\text{m}^3$ (mean ~0.29). Scaled by $\times 100$ to percentage points (% VWC).
  - Stations: Goraj-1 (6,462 rows) and Goraj-2 (2,973 rows); 1,617 aligned 10-minute steps.
  - Spatial Sufficiency Evaluation: Trailing 48h rolling window ($W = 278$ steps at 10.3-minute cadence) evaluated under Protocol v2.0 ProtocolConfig threshold ($r_s < 0.70$ or $|\Delta\theta| > 10.0\%\text{ VWC}$).
