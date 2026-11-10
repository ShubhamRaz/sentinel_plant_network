# Supplementary Material S2: Experimental Methodology, Data Cleaning, and Quality Control

**Project:** Sentinel Plant Network (Protocol v2.0)  
**Authors:** Sentinel Plant Network Research Group  
**Scope:** Data Ingestion, Timestamp Alignment, Gap Detection, Imputation Rules, and Quality Filters  

---

## 1. Data Ingestion Architecture & Canonical Mappings

External benchmark datasets exhibit divergent schemas, column identifiers, and measurement units. To eliminate fragile ad-hoc parsing, the Sentinel Plant Network implements an adapter pattern via `src/real_data_validation.py` using canonical JSON configuration mappings:

- `data/mappings/tomato_mapping.json`: Maps `soil_moisture` (% VWC) and `water_vol_past_4h` (liters).
- `data/mappings/leafwetness_mapping.json`: Maps `time` (UTC), `leaf_top` (capacitive 0–100%), `rh` (% RH), and `temperature` (°C).
- `data/mappings/libelium_mapping.json`: Maps `timestamp`, `device_id`, and `teros11_vwc_m3_m3` (with `scale_vwc: 100.0`).

---

## 2. Quality Control & Timestamp Plausibility Filters

Every ingested telemetry series is subjected to automated data-cleaning and quality diagnostics:

1. **Timestamp Monotonicity and Duplicate Checking:**
   - Evaluates composite primary keys (`__source_file + timestamp` or `device_id + timestamp`).
   - Duplicate records are flagged and deduplicated; across all three evaluated datasets, exactly zero duplicate timestamps were detected.
2. **Interval Cadence and Gap Detection:**
   - Computes median inter-reading delta $\Delta t_{\text{median}}$.
   - Cadence-aware gap thresholds:
     * 10-minute series (Tomato, Libelium): $\tau_{\text{gap}} = 20.0\text{ min}$ (intervals $> 20$ min indicate omitted readings). Libelium exhibited 105 gaps (Goraj-1: 72, Goraj-2: 33), with the largest gap spanning 14,560.7 min (~10.1 days).
     * Hourly series (Leaf Wetness): $\tau_{\text{gap}} = 90.0\text{ min}$ (intervals $> 90$ min indicate omitted observation cycles). Across all 7 sites (55,550 hourly rows), exactly 153 missing observation gaps were detected (Site 1: 5, Site 2: 23, Site 3: 35, Site 4: 71, Site 5: 12, Site 6: 2, Site 7: 5). The earlier reported count of 55,543 was an artifact of applying a 20-minute gap threshold to 60-minute data.
3. **Missing Value Auditing:**
   - Tomato: 288 missing cells out of 21,460 rows (1.34%).
   - Leaf Wetness: 0 missing cells out of 55,550 hourly rows (100% complete).
   - Libelium: 45,188 missing sensor channel cells out of 9,435 frames (Goraj-1 experienced intermittent soil sensor drops while Goraj-2 was fully populated).

---

## 3. Sensor Scaling & Unit Standardization

- **Fractional Soil Moisture Scaling:** The TEROS 11 probe reports volumetric water content as a dimensionless fraction ($\text{m}^3/\text{m}^3 \in [0.0, 1.0]$). Protocol v2.0 defines all operational thresholds (such as $\mathrm{MAD} = 22.0\%$ and divergence $|\Delta\theta| > 10.0\%$) in percentage points. In `validate_libelium()`, fractional readings are automatically detected and scaled:
  $$\theta_{\% \text{ VWC}} = 100.0 \times \theta_{\text{m}^3/\text{m}^3}$$
- **Leaf Wetness Capacitive Normalization & Threshold Analysis Choices:** The Seven-Site sensors output a percentage scale from 0.0 (dry) to 100.0 (fully wetted):
  - **Published Analysis Cutoff (50.0%):** Filipescu et al. (2024, *IEEE Trans. AgriFood Electronics*, DOI: 10.1109/TAFE.2024.3401252) reported seasonal leaf-wetness comparisons using a 50% cutoff alongside sensor immersion experiments. However, the published cutoff was not established as an experimentally validated wet/dry decision boundary for all field conditions or across the separate seven-site dataset.
  - **Research-Selected Sensitivity Threshold (20.0%):** In our comparative analysis, a lower threshold of 20.0% is evaluated as a research-selected sensitivity threshold:
    $$W(t) = \begin{cases} 1 & \text{if } \text{LWS}(t) \ge 20.0\% \\ 0 & \text{otherwise} \end{cases}$$
  - **Candidate Selection Invariance:** Site 2 is selected as candidate Node A under both analytical thresholds (mean 11.23 h/night at 20%, 9.49 h/night at 50%), confirming robustness against threshold choice.

---

## 4. Nocturnal vs. Daily Aggregation Protocols

To ensure rigorous biological alignment, two separate temporal aggregation pipelines are enforced:

1. **Nocturnal Leaf Wetness Duration (LWD) & Humid-Pole Selection:**
   - Window: 18:00:00 UTC (inclusive) to 06:00:00 UTC (exclusive). Nominal duration: exactly 12.0 hours per night.
   - Purpose: Evaluation of regional microclimatic wetness and selection of candidate Node A under Protocol v2.0. Dew formation and oomycete zoospore release occur predominantly during nocturnal hours.
   - **Multi-Year Regional Scope Limitation:** Metadata in `sites.json` confirm that the seven stations operated asynchronously across separate Italian regions and monitoring years (Sites 1, 3, 5: 2022; Sites 2, 4: 2023; Sites 6, 7: 2024). They represent regional microclimatic diversity across topographically distinct agro-climatic zones, not concurrent nodes in a single experimental field. Site 2 represents the highest-ranked humid station in the regional multi-site dataset under Protocol v2.0, not a co-located parcel's humid microclimate pole. Temporal and geographical divergence limits direct station-to-station comparisons and cannot demonstrate concurrent within-field dual-pole network performance.
   - **Multi-Tier Deterministic Ranking:**
     * *Primary criterion:* Maximum $P_{90}$ nocturnal LWD. Under the 12-hour ceiling, five sites (Sites 1, 2, 3, 4, 5) hit $P_{90} = 12.0\text{ h/night}$.
     * *Secondary criterion:* Highest mean nocturnal LWD among max-$P_{90}$ tied candidates decisively isolates **Site 2** as the highest-ranked humid station under the protocol (mean 11.23 h/night vs Site 1 at 8.58 h/night, Site 3 at 5.98 h/night, Site 5 at 4.69 h/night, Site 4 at 3.87 h/night).
     * *Tertiary tie-break:* Alphabetically smallest site identifier guarantees complete order-invariance if both $P_{90}$ and mean tie.
2. **Daily Disease Severity Values (DSV):**
   - Window: Full 24-hour diurnal cycle (00:00:00 to 23:59:59 UTC).
   - Models:
     - **Wallin DSV:** Lookup based on ambient temperature ($T_a$) and duration of hours with $\mathrm{RH} \ge 90\%$.
     - **LWS-Modified DSV:** Lookup substituting physical leaf wetness duration ($W(t) = 1$) for $\mathrm{RH} \ge 90\%$.
   - Demonstrates that ambient relative humidity underestimates foliar pathogen risk during radiatively cooled clear nights where foliar dew persists while aspirated air humidity dips between 80% and 89%.
