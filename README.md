# Canadian Real Estate Intelligence & Valuation Platform

Comprehensive end-to-end real estate engineering platform consisting of three interconnected projects:
1. **Daily Airflow Ingestion Pipeline**: Ingestion of MLS listings from Realtor.ca and assessment rolls from BC Assessment across Greater Vancouver and Fraser Valley.
2. **Machine Learning Model Research**: Systematic research on Canadian housing data covering missing value imputation, outlier treatment, feature engineering, and a 10-algorithm benchmark.
3. **In-Browser Valuation & Discount WebApp**: Mobile-first, responsive React web app performing 100% client-side inference to estimate fair market value and listing discounts.

---

## Repository Structure

```
.
├── airflow_pipeline/                   # Project 1: Daily Airflow Ingestion Stack
│   ├── docker-compose.yml              # Airflow 2.11.2 + FlareSolverr v3.5.2 + Postgres
│   ├── .env.example                    # Environment template
│   ├── requirements.txt                # Python dependencies
│   ├── dags/
│   │   ├── real_estate_collector_dag.py # Daily scheduled DAG
│   │   └── utils/
│   │       ├── flaresolverr_client.py  # Cloudflare turnstile solver & backoff client
│   │       ├── realtor_scraper.py      # Realtor.ca GVA & Fraser Valley search
│   │       ├── bcassessment_scraper.py # BC Assessment search & valuation parser
│   │       ├── data_transformer.py     # Schema normalizer & 3-sale denormalizer
│   │       └── db_storage.py           # SQLite upsert engine & CSV exporter
│   └── tests/
│       └── test_airflow_pipeline.py    # Unit & integration test suite
│
├── ml_research/                        # Project 2: ML Model Research (Tasks 2A - 2D)
│   ├── data_quality.py                 # Task 2A: Mode, KNN, LDA, Hot Deck, LOCF, Interpolation
│   ├── pretraining_quality.py          # Task 2B: IQR removal, 1%-99% Capping, Isolation Forest
│   ├── feature_engineering.py          # Task 2C: Domain interactions, metro proximity, polynomials
│   ├── model_training.py               # Task 2D: 10-algorithm benchmark & model export
│   ├── run_ml_experiments.py           # End-to-end execution runner
│   ├── RealEstateDeals_Enhanced.ipynb  # Interactive Jupyter notebook
│   ├── exported_models/
│   │   ├── best_model_meta.json        # Exported model weights, scaler, and metadata
│   │   └── ml_research_summary.json    # Quantitative benchmark metrics
│   └── tests/
│       └── test_ml_research.py         # Unit test suite
│
├── webapp/                             # Project 3: In-Browser ML Discount Web Application
│   ├── src/
│   │   ├── App.tsx                     # Minimalist, spacious UI canvas
│   │   ├── components/
│   │   │   ├── PropertyEvaluator.tsx   # Address input, autocomplete, live discount evaluation
│   │   │   ├── DiscountBadge.tsx       # Discount/premium visual status badge
│   │   │   └── SpecsDisplay.tsx        # Inline specs and interactive adjustment drawer
│   │   ├── ml/
│   │   │   ├── browserModel.ts         # In-browser pandas and scikit-learn inference engine
│   │   │   └── modelData.json          # Bundled model weights and RobustScaler params
│   │   └── services/
│   │       └── propertyLookup.ts       # Address resolver for GVA & Fraser Valley
│   ├── package.json
│   ├── vite.config.ts
│   └── dist/                           # Compiled production assets
│
├── RealEstateDeals.ipynb               # Base research notebook
├── RealEstateDeals_Enhanced.ipynb      # Enhanced research notebook
└── README.md                           # Master repository documentation
```

---

## Project 1: Airflow Real Estate Data Pipeline

### Coverage
- **Greater Vancouver Area**: Vancouver, Surrey, Burnaby, Richmond, Coquitlam, New Westminster, West Vancouver, North Vancouver, Delta, White Rock, Langley City, Township of Langley, Port Coquitlam, Port Moody, Maple Ridge, Pitt Meadows, Bowen Island, Lions Bay, Anmore, Belcarra.
- **Fraser Valley**: Abbotsford, Mission, Chilliwack, Aldergrove, Hope, Kent, Harrison Hot Springs.

### Core Features
- **Cloudflare Bypass**: FlareSolverr proxy resolves Cloudflare Turnstiles/WAF challenges automatically.
- **Rate Limiting & Backoff**: Configurable request delay with random jitter (2.0s ± 1.0s) and exponential backoff on HTTP 429 (`base * 2^attempt`).
- **Atomic Data Fields**: Individual columns for street number, street name, unit, postal code, bedrooms, bathrooms, sqft, heating, cooling, basement finish, property tax, and assessment roll values.
- **Denormalized Sales History**: Captures up to 3 previous transaction prices and dates (`sale_price_1`, `sale_date_1`, `sale_price_2`, `sale_date_2`, `sale_price_3`, `sale_date_3`).
- **Dual Persistence**: SQLite database (`real_estate.db`) with indexes on `mls_number`, `city`, `price`, `date_listed`, plus daily CSV exports (`real_estate_listings.csv`).

