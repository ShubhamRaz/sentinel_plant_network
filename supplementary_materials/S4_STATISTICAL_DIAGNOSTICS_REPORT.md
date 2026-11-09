# Supplementary Material S4: Statistical Diagnostics and Non-Inferiority Verification

**Project:** Sentinel Plant Network (Protocol v2.0)  
**Authors:** Sentinel Plant Network Research Group  
**Scope:** Randomized Complete Block Design (RCBD) ANOVA, Shapiro-Wilk Test, Levene's Test, Yield Non-Inferiority Contrasts, and REML MixedLM  

---

## 1. Experimental Design & Units of Observation

The digital-twin agronomic simulation models a Phase 2 field trial evaluated as a Randomized Complete Block Design (RCBD):
- **Factors:** 4 Treatments $\times$ 4 Blocks = 16 Experimental Plots ($20\text{ m}^2$ each).
- **Treatments:**
  - T1: Full Irrigation (100% $\text{ET}_c$ replenishment via conventional scheduling).
  - T2: Deficit Irrigation (70% $\text{ET}_c$ fixed deficit).
  - T3: Vachaud Single-Node Baseline (irrigation triggered from spatial mean-representative location).
  - T4: Sentinel Plant Network (dual-pole extreme placement with six-state FSM arbitration).
- **Independent Experimental Unit:** Plot ($n = 16$). The 160 tagged crop plants (10 per plot) are observational subsamples and are strictly averaged to plot means prior to analysis. Residual degrees of freedom are $(k-1)(b-1) = (4-1)(4-1) = 9$.

---

## 2. Marketable Yield RCBD ANOVA & Residual Diagnostics

The additive linear model is:
$$y_{ij} = \mu + \tau_i + \beta_j + \epsilon_{ij}$$
where $\tau_i$ represents treatment effect ($df = 3$), $\beta_j$ represents block effect ($df = 3$), and $\epsilon_{ij}$ is the plot residual ($df = 9$).

### ANOVA Summary (Response: Marketable Tuber Yield, $\text{t ha}^{-1}$):
- $\text{SS}_{\text{Treatment}} = 13.3444$
- $\text{SS}_{\text{Block}} = 2.0477$
- $\text{SS}_{\text{Error}} = 0.3636$
- $\text{MSE} = 0.0404$
- $F_{\text{Treatment}} = 110.11$ ($p = 2.06 \times 10^{-7}$)
- Standard Error of Difference: $\text{SED} = \sqrt{2 \cdot \text{MSE} / b} = \sqrt{2 \times 0.0404 / 4} = 0.1421\text{ t ha}^{-1}$
- Fisher's Protected LSD ($\alpha = 0.05, df = 9$): $\text{LSD}_{0.05} = 2.262 \times 0.1421 = 0.3215\text{ t ha}^{-1}$

### Residual Assumption Diagnostics:
- **Shapiro-Wilk Test for Residual Normality:**
  - Statistic: $W = 0.9507$
  - $p$-value: $p = 0.5002$ ($p > 0.05$, no evidence of gross normality violation)
- **Median-Centered Levene's Test for Homoscedasticity:**
  - Statistic: $W_{\text{Levene}} = 1.5489$
  - $p$-value: $p = 0.2528$ ($p > 0.05$, treatment variances statistically homogeneous)
- *Interpretation Caveat:* With $n = 16$ plots, diagnostic tests have limited power. These non-significant results confirm the absence of gross distributional distortions, not definitive proof of normality.

---

## 3. Pre-Specified 5% Yield Non-Inferiority Analysis

Protocol v2.0 pre-specifies a non-inferiority margin of $M_{\text{T1}} = -5.0\%$ of the full-irrigation comparator mean:
$$M_{\text{T1}} = -0.05 \times 33.018 = -1.6509\text{ t ha}^{-1}$$
The observed treatment difference between T4 and T1 is:
$$\Delta Y = Y_{\text{T4}} - Y_{\text{T1}} = 34.401 - 33.018 = +1.3830\text{ t ha}^{-1}\ (+4.19\%)$$
The one-sided 95% lower confidence bound with $df = 9$ ($t_{0.95, 9} = 1.833$) is:
$$L_{95} = \Delta Y - t_{0.95, 9} \times \text{SED} = 1.3830 - 1.833 \times 0.1421 = +1.1225\text{ t ha}^{-1}\ (+3.40\%)$$
The non-inferiority hypothesis test statistic is:
$$t_{\text{NI}} = \frac{\Delta Y - M_{\text{T1}}}{\text{SED}} = \frac{1.3830 - (-1.6509)}{0.1421} = 21.347\quad (p = 2.55 \times 10^{-9})$$
Because $L_{95} = +1.1225 > -1.6509$, non-inferiority of T4 relative to conventional full irrigation is statistically established within the simulation model.

---

## 4. Repeated-Measures Random-Intercept Linear Mixed Model (REML)

To model foliar disease progression over time across the 16 plots, a Restricted Maximum Likelihood (REML) linear mixed-effects model was fitted:
$$\text{Severity}_{ijk} = \mu + \text{Treatment}_i + \text{Day}_j + (\text{Treatment} \times \text{Day})_{ij} + u_k + \epsilon_{ijk}$$
where $u_k \sim \mathcal{N}(0, \sigma_u^2)$ represents random between-plot intercepts across the 16 clusters ($N_{\text{obs}} = 80$, 5 epochs per plot).

### Model Convergence & Variance Components:
- **Status:** Converged successfully.
- **Between-Plot Variance ($\sigma_u^2$):** $0.3150$
- **Within-Plot Residual Variance ($\sigma_e^2$):** $0.2157$
- **Intraclass Correlation Coefficient (ICC):**
  $$\text{ICC} = \frac{\sigma_u^2}{\sigma_u^2 + \sigma_e^2} = \frac{0.3150}{0.3150 + 0.2157} = 0.5935$$
An ICC of 0.5935 confirms substantial plot-level clustering, validating the requirement for repeated-measures mixed modeling over ordinary pooled regression.
