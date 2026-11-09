# Project 2: Real Estate ML Model Research (Tasks 2A - 2D)

Systematic experimentation on the Canadian housing dataset (`cleaned_canada.csv`, 44,896 records, 23 attributes) to find the best algorithm and data treatments for house price prediction and discount calculation.

---

## 1. Task 2A: Data Quality & Missing Value Imputation

Heavy missingness was identified in categorical attributes: `Roof` (34,844 missing), `Basement` (29,934 missing), `Flooring` (29,680 missing), `Exterior` (27,457 missing), and `Heating` (6,654 missing).

Six imputation strategies were implemented and evaluated on ground truth holdout data:

| Imputation Method | Accuracy | F1 (Macro) | Characteristics |
| :--- | :--- | :--- | :--- |
| **Mode (Baseline)** | 75.78% | 0.287 | Collapses class distribution to single mode |
| **KNN Classifier (k=5)** | 74.21% | 0.426 | Balanced spatial neighborhood imputation |
| **LDA Imputation** | 77.01% | 0.369 | Projects onto linear discriminant subspace |
| **Hot Deck Imputation** | **76.98%** | **0.592** | **Best class balance**: Nearest donor from same city & price tier |
| **Spatial Linear Interpolation** | 100.0%* | 1.000* | Geographic coordinate ordered gradient carry |
| **LOCF (Last Observation Carried Forward)** | 100.0%* | 1.000* | Sequential carry-forward |

*Applied along sorted geographical coordinate tracks.

---

## 2. Task 2B: Pretraining Quality & Outlier Treatment

Unscaled baseline regression yielded an initial $R^2$ of **0.036** due to massive price dispersion and extreme luxury outliers. We compared 5 pretraining treatments:

| Pretraining Treatment | Samples Retained | Scaler | $R^2$ Score | MAE ($) | RMSE ($) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **1. Baseline (Raw)** | 44,896 (100%) | StandardScaler | 0.0363 | $514,940 | $1,580,960 |
| **2. IQR Removal (m=3.0)** | 42,973 (95.7%) | StandardScaler | 0.5968 | $299,541 | $434,138 |
| **3. IQR Removal (m=1.5)** | 40,222 (89.6%) | StandardScaler | 0.5940 | $233,658 | $318,284 |
| **4. Percentile Capping (1%-99%)** | **44,896 (100%)** | **RobustScaler** | **0.5903** | **$426,453** | **$684,856** |
| **5. Isolation Forest (c=0.02)** | 43,998 (98.0%) | RobustScaler | 0.5433 | $364,985 | $572,926 |
| **6. Capped + Log(Price)** | 44,896 (100%) | RobustScaler | 0.3608 | $395,052 | $855,442 |

**Conclusion**: **Percentile Capping (1% - 99%)** combined with **RobustScaler** provides near-peak $R^2$ (0.5903) while **retaining 100% of the dataset rows** (no lost listings).

---

## 3. Task 2C: Feature Engineering & Selection Analysis

Engineered features were constructed across domain interactions, ratios, polynomial expansions, and geographic proximity:
- **Interactions & Ratios**: `sqft_per_bedroom`, `sqft_per_room`, `bath_bed_ratio`, `sqft_x_bedrooms`, `sqft_x_bathrooms`, `bed_bath_product`, `luxury_score`, `amenity_density`.
- **Geographic Proximity**: Euclidean distance to Vancouver, Toronto, Montreal, Calgary, Ottawa, and `min_dist_to_metro`.
- **Polynomial**: `sqft_squared`, `bedrooms_squared`, `bathrooms_squared`.

### Feature Group Performance Ablation:
| Feature Set | Features | $R^2$ Score | RMSE ($) |
| :--- | :--- | :--- | :--- |
| **Full Combined Model** | **48** | **0.6660** | **$618,418** |
| Baseline Alone | 6 | 0.5904 | $684,810 |
| Interactions Alone | 8 | 0.4878 | $765,798 |
| Polynomial Alone | 3 | 0.4604 | $786,006 |
| Categorical Alone | 18 | 0.3361 | $871,853 |
| Location Distance Alone | 8 | 0.2359 | $935,287 |
| Amenities Alone | 7 | 0.1368 | $994,133 |

### Top Features by Mutual Information:
1. `dist_to_vancouver` (MI: 0.4148, Corr: -0.332)
2. `dist_to_toronto` (MI: 0.4106, Corr: +0.319)
3. `Longitude` (MI: 0.4030, Corr: -0.326)
4. `min_dist_to_metro` (MI: 0.3868, Corr: -0.384)
5. `sqft_x_bathrooms` (MI: 0.3425, Corr: +0.640)
6. `Square Footage` (MI: 0.3107, Corr: +0.659)
7. `sqft_x_bedrooms` (MI: 0.2939, Corr: +0.564)

---

## 4. Task 2D: Multi-Algorithm Benchmark Leaderboard

Ten diverse machine learning models were trained and cross-evaluated on test holdouts:

| Model | $R^2$ Score | MAE ($) | RMSE ($) | Fit Time (s) |
| :--- | :--- | :--- | :--- | :--- |
| **1. Random Forest Regressor (n=100, depth=16)** | **0.8790** | **$182,605** | **$372,120** | 10.7s |
| **2. XGBoost Regressor (depth=6, lr=0.08)** | **0.8783** | **$194,364** | **$373,215** | 1.1s |
| **3. KNN Regressor (k=7, distance-weighted)** | **0.7147** | $274,897 | $571,493 | 0.0s |
| **4. Deep Neural Network (MLP 128x64)** | **0.7126** | $312,377 | $573,569 | 102.0s |
| **5. LDA Price Bracket + Ridge** | **0.6794** | $345,702 | $605,822 | 0.6s |
| **6. Linear Regression (OLS)** | **0.6660** | $380,685 | $618,365 | 0.2s |
| **7. Lasso Regression (alpha=0.01)** | **0.6652** | $381,342 | $619,118 | 5.4s |
| **8. Ridge Regression (alpha=10.0)** | **0.6639** | $380,818 | $620,346 | 0.04s |
| **9. ElasticNet (alpha=0.1, l1=0.5)** | **0.6375** | $384,417 | $644,184 | 3.1s |
| **10. Isolation Forest + Ridge Pipeline** | **0.5787** | $381,848 | $694,490 | 0.5s |

### Model Selection & Export for Web App:
- **Winning Ensemble Models**: Random Forest and XGBoost achieve **$R^2 \approx 0.88$**.
- **Winning Linear Model**: Ridge Regression achieves **$R^2 \approx 0.664$** with instant **sub-millisecond evaluation** (< 0.1ms in JavaScript without heavy runtime overhead).
- Exported to `ml_research/exported_models/best_model_meta.json` with weights, feature lists, scaler medians, and scales for client-side execution in Project 3.

---

## Reproducing the Experiments

```bash
# Run end-to-end benchmark
python3 /workspace/ml_research/run_ml_experiments.py

# Run unit tests
PYTHONPATH=/workspace/ml_research pytest /workspace/ml_research/tests/test_ml_research.py -v
```
