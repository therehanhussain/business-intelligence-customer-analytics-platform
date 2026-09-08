# Executive Power BI Dashboard Specification & Business Recommendations

**Project:** Business Intelligence & Customer Analytics Platform  
**Target Role:** ZS Business Technology Solutions (BTS) Associate  
**Stage:** Phase 5 — Executive BI Layer & Commercial Playbooks  
**Status:** Validated Star Schema & Functional Visual Prototype Complete  
**Reconciliation Status:** 100.0% Exact Match with Phase 3 SQL and Phase 4 Modeling (\$31,028,579.95 Net Revenue)

---

> [!IMPORTANT]
> **Environment Status & Architecture Disclaimer:**  
> Power BI Desktop was unavailable in the development environment; therefore, the HTML dashboard is a functional visual prototype, while the accompanying star schema, DAX measures, Power Query scripts, and import instructions provide the Power BI implementation specification.

---

## 1. Executive Overview & Purpose

The objective of Phase 5 is to translate the foundational engineering and modeling outputs of Phases 2, 3, and 4 into an **executive decision-support system**. 

The dashboard enables retail stakeholders to monitor financial performance, identify customer concentration risks, evaluate category margin dynamics, and activate targeted retention interventions before customer churn occurs.

### Core Business Questions Addressed:
1. **Financial Health:** What is our net revenue run-rate, gross profit margin, and how do seasonal peaks influence cash flow?
2. **Customer Portfolio Concentration:** What share of top-line revenue depends on high-value repeat shoppers vs. single-purchase buyers?
3. **Category Profitability Divergence:** Which categories drive top-line volume versus bottom-line margin? Where does return/cancellation friction erode margin?
4. **Predictive Risk & Capital Allocation:** How much revenue is exposed to churn, which high-value accounts require immediate outreach, and how can marketing dollars be allocated efficiently across risk thresholds?

---

## 2. Power BI Star Schema Data Model

The data layer is structured as an analytical **star schema** under `data/processed/powerbi/`:

```
                           ┌──────────────────────────┐
                           │         DimDate          │
                           │   (1,096 Calendar Days)  │
                           └─────────────┬────────────┘
                                         │ 1
                                         │ 
                                         │ * (order_date_id -> date_id)
                                         ▼
┌──────────────────────┐ *          ┌──────────────┐          * ┌──────────────────────┐
│     DimCustomers     ├───────────►│  FactOrders  │◄───────────┤     DimProducts      │
│  (10,000 Demographics│ 1          │(103,695 Rows)│ 1          │  (492 Product SKUs)  │
└──────────┬───────────┘            └──────────────┘            └──────────────────────┘
           │ 1
           │ 
           │ 1 (1-to-1 extension)
           ▼
┌──────────────────────────────┐
│     DimCustomerAnalytics     │
│  (RFM, Risk Tiers, ML Churn) │
└──────────────────────────────┘
```

### Table Specifications & Relationships

| Relationship | From Table & Key | To Table & Key | Cardinality | Cross-Filter Direction | Purpose / Integrity Guard |
| :--- | :--- | :--- | :---: | :---: | :--- |
| **Calendar Relationship** | `FactOrders[order_date_id]` | `DimDate[date_id]` | Many to One (`* : 1`) | Single (`DimDate` $\to$ `FactOrders`) | Enables time-intelligence without raw date discrepancies. |
| **Customer Dimension** | `FactOrders[customer_id]` | `DimCustomers[customer_id]` | Many to One (`* : 1`) | Single (`DimCustomers` $\to$ `FactOrders`) | Slices orders by demographics and registration cohort. |
| **Product Dimension** | `FactOrders[product_id]` | `DimProducts[product_id]` | Many to One (`* : 1`) | Single (`DimProducts` $\to$ `FactOrders`) | Enables category-to-SKU rollups and margin modeling. |
| **Customer Analytics** | `DimCustomerAnalytics[customer_id]` | `DimCustomers[customer_id]` | One to One (`1 : 1`) | Both or Single | Connects RFM segments and ML churn probabilities. |

