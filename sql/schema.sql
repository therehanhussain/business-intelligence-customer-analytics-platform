-- =============================================================================
-- Customer Analytics Platform — Relational Data Warehouse Schema (Star Schema)
-- Production Engine: PostgreSQL 14+
-- Staging Engine Compatibility: SQLite 3.35+
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 1. DIMENSION TABLE: dim_customers
-- Granularity: One record per unique verified customer.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dim_customers (
    customer_id         VARCHAR(20) PRIMARY KEY,
    name                VARCHAR(100) NOT NULL,
    gender              VARCHAR(20) NOT NULL DEFAULT 'Unknown',
    age                 NUMERIC(5, 1) NOT NULL,
    city                VARCHAR(100) NOT NULL,
    state               VARCHAR(10) NOT NULL,
    signup_date         DATE NOT NULL,
    is_age_imputed      BOOLEAN NOT NULL DEFAULT FALSE,
    created_at          TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT chk_customer_age CHECK (age >= 18.0 AND age <= 120.0)
);

CREATE INDEX IF NOT EXISTS idx_dim_customers_state ON dim_customers (state);
CREATE INDEX IF NOT EXISTS idx_dim_customers_signup ON dim_customers (signup_date);


-- -----------------------------------------------------------------------------
-- 2. DIMENSION TABLE: dim_products
-- Granularity: One record per active catalog SKU.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dim_products (
    product_id          VARCHAR(20) PRIMARY KEY,
    product_name        VARCHAR(255) NOT NULL,
    category            VARCHAR(100) NOT NULL,
    price               NUMERIC(10, 2) NOT NULL,
    cost                NUMERIC(10, 2) NOT NULL,
    gross_margin_pct    NUMERIC(5, 2) NOT NULL,
    created_at          TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT chk_product_price_positive CHECK (price > 0.0),
    CONSTRAINT chk_product_cost_positive CHECK (cost > 0.0),
    CONSTRAINT chk_product_margin_valid CHECK (cost <= price)
);

CREATE INDEX IF NOT EXISTS idx_dim_products_category ON dim_products (category);


-- -----------------------------------------------------------------------------
-- 3. FACT TABLE: fact_orders
-- Granularity: One record per customer order line transaction.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS fact_orders (
    order_id            VARCHAR(30) PRIMARY KEY,
    customer_id         VARCHAR(20) NOT NULL,
    product_id          VARCHAR(20) NOT NULL,
    order_date          DATE NOT NULL,
    quantity            INTEGER NOT NULL,
    payment_method      VARCHAR(50) NOT NULL DEFAULT 'Unknown',
    order_status        VARCHAR(30) NOT NULL,
    created_at          TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_fact_orders_customer 
        FOREIGN KEY (customer_id) REFERENCES dim_customers (customer_id) 
        ON DELETE RESTRICT,
    CONSTRAINT fk_fact_orders_product 
        FOREIGN KEY (product_id) REFERENCES dim_products (product_id) 
        ON DELETE RESTRICT,
    CONSTRAINT chk_order_quantity_positive CHECK (quantity > 0),
    CONSTRAINT chk_order_status_valid CHECK (
        order_status IN ('Completed', 'Shipped', 'Cancelled', 'Refunded')
    )
);

CREATE INDEX IF NOT EXISTS idx_fact_orders_date ON fact_orders (order_date);
CREATE INDEX IF NOT EXISTS idx_fact_orders_customer ON fact_orders (customer_id);
CREATE INDEX IF NOT EXISTS idx_fact_orders_product ON fact_orders (product_id);
CREATE INDEX IF NOT EXISTS idx_fact_orders_status ON fact_orders (order_status);


-- -----------------------------------------------------------------------------
-- 4. GOVERNANCE TABLE: audit_rejected_records (Dead-Letter Queue Sink)
-- Granularity: One record per quarantined / rejected row from ETL pipeline.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS audit_rejected_records (
    rejection_id        BIGSERIAL PRIMARY KEY,
    table_name          VARCHAR(50) NOT NULL,
    record_identifier   VARCHAR(50) NOT NULL,
    rejection_reason    VARCHAR(100) NOT NULL,
    rejected_at         TIMESTAMP WITH TIME ZONE NOT NULL,
    raw_payload         TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_audit_table_reason ON audit_rejected_records (table_name, rejection_reason);


-- -----------------------------------------------------------------------------
-- 5. AUDIT LOG: audit_pipeline_execution
-- Granularity: One record per ETL orchestration run.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS audit_pipeline_execution (
    pipeline_run_id     VARCHAR(50) PRIMARY KEY,
    run_timestamp       TIMESTAMP WITH TIME ZONE NOT NULL,
    database_type       VARCHAR(50) NOT NULL,
    total_extracted     INTEGER NOT NULL,
    total_valid         INTEGER NOT NULL,
    total_rejected      INTEGER NOT NULL,
    pass_rate_pct       NUMERIC(5, 2) NOT NULL,
    audit_json          TEXT NOT NULL
);
