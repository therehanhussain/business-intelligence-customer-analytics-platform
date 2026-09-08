"""Unit tests for Phase 1 synthetic dataset generation."""

import unittest
import pandas as pd

from src.config.paths import RAW_DATA_DIR


class TestDataGeneration(unittest.TestCase):
    """Test suite verifying generated raw datasets."""

    @classmethod
    def setUpClass(cls):
        cls.customers_path = RAW_DATA_DIR / "customers.csv"
        cls.products_path = RAW_DATA_DIR / "products.csv"
        cls.orders_path = RAW_DATA_DIR / "orders.csv"

        cls.customers_df = pd.read_csv(cls.customers_path)
        cls.products_df = pd.read_csv(cls.products_path)
        cls.orders_df = pd.read_csv(cls.orders_path)

    def test_raw_files_exist(self):
        """Verify all three raw CSV files exist."""
        self.assertTrue(self.customers_path.exists())
        self.assertTrue(self.products_path.exists())
        self.assertTrue(self.orders_path.exists())

    def test_row_counts_meet_specifications(self):
        """Verify row counts meet Phase 1 volume requirements."""
        self.assertGreaterEqual(len(self.customers_df), 10000)
        self.assertGreaterEqual(len(self.products_df), 490)
        self.assertGreaterEqual(len(self.orders_df), 100000)

    def test_column_schemas(self):
        """Verify column schemas match specifications."""
        expected_cust_cols = {"customer_id", "name", "gender", "age", "city", "state", "signup_date"}
        expected_prod_cols = {"product_id", "product_name", "category", "price", "cost"}
        expected_ord_cols = {"order_id", "customer_id", "product_id", "order_date", "quantity", "payment_method", "order_status"}

        self.assertTrue(expected_cust_cols.issubset(set(self.customers_df.columns)))
        self.assertTrue(expected_prod_cols.issubset(set(self.products_df.columns)))
        self.assertTrue(expected_ord_cols.issubset(set(self.orders_df.columns)))

    def test_referential_integrity(self):
        """Verify that every order references valid customers and products."""
        valid_customers = set(self.customers_df["customer_id"].unique())
        valid_products = set(self.products_df["product_id"].unique())

        order_customers = set(self.orders_df["customer_id"].unique())
        order_products = set(self.orders_df["product_id"].unique())

        orphan_customers = order_customers - valid_customers
        orphan_products = order_products - valid_products

        self.assertEqual(len(orphan_customers), 0, f"Found orphan customers: {orphan_customers}")
        self.assertEqual(len(orphan_products), 0, f"Found orphan products: {orphan_products}")

    def test_temporal_consistency(self):
        """Verify that no order occurs prior to the customer's signup date."""
        cust_signup = self.customers_df.drop_duplicates("customer_id").set_index("customer_id")["signup_date"].to_dict()
        order_signups = self.orders_df["customer_id"].map(cust_signup)
        violations = (self.orders_df["order_date"] < order_signups).sum()
        self.assertEqual(violations, 0, "Found orders placed prior to customer signup date")

    def test_anomalies_present_for_phase2_etl(self):
        """Verify intentional data anomalies exist for the ETL cleaning phase."""
        # 1. Duplicates in customers
        self.assertGreater(self.customers_df.duplicated().sum(), 0)
        # 2. Nulls in customers
        self.assertGreater(self.customers_df["age"].isnull().sum(), 0)
        self.assertGreater(self.customers_df["gender"].isnull().sum(), 0)
        # 3. Invalid quantities in orders
        self.assertGreater((self.orders_df["quantity"] < 0).sum(), 0)
        self.assertGreater((self.orders_df["quantity"] == 0).sum(), 0)


if __name__ == "__main__":
    unittest.main()