### Data Model Integrity Controls:
1. **No Many-to-Many Relationships:** All fact-to-dimension relationships resolve through unique primary keys (`date_id`, `customer_id`, `product_id`).
2. **Zero Orphan Foreign Keys:** Verified by `tests/test_powerbi_data_model.py` (100% of order keys exist in dimensions).
3. **No Revenue Duplication:** Dimensions filter the fact table unidirectionally; fact transactions are never joined to other transactional facts.

---

## 3. Reusable DAX Measure Library (24 Measures)

All business metrics are implemented as **reusable DAX measures** (located in `dashboard/specs/dax_measures.dax`), eliminating redundant calculated columns and optimizing in-memory VertiPaq performance.

### 1. Core Financials

```dax
[Total Gross Revenue] = 
SUM(FactOrders[gross_revenue])

[Net Revenue] = 
CALCULATE(
    SUM(FactOrders[gross_revenue]),
    FactOrders[order_status] IN { "Completed", "Shipped" }
)

[Gross Profit] = 
CALCULATE(
    SUM(FactOrders[gross_profit]),
    FactOrders[order_status] IN { "Completed", "Shipped" }
)

[Gross Margin %] = 
DIVIDE(
    [Gross Profit],
    [Net Revenue],
    0
)

[Total Units Sold] = 
CALCULATE(
    SUM(FactOrders[quantity]),
    FactOrders[order_status] IN { "Completed", "Shipped" }
)
```

### 2. Orders & Fulfillment Operations

```dax
[Total Orders] = 
COUNTROWS(FactOrders)

[Completed Orders] = 
CALCULATE(
    COUNTROWS(FactOrders),
    FactOrders[order_status] IN { "Completed", "Shipped" }
)

[Refunded Orders] = 
CALCULATE(
    COUNTROWS(FactOrders),
    FactOrders[order_status] = "Refunded"
)

[Cancelled Orders] = 
CALCULATE(
    COUNTROWS(FactOrders),
    FactOrders[order_status] = "Cancelled"
)

[Refund Rate %] = 
DIVIDE([Refunded Orders], [Total Orders], 0)

[Cancellation Rate %] = 
DIVIDE([Cancelled Orders], [Total Orders], 0)

[Refunded Revenue] = 
CALCULATE(
    SUM(FactOrders[gross_revenue]),
    FactOrders[order_status] = "Refunded"
)

[Cancelled Revenue] = 
CALCULATE(
    SUM(FactOrders[gross_revenue]),
    FactOrders[order_status] = "Cancelled"
)
```

### 3. Customer Portfolio & LTV KPIs

```dax
[Total Customers] = 
COUNTROWS(DimCustomers)

[Active Customers] = 
CALCULATE(
    DISTINCTCOUNT(FactOrders[customer_id]),
    FactOrders[order_status] IN { "Completed", "Shipped" }
)

[Average Order Value (AOV)] = 
DIVIDE([Net Revenue], [Completed Orders], 0)

[Revenue Per Customer] = 
DIVIDE([Net Revenue], [Active Customers], 0)

[Repeat Buyer Rate %] = 
DIVIDE(
    CALCULATE(
        [Active Customers],
        DimCustomerAnalytics[completed_orders] >= 2
    ),
    [Active Customers],
    0
)
```

### 4. Time-Series Intelligence

```dax
[Net Revenue Prior Month] = 
CALCULATE(
    [Net Revenue],
    DATEADD(DimDate[date], -1, MONTH)
)

[MoM Revenue Growth %] = 
DIVIDE(
    [Net Revenue] - [Net Revenue Prior Month],
    [Net Revenue Prior Month],
    0
)

[YoY Revenue Growth %] = 
VAR RevenuePriorYear = 
    CALCULATE(
        [Net Revenue],
        SAMEPERIODLASTYEAR(DimDate[date])
    )
RETURN
    DIVIDE(
        [Net Revenue] - RevenuePriorYear,
        RevenuePriorYear,
        0
    )

[Running Net Revenue] = 
CALCULATE(
    [Net Revenue],
    FILTER(
        ALLSELECTED(DimDate),
        DimDate[date] <= MAX(DimDate[date])
    )
)
```

### 5. Risk Intelligence & Churn Scoring

