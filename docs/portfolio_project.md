# Business Intelligence & Customer Analytics Platform

## The Problem

Working with retail transactional data sounds straightforward until you actually look at the raw files. In most multi-channel retail companies, point-of-sale systems, e-commerce checkout platforms, and CRM databases log data independently. You end up with duplicated customer IDs, negative return lines mixed into regular orders, missing product costs, and orders referencing items that do not exist in the active catalog.

If an analytics team feeds that messy data directly into dashboards or machine learning models without strict validation, business leaders end up making decisions on wrong numbers. Marketing spends budget re-engaging customers who already churned, finance questions margin reports because returns were not accounted for properly, and executives lose trust in the data.

I built this project to solve that exact problem: take raw, messy retail data, clean and validate it through an automated pipeline with a Dead-Letter Queue, model it in SQL, segment customers by purchasing habits, predict churn risk with zero data leakage, and prepare a verified reporting layer for business decision-making.

---

## What I Built

I developed an end-to-end Python and SQL platform that handles the full analytics workflow:

```
Raw CSVs → Python ETL & Validation → Staging Database → SQL Analytics → RFM & Churn Models → Power BI Data Layer
```

Instead of running manual ad-hoc scripts, the pipeline is fully automated and modular. It cleans data, tests constraints, loads valid records into a relational star schema, computes financial metrics, segments customers using RFM quintiles, predicts 90-day churn using Logistic Regression and Random Forest, and exports Power BI-ready datasets with an interactive HTML prototype.

---

## Data Engineering

The pipeline started with 117,499 raw records across customers (10,080), products (500), and orders (106,919). 

The extraction and transformation scripts (`src/etl/extract.py`, `src/etl/transform.py`) normalize names and casing, map inconsistent payment methods (like "CC" to "Credit Card"), and impute missing customer ages using the median age (39.0) with an audit flag.

The validation step (`src/etl/validate.py`) enforces strict business rules:
* Primary key uniqueness on customer IDs and order IDs
* Demographic bounds (age between 18 and 100)
* Product catalog completeness (category and cost must not be null)
* Price and cost domain checks (price > 0, cost > 0, cost $\le$ price)
* Order quantity constraints (quantity > 0)
* Foreign-key integrity (orders must reference existing customers and products)

Rather than dropping non-conforming rows silently, I routed all invalid rows into a Dead-Letter Queue (`data/processed/rejected_records.csv`) with the rejection reason, timestamp, and the raw payload stored as JSON. 

Out of 117,499 raw records, **114,187 passed validation (97.18%)** and **3,312 were quarantined**:
* 80 customer records with duplicate IDs
* 8 product records missing categories or costs
* 2,729 orders referencing the 8 invalid products (orphan foreign keys)
* 330 negative return quantity orders
* 165 zero-quantity orders

The valid records were loaded into clean CSVs and a local SQLite staging database (`data/processed/staging.db`).

---

## Analysis

In `sql/views.sql`, I built `v_order_analytics` to join valid orders, customers, and products without multiplying rows. I verified two core accounting identities to the exact cent:
1. $\text{Gross Invoiced Revenue (\$33,726,886.71)} = \text{Net Revenue (\$31,028,579.95)} + \text{Refunds (\$1,334,921.53)} + \text{Cancellations (\$1,363,385.23)}$
2. $\text{Net Revenue (\$31,028,579.95)} = \text{Gross Profit (\$12,461,250.73)} + \text{COGS (\$18,567,329.22)}$

The overall realized gross margin is **40.16%** across 95,526 fulfilled orders, with an Average Order Value of **\$324.82**. 

Cross-dimensional checks confirmed that summing net revenue by customer, by product, by order date, or across all 30 active transaction months yields the exact same \$31,028,579.95 figure.

---

## Churn / Risk Modeling

For customer analytics, I segmented the 10,000 customers into 9 RFM groups. 1,075 registered customers had never completed an order, so they were cleanly labeled as "Inactive / Unactivated" (\$0 revenue).

