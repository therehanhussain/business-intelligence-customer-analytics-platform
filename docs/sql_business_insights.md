# SQL Business Insights & Strategic Analysis

**Platform**: Business Intelligence & Customer Analytics Platform  
**Target Role**: ZS Business Technology Solutions Associate  
**Data Scope**: Phase 3 Relational Analytics Layer (`v_order_analytics` across 103,695 orders, 10,000 customers, 492 products)  
**Database**: Staging Relational Warehouse (`data/processed/staging.db`)

---

## Executive Summary

Through SQL-based dimensional modeling and aggregations, we translated raw transactional data into high-conviction commercial intelligence. The business realized **\$31,028,579.95 in net revenue** and **\$12,461,250.73 in net gross profit** (40.16% realized margin) across 95,526 completed transactions.

However, three primary commercial vulnerabilities were identified:
1. **Severe Customer Concentration**: The top 20% of customer accounts drive **57.86% of total company revenue** (\$17.95M), leaving the business exposed to key-account churn.
2. **Category Margin Asymmetry**: The flagship department (*Electronics*) accounts for nearly half of all gross sales (49.01%), but operates on the lowest margin (24.01%), while high-margin categories (*Beauty* at 74.31% margin, *Apparel* at 61.69% margin) remain under-penetrated.
3. **Revenue Leaks from Inactivity & Returns**: Over **4,435 previously paying customers** (49.7% of the paying base) have been inactive for over 180 days, representing **\$8.54M in historical revenue** at risk. Simultaneously, refunds and cancellations siphon **\$2.70M (8.00%)** from gross invoiced revenue.

---

## 1. Customer Revenue Concentration & Pareto Deciles

### Business Question
How concentrated is our customer revenue base, and what percentage of accounts drives the majority of top-line commercial growth?

### SQL Metric & Query Logic
```sql
WITH customer_spend AS (
    SELECT customer_id, ROUND(SUM(net_revenue), 2) AS customer_revenue
    FROM v_order_analytics
    WHERE is_completed = 1
    GROUP BY customer_id
),
ranked_deciles AS (
    SELECT
        customer_id,
        customer_revenue,
        NTILE(10) OVER (ORDER BY customer_revenue DESC) AS revenue_decile
    FROM customer_spend
)
SELECT
    revenue_decile,
    COUNT(customer_id)                                          AS customer_count,
    ROUND(SUM(customer_revenue), 2)                             AS decile_revenue,
    ROUND(SUM(customer_revenue) * 100.0 / SUM(SUM(customer_revenue)) OVER(), 2) AS pct_of_total_revenue,
    ROUND(
        SUM(SUM(customer_revenue)) OVER (ORDER BY revenue_decile ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) 
        * 100.0 / SUM(SUM(customer_revenue)) OVER(), 
        2
    )                                                           AS cumulative_revenue_pct
FROM ranked_deciles
GROUP BY revenue_decile;
```

### Actual Quantitative Result
* **Decile 1 (Top 10% / 893 customers)**: Generated **\$11,513,276.97** (**37.11%** of total revenue).
* **Deciles 1–2 (Top 20% / 1,786 customers)**: Generated **\$17,953,924.46** (**57.86%** of total revenue).
* **Deciles 1–4 (Top 40% / 3,572 customers)**: Generated **\$25,733,376.34** (**82.93%** of total revenue).
* **Deciles 8–10 (Bottom 30% / 2,676 customers)**: Generated only **\$807,236.04** (**2.60%** of total revenue).

### Commercial Significance
The business exhibits strong Pareto skew. Over half of total realized revenue relies entirely on fewer than 1,800 customer accounts. While this indicates strong product-market fit among high-value retail consumers, it represents a substantial revenue vulnerability if customer churn increases among the top two deciles.

