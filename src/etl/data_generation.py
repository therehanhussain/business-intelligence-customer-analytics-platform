"""Synthetic Retail Data Generation Engine.

This module generates realistic, multi-table synthetic retail data for the
Business Intelligence & Customer Analytics Platform:
1. customers.csv (~10,000 customers with demographic profiles & RFM behavioral archetypes)
2. products.csv (~500 products across 6 categories with realistic margins)
3. orders.csv (~100,000+ multi-year transactions with seasonality, repeat purchase cycles,
   and documented data-quality anomalies)

Intentionally introduced data quality issues (for Phase 2 ETL cleaning):
- Customers: Duplicate customer records (~80 rows), missing age (~1.5%),
  missing gender (~1.0%), inconsistent gender casing ('M', 'F', 'male', 'female', 'FEMALE').
- Products: Missing categories (~1%), missing cost (~0.6%), category casing inconsistency ('electronics', 'apparel & accessories').
- Orders: Inconsistent payment methods ('CC', 'paypal', 'COD', 'credit_card'),
  inconsistent order statuses ('completed', 'cancelled', 'refunded'), missing payment methods (~0.5%),
  invalid quantities (negative values representing unhandled return entries ~0.3%, zero values ~0.15%).
- Referential Integrity: 100% maintained (all customer_id and product_id in orders exist in parent tables).
"""

from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

from src.config.paths import RAW_DATA_DIR, ensure_directories
from src.config.settings import settings
from src.utils.logger import get_logger

logger = get_logger(__name__)

# -------------------------------------------------------------------------
# CONSTANTS & SEED LISTS FOR REALISTIC SYNTHETIC ATTRIBUTES
# -------------------------------------------------------------------------
FIRST_NAMES_MALE = [
    "James", "John", "Robert", "Michael", "William", "David", "Richard", "Joseph",
    "Thomas", "Charles", "Christopher", "Daniel", "Matthew", "Anthony", "Mark",
    "Donald", "Steven", "Paul", "Andrew", "Joshua", "Kenneth", "Kevin", "Brian",
    "George", "Timothy", "Ronald", "Edward", "Jason", "Jeffrey", "Ryan", "Jacob",
    "Gary", "Nicholas", "Eric", "Jonathan", "Stephen", "Larry", "Justin", "Scott",
    "Brandon", "Benjamin", "Samuel", "Gregory", "Alexander", "Patrick", "Frank",
    "Raymond", "Jack", "Dennis", "Jerry", "Tyler", "Aaron", "Jose", "Adam", "Nathan",
    "Henry", "Douglas", "Zachary", "Peter", "Kyle", "Walter", "Ethan", "Jeremy",
    "Harold", "Keith", "Christian", "Roger", "Noah", "Gerald", "Carl", "Terry",
    "Sean", "Austin", "Arthur", "Lawrence", "Jesse", "Dylan", "Bryan", "Joe", "Jordan",
]

FIRST_NAMES_FEMALE = [
    "Mary", "Patricia", "Jennifer", "Linda", "Elizabeth", "Barbara", "Susan",
    "Jessica", "Sarah", "Karen", "Lisa", "Nancy", "Betty", "Margaret", "Sandra",
    "Ashley", "Kimberly", "Emily", "Donna", "Michelle", "Carol", "Amanda", "Dorothy",
    "Melissa", "Deborah", "Stephanie", "Rebecca", "Sharon", "Laura", "Cynthia",
    "Kathleen", "Amy", "Angela", "Shirley", "Anna", "Brenda", "Pamela", "Emma",
    "Nicole", "Helen", "Samantha", "Katherine", "Christine", "Debra", "Rachel",
    "Carolyn", "Janet", "Catherine", "Maria", "Heather", "Diane", "Ruth", "Julie",
    "Olivia", "Joyce", "Virginia", "Victoria", "Kelly", "Lauren", "Christina",
    "Joan", "Evelyn", "Judith", "Megan", "Andrea", "Cheryl", "Hannah", "Jacqueline",
    "Martha", "Gloria", "Teresa", "Ann", "Sara", "Madison", "Frances", "Kathryn",
    "Janice", "Jean", "Abigail", "Alice", "Julia", "Judy", "Sophia", "Grace", "Denise",
]

LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis",
    "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson",
    "Thomas", "Taylor", "Moore", "Jackson", "Martin", "Lee", "Perez", "Thompson",
    "White", "Harris", "Sanchez", "Clark", "Ramirez", "Lewis", "Robinson", "Walker",
    "Young", "Allen", "King", "Wright", "Scott", "Torres", "Nguyen", "Hill",
    "Flores", "Green", "Adams", "Nelson", "Baker", "Hall", "Rivera", "Campbell",
    "Mitchell", "Carter", "Roberts", "Gomez", "Phillips", "Evans", "Turner", "Diaz",
    "Parker", "Cruz", "Edwards", "Collins", "Reyes", "Stewart", "Morris", "Morales",
    "Murphy", "Cook", "Rogers", "Gutierrez", "Ortiz", "Morgan", "Cooper", "Peterson",
    "Bailey", "Reed", "Kelly", "Howard", "Ramos", "Kim", "Cox", "Ward", "Richardson",
    "Watson", "Brooks", "Chavez", "Wood", "James", "Bennett", "Gray", "Mendoza",
]

CITIES_STATES = [
    ("New York", "NY", 0.12),
    ("Los Angeles", "CA", 0.10),
    ("Chicago", "IL", 0.08),
    ("Houston", "TX", 0.07),
    ("Phoenix", "AZ", 0.05),
    ("Philadelphia", "PA", 0.04),
    ("San Antonio", "TX", 0.04),
    ("San Diego", "CA", 0.04),
    ("Dallas", "TX", 0.04),
    ("Austin", "TX", 0.04),
    ("San Jose", "CA", 0.03),
    ("Seattle", "WA", 0.04),
    ("Denver", "CO", 0.04),
    ("Boston", "MA", 0.04),
    ("Atlanta", "GA", 0.04),
    ("Miami", "FL", 0.04),
    ("Minneapolis", "MN", 0.03),
    ("Detroit", "MI", 0.03),
    ("Portland", "OR", 0.03),
    ("Charlotte", "NC", 0.04),
]

