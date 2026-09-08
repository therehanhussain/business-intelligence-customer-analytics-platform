# Business Intelligence & Customer Analytics Platform

This project is an end-to-end data pipeline and analytics platform for a multi-channel retail business. I built it to take raw customer demographics, product catalog records, and e-commerce order transactions and turn them into validated business insights. The platform covers data cleaning and validation with a Dead-Letter Queue, relational modeling, SQL business analytics, customer RFM segmentation, a churn risk model built with anti-leakage controls, and a Power BI-ready star schema. It answers practical commercial questions around customer concentration, product category margins, fulfillment friction, and retention prioritization.

---

## What I Built

I built a complete analytical workflow in Python and SQL that moves data from raw CSV files to decision-ready dashboards:

1. **Python ETL & Validation**: An automated ingestion pipeline that cleans raw text, normalizes payment methods and statuses, imputes missing values, checks foreign-key integrity, and isolates bad records into a Dead-Letter Queue (DLQ).
2. **Relational Data Warehouse**: A star-schema database in SQLite (with PostgreSQL DDL and loader ready) that organizes customers, products, and orders into queryable tables and dimensional views.
3. **SQL Analytics Engine**: A set of SQL queries and views that aggregate revenue, profit, refund rates, customer order frequency, and category margins.
4. **Customer Segmentation (RFM)**: A scoring script that groups customers into 9 behavioral segments based on recency, frequency, and monetary value.
5. **Churn & Risk Modeling**: A rule-based risk score (0–100) and two machine learning models (Logistic Regression and Random Forest) trained on historical features to predict churn risk without temporal data leakage.
6. **Power BI Data Layer & Prototype**: Clean star-schema CSV exports, 24 DAX measures, Power Query M transformation scripts, and an interactive HTML prototype showing executive, customer, product, and retention views.

---

## Why I Built It

Retail teams often sit on lots of transactional data but struggle to answer basic business questions consistently:

* **Which customers drive the business?** How concentrated is revenue across our customer base, and what happens if top accounts stop buying?
* **Which accounts need attention right now?** Can we identify customers who used to buy regularly but are drifting toward inactivity before they leave entirely?
* **Which products actually make money?** High sales volume does not always mean high profit. Are popular categories carrying low margins or high return rates?
* **Where are returns and cancellations hurting performance?** How much money is lost between gross order placement and net fulfilled revenue?
* **How do we prioritize retention budgets?** Instead of giving discounts to everyone, how can marketing and account teams target customers by value and churn probability?

---

## Tech Stack

* **Python 3.10+**: Core pipeline, feature engineering, and modeling
* **Pandas / NumPy**: Data transformation, cleaning, and array math
* **SQL**: Analytical aggregations, window functions, and views
* **PostgreSQL**: Target database schema and DDL
* **SQLite fallback**: Local staging data warehouse used for testing and validation
* **SQLAlchemy**: Database connection and loading abstraction
* **Scikit-learn**: StandardScaler, Logistic Regression, Random Forest, and model evaluation metrics
* **Power BI**: Star schema design, DAX measures catalog, and Power Query M scripts
* **unittest**: 71 automated regression and data quality tests
* **Git**: Version control

---

## Project Flow

```
Raw CSV Data (Customers, Products, Orders)
                  ↓
          Python ETL Pipeline
                  ↓
      Validation Rules + Dead-Letter Queue (DLQ)
                  ↓
       Relational Database (Staging / PostgreSQL)
                  ↓
         SQL Analytics & Business Views
                  ↓
       RFM Segmentation + Churn / Risk Modeling
                  ↓
           Power BI-Ready Data Layer
                  ↓
       Executive Dashboard & Business Insights
```

The data flows forward without manual steps. Raw files are cleaned, checked against validation rules, written to clean tables or the DLQ, analyzed with SQL, enriched with customer scores and churn probabilities, and exported for reporting.

---

## Data & ETL

The raw dataset contains 117,499 records across three tables. The ETL pipeline validates each table against business rules and referential integrity before loading.

* **117,499 total raw records ingested**:
  * 10,080 customer records
  * 500 product records
  * 106,919 order transactions
* **114,187 valid clean records loaded**:
  * 10,000 clean customers
  * 492 clean products
  * 103,695 clean orders
