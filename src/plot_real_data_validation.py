"""Generate publication-quality figures from real public dataset validation."""
import json
from pathlib import Path
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

plt.style.use("seaborn-v0_8-whitegrid" if "seaborn-v0_8-whitegrid" in plt.style.available else "default")
plt.rcParams.update({
    "font.family": "serif",
    "font.size": 10,
    "axes.labelsize": 11,
    "axes.titlesize": 12,
    "xtick.labelsize": 9,
    "ytick.labelsize": 9,
    "legend.fontsize": 9,
    "figure.titlesize": 13,
})

RESULTS_DIR = Path("results/real_data_validation")
FIG_DIR = Path("figures/real_data_validation")
FIG_DIR.mkdir(parents=True, exist_ok=True)


def plot_libelium():
    roll_path = RESULTS_DIR / "libelium" / "rolling_spatial_sufficiency.csv"
    if not roll_path.exists():
        print("Libelium rolling file missing, skipping.")
        return
    df = pd.read_csv(roll_path)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values("timestamp")

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(9, 5.5), sharex=True)
    
    # Panel 1: Divergence
    ax1.plot(df["timestamp"], df["mean_abs_vwc_diff"], color="#2b5c8f", lw=1.2, label=r"Trailing 48h Mean $|\Delta\theta|$")
    ax1.axhline(10.0, color="#d95f02", linestyle="--", lw=1.2, label=r"Protocol Trigger Threshold ($10\%$ VWC)")
    ax1.set_ylabel(r"Divergence $|\Delta\theta|$ (% VWC)")
    ax1.legend(loc="upper left", frameon=True)
    ax1.set_title("Libelium Olive Grove (Albania): Two-Node Spatial Sufficiency Telemetry")

    # Panel 2: Spearman correlation
    ax2.plot(df["timestamp"], df["spearman_r"], color="#7570b3", lw=1.2, label=r"Trailing 48h Spearman $r_s$")
    ax2.axhline(0.60, color="#d95f02", linestyle="--", lw=1.2, label=r"Protocol Minimum $r_s$ Threshold ($0.60$)")
    ax2.axhline(0.0, color="gray", linestyle=":", lw=0.8)
    ax2.set_ylabel(r"Spearman Rank $r_s$")
    ax2.set_xlabel("Observation Timestamp (UTC)")
    ax2.legend(loc="lower left", frameon=True)
    ax2.set_ylim(-1.05, 1.05)

    # Shade insufficient coverage triggers
    flagged = df["insufficient_coverage_flag"].to_numpy()
    if flagged.any():
        ax1.fill_between(df["timestamp"], 0, df["mean_abs_vwc_diff"].max() * 1.15,
                         where=flagged, color="#d95f02", alpha=0.15, label="Trigger Active (Insufficient Coverage)")
        ax2.fill_between(df["timestamp"], -1.05, 1.05,
                         where=flagged, color="#d95f02", alpha=0.15)
        ax1.legend(loc="upper left", frameon=True)

    plt.tight_layout()
    out = FIG_DIR / "libelium_two_node_spatial_sufficiency.png"
    plt.savefig(out, dpi=300)
    plt.close()
    print(f"Saved: {out}")


