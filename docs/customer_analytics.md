# Customer Analytics, RFM Segmentation & Churn Risk Engine

**Project:** Business Intelligence & Customer Analytics Platform  
**Target Role:** ZS Business Technology Solutions (BTS) Associate  
**Stage:** Phase 4 — Production Analytics & Predictive Risk Layer  
**Engine Compatibility:** PostgreSQL (Production) & SQLite 3.35+ (Local Staging)  
**Reconciliation Status:** Confirmed Match with Phase 3 Analytics (\$31,028,579.95 Net Revenue)

---

## 1. Executive Summary

This module implements customer analytics and churn modeling to turn raw order histories into customer lifecycle segments, rule-based risk tiers, and time-aware churn predictions.

### Key Business Metrics at a Glance
* **Total Customer Base:** 10,000 accounts
* **Active Paying Accounts:** 8,925 (89.25%)
* **Unactivated / Zero-Order Accounts:** 1,075 (10.75%)
* **Realized Net Revenue:** \$31,028,579.95 (100.0% reconciled against Phase 3 data warehouse views)
* **Realized Gross Profit:** \$12,461,250.73 (40.16% gross margin)
* **Out-of-Time Churn Model ROC-AUC:** 0.9481 (Logistic Regression) vs 0.9510 (Random Forest)
* **Model Precision / Recall (Default 0.50 Threshold):** 94.39% Precision, 84.18% Recall, 89.00% F1-score

---

## 2. Anti-Leakage Temporal Modeling Architecture

Predicting customer churn using transactional data carries high risks of **data leakage** if features are calculated across the entire dataset and split afterwards. In this platform, strict **Out-Of-Time (OOT) temporal validation** is enforced:

```
Full History: 2022-01-01 to 2024-06-30 (30 Months)
---------------------------------------------------------------------------------------------------
TRAIN COHORT:
  Feature Calculation Cutoff : Order Date <= 2023-12-31
  Forward Churn Outcome Window: 2024-01-01 to 2024-03-31 (Q1 2024, 90 Days)
  Eligible Base              : 7,664 Customers with >= 1 completed order <= 2023-12-31
  Actual Churn Rate          : 60.27% (4,619 churned, 3,045 retained)

TEST COHORT (Out-Of-Time Validation):
  Feature Calculation Cutoff : Order Date <= 2024-03-31
  Forward Churn Outcome Window: 2024-04-01 to 2024-06-30 (Q2 2024, 90 Days)
  Eligible Base              : 8,873 Customers with >= 1 completed order <= 2024-03-31
  Actual Churn Rate          : 61.06% (5,418 churned, 3,455 retained)
---------------------------------------------------------------------------------------------------
```

### Anti-Leakage Guarantees:
1. **Cutoff-Enforced Feature Boundaries:** For any evaluation cutoff date $T$, all order counts, spend, recency, and activity ratios are calculated strictly using orders where `order_date <= T` and customers where `signup_date <= T`.
2. **Outcome Isolation:** A customer is labeled as **Churned (`is_churned = 1`)** if and only if they make **zero completed orders** during the prospective 90-day window following cutoff $T$.
3. **Strict Preprocessing Isolation:** Feature scaling (`StandardScaler`) is fitted **exclusively on training features** (`X_train`) and transformed out-of-sample on test features (`X_test`) and production inference.
4. **No Identity Leakage:** Identifiers (`customer_id`, `name`) and target indicators are strictly excluded from the model feature matrix.

---

## 3. Customer Feature Store & Mathematical Definitions

The customer feature layer (`src/modeling/features.py` and `sql/customer_model_features.sql`) extracts 14 core predictive features:

