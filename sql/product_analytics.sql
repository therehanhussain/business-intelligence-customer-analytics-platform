-- =============================================================================
-- Customer Analytics Platform — Merchandising & Product Portfolio Analytics
-- Standard: ANSI SQL (Compatible with PostgreSQL and SQLite 3.35+)
-- =============================================================================

-- -----------------------------------------------------------------------------
-- QUERY 1: Category Contribution & Profitability Matrix
-- Business Question: Which categories generate the bulk of revenue, and which
--                    yield the strongest gross margins?
-- -----------------------------------------------------------------------------
SELECT
    product_category,
    COUNT(DISTINCT product_id)                                      AS active_products,
    SUM(is_completed)                                               AS completed_orders,
    SUM(CASE WHEN is_completed = 1 THEN quantity ELSE 0 END)        AS units_sold,
    ROUND(SUM(net_revenue), 2)                                      AS total_net_revenue,
    ROUND(SUM(net_revenue) * 100.0 / SUM(SUM(net_revenue)) OVER(), 2) AS category_revenue_share_pct,
    ROUND(SUM(net_profit), 2)                                       AS total_net_profit,
    ROUND(SUM(net_profit) * 100.0 / SUM(SUM(net_profit)) OVER(), 2)   AS category_profit_share_pct,
    ROUND((SUM(net_profit) / NULLIF(SUM(net_revenue), 0)) * 100.0, 2) AS realized_gross_margin_pct,
    ROUND(SUM(net_revenue) / NULLIF(SUM(CASE WHEN is_completed = 1 THEN quantity ELSE 0 END), 0), 2) AS avg_realized_price_per_unit
FROM v_order_analytics
GROUP BY product_category
ORDER BY total_net_revenue DESC;


-- -----------------------------------------------------------------------------
-- QUERY 2: Top 15 Revenue-Generating Hero Products
-- Business Question: What are our top 15 flagship commercial SKUs?
-- -----------------------------------------------------------------------------
WITH product_summary AS (
    SELECT
        product_id,
        product_name,
        product_category,
        unit_price,
        unit_cost,
        SUM(is_completed)                                           AS completed_orders,
        SUM(CASE WHEN is_completed = 1 THEN quantity ELSE 0 END)    AS total_units_sold,
        ROUND(SUM(net_revenue), 2)                                  AS product_net_revenue,
        ROUND(SUM(net_profit), 2)                                   AS product_net_profit,
        ROUND((SUM(net_profit) / NULLIF(SUM(net_revenue), 0)) * 100.0, 2) AS realized_margin_pct
    FROM v_order_analytics
    GROUP BY product_id, product_name, product_category, unit_price, unit_cost
)
SELECT
    DENSE_RANK() OVER (ORDER BY product_net_revenue DESC)           AS revenue_rank,
    product_id,
    product_name,
    product_category,
    unit_price,
    unit_cost,
    total_units_sold,
    completed_orders,
    product_net_revenue,
    product_net_profit,
    realized_margin_pct,
    ROUND(product_net_revenue * 100.0 / SUM(product_net_revenue) OVER(), 2) AS share_of_total_catalog_revenue
FROM product_summary
ORDER BY revenue_rank ASC
LIMIT 15;


-- -----------------------------------------------------------------------------
-- QUERY 3: Bottom 15 Underperforming / Tail Products
-- Business Question: Which catalog SKUs generate the lowest commercial returns
--                    and may be candidates for rationalization or markdown?
-- -----------------------------------------------------------------------------
WITH product_summary AS (
    SELECT
        product_id,
        product_name,
        product_category,
        unit_price,
        unit_cost,
        SUM(is_completed)                                           AS completed_orders,
        SUM(CASE WHEN is_completed = 1 THEN quantity ELSE 0 END)    AS total_units_sold,
        ROUND(SUM(net_revenue), 2)                                  AS product_net_revenue,
        ROUND(SUM(net_profit), 2)                                   AS product_net_profit,
        ROUND((SUM(net_profit) / NULLIF(SUM(net_revenue), 0)) * 100.0, 2) AS realized_margin_pct
    FROM v_order_analytics
    GROUP BY product_id, product_name, product_category, unit_price, unit_cost
)
SELECT
    DENSE_RANK() OVER (ORDER BY product_net_revenue ASC)            AS tail_rank,
    product_id,
    product_name,
    product_category,
    unit_price,
    unit_cost,
    total_units_sold,
    completed_orders,
    product_net_revenue,
    product_net_profit,
    realized_margin_pct
FROM product_summary
ORDER BY tail_rank ASC
LIMIT 15;


-- -----------------------------------------------------------------------------
-- QUERY 4: Product Revenue Concentration (Catalog Pareto Analysis)
-- Business Question: What percentage of our catalog drives 80% of our sales?
-- -----------------------------------------------------------------------------
WITH product_revenue AS (
    SELECT
        product_id,
        product_name,
        product_category,
        ROUND(SUM(net_revenue), 2)                                  AS net_revenue
    FROM v_order_analytics
    WHERE is_completed = 1
    GROUP BY product_id, product_name, product_category
),
ranked_products AS (
    SELECT
        product_id,
        product_name,
        product_category,
        net_revenue,
        ROW_NUMBER() OVER (ORDER BY net_revenue DESC)               AS product_rank,
        COUNT(product_id) OVER()                                    AS total_products,
        SUM(net_revenue) OVER()                                     AS total_catalog_revenue,
        SUM(net_revenue) OVER (ORDER BY net_revenue DESC ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS cumulative_revenue
    FROM product_revenue
)
SELECT
    product_rank,
    product_id,
    product_name,
    product_category,
    net_revenue,
    ROUND(product_rank * 100.0 / total_products, 2)                 AS cumulative_product_pct,
    ROUND(cumulative_revenue * 100.0 / total_catalog_revenue, 2)    AS cumulative_revenue_pct
FROM ranked_products
WHERE product_rank IN (1, 10, 25, 50, 100, 150, 200, 250, 300, 350, 400, 450, 492)
ORDER BY product_rank ASC;
