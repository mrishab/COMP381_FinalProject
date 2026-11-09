"""Task 2C: Feature Engineering & Exhaustive Feature Analysis.

Analyzes and evaluates:
1. As-it-is baseline features
2. Interaction features (sqft x beds, sqft x baths, bed/bath ratio, luxury score, amenity density)
3. Geographic proximity features (distance to major metro hubs)
4. Polynomial features (degree-2 expansion of key continuous variables)
5. Mutual information ranking and feature selection
6. Comparative R2 analysis across all individual feature subsets vs combined optimal set
"""

from typing import Any, Dict, List, Tuple
import numpy as np
import pandas as pd
from sklearn.feature_selection import mutual_info_regression
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_squared_error, r2_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import RobustScaler


# Major Canadian metropolitan coordinates (Lat, Lon)
METRO_COORDINATES = {
    "Vancouver": (49.2827, -123.1207),
    "Toronto": (43.6532, -79.3832),
    "Montreal": (45.5017, -73.5673),
    "Calgary": (51.0447, -114.0719),
    "Ottawa": (45.4215, -75.6972),
}


def add_engineered_features(df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, List[str]]]:
    """Generates all engineered feature sets and returns enriched DataFrame and feature group catalog."""
    df_feat = df.copy()

    # 1. Map Binary columns
    binary_cols = ["Garage", "Parking", "Fireplace", "Waterfront", "Pool", "Garden", "Balcony"]
    for col in binary_cols:
        if col in df_feat.columns:
            if df_feat[col].dtype == object:
                df_feat[col] = df_feat[col].map({"Yes": 1, "No": 0, "1": 1, "0": 0}).fillna(0).astype(int)
            else:
                df_feat[col] = df_feat[col].fillna(0).astype(int)
        else:
            df_feat[col] = 0

    # 2. As-is baseline numeric features
    baseline_features = ["Bedrooms", "Bathrooms", "Square Footage", "Acreage", "Latitude", "Longitude"]
    for col in baseline_features:
        if col in df_feat.columns:
            df_feat[col] = pd.to_numeric(df_feat[col], errors="coerce").fillna(df_feat[col].median())
        else:
            df_feat[col] = 0.0

    # 3. Interactive & Ratio Features
    df_feat["sqft_per_bedroom"] = df_feat["Square Footage"] / (df_feat["Bedrooms"] + 1)
    df_feat["sqft_per_room"] = df_feat["Square Footage"] / (df_feat["Bedrooms"] + df_feat["Bathrooms"] + 1)
    df_feat["bath_bed_ratio"] = df_feat["Bathrooms"] / (df_feat["Bedrooms"] + 1)
    df_feat["sqft_x_bedrooms"] = df_feat["Square Footage"] * df_feat["Bedrooms"]
    df_feat["sqft_x_bathrooms"] = df_feat["Square Footage"] * df_feat["Bathrooms"]
    df_feat["bed_bath_product"] = df_feat["Bedrooms"] * df_feat["Bathrooms"]
    df_feat["luxury_score"] = (
        df_feat["Fireplace"] + df_feat["Waterfront"] + df_feat["Pool"] + df_feat["Garden"] + df_feat["Balcony"]
    )
    df_feat["amenity_density"] = df_feat["luxury_score"] / ((df_feat["Square Footage"] / 1000.0) + 1.0)

    interaction_features = [
        "sqft_per_bedroom",
        "sqft_per_room",
        "bath_bed_ratio",
        "sqft_x_bedrooms",
        "sqft_x_bathrooms",
        "bed_bath_product",
        "luxury_score",
        "amenity_density",
    ]

    # 4. Geographic Hub Distance Features
    for city, (c_lat, c_lon) in METRO_COORDINATES.items():
        dist_col = f"dist_to_{city.lower()}"
        df_feat[dist_col] = np.sqrt(
            (df_feat["Latitude"] - c_lat) ** 2 + (df_feat["Longitude"] - c_lon) ** 2
        )

    metro_dist_cols = [f"dist_to_{city.lower()}" for city in METRO_COORDINATES]
    df_feat["min_dist_to_metro"] = df_feat[metro_dist_cols].min(axis=1)

    location_features = ["Latitude", "Longitude", "min_dist_to_metro"] + metro_dist_cols

    # 5. Polynomial Features
    df_feat["sqft_squared"] = df_feat["Square Footage"] ** 2
    df_feat["bedrooms_squared"] = df_feat["Bedrooms"] ** 2
    df_feat["bathrooms_squared"] = df_feat["Bathrooms"] ** 2

    polynomial_features = ["sqft_squared", "bedrooms_squared", "bathrooms_squared"]

    # 6. One-hot encode key categoricals
    cat_cols_to_encode = ["Property Type", "Province"]
    present_cats = [c for c in cat_cols_to_encode if c in df_feat.columns]
    df_feat = pd.get_dummies(df_feat, columns=present_cats, drop_first=True, dtype=int)
    categorical_features = [
        col for col in df_feat.columns
        if any(col.startswith(f"{c}_") for c in present_cats)
    ]

    feature_groups = {
        "baseline": baseline_features,
        "amenities": binary_cols,
        "interactions": interaction_features,
        "location": location_features,
        "polynomial": polynomial_features,
        "categorical": categorical_features,
    }

    # Combined full feature set
    full_set = list(dict.fromkeys(
        baseline_features
        + binary_cols
        + interaction_features
        + location_features
        + polynomial_features
        + categorical_features
    ))
    feature_groups["full_model"] = full_set

    return df_feat, feature_groups


