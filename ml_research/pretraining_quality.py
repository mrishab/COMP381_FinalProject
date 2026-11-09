"""Task 2B: Pretraining Quality & Outlier Treatment Research.

Evaluates and benchmarks multiple pretraining treatments:
1. Baseline (Unfiltered)
2. IQR Removal (multiplier=3.0 vs multiplier=1.5)
3. Capping / Winsorization (1st - 99th percentile boundaries)
4. Isolation Forest Multivariate Outlier Filtering
5. Scaler Benchmarking: StandardScaler vs RobustScaler vs MinMaxScaler
6. Target Log Transformation: log1p(Price)
"""

from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import MinMaxScaler, RobustScaler, StandardScaler


def remove_outliers_iqr(
    df: pd.DataFrame,
    columns: List[str],
    multiplier: float = 3.0,
) -> Tuple[pd.DataFrame, pd.Series]:
    """Removes rows where any specified column exceeds Q1 - m*IQR or Q3 + m*IQR."""
    mask = pd.Series(True, index=df.index)
    for col in columns:
        q1 = df[col].quantile(0.25)
        q3 = df[col].quantile(0.75)
        iqr = q3 - q1
        lower = q1 - multiplier * iqr
        upper = q3 + multiplier * iqr
        mask &= (df[col] >= lower) & (df[col] <= upper)
    return df[mask].copy(), mask


def cap_outliers_percentile(
    df: pd.DataFrame,
    columns: List[str],
    lower_pct: float = 0.01,
    upper_pct: float = 0.99,
) -> pd.DataFrame:
    """Winsorizes extreme values to lower and upper percentile cutoffs without dropping rows."""
    df_capped = df.copy()
    for col in columns:
        low_val = df_capped[col].quantile(lower_pct)
        high_val = df_capped[col].quantile(upper_pct)
        df_capped[col] = df_capped[col].clip(lower=low_val, upper=high_val)
    return df_capped


def filter_isolation_forest(
    df: pd.DataFrame,
    columns: List[str],
    contamination: float = 0.02,
    random_state: int = 42,
) -> Tuple[pd.DataFrame, pd.Series]:
    """Uses Isolation Forest to detect and filter multidimensional anomalies."""
    iso = IsolationForest(
        contamination=contamination,
        random_state=random_state,
        n_estimators=100,
    )
    preds = iso.fit_predict(df[columns])
    mask = pd.Series(preds == 1, index=df.index)
    return df[mask].copy(), mask


def evaluate_pretraining_treatments(
    df: pd.DataFrame,
    feature_cols: List[str],
    target_col: str = "Price",
    outlier_cols: Optional[List[str]] = None,
) -> Dict[str, Dict[str, Any]]:
    """Compares different pretraining outlier and scaling strategies using Ridge regression."""
    if outlier_cols is None:
        outlier_cols = ["Price", "Square Footage"]

    results = {}

    def test_treatment(df_treated: pd.DataFrame, name: str, scaler_type: str = "robust", use_log_target: bool = False):
        X = df_treated[feature_cols].copy()
        y = df_treated[target_col].copy()

        if use_log_target:
            y_train_target = np.log1p(y)
        else:
            y_train_target = y

        X_train, X_test, y_train, y_test = train_test_split(
            X, y_train_target, test_size=0.2, random_state=42
        )

        # Scale features
        if scaler_type == "standard":
            scaler = StandardScaler()
        elif scaler_type == "minmax":
            scaler = MinMaxScaler()
        else:
            scaler = RobustScaler()

        X_train_scaled = scaler.fit_transform(X_train)
        X_test_scaled = scaler.transform(X_test)

        model = Ridge(alpha=1.0)
        model.fit(X_train_scaled, y_train)
        preds = model.predict(X_test_scaled)

        if use_log_target:
            preds_orig = np.expm1(preds)
            y_test_orig = np.expm1(y_test)
        else:
            preds_orig = preds
            y_test_orig = y_test

        r2 = float(r2_score(y_test_orig, preds_orig))
        mae = float(mean_absolute_error(y_test_orig, preds_orig))
        rmse = float(np.sqrt(mean_squared_error(y_test_orig, preds_orig)))

        results[name] = {
            "samples": len(df_treated),
            "scaler": scaler_type,
            "log_target": use_log_target,
            "r2": r2,
            "mae": mae,
            "rmse": rmse,
        }

    # 1. Baseline
    test_treatment(df, "1. Baseline (Raw + StandardScale)", scaler_type="standard")

    # 2. IQR Removal (m=3.0)
    df_iqr3, _ = remove_outliers_iqr(df, outlier_cols, multiplier=3.0)
    test_treatment(df_iqr3, "2. IQR Removal (m=3.0 + StandardScale)", scaler_type="standard")

    # 3. IQR Removal (m=1.5 stricter)
    df_iqr15, _ = remove_outliers_iqr(df, outlier_cols, multiplier=1.5)
    test_treatment(df_iqr15, "3. IQR Removal (m=1.5 + StandardScale)", scaler_type="standard")

    # 4. Capping / Winsorization (1st - 99th percentile)
    df_capped = cap_outliers_percentile(df, outlier_cols, lower_pct=0.01, upper_pct=0.99)
    test_treatment(df_capped, "4. Percentile Capping (1%-99% + RobustScale)", scaler_type="robust")

    # 5. Isolation Forest Filtering
    df_iso, _ = filter_isolation_forest(df, outlier_cols, contamination=0.02)
    test_treatment(df_iso, "5. Isolation Forest (c=0.02 + RobustScale)", scaler_type="robust")

    # 6. Capped + Log Target Transformation
    test_treatment(df_capped, "6. Capped (1%-99%) + Log(Price) + RobustScale", scaler_type="robust", use_log_target=True)

    return results
