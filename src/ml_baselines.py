"""Leakage-aware chronological time-series baselines for Sentinel Plant Network.

The functions expect a regularised time series. The forecast origin is time t;
features may contain observations available at or before t only, while targets
are shifted into the future. No random row-level split is used.
"""
from __future__ import annotations

from typing import Iterable, Optional, Sequence
import numpy as np
import pandas as pd
from sklearn.ensemble import (
    RandomForestRegressor, GradientBoostingRegressor,
    RandomForestClassifier, GradientBoostingClassifier,
)
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge, LogisticRegression
from sklearn.metrics import (
    mean_absolute_error, mean_squared_error, r2_score,
    precision_score, recall_score, f1_score, roc_auc_score,
)
from sklearn.pipeline import Pipeline


def _prepare_time_series(
    frame: pd.DataFrame,
    timestamp_col: str,
    target_col: str,
    horizon_steps: int,
    feature_cols: Optional[Sequence[str]] = None,
    expected_step_minutes: Optional[float] = None,
):
    if horizon_steps < 1:
        raise ValueError("horizon_steps must be >= 1")
    if timestamp_col not in frame or target_col not in frame:
        raise KeyError(f"Required columns missing: {timestamp_col!r}, {target_col!r}")
    df = frame.copy()
    df[timestamp_col] = pd.to_datetime(df[timestamp_col], errors="coerce", utc=True)
    df[target_col] = pd.to_numeric(df[target_col], errors="coerce")
    df = df.dropna(subset=[timestamp_col, target_col]).sort_values(timestamp_col)
    df = df.drop_duplicates(timestamp_col, keep="last").reset_index(drop=True)
    if len(df) < max(100, horizon_steps + 30):
        raise ValueError("Not enough time-ordered rows for this horizon and chronological split")

    delta_min = df[timestamp_col].diff().dt.total_seconds().div(60).dropna()
    if expected_step_minutes is None:
        step = float(delta_min.median())
    else:
        step = float(expected_step_minutes)
    if not np.isfinite(step) or step <= 0:
        raise ValueError("Could not infer a valid sampling interval")
    future_target = df[target_col].shift(-horizon_steps)
    # Validate every adjacent interval, rather than only comparing net elapsed
    # time. A short interval following a long gap must not cancel that gap.
    tolerance = max(0.01, step * 0.02)
    deltas_all = df[timestamp_col].diff().dt.total_seconds().div(60)
    bad_transition = deltas_all.sub(step).abs().gt(tolerance)
    bad_transition.iloc[0] = True
    bad_prefix = bad_transition.astype("int64").cumsum()
    future_bad_count = bad_prefix.shift(-horizon_steps) - bad_prefix
    exact_horizon = future_bad_count.eq(0) & future_target.notna()
    contiguous_lags = bad_transition.rolling(24, min_periods=24).sum().eq(0)

    if feature_cols is None:
        excluded = {timestamp_col, target_col}
        numeric = df.select_dtypes(include=[np.number]).columns.tolist()
        feature_cols = [c for c in numeric if c not in excluded and not any(
            token in c.lower() for token in ("future", "target_24h", "ahead", "label")
        )]
    missing = [c for c in feature_cols if c not in df.columns]
    if missing:
        raise KeyError(f"Unknown feature columns: {missing}")

    X = pd.DataFrame(index=df.index)
    X["vwc_now"] = df[target_col]
    for lag in (1, 2, 3, 6, 12, 24):
        X[f"{target_col}_lag_{lag}"] = df[target_col].shift(lag)
    for window in (3, 6, 12):
        X[f"{target_col}_mean_{window}"] = df[target_col].shift(1).rolling(window, min_periods=window).mean()
        X[f"{target_col}_std_{window}"] = df[target_col].shift(1).rolling(window, min_periods=window).std()
    for col in feature_cols:
        X[f"origin_{col}"] = pd.to_numeric(df[col], errors="coerce")

    y = future_target.rename("future_target")
    valid = exact_horizon & contiguous_lags & y.notna() & X.notna().any(axis=1)
    dataset = X.loc[valid].copy()
    dataset["__target"] = y.loc[valid].astype(float)
    dataset["__timestamp"] = df.loc[valid, timestamp_col].to_numpy()
    dataset = dataset.dropna(subset=[c for c in dataset.columns if c.startswith(f"{target_col}_lag_") or c.endswith("_mean_3")])
    if len(dataset) < 60:
        raise ValueError("Too few regularly spaced, complete supervised rows after lag construction")
    return dataset, step


