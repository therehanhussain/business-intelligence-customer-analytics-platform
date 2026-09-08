// =============================================================================
// Power Query M Scripts for Customer Analytics Platform
// Engine: Microsoft Power BI Desktop / Power Query Engine
// =============================================================================

// 1. DIM_DATE (Calendar Dimension)
// Path: Source = Csv.Document(File.Contents("data/processed/powerbi/dim_date.csv"), [Delimiter=",", Columns=14, Encoding=65001, QuoteStyle=QuoteStyle.None])
let
    Source = Csv.Document(File.Contents("data/processed/powerbi/dim_date.csv"),[Delimiter=",", Columns=14, Encoding=65001, QuoteStyle=QuoteStyle.None]),
    #"Promoted Headers" = Table.PromoteHeaders(Source, [PromoteAllScalars=true]),
    #"Changed Type" = Table.TransformColumnTypes(#"Promoted Headers",{
        {"date_id", Int64.Type},
        {"date", type date},
        {"year", Int64.Type},
        {"quarter", Int64.Type},
        {"quarter_name", type text},
        {"year_quarter", type text},
        {"month", Int64.Type},
        {"month_name", type text},
        {"month_short", type text},
        {"month_year", type text},
        {"day_of_month", Int64.Type},
        {"day_of_week", Int64.Type},
        {"day_name", type text},
        {"is_weekend", Int64.Type}
    })
in
    #"Changed Type";


// 2. DIM_CUSTOMERS (Customer Master)
let
    Source = Csv.Document(File.Contents("data/processed/powerbi/dim_customers.csv"),[Delimiter=",", Columns=9, Encoding=65001, QuoteStyle=QuoteStyle.None]),
    #"Promoted Headers" = Table.PromoteHeaders(Source, [PromoteAllScalars=true]),
    #"Changed Type" = Table.TransformColumnTypes(#"Promoted Headers",{
        {"customer_id", type text},
        {"name", type text},
        {"gender", type text},
        {"age", Int64.Type},
        {"city", type text},
        {"state", type text},
        {"signup_date", type date},
        {"signup_date_id", Int64.Type},
        {"is_age_imputed", Int64.Type}
    })
in
    #"Changed Type";


// 3. DIM_PRODUCTS (Product Catalog)
let
    Source = Csv.Document(File.Contents("data/processed/powerbi/dim_products.csv"),[Delimiter=",", Columns=6, Encoding=65001, QuoteStyle=QuoteStyle.None]),
    #"Promoted Headers" = Table.PromoteHeaders(Source, [PromoteAllScalars=true]),
    #"Changed Type" = Table.TransformColumnTypes(#"Promoted Headers",{
        {"product_id", type text},
        {"product_name", type text},
        {"category", type text},
        {"price", type number},
        {"cost", type number},
        {"margin_pct", type number}
    })
in
    #"Changed Type";


// 4. FACT_ORDERS (Order Transactions)
let
    Source = Csv.Document(File.Contents("data/processed/powerbi/fact_orders.csv"),[Delimiter=",", Columns=19, Encoding=65001, QuoteStyle=QuoteStyle.None]),
    #"Promoted Headers" = Table.PromoteHeaders(Source, [PromoteAllScalars=true]),
    #"Changed Type" = Table.TransformColumnTypes(#"Promoted Headers",{
        {"order_id", type text},
        {"customer_id", type text},
        {"product_id", type text},
        {"order_date", type date},
        {"order_date_id", Int64.Type},
        {"quantity", Int64.Type},
        {"unit_price", type number},
        {"unit_cost", type number},
        {"gross_revenue", type number},
        {"gross_profit", type number},
        {"net_revenue", type number},
        {"net_profit", type number},
        {"refunded_amount", type number},
        {"cancelled_amount", type number},
        {"payment_method", type text},
        {"order_status", type text},
        {"is_completed", Int64.Type},
        {"is_refunded", Int64.Type},
        {"is_cancelled", Int64.Type}
    })
in
    #"Changed Type";


// 5. DIM_CUSTOMER_ANALYTICS (Segmentation, Risk & ML Churn)
let
    Source = Csv.Document(File.Contents("data/processed/powerbi/dim_customer_analytics.csv"),[Delimiter=",", Encoding=65001, QuoteStyle=QuoteStyle.None]),
    #"Promoted Headers" = Table.PromoteHeaders(Source, [PromoteAllScalars=true]),
    #"Changed Type" = Table.TransformColumnTypes(#"Promoted Headers",{
        {"customer_id", type text},
        {"customer_segment", type text},
        {"risk_level", type text},
        {"risk_score", Int64.Type},
        {"churn_probability", type number},
        {"total_revenue", type number},
        {"total_profit", type number},
        {"completed_orders", Int64.Type},
        {"recency_days", Int64.Type}
    })
in
    #"Changed Type";
