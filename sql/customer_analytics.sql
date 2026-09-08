-- =============================================================================
-- Customer Analytics Platform — Customer Intelligence & Behavior Queries
-- Standard: ANSI SQL (Compatible with PostgreSQL and SQLite 3.35+)
-- =============================================================================

-- -----------------------------------------------------------------------------
-- QUERY 1: Customer Base Lifecycle & Activity Summary
-- Business Question: What is the total size, activation rate, repeat purchase
--                    rate, and dormancy in our customer base?
-- -----------------------------------------------------------------------------
WITH customer_order_summary AS (
    SELECT
        c.customer_id,
        COUNT(v.order_id)                                           AS total_orders,
        SUM(CASE WHEN v.is_completed = 1 THEN 1 ELSE 0 END)         AS completed_orders,
        SUM(v.net_revenue)                                          AS total_net_revenue
    FROM customers c
    LEFT JOIN v_order_analytics v ON c.customer_id = v.customer_id
    GROUP BY c.customer_id
)
SELECT
    COUNT(1)                                                        AS total_customers,
    SUM(CASE WHEN total_orders > 0 THEN 1 ELSE 0 END)              AS active_customers_with_orders,
    SUM(CASE WHEN total_orders = 0 THEN 1 ELSE 0 END)              AS dormant_customers_zero_orders,
    ROUND(SUM(CASE WHEN total_orders = 0 THEN 1 ELSE 0 END) * 100.0 / COUNT(1), 2) AS zero_order_rate_pct,
    SUM(CASE WHEN completed_orders > 0 THEN 1 ELSE 0 END)          AS customers_with_completed_orders,
    SUM(CASE WHEN completed_orders = 1 THEN 1 ELSE 0 END)          AS one_time_buyers,
    SUM(CASE WHEN completed_orders >= 2 THEN 1 ELSE 0 END)         AS repeat_buyers,
    ROUND(
        SUM(CASE WHEN completed_orders >= 2 THEN 1 ELSE 0 END) * 100.0 / 
        NULLIF(SUM(CASE WHEN completed_orders > 0 THEN 1 ELSE 0 END), 0), 
        2
    )                                                               AS repeat_buyer_rate_pct,
    ROUND(SUM(total_net_revenue), 2)                                AS total_realized_revenue,
    ROUND(SUM(total_net_revenue) / NULLIF(SUM(CASE WHEN completed_orders > 0 THEN 1 ELSE 0 END), 0), 2) AS avg_revenue_per_paying_customer
FROM customer_order_summary;


-- -----------------------------------------------------------------------------
-- QUERY 2: Customer LTV & RFM Metrics Proxy
-- Business Question: What are the order frequencies, spend, gross profit,
--                    AOV, and recency distribution per customer?
-- -----------------------------------------------------------------------------
SELECT
    c.customer_id,
    c.name                                                          AS customer_name,
    c.gender                                                        AS customer_gender,
    c.city                                                          AS customer_city,
    c.state                                                         AS customer_state,
    c.signup_date,
    COUNT(v.order_id)                                               AS total_order_count,
    SUM(v.is_completed)                                             AS completed_order_count,
    ROUND(SUM(v.net_revenue), 2)                                    AS total_spend,
    ROUND(SUM(v.net_profit), 2)                                     AS total_profit,
    ROUND(SUM(v.net_revenue) / NULLIF(SUM(v.is_completed), 0), 2)   AS average_order_value,
    MIN(v.order_date)                                               AS first_order_date,
    MAX(v.order_date)                                               AS last_order_date,
    -- Recency relative to snapshot end-date (2024-06-30)
    ROUND(JULIANDAY('2024-06-30') - JULIANDAY(MAX(v.order_date)))  AS recency_days
FROM customers c
INNER JOIN v_order_analytics v ON c.customer_id = v.customer_id
WHERE v.is_completed = 1
GROUP BY c.customer_id, c.name, c.gender, c.city, c.state, c.signup_date
ORDER BY total_spend DESC
LIMIT 100;