def chronological_indices(n_rows: int, train_fraction: float = 0.70, validation_fraction: float = 0.15):
    if not 0.5 <= train_fraction < 0.9 or not 0.05 <= validation_fraction < 0.3:
        raise ValueError("Use train_fraction in [0.5, 0.9) and validation_fraction in [0.05, 0.3)")
    train_end = int(n_rows * train_fraction)
    val_end = int(n_rows * (train_fraction + validation_fraction))
    if train_end < 20 or val_end <= train_end or n_rows - val_end < 10:
        raise ValueError("Insufficient rows for chronological train/validation/test partitions")
    return slice(0, train_end), slice(train_end, val_end), slice(val_end, n_rows)


def _regression_metrics(y_true, y_pred, drought_threshold=22.0):
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    event = y_true <= drought_threshold
    predicted_event = y_pred <= drought_threshold
    return {
        "rmse": float(np.sqrt(mean_squared_error(y_true, y_pred))),
        "mae": float(mean_absolute_error(y_true, y_pred)),
        "r2": float(r2_score(y_true, y_pred)) if len(y_true) > 1 else None,
        "drought_crossing_recall": float(recall_score(event, predicted_event, zero_division=0)) if event.any() else None,
        "drought_events": int(event.sum()),
    }


def benchmark_vwc_forecasting(
    frame: pd.DataFrame,
    timestamp_col: str,
    target_col: str,
    horizon_steps: int = 144,
    feature_cols: Optional[Sequence[str]] = None,
    expected_step_minutes: Optional[float] = None,
    drought_threshold: float = 22.0,
):
    """Compare persistence, Ridge, Random Forest and Gradient Boosting for future VWC."""
    supervised, step_minutes = _prepare_time_series(
        frame, timestamp_col, target_col, horizon_steps, feature_cols, expected_step_minutes
    )
    train, validation, test = chronological_indices(len(supervised))
    feature_names = [c for c in supervised.columns if not c.startswith("__") and c != "__target"]
    X = supervised[feature_names]
    y = supervised["__target"]
    # Validation remains chronologically separate. Models use only the train
    # window for model selection/diagnostics, then are refit on train+validation.
    model_factories = {
        "ridge": lambda: Ridge(alpha=1.0),
        "random_forest": lambda: RandomForestRegressor(
            n_estimators=250, max_depth=12, min_samples_leaf=3, random_state=42, n_jobs=-1
        ),
        "gradient_boosting": lambda: GradientBoostingRegressor(
            n_estimators=150, learning_rate=0.04, max_depth=2, loss="huber", random_state=42
        ),
    }
    rows = []
    x_test = X.iloc[test]
    y_test = y.iloc[test]
    persistence = supervised.loc[supervised.index[test], "vwc_now"].to_numpy()
    rows.append({"model": "persistence", "split": "test", **_regression_metrics(y_test, persistence, drought_threshold)})
    for name, factory in model_factories.items():
        train_pipe = Pipeline([("imputer", SimpleImputer(strategy="median")), ("model", factory())])
        train_pipe.fit(X.iloc[train], y.iloc[train])
        validation_metrics = _regression_metrics(
            y.iloc[validation], train_pipe.predict(X.iloc[validation]), drought_threshold
        )
        final_pipe = Pipeline([("imputer", SimpleImputer(strategy="median")), ("model", factory())])
        fit_rows = slice(0, validation.stop)
        final_pipe.fit(X.iloc[fit_rows], y.iloc[fit_rows])
        rows.append({
            "model": name, "split": "test",
            **_regression_metrics(y_test, final_pipe.predict(x_test), drought_threshold),
            "validation_rmse": validation_metrics["rmse"],
        })
    return {
        "task": "24h_ahead_vwc_forecast" if abs(horizon_steps * step_minutes - 1440) <= step_minutes else "fixed_horizon_vwc_forecast",
        "horizon_steps": int(horizon_steps),
        "sampling_minutes_median": step_minutes,
        "horizon_minutes": float(horizon_steps * step_minutes),
        "rows_after_lags": int(len(supervised)),
        "split_rows": {"train": train.stop, "validation": validation.stop - validation.start, "test": len(supervised) - validation.stop},
        "metrics": pd.DataFrame(rows),
        "feature_columns": feature_names,
        "test_timestamps": supervised.loc[supervised.index[test], "__timestamp"].astype(str).tolist(),
    }


