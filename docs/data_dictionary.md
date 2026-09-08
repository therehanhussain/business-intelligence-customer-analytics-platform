# Data Dictionary

This document details the schemas and field definitions for the clean data files, analytical tables, and Power BI star-schema layers used across the platform.

---

## 1. Customers (`data/processed/customers_clean.csv`)

| Field Name | Data Type | Nullable | Description | Example / Values |
| :--- | :--- | :---: | :--- | :--- |
| `customer_id` | STRING | No | Unique customer identifier (Primary Key) | `CUST_000001` |
| `name` | STRING | No | Full customer name (Title Case normalized) | `James Smith` |
| `gender` | STRING | No | Standardized customer gender | `Male`, `Female`, `Unknown` |
| `age` | FLOAT | No | Customer age in years (18 to 100) | `39.0` |
| `city` | STRING | No | Customer residential city | `New York`, `Los Angeles` |
| `state` | STRING | No | Two-letter US state postal abbreviation | `NY`, `CA`, `TX` |
| `signup_date` | DATE | No | Account registration date (`YYYY-MM-DD`) | `2022-03-15` |
| `is_age_imputed` | BOOLEAN | No | Audit flag indicating if age was imputed via median | `True`, `False` |

---

## 2. Products (`data/processed/products_clean.csv`)

| Field Name | Data Type | Nullable | Description | Example / Values |
| :--- | :--- | :---: | :--- | :--- |
| `product_id` | STRING | No | Unique product identifier (Primary Key) | `PROD_00001` |
| `product_name` | STRING | No | Commercial product name | `Wireless Noise-Canceling Headphones` |
| `category` | STRING | No | Standardized product department/category | `Electronics`, `Apparel`, `Home`, `Beauty`, `Sports` |
| `price` | FLOAT | No | Standard retail selling price per unit in USD | `199.99` |
| `cost` | FLOAT | No | Unit manufacturing / acquisition cost in USD | `120.00` |
| `gross_margin_pct` | FLOAT | No | Pre-computed gross margin percentage: `((price - cost) / price) * 100` | `39.99` |

---

## 3. Orders (`data/processed/orders_clean.csv`)

| Field Name | Data Type | Nullable | Description | Example / Values |
| :--- | :--- | :---: | :--- | :--- |
| `order_id` | STRING | No | Unique order identifier (Primary Key) | `ORD_000001` |
| `customer_id` | STRING | No | Customer placing the order (Foreign Key to Customers) | `CUST_000140` |
| `product_id` | STRING | No | Product purchased (Foreign Key to Products) | `PROD_000042` |
| `order_date` | DATE | No | Transaction date (`YYYY-MM-DD`, 2022-01-01 to 2024-06-30) | `2023-08-14` |
| `quantity` | INTEGER | No | Units purchased (strictly > 0) | `1`, `2`, `4` |
| `payment_method` | STRING | No | Standardized payment method | `Credit Card`, `Debit Card`, `PayPal`, `Bank Transfer`, `Cash on Delivery` |
| `order_status` | STRING | No | Final order fulfillment status | `Completed`, `Shipped`, `Refunded`, `Cancelled` |

---

## 4. Dead-Letter Queue (`data/processed/rejected_records.csv`)

| Field Name | Data Type | Nullable | Description | Example / Values |
| :--- | :--- | :---: | :--- | :--- |
| `table_name` | STRING | No | Originating source table name | `customers`, `products`, `orders` |
| `record_identifier` | STRING | No | Primary key or natural key of the rejected record | `CUST_000012`, `PROD_000005`, `ORD_001245` |
| `rejection_reason` | STRING | No | Standardized validation failure code | `DUPLICATE_CUSTOMER_ID`, `ORPHAN_PRODUCT_FOREIGN_KEY`, etc. |
| `rejected_at` | TIMESTAMP | No | UTC timestamp when quarantine occurred | `2026-09-08T16:00:15.123456+00:00` |
| `raw_payload` | STRING | No | Full raw record payload serialized as a JSON string | `{"order_id": "ORD_01", "quantity": -2, ...}` |