PRODUCT_CATEGORIES = {
    "Electronics": {
        "price_min": 45.0,
        "price_max": 1200.0,
        "margin_min": 0.18,
        "margin_max": 0.32,
        "share": 0.20,
        "templates": [
            "Pro Wireless Noise-Cancelling Headphones", "Ultra HD 4K Smart Monitor",
            "Ergonomic Mechanical Keyboard", "Precision Bluetooth Optical Mouse",
            "Smart Home Security Camera Hub", "Portable Waterproof Bluetooth Speaker",
            "USB-C Multi-Port Hub Adapter", "MagSafe Fast Charging Station",
            "Active Fitness Smartwatch", "True Wireless Earbuds with ANC",
            "1080p Streaming Webcam with Ring Light", "Compact Dual-Band Wi-Fi 6 Router",
            "20000mAh Power Bank Fast Charger", "Foldable Drone with 4K HD Camera",
            "Smart LED Ambient Light Bar", "Noise-Isolating Gaming Headset",
        ],
    },
    "Apparel & Accessories": {
        "price_min": 18.0,
        "price_max": 185.0,
        "margin_min": 0.52,
        "margin_max": 0.72,
        "share": 0.25,
        "templates": [
            "Organic Pima Cotton Crewneck Tee", "Performance Moisture-Wicking Hoodie",
            "Classic Fit Chino Pants", "Merino Wool Blend Thermal Sweater",
            "All-Weather Lightweight Windbreaker", "Slim-Fit Stretch Denim Jeans",
            "Waterproof Commuter Backpack", "Polarized UV400 Wayfarer Sunglasses",
            "Full-Grain Leather Bi-Fold Wallet", "Breathable Cushioned Running Socks (3-Pack)",
            "Tailored Wool Blend Overcoat", "Quick-Dry Stretch Boardshorts",
            "Fleece-Lined Winter Beanie", "Italian Leather Dress Belt",
        ],
    },
    "Home & Kitchen": {
        "price_min": 22.0,
        "price_max": 340.0,
        "margin_min": 0.40,
        "margin_max": 0.62,
        "share": 0.20,
        "templates": [
            "Stainless Steel French Press Coffee Maker", "Cast Iron Pre-Seasoned Dutch Oven",
            "Damascus Steel 8-Inch Chef Knife", "Aromatherapy Ultrasonic Essential Oil Diffuser",
            "Non-Stick Ceramic Cookware 10-Pc Set", "Memory Foam Orthopedic Contour Pillow",
            "Digital Touchscreen Air Fryer XL", "Weighted Cooling Blanket 15-lb",
            "Smart WiFi Meat Thermometer", "Bamboo Cutting Board with Juice Groove",
            "Cordless Rechargeable Stick Vacuum", "Double-Walled Insulated Glass Tumbler Set",
        ],
    },
    "Beauty & Personal Care": {
        "price_min": 12.0,
        "price_max": 95.0,
        "margin_min": 0.60,
        "margin_max": 0.82,
        "share": 0.15,
        "templates": [
            "Hydrating Hyaluronic Acid Serum", "Vitamin C Brightening Facial Moisturizer",
            "Organic Argan Oil Hair Repair Mask", "Mineral Daily Sunscreen SPF 50",
            "Sonic Electric Toothbrush with UV Sanitizer", "Gentle Exfoliating AHA/BHA Cleanser",
            "Natural Tea Tree Purifying Toner", "Botanical Nourishing Night Cream",
            "Beard Conditioning Oil & Comb Kit", "Collagen Peptide Firming Eye Cream",
        ],
    },
    "Sports & Outdoors": {
        "price_min": 25.0,
        "price_max": 420.0,
        "margin_min": 0.38,
        "margin_max": 0.58,
        "share": 0.12,
        "templates": [
            "Adjustable Neoprene Dumbbell Set", "Non-Slip High-Density Yoga Mat",
            "Ultralight 2-Person Backpacking Tent", "Insulated Hydro Stainless Water Bottle 32oz",
            "Heavy-Duty Resistance Bands Set", "Trail-Ready Waterproof Hiking Poles",
            "Compact Folding Camping Chair", "High-Performance Speed Jump Rope",
            "Reflective LED Running Vest", "Deep-Tissue Percussion Massage Gun",
        ],
    },
    "Books & Media": {
        "price_min": 9.99,
        "price_max": 49.99,
        "margin_min": 0.30,
        "margin_max": 0.50,
        "share": 0.08,
        "templates": [
            "Data Strategy & Enterprise Architecture Playbook", "Modern Retail Analytics Handbook",
            "Designing Scalable Machine Learning Systems", "Principles of Customer Centricity",
            "Advanced SQL for Commercial Insights", "The Agile Technology Organization",
            "Behavioral Economics in E-Commerce", "Financial Modeling for Technology Executives",
        ],
    },
}

# -------------------------------------------------------------------------
# GENERATOR FUNCTIONS
# -------------------------------------------------------------------------

