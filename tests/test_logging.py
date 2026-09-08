"""Tests for centralized logger functionality."""

import logging
from pathlib import Path
import tempfile
import unittest

from src.utils.logger import get_logger, setup_logger


class TestLogging(unittest.TestCase):
    """Test suite for logging configuration and behavior."""

    def test_get_logger_instance(self):
        """Verify that get_logger returns a properly configured Logger instance."""
        logger = get_logger("test_module")
        self.assertIsInstance(logger, logging.Logger)
        self.assertEqual(logger.name, "test_module")
        self.assertGreater(len(logger.handlers), 0)

    def test_logger_file_handler_creation(self):
        """Verify that file handler writes log output when enabled."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_log_file = Path(tmpdir) / "test_run.log"
            logger = setup_logger(
                name="file_test_logger",
                log_level="DEBUG",
                log_to_file=True,
                log_file_path=test_log_file,
            )

            test_message = "Phase 0 basic check verification log"
            logger.info(test_message)

            # Flush handlers to ensure file write
            for handler in logger.handlers:
                handler.flush()

            self.assertTrue(test_log_file.exists())
            content = test_log_file.read_text(encoding="utf-8")
            self.assertIn(test_message, content)

            # Explicitly close and detach handlers so Windows can release file lock
            for handler in list(logger.handlers):
                handler.close()
                logger.removeHandler(handler)


if __name__ == "__main__":
    unittest.main()