```dax
[High Risk Customers] = 
CALCULATE(
    COUNTROWS(DimCustomerAnalytics),
    DimCustomerAnalytics[risk_level] = "HIGH"
)

[Critical Risk Customers] = 
CALCULATE(
    COUNTROWS(DimCustomerAnalytics),
    DimCustomerAnalytics[risk_level] = "CRITICAL"
)

[Historical Revenue at Risk] = 
// Historical revenue associated with HIGH + CRITICAL risk accounts (not a guaranteed future loss)
CALCULATE(
    SUM(DimCustomerAnalytics[total_revenue]),
    DimCustomerAnalytics[risk_level] IN { "HIGH", "CRITICAL" }
)

[Avg Churn Probability] = 
AVERAGE(DimCustomerAnalytics[churn_probability])
```

---

## 4. Four Decision-Oriented Dashboard Pages

### Page 1: Executive Overview
* **Primary Stakeholder:** C-Suite, Managing Directors, Head of Retail.
* **Objective:** Fast, high-level pulse of business health, growth velocity, and top-line risk.
* **KPI Header Cards:**
  * Net Revenue: **\$31.03M**
  * Gross Profit: **\$12.46M**
  * Gross Margin: **40.16%**
  * Active Customers: **8,925** (89.25% activation)
  * Total Orders: **103,695** (95,526 completed/shipped)
  * Average Order Value: **\$324.81**
  * Refund Rate: **3.94%** (\$1.33M)
  * Cancellation Rate: **3.94%** (\$1.36M)
* **Core Visuals:**
  1. *Monthly Net Revenue & Profit Area Chart:* Highlights quarterly cadence and November–December seasonal surge (~1.35M/mo).
  2. *Net Revenue by Category Bar Chart:* Illustrates Electronics dominance (\$15.21M, 49.0%) vs. high-margin Beauty (\$2.18M).
  3. *Order Fulfillment Status Funnel:* Completed (86.10%), Shipped (6.02%), Refunded (3.94%), Cancelled (3.94%).
  4. *Customer Revenue Concentration:* Champions and Loyal Customers represent 38.04% of customers but generate 76.16% of total revenue (\$23.63M).
* **Executive Narrative:** Dedicated insights callout panel summarizing verified data takeaways.

---

### Page 2: Customer Analytics & Lifecycle Segmentation
* **Primary Stakeholder:** VP of Marketing, CRM Lead, Customer Success Director.
* **Objective:** Evaluate cohort value, monitor repeat purchase behavior, and prevent high-value churn.
* **Slicers:** Segment, Risk Level, State, Age Group.
* **Core Visuals:**
  1. *RFM Segment Distribution Table & Treemap:*
     * **Champions** (2,150 customers, 21.5% base): **\$17.19M** (55.4% revenue, avg recency 11.7 days).
     * **Loyal Customers** (1,654 customers, 16.5% base): **\$6.44M** (20.8% revenue, avg recency 100.5 days).
     * **At Risk** (1,000 customers, 10.0% base): **\$4.10M** (13.2% revenue, avg recency 401.2 days).
     * **Promising** (1,441 customers, 14.4% base): **\$1.43M** (4.6% revenue, avg recency 283.5 days).
     * **Hibernating** (1,976 customers, 19.8% base): **\$705K** (2.3% revenue, avg recency 539.4 days).
     * **Cannot Lose Them** (110 customers, 1.1% base): **\$588K** (1.9% revenue, avg recency 529.9 days).
     * **Potential Loyalists** (570 customers, 5.7% base): **\$572K** (1.8% revenue, avg recency 31.0 days).
     * **New Customers** (24 customers, 0.2% base): **\$5.0K** (0.02% revenue, avg recency 90.1 days).
     * **Inactive / Unactivated** (1,075 customers, 10.8% base): **\$0.00** (0 orders).
  2. *Lifecycle Dynamics Matrix:* Compares Average Spend (\$7,994 Champions vs. \$357 Hibernating) vs. Order Frequency.

---

