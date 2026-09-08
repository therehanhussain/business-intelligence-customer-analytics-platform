"""End-to-End ETL Pipeline Orchestrator.

Coordinates the complete extraction, transformation, validation (DLQ segregation),
and loading workflow for the Customer Analytics Platform.
"""

from datetime import datetime, timezone
import json
import time
from typing import Any, Dict
import uuid

from src.etl.extract import extract_all_raw_data
from src.etl.load import load_to_database, save_processed_files
from src.etl.transform import transform_all_data
from src.etl.validate import validate_all_data
from src.utils.logger import get_logger

logger = get_logger(__name__)


def run_pipeline() -> Dict[str, Any]:
    """Execute the end-to-end ETL pipeline and return comprehensive audit report."""
    run_id = f"RUN_{uuid.uuid4().hex[:8].upper()}"
    start_time = time.time()
    start_iso = datetime.now(timezone.utc).isoformat()

    logger.info("================================================================================")
    logger.info("STARTING ENTERPRISE ETL PIPELINE [Run ID: %s]", run_id)
    logger.info("================================================================================")

    # 1. EXTRACT (E)
    logger.info(">> STEP 1: EXTRACTION")
    cust_raw, prod_raw, ord_raw, extract_meta = extract_all_raw_data()

    # 2. TRANSFORM (T)
    logger.info(">> STEP 2: TRANSFORMATION")
    cust_tf, prod_tf, ord_tf, transform_meta = transform_all_data(cust_raw, prod_raw, ord_raw)

    # 3. VALIDATE & QUARANTINE (V)
    logger.info(">> STEP 3: VALIDATION & DEAD-LETTER QUEUE (DLQ)")
    valid_cust, valid_prod, valid_ord, rejected_df, val_summary = validate_all_data(
        cust_tf, prod_tf, ord_tf
    )

    # Compile validation metrics
    total_extracted = len(cust_raw) + len(prod_raw) + len(ord_raw)
    total_valid = len(valid_cust) + len(valid_prod) + len(valid_ord)
    total_rejected = len(rejected_df)
    overall_pass_rate = round((total_valid / total_extracted) * 100, 2)

    # 4. AUDIT COMPILATION
    duration_sec = round(time.time() - start_time, 2)
    audit_summary = {
        "pipeline_run_id": run_id,
        "run_timestamp": start_iso,
        "duration_seconds": duration_sec,
        "extraction": {
            "total_extracted": total_extracted,
            "counts": extract_meta["source_counts"],
        },
        "transformation": transform_meta,
        "validation": {
            "total_valid": total_valid,
            "total_rejected": total_rejected,
            "overall_pass_rate_pct": overall_pass_rate,
            "tables": {
                "customers": val_summary["customers"],
                "products": val_summary["products"],
                "orders": val_summary["orders"],
            },
            "dead_letter_queue_breakdown": val_summary["consolidated_reasons"],
        },
    }

    # 5. LOAD (L)
    logger.info(">> STEP 4: LOADING & PERSISTENCE")
    file_paths = save_processed_files(
        valid_cust, valid_prod, valid_ord, rejected_df, audit_summary
    )
    db_load_meta = load_to_database(
        valid_cust, valid_prod, valid_ord, rejected_df, audit_summary
    )

    audit_summary["loading"] = {
        "file_artifacts": {k: str(v) for k, v in file_paths.items()},
        "database": db_load_meta,
    }

    # Update the audit summary JSON file on disk with loading metadata
    with open(file_paths["audit_summary"], "w", encoding="utf-8") as f:
        json.dump(audit_summary, f, indent=2, default=str)

    logger.info("================================================================================")
    logger.info("ETL PIPELINE EXECUTION FINISHED IN %.2f SECONDS", duration_sec)
    logger.info("================================================================================")

    # 6. PRINT EXECUTIVE SCORECARD
    print_pipeline_scorecard(audit_summary)

    return audit_summary


def print_pipeline_scorecard(audit: Dict[str, Any]) -> None:
    """Print executive scorecard detailing pipeline audit metrics."""
    val = audit["validation"]
    cust_val = val["tables"]["customers"]
    prod_val = val["tables"]["products"]
    ord_val = val["tables"]["orders"]
    db = audit["loading"]["database"]

    print("\n" + "=" * 82)
    print(f"ETL PIPELINE SCORECARD — RUN ID: {audit['pipeline_run_id']}")
    print(f"Timestamp: {audit['run_timestamp']} | Duration: {audit['duration_seconds']}s")
    print("=" * 82)

    print("\n[1] DATASET QUALITY & THROUGHPUT AUDIT")
    print(f"{'Table':<14} | {'Extracted':>10} | {'Valid (Loaded)':>15} | {'Rejected (DLQ)':>15} | {'Pass Rate':>10}")
    print("-" * 82)
    print(f"{'Customers':<14} | {cust_val['total_input']:>10,d} | {cust_val['valid_count']:>15,d} | {cust_val['rejected_count']:>15,d} | {cust_val['pass_rate_pct']:>9.2f}%")
    print(f"{'Products':<14} | {prod_val['total_input']:>10,d} | {prod_val['valid_count']:>15,d} | {prod_val['rejected_count']:>15,d} | {prod_val['pass_rate_pct']:>9.2f}%")
    print(f"{'Orders':<14} | {ord_val['total_input']:>10,d} | {ord_val['valid_count']:>15,d} | {ord_val['rejected_count']:>15,d} | {ord_val['pass_rate_pct']:>9.2f}%")
    print("-" * 82)
    print(f"{'TOTAL':<14} | {audit['extraction']['total_extracted']:>10,d} | {val['total_valid']:>15,d} | {val['total_rejected']:>15,d} | {val['overall_pass_rate_pct']:>9.2f}%")

    print("\n[2] DEAD-LETTER QUEUE (DLQ) REJECTION ROOT CAUSES")
    print("-" * 82)
    for reason, count in val["dead_letter_queue_breakdown"].items():
        pct = (count / val["total_rejected"]) * 100
        print(f"  * {reason:<38} : {count:>6,d} records ({pct:>5.1f}%)")

    print("\n[3] TRANSFORMATION & ENRICHMENT AUDIT")
    print("-" * 82)
    print(f"  * Customers Missing Ages Imputed      : {audit['transformation']['customers']['ages_imputed']:,d} (Median: {audit['transformation']['customers']['median_imputed_age']:.1f} yrs)")
    print(f"  * Customers Unknown Genders Handled   : {audit['transformation']['customers']['unknown_genders']:,d}")
    print(f"  * Products Average Derived Margin     : {audit['transformation']['products']['average_margin_pct']:.2f}%")
    print(f"  * Orders Missing Payment Imputed      : {audit['transformation']['orders']['unknown_payment_methods']:,d}")

    print("\n[4] PERSISTENCE & STORAGE SINK")
    print("-" * 82)
    print(f"  * Relational Target Engine            : {db['database_type']}")
    for tbl, cnt in db["tables_loaded"].items():
        print(f"    - Table '{tbl:<20}' : {cnt:>8,d} rows loaded")
    print(f"  * Processed File Artifacts Directory  : {audit['loading']['file_artifacts']['customers']}")
    print("=" * 82 + "\n")


if __name__ == "__main__":
    run_pipeline()
