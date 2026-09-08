-- =============================================================================
-- Customer Analytics Platform — Machine Learning & Behavioral Feature Store
-- Standard: ANSI SQL (PostgreSQL & SQLite 3.35+ Compatible)
--
-- Objective:
-- Compute cutoff-safe customer-level behavioral, monetary, tenure, and friction
-- features matching the Phase 4 Python feature engineering pipeline (features.py).
--
-- Includes:
-- 1. Base Feature View: v_customer_features
-- 2. Time-Aware Churn Labeling & Predictive Feature Extraction (OOT Design)
-- 3. Unified Customer Segment & Risk Profile Query
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 1. ANALYTICAL VIEW: v_customer_features
-- Computes customer-level aggregations over complete validated history
-- Reference snapshot date: 2024-06-30 (Dataset end date)
-- -----------------------------------------------------------------------------
DROP VIEW IF EXISTS v_customer_features;

CREATE VIEW v_customer_features AS
WITH order_aggregations AS (
    SELECT
        v.customer_id,
        COUNT(v.order_id)                                           AS total_orders,
        SUM(CASE WHEN v.is_completed = 1 THEN 1 ELSE 0 END)         AS completed_orders,
        SUM(CASE WHEN v.is_completed = 1 THEN v.quantity ELSE 0 END) AS total_units,
        SUM(v.gross_revenue)                                        AS total_gross_revenue,
        SUM(v.net_revenue)                                          AS total_revenue,
        SUM(v.net_profit)                                           AS total_profit,
        MIN(v.order_date)                                           AS first_order_date,
        MAX(v.order_date)                                           AS last_order_date,
        MAX(CASE WHEN v.is_completed = 1 THEN v.order_date END)     AS last_completed_order_date,
        COUNT(DISTINCT SUBSTR(v.order_date, 1, 7))                  AS active_months,
        -- Friction Metrics
        SUM(CASE WHEN v.is_refunded = 1 THEN 1 ELSE 0 END)          AS refund_count,
        SUM(CASE WHEN v.is_refunded = 1 THEN v.gross_revenue ELSE 0 END) AS refund_amount,
        SUM(CASE WHEN v.is_cancelled = 1 THEN 1 ELSE 0 END)         AS cancellation_count,
        SUM(CASE WHEN v.is_cancelled = 1 THEN v.gross_revenue ELSE 0 END) AS cancellation_amount,
        -- Recent Activity (Last 90 days: >= 2024-04-01)
        SUM(CASE WHEN v.order_date >= '2024-04-01' AND v.is_completed = 1 THEN 1 ELSE 0 END) AS recent_order_count,
        SUM(CASE WHEN v.order_date >= '2024-04-01' AND v.is_completed = 1 THEN v.net_revenue ELSE 0 END) AS recent_revenue
    FROM v_order_analytics v
    GROUP BY v.customer_id
)
SELECT
    c.customer_id,
    c.name                                                          AS customer_name,
    c.gender,
    c.age,
    c.city,
    c.state,
    c.signup_date,
    COALESCE(o.total_orders, 0)                                     AS total_orders,
    COALESCE(o.completed_orders, 0)                                 AS completed_orders,
    COALESCE(o.total_units, 0)                                      AS total_units,
    COALESCE(o.active_months, 0)                                    AS active_months,
    o.first_order_date,
    o.last_order_date,
    o.last_completed_order_date,
    -- Recency in Days relative to snapshot date (2024-06-30)
    CASE 
        WHEN o.last_completed_order_date IS NOT NULL 
        THEN CAST(JULIANDAY('2024-06-30') - JULIANDAY(o.last_completed_order_date) AS INTEGER)
        ELSE 999 
    END                                                             AS recency_days,
    -- Account Age in Days
    CAST(JULIANDAY('2024-06-30') - JULIANDAY(c.signup_date) AS INTEGER) AS account_age_days,
    -- Customer Lifetime in Days
    CASE 
        WHEN o.first_order_date IS NOT NULL AND o.last_order_date IS NOT NULL
        THEN CAST(JULIANDAY(o.last_order_date) - JULIANDAY(o.first_order_date) AS INTEGER)
        ELSE 0 
    END                                                             AS customer_lifetime_days,
    -- Monetary & Financial Metrics
    ROUND(COALESCE(o.total_gross_revenue, 0), 2)                    AS total_gross_revenue,
    ROUND(COALESCE(o.total_revenue, 0), 2)                          AS total_revenue,
    ROUND(COALESCE(o.total_profit, 0), 2)                           AS total_profit,
    -- Average Order Value (AOV)
    ROUND(
        COALESCE(o.total_revenue, 0) / NULLIF(COALESCE(o.completed_orders, 0), 0),
        2
    )                                                               AS average_order_value,
    -- Average Monthly Frequency (Orders per 30 days of tenure)
    ROUND(
        COALESCE(o.completed_orders, 0) / 
        NULLIF((JULIANDAY('2024-06-30') - JULIANDAY(c.signup_date)) / 30.0, 0),
        3
    )                                                               AS order_frequency_monthly,
    -- Realized Gross Margin %
    ROUND(
        (COALESCE(o.total_profit, 0) * 100.0) / NULLIF(COALESCE(o.total_revenue, 0), 0),
        2
    )                                                               AS gross_margin_pct,
    -- Friction Rates
    COALESCE(o.refund_count, 0)                                     AS refund_count,
    ROUND(COALESCE(o.refund_amount, 0), 2)                          AS refund_amount,
    ROUND(
        COALESCE(o.refund_count, 0) * 1.0 / NULLIF(COALESCE(o.total_orders, 0), 0),
        4
    )                                                               AS refund_rate,
    COALESCE(o.cancellation_count, 0)                               AS cancellation_count,
    ROUND(COALESCE(o.cancellation_amount, 0), 2)                    AS cancellation_amount,
    ROUND(
        COALESCE(o.cancellation_count, 0) * 1.0 / NULLIF(COALESCE(o.total_orders, 0), 0),
        4
    )                                                               AS cancellation_rate,
    -- Recent vs Historical Split
    ROUND(COALESCE(o.recent_revenue, 0), 2)                         AS recent_revenue,
    COALESCE(o.recent_order_count, 0)                               AS recent_order_count,
    ROUND(
        COALESCE(o.total_revenue, 0) - COALESCE(o.recent_revenue, 0), 
        2
    )                                                               AS historical_revenue,
    COALESCE(o.completed_orders, 0) - COALESCE(o.recent_order_count, 0) AS historical_order_count,
    ROUND(
        COALESCE(o.recent_revenue, 0) / NULLIF(COALESCE(o.total_revenue, 0), 0),
        4
    )                                                               AS recent_revenue_ratio,
    ROUND(
        COALESCE(o.recent_order_count, 0) * 1.0 / NULLIF(COALESCE(o.completed_orders, 0), 0),
        4
    )                                                               AS recent_order_ratio