def plot_leafwetness():
    daily_path = RESULTS_DIR / "leafwetness" / "daily_leafwetness_dsv.csv"
    rep_path = RESULTS_DIR / "leafwetness" / "validation_report.json"
    if not daily_path.exists() or not rep_path.exists():
        print("Leafwetness files missing, skipping.")
        return
    daily = pd.read_csv(daily_path)
    with rep_path.open(encoding="utf-8") as f:
        rep = json.load(f)

    p90_dict = rep["site_p90_nocturnal_lwd_hours"]
    sites = sorted(p90_dict.keys(), key=lambda s: p90_dict[s], reverse=True)
    p90_vals = [p90_dict[s] for s in sites]
    site_labels = [s.replace(".csv", "").upper() for s in sites]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4.5))

    # Bar chart of P90 LWD
    colors = ["#1b9e77" if v == max(p90_vals) else "#4575b4" for v in p90_vals]
    bars = ax1.bar(site_labels, p90_vals, color=colors, edgecolor="black", lw=0.6)
    ax1.set_ylabel("90th Percentile Nocturnal LWD (hours/night)")
    ax1.set_xlabel("Monitoring Station / Microclimate Site")
    ax1.set_title("A: Nocturnal Microclimatic LWD ($P_{90}$)")
    for bar in bars:
        yval = bar.get_height()
        ax1.text(bar.get_x() + bar.get_width()/2.0, yval + 0.4, f"{yval:.1f}h", ha="center", va="bottom", fontsize=8.5)
    ax1.set_ylim(0, 27)

    # Boxplot of DSV comparison
    dsv_data = []
    labels = []
    for site in sites:
        sub = daily[daily["site"] == site]
        dsv_data.append(sub["dsv_lws_modified"].dropna())
        labels.append(site.replace(".csv", "").upper())

    bp = ax2.boxplot(dsv_data, tick_labels=labels, patch_artist=True,
                     boxprops=dict(facecolor="#abd9e9", color="#2c7bb6"),
                     medianprops=dict(color="#d7191c", lw=1.5))
    ax2.set_ylabel("Daily LWS-Modified DSV")
    ax2.set_xlabel("Monitoring Station / Microclimate Site")
    ax2.set_title("B: Daily Disease Severity Value (DSV) by Site")

    plt.tight_layout()
    out = FIG_DIR / "leafwetness_microclimate_dsv_ranking.png"
    plt.savefig(out, dpi=300)
    plt.close()
    print(f"Saved: {out}")


def plot_tomato():
    rep_path = RESULTS_DIR / "tomato" / "validation_report.json"
    if not rep_path.exists():
        print("Tomato report missing, skipping.")
        return
    with rep_path.open(encoding="utf-8") as f:
        rep = json.load(f)

    sectors = rep["per_sector"]
    sector_names = list(sectors.keys())
    
    models = ["persistence", "ridge", "random_forest", "gradient_boosting"]
    display_models = ["Persistence", "Ridge Reg.", "Random Forest", "Gradient Boosting"]
    
    rmse_by_zone = {s: [] for s in sector_names}
    mae_by_zone = {s: [] for s in sector_names}
    
    for s_name in sector_names:
        m_list = {m["model"]: m for m in sectors[s_name]["vwc_forecast"]["metrics"]}
        for m in models:
            rmse_by_zone[s_name].append(m_list[m]["rmse"])
            mae_by_zone[s_name].append(m_list[m]["mae"])

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4.5))

    x = np.arange(len(models))
    width = 0.35

    z1_label = "Zone 1 (Open Field)"
    z2_label = "Zone 2 (Open Field)"

    # RMSE plot
    ax1.bar(x - width/2, rmse_by_zone[sector_names[0]], width, label=z1_label, color="#386cb0", edgecolor="black", lw=0.6)
    ax1.bar(x + width/2, rmse_by_zone[sector_names[1]], width, label=z2_label, color="#7fc97f", edgecolor="black", lw=0.6)
    ax1.set_ylabel(r"Test Root Mean Squared Error (% VWC)")
    ax1.set_title(r"A: 24h Ahead VWC Forecast Error (RMSE)")
    ax1.set_xticks(x)
    ax1.set_xticklabels(display_models, rotation=15)
    ax1.legend(frameon=True)

    # MAE plot
    ax2.bar(x - width/2, mae_by_zone[sector_names[0]], width, label=z1_label, color="#386cb0", edgecolor="black", lw=0.6)
    ax2.bar(x + width/2, mae_by_zone[sector_names[1]], width, label=z2_label, color="#7fc97f", edgecolor="black", lw=0.6)
    ax2.set_ylabel(r"Test Mean Absolute Error (% VWC)")
    ax2.set_title(r"B: 24h Ahead VWC Forecast Error (MAE)")
    ax2.set_xticks(x)
    ax2.set_xticklabels(display_models, rotation=15)
    ax2.legend(frameon=True)

    plt.tight_layout()
    out = FIG_DIR / "tomato_vwc_forecasting_benchmark.png"
    plt.savefig(out, dpi=300)
    plt.close()
    print(f"Saved: {out}")


if __name__ == "__main__":
    plot_libelium()
    plot_leafwetness()
    plot_tomato()
