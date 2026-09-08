-- =============================================================================
-- Customer Analytics Platform — Data Quality & Governance Analytics
-- Standard: ANSI SQL (Compatible with PostgreSQL and SQLite 3.35+)
-- =============================================================================

-- -----------------------------------------------------------------------------
-- QUERY 1: Pipeline Overall Throughput & Quality Health
-- Business Question: What was the overall ingestion pass rate and quarantine rate?
-- -----------------------------------------------------------------------------
WITH entity_counts AS (
    SELECT 'customers' AS table_name, COUNT(1) AS valid_count FROM customers
    UNION ALL
    SELECT 'products' AS table_name, COUNT(1) AS valid_count FROM products
    UNION ALL
    SELECT 'orders' AS table_name, COUNT(1) AS valid_count FROM orders
),
rejection_counts AS (
    SELECT 
        table_name, 
        COUNT(1) AS rejected_count 
    FROM rejected_records 
    GROUP BY table_name
)
SELECT
    e.table_name,
    e.valid_count,
    COALESCE(r.rejected_count, 0)                                   AS quarantined_in_dlq,
    (e.valid_count + COALESCE(r.rejected_count, 0))                 AS total_extracted_records,
    ROUND(
        e.valid_count * 100.0 / (e.valid_count + COALESCE(r.rejected_count, 0)), 
        2
    )                                                               AS data_quality_pass_rate_pct,
    ROUND(
        COALESCE(r.rejected_count, 0) * 100.0 / (e.valid_count + COALESCE(r.rejected_count, 0)), 
        2
    )                                                               AS rejection_quarantine_rate_pct
FROM entity_counts e
LEFT JOIN rejection_counts r ON e.table_name = r.table_name;


-- -----------------------------------------------------------------------------
-- QUERY 2: Dead-Letter Queue (DLQ) Root Cause Breakdown
-- Business Question: What specific data defects caused records to be quarantined?
-- -----------------------------------------------------------------------------
SELECT
    table_name,
    rejection_reason,
    COUNT(1)                                                        AS quarantined_record_count,
    ROUND(COUNT(1) * 100.0 / SUM(COUNT(1)) OVER(), 2)               AS pct_of_total_dlq,
    MIN(rejected_at)                                                AS first_rejection_timestamp,
    MAX(rejected_at)                                                AS last_rejection_timestamp
FROM rejected_records
GROUP BY table_name, rejection_reason
ORDER BY quarantined_record_count DESC;


-- -----------------------------------------------------------------------------
-- QUERY 3: Pipeline Audit Orchestration Log
-- Business Question: What were the macro execution results logged by the pipeline?
-- -----------------------------------------------------------------------------
SELECT
    pipeline_run_id,
    run_timestamp,
    database_type,
    total_extracted,
    total_valid,
    total_rejected,
    pass_rate_pct
FROM pipeline_audit_log
ORDER BY run_timestamp DESC;