### Recommended Strategic Action
1. Establish an **Exclusive VIP Loyalty Tier** for Deciles 1 and 2 (annual spend $> \$4,200$) with dedicated concierge support, early access to catalog drops, and expedited shipping.
2. Implement proactive churn alert monitoring for any Decile 1–2 customer exceeding 45 days without an order.

---

## 2. Category Margin Contribution & Strategic Asymmetry

### Business Question
Which merchandising departments drive top-line volume versus bottom-line cash generation, and where is gross margin being diluted?

### SQL Metric & Query Logic
```sql
SELECT
    product_category,
    COUNT(DISTINCT product_id)                                      AS active_products,
    SUM(is_completed)                                               AS completed_orders,
    ROUND(SUM(net_revenue), 2)                                      AS total_net_revenue,
    ROUND(SUM(net_revenue) * 100.0 / SUM(SUM(net_revenue)) OVER(), 2) AS revenue_share_pct,
    ROUND(SUM(net_profit), 2)                                       AS total_net_profit,
    ROUND((SUM(net_profit) / NULLIF(SUM(net_revenue), 0)) * 100.0, 2) AS realized_gross_margin_pct
FROM v_order_analytics
GROUP BY product_category
ORDER BY total_net_revenue DESC;
```

### Actual Quantitative Result
| Category | Completed Orders | Realized Net Revenue | Revenue Share | Net Profit | Gross Margin % |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Electronics** | 35,468 | **\$15,208,390.87** | **49.01%** | \$3,651,855.87 | **24.01%** |
| **Home & Kitchen** | 18,172 | **\$5,244,768.06** | **16.90%** | \$2,639,996.87 | **50.34%** |
| **Sports & Outdoors** | 15,250 | **\$4,685,995.06** | **15.10%** | \$2,338,065.32 | **49.89%** |
| **Apparel & Accessories** | 13,874 | **\$3,381,087.25** | **10.90%** | \$2,085,899.24 | **61.69%** |
| **Beauty & Personal Care** | 9,842 | **\$2,175,902.89** | **7.01%** | \$1,616,889.07 | **74.31%** |
| **Books & Media** | 2,920 | **\$332,435.82** | **1.07%** | \$128,544.36 | **38.67%** |

### Commercial Significance
* **The Volume Driver**: *Electronics* generates 49.01% of all revenue, but operates at a 24.01% margin.
* **The Margin Powerhouse**: *Beauty & Personal Care* delivers an extraordinary **74.31% margin**, generating \$1.62M in profit on only \$2.18M in sales. *Apparel* similarly delivers **61.69% margin**.
* A 5% promotional shift from low-margin Electronics to high-margin Beauty and Apparel would expand portfolio gross profit by over **\$350,000** without requiring any increase in total marketing acquisition spend.

### Recommended Strategic Action
1. Launch **Cross-Merchandising Bundles**: Bundle lower-margin electronics (e.g. smart watches) with high-margin apparel or fitness accessories at checkout.
2. Rebalance marketing ad spend by allocating 15% more budget toward Beauty & Personal Care campaigns.

---

## 3. Product Catalog Pareto Skew (Hero vs. Tail SKUs)

### Business Question
What percentage of catalog SKUs account for 70% and 80% of net revenue, and which items constitute the low-velocity "long tail"?

### SQL Metric & Query Logic
```sql
WITH prod_rev AS (
    SELECT product_id, ROUND(SUM(net_revenue), 2) AS rev
    FROM v_order_analytics 
    WHERE is_completed = 1 
    GROUP BY product_id
),
ranked AS (
    SELECT 
        product_id, rev,
        ROW_NUMBER() OVER (ORDER BY rev DESC) AS rnk,
        COUNT(1) OVER()                       AS tot_prods,
        SUM(rev) OVER()                       AS tot_rev,
        SUM(rev) OVER (ORDER BY rev DESC ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS cum_rev
    FROM prod_rev
)
SELECT 
    rnk, 
    ROUND(rnk * 100.0 / tot_prods, 1) AS prod_pct, 
    ROUND(cum_rev * 100.0 / tot_rev, 1) AS cum_rev_pct
FROM ranked 
WHERE rnk IN (10, 50, 98, 150, 492);
```