---

## 5. Customer Analytics & Churn Features (`data/processed/customer_analytics.csv`)

| Field Name | Data Type | Nullable | Description | Example / Values |
| :--- | :--- | :---: | :--- | :--- |
| `customer_id` | STRING | No | Customer identifier | `CUST_000140` |
| `total_orders` | INTEGER | No | Total lifetime orders placed (all statuses) | `15` |
| `completed_orders` | INTEGER | No | Total fulfilled orders (`Completed` + `Shipped`) | `14` |
| `total_units` | INTEGER | No | Total units purchased across fulfilled orders | `28` |
| `active_months` | INTEGER | No | Distinct calendar months with completed transactions | `11` |
| `first_order_date` | DATE | Yes | Date of earliest order (`YYYY-MM-DD`) | `2022-02-10` |
| `last_order_date` | DATE | Yes | Date of most recent order (`YYYY-MM-DD`) | `2024-05-18` |
| `last_completed_order_date`| DATE | Yes | Date of most recent fulfilled order (`YYYY-MM-DD`) | `2024-05-18` |
| `recency_days` | INTEGER | No | Days between dataset cutoff and last fulfilled order | `43` |
| `account_age_days` | INTEGER | No | Days between customer signup date and cutoff date | `871` |
| `customer_lifetime_days` | INTEGER | No | Days between first and last order | `828` |
| `total_gross_revenue` | FLOAT | No | Invoiced value across all orders placed | `4580.50` |
| `total_revenue` | FLOAT | No | Net realized revenue across fulfilled orders | `4290.00` |
| `total_profit` | FLOAT | No | Net gross profit across fulfilled orders | `1845.20` |
| `average_order_value` | FLOAT | No | Average net spend per fulfilled order: `total_revenue / completed_orders` | `306.43` |
| `order_frequency_monthly` | FLOAT | No | Fulfilled orders per active month: `completed_orders / active_months` | `1.27` |
| `gross_margin_pct` | FLOAT | No | Realized customer margin: `(total_profit / total_revenue) * 100` | `43.01` |
| `refund_count` | INTEGER | No | Total orders with status `Refunded` | `1` |
| `refund_amount` | FLOAT | No | Cumulative dollar value of refunded orders | `290.50` |
| `refund_rate` | FLOAT | No | Ratio of refunded orders: `refund_count / total_orders` | `0.0667` |
| `cancellation_count` | INTEGER | No | Total orders with status `Cancelled` | `0` |
| `cancellation_amount` | FLOAT | No | Cumulative dollar value of cancelled orders | `0.00` |
| `cancellation_rate` | FLOAT | No | Ratio of cancelled orders: `cancellation_count / total_orders` | `0.0000` |
| `recent_revenue` | FLOAT | No | Net revenue earned in the last 90 days before cutoff | `620.00` |
| `recent_order_count` | INTEGER | No | Orders placed in the last 90 days before cutoff | `2` |
| `historical_revenue` | FLOAT | No | Net revenue earned prior to the 90-day recent window | `3670.00` |
| `historical_order_count` | INTEGER | No | Orders placed prior to the 90-day recent window | `12` |
| `recent_revenue_ratio` | FLOAT | No | Ratio of recent spend to total spend: `recent_revenue / total_revenue` | `0.1445` |
| `recent_order_ratio` | FLOAT | No | Ratio of recent orders to total orders: `recent_order_count / total_orders` | `0.1429` |
| `revenue_trend` | FLOAT | No | Velocity trend: annualized recent revenue vs annualized historical revenue | `-0.0521` |
| `r_score` | INTEGER | No | Recency quintile score (1 to 5; 0 for unactivated) | `5` |
| `f_score` | INTEGER | No | Frequency quintile score (1 to 5; 0 for unactivated) | `4` |
| `m_score` | INTEGER | No | Monetary spend quintile score (1 to 5; 0 for unactivated) | `4` |
| `rfm_score` | STRING | No | Concatenated RFM score | `544` |
| `customer_segment` | STRING | No | Behavioral segment name | `Champions`, `Loyal Customers`, `At Risk`, etc. |
| `risk_score` | INTEGER | No | Rule-based baseline attrition risk score (0 to 100) | `18` |
| `risk_level` | STRING | No | Risk tier | `LOW` (0-24), `MEDIUM` (25-49), `HIGH` (50-74), `CRITICAL` (75-100) |
| `key_risk_driver` | STRING | No | Primary behavioral factor elevating customer risk | `Healthy Engagement`, `High Inactivity`, etc. |
| `recommended_action` | STRING | No | Strategic business action playbook | `Reward Loyalty`, `VIP Win-Back`, `Welcome Incentive` |
| `churn_probability` | FLOAT | No | ML-predicted probability of 90-day inactivity from Logistic Regression | `0.124` |