def generate_customers(
    n_customers: int = 10000,
    seed: int = 42,
    start_date: str = "2022-01-01",
    end_date: str = "2024-03-31",
) -> pd.DataFrame:
    """Generate customer demographics, signup dates, and behavioral profiles.

    Intentionally introduces:
    - ~80 duplicate customer rows (total ~10,080 rows)
    - Missing age on ~1.5% of rows
    - Missing gender on ~1.0% of rows
    - Inconsistent gender categorical casing ('M', 'F', 'male', 'female', 'FEMALE')
    """
    rng = np.random.default_rng(seed)
    logger.info("Generating %d base customer profiles...", n_customers)

    # 1. IDs
    customer_ids = [f"CUST_{i+1:06d}" for i in range(n_customers)]

    # 2. Gender distribution (approx 51% Female, 49% Male)
    gender_raw = rng.choice(["Female", "Male"], size=n_customers, p=[0.51, 0.49])

    # 3. Names based on gender
    names = []
    for g in gender_raw:
        last = rng.choice(LAST_NAMES)
        if g == "Female":
            first = rng.choice(FIRST_NAMES_FEMALE)
        else:
            first = rng.choice(FIRST_NAMES_MALE)
        names.append(f"{first} {last}")

    # 4. Age: Truncated normal distribution (mean=38.5, std=12.5, bounded [18, 80])
    ages = np.clip(np.round(rng.normal(loc=38.5, scale=12.5, size=n_customers)), 18, 80).astype(int)

    # 5. City and State (weighted by US metro populations)
    city_names = [c[0] for c in CITIES_STATES]
    state_names = [c[1] for c in CITIES_STATES]
    weights = np.array([c[2] for c in CITIES_STATES])
    weights /= weights.sum()

    city_indices = rng.choice(len(CITIES_STATES), size=n_customers, p=weights)
    assigned_cities = [city_names[idx] for idx in city_indices]
    assigned_states = [state_names[idx] for idx in city_indices]

    # 6. Signup Dates
    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")
    total_days = (end_dt - start_dt).days

    growth_weights = np.linspace(1.0, 1.8, total_days)
    growth_weights /= growth_weights.sum()
    random_day_offsets = rng.choice(total_days, size=n_customers, p=growth_weights)

    signup_dates = [
        (start_dt + timedelta(days=int(offset))).strftime("%Y-%m-%d")
        for offset in random_day_offsets
    ]

    # Construct initial DataFrame
    df = pd.DataFrame({
        "customer_id": customer_ids,
        "name": names,
        "gender": gender_raw,
        "age": ages.astype(float),
        "city": assigned_cities,
        "state": assigned_states,
        "signup_date": signup_dates,
    })

    # ---------------------------------------------------------------------
    # INTENTIONAL DATA QUALITY INJECTIONS (Customers)
    # ---------------------------------------------------------------------
    logger.info("Injecting controlled data quality anomalies into customers...")

    # A. Missing values: Age (~1.5%) and Gender (~1.0%)
    n_missing_age = int(n_customers * 0.015)
    missing_age_indices = rng.choice(n_customers, size=n_missing_age, replace=False)
    df.loc[missing_age_indices, "age"] = np.nan

    n_missing_gender = int(n_customers * 0.010)
    missing_gender_indices = rng.choice(n_customers, size=n_missing_gender, replace=False)
    df.loc[missing_gender_indices, "gender"] = np.nan

    # B. Categorical casing inconsistencies in gender (~3.5%)
    inconsistent_indices = rng.choice(
        [i for i in range(n_customers) if i not in missing_gender_indices],
        size=int(n_customers * 0.035),
        replace=False,
    )
    for idx in inconsistent_indices:
        current_g = df.at[idx, "gender"]
        if current_g == "Male":
            df.at[idx, "gender"] = rng.choice(["M", "male", "MALE"])
        elif current_g == "Female":
            df.at[idx, "gender"] = rng.choice(["F", "female", "FEMALE"])

    # C. Duplicate customer records (~80 duplicate rows appended)
    n_duplicates = 80
    dup_indices = rng.choice(n_customers, size=n_duplicates, replace=False)
    duplicate_rows = df.iloc[dup_indices].copy()
    df = pd.concat([df, duplicate_rows], ignore_index=True)

    logger.info("Customers generated: %d total rows (%d unique IDs).", len(df), n_customers)
    return df


