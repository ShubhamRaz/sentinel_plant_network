"""Design-based diagnostics for the 4-treatment x 4-block RCBD simulation.

This script computes residual diagnostics from plot-level observations. Plant
subsamples are not treated as independent experimental units. It does not
declare assumptions passed; it reports Shapiro-Wilk and Levene statistics for
the analyst to interpret alongside plots and the small sample size.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd
from scipy import stats


def rcbd_diagnostics(
    frame: pd.DataFrame,
    response: str,
    treatment_col: str = "treatment",
    block_col: str = "block",
    reference: str = "T1",
    candidate: str = "T4",
    noninferiority_margin_fraction: float = 0.05,
):
    required = {response, treatment_col, block_col}
    missing = required - set(frame.columns)
    if missing:
        raise KeyError(f"Missing columns: {sorted(missing)}")
    d = frame[[response, treatment_col, block_col]].copy()
    d[response] = pd.to_numeric(d[response], errors="coerce")
    d = d.dropna()
    pivot = d.pivot(index=block_col, columns=treatment_col, values=response)
    if pivot.isna().any().any() or reference not in pivot or candidate not in pivot:
        raise ValueError("A complete balanced RCBD with reference and candidate treatments is required")
    if pivot.shape[0] < 3 or pivot.shape[1] < 3:
        raise ValueError("Too few blocks or treatments for RCBD diagnostics")

    grand = float(pivot.to_numpy().mean())
    treatment_means = pivot.mean(axis=0)
    block_means = pivot.mean(axis=1)
    fitted = pd.DataFrame(
        {t: treatment_means[t] for t in pivot.columns}, index=pivot.index
    ).add(block_means, axis=0).sub(grand)
    residuals = (pivot - fitted).to_numpy().ravel()

    n_blocks, n_treatments = pivot.shape
    df_error = (n_blocks - 1) * (n_treatments - 1)
    ss_error = float(np.square(residuals).sum())
    mse = ss_error / df_error
    ss_treatment = float(n_blocks * np.square(treatment_means - grand).sum())
    ss_block = float(n_treatments * np.square(block_means - grand).sum())
    ss_treatment_total = float((n_treatments - 1) * 0 + ss_treatment)
    ms_treatment = ss_treatment_total / (n_treatments - 1)
    f_treatment = ms_treatment / mse if mse > 0 else float("inf")
    p_treatment = float(stats.f.sf(f_treatment, n_treatments - 1, df_error))

    shapiro = stats.shapiro(residuals) if 3 <= len(residuals) <= 5000 else None
    levene = stats.levene(*[pivot[c].to_numpy() for c in pivot.columns], center="median")
    assumption_checks = {
        "shapiro_wilk_residuals": None if shapiro is None else {
            "statistic": float(shapiro.statistic), "p_value": float(shapiro.pvalue),
            "n_residuals": int(len(residuals)),
        },
        "levene_median_by_treatment": {
            "statistic": float(levene.statistic), "p_value": float(levene.pvalue),
            "groups": int(n_treatments),
        },
        "interpretation": (
            "Diagnostics are descriptive; non-significant tests do not prove assumptions. "
            "Inspect residual plots and consider the small number of independent plots."
        ),
    }

    contrasts = {}
    se_difference = float(np.sqrt(2.0 * mse / n_blocks))
    t_critical = float(stats.t.ppf(0.95, df_error))
    for ref in [c for c in pivot.columns if c != candidate]:
        ref_mean = float(treatment_means[ref])
        cand_mean = float(treatment_means[candidate])
        difference = cand_mean - ref_mean
        margin = -noninferiority_margin_fraction * ref_mean
        t_stat = (difference - margin) / se_difference if se_difference > 0 else float("inf")
        p_one_sided = float(stats.t.sf(t_stat, df_error))
        lower_bound = difference - t_critical * se_difference
        contrasts[f"{candidate}_vs_{ref}"] = {
            "candidate_mean": cand_mean, "reference_mean": ref_mean,
            "difference": float(difference), "margin": float(margin),
            "standard_error": se_difference, "df_error": int(df_error),
            "one_sided_95_ci_lower": float(lower_bound),
            "t_statistic": float(t_stat), "p_value_one_sided": p_one_sided,
            "non_inferior": bool(lower_bound > margin),
        }

    return {
        "design": "randomized_complete_block",
        "independent_units": int(len(d)),
        "blocks": int(n_blocks),
        "treatments": int(n_treatments),
        "response": response,
        "rcbd_anova": {
            "ss_treatment": ss_treatment, "ss_block": ss_block,
            "ss_error": ss_error, "df_error": int(df_error),
            "mse": float(mse), "f_treatment": float(f_treatment),
            "p_value_treatment": p_treatment,
        },
        "assumption_checks": assumption_checks,
        "yield_noninferiority": contrasts,
    }


def run_all_diagnostics(csv_path: Path):
    frame = pd.read_csv(csv_path)
    outputs = {}
    for response in ("marketable_yield_t_ha", "applied_water_mm", "iwp_kg_m3", "audpc_pct_days"):
        if response in frame:
            outputs[response] = rcbd_diagnostics(frame, response)
    return outputs


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("statistical_diagnostics.json"))
    args = parser.parse_args(argv)
    result = run_all_diagnostics(args.input)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