| Feature Name | Type | Formula / Business Logic | Churn Signal Intuition |
| :--- | :--- | :--- | :--- |
| `recency_days` | Integer | $\Delta \text{Days}(\text{Cutoff Date}, \text{Last Completed Order Date})$ | High recency indicates growing dormancy |
| `completed_orders` | Integer | $\sum \mathbf{1}_{\{\text{status} \in [\text{'Completed'}, \text{'Shipped'}] \land \text{date} \le T\}}$ | Core repeat purchasing cadence |
| `total_revenue` | Float | $\sum (\text{quantity} \times \text{price})_{\text{completed}}$ | Cumulative historical customer spend |
| `total_profit` | Float | $\sum (\text{price} - \text{cost}) \times \text{quantity}_{\text{completed}}$ | Lifetime gross margin contribution |
| `average_order_value` | Float | $\text{total\_revenue} / \max(1, \text{completed\_orders})$ | Spending power per transaction basket |
| `active_months` | Integer | $\text{CountDistinct}(\text{YYYY-MM}(\text{order\_date}))$ | Regularity of engagement over time |
| `refund_rate` | Float | $\text{refunded\_orders} / \max(1, \text{total\_orders})$ | Fulfillment or product satisfaction friction |
| `cancellation_rate` | Float | $\text{cancelled\_orders} / \max(1, \text{total\_orders})$ | Checkout or buyer remorse friction |
| `recent_revenue_ratio`| Float | $\text{revenue}_{\text{last 90d}} / \max(1, \text{total\_revenue})$ | Share of spend occurring recently |
| `recent_order_ratio`  | Float | $\text{orders}_{\text{last 90d}} / \max(1, \text{completed\_orders})$ | Velocity of order activity |
| `revenue_trend` | Float | $\frac{\text{recent\_rev} - (\text{hist\_rev} / 3.0)}{\text{total\_revenue} + 10.0}$ | Spend trajectory (+ acceleration, - deceleration) |
| `customer_lifetime_days`| Integer | $\Delta \text{Days}(\text{First Order}, \text{Last Order})$ | Active lifespan span in days |
| `account_age_days` | Integer | $\Delta \text{Days}(\text{Cutoff Date}, \text{Signup Date})$ | Days since customer registration |
| `order_frequency_monthly`| Float | $\text{completed\_orders} / (\text{account\_age\_days} / 30.0)$ | Normalized monthly purchasing frequency |

---

## 4. RFM Quintile Segmentation

The RFM segmentation engine (`src/modeling/rfm.py`) divides the active paying population into 5 statistical quintiles ($R \in [1..5], F \in [1..5], M \in [1..5]$). Unactivated accounts are assigned $R=0, F=0, M=0$.

### RFM Segment Distribution (10,000 Accounts)

| Customer Segment | Customer Count | % Customers | Total Revenue (\$) | % Revenue | Avg Spend (\$) | Avg Orders | Avg Recency (Days) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Champions** | 2,150 | 21.50% | \$17,187,268.70 | 55.39% | \$7,994.08 | 23.9 | 11.7 |
| **Loyal Customers** | 1,654 | 16.54% | \$6,444,598.27 | 20.77% | \$3,896.37 | 12.0 | 100.5 |
| **At Risk** | 1,000 | 10.00% | \$4,099,567.19 | 13.21% | \$4,099.57 | 12.1 | 401.2 |
| **Promising** | 1,441 | 14.41% | \$1,426,446.27 | 4.60% | \$989.90 | 3.2 | 283.5 |
| **Hibernating** | 1,976 | 19.76% | \$705,553.51 | 2.27% | \$357.06 | 1.7 | 539.4 |
| **Cannot Lose Them** | 110 | 1.10% | \$587,672.52 | 1.89% | \$5,342.48 | 15.9 | 529.9 |
| **Potential Loyalists**| 570 | 5.70% | \$572,474.59 | 1.84% | \$1,004.34 | 4.7 | 31.0 |
| **New Customers** | 24 | 0.24% | \$4,998.90 | 0.02% | \$208.29 | 1.0 | 90.1 |
| **Inactive / Unactivated** | 1,075 | 10.75% | \$0.00 | 0.00% | \$0.00 | 0.0 | 999.0 |
| **Total / Base Average** | **10,000** | **100.0%** | **\$31,028,579.95** | **100.0%** | **\$3,102.86** | **9.6** | **315.6** |

### Commercial Observations:
1. **Pareto Concentration:** The top two segments (*Champions* and *Loyal Customers*) represent **38.04% of customers** but generate **76.16% of total revenue** (\$23.63M).
2. **Critical Revenue Exposure:** The *At Risk* and *Cannot Lose Them* segments represent **\$4.69M in historical revenue** (15.10% of company revenue) that is currently dormant (average recency > 400–530 days).