### Execution
```bash
# Start Docker stack
cd airflow_pipeline && docker-compose up -d

# Run pipeline tests
PYTHONPATH=/workspace/airflow_pipeline pytest /workspace/airflow_pipeline/tests/test_airflow_pipeline.py -v
```

---

## Project 2: Real Estate ML Model Research

Systematic empirical evaluation on 44,896 Canadian housing records:

### Task 2A: Missing Data Imputation
Evaluated 6 imputation strategies on holdout ground truth data:
- **Hot Deck Imputation** achieved the best class balance (**F1 Macro 0.592**, Accuracy 76.98%) by matching donors within the same municipality and price cohort.
- **KNN Classifier (k=5)** achieved F1 0.426.
- **Mode Baseline** achieved Accuracy 75.78% but collapsed F1 to 0.287.

### Task 2B: Pretraining Quality & Outlier Treatment
- Raw baseline linear regression achieved an $R^2$ of **0.036** due to massive price variance in raw listings.
- **Percentile Capping (1% - 99%)** with **RobustScaler** achieved an $R^2$ of **0.5903** while **preserving 100% of data rows** (44,896 records).
- IQR removal (multiplier=3.0) achieved $R^2$ 0.5968 but discarded 1,923 listings.

### Task 2C: Feature Engineering & Analysis
- **Full Engineered Model** achieved $R^2$ **0.6660**, outperforming baseline features alone ($R^2$ 0.5904) and interactions alone ($R^2$ 0.4878).
- **Top Features by Mutual Information**: Distance to Vancouver (0.415), Distance to Toronto (0.411), Longitude (0.403), Minimum Distance to Metro Hub (0.387), `sqft_x_bathrooms` (0.342), Square Footage (0.311), `sqft_x_bedrooms` (0.294).

### Task 2D: Multi-Algorithm Benchmark
Cross-evaluated 10 candidate regression algorithms:

| Model | $R^2$ Score | MAE ($) | RMSE ($) |
| :--- | :--- | :--- | :--- |
| **Random Forest Regressor (n=100, depth=16)** | **0.8790** | **$182,605** | **$372,120** |
| **XGBoost Regressor (depth=6, lr=0.08)** | **0.8783** | **$194,364** | **$373,215** |
| **KNN Regressor (k=7, distance-weighted)** | **0.7147** | $274,897 | $571,493 |
| **Deep Neural Network (MLP 128x64)** | **0.7126** | $312,377 | $573,569 |
| **LDA Price Bracket + Ridge** | **0.6794** | $345,702 | $605,822 |
| **Linear Regression (OLS)** | **0.6660** | $380,685 | $618,365 |
| **Lasso Regression (alpha=0.01)** | **0.6652** | $381,342 | $619,118 |
| **Ridge Regression (alpha=10.0)** | **0.6639** | $380,818 | $620,346 |
| **ElasticNet (alpha=0.1, l1=0.5)** | **0.6375** | $384,417 | $644,184 |
| **Isolation Forest + Ridge Pipeline** | **0.5787** | $381,848 | $694,490 |

### Execution
```bash
python3 /workspace/ml_research/run_ml_experiments.py
PYTHONPATH=/workspace/ml_research pytest /workspace/ml_research/tests/test_ml_research.py -v
```

---

## Project 3: Responsive In-Browser ML Valuation WebApp

A minimalist, mobile-first, empty-canvas web application where the machine learning model runs 100% inside the user's browser.

### Key Capabilities
- **Single-Field Address Search**: Users type or select an address across Greater Vancouver and Fraser Valley. No manual form-filling of 20 attributes required. Intelligent municipality detection maps coordinates and price thresholds automatically.
- **In-Browser ML Engines (Dual-Model Architecture)**:
  - **Random Forest Tree Ensemble**: 40 decision trees traversed directly in browser memory in < 1ms, delivering non-linear state-of-the-art accuracy (**$R^2 = 0.8616$**).
  - **Ridge Regularized Regression**: Instant linear valuation (**$R^2 = 0.6639$**) and dynamic feature impact attribution (highlighting specific value drivers like square footage, waterfront, pool, or bedrooms).
- **ShadCN UI Foundation & Minimalist Canvas**: Clean, spacious empty-canvas aesthetic built with ShadCN primitives (`Card`, `Badge`, `Button`, `Input`) and TailwindCSS.
- **Live Discount Badge**: Compares Asking Price vs ML Fair Value:
  - **Underpriced**: Emerald badge displaying discount percentage and dollar savings.
  - **Overpriced**: Rose badge displaying premium percentage and dollar excess.
  - **Fair Price**: Neutral badge when asking price is within ±4% of market value.
- **Zero Backend Latency**: 100% in-browser inference executes synchronously with no network API dependencies.

### Build & Serve
```bash
# Run unit & integration test suite (25 tests)
pytest -v

# Build webapp production assets
cd /workspace/webapp && npm run build
```