* **3,312 rejected records quarantined into the Dead-Letter Queue**:
  * 80 customer records with duplicate IDs (`DUPLICATE_CUSTOMER_ID`)
  * 8 product records rejected for missing categories (5) or missing costs (3)
  * 3,224 order records rejected:
    * 2,729 orders referencing product IDs not present in the clean catalog (`ORPHAN_PRODUCT_FOREIGN_KEY`)
    * 330 negative return quantity orders (`INVALID_QUANTITY_NEGATIVE_RETURN`)
    * 165 zero-quantity orders (`INVALID_QUANTITY_ZERO`)

Every rejected record goes into `data/processed/rejected_records.csv` with the table name, record identifier, rejection reason, timestamp, and the raw payload stored as JSON. Nothing is dropped silently.

---

## SQL Analysis

Using `v_order_analytics` in SQLite, I ran analyses across orders, customers, and products. Key validated numbers:

* **Total Gross Invoiced Revenue**: \$33,726,886.71
* **Net Realized Revenue**: \$31,028,579.95 (from 95,526 completed and shipped orders)
* **Cost of Goods Sold (COGS)**: \$18,567,329.22
* **Net Gross Profit**: \$12,461,250.73
* **Realized Gross Margin**: 40.16%
* **Fulfillment Losses**:
  * Refunded orders: 4,087 orders, representing \$1,334,921.53
  * Cancelled orders: 4,082 orders, representing \$1,363,385.23
  * Total leakage: \$2,698,306.76 (8.00% of gross invoiced revenue)
* **Average Order Value (AOV)**: \$324.82 across revenue-generating orders
* **Category Dynamics**:
  * *Electronics* is the largest revenue driver (\$15.21M, 49.0% of net sales), but operates on the thinnest margin (24.01%) and generates the highest return/cancellation volume (\$1.36M).
  * *Beauty* (\$3.51M net revenue) and *Apparel* (\$5.51M net revenue) carry high margins of 74.31% and 61.69%, showing clear upside for marketing focus.

---

## Customer Segmentation & Churn

### RFM Segmentation
I segmented the 10,000 customers into 9 behavioral groups using quintiles on recency, frequency, and monetary spend:

* **Champions + Loyal Customers**: Represent **38.04% of customers (3,804 accounts) but generate 76.16% of total revenue (\$23,631,866.97)**.
  * *Champions* (2,150 customers): \$17.19M revenue (55.39%), averaging \$7,994 spend and 11.7 days recency.
  * *Loyal Customers* (1,654 customers): \$6.44M revenue (20.77%), averaging \$3,896 spend and 100.5 days recency.
* **At Risk** (1,000 customers): High past spend (\$4.10M revenue, 13.21%), but average recency has slipped to 401 days.
* **Hibernating** (1,976 customers): \$705K revenue (2.27%), low frequency, and 539 days average recency.
* **Inactive / Unactivated** (1,075 customers): Registered accounts that never completed an order (\$0 spend).

### Churn Risk Model
To predict which customers are likely to stop buying, I built a predictive model using an Out-of-Time (OOT) validation design to prevent data leakage:

* **Train Cohort**: Features calculated using orders on or before `2023-12-31`. Churn target evaluated over the next 90 days (`2024-01-01` to `2024-03-31`). 7,664 eligible customers, 60.27% churn rate.
* **Test Cohort**: Features calculated using orders on or before `2024-03-31`. Churn target evaluated over `2024-04-01` to `2024-06-30`. 8,873 eligible customers, 61.06% churn rate.
* **Zero Leakage**: All feature windows (recency, frequency, monetary value, ratios) strictly cut off on the feature date. Post-cutoff orders were excluded from feature extraction, and the `StandardScaler` was fit only on the training set.

### Model Results (Test Set, N = 8,873)
* **Logistic Regression (Primary Interpretable Model)**:
  * ROC-AUC: **0.9481**
  * Accuracy: **87.29%**
  * Precision: **94.39%**
  * Recall: **84.18%**
  * F1 Score: **0.8900**
  * Confusion Matrix: TN=3,184 | FP=271 | FN=857 | TP=4,561
