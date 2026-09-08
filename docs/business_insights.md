# Business Insights & Commercial Findings

This document summarizes the core analytical findings from the transactional data, SQL queries, customer segmentation, and churn modeling. It is written from the perspective of an analyst explaining the numbers and recommending practical actions to business stakeholders.

---

## 1. Customer Revenue Concentration

The customer base shows high revenue concentration:

* **Champions and Loyal Customers represent 38.04% of customers (3,804 accounts) but generate 76.16% of total revenue (\$23,631,866.97).**
* Decile analysis of paying customers reveals:
  * **Top 10% of customers (893 accounts)**: Generate **\$11,513,276.97** (37.11% of revenue).
  * **Top 20% of customers (1,786 accounts)**: Generate **\$17,953,924.46** (57.86% of revenue).
  * **Bottom 30% of customers (2,676 accounts)**: Generate only **\$807,236.04** (2.60% of revenue).

**What this means**: The business relies heavily on a core cohort of repeat buyers. Losing a small fraction of these top accounts has a disproportionate impact on top-line revenue compared to losing hundreds of low-frequency buyers.

---

## 2. Customer Lifecycle & RFM Breakdown

Segmenting the 10,000 customer accounts across Recency, Frequency, and Monetary spend provides a clear breakdown of customer health:

| Segment Name | Customer Count | % of Customers | Total Net Revenue | % of Revenue | Avg Orders / Cust | Avg Recency |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Champions** | 2,150 | 21.50% | \$17,187,268.70 | 55.39% | 23.9 | 11.7 days |
| **Loyal Customers** | 1,654 | 16.54% | \$6,444,598.27 | 20.77% | 12.0 | 100.5 days |
| **At Risk** | 1,000 | 10.00% | \$4,099,567.19 | 13.21% | 12.1 | 401.2 days |
| **Promising** | 1,441 | 14.41% | \$1,426,446.27 | 4.60% | 3.2 | 283.5 days |
| **Hibernating** | 1,976 | 19.76% | \$705,553.51 | 2.27% | 1.7 | 539.4 days |
| **Cannot Lose Them** | 110 | 1.10% | \$587,672.52 | 1.89% | 15.9 | 529.9 days |
| **Potential Loyalists** | 570 | 5.70% | \$572,474.59 | 1.85% | 4.7 | 31.0 days |
| **New Customers** | 24 | 0.24% | \$4,998.90 | 0.02% | 1.0 | 90.1 days |
| **Inactive / Unactivated** | 1,075 | 10.75% | \$0.00 | 0.00% | 0.0 | N/A |
| **Total Base** | **10,000** | **100.00%** | **\$31,028,579.95** | **100.00%** | **9.6** | **232.0 days** |

### Key Lifecycle Observations
1. **Dormant VIP Accounts**: The combined *At Risk* and *Cannot Lose Them* segments contain **1,110 accounts** that spent **\$4,687,239.71 historically** (15.1% of all revenue). These customers averaged 12 to 16 orders each in the past, but have not ordered in 400 to 530 days. They represent the highest-ROI opportunity for targeted re-engagement.
2. **Onboarding Leakage**: Exactly **1,075 registered customers (10.75%)** never completed an order. This points to friction in the initial post-signup experience.
3. **Mid-Tier Momentum**: *Potential Loyalists* (570 accounts, \$572K revenue) have recent purchase activity (average recency 31 days) and average 4.7 orders. They are prime candidates to graduate into Loyal Customers with cross-category product recommendations.

---

## 3. Product Category Profitability & Margin Disparity

Analyzing sales across the five product departments shows an inverse relationship between revenue volume and profit margin:

| Category | Net Revenue | % of Revenue | Gross Profit | Category Margin | Total Units Sold |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Electronics** | \$15,208,081.71 | 49.01% | \$3,651,605.35 | **24.01%** | 82,900 |
| **Home** | \$4,879,531.09 | 15.73% | \$2,109,241.05 | **43.23%** | 43,267 |
| **Sports** | \$1,921,805.15 | 6.19% | \$973,865.23 | **50.67%** | 24,015 |
| **Apparel** | \$5,508,460.75 | 17.75% | \$3,398,349.52 | **61.69%** | 56,128 |
| **Beauty** | \$3,510,701.25 | 11.31% | \$2,608,189.58 | **74.31%** | 46,242 |
| **Total** | **\$31,028,579.95** | **100.00%** | **\$12,461,250.73** | **40.16%** | **252,552** |

### Key Category Takeaways
* **Electronics generates volume, not margin**: Electronics drives nearly half of all gross revenue (\$15.21M), but yields only 24.01% margin.
* **Beauty and Apparel generate high margins**: Beauty generates \$2.61M in gross profit from just \$3.51M in net sales (74.31% margin), and Apparel delivers \$3.40M profit from \$5.51M sales (61.69% margin). Shifting marketing spend toward Beauty and Apparel would improve overall company margins.

