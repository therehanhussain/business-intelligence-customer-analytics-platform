-- =============================================================================
-- Customer Analytics Platform — Sales Performance & Revenue Dynamics
-- Standard: ANSI SQL (Compatible with PostgreSQL and SQLite 3.35+)
-- =============================================================================

-- -----------------------------------------------------------------------------
-- QUERY 1: Executive Sales & Profitability Scorecard
-- Business Question: What are our macro commercial results across gross revenue,
--                    net revenue, refunds, cancellations, and net profit?
-- -----------------------------------------------------------------------------
SELECT
    COUNT(order_id)                                                 AS total_order_volume,
    SUM(quantity)                                                   AS total_gross_units,
    SUM(is_completed)                                               AS completed_order_count,
    SUM(is_refunded)                                                AS refunded_order_count,
    SUM(is_cancelled)                                               AS cancelled_order_count,
    ROUND(SUM(is_completed) * 100.0 / COUNT(order_id), 2)           AS fulfillment_rate_pct,
    ROUND(SUM(is_refunded) * 100.0 / COUNT(order_id), 2)            AS refund_rate_pct,
    ROUND(SUM(is_cancelled) * 100.0 / COUNT(order_id), 2)           AS cancellation_rate_pct,
    ROUND(SUM(gross_revenue), 2)                                    AS total_gross_invoiced_revenue,
    ROUND(SUM(refunded_amount), 2)                                  AS total_refunded_amount,
    ROUND(SUM(cancelled_amount), 2)                                 AS total_cancelled_amount,
    ROUND(SUM(net_revenue), 2)                                      AS total_net_realized_revenue,
    ROUND(SUM(CASE WHEN is_completed = 1 THEN total_cost ELSE 0 END), 2) AS total_realized_cogs,
    ROUND(SUM(net_profit), 2)                                       AS total_net_profit,
    ROUND((SUM(net_profit) / NULLIF(SUM(net_revenue), 0)) * 100.0, 2) AS realized_gross_margin_pct,
    ROUND(SUM(net_revenue) / NULLIF(SUM(is_completed), 0), 2)       AS average_order_value_aov
FROM v_order_analytics;


-- -----------------------------------------------------------------------------
-- QUERY 2: Monthly Revenue, Volume & MoM Growth Dynamics
-- Business Question: How do sales and margins evolve month-over-month, and what
--                    seasonal patterns exist?
-- -----------------------------------------------------------------------------
WITH monthly_metrics AS (
    SELECT
        order_month,
        COUNT(order_id)                                             AS total_orders,
        SUM(is_completed)                                           AS completed_orders,
        SUM(CASE WHEN is_completed = 1 THEN quantity ELSE 0 END)    AS completed_units,
        ROUND(SUM(net_revenue), 2)                                  AS monthly_net_revenue,
        ROUND(SUM(net_profit), 2)                                   AS monthly_net_profit,
        ROUND((SUM(net_profit) / NULLIF(SUM(net_revenue), 0)) * 100.0, 2) AS monthly_margin_pct,
        ROUND(SUM(net_revenue) / NULLIF(SUM(is_completed), 0), 2)   AS monthly_aov
    FROM v_order_analytics
    GROUP BY order_month
)
SELECT
    order_month,
    completed_orders,
    completed_units,
    monthly_net_revenue,
    monthly_net_profit,
    monthly_margin_pct,
    monthly_aov,
    LAG(monthly_net_revenue, 1) OVER (ORDER BY order_month)         AS prev_month_net_revenue,
    ROUND(
        (monthly_net_revenue - LAG(monthly_net_revenue, 1) OVER (ORDER BY order_month)) * 100.0 
        / NULLIF(LAG(monthly_net_revenue, 1) OVER (ORDER BY order_month), 0),
        2
    )                                                               AS mom_revenue_growth_pct,
    ROUND(
        SUM(monthly_net_revenue) OVER (ORDER BY order_month ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW),
        2
    )                                                               AS cumulative_run_rate_revenue
FROM monthly_metrics
ORDER BY order_month ASC;


-- -----------------------------------------------------------------------------
-- QUERY 3: Annual Sales Performance & YoY Trajectory
-- Business Question: What is our annual revenue, profit growth, and margin trend?
-- -----------------------------------------------------------------------------
WITH annual_metrics AS (
    SELECT
        order_year,
        SUM(is_completed)                                           AS completed_orders,
        SUM(CASE WHEN is_completed = 1 THEN quantity ELSE 0 END)    AS completed_units,
        ROUND(SUM(net_revenue), 2)                                  AS annual_net_revenue,
        ROUND(SUM(net_profit), 2)                                   AS annual_net_profit,
        ROUND((SUM(net_profit) / NULLIF(SUM(net_revenue), 0)) * 100.0, 2) AS annual_margin_pct,
        ROUND(SUM(net_revenue) / NULLIF(SUM(is_completed), 0), 2)   AS annual_aov
    FROM v_order_analytics
    GROUP BY order_year
)
SELECT
    order_year,
    completed_orders,
    completed_units,
    annual_net_revenue,
    annual_net_profit,
    annual_margin_pct,
    annual_aov,
    LAG(annual_net_revenue, 1) OVER (ORDER BY order_year)           AS prev_year_revenue,
    ROUND(
        (annual_net_revenue - LAG(annual_net_revenue, 1) OVER (ORDER BY order_year)) * 100.0 
        / NULLIF(LAG(annual_net_revenue, 1) OVER (ORDER BY order_year), 0),
        2
    )                                                               AS yoy_revenue_growth_pct
FROM annual_metrics
ORDER BY order_year ASC;


-- -----------------------------------------------------------------------------
-- QUERY 4: Order Status & Commercial Funnel Breakdown
-- Business Question: How does revenue break down across order statuses?
-- -----------------------------------------------------------------------------
SELECT
    order_status,
    COUNT(order_id)                                                 AS order_count,
    ROUND(COUNT(order_id) * 100.0 / SUM(COUNT(order_id)) OVER(), 2) AS pct_of_total_orders,
    SUM(quantity)                                                   AS total_quantity,
    ROUND(SUM(gross_revenue), 2)                                    AS total_invoiced_gross_revenue,
    ROUND(SUM(gross_revenue) * 100.0 / SUM(SUM(gross_revenue)) OVER(), 2) AS pct_of_total_revenue,
    ROUND(AVG(gross_revenue), 2)                                    AS avg_order_gross_value
FROM v_order_analytics
GROUP BY order_status
ORDER BY order_count DESC;


-- -----------------------------------------------------------------------------
-- QUERY 5: Payment Method Adoption & Revenue Share
-- Business Question: What tender types are driving sales and what is their AOV?
-- -----------------------------------------------------------------------------
SELECT
    payment_method,
    SUM(is_completed)                                               AS completed_transactions,
    ROUND(SUM(is_completed) * 100.0 / SUM(SUM(is_completed)) OVER(), 2) AS pct_of_transactions,
    ROUND(SUM(net_revenue), 2)                                      AS realized_revenue,
    ROUND(SUM(net_revenue) * 100.0 / SUM(SUM(net_revenue)) OVER(), 2) AS pct_of_realized_revenue,
    ROUND(SUM(net_revenue) / NULLIF(SUM(is_completed), 0), 2)       AS average_ticket_size
FROM v_order_analytics
GROUP BY payment_method
ORDER BY realized_revenue DESC;