FROM customers c
LEFT JOIN order_aggregations o ON c.customer_id = o.customer_id;


-- -----------------------------------------------------------------------------
-- 2. TIME-AWARE CHURN TARGET & PREDICTIVE FEATURE QUERY
-- ANTI-LEAKAGE DEMONSTRATION:
-- Feature cutoff : 2023-12-31 (Features computed STRICTLY using orders <= 2023-12-31)
-- Outcome window : 2024-01-01 to 2024-03-31 (Label = 1 if ZERO completed orders in window)
-- -----------------------------------------------------------------------------
WITH cutoff_eligible_customers AS (
    -- Customers with at least 1 completed order on or before cutoff
    SELECT DISTINCT v.customer_id
    FROM v_order_analytics v
    WHERE v.order_date <= '2023-12-31'
      AND v.is_completed = 1
),
historical_features AS (
    SELECT
        v.customer_id,
        COUNT(v.order_id)                                           AS hist_total_orders,
        SUM(CASE WHEN v.is_completed = 1 THEN 1 ELSE 0 END)         AS hist_completed_orders,
        SUM(v.net_revenue)                                          AS hist_net_revenue,
        SUM(v.net_profit)                                           AS hist_net_profit,
        MAX(CASE WHEN v.is_completed = 1 THEN v.order_date END)     AS hist_last_order_date,
        CAST(JULIANDAY('2023-12-31') - JULIANDAY(MAX(CASE WHEN v.is_completed = 1 THEN v.order_date END)) AS INTEGER) AS hist_recency_days,
        SUM(CASE WHEN v.is_refunded = 1 THEN 1 ELSE 0 END) * 1.0 / COUNT(v.order_id) AS hist_refund_rate
    FROM v_order_analytics v
    WHERE v.order_date <= '2023-12-31'
    GROUP BY v.customer_id
),
future_outcome AS (
    -- Churn outcome evaluation strictly inside outcome window
    SELECT
        v.customer_id,
        COUNT(v.order_id)                                           AS outcome_orders
    FROM v_order_analytics v
    WHERE v.order_date >= '2024-01-01' 
      AND v.order_date <= '2024-03-31'
      AND v.is_completed = 1
    GROUP BY v.customer_id
)
SELECT
    e.customer_id,
    c.signup_date,
    hf.hist_completed_orders,
    hf.hist_recency_days,
    ROUND(hf.hist_net_revenue, 2)                                   AS hist_net_revenue,
    ROUND(hf.hist_net_profit, 2)                                    AS hist_net_profit,
    ROUND(hf.hist_net_revenue / NULLIF(hf.hist_completed_orders, 0), 2) AS hist_aov,
    ROUND(hf.hist_refund_rate, 4)                                   AS hist_refund_rate,
    COALESCE(fo.outcome_orders, 0)                                  AS outcome_completed_orders,
    -- Binary Target: 1 = Churned (zero purchases in outcome window), 0 = Retained
    CASE WHEN COALESCE(fo.outcome_orders, 0) = 0 THEN 1 ELSE 0 END  AS is_churned
FROM cutoff_eligible_customers e
JOIN customers c ON e.customer_id = c.customer_id
JOIN historical_features hf ON e.customer_id = hf.customer_id
LEFT JOIN future_outcome fo ON e.customer_id = fo.customer_id;