### Actual Quantitative Result
* **Top 10 Products (2.0% of catalog)**: Account for **26.3% of revenue** (\$8.16M).
* **Top 50 Products (10.2% of catalog)**: Account for **55.9% of revenue** (\$17.34M).
* **Top 98 Products (19.9% of catalog)**: Account for **71.4% of revenue** (\$22.15M) — Confirming the classical **80/20 rule**.
* **Top 150 Products (30.5% of catalog)**: Account for **81.5% of revenue** (\$25.29M).
* **Bottom 192 Products (39.0% of catalog)**: Contribute only **4.6% of total revenue**.

### Top 3 Flagship SKUs
1. `PROD_0001` (*Hydrating Hyaluronic Acid Serum*): \$1,211,887.95 revenue, \$972,634.35 profit (80.26% margin).
2. `PROD_0003` (*Cast Iron Pre-Seasoned Dutch Oven*): \$1,126,825.96 revenue, \$530,944.57 profit (47.12% margin).
3. `PROD_0002` (*Classic Fit Chino Pants*): \$1,104,188.58 revenue, \$753,047.88 profit (68.20% margin).

### Commercial Significance
Almost three-quarters of total sales come from fewer than 100 products. Over 190 tail SKUs occupy working capital, warehouse shelf space, and inventory holding costs while generating negligible turnover.

### Recommended Strategic Action
1. **Supply Chain Defense**: Guarantee 99.5% service levels and safety stock for the top 50 revenue-driving SKUs to prevent stock-outs during peak seasons.
2. **Catalog Rationalization**: Review the bottom 15 SKUs (e.g. niche books and low-velocity editions generating under \$3,000 annually) for markdown liquidation and SKU discontinuation.

---

## 4. Customer Retention Decay & Churn Risk Cohorts

### Business Question
What proportion of paying customers show declining engagement or extended dormancy ($> 180$ days), and what historical revenue volume is at risk?

### SQL Metric & Query Logic
```sql
WITH last_purchases AS (
    SELECT 
        customer_id, 
        ROUND(SUM(net_revenue), 2) AS ltv,
        ROUND(JULIANDAY('2024-06-30') - JULIANDAY(MAX(order_date))) AS days_since
    FROM v_order_analytics 
    WHERE is_completed = 1 
    GROUP BY customer_id
)
SELECT
    CASE
        WHEN days_since > 365 THEN 'Dormant (>365d)'
        WHEN days_since > 180 THEN 'At-Risk (181-365d)'
        WHEN days_since > 90  THEN 'Cooling (91-180d)'
        ELSE 'Active (<=90d)'
    END AS activity_cohort,
    COUNT(1)                                                        AS customer_count,
    ROUND(SUM(ltv), 2)                                              AS cohort_historical_spend,
    ROUND(SUM(ltv) * 100.0 / SUM(SUM(ltv)) OVER(), 2)               AS pct_of_cumulative_spend
FROM last_purchases 
GROUP BY 1 
ORDER BY customer_count DESC;
```

### Actual Quantitative Result
* **Active ($\le 90$ Days)**: **3,507 customers (39.29%)** | **\$19,657,135.89 (63.35% of total spend)**.
* **Cooling (91–180 Days)**: **983 customers (11.01%)** | **\$2,833,375.72 (9.13% of total spend)**.
* **At-Risk (181–365 Days)**: **1,862 customers (20.86%)** | **\$4,901,504.06 (15.80% of total spend)**.
* **Dormant ($> 365$ Days)**: **2,573 customers (28.83%)** | **\$3,636,564.28 (11.72% of total spend)**.
* **Unactivated Accounts**: **935 customers (9.35% of total 10k base)** registered but never placed an order.