def benchmark_blight_classifier(
    frame: pd.DataFrame,
    timestamp_col: str,
    risk_target_col: str,
    horizon_steps: int,
    feature_cols: Sequence[str],
    expected_step_minutes: Optional[float] = None,
):
    """Predict a future binary DSV/risk state without crossing timestamp gaps."""
    if timestamp_col not in frame or risk_target_col not in frame:
        raise KeyError("timestamp_col and risk_target_col must exist")
    if horizon_steps < 1:
        raise ValueError("horizon_steps must be >= 1")
    df = frame.copy()
    df[timestamp_col] = pd.to_datetime(df[timestamp_col], errors="coerce", utc=True)
    df = df.dropna(subset=[timestamp_col]).sort_values(timestamp_col).drop_duplicates(timestamp_col).reset_index(drop=True)
    for col in feature_cols:
        if col not in df:
            raise KeyError(f"Unknown feature column: {col}")

    deltas = df[timestamp_col].diff().dt.total_seconds().div(60).dropna()
    step = float(expected_step_minutes or deltas.median())
    if not np.isfinite(step) or step <= 0:
        raise ValueError("Could not infer a valid sampling interval")
    tolerance = max(0.01, step * 0.02)
    delta_all = df[timestamp_col].diff().dt.total_seconds().div(60)
    bad_transition = delta_all.sub(step).abs().gt(tolerance)
    bad_transition.iloc[0] = True
    bad_prefix = bad_transition.astype("int64").cumsum()
    future_bad_count = bad_prefix.shift(-horizon_steps) - bad_prefix
    target = pd.to_numeric(df[risk_target_col], errors="coerce").shift(-horizon_steps)
    exact_horizon = future_bad_count.eq(0) & target.notna()

    X = df[list(feature_cols)].apply(pd.to_numeric, errors="coerce")
    for lag in (1, 2, 3, 6, 12):
        for col in feature_cols:
            X[f"{col}_lag_{lag}"] = pd.to_numeric(df[col], errors="coerce").shift(lag)

    contiguous_lags = bad_transition.rolling(12, min_periods=12).sum().eq(0)
    valid = exact_horizon & contiguous_lags & target.notna() & X.notna().any(axis=1)
    X, y = X.loc[valid], target.loc[valid].astype(int)
    if len(X) < 60:
        raise ValueError("Too few timestamp-contiguous records for a chronological risk classifier")
    if not set(y.unique()).issubset({0, 1}):
        raise ValueError("risk_target_col must be binary (0/1), e.g. DSV_LWS >= 18")
    train, validation, test = chronological_indices(len(X))
    factories = {
        "logistic_regression": lambda: LogisticRegression(max_iter=1000, class_weight="balanced"),
        "random_forest": lambda: RandomForestClassifier(
            n_estimators=250, max_depth=10, min_samples_leaf=3, class_weight="balanced", random_state=42, n_jobs=-1
        ),
        "gradient_boosting": lambda: GradientBoostingClassifier(
            n_estimators=120, learning_rate=0.04, max_depth=2, random_state=42
        ),
    }
    rows = []
    for name, factory in factories.items():
        pipe_train = Pipeline([("imputer", SimpleImputer(strategy="median")), ("model", factory())])
        pipe_train.fit(X.iloc[train], y.iloc[train])
        val_f1 = f1_score(y.iloc[validation], pipe_train.predict(X.iloc[validation]), zero_division=0)
        pipe = Pipeline([("imputer", SimpleImputer(strategy="median")), ("model", factory())])
        pipe.fit(X.iloc[:validation.stop], y.iloc[:validation.stop])
        xt, yt = X.iloc[test], y.iloc[test]
        pred = pipe.predict(xt)
        proba = pipe.predict_proba(xt)[:, 1]
        rows.append({
            "model": name,
            "precision": float(precision_score(yt, pred, zero_division=0)),
            "recall": float(recall_score(yt, pred, zero_division=0)),
            "f1": float(f1_score(yt, pred, zero_division=0)),
            "roc_auc": float(roc_auc_score(yt, proba)) if yt.nunique() == 2 else None,
            "validation_f1": float(val_f1),
            "test_positive_count": int(yt.sum()),
        })
    return {
        "metrics": pd.DataFrame(rows),
        "rows": int(len(X)),
        "horizon_steps": int(horizon_steps),
        "sampling_minutes_median": step,
        "horizon_minutes": float(horizon_steps * step),
    }