### Page 3: Sales & Product Analytics
* **Primary Stakeholder:** Head of Merchandising, Supply Chain Lead, Product Line Managers.
* **Objective:** Understand SKU margin contribution, category volume drivers, and friction points.
* **Slicers:** Category, Product, Year, Month, Fulfillment Status.
* **Core Visuals:**
  1. *Category Profitability Matrix:*
     * **Beauty & Personal Care:** 74.31% margin (\$1.62M profit on \$2.18M net revenue).
     * **Apparel & Accessories:** 61.69% margin (\$2.09M profit on \$3.38M net revenue).
     * **Home & Kitchen:** 50.34% margin (\$2.64M profit on \$5.24M net revenue).
     * **Sports & Outdoors:** 49.89% margin (\$2.34M profit on \$4.69M net revenue).
     * **Books & Media:** 38.67% margin (\$128K profit on \$332K net revenue).
     * **Electronics:** 24.01% margin (\$3.65M profit on \$15.21M net revenue).
  2. *Top 5 Commercial Hero SKUs:*
     * *Ultralight 2-Person Backpacking Tent:* \$1.86M revenue (54.75% margin).
     * *Ultra HD 4K Smart Monitor:* \$1.36M revenue (19.98% margin).
     * *Hydrating Hyaluronic Acid Serum:* \$954K revenue (80.26% margin).
     * *Performance Moisture-Wicking Hoodie:* \$776K revenue (62.40% margin).
     * *Smart Home Security Hub - Ed. 2:* \$709K revenue (22.31% margin).
  3. *Friction Breakdown:* Highlights that Electronics accounts for **\$1.36M in combined returns and cancellations** (50.5% of total company friction).

---

### Page 4: Customer Risk & Retention Strategy
* **Primary Stakeholder:** VP of Retention, CRM Operations, Commercial Strategy.
* **Objective:** Target at-risk customer cohorts and trigger personalized win-back workflows.
* **Risk Scorecards:**
  * High & Critical Risk Accounts: **4,274 customers** (42.74% of base).
  * Historical Revenue Exposure — High & Critical Risk Customers: **\$10.47M** (33.73% of cumulative net spend; represents past revenue associated with accounts currently exhibiting elevated churn risk, not a guaranteed future churn amount).
  * High-Value Dormant Base: **1,110 customers** (\$4.69M revenue exposure in *At Risk* and *Cannot Lose Them*).
  * Out-of-Time Churn Model Quality: **0.9481 ROC-AUC** (84.18% recall, 94.39% precision).
* **Core Visuals:**
  1. *Customer Segment $\times$ Risk Tier Cross-Tabulation:* Identifies the exact revenue distribution across risk severity.
  2. *High-Priority Account Action Table:* Filtered by high-value accounts with conditional risk formatting, displaying `customer_id`, `name`, `segment`, `risk_level`, `risk_score`, `churn_probability`, `total_revenue`, `recency_days`, `key_risk_driver`, and `recommended_action`.

---

## 5. Structured Business Recommendations

The following actionable recommendations are derived directly from verified analytical findings:

### Recommendation 1: VIP Dormancy Intervention (Playbook A)
* **Finding:** 1,110 high-value customers in the *Cannot Lose Them* ($n=110$, avg spend \$5,342) and *At Risk* ($n=1,000$, avg spend \$4,100) segments represent **\$4.69M in historical revenue** but exhibit severe dormancy (average recency 401–530 days).
* **Business Implication:** If unaddressed, natural churn will permanently erode 15.1% of historical corporate revenue.
* **Recommended Action:** Launch a high-touch VIP Concierge campaign featuring personalized executive win-back emails, dedicated account reps, and margin-subsidized reactivation offers (e.g. 20% discount on their historically preferred category).

### Recommendation 2: Core Loyalty Preservation (Playbook B)
* **Finding:** *Champions* ($n=2,150$) and *Loyal Customers* ($n=1,654$) comprise **38.04% of customers but deliver 76.16% of total revenue** (\$23.63M), with near-zero recency (11.7 days).
* **Business Implication:** Small percentage drops in Champion retention create severe revenue shocks that acquisition cannot replace.
* **Recommended Action:** Implement a Tier-1 Loyalty Rewards tier with early access to limited-edition drops, free express shipping thresholds, and automated cross-sell bundles to sustain purchasing momentum.

