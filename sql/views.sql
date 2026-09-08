-- =============================================================================
-- Customer Analytics Platform — Analytical Views
-- Standard: ANSI SQL (Fully compatible with PostgreSQL and SQLite 3.35+)
-- =============================================================================

-- -----------------------------------------------------------------------------
-- VIEW: v_order_analytics
-- Purpose: Denormalized transactional view joining orders, customer demographics,
--          and product catalog economics. Serves as the single source of truth
--          for sales, customer, and merchandising analytics.
-- -----------------------------------------------------------------------------
DROP VIEW IF EXISTS v_order_analytics;

CREATE VIEW v_order_analytics AS
SELECT
    -- Order Line Identifiers
    o.order_id,
    o.customer_id,
    o.product_id,
    o.order_date,
    SUBSTR(o.order_date, 1, 4)                                      AS order_year,
    SUBSTR(o.order_date, 1, 7)                                      AS order_month,
    o.order_status,
    o.payment_method,

    -- Volume & Pricing
    o.quantity,
    p.price                                                         AS unit_price,
    p.cost                                                          AS unit_cost,

    -- Financial Calculations (Gross)
    ROUND(o.quantity * p.price, 2)                                  AS gross_revenue,
    ROUND(o.quantity * p.cost, 2)                                   AS total_cost,
    ROUND((p.price - p.cost) * o.quantity, 2)                       AS gross_profit,
    ROUND(((p.price - p.cost) / p.price) * 100.0, 2)                AS margin_pct,

    -- Lifecycle & Status Indicators
    CASE WHEN o.order_status IN ('Completed', 'Shipped') THEN 1 ELSE 0 END AS is_completed,
    CASE WHEN o.order_status = 'Refunded' THEN 1 ELSE 0 END               AS is_refunded,
    CASE WHEN o.order_status = 'Cancelled' THEN 1 ELSE 0 END              AS is_cancelled,

    -- Commercial Realized Metrics (Net of Cancellations & Refunds)
    CASE 
        WHEN o.order_status IN ('Completed', 'Shipped') 
        THEN ROUND(o.quantity * p.price, 2) 
        ELSE 0.0 
    END                                                             AS net_revenue,

    CASE 
        WHEN o.order_status IN ('Completed', 'Shipped') 
        THEN ROUND((p.price - p.cost) * o.quantity, 2) 
        ELSE 0.0 
    END                                                             AS net_profit,

    CASE 
        WHEN o.order_status = 'Refunded' 
        THEN ROUND(o.quantity * p.price, 2) 
        ELSE 0.0 
    END                                                             AS refunded_amount,

    CASE 
        WHEN o.order_status = 'Cancelled' 
        THEN ROUND(o.quantity * p.price, 2) 
        ELSE 0.0 
    END                                                             AS cancelled_amount,

    -- Customer Dimension Attributes
    c.name                                                          AS customer_name,
    c.gender                                                        AS customer_gender,
    c.age                                                           AS customer_age,
    c.city                                                          AS customer_city,
    c.state                                                         AS customer_state,
    c.signup_date                                                   AS customer_signup_date,
    c.is_age_imputed                                                AS customer_is_age_imputed,

    -- Product Dimension Attributes
    p.product_name,
    p.category                                                      AS product_category

FROM orders o
INNER JOIN customers c ON o.customer_id = c.customer_id
INNER JOIN products p  ON o.product_id = p.product_id;
