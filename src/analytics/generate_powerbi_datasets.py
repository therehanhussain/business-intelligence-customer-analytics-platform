"""Power BI Star Schema Dataset Generator.

Prepares production-ready dimensional and fact datasets formatted for direct import
into Microsoft Power BI Desktop or tabular data models:
1. dim_date.csv - Comprehensive date dimension with calendar and fiscal hierarchies.
2. fact_orders.csv - Transactional fact table with foreign keys, metrics, and flags.
3. dim_customers.csv - Demographics and account attributes.
4. dim_products.csv - Product catalog, pricing, cost, and category hierarchy.
5. dim_customer_analytics.csv - Customer-level RFM, risk tiers, and ML churn probabilities.

Also persists tables into SQLite staging.db to support automated SQL QA validation.
"""

from datetime import datetime
from pathlib import Path
import sqlite3
from typing import Dict, Tuple

import numpy as np
import pandas as pd

from src.config.paths import PROCESSED_DATA_DIR
from src.utils.logger import get_logger

logger = get_logger(__name__)

PBI_DIR = PROCESSED_DATA_DIR / "powerbi"


def generate_date_dimension(start_date: str = "2022-01-01", end_date: str = "2024-12-31") -> pd.DataFrame:
    """Generate a comprehensive Date dimension spanning the entire transactional window and forward horizon."""
    logger.info("Generating DimDate spanning %s to %s...", start_date, end_date)
    dates = pd.date_range(start=start_date, end=end_date, freq="D")
    
    df = pd.DataFrame({"date": dates})
    df["date_id"] = df["date"].dt.strftime("%Y%m%d").astype(int)
    df["date_str"] = df["date"].dt.strftime("%Y-%m-%d")
    df["year"] = df["date"].dt.year
    df["quarter"] = df["date"].dt.quarter
    df["quarter_name"] = "Q" + df["quarter"].astype(str)
    df["year_quarter"] = df["year"].astype(str) + "-Q" + df["quarter"].astype(str)
    df["month"] = df["date"].dt.month
    df["month_name"] = df["date"].dt.strftime("%B")
    df["month_short"] = df["date"].dt.strftime("%b")
    df["month_year"] = df["date"].dt.strftime("%Y-%m")
    df["day_of_month"] = df["date"].dt.day
    df["day_of_week"] = df["date"].dt.dayofweek + 1  # 1=Monday, 7=Sunday
    df["day_name"] = df["date"].dt.strftime("%A")
    df["is_weekend"] = df["day_of_week"].isin([6, 7]).astype(int)
    
    # Fiscal year definition (assuming fiscal year = calendar year for retail model)
    df["fiscal_year"] = "FY" + df["year"].astype(str)
    df["fiscal_quarter"] = "FQ" + df["quarter"].astype(str)
    
    logger.info("Generated %d date dimension records.", len(df))
    return df