### Recommendation 3: Onboarding Friction Elimination (Playbook C)
* **Finding:** 1,075 registered customers (10.75% of customer master) have **never placed a single completed order** ($0 revenue contribution), resulting in an immediate `CRITICAL` risk classification.
* **Business Implication:** Paid acquisition spend is wasted at top-of-funnel registration without downstream conversion.
* **Recommended Action:** Implement an automated 3-step onboarding drip campaign triggered on Day 1, Day 3, and Day 7 post-signup, offering a first-order incentive (\$15 off orders over \$50) focusing on top-converting hero SKUs.

### Recommendation 4: Electronics Return & Cancellation Mitigation
* **Finding:** Electronics drives 49.0% of net revenue (\$15.21M) but accounts for **\$1.36M in return and cancellation losses** (50.5% of total company friction) and carries the lowest gross margin (24.01%).
* **Business Implication:** Low category margin combined with reverse-logistics freight costs creates severe net margin compression.
* **Recommended Action:** Conduct a catalog-level return audit on electronics SKUs, improve product dimension/spec transparency on product detail pages, and require automated return reason surveys.

### Recommendation 5: ML-Calibrated Retention Budget Optimization
* **Finding:** The Out-of-Time Churn Model demonstrates that lowering the decision threshold from 0.50 to 0.40 expands captured churners from 84.18% to **87.80% recall** (5,232 targeted accounts) while maintaining high **90.92% precision** (only 475 false alarms).
* **Business Implication:** Low-cost digital campaigns (email/SMS) achieve superior ROI at lower thresholds, whereas expensive phone calls require a higher threshold.
* **Recommended Action:** Adopt a two-tier operational threshold: deploy automated email/SMS flows at threshold **0.30–0.40** (casting a wide net), and reserve outbound phone calls or VIP gift boxes for accounts exceeding threshold **0.70** (98.77% precision).

---

## 6. Power BI Desktop Import & Setup Instructions

To deploy this specification into Microsoft Power BI Desktop on any workstation:

1. **Step 1: Download & Open Power BI Desktop**
   * Launch Power BI Desktop on your local machine.
2. **Step 2: Ingest Datasets via Power Query**
   * In Power BI Desktop, click **Get Data $\to$ Blank Query**, open the **Advanced Editor**, and paste the M-scripts from [`dashboard/specs/powerquery_scripts.m`](file:///c:/Users/MD%20REHAN%20HUSSAIN/Documents/customer-analytics-platform/dashboard/specs/powerquery_scripts.m).
   * Alternatively, use **Get Data $\to$ Text/CSV** and select the 5 CSVs from `data/processed/powerbi/`:
     * `dim_date.csv`
     * `dim_customers.csv`
     * `dim_products.csv`
     * `fact_orders.csv`
     * `dim_customer_analytics.csv`
3. **Step 3: Configure Relationships in Model View**
   * Connect `DimDate[date_id]` to `FactOrders[order_date_id]` (1 to Many).
   * Connect `DimCustomers[customer_id]` to `FactOrders[customer_id]` (1 to Many).
   * Connect `DimProducts[product_id]` to `FactOrders[product_id]` (1 to Many).
   * Connect `DimCustomers[customer_id]` to `DimCustomerAnalytics[customer_id]` (1 to 1).
   * Confirm all cross-filter directions are **Single** (Dimension filters Fact).
4. **Step 4: Create DAX Measures**
   * Create a dedicated measure table (`_Measures`).
   * Copy and paste each formula from [`dashboard/specs/dax_measures.dax`](file:///c:/Users/MD%20REHAN%20HUSSAIN/Documents/customer-analytics-platform/dashboard/specs/dax_measures.dax) into the formula bar.
5. **Step 5: Lay Out the 4 Dashboard Pages**
   * Open [`dashboard/index.html`](file:///c:/Users/MD%20REHAN%20HUSSAIN/Documents/customer-analytics-platform/dashboard/index.html) in any web browser to view the exact layout, visual hierarchy, color palette, and metric cards.
   * Reproduce the visual layout on Pages 1–4 using Power BI native visuals (Cards, Clustered Bar/Column, Donut, Area Chart, Matrix, Table with Conditional Formatting).
6. **Step 6: Refresh & Validate**
   * Verify that Card visuals reconcile:
     * `[Net Revenue]` = **\$31,028,579.95**
     * `[Gross Profit]` = **\$12,461,250.73**
     * `[Total Orders]` = **103,695**
     * `[Total Customers]` = **10,000**