### Commercial Significance
* Nearly **half (49.69%) of all paying customers** (4,435 accounts) have not purchased in over 6 months.
* These inactive accounts previously contributed **\$8,538,068.34 (27.52%)** in revenue. If left unaddressed, customer acquisition costs (CAC) will rise as marketing must replace lost buyers with expensive cold traffic.

### Recommended Strategic Action
1. **Automated Win-Back Flows**: Trigger an automated 3-part email/SMS re-engagement sequence at day 91 with an escalating discount (10% at day 90, 15% at day 120, 20% + free shipping at day 150).
2. **Onboarding Nudge for Unactivated Cohort**: Deploy an immediate welcome promo for the 935 registered zero-order accounts within 7 days of signup.

---

## 5. Commercial Leakage: Refund & Cancellation Impact

### Business Question
What is the financial volume and rate of cancelled and refunded orders, and how does leakage vary across fulfillment?

### SQL Metric & Query Logic
```sql
SELECT
    COUNT(order_id)                                                 AS total_orders,
    ROUND(SUM(gross_revenue), 2)                                    AS gross_revenue,
    ROUND(SUM(refunded_amount), 2)                                  AS refunded_amount,
    ROUND(SUM(refunded_amount) * 100.0 / SUM(gross_revenue), 2)     AS refund_revenue_rate_pct,
    ROUND(SUM(cancelled_amount), 2)                                 AS cancelled_amount,
    ROUND(SUM(cancelled_amount) * 100.0 / SUM(gross_revenue), 2)    AS cancellation_revenue_rate_pct,
    ROUND(SUM(net_revenue), 2)                                      AS net_revenue
FROM v_order_analytics;
```

### Actual Quantitative Result
* **Gross Invoiced Revenue**: **\$33,726,886.71** (103,695 orders)
* **Total Refunded Orders**: **4,087 orders (3.94%)** $\rightarrow$ **\$1,334,921.53 lost (3.96% of gross)**
* **Total Cancelled Orders**: **4,082 orders (3.94%)** $\rightarrow$ **\$1,363,385.23 lost (4.04% of gross)**
* **Total Unrealized / Leaked Revenue**: **\$2,698,306.76 (8.00% total revenue erosion)**
* **Net Realized Revenue**: **\$31,028,579.95** (95,526 completed/shipped orders)

### Commercial Significance
An 8.00% top-line revenue leakage (\$2.70M) erodes operating margin. Cancellations typically reflect checkout friction, unexpected shipping charges, or long delivery estimates, whereas refunds reflect product expectation mismatches, sizing defects (in apparel), or electronics setup confusion.

### Recommended Strategic Action
1. **Reduce Cancellations**: Implement instant payment address auto-complete and transparent delivery date estimations before checkout.
2. **Targeted Return Reduction**: For top-returned products, audit online product imagery, provide 3D sizing charts, and include quick-start product setup guides.

---

## Summary of Key Metrics & Baselines

| Key Metric | Value |
| :--- | :--- |
| **Total Customer Base** | 10,000 accounts |
| **Paying Customers** | 8,925 accounts (89.25%) |
| **Repeat Buyer Rate** | 81.13% of paying base (7,241 customers) |
| **Average Revenue Per Paying Customer** | \$3,476.59 |
| **Total Valid Orders** | 103,695 transactions |
| **Completed / Shipped Orders** | 95,526 transactions (92.12%) |
| **Total Net Realized Revenue** | \$31,028,579.95 |
| **Total Net Realized Profit** | \$12,461,250.73 |
| **Overall Realized Gross Margin** | 40.16% |
| **Average Order Value (AOV)** | \$324.82 |
| **Revenue in Top 20% of Customers** | 57.86% (\$17.95M) |
| **Revenue in Top 20% of Products** | 71.40% (\$22.15M) |
| **Quarantined Records in DLQ** | 3,312 records (2.82% overall pipeline quarantine rate) |