* **Random Forest (Nonlinear Comparator)**:
  * ROC-AUC: **0.9510**
  * Accuracy: **87.56%**
  * Precision: **96.87%**
  * Recall: **82.28%**
  * F1 Score: **0.8898**
  * Confusion Matrix: TN=3,311 | FP=144 | FN=960 | TP=4,458

The model does not predict the future with 100% certainty, but it provides a clean probability score for ranking customer risk. Shifting the decision threshold between 0.30 and 0.70 allows teams to balance broad digital outreach (high recall) versus expensive sales-rep outreach (high precision).

---

## Power BI

I designed the reporting layer as a clean star schema under `data/processed/powerbi/`:

* `dim_date.csv`: 1,096 calendar days (2022-01-01 to 2024-12-31)
* `dim_customers.csv`: 10,000 customer profiles
* `dim_products.csv`: 492 products
* `fact_orders.csv`: 103,695 valid orders with clean foreign keys
* `dim_customer_analytics.csv`: 10,000 customer analytics profiles (RFM segment, risk score, churn probability)

I also built:
* A 24-measure DAX catalog (`dashboard/specs/dax_measures.dax`) covering revenue, profit, order status rates, customer metrics, and risk counts.
* Power Query M scripts (`dashboard/specs/powerquery_scripts.m`) for importing and typing the CSV files.
* A functional interactive HTML prototype (`dashboard/index.html`) demonstrating the four dashboard views (Executive Overview, Customer Analytics, Sales & Products, Risk & Retention).

**Environment Note**: Power BI Desktop was not installed in this environment. I did not fabricate a binary `.pbix` file. The star-schema CSVs, DAX measures, M scripts, and HTML prototype provide the complete blueprint and visual implementation.

---

## Some Results

| Metric | Validated Value | Business Meaning |
| :--- | :---: | :--- |
| **Net Realized Revenue** | **\$31,028,579.95** | Invoiced value across 95,526 completed and shipped orders |
| **Realized Gross Profit** | **\$12,461,250.73** | Net revenue minus cost of goods sold |
| **Realized Gross Margin** | **40.16%** | Overall product profitability |
| **Active Paying Customers** | **8,925** | Customers with at least 1 completed order |
| **Unactivated Accounts** | **1,075** | Signed-up users with 0 purchases |
| **Champions + Loyal Share** | **76.16%** | Share of revenue generated by top two customer segments (38.04% of base) |
| **High + Critical Risk Accounts** | **4,274** | Accounts with churn risk score $\ge 50$ |
| **Historical Revenue Exposure** | **\$10,466,895.09** | Past spend associated with High & Critical risk accounts (not guaranteed future loss) |
| **Fulfillment Leakage** | **\$2,698,306.76** | Revenue lost to refunds (\$1.33M) and cancellations (\$1.36M) |

---

## Business Actions

Based on the data, I identified five practical recommendations:

1. **Protect high-value customers**: The 3,804 Champions and Loyal Customers account for 76.16% of revenue. A dedicated VIP loyalty program with early access and dedicated support will reduce the risk of losing these core accounts.
2. **Re-engage dormant VIP accounts**: 1,110 customers in *At Risk* and *Cannot Lose Them* have generated \$4.69M historically, but have not ordered in over 400 days. High-touch personalized outreach with margin-subsidized incentives can recover a portion of these accounts.
3. **Fix the onboarding gap**: 1,075 registered customers (10.75%) have never placed an order. An automated 3-step welcome email sequence with a small first-order discount on hero products can convert more signups.
4. **Address electronics returns and margin**: Electronics brings in 49% of sales but delivers only 24% gross margin and loses \$1.36M to refunds and cancellations. Improving product detail specifications and analyzing return root causes will protect margin.
5. **Prioritize retention using churn risk**: Instead of broad blanket discounts, use the model's risk scores. Use automated digital emails for medium-risk accounts (threshold 0.30–0.40) and save expensive direct outreach for high-value accounts above threshold 0.60.

---

## Testing

The platform has a full test suite built with Python's standard `unittest` framework:

* **71 tests passed**
* **0 failures**
* **0 errors**
* **0 skipped**
* **Execution time**: ~148 seconds

