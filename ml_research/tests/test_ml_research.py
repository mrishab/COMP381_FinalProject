"""Unit Tests for Project 2: Real Estate ML Model Research."""

import json
import os
import tempfile
import numpy as np
import pandas as pd
import pytest
from sklearn.linear_model import Ridge
from sklearn.preprocessing import RobustScaler

from data_quality import evaluate_imputation_techniques, impute_dataset
from pretraining_quality import cap_outliers_percentile, filter_isolation_forest, remove_outliers_iqr
from feature_engineering import add_engineered_features, compare_feature_subsets
from model_training import export_model_for_browser, train_and_evaluate_models, tune_winning_models


@pytest.fixture
def synthetic_housing_data():
    """Generates synthetic housing data mimicking cleaned_canada.csv structure."""
    np.random.seed(42)
    n = 200
    sqft = np.random.uniform(500, 3500, size=n)
    beds = np.random.randint(1, 6, size=n)
    baths = np.random.randint(1, 4, size=n)
    lat = np.random.uniform(49.0, 49.3, size=n)
    lon = np.random.uniform(-123.3, -122.5, size=n)
    price = 200000 + 400 * sqft + 50000 * beds + np.random.normal(0, 20000, size=n)

    # Some missing categories
    basements = np.random.choice(["Finished", "Unfinished", "None", np.nan], size=n, p=[0.4, 0.2, 0.2, 0.2])
    exteriors = np.random.choice(["Brick", "Wood", "Vinyl", np.nan], size=n, p=[0.3, 0.3, 0.2, 0.2])

    df = pd.DataFrame({
        "City": np.random.choice(["Vancouver", "Surrey", "Burnaby", "Richmond"], size=n),
        "Province": ["BC"] * n,
        "Latitude": lat,
        "Longitude": lon,
        "Price": price,
        "Bedrooms": beds,
        "Bathrooms": baths,
        "Acreage": np.random.uniform(0.05, 1.0, size=n),
        "Property Type": np.random.choice(["Single Family", "Condo", "Townhouse"], size=n),
        "Square Footage": sqft,
        "Garage": np.random.choice(["Yes", "No"], size=n),
        "Parking": np.random.choice(["Yes", "No"], size=n),
        "Fireplace": np.random.choice(["Yes", "No"], size=n),
        "Basement": basements,
        "Exterior": exteriors,
        "Heating": ["Forced Air"] * n,
        "Flooring": ["Hardwood"] * n,
        "Roof": ["Asphalt"] * n,
        "Waterfront": np.random.choice(["Yes", "No"], size=n),
        "Sewer": ["Municipal"] * n,
        "Pool": np.random.choice(["Yes", "No"], size=n),
        "Garden": np.random.choice(["Yes", "No"], size=n),
        "Balcony": np.random.choice(["Yes", "No"], size=n),
    })
    return df


class TestDataQuality:
    def test_imputation_evaluation(self, synthetic_housing_data):
        results = evaluate_imputation_techniques(synthetic_housing_data, target_col="Basement")
        assert "Mode (Baseline)" in results
        assert "KNN (k=5)" in results
        assert "Hot Deck" in results
        assert "Linear/Spatial Interpolation" in results
        assert "LOCF (Last Observation Carried Forward)" in results
        for k, v in results.items():
            assert "accuracy" in v
            assert 0.0 <= v["accuracy"] <= 1.0

    def test_impute_dataset_knn(self, synthetic_housing_data):
        df_imputed = impute_dataset(synthetic_housing_data, strategy="knn", target_cols=["Basement", "Exterior"])
        assert df_imputed["Basement"].isna().sum() == 0
        assert df_imputed["Exterior"].isna().sum() == 0