---

## 5. Multi-Factor Rule-Based Risk Engine

To provide transparency and immediate actionability, a deterministic rule engine (`src/modeling/risk_rules.py`) scores each account from **0 to 100** based on operational penalties:

* **Recency Decay Penalty (up to 40 pts):** Escalates from 15 pts (>90 days) to 40 pts (>365 days).
* **Frequency Slowdown Penalty (up to 25 pts):** Triggers when repeat buyers (historically $\ge 2$ or $\ge 5$ orders) place zero orders in the last 90 days.
* **High-Value Account Exposure (up to 20 pts):** Triggers when high-spend customers (\$1,500+ or \$3,000+) show recency $>90$ days.
* **Fulfillment & Return Friction (up to 15 pts):** Penalizes accounts with refund rates exceeding 15%.
* **Unactivated Onboarding Risk (85 pts):** Automatically assigns unactivated accounts to `CRITICAL` risk.

### Risk Tier Breakdown

| Risk Level | Score Range | Customer Count | % Customers | Total Revenue (\$) | % Revenue Exposure | Avg Recency (Days) | Avg Orders |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **LOW** | 0 – 24 | 3,684 | 36.84% | \$19,662,873.78 | 63.37% | 22.4 | 16.3 |
| **MEDIUM** | 25 – 49 | 2,042 | 20.42% | \$898,811.08 | 2.90% | 406.7 | 1.8 |
| **HIGH** | 50 – 74 | 2,495 | 24.95% | \$7,757,734.63 | 25.00% | 359.6 | 9.7 |
| **CRITICAL** | 75 – 100 | 1,779 | 17.79% | \$2,709,160.46 | 8.73% | 792.0 | 4.2 |
| **Total** | | **10,000** | **100.0%** | **\$31,028,579.95** | **100.0%** | **315.6** | **9.6** |

---

## 6. Out-Of-Time Machine Learning Churn Models

Two classification algorithms were evaluated on the independent **Out-Of-Time Test Cohort** (8,873 customers; evaluated over Q2 2024):

### Model Evaluation Scorecard

| Performance Metric | Logistic Regression (Primary) | Random Forest (Comparator) | Business Significance |
| :--- | :---: | :---: | :--- |
| **ROC-AUC Score** | **0.9481** | **0.9510** | Outstanding discrimination across all thresholds |
| **Accuracy** | **87.29%** | **87.56%** | Overall correct classification rate |
| **Precision** | **94.39%** | **96.87%** | Low false alarm rate (marketing budget protected) |
| **Recall** | **84.18%** | **82.28%** | Captures 84%+ of all churning customers |
| **F1-Score** | **0.8900** | **0.8898** | Optimal balance between precision and recall |

### Confusion Matrix (Logistic Regression, Threshold = 0.50)
* **True Negatives (TN):** 3,184 (Correctly predicted retained)
* **False Positives (FP):** 271 (Predicted churned, but purchased — 5.6% false alarm rate)
* **False Negatives (FN):** 857 (Predicted retained, but churned — missed opportunities)
* **True Positives (TP):** 4,561 (Correctly caught churners)

### Model Interpretability: Standardized Feature Coefficients

Logistic Regression standardized coefficients indicate the relative log-odds shift per one standard deviation increase in each feature:

```
Top Churn Risk Drivers:
  (+) account_age_days          : +4.5173 (Older registered accounts without recent orders are most at risk)
  (+) recency_days              : +2.5973 (Days since last purchase strongly elevates abandonment odds)
  (+) recent_revenue_ratio      : +1.0857 (Short-term concentrated bursts with sudden cutoffs)
  (+) recent_order_ratio        : +0.4819 (Order skew)
  (+) total_profit              : +0.1220 (Margin volume proxy)

Top Retention Drivers:
  (-) customer_lifetime_days    : -2.7233 (Long sustained purchasing spans strongly protect retention)
  (-) revenue_trend             : -1.0255 (Positive momentum strongly mitigates churn risk)
  (-) active_months             : -0.1926 (Consistent cross-season engagement)
  (-) total_revenue             : -0.1369 (Total cumulative investment)
  (-) refund_rate               : -0.1359 (Customers who engage through refund resolution remain active)
```