To predict customer churn, I set up an Out-of-Time (OOT) temporal validation split to prevent data leakage:
* **Train Cohort**: Feature cutoff $\le$ `2023-12-31`, outcome window `2024-01-01` to `2024-03-31` (7,664 accounts, 60.27% churn rate).
* **Test Cohort**: Feature cutoff $\le$ `2024-03-31`, outcome window `2024-04-01` to `2024-06-30` (8,873 accounts, 61.06% churn rate).

Every feature (recency, frequency, monetary ratios) was calculated strictly using transactions on or before the cutoff date. 32,476 post-cutoff transactions were completely excluded during training feature extraction, and the `StandardScaler` was fit only on training data.

On the test set ($N=8,873$):
* **Logistic Regression (Primary)**: ROC-AUC **0.9481**, Accuracy **87.29%**, Precision **94.39%**, Recall **84.18%**, F1 **0.8900**
* **Random Forest (Comparator)**: ROC-AUC **0.9510**, Accuracy **87.56%**, Precision **96.87%**, Recall **82.28%**, F1 **0.8898**

Evaluating the decision threshold across 0.30 to 0.70 showed that marketing can lower the threshold to 0.40 to capture 87.80% of churners with 90.92% precision for low-cost digital campaigns, while using a 0.60+ threshold for high-cost retention offers.

---

## Dashboard

I prepared a clean star schema under `data/processed/powerbi/` with five tables: `dim_date.csv`, `dim_customers.csv`, `dim_products.csv`, `fact_orders.csv`, and `dim_customer_analytics.csv`. All foreign keys resolve cleanly with zero orphans.

I wrote 24 DAX measures in `dashboard/specs/dax_measures.dax`, Power Query M scripts in `dashboard/specs/powerquery_scripts.m`, and an interactive HTML prototype in `dashboard/index.html`. 

Power BI Desktop was not available in my development environment, so I did not claim a `.pbix` file. Instead, the star schema files, DAX specifications, and HTML prototype provide the complete visual and technical implementation.

---

## What I Found

1. **Customer Revenue Concentration**: Champions and Loyal Customers represent **38.04% of customers (3,804 accounts) but generate 76.16% of total net revenue (\$23,631,866.97)**.
2. **Category Margin Disparity**: Electronics drives 49.0% of net sales (\$15.21M) but operates on a thin 24.01% gross margin and loses \$1.36M to refunds and cancellations. High-margin categories like Beauty (74.31% margin) and Apparel (61.69% margin) represent substantial untapped profit potential.
3. **VIP Dormancy**: 1,110 customers in *At Risk* and *Cannot Lose Them* have spent \$4.69M historically, but have not ordered in over 400 days.
4. **Onboarding Leakage**: 10.75% of registered users (1,075 accounts) never placed a single order.
5. **Historical Revenue Exposure**: 4,274 customers are currently classified as High or Critical churn risk, accounting for **\$10,466,895.09 in cumulative past spend**.

---

## What I Would Do Next

* Connect the pipeline to a live PostgreSQL database cluster to test live query throughput and indexing performance.
* Open the star schema in Power BI Desktop and save the official `.pbix` file.
* Build an automated monthly retraining pipeline that monitors model drift and feature importance shifts.
* Add interaction features such as web browse events, email opens, and support ticket sentiment to improve churn prediction accuracy for newer accounts.

---

## What I Learned

Building this project reinforced that the hardest part of data engineering is not writing complex code, but maintaining strict integrity across layers. A minor bug in order filtering or date comparison can silently corrupt downstream revenue metrics or leak future information into machine learning models. 

Writing 71 automated tests forced me to think about edge cases upfront: how to handle zero orders cleanly, how to isolate rejected records without halting the pipeline, and how to verify financial numbers down to the cent. The resulting platform is disciplined, reproducible, and easy to explain.