def analyze_feature_importance(
    df: pd.DataFrame,
    feature_cols: List[str],
    target_col: str = "Price",
    sample_size: int = 5000,
    random_state: int = 42,
) -> pd.DataFrame:
    """Computes Mutual Information Regression and Pearson Correlation scores for each feature."""
    df_sub = df.dropna(subset=[target_col] + feature_cols)
    if len(df_sub) > sample_size:
        df_sub = df_sub.sample(n=sample_size, random_state=random_state)

    X = df_sub[feature_cols]
    y = df_sub[target_col]

    mi_scores = mutual_info_regression(X, y, random_state=random_state)
    correlations = [df_sub[col].corr(y) for col in feature_cols]

    report_df = pd.DataFrame({
        "Feature": feature_cols,
        "Mutual_Information": mi_scores,
        "Pearson_Correlation": correlations,
    }).sort_values(by="Mutual_Information", ascending=False).reset_index(drop=True)

    return report_df


def compare_feature_subsets(
    df: pd.DataFrame,
    feature_groups: Dict[str, List[str]],
    target_col: str = "Price",
) -> pd.DataFrame:
    """Evaluates Ridge regression R2, MAE, and RMSE across each individual and combined feature set."""
    y = df[target_col]
    X_train_full, X_test_full, y_train, y_test = train_test_split(
        df, y, test_size=0.2, random_state=42
    )

    results = []
    for group_name, features in feature_groups.items():
        if not features:
            continue
        valid_features = [f for f in features if f in df.columns]
        if not valid_features:
            continue

        scaler = RobustScaler()
        X_train_scaled = scaler.fit_transform(X_train_full[valid_features])
        X_test_scaled = scaler.transform(X_test_full[valid_features])

        model = Ridge(alpha=1.0)
        model.fit(X_train_scaled, y_train)
        preds = model.predict(X_test_scaled)

        r2 = float(r2_score(y_test, preds))
        rmse = float(np.sqrt(mean_squared_error(y_test, preds)))

        results.append({
            "Feature_Set": group_name,
            "Num_Features": len(valid_features),
            "R2_Score": r2,
            "RMSE": rmse,
        })

    return pd.DataFrame(results).sort_values(by="R2_Score", ascending=False).reset_index(drop=True)