The tests cover:
* Raw data extraction and transformations
* Data quality rules, null checks, and DLQ quarantine
* Mathematical financial invariants (Gross = Net + Refunds + Cancellations)
* Multi-dimensional revenue reconciliations (Customer, Product, Date, Month)
* RFM scoring bounds, mutual exclusivity, and unactivated handling
* Out-of-time train/test split safety and temporal anti-leakage
* Model artifact persistence, scorecard verification, and threshold curves
* Star-schema referential integrity (zero orphaned foreign keys)
* Pipeline reproducibility and dependency imports

The platform is **Production-Oriented and QA-Validated**.

---

## Repository Structure

```
customer-analytics-platform/
├── config/
│   └── config.yaml                     # Database, logging, and analytical settings
├── data/
│   ├── raw/                            # Immutable raw CSV extracts
│   └── processed/                      # Cleaned CSVs, staging SQLite database, DLQ
│       ├── models/                     # Saved model artifacts (.joblib, metrics JSON)
│       └── powerbi/                    # Star-schema CSV tables for BI import
├── dashboard/
│   ├── index.html                      # Interactive HTML executive dashboard prototype
│   └── specs/                          # 24 DAX measures and Power Query M scripts
├── docs/
│   ├── architecture.md                 # System architecture diagram and pipeline flow
│   ├── business_insights.md            # Detailed business analysis and findings
│   ├── customer_analytics.md           # RFM segmentation and churn model details
│   ├── data_dictionary.md              # Field-by-field schema documentation
│   ├── portfolio_project.md            # Case study write-up
│   ├── powerbi_dashboard.md            # Power BI specification and setup guide
│   ├── sql_business_insights.md        # SQL queries, aggregations, and metrics
│   └── testing_and_qa.md               # Complete QA audit report
├── scripts/                            # Diagnostic and verification scripts
├── sql/
│   ├── schema.sql                      # Production PostgreSQL DDL schema
│   ├── views.sql                       # Dimensional analytical view (v_order_analytics)
│   └── *.sql                           # Modular analytical queries (Sales, Product, Customer)
├── src/
│   ├── analytics/                      # SQL runner and Power BI dataset export
│   ├── config/                         # Paths and settings loader
│   ├── etl/                            # Extract, Transform, Validate (DLQ), and Load
│   ├── modeling/                       # Features, RFM scoring, Risk rules, Churn ML
│   └── utils/                          # Logging utilities
├── tests/                              # 8 test suites covering 71 automated tests
├── requirements.txt                    # Project dependencies
└── README.md
```

---

## Running the Project

### 1. Set Up Environment
```bash
python -m venv venv
# Windows (PowerShell):
.\venv\Scripts\Activate.ps1
# macOS/Linux:
source venv/bin/activate

pip install -r requirements.txt
```

### 2. Run ETL Pipeline
Cleans raw data, runs validation checks, isolates bad records to the DLQ, and loads valid tables into staging:
```bash
python -m src.etl.run_pipeline
```

### 3. Run Modeling & Customer Analytics
Calculates customer features, computes RFM scores, applies risk rules, trains the churn models, and saves artifacts:
```bash
python -m src.modeling.run_modeling
```

### 4. Generate Power BI Star-Schema Datasets
Builds the dimensional tables and fact orders for Power BI import:
```bash
python -m src.analytics.generate_powerbi_datasets
```

### 5. Run the Test Suite
Runs all 71 tests across all components:
```bash
python -m unittest discover -s tests -p "test_*.py"
```

---

## Limitations

* **Database Staging**: I validated the relational queries against a local SQLite staging database (`data/processed/staging.db`). PostgreSQL DDL and loaders are written and tested, but live execution against an external PostgreSQL cluster was not part of this local setup.
* **Power BI Environment**: Power BI Desktop was not installed on this system. Rather than claiming an unverified `.pbix` file, I built the star-schema CSVs, the DAX measure catalog, the Power Query M scripts, and an interactive HTML visual prototype.
* **Order Line Granularity**: Orders represent item-level transactions. Multi-item cart implementations would separate order headers and line items via a bridge table.
* **Batch Scoring**: Churn scores are calculated in a batch process. Real-time scoring would require an API endpoint wrapping the serialized model.