-- -----------------------------------------------------------------------------
-- QUERY 3: Customer Revenue Concentration (Pareto Decile Analysis)
-- Business Question: How concentrated is total revenue across customer deciles?
--                    Does the top 10% or 20% generate the vast majority of revenue?
-- -----------------------------------------------------------------------------
WITH customer_spend AS (
    SELECT
        customer_id,
        ROUND(SUM(net_revenue), 2)                                  AS customer_revenue
    FROM v_order_analytics
    WHERE is_completed = 1
    GROUP BY customer_id
),
ranked_deciles AS (
    SELECT
        customer_id,
        customer_revenue,
        NTILE(10) OVER (ORDER BY customer_revenue DESC)             AS revenue_decile
    FROM customer_spend
),
decile_aggregation AS (
    SELECT
        revenue_decile,
        COUNT(customer_id)                                          AS customer_count,
        ROUND(SUM(customer_revenue), 2)                             AS decile_revenue,
        ROUND(MIN(customer_revenue), 2)                             AS min_spend_in_decile,
        ROUND(MAX(customer_revenue), 2)                             AS max_spend_in_decile
    FROM ranked_deciles
    GROUP BY revenue_decile
)
SELECT
    revenue_decile,
    customer_count,
    decile_revenue,
    min_spend_in_decile,
    max_spend_in_decile,
    ROUND(decile_revenue * 100.0 / SUM(decile_revenue) OVER(), 2)   AS pct_of_total_revenue,
    ROUND(
        SUM(decile_revenue) OVER (ORDER BY revenue_decile ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) 
        * 100.0 / SUM(decile_revenue) OVER(), 
        2
    )                                                               AS cumulative_revenue_pct
FROM decile_aggregation
ORDER BY revenue_decile ASC;


-- -----------------------------------------------------------------------------
-- QUERY 4: Top 20 Commercial Champions
-- Business Question: Who are our top 20 most valuable individual accounts?
-- -----------------------------------------------------------------------------
SELECT
    customer_id,
    customer_name,
    customer_city,
    customer_state,
    customer_signup_date,
    COUNT(order_id)                                                 AS completed_orders,
    ROUND(SUM(net_revenue), 2)                                      AS total_revenue,
    ROUND(SUM(net_profit), 2)                                       AS total_profit,
    ROUND((SUM(net_profit) / NULLIF(SUM(net_revenue), 0)) * 100.0, 2) AS realized_margin_pct,
    ROUND(SUM(net_revenue) / COUNT(order_id), 2)                     AS avg_order_value
FROM v_order_analytics
WHERE is_completed = 1
GROUP BY customer_id, customer_name, customer_city, customer_state, customer_signup_date
ORDER BY total_revenue DESC
LIMIT 20;


-- -----------------------------------------------------------------------------
-- QUERY 5: At-Risk & Dormant Customer Cohort
-- Business Question: Which customers have not purchased in over 180 days despite
--                    prior purchasing activity (candidates for win-back campaigns)?
-- -----------------------------------------------------------------------------
WITH customer_activity AS (
    SELECT
        customer_id,
        customer_name,
        customer_state,
        customer_signup_date,
        COUNT(order_id)                                             AS lifetime_completed_orders,
        ROUND(SUM(net_revenue), 2)                                  AS lifetime_revenue,
        MAX(order_date)                                             AS last_purchase_date,
        ROUND(JULIANDAY('2024-06-30') - JULIANDAY(MAX(order_date))) AS days_since_last_purchase
    FROM v_order_analytics
    WHERE is_completed = 1
    GROUP BY customer_id, customer_name, customer_state, customer_signup_date
)
SELECT
    customer_id,
    customer_name,
    customer_state,
    customer_signup_date,
    lifetime_completed_orders,
    lifetime_revenue,
    last_purchase_date,
    days_since_last_purchase,
    CASE
        WHEN days_since_last_purchase > 365 THEN 'Severe Churn (>1 Year)'
        WHEN days_since_last_purchase > 180 THEN 'High Inactivity (6-12 Months)'
        WHEN days_since_last_purchase > 90  THEN 'Moderate Inactivity (3-6 Months)'
        ELSE 'Active (<90 Days)'
    END                                                             AS inactivity_tier
FROM customer_activity
WHERE days_since_last_purchase > 180
ORDER BY lifetime_revenue DESC
LIMIT 50;