class TestPretrainingQuality:
    def test_remove_outliers_iqr(self, synthetic_housing_data):
        # Insert an extreme outlier
        df = synthetic_housing_data.copy()
        df.loc[0, "Price"] = 100000000.0  # $100M
        clean_df, mask = remove_outliers_iqr(df, ["Price"], multiplier=3.0)
        assert len(clean_df) < len(df)
        assert 0 not in clean_df.index

    def test_cap_outliers_percentile(self, synthetic_housing_data):
        df = synthetic_housing_data.copy()
        df.loc[0, "Price"] = 999999999.0
        capped_df = cap_outliers_percentile(df, ["Price"], lower_pct=0.01, upper_pct=0.95)
        assert len(capped_df) == len(df)
        assert capped_df.loc[0, "Price"] < 999999999.0

    def test_filter_isolation_forest(self, synthetic_housing_data):
        clean_df, mask = filter_isolation_forest(synthetic_housing_data, ["Price", "Square Footage"], contamination=0.05)
        assert len(clean_df) < len(synthetic_housing_data)
        assert len(clean_df) == mask.sum()


class TestFeatureEngineering:
    def test_add_engineered_features(self, synthetic_housing_data):
        df_feat, groups = add_engineered_features(synthetic_housing_data)
        assert "sqft_per_bedroom" in df_feat.columns
        assert "sqft_x_bedrooms" in df_feat.columns
        assert "luxury_score" in df_feat.columns
        assert "min_dist_to_metro" in df_feat.columns
        assert "sqft_squared" in df_feat.columns
        assert len(groups["full_model"]) > 15

    def test_compare_feature_subsets(self, synthetic_housing_data):
        df_feat, groups = add_engineered_features(synthetic_housing_data)
        subset_df = compare_feature_subsets(df_feat, groups, target_col="Price")
        assert len(subset_df) > 0
        assert "R2_Score" in subset_df.columns


class TestModelTrainingAndExport:
    def test_train_and_evaluate_models(self, synthetic_housing_data):
        df_feat, groups = add_engineered_features(synthetic_housing_data)
        features = groups["baseline"] + groups["interactions"][:3]
        X = df_feat[features].values
        y = df_feat["Price"].values
        scaler = RobustScaler()
        X_scaled = scaler.fit_transform(X)

        leaderboard, fitted_models = train_and_evaluate_models(
            X_scaled[:150], X_scaled[150:], y[:150], y[150:], features
        )
        assert len(leaderboard) >= 8
        assert "2. Ridge Regression (alpha=10.0)" in fitted_models

    def test_export_model_for_browser(self):
        model = Ridge(alpha=1.0)
        X = np.array([[1.0, 2.0], [3.0, 4.0], [5.0, 6.0]])
        y = np.array([10.0, 20.0, 30.0])
        scaler = RobustScaler()
        X_scaled = scaler.fit_transform(X)
        model.fit(X_scaled, y)

        with tempfile.NamedTemporaryFile(suffix=".json") as tmp_file:
            export_data = export_model_for_browser(
                model, scaler, ["feat_a", "feat_b"], {"r2": 0.99}, tmp_file.name
            )
            assert export_data["model_type"] == "linear_ridge"
            assert "coefficients" in export_data
            assert "intercept" in export_data

            with open(tmp_file.name) as f:
                loaded = json.load(f)
                assert loaded["features"] == ["feat_a", "feat_b"]

    def test_tune_winning_models(self, synthetic_housing_data):
        df_feat, groups = add_engineered_features(synthetic_housing_data)
        features = groups["baseline"]
        X = df_feat[features].values
        y = df_feat["Price"].values
        scaler = RobustScaler()
        X_scaled = scaler.fit_transform(X)

        tuning_results = tune_winning_models(
            X_scaled[:150], X_scaled[150:], y[:150], y[150:]
        )
        assert "Random Forest" in tuning_results
        assert "Ridge Regression" in tuning_results
        assert len(tuning_results["Random Forest"]) > 0

    def test_export_random_forest_ensemble(self):
        from sklearn.ensemble import RandomForestRegressor
        model = RandomForestRegressor(n_estimators=5, max_depth=4, random_state=42)
        X = np.random.randn(50, 4)
        y = np.random.randn(50) * 1000
        scaler = RobustScaler()
        X_scaled = scaler.fit_transform(X)
        model.fit(X_scaled, y)

        with tempfile.NamedTemporaryFile(suffix=".json") as tmp_file:
            export_data = export_model_for_browser(
                model, scaler, ["f1", "f2", "f3", "f4"], {"r2": 0.85}, tmp_file.name
            )
            assert export_data["model_type"] == "random_forest"
            assert "forest" in export_data
            assert len(export_data["forest"]["trees"]) == 5