def prepare_powerbi_datasets() -> Dict[str, pd.DataFrame]:
    """Extract, enrich, and format star-schema tables for Power BI."""
    PBI_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("Preparing Power BI ready datasets in %s...", PBI_DIR)

    # 1. Load validated datasets from Phase 2 and Phase 4
    cust_path = PROCESSED_DATA_DIR / "customers_clean.csv"
    prod_path = PROCESSED_DATA_DIR / "products_clean.csv"
    ord_path = PROCESSED_DATA_DIR / "orders_clean.csv"
    analytics_path = PROCESSED_DATA_DIR / "customer_analytics.csv"

    customers_df = pd.read_csv(cust_path)
    products_df = pd.read_csv(prod_path)
    orders_df = pd.read_csv(ord_path)
    customer_analytics_df = pd.read_csv(analytics_path)

    # 2. Build DimDate
    dim_date = generate_date_dimension("2022-01-01", "2024-12-31")

    # 3. Build DimProducts
    dim_products = products_df.copy()
    dim_products["margin_pct"] = (
        (dim_products["price"] - dim_products["cost"]) * 100.0 / dim_products["price"]
    ).round(2)
    dim_products = dim_products[[
        "product_id", "product_name", "category", "price", "cost", "margin_pct"
    ]]

    # 4. Build DimCustomers
    dim_customers = customers_df.copy()
    dim_customers["signup_date_id"] = pd.to_datetime(dim_customers["signup_date"]).dt.strftime("%Y%m%d").astype(int)
    dim_customers = dim_customers[[
        "customer_id", "name", "gender", "age", "city", "state", "signup_date", "signup_date_id", "is_age_imputed"
    ]]

    # 5. Build FactOrders
    # Join with products to compute gross revenue and margin contribution
    fact_orders = orders_df.merge(
        products_df[["product_id", "price", "cost"]],
        on="product_id",
        how="left"
    )
    fact_orders["order_date_id"] = pd.to_datetime(fact_orders["order_date"]).dt.strftime("%Y%m%d").astype(int)
    fact_orders["unit_price"] = fact_orders["price"].round(2)
    fact_orders["unit_cost"] = fact_orders["cost"].round(2)
    fact_orders["gross_revenue"] = (fact_orders["quantity"] * fact_orders["unit_price"]).round(2)
    fact_orders["gross_profit"] = (
        (fact_orders["unit_price"] - fact_orders["unit_cost"]) * fact_orders["quantity"]
    ).round(2)

    # Status indicators
    fact_orders["is_completed"] = fact_orders["order_status"].isin(["Completed", "Shipped"]).astype(int)
    fact_orders["is_refunded"] = (fact_orders["order_status"] == "Refunded").astype(int)
    fact_orders["is_cancelled"] = (fact_orders["order_status"] == "Cancelled").astype(int)
    
    # Net measures (aligned with Phase 3/4 definitions)
    fact_orders["net_revenue"] = np.where(fact_orders["is_completed"] == 1, fact_orders["gross_revenue"], 0.0)
    fact_orders["net_profit"] = np.where(fact_orders["is_completed"] == 1, fact_orders["gross_profit"], 0.0)
    fact_orders["refunded_amount"] = np.where(fact_orders["is_refunded"] == 1, fact_orders["gross_revenue"], 0.0)
    fact_orders["cancelled_amount"] = np.where(fact_orders["is_cancelled"] == 1, fact_orders["gross_revenue"], 0.0)

    fact_orders = fact_orders[[
        "order_id", "customer_id", "product_id", "order_date", "order_date_id",
        "quantity", "unit_price", "unit_cost", "gross_revenue", "gross_profit",
        "net_revenue", "net_profit", "refunded_amount", "cancelled_amount",
        "payment_method", "order_status", "is_completed", "is_refunded", "is_cancelled"
    ]]

    # 6. Build DimCustomerAnalytics
    dim_customer_analytics = customer_analytics_df.copy()

    # 7. Save CSVs to data/processed/powerbi/
    dim_date.to_csv(PBI_DIR / "dim_date.csv", index=False)
    dim_products.to_csv(PBI_DIR / "dim_products.csv", index=False)
    dim_customers.to_csv(PBI_DIR / "dim_customers.csv", index=False)
    fact_orders.to_csv(PBI_DIR / "fact_orders.csv", index=False)
    dim_customer_analytics.to_csv(PBI_DIR / "dim_customer_analytics.csv", index=False)

    logger.info("Saved 5 Power BI datasets to %s", PBI_DIR)

    # 8. Persist into SQLite staging.db for local SQL verification
    db_path = PROCESSED_DATA_DIR / "staging.db"
    with sqlite3.connect(db_path) as conn:
        dim_date.to_sql("pbi_dim_date", conn, if_exists="replace", index=False)
        dim_products.to_sql("pbi_dim_products", conn, if_exists="replace", index=False)
        dim_customers.to_sql("pbi_dim_customers", conn, if_exists="replace", index=False)
        fact_orders.to_sql("pbi_fact_orders", conn, if_exists="replace", index=False)
        dim_customer_analytics.to_sql("pbi_dim_customer_analytics", conn, if_exists="replace", index=False)
        logger.info("Persisted pbi_* tables into %s", db_path)

    # Reconciliation printout
    total_net_rev = fact_orders["net_revenue"].sum()
    total_net_profit = fact_orders["net_profit"].sum()
    total_orders = len(fact_orders)
    total_custs = len(dim_customers)

    print("=" * 80)
    print("  POWER BI DATA LAYER GENERATION & RECONCILIATION")
    print("=" * 80)
    print(f"Fact Orders Count       : {total_orders:,} (Expected: 103,695)")
    print(f"Dim Customer Count      : {total_custs:,} (Expected: 10,000)")
    print(f"Dim Products Count      : {len(dim_products):,} (Expected: 492)")
    print(f"Dim Date Count          : {len(dim_date):,} days (2022-01-01 to 2024-12-31)")
    print(f"Total Net Revenue       : ${total_net_rev:,.2f} (Expected: $31,028,579.95)")
    print(f"Total Net Profit        : ${total_net_profit:,.2f} (Expected: $12,461,250.73)")
    print(f"Reconciliation Match    : {'CONFIRMED EXACT MATCH' if abs(total_net_rev - 31028579.95) < 0.01 else 'DISCREPANCY'}")
    print("=" * 80)

    return {
        "dim_date": dim_date,
        "dim_products": dim_products,
        "dim_customers": dim_customers,
        "fact_orders": fact_orders,
        "dim_customer_analytics": dim_customer_analytics,
    }


if __name__ == "__main__":
    prepare_powerbi_datasets()
