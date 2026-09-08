"""Transformation module for the Customer Analytics Platform.

Applies deterministic cleaning, text normalization, categorical standardization,
and feature derivation across extracted raw tables.
"""

from typing import Any, Dict, Tuple
import numpy as np
import pandas as pd

from src.utils.logger import get_logger

logger = get_logger(__name__)

# Gender canonical mapping
GENDER_MAP = {
    "m": "Male",
    "male": "Male",
    "f": "Female",
    "female": "Female",
}

# Payment method canonical mapping
PAYMENT_METHOD_MAP = {
    "cc": "Credit Card",
    "credit_card": "Credit Card",
    "credit card": "Credit Card",
    "paypal": "PayPal",
    "cod": "Cash on Delivery",
    "cash on delivery": "Cash on Delivery",
    "debit_card": "Debit Card",
    "debit card": "Debit Card",
    "apple pay": "Apple Pay",
    "apple_pay": "Apple Pay",
}

# Product category canonical mapping
CATEGORY_MAP = {
    "electronics": "Electronics",
    "apparel & accessories": "Apparel & Accessories",
    "home & kitchen": "Home & Kitchen",
    "beauty & personal care": "Beauty & Personal Care",
    "sports & outdoors": "Sports & Outdoors",
    "books & media": "Books & Media",
}


def transform_customers(df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """Clean and standardize customer records.

    Transformations:
    - Strip whitespace and title-case customer name and city.
    - Canonicalize state code to uppercase.
    - Standardize gender values to 'Male', 'Female', or 'Unknown'.
    - Impute missing age with the population median, creating `is_age_imputed` flag.
    - Standardize signup_date to ISO YYYY-MM-DD.
    """
    logger.info("Transforming customer records (%d input rows)...", len(df))
    transformed = df.copy()

    # 1. Text normalization
    transformed["name"] = transformed["name"].astype(str).str.strip().str.title()
    transformed["city"] = transformed["city"].astype(str).str.strip().str.title()
    transformed["state"] = transformed["state"].astype(str).str.strip().str.upper()

    # 2. Gender standardization
    raw_gender_lower = transformed["gender"].astype(str).str.strip().str.lower()
    normalized_gender = raw_gender_lower.map(GENDER_MAP)
    # Where unmapped or NaN, mark as 'Unknown'
    normalized_gender = normalized_gender.fillna("Unknown")
    # Restore 'Unknown' if the original value was NaN/None
    normalized_gender[df["gender"].isna()] = "Unknown"
    transformed["gender"] = normalized_gender

    # 3. Age imputation & auditing
    valid_ages = pd.to_numeric(transformed["age"], errors="coerce")
    median_age = float(valid_ages.median()) if valid_ages.notna().any() else 38.0
    is_missing_age = transformed["age"].isna() | valid_ages.isna()
    n_imputed_age = int(is_missing_age.sum())

    transformed["is_age_imputed"] = is_missing_age
    transformed["age"] = valid_ages.fillna(median_age).round(1)

    # 4. Date formatting
    transformed["signup_date"] = pd.to_datetime(transformed["signup_date"]).dt.strftime("%Y-%m-%d")

    stats = {
        "input_rows": len(df),
        "ages_imputed": n_imputed_age,
        "median_imputed_age": median_age,
        "unknown_genders": int((transformed["gender"] == "Unknown").sum()),
    }
    logger.info("Customer transformation completed: %d ages imputed.", n_imputed_age)
    return transformed, stats


def transform_products(df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """Clean and standardize product catalog records.

    Transformations:
    - Standardize category naming to canonical title case.
    - Round price and cost to 2 decimal places.
    - Derive `gross_margin_pct` for valid pricing.
    """
    logger.info("Transforming product catalog (%d input rows)...", len(df))
    transformed = df.copy()

    # 1. Text & Category normalization
    transformed["product_name"] = transformed["product_name"].astype(str).str.strip()
    
    # Map non-null categories to canonical title casing
    def _clean_cat(val: Any) -> Any:
        if pd.isna(val):
            return np.nan
        val_str = str(val).strip().lower()
        return CATEGORY_MAP.get(val_str, str(val).strip().title())

    transformed["category"] = transformed["category"].apply(_clean_cat)

    # 2. Currency rounding
    transformed["price"] = pd.to_numeric(transformed["price"], errors="coerce").round(2)
    transformed["cost"] = pd.to_numeric(transformed["cost"], errors="coerce").round(2)

    # 3. Derived feature: Gross Margin Percentage
    valid_pricing_mask = (transformed["price"] > 0) & transformed["cost"].notna()
    margin = pd.Series(index=transformed.index, dtype=float)
    margin[valid_pricing_mask] = (
        (transformed.loc[valid_pricing_mask, "price"] - transformed.loc[valid_pricing_mask, "cost"])
        / transformed.loc[valid_pricing_mask, "price"]
    ) * 100.0
    transformed["gross_margin_pct"] = margin.round(2)

    stats = {
        "input_rows": len(df),
        "missing_categories": int(transformed["category"].isna().sum()),
        "missing_costs": int(transformed["cost"].isna().sum()),
        "average_margin_pct": float(transformed["gross_margin_pct"].mean(skipna=True)),
    }
    logger.info("Product transformation completed.")
    return transformed, stats


def transform_orders(df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """Clean and standardize transactional order records.

    Transformations:
    - Standardize payment method aliases ('CC', 'paypal', 'COD') to canonical forms.
    - Impute missing payment methods as 'Unknown'.
    - Standardize order status to title casing ('Completed', 'Shipped', 'Cancelled', 'Refunded').
    - Standardize order_date to ISO YYYY-MM-DD.
    """
    logger.info("Transforming transactional orders (%d input rows)...", len(df))
    transformed = df.copy()

    # 1. Payment method normalization
    raw_pm_lower = transformed["payment_method"].astype(str).str.strip().str.lower()
    normalized_pm = raw_pm_lower.map(PAYMENT_METHOD_MAP)
    normalized_pm = normalized_pm.fillna("Unknown")
    normalized_pm[df["payment_method"].isna()] = "Unknown"
    transformed["payment_method"] = normalized_pm

    # 2. Order status normalization
    transformed["order_status"] = transformed["order_status"].astype(str).str.strip().str.title()

    # 3. Order date normalization
    transformed["order_date"] = pd.to_datetime(transformed["order_date"]).dt.strftime("%Y-%m-%d")

    stats = {
        "input_rows": len(df),
        "unknown_payment_methods": int((transformed["payment_method"] == "Unknown").sum()),
        "status_distribution": transformed["order_status"].value_counts().to_dict(),
    }
    logger.info("Order transformation completed.")
    return transformed, stats


def transform_all_data(
    customers_df: pd.DataFrame,
    products_df: pd.DataFrame,
    orders_df: pd.DataFrame,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, Dict[str, Any]]:
    """Apply transformations across all extracted source datasets."""
    cust_tf, cust_stats = transform_customers(customers_df)
    prod_tf, prod_stats = transform_products(products_df)
    ord_tf, ord_stats = transform_orders(orders_df)

    transformation_metadata = {
        "customers": cust_stats,
        "products": prod_stats,
        "orders": ord_stats,
    }
    return cust_tf, prod_tf, ord_tf, transformation_metadata
