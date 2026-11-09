# Supplementary Material S5: Reproducibility, Python Environment, and Checksums

**Project:** Sentinel Plant Network (Protocol v2.0)  
**Authors:** Sentinel Plant Network Research Group  
**Scope:** Execution Instructions, Dependency Specifications, Platform Requirements, and Verification Checksums  

---

## 1. Complete Reproducibility Workflow

### Step 1: Environment Setup
Python 3.10 through 3.12 is supported (reference: Python 3.11.9).
```bash
git clone https://github.com/ShubhamRaz/sentinel_plant_network.git
cd sentinel_plant_network
python -m venv .venv

# Activate virtual environment
# Windows PowerShell:
.venv\Scripts\Activate.ps1
# Linux / macOS:
source .venv/bin/activate

# Install dependencies
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### Step 2: Automated Unit and Integration Testing
Run the 20-test test suite:
```bash
pytest -v
```
All 20 tests must pass.

### Step 3: Reproduce Deterministic Digital-Twin Simulations
```bash
python src/run_experiments.py --seed 20261106 --config config.json --output-dir .
```
This script reproduces all synthetic data under `data/simulated_digital_twin/`, results under `results/simulated_digital_twin/`, and plots under `figures/`. Two independent executions produce 100% byte-identical CSV/JSON outputs.

### Step 4: Reproduce Public-Dataset Validation
Ensure original public dataset archives are placed in `data/raw_public/`. Run the complete validation sequence:
```bash
# 1. Tomato Precision Irrigation Forecasting (Zones 1 & 2)
python src/real_data_validation.py \
  --dataset tomato \
  --input "data/raw_public/tomato/Soil Moisture, Irrigation Actuator and Weather Dat/02_processed_data/preprocessed/dataset_zone_1_preprocessed.csv" \
          "data/raw_public/tomato/Soil Moisture, Irrigation Actuator and Weather Dat/02_processed_data/preprocessed/dataset_zone_2_preprocessed.csv" \
  --mapping data/mappings/tomato_mapping.json \
  --step-minutes 10.0 \
  --output-dir results/real_data_validation

# 2. Seven-Site Leaf Wetness Duration (UTC, 20% Wetness Threshold)
python src/real_data_validation.py \
  --dataset leafwetness \
  --input "data/raw_public/leafwetness/Leaf Wetness and Agrometeorological Dataset/site1.csv" \
          "data/raw_public/leafwetness/Leaf Wetness and Agrometeorological Dataset/site2.csv" \
          "data/raw_public/leafwetness/Leaf Wetness and Agrometeorological Dataset/site3.csv" \
          "data/raw_public/leafwetness/Leaf Wetness and Agrometeorological Dataset/site4.csv" \
          "data/raw_public/leafwetness/Leaf Wetness and Agrometeorological Dataset/site5.csv" \
          "data/raw_public/leafwetness/Leaf Wetness and Agrometeorological Dataset/site6.csv" \
          "data/raw_public/leafwetness/Leaf Wetness and Agrometeorological Dataset/site7.csv" \
  --mapping data/mappings/leafwetness_mapping.json \
  --timezone UTC \
  --wet-threshold 20.0 \
  --night-start-hour 18 \
  --night-end-hour 6 \
  --output-dir results/real_data_validation

# 3. Libelium Olive Grove Two-Node Telemetry
python src/real_data_validation.py \
  --dataset libelium \
  --input "data/raw_public/libelium/A Libelium-Based Multisensor Dataset for Precision/extracted/Libelium_Olive_Grove_Dataset_Goraj_Kucova_Albania/Libelium_Olive_Grove_Dataset_Goraj_Kucova_Albania/libelium_measurements_quality_controlled.csv" \
  --mapping data/mappings/libelium_mapping.json \
  --output-dir results/real_data_validation

# 4. Generate Publication Plots
python src/plot_real_data_validation.py
```

---

## 2. Pinned Python Dependencies

Extracted from `requirements.txt`:
```text
numpy>=1.24.0,<2.0.0
pandas>=2.0.0,<2.3.0
scipy>=1.10.0,<1.14.0
scikit-learn>=1.3.0,<1.6.0
statsmodels>=0.14.0,<0.15.0
matplotlib>=3.7.0,<3.10.0
seaborn>=0.12.0,<0.14.0
pytest>=7.4.0,<9.0.0
pytest-cov>=4.1.0,<6.0.0
```

---

## 3. GitHub Actions Continuous Integration Workflow

The repository includes `.github/workflows/reproducibility.yml`, which executes on every push:
1. Provisions Ubuntu latest environment with Python 3.11.
2. Installs dependencies and runs `pytest -q`.
3. Runs `run_experiments.py` twice into separate isolated directories and executes SHA-256 byte comparison on all generated outputs.
4. Compiles C++17 host firmware protocol assertions via `g++ -std=c++17 -Wall -Wextra -Werror tests/test_firmware_host.cpp`.
5. Compiles ESP32-S3 firmware targets (`node_a`, `node_b`, `gateway`) using PlatformIO.
6. Installs TeX Live and compiles `paper/Sentinel_Plant_Network_Journal_Paper.tex` via `latexmk`.
7. Uploads verified digital-twin and manuscript artifacts.