---

## 7. Decision Threshold Trade-Off Analysis

In enterprise churn management, the decision threshold directly governs the operational campaign size and retention budget ROI:

| Threshold | Precision | Recall | F1-Score | Targeted Customers | False Alarms | Recommended Use Case |
| :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| **0.30** | 87.06% | **91.14%** | 0.8905 | 5,672 | 734 | **Aggressive Low-Cost Win-Back:** Email/SMS push campaigns where cost per outreach is near zero. |
| **0.40** | 90.92% | 87.80% | **0.8933** | 5,232 | 475 | **Balanced Growth Campaign:** Standard digital coupon and personalized catalogue delivery. |
| **0.50** | **94.39%** | 84.18% | 0.8900 | 4,832 | 271 | **Baseline Enterprise Setting:** Primary operational production threshold. |
| **0.60** | 97.35% | 81.21% | 0.8855 | 4,520 | 120 | **High-Cost Retention Inventions:** Direct outbound calls, dedicated account reps. |
| **0.70** | **98.77%** | 78.26% | 0.8732 | 4,293 | 53 | **VIP Executive Concierge:** Expensive physical gifts, VIP concierge win-back calls. |

---

## 8. Rule-Based Engine vs. Machine Learning Comparison

| Architectural Dimension | Rule-Based Risk Engine | Machine Learning Churn Model |
| :--- | :--- | :--- |
| **Primary Strength** | 100% transparent, deterministic, instant executive buy-in. | Uncovers non-linear, multi-variate interaction effects. |
| **Cold-Start Handling** | Fully handles zero-order and newly registered accounts. | Requires historical transaction activity for feature generation. |
| **Output Type** | Discrete score (0–100) and categorical risk tiers. | Continuous calibrated probability ($p \in [0, 1]$). |
| **Action Mapping** | Directly linked to rule triggers (e.g. refund friction playbook). | Governed by threshold optimization and customer lifetime value. |
| **Production Role** | **Baseline Operational Governance:** Immediate onboarding & compliance checks. | **Predictive Optimization:** High-ROI targeted retention and budget allocation. |

---

## 9. Strategic Commercial Playbooks

### Playbook A: "Cannot Lose Them" & "At Risk" High-Value Win-Back
* **Target Audience:** Customers in RFM segments *Cannot Lose Them* and *At Risk* with `risk_level` $\in [\text{'HIGH'}, \text{'CRITICAL'}]$.
* **Revenue at Stake:** \$4.69M across 1,110 accounts.
* **Prescribed Action:**
  1. Automated tier escalation to outbound customer success / concierge.
  2. Targeted high-incentive reactivation offer (20% margin-subsidized discount on favorite categories).
  3. Executive outreach survey to identify fulfillment or product catalog dissatisfaction.

### Playbook B: Champions & Loyal Customer Retention Acceleration
* **Target Audience:** Customers in *Champions* and *Loyal Customers* ($n=3,804$, generating 76.16% of revenue).
* **Prescribed Action:**
  1. Enrollment into exclusive Tier-1 VIP loyalty program with early access to new product drops.
  2. Personalized category cross-sell recommendations (maximizing basket diversity).
  3. Free express shipping threshold removal to sustain purchase momentum.

### Playbook C: Unactivated Customer Onboarding Rescue
* **Target Audience:** 1,075 registered customers with 0 completed orders.
* **Prescribed Action:**
  1. Trigger 3-part automated onboarding email drip focused on top 5 hero products.
  2. First-purchase incentive (\$15 off first order over \$50).
  3. SMS abandoned-cart follow-up for accounts showing browsing activity.

---

## 10. Verification & Reconciliation Summary

1. **Exact Customer Count:** 10,000 unique records in `data/processed/customer_analytics.csv` and `staging.db:customer_analytics`.
2. **Net Revenue Reconciliation:**
   $$\sum \text{total\_revenue} = \$31,028,579.95 \quad (\Delta = \$0.00 \text{ vs Phase 3 views})$$
3. **Data Integrity:** No null values in RFM scores, risk tiers, or churn probabilities.
4. **Leakage Verification:** 100% verified cutoff isolation via automated test suite.
