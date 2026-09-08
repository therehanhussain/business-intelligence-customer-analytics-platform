"""Tests for path resolution and configuration loading."""

import unittest
from pathlib import Path

from src.config.paths import (
    ANALYTICS_DIR,
    CONFIG_DIR,
    DASHBOARD_DIR,
    DATA_DIR,
    DOCS_DIR,
    ETL_DIR,
    LOGS_DIR,
    MODELING_DIR,
    NOTEBOOKS_DIR,
    PROCESSED_DATA_DIR,
    PROJECT_ROOT,
    RAW_DATA_DIR,
    SQL_DIR,
    SRC_DIR,
    TESTS_DIR,
    ensure_directories,
)
from src.config.settings import AppConfig, DatabaseConfig, load_config, settings


class TestConfig(unittest.TestCase):
    """Test suite for paths and configuration."""

    def test_project_paths_exist(self):
        """Verify that core directory paths resolve and exist."""
        ensure_directories()

        self.assertTrue(PROJECT_ROOT.is_dir())
        self.assertTrue(SRC_DIR.is_dir())
        self.assertTrue(CONFIG_DIR.is_dir())
        self.assertTrue(ETL_DIR.is_dir())
        self.assertTrue(ANALYTICS_DIR.is_dir())
        self.assertTrue(MODELING_DIR.is_dir())
        self.assertTrue(DATA_DIR.is_dir())
        self.assertTrue(RAW_DATA_DIR.is_dir())
        self.assertTrue(PROCESSED_DATA_DIR.is_dir())
        self.assertTrue(SQL_DIR.is_dir())
        self.assertTrue(TESTS_DIR.is_dir())
        self.assertTrue(NOTEBOOKS_DIR.is_dir())
        self.assertTrue(DASHBOARD_DIR.is_dir())
        self.assertTrue(DOCS_DIR.is_dir())

    def test_settings_defaults(self):
        """Verify that default settings instantiate with expected properties."""
        self.assertIsInstance(settings, AppConfig)
        self.assertEqual(settings.project_name, "customer-analytics-platform")
        self.assertEqual(settings.random_seed, 42)
        self.assertIsInstance(settings.database, DatabaseConfig)
        self.assertEqual(settings.database.port, 5432)
        self.assertIn(settings.logging.level, ["DEBUG", "INFO", "WARNING", "ERROR"])

    def test_database_connection_url_masking(self):
        """Verify that sensitive database credentials can be properly masked."""
        db_cfg = DatabaseConfig(
            host="localhost",
            port=5432,
            name="test_db",
            user="test_user",
            password="super_secret_password",
        )
        url_masked = db_cfg.get_connection_url(masked=True)
        self.assertNotIn("super_secret_password", url_masked)
        self.assertIn("********", url_masked)

        url_unmasked = db_cfg.get_connection_url(masked=False)
        self.assertIn("super_secret_password", url_unmasked)


if __name__ == "__main__":
    unittest.main()