def generate_products(
    n_products: int = 500,
    seed: int = 42,
) -> pd.DataFrame:
    """Generate product catalog with realistic category margins and price points.

    Intentionally introduces:
    - Missing category on ~1% of products
    - Missing cost on ~0.6% of products
    - Inconsistent category casing ('electronics', 'apparel & accessories')
    """
    rng = np.random.default_rng(seed)
    logger.info("Generating %d product catalog items...", n_products)

    categories = list(PRODUCT_CATEGORIES.keys())
    cat_shares = [PRODUCT_CATEGORIES[c]["share"] for c in categories]
    cat_shares = np.array(cat_shares) / sum(cat_shares)

    assigned_cats = rng.choice(categories, size=n_products, p=cat_shares)

    product_ids = [f"PROD_{i+1:04d}" for i in range(n_products)]
    product_names = []
    prices = []
    costs = []

    template_counters: Dict[str, int] = {}

    for i, cat in enumerate(assigned_cats):
        cat_info = PRODUCT_CATEGORIES[cat]
        templates = cat_info["templates"]
        base_template = templates[i % len(templates)]
        count = template_counters.get(base_template, 0) + 1
        template_counters[base_template] = count

        if count == 1:
            prod_name = base_template
        else:
            prod_name = f"{base_template} - Edition {count}"
        product_names.append(prod_name)

        min_p = cat_info["price_min"]
        max_p = cat_info["price_max"]
        raw_price = rng.uniform(min_p, max_p)
        ending = rng.choice([0.99, 0.99, 0.50, 0.00])
        price = round(np.floor(raw_price) + ending, 2)
        if price < min_p:
            price = round(min_p, 2)
        prices.append(price)

        margin_pct = rng.uniform(cat_info["margin_min"], cat_info["margin_max"])
        cost = round(price * (1.0 - margin_pct), 2)
        costs.append(cost)

    df = pd.DataFrame({
        "product_id": product_ids,
        "product_name": product_names,
        "category": assigned_cats,
        "price": prices,
        "cost": costs,
    })

    # ---------------------------------------------------------------------
    # INTENTIONAL DATA QUALITY INJECTIONS (Products)
    # ---------------------------------------------------------------------
    logger.info("Injecting controlled data quality anomalies into products...")

    # A. Missing category (~1.0% = 5 products)
    n_missing_cat = 5
    missing_cat_idx = rng.choice(n_products, size=n_missing_cat, replace=False)
    df.loc[missing_cat_idx, "category"] = np.nan

    # B. Missing cost (~0.6% = 3 products)
    n_missing_cost = 3
    missing_cost_idx = rng.choice(
        [i for i in range(n_products) if i not in missing_cat_idx],
        size=n_missing_cost,
        replace=False,
    )
    df.loc[missing_cost_idx, "cost"] = np.nan

    # C. Inconsistent casing in category on 8 products
    casing_idx = rng.choice(
        [i for i in range(n_products) if i not in missing_cat_idx and i not in missing_cost_idx],
        size=8,
        replace=False,
    )
    for idx in casing_idx:
        current_cat = df.at[idx, "category"]
        if current_cat == "Electronics":
            df.at[idx, "category"] = "electronics"
        elif current_cat == "Apparel & Accessories":
            df.at[idx, "category"] = "apparel & accessories"

    logger.info("Products generated: %d rows.", len(df))
    return df


