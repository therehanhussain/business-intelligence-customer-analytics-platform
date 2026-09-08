"""Unit test suite for Phase 2 ETL pipeline modules (extract, transform, validate, load)."""

import json
from pathlib import Path
import unittest
import pandas as pd
import numpy as np

from src.config.paths import PROCESSED_DATA_DIR, RAW_DATA_DIR
from src.etl.extract import extract_all_raw_data, extract_raw_table
from src.etl.transform import (
    transform_customers,
    transform_products,
    transform_orders,
)
from src.etl.validate import (
    validate_customers,
    validate_products,
    validate_orders,
    validate_all_data,
)
from src.etl.load import get_database_engine, save_processed_files, load_to_database


class TestETLPipeline(unittest.TestCase):
    """Automated tests for extraction, transformation, validation, and loading."""

    @classmethod
    def setUpClass(cls):
        """Extract raw datasets once for test suite."""
        cls.cust_raw, cls.prod_raw, cls.ord_raw, cls.meta = extract_all_raw_data(RAW_DATA_DIR)

    def test_extraction_loads_all_tables(self):
        """Verify extraction returns non-empty dataframes with correct metadata."""
        self.assertGreater(len(self.cust_raw), 0)
        self.assertGreater(len(self.prod_raw), 0)
        self.assertGreater(len(self.ord_raw), 0)
        self.assertIn("extracted_at", self.meta)
        self.assertIn("source_counts", self.meta)

    def test_transform_customers_normalization_and_imputation(self):
        """Verify customer transformations standardize casing and impute missing age."""
        tf_cust, stats = transform_customers(self.cust_raw)

        # 1. Title casing
        self.assertTrue(tf_cust["name"].str.istitle().all() or not tf_cust["name"].str.islower().any())

        # 2. Gender canonical mapping
        unique_genders = set(tf_cust["gender"].unique())
        self.assertTrue(unique_genders.issubset({"Male", "Female", "Unknown"}))

        # 3. Age imputation
        self.assertFalse(tf_cust["age"].isna().any(), "Imputed age column should have no nulls")
        self.assertIn("is_age_imputed", tf_cust.columns)
        self.assertEqual(tf_cust["is_age_imputed"].sum(), stats["ages_imputed"])
        self.assertGreater(stats["ages_imputed"], 0)

    def test_transform_products_casing_and_derived_margin(self):
        """Verify product categories are title cased and gross margin is computed."""
        tf_prod, stats = transform_products(self.prod_raw)

        # Margin derived column
        self.assertIn("gross_margin_pct", tf_prod.columns)
        valid_margins = tf_prod["gross_margin_pct"].dropna()
        self.assertTrue((valid_margins > 0).all())
        self.assertTrue((valid_margins < 100).all())

        # No lowercase 'electronics'
        valid_cats = tf_prod["category"].dropna().unique()
        self.assertNotIn("electronics", valid_cats)
        self.assertIn("Electronics", valid_cats)

    def test_transform_orders_canonical_mappings(self):
        """Verify payment methods and statuses are canonicalized."""
        tf_ord, stats = transform_orders(self.ord_raw)

        # No raw abbreviations like 'CC' or 'COD'
        valid_pm = set(tf_ord["payment_method"].dropna().unique())
        self.assertNotIn("CC", valid_pm)
        self.assertNotIn("credit_card", valid_pm)
        self.assertNotIn("COD", valid_pm)
        self.assertIn("Credit Card", valid_pm)
        self.assertIn("Cash on Delivery", valid_pm)

        # Order statuses are title cased
        valid_st = set(tf_ord["order_status"].dropna().unique())
        self.assertNotIn("completed", valid_st)
        self.assertIn("Completed", valid_st)

    def test_validation_customers_dlq_quarantine(self):
        """Verify customer duplicates are partitioned into Dead-Letter Queue."""
        tf_cust, _ = transform_customers(self.cust_raw)
        valid_cust, rej_cust, stats = validate_customers(tf_cust)

        # Check that valid customers have zero duplicates
        self.assertEqual(valid_cust["customer_id"].duplicated().sum(), 0)
        self.assertEqual(len(valid_cust), 10000)

        # Check DLQ quarantine
        self.assertEqual(len(rej_cust), 80)
        self.assertEqual((rej_cust["rejection_reason"] == "DUPLICATE_CUSTOMER_ID").sum(), 80)
        self.assertIn("raw_payload", rej_cust.columns)

    def test_validation_products_dlq_quarantine(self):
        """Verify products with missing critical categories/costs are quarantined."""
        tf_prod, _ = transform_products(self.prod_raw)
        valid_prod, rej_prod, stats = validate_products(tf_prod)

        # Check valid products have 100% complete critical fields
        self.assertEqual(valid_prod["category"].isna().sum(), 0)
        self.assertEqual(valid_prod["cost"].isna().sum(), 0)
        self.assertTrue((valid_prod["cost"] <= valid_prod["price"]).all())

        # Check DLQ contains the missing category & missing cost items
        reasons = set(rej_prod["rejection_reason"].unique())
        self.assertIn("MISSING_PRODUCT_CATEGORY", reasons)
        self.assertIn("MISSING_PRODUCT_COST", reasons)
        self.assertEqual(len(rej_prod), 8)

    def test_validation_orders_dlq_quarantine(self):
        """Verify invalid quantities (negative and zero) are quarantined from orders."""
        tf_cust, _ = transform_customers(self.cust_raw)
        tf_prod, _ = transform_products(self.prod_raw)
        tf_ord, _ = transform_orders(self.ord_raw)

        valid_cust, _, _ = validate_customers(tf_cust)
        valid_prod, _, _ = validate_products(tf_prod)

        valid_cust_ids = set(valid_cust["customer_id"].unique())
        valid_prod_ids = set(valid_prod["product_id"].unique())

        valid_ord, rej_ord, stats = validate_orders(tf_ord, valid_cust_ids, valid_prod_ids)

        # 1. Zero negative or zero quantities in valid orders
        self.assertTrue((valid_ord["quantity"] > 0).all())

        # 2. Rejection reasons in DLQ
        ord_reasons = set(rej_ord["rejection_reason"].unique())
        self.assertIn("INVALID_QUANTITY_NEGATIVE_RETURN", ord_reasons)
        self.assertIn("INVALID_QUANTITY_ZERO", ord_reasons)

        # 3. 100% Referential Integrity in valid orders
        self.assertTrue(valid_ord["customer_id"].isin(valid_cust_ids).all())
        self.assertTrue(valid_ord["product_id"].isin(valid_prod_ids).all())

    def test_processed_output_artifacts_exist(self):
        """Verify that processed CSV files and audit summary were persisted to data/processed/."""
        expected_files = [
            PROCESSED_DATA_DIR / "customers_clean.csv",
            PROCESSED_DATA_DIR / "products_clean.csv",
            PROCESSED_DATA_DIR / "orders_clean.csv",
            PROCESSED_DATA_DIR / "rejected_records.csv",
            PROCESSED_DATA_DIR / "etl_audit_summary.json",
        ]
        for f in expected_files:
            self.assertTrue(f.exists(), f"Processed artifact missing: {f}")

        # Verify audit summary content
        audit_file = PROCESSED_DATA_DIR / "etl_audit_summary.json"
        with open(audit_file, "r", encoding="utf-8") as fp:
            data = json.load(fp)
            self.assertIn("pipeline_run_id", data)
            self.assertIn("validation", data)
            self.assertIn("dead_letter_queue_breakdown", data["validation"])


if __name__ == "__main__":
    unittest.main()
