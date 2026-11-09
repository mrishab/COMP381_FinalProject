"""End-to-End Orchestrator for Real Estate ML Model Research (Tasks 2A - 2D).

Loads Canadian housing dataset, performs systematic data quality comparisons,
pretraining treatments, feature engineering, multi-algorithm training, and exports
the winning model for browser-side inference.
"""

import json
import logging
import os
import sys
import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import RobustScaler

# Add parent to path
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

from data_quality import evaluate_imputation_techniques, impute_dataset
from pretraining_quality import cap_outliers_percentile, evaluate_pretraining_treatments, remove_outliers_iqr
from feature_engineering import add_engineered_features, analyze_feature_importance, compare_feature_subsets
from model_training import export_model_for_browser, train_and_evaluate_models, tune_winning_models

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ml_experiments")

DATA_PATH = "/workspace/cleaned_canada.csv"
EXPORT_DIR = os.path.join(CURRENT_DIR, "exported_models")
os.makedirs(EXPORT_DIR, exist_ok=True)


def main():
    logger.info("=== STEP 1: LOADING DATASET ===")
    if not os.path.exists(DATA_PATH):
        raise FileNotFoundError(f"Dataset not found at {DATA_PATH}")

    df_raw = pd.read_csv(DATA_PATH)
    logger.info(f"Loaded raw dataset with {df_raw.shape[0]} rows and {df_raw.shape[1]} columns.")

    # -------------------------------------------------------------
    # Task 2A: Data Quality & Missing Value Imputation
    # -------------------------------------------------------------
    logger.info("\n=== TASK 2A: DATA QUALITY & MISSING DATA IMPUTATION ===")
    missing_summary = df_raw.isna().sum()
    logger.info("Missing column statistics:\n" + str(missing_summary[missing_summary > 0]))

    imputation_bench = evaluate_imputation_techniques(df_raw, target_col="Basement")
    df_imputation_report = pd.DataFrame.from_dict(imputation_bench, orient="index")
    logger.info("\nImputation Benchmark Results (Target: Basement):\n" + df_imputation_report.to_string())

    logger.info("Imputing full dataset using KNN classification...")
    df_imputed = impute_dataset(df_raw, strategy="knn")
    logger.info(f"Imputation complete. Remaining NaNs: {df_imputed.isna().sum().sum()}")

    # -------------------------------------------------------------
    # Task 2B: Pretraining Quality & Outlier Treatment
    # -------------------------------------------------------------
    logger.info("\n=== TASK 2B: PRETRAINING QUALITY & OUTLIER TREATMENT ===")
    pretrain_features = ["Bedrooms", "Bathrooms", "Square Footage", "Latitude", "Longitude"]
    pretrain_bench = evaluate_pretraining_treatments(
        df_imputed, feature_cols=pretrain_features, target_col="Price", outlier_cols=["Price", "Square Footage"]
    )
    df_pretrain_report = pd.DataFrame.from_dict(pretrain_bench, orient="index")
    logger.info("\nPretraining Treatment Benchmark:\n" + df_pretrain_report.to_string())

    # Apply optimal pretraining treatment: Capping at 1%-99% to retain full data integrity
    df_pretreated = cap_outliers_percentile(df_imputed, ["Price", "Square Footage"], lower_pct=0.01, upper_pct=0.99)
    logger.info(f"Capping applied. Total records preserved: {len(df_pretreated)}")

    # -------------------------------------------------------------
    # Task 2C: Feature Engineering & Selection Analysis
    # -------------------------------------------------------------
    logger.info("\n=== TASK 2C: FEATURE ENGINEERING & SELECTION ===")
    df_engineered, feature_groups = add_engineered_features(df_pretreated)
    logger.info(f"Generated {len(feature_groups['full_model'])} total candidate features.")

    subset_comparison = compare_feature_subsets(df_engineered, feature_groups, target_col="Price")
    logger.info("\nFeature Subset Performance Comparison:\n" + subset_comparison.to_string())

    top_features = analyze_feature_importance(df_engineered, feature_groups["full_model"][:25], target_col="Price")
    logger.info("\nTop 15 Features by Mutual Information:\n" + top_features.head(15).to_string())

    # -------------------------------------------------------------
    # Task 2D: Multi-Model Training & Benchmark
    # -------------------------------------------------------------
    logger.info("\n=== TASK 2D: TRAINING MULTIPLE ML MODELS ===")
    # Select best performing feature set
    selected_features = feature_groups["full_model"]
    X = df_engineered[selected_features].values
    y = df_engineered["Price"].values

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42
    )

    scaler = RobustScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    leaderboard, fitted_models = train_and_evaluate_models(
        X_train_scaled, X_test_scaled, y_train, y_test, selected_features
    )
    logger.info("\nAlgorithm Leaderboard:\n" + leaderboard.to_string())

    logger.info("\n=== HYPERPARAMETER TUNING FOR WINNING MODELS ===")
    tuning_results = tune_winning_models(X_train_scaled, X_test_scaled, y_train, y_test)
    for model_name, configs in tuning_results.items():
        logger.info(f"Tuning {model_name}: {configs}")

    # Train compact browser-optimized Random Forest (40 trees, depth 10) for instant client inference
    from sklearn.ensemble import RandomForestRegressor
    rf_browser = RandomForestRegressor(n_estimators=40, max_depth=10, random_state=42, n_jobs=-1)
    rf_browser.fit(X_train_scaled, y_train)
    rf_preds = rf_browser.predict(X_test_scaled)
    from sklearn.metrics import r2_score, mean_absolute_error, mean_squared_error
    rf_browser_r2 = float(r2_score(y_test, rf_preds))
    logger.info(f"Compact Browser-Optimized Random Forest R2: {rf_browser_r2:.4f}")

    ridge_model = fitted_models["2. Ridge Regression (alpha=10.0)"]
    best_metrics = {
        "random_forest_r2": round(rf_browser_r2, 4),
        "random_forest_mae": round(float(mean_absolute_error(y_test, rf_preds)), 2),
        "ridge_r2": leaderboard[leaderboard["Model"] == "2. Ridge Regression (alpha=10.0)"]["R2_Score"].iloc[0],
    }

    export_json_path = os.path.join(EXPORT_DIR, "best_model_meta.json")
    export_data = export_model_for_browser(
        model=rf_browser,
        scaler=scaler,
        feature_names=selected_features,
        metrics=best_metrics,
        export_path=export_json_path,
        ridge_model=ridge_model,
    )
    logger.info(f"Exported browser inference model artifact to {export_json_path}")

    # Sync to webapp ml directory
    webapp_model_path = "/workspace/webapp/src/ml/modelData.json"
    if os.path.exists(os.path.dirname(webapp_model_path)):
        with open(webapp_model_path, "w", encoding="utf-8") as f:
            json.dump(export_data, f, indent=2)
        logger.info(f"Synced model weights to {webapp_model_path}")

    # Also save benchmark summary for reports
    results_summary = {
        "imputation_benchmark": imputation_bench,
        "pretraining_benchmark": pretrain_bench,
        "feature_subsets": subset_comparison.to_dict(orient="records"),
        "model_leaderboard": leaderboard.to_dict(orient="records"),
        "hyperparameter_tuning": tuning_results,
        "browser_model_metrics": best_metrics,
    }
    with open(os.path.join(EXPORT_DIR, "ml_research_summary.json"), "w") as f:
        json.dump(results_summary, f, indent=2)

    logger.info("ML Research experiments completed successfully!")


if __name__ == "__main__":
    main()