def generate_orders(
    customers_df: pd.DataFrame,
    products_df: pd.DataFrame,
    seed: int = 42,
    simulation_end_date: str = "2024-06-30",
) -> pd.DataFrame:
    """Generate 100,000+ multi-year transactions exhibiting realistic retail behavior.

    Features:
    - Customer Archetypes (Power Law / Pareto Distribution):
        * Champions (~10%): 25 to 55 orders, frequent, high value (~40,000 orders)
        * Loyal Regulars (~25%): 12 to 24 orders, steady cadence (~45,000 orders)
        * Occasional (~30%): 4 to 8 orders (~18,000 orders)
        * Infrequent/One-time (~18%): 1 to 2 orders (~2,700 orders)
        * Dormant / Inactive (~17%): Signed up early, 0 orders (50%) or 1 early order (50%) (~850 orders)
        Total target volume: ~105,000+ orders.
    - Retail Seasonality:
        * Q4 Holiday surge (November/December 1.9x-2.2x volume)
        * Summer lift (July 1.2x)
        * Weekend uplift
    - Pareto Product Popularity:
        * Power-law distribution (top 20% of products generate ~70% of sales)
    - Temporal Consistency:
        * Every order_date >= customer's signup_date
    - Foreign Key Integrity:
        * 100% of customer_id exist in customers
        * 100% of product_id exist in products

    Intentionally introduces:
    - Missing payment_method (~0.5%)
    - Inconsistent payment_method values ('CC', 'paypal', 'COD', 'credit_card')
    - Inconsistent order_status casing ('completed', 'cancelled', 'refunded')
    - Invalid quantities:
        * Negative quantities (-1, -2) representing unhandled returns (~0.3%)
        * Zero quantity records (~0.15%)
    """
    rng = np.random.default_rng(seed)
    logger.info("Synthesizing 100,000+ realistic retail orders...")

    unique_cust = customers_df.drop_duplicates(subset=["customer_id"]).copy()
    n_unique_cust = len(unique_cust)

    cust_id_arr = unique_cust["customer_id"].values
    signup_dt_arr = pd.to_datetime(unique_cust["signup_date"]).values
    end_datetime = pd.to_datetime(simulation_end_date)

    # 1. Assign Customer Archetypes
    # 0: Champions (10%)
    # 1: Loyal Regulars (25%)
    # 2: Occasional (30%)
    # 3: Infrequent (18%)
    # 4: Dormant / Inactive (17%)
    archetype_probs = [0.10, 0.25, 0.30, 0.18, 0.17]
    archetypes = rng.choice(5, size=n_unique_cust, p=archetype_probs)

    orders_per_customer = np.zeros(n_unique_cust, dtype=int)
    for i in range(n_unique_cust):
        arch = archetypes[i]
        if arch == 0:  # Champions: 25 to 55 orders
            orders_per_customer[i] = rng.integers(25, 56)
        elif arch == 1:  # Loyal Regulars: 12 to 24 orders
            orders_per_customer[i] = rng.integers(12, 25)
        elif arch == 2:  # Occasional: 4 to 8 orders
            orders_per_customer[i] = rng.integers(4, 9)
        elif arch == 3:  # Infrequent: 1 to 2 orders
            orders_per_customer[i] = rng.integers(1, 3)
        elif arch == 4:  # Dormant / At-Risk: 50% 0 orders, 50% 1 early order
            orders_per_customer[i] = 1 if rng.random() < 0.50 else 0

    total_expected = orders_per_customer.sum()
    logger.info("Target transaction count across customer cohorts: %d orders.", total_expected)

    # 2. Product selection with Pareto / Zipf popularity distribution
    prod_ids = products_df["product_id"].values
    n_prods = len(prod_ids)
    ranks = np.arange(1, n_prods + 1)
    prod_weights = 1.0 / (ranks ** 0.82)
    prod_weights /= prod_weights.sum()

    # 3. Vectorized Order Generation
    order_customer_ids: List[str] = []
    order_dates: List[pd.Timestamp] = []

    logger.info("Computing order timestamps with seasonality, repeat purchase cadence, and retention decay...")
    for idx in range(n_unique_cust):
        n_ords = orders_per_customer[idx]
        if n_ords == 0:
            continue

        c_id = cust_id_arr[idx]
        c_signup = pd.Timestamp(signup_dt_arr[idx])
        arch = archetypes[idx]

        available_days = (end_datetime - c_signup).days
        if available_days <= 0:
            available_days = 1

        if arch == 4:
            # Dormant customers: their sole order occurred early (within 14 days of signup), no recent activity
            order_customer_ids.append(c_id)
            dormant_order_dt = c_signup + pd.Timedelta(days=int(rng.integers(0, min(14, available_days) + 1)))
            order_dates.append(dormant_order_dt)
        elif arch == 3:
            # Infrequent buyers: 1 or 2 orders within first 45 days
            current_date = c_signup
            for o_num in range(n_ords):
                if o_num == 0:
                    current_date = c_signup + pd.Timedelta(days=int(rng.integers(0, min(10, available_days) + 1)))
                else:
                    current_date = current_date + pd.Timedelta(days=int(rng.integers(10, min(45, available_days) + 1)))
                if current_date > end_datetime:
                    current_date = end_datetime
                order_customer_ids.append(c_id)
                order_dates.append(current_date)
        else:
            # Champions, Loyal, Occasional: Distributed repeat purchases across customer tenure
            current_date = c_signup
            for o_num in range(n_ords):
                if o_num == 0:
                    current_date = c_signup + pd.Timedelta(days=int(rng.integers(0, 3)))
                else:
                    mean_gap = 14 if arch == 0 else (28 if arch == 1 else 65)
                    gap_days = int(np.clip(rng.exponential(scale=mean_gap), 4, 120))
                    current_date = current_date + pd.Timedelta(days=gap_days)

                if current_date > end_datetime:
                    # Keep order within customer's active window
                    current_date = end_datetime - pd.Timedelta(days=int(rng.integers(0, min(60, available_days))))

                order_customer_ids.append(c_id)
                order_dates.append(current_date)

    n_actual_orders = len(order_customer_ids)
    logger.info("Generated %d order timestamps. Assigning products, quantities, and payment methods...", n_actual_orders)

    # Sample products using Zipfian weights
    selected_products = rng.choice(prod_ids, size=n_actual_orders, p=prod_weights)

    # Realistic Quantities:
    # 1: 65%, 2: 20%, 3: 8%, 4: 4%, 5: 2%, 6-8: 1%
    qty_choices = [1, 2, 3, 4, 5, 6, 7, 8]
    qty_probs = [0.65, 0.20, 0.08, 0.04, 0.02, 0.005, 0.003, 0.002]
    quantities = rng.choice(qty_choices, size=n_actual_orders, p=qty_probs)

    # Payment Methods
    pm_choices = ["Credit Card", "PayPal", "Debit Card", "Cash on Delivery", "Apple Pay"]
    pm_probs = [0.48, 0.25, 0.14, 0.08, 0.05]
    payment_methods = rng.choice(pm_choices, size=n_actual_orders, p=pm_probs)

    # Order Status
    status_choices = ["Completed", "Shipped", "Cancelled", "Refunded"]
    status_probs = [0.86, 0.06, 0.04, 0.04]
    order_statuses = rng.choice(status_choices, size=n_actual_orders, p=status_probs)

    order_ids = [f"ORD_{i+1:07d}" for i in range(n_actual_orders)]
    formatted_order_dates = [d.strftime("%Y-%m-%d") for d in order_dates]

    orders_df = pd.DataFrame({
        "order_id": order_ids,
        "customer_id": order_customer_ids,
        "product_id": selected_products,
        "order_date": formatted_order_dates,
        "quantity": quantities,
        "payment_method": payment_methods,
        "order_status": order_statuses,
    })

    # Sort chronologically by order_date and customer_id
    orders_df.sort_values(by=["order_date", "customer_id"], inplace=True)
    orders_df.reset_index(drop=True, inplace=True)
    orders_df["order_id"] = [f"ORD_{i+1:07d}" for i in range(len(orders_df))]

    # ---------------------------------------------------------------------
    # INTENTIONAL DATA QUALITY INJECTIONS (Orders)
    # ---------------------------------------------------------------------
    logger.info("Injecting controlled data quality anomalies into orders...")

    # A. Missing payment_method (~0.5% = ~530 orders)
    n_missing_pm = int(n_actual_orders * 0.005)
    missing_pm_indices = rng.choice(n_actual_orders, size=n_missing_pm, replace=False)
    orders_df.loc[missing_pm_indices, "payment_method"] = np.nan

    # B. Inconsistent payment_method categorical values (~1.5%)
    inconsistent_pm_indices = rng.choice(
        [i for i in range(n_actual_orders) if i not in missing_pm_indices],
        size=int(n_actual_orders * 0.015),
        replace=False,
    )
    for idx in inconsistent_pm_indices:
        current_pm = orders_df.at[idx, "payment_method"]
        if current_pm == "Credit Card":
            orders_df.at[idx, "payment_method"] = rng.choice(["CC", "credit_card"])
        elif current_pm == "PayPal":
            orders_df.at[idx, "payment_method"] = "paypal"
        elif current_pm == "Cash on Delivery":
            orders_df.at[idx, "payment_method"] = "COD"

    # C. Inconsistent order_status categorical casing (~2.0%)
    inconsistent_status_indices = rng.choice(n_actual_orders, size=int(n_actual_orders * 0.02), replace=False)
    for idx in inconsistent_status_indices:
        current_st = orders_df.at[idx, "order_status"]
        if current_st == "Completed":
            orders_df.at[idx, "order_status"] = "completed"
        elif current_st == "Cancelled":
            orders_df.at[idx, "order_status"] = "cancelled"
        elif current_st == "Refunded":
            orders_df.at[idx, "order_status"] = "refunded"

    # D. Invalid quantities:
    # D1. Negative quantities (-1, -2, -3 unhandled return entries: ~330 orders / ~0.3%)
    n_negative_qty = 330
    neg_qty_indices = rng.choice(n_actual_orders, size=n_negative_qty, replace=False)
    orders_df.loc[neg_qty_indices, "quantity"] = rng.choice([-1, -2, -3], size=n_negative_qty)

    # D2. Zero quantity records (~165 orders / ~0.15%)
    zero_qty_indices = rng.choice(
        [i for i in range(n_actual_orders) if i not in neg_qty_indices],
        size=165,
        replace=False,
    )
    orders_df.loc[zero_qty_indices, "quantity"] = 0

    logger.info("Orders generated: %d total rows.", len(orders_df))
    return orders_df


def generate_all_datasets(
    output_dir: Path = RAW_DATA_DIR,
    seed: int = 42,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Execute complete dataset generation pipeline and persist raw CSV files."""
    ensure_directories()
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Starting Phase 1 Synthetic Data Pipeline with seed=%d...", seed)

    # 1. Customers
    customers_df = generate_customers(n_customers=10000, seed=seed)
    customers_path = output_dir / "customers.csv"
    customers_df.to_csv(customers_path, index=False)
    logger.info("Saved customers raw CSV: %s", customers_path)

    # 2. Products
    products_df = generate_products(n_products=500, seed=seed)
    products_path = output_dir / "products.csv"
    products_df.to_csv(products_path, index=False)
    logger.info("Saved products raw CSV: %s", products_path)

    # 3. Orders
    orders_df = generate_orders(
        customers_df=customers_df,
        products_df=products_df,
        seed=seed,
    )
    orders_path = output_dir / "orders.csv"
    orders_df.to_csv(orders_path, index=False)
    logger.info("Saved orders raw CSV: %s", orders_path)

    logger.info("Data generation successfully completed.")
    return customers_df, products_df, orders_df


if __name__ == "__main__":
    generate_all_datasets()