---

## 4. Fulfillment Friction: Refunds and Cancellations

Out of 103,695 valid orders, 8,169 orders were either refunded or cancelled before fulfillment:

* **Refunded Orders**: 4,087 orders (3.94%) → **\$1,334,921.53 lost revenue**
* **Cancelled Orders**: 4,082 orders (3.94%) → **\$1,363,385.23 lost revenue**
* **Total Friction Loss**: **\$2,698,306.76** (8.00% of gross invoiced sales)

### Category Friction Breakdown
* **Electronics**: Incurred **\$1,360,782.98 in returns and cancellations** (more than 50% of all company friction). Because electronics items have high unit prices and low margins, reverse logistics and restocking costs hit this category especially hard.
* **Apparel**: Incurred **\$462,805.10 in friction** (primarily sizing-related returns).

---

## 5. Product SKU Concentration

Product-level revenue is also concentrated:
* Out of 492 active catalog products, the **top 10 products generate \$2,845,920.00 (9.17% of total revenue)**.
* The top 20% of products (98 SKUs) drive **54.2% of total sales**.
* 45 products have generated fewer than 10 orders over the entire 30 active transaction months. These slow-moving SKUs tie up working capital and should be evaluated for rationalization.

---

## 6. Customer Attrition Risk & Churn Modeling

### Baseline Risk Distribution
Combining RFM recency with order velocity trend and refund frequency categorizes the 10,000 customers into four risk levels:

| Risk Tier | Risk Score Range | Customer Count | % of Customers | Historical Net Spend | % of Past Spend |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **LOW** | 0–24 | 3,684 | 36.84% | \$19,662,873.78 | 63.37% |
| **MEDIUM** | 25–49 | 2,042 | 20.42% | \$898,811.08 | 2.90% |
| **HIGH** | 50–74 | 2,495 | 24.95% | \$7,757,734.63 | 25.00% |
| **CRITICAL** | 75–100 | 1,779 | 17.79% | \$2,709,160.46 | 8.73% |
| **High + Critical Combined** | **50–100** | **4,274** | **42.74%** | **\$10,466,895.09** | **33.73%** |

### Historical Revenue Exposure
The **\$10,466,895.09** associated with High and Critical risk customers represents **Historical Revenue Exposure** — the past cumulative revenue generated by accounts currently exhibiting warning signs of churn. This is an indicator of relationship value at stake, not a guaranteed future revenue loss.

### Predictive Model Performance (Out-of-Time Test Cohort, N = 8,873)
* **Logistic Regression (Primary)**:
  * ROC-AUC: **0.9481** | Accuracy: **87.29%** | Precision: **94.39%** | Recall: **84.18%** | F1: **0.8900**
  * Top churn drivers: long recency (`recency_days`), declining purchase velocity (`revenue_trend`), and low recent order ratio (`recent_order_ratio`).
* **Decision Threshold Trade-offs**:
  * At threshold **0.30**: Recall rises to **91.14%** (captures 4,938 churners), with precision at 87.06%. Best for low-cost digital retargeting.
  * At threshold **0.50**: Balances precision (**94.39%**) and recall (**84.18%**). Targets 4,832 accounts with only 271 false alarms.
  * At threshold **0.70**: Precision reaches **98.77%** with 53 false alarms. Best for expensive outbound account rep outreach.

---

## 7. Recommended Business Actions

Based on these findings, I recommend five practical actions:

### Action 1: Protect the Top 38%
Champions and Loyal Customers generate 76.16% of revenue. Set up a dedicated VIP loyalty tier with perks that do not hurt product margins: early access to product releases, dedicated customer service, and annual loyalty rewards.

### Action 2: Run a Win-Back Campaign for Dormant VIPs
Target the 1,110 customers in *At Risk* and *Cannot Lose Them* (\$4.69M historical spend). Because these customers have demonstrated high willingness to pay, an email or SMS win-back series offering a 15% discount on high-margin categories (Beauty or Apparel) is economically justified.

### Action 3: Automate Signup Onboarding
Address the 1,075 unactivated registered accounts (10.75% of customer base). Set up an automated 3-part welcome email sequence triggered on days 1, 3, and 7 after signup, featuring best-selling hero products and a first-order discount code.

### Action 4: Audit Electronics Returns
Electronics accounts for \$1.36M in refunds and cancellations while operating on a 24.01% gross margin. Implement detailed return-reason surveys at checkout, audit product descriptions on top returned SKUs, and consider updated packaging to reduce transit damage.

### Action 5: Calibrate Retention Spending Using Churn Probabilities
Do not offer discounts across the board. Use the model's churn probability to match marketing cost to customer value:
* **Low-cost email flows** for medium-risk accounts (probability 0.30 to 0.50).
* **Direct sales/CSM outreach or gift cards** for high-value Champions and Loyal accounts whose churn probability exceeds 0.60.
