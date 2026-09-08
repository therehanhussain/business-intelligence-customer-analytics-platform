"""Time-Aware Machine Learning Churn Prediction Pipeline.

Enforces strict Out-Of-Time (OOT) temporal validation to guarantee zero data leakage:
- Train Cutoff: 2023-12-31 | Outcome: 2024-01-01 to 2024-03-31 (90 days)
- Test Cutoff:  2024-03-31 | Outcome: 2024-04-01 to 2024-06-30 (90 days)
- Scaling fitted exclusively on training features.
- Primary interpretable model: Logistic Regression (standardized coefficients).
- Secondary comparator: Random Forest.
"""

from datetime import datetime
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.preprocessing import StandardScaler

from src.config.paths import PROCESSED_DATA_DIR
from src.modeling.features import build_time_aware_churn_dataset
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Core feature set strictly available on or before cutoff
MODEL_FEATURE_COLS = [
    "recency_days",
    "completed_orders",
    "total_revenue",
    "total_profit",
    "average_order_value",
    "active_months",
    "refund_rate",
    "cancellation_rate",
    "recent_revenue_ratio",
    "recent_order_ratio",
    "revenue_trend",
    "customer_lifetime_days",
    "account_age_days",
    "order_frequency_monthly",
]


class TimeAwareChurnPipeline:
    """Manages OOT training, evaluation, interpretability, and scoring."""

    def __init__(
        self,
        train_cutoff: str = "2023-12-31",
        train_outcome_start: str = "2024-01-01",
        train_outcome_end: str = "2024-03-31",
        test_cutoff: str = "2024-03-31",
        test_outcome_start: str = "2024-04-01",
        test_outcome_end: str = "2024-06-30",
        artifacts_dir: Path = PROCESSED_DATA_DIR / "models",
    ):
        self.train_cutoff = train_cutoff
        self.train_outcome_start = train_outcome_start
        self.train_outcome_end = train_outcome_end
        self.test_cutoff = test_cutoff
        self.test_outcome_start = test_outcome_start
        self.test_outcome_end = test_outcome_end
        self.artifacts_dir = artifacts_dir
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)

        self.scaler = StandardScaler()
        self.logreg_model = LogisticRegression(
            random_state=42,
            max_iter=1000,
            class_weight="balanced",
        )
        self.rf_model = RandomForestClassifier(
            random_state=42,
            n_estimators=100,
            max_depth=5,
            min_samples_leaf=10,
            class_weight="balanced",
        )
        self.feature_cols = MODEL_FEATURE_COLS

    def prepare_datasets(
        self,
        orders_df: pd.DataFrame,
        customers_df: pd.DataFrame,
        products_df: pd.DataFrame,
    ) -> Tuple[pd.DataFrame, pd.Series, pd.DataFrame, pd.Series, Dict[str, Any]]:
        """Construct Out-of-Time train and test datasets strictly observing temporal cutoffs."""
        logger.info("Preparing Out-Of-Time train dataset...")
        train_feat_df, y_train, train_meta = build_time_aware_churn_dataset(
            orders_df=orders_df,
            customers_df=customers_df,
            products_df=products_df,
            feature_cutoff=self.train_cutoff,
            outcome_start=self.train_outcome_start,
            outcome_end=self.train_outcome_end,
        )

        logger.info("Preparing Out-Of-Time test dataset...")
        test_feat_df, y_test, test_meta = build_time_aware_churn_dataset(
            orders_df=orders_df,
            customers_df=customers_df,
            products_df=products_df,
            feature_cutoff=self.test_cutoff,
            outcome_start=self.test_outcome_start,
            outcome_end=self.test_outcome_end,
        )

        X_train = train_feat_df[self.feature_cols].copy()
        X_test = test_feat_df[self.feature_cols].copy()

        metadata = {
            "train": train_meta,
            "test": test_meta,
            "feature_columns": self.feature_cols,
        }
        return X_train, y_train, X_test, y_test, metadata

    def train_and_evaluate(
        self,
        X_train: pd.DataFrame,
        y_train: pd.Series,
        X_test: pd.DataFrame,
        y_test: pd.Series,
    ) -> Dict[str, Any]:
        """Fit scaler on train only, train models, and compute evaluation metrics on OOT test data."""
        logger.info("Fitting StandardScaler strictly on training set...")
        X_train_scaled = self.scaler.fit_transform(X_train)
        X_test_scaled = self.scaler.transform(X_test)

        # 1. Train Logistic Regression
        logger.info("Training primary Logistic Regression model...")
        self.logreg_model.fit(X_train_scaled, y_train)

        # 2. Train Random Forest (fitted on unscaled for pure tree splitting)
        logger.info("Training secondary Random Forest model...")
        self.rf_model.fit(X_train, y_train)

        # 3. Evaluate Logistic Regression on Test Set
        lr_probs = self.logreg_model.predict_proba(X_test_scaled)[:, 1]
        lr_preds = (lr_probs >= 0.50).astype(int)

        lr_metrics = self._calculate_metrics(y_test, lr_preds, lr_probs)
        lr_thresholds = self._evaluate_threshold_tradeoffs(y_test, lr_probs)

        # Feature Importance (Standardized Coefficients)
        coef_series = pd.Series(
            self.logreg_model.coef_[0],
            index=self.feature_cols,
        ).sort_values(ascending=False)
        lr_coefficients = coef_series.to_dict()

        # 4. Evaluate Random Forest on Test Set
        rf_probs = self.rf_model.predict_proba(X_test)[:, 1]
        rf_preds = (rf_probs >= 0.50).astype(int)
        rf_metrics = self._calculate_metrics(y_test, rf_preds, rf_probs)

        rf_importances = pd.Series(
            self.rf_model.feature_importances_,
            index=self.feature_cols,
        ).sort_values(ascending=False).to_dict()

        evaluation_results = {
            "logistic_regression": {
                "metrics": lr_metrics,
                "coefficients": lr_coefficients,
                "threshold_tradeoffs": lr_thresholds,
            },
            "random_forest": {
                "metrics": rf_metrics,
                "feature_importances": rf_importances,
            },
        }

        # 5. Persist Model Artifacts
        self._save_artifacts(evaluation_results)
        return evaluation_results

    def _calculate_metrics(
        self, y_true: pd.Series, y_pred: np.ndarray, y_prob: np.ndarray
    ) -> Dict[str, Any]:
        """Compute standard binary classification performance metrics."""
        cm = confusion_matrix(y_true, y_pred)
        tn, fp, fn, tp = cm.ravel()

        return {
            "roc_auc": round(float(roc_auc_score(y_true, y_prob)), 4),
            "accuracy": round(float(accuracy_score(y_true, y_pred)), 4),
            "precision": round(float(precision_score(y_true, y_pred, zero_division=0)), 4),
            "recall": round(float(recall_score(y_true, y_pred, zero_division=0)), 4),
            "f1": round(float(f1_score(y_true, y_pred, zero_division=0)), 4),
            "confusion_matrix": {
                "true_negative": int(tn),
                "false_positive": int(fp),
                "false_negative": int(fn),
                "true_positive": int(tp),
            },
        }

    def _evaluate_threshold_tradeoffs(
        self, y_true: pd.Series, y_prob: np.ndarray
    ) -> List[Dict[str, Any]]:
        """Evaluate precision, recall, and false alert rate across different decision thresholds."""
        thresholds = [0.30, 0.40, 0.50, 0.60, 0.70]
        results = []
        for t in thresholds:
            preds = (y_prob >= t).astype(int)
            cm = confusion_matrix(y_true, preds)
            tn, fp, fn, tp = cm.ravel()
            results.append({
                "threshold": t,
                "precision": round(float(precision_score(y_true, preds, zero_division=0)), 4),
                "recall": round(float(recall_score(y_true, preds, zero_division=0)), 4),
                "f1": round(float(f1_score(y_true, preds, zero_division=0)), 4),
                "targeted_count": int(preds.sum()),
                "false_alarms": int(fp),
            })
        return results

    def _save_artifacts(self, results: Dict[str, Any]) -> None:
        """Persist serialized models and evaluation metrics to disk."""
        lr_path = self.artifacts_dir / "logistic_regression.joblib"
        scaler_path = self.artifacts_dir / "scaler.joblib"
        rf_path = self.artifacts_dir / "random_forest.joblib"
        metrics_path = self.artifacts_dir / "model_metrics.json"

        joblib.dump(self.logreg_model, lr_path)
        joblib.dump(self.scaler, scaler_path)
        joblib.dump(self.rf_model, rf_path)

        with open(metrics_path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)

        logger.info("Saved modeling artifacts to %s", self.artifacts_dir)

    def predict_current_probabilities(self, features_df: pd.DataFrame) -> pd.Series:
        """Score full customer population to estimate forward 90-day churn probability."""
        X = features_df[self.feature_cols].copy()
        X_scaled = self.scaler.transform(X)
        probs = self.logreg_model.predict_proba(X_scaled)[:, 1]
        return pd.Series(probs, index=features_df.index, name="churn_probability").round(4)
