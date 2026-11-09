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
   - Identifies outage intervals exceeding threshold $\tau_{\text{gap}} = 20.0\text{ min}$ (for 10-minute series) or $\tau_{\text{gap}} = 120\text{ min}$ (for hourly series).
   - In Libelium telemetry, largest observed gap was 14,560.7 minutes (~10.1 days) during battery/gateway power disruptions.
3. **Missing Value Auditing:**
   - Tomato: 288 missing cells out of 21,460 rows (1.34%).
   - Leaf Wetness: 0 missing cells out of 55,550 hourly rows (100% complete).
   - Libelium: 45,188 missing sensor channel cells out of 9,435 frames (Goraj-1 experienced intermittent soil sensor drops while Goraj-2 was fully populated).

---

## 3. Sensor Scaling & Unit Standardization

- **Fractional Soil Moisture Scaling:** The TEROS 11 probe reports volumetric water content as a dimensionless fraction ($\text{m}^3/\text{m}^3 \in [0.0, 1.0]$). Protocol v2.0 defines all operational thresholds (such as $\mathrm{MAD} = 22.0\%$ and divergence $|\Delta\theta| > 10.0\%$) in percentage points. In `validate_libelium()`, fractional readings are automatically detected and scaled:
  $$\theta_{\% \text{ VWC}} = 100.0 \times \theta_{\text{m}^3/\text{m}^3}$$
- **Leaf Wetness Capacitive Normalization:** The Seven-Site sensors output a percentage scale from 0.0 (dry) to 100.0 (fully wetted). In accordance with Colucci et al. (2025), a binary wetness indicator is generated:
  $$W(t) = \begin{cases} 1 & \text{if } \text{LWS}(t) \ge 20.0\% \\ 0 & \text{otherwise} \end{cases}$$

---

## 4. Nocturnal vs. Daily Aggregation Protocols

To ensure rigorous biological alignment, two separate temporal aggregation pipelines are enforced:

1. **Nocturnal Leaf Wetness Duration (LWD):**
   - Window: 18:00:00 UTC (inclusive) to 06:00:00 UTC (exclusive). Nominal duration: exactly 12.0 hours per night.
   - Purpose: Identification of microclimatic humid pole (candidate Node A). Dew formation and oomycete zoospore release occur predominantly during nocturnal hours.
2. **Daily Disease Severity Values (DSV):**
   - Window: Full 24-hour diurnal cycle (00:00:00 to 23:59:59 UTC).
   - Models:
     - **Wallin DSV:** Lookup based on ambient temperature ($T_a$) and duration of hours with $\mathrm{RH} \ge 90\%$.
     - **LWS-Modified DSV:** Lookup substituting physical leaf wetness duration ($W(t) = 1$) for $\mathrm{RH} \ge 90\%$.
   - Demonstrates that ambient relative humidity underestimates foliar pathogen risk during radiatively cooled clear nights where foliar dew persists while aspirated air humidity dips between 80% and 89%.