---

## 6. Power BI Star Schema Tables (`data/processed/powerbi/`)

### 6.1 `dim_date.csv` (1,096 rows)
* `date`: Full date (`YYYY-MM-DD`).
* `date_id`: Integer surrogate key (`YYYYMMDD`, Primary Key).
* `date_str`: Formatted string (`YYYY-MM-DD`).
* `year`, `quarter`, `quarter_name`, `year_quarter`: Calendar year and quarterly identifiers.
* `month`, `month_name`, `month_short`, `month_year`: Month numbers, names, and labels.
* `day_of_month`, `day_of_week`, `day_name`, `is_weekend`: Day-level calendar attributes.
* `fiscal_year`, `fiscal_quarter`: Fiscal calendar mappings.

### 6.2 `dim_customers.csv` (10,000 rows)
* `customer_id`: Primary Key (`CUST_000001`).
* `name`, `gender`, `age`, `city`, `state`, `signup_date`: Core demographic attributes.
* `signup_date_id`: Surrogate foreign key to `DimDate`.
* `is_age_imputed`: Data quality flag.

### 6.3 `dim_products.csv` (492 rows)
* `product_id`: Primary Key (`PROD_00001`).
* `product_name`, `category`: Catalog descriptions.
* `price`, `cost`: Baseline unit economics.
* `margin_pct`: Pre-computed catalog margin percentage.

### 6.4 `fact_orders.csv` (103,695 rows)
* `order_id`: Primary Key (`ORD_000001`).
* `customer_id`: Foreign Key to `DimCustomers`.
* `product_id`: Foreign Key to `DimProducts`.
* `order_date`: Calendar transaction date.
* `order_date_id`: Foreign Key to `DimDate` (`YYYYMMDD`).
* `quantity`: Units ordered.
* `unit_price`, `unit_cost`: Unit price and unit cost at time of order.
* `gross_revenue`: Invoiced revenue (`quantity * unit_price`).
* `gross_profit`: Invoiced gross margin (`gross_revenue - (quantity * unit_cost)`).
* `net_revenue`: Realized revenue (\$0.00 for Refunded/Cancelled; equal to `gross_revenue` for Completed/Shipped).
* `net_profit`: Realized gross profit (\$0.00 for Refunded/Cancelled).
* `refunded_amount`: Dollar value refunded if `order_status = 'Refunded'`.
* `cancelled_amount`: Dollar value lost if `order_status = 'Cancelled'`.
* `payment_method`, `order_status`: Operational transaction metadata.
* `is_completed`, `is_refunded`, `is_cancelled`: Binary status flags for fast DAX aggregation.

### 6.5 `dim_customer_analytics.csv` (10,000 rows)
* 1-to-1 extension of `DimCustomers` containing all pre-computed fields from Section 5 (RFM scores, segment names, baseline risk scores, risk tiers, key drivers, recommended actions, and ML churn probabilities).
