"""
Generate a SYNTHETIC dataset of orders for a mid-size Indian online seller.

The seller gets plenty of orders, but the profit is thin. The owner thinks
returns, COD orders, heavy discounts and slow deliveries are eating the
margin — this dataset is built to test exactly those ideas.

Patterns built in on purpose (like real e-commerce):
- Fashion comes back a lot, mostly for size issues
- COD orders are returned / cancelled more than prepaid orders
- Heavy discounts bring more orders, but the margin gets thin
- Slow delivery (more days) makes a return more likely
- A few cities get slower delivery and more returns than the rest

The file is also MESSY on purpose, like a real export: mixed date formats,
city names written in different ways, some missing values and some duplicate
rows. Cleaning it is part of the project (see analysis.py and the notebook).

Run:  python generate_data.py
Seed: 42 (reproducible)
"""

import random
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

SEED = 42
N_ORDERS = 10_000
YEAR_START = date(2025, 1, 1)

random.seed(SEED)
np.random.seed(SEED)

BASE = Path(__file__).parent
OUT = BASE / "data" / "ecommerce_orders_raw.csv"

# ---------------------------------------------------------------- products
PRODUCTS = {
    "Electronics": [
        ("Wireless Earbuds", 1299, 3999), ("Bluetooth Speaker", 999, 3499),
        ("Power Bank 10000mAh", 799, 2499), ("Smart Watch", 1999, 5999),
        ("USB Charging Cable", 299, 799), ("Headphones", 899, 4999),
    ],
    "Fashion": [
        ("Men's Cotton T-Shirt", 399, 999), ("Women's Kurti", 599, 1799),
        ("Slim Fit Jeans", 899, 2499), ("Running Sneakers", 999, 3499),
        ("Handbag", 699, 2499), ("Sunglasses", 499, 1999),
    ],
    "Home & Kitchen": [
        ("Pressure Cooker 5L", 899, 2499), ("Non-Stick Pan Set", 799, 2199),
        ("Cotton Bedsheet Set", 499, 1599), ("LED Table Lamp", 349, 1299),
        ("Storage Boxes (Set of 4)", 399, 999), ("Mixer Grinder", 2499, 5999),
    ],
    "Beauty": [
        ("Vitamin C Face Serum", 349, 1299), ("Matte Lipstick", 249, 699),
        ("Herbal Shampoo", 199, 599), ("Sunscreen SPF 50", 299, 799),
        ("Hair Dryer", 899, 2499),
    ],
    "Sports": [
        ("Yoga Mat 6mm", 499, 1299), ("Dumbbell Pair 5kg", 599, 2499),
        ("Cricket Bat", 899, 3999), ("Badminton Racket", 499, 1999),
        ("Gym Gloves", 299, 799),
    ],
    "Grocery": [
        ("Almonds 500g", 399, 999), ("Whole Wheat Atta 10kg", 349, 549),
        ("Olive Oil 1L", 599, 999), ("Green Tea (100 Bags)", 249, 499),
        ("Raw Honey 500g", 299, 599), ("Basmati Rice 5kg", 399, 799),
    ],
}
CATEGORIES = list(PRODUCTS)
CATEGORY_W = [0.24, 0.28, 0.18, 0.12, 0.08, 0.10]  # Electronics, Fashion, ...

# Average discount (%) the seller usually gives in each category
CATEGORY_DISCOUNT = {
    "Electronics": 12, "Fashion": 26, "Home & Kitchen": 18,
    "Beauty": 15, "Sports": 20, "Grocery": 6,
}
# Base return chance per category (before COD / delivery effects)
CATEGORY_RETURN_BASE = {
    "Electronics": 0.09, "Fashion": 0.20, "Home & Kitchen": 0.11,
    "Beauty": 0.07, "Sports": 0.10, "Grocery": 0.035,
}

# ------------------------------------------------------------------ cities
# (city, state, order share, usual delivery days)
CITIES = [
    ("Delhi", "Delhi", 0.12, 2), ("Mumbai", "Maharashtra", 0.11, 2),
    ("Bengaluru", "Karnataka", 0.11, 2), ("Hyderabad", "Telangana", 0.08, 3),
    ("Chennai", "Tamil Nadu", 0.07, 3), ("Pune", "Maharashtra", 0.07, 3),
    ("Kolkata", "West Bengal", 0.06, 4), ("Ahmedabad", "Gujarat", 0.06, 3),
    ("Jaipur", "Rajasthan", 0.06, 3), ("Lucknow", "Uttar Pradesh", 0.05, 5),
    ("Indore", "Madhya Pradesh", 0.05, 4), ("Patna", "Bihar", 0.05, 5),
    ("Kochi", "Kerala", 0.05, 4), ("Surat", "Gujarat", 0.06, 3),
]
CITY_NAMES = [c[0] for c in CITIES]
CITY_W = [c[2] for c in CITIES]
CITY_STATE = {c[0]: c[1] for c in CITIES}
CITY_DELIVERY = {c[0]: c[3] for c in CITIES}

PAYMENTS = ["COD", "UPI", "Card", "NetBanking"]
PAYMENT_W = [0.42, 0.33, 0.17, 0.08]

# More orders in the festival months (Oct, Nov), like every Indian seller sees
MONTH_W = [0.07, 0.06, 0.07, 0.07, 0.08, 0.07, 0.08, 0.08, 0.09, 0.13, 0.12, 0.08]
FESTIVAL_MONTHS = {10, 11}

RETURN_REASONS = ["Size issue", "Damaged", "Wrong item",
                  "Quality not as expected", "Changed mind", "Late delivery"]
REASON_W = {
    "Electronics":    [0.08, 0.25, 0.15, 0.30, 0.12, 0.10],
    "Fashion":        [0.55, 0.05, 0.08, 0.15, 0.12, 0.05],
    "Home & Kitchen": [0.08, 0.30, 0.15, 0.25, 0.12, 0.10],
    "Beauty":         [0.08, 0.15, 0.12, 0.35, 0.20, 0.10],
    "Sports":         [0.35, 0.12, 0.10, 0.20, 0.15, 0.08],
    "Grocery":        [0.00, 0.30, 0.15, 0.37, 0.08, 0.10],
}

N_CUSTOMERS = 4200  # a pool of customers, so many people order more than once


def messy_city(city: str) -> str:
    """Write the same city in different ways, like real data does."""
    r = random.random()
    if city == "Delhi":
        if r < 0.12:
            return "delhi "
        if r < 0.20:
            return "New Delhi"
        if r < 0.25:
            return "DELHI"
    elif city == "Bengaluru":
        if r < 0.10:
            return "Bangalore"
        if r < 0.15:
            return "bengaluru"
    elif city == "Mumbai":
        if r < 0.06:
            return "mumbai"
    elif r < 0.03:
        return city.lower()
    return city


DATE_FORMATS = ["%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d"]


def make_order(i: int) -> dict:
    month = random.choices(range(1, 13), weights=MONTH_W)[0]
    day = random.randint(1, 28)
    order_date = date(2025, month, day)

    category = random.choices(CATEGORIES, weights=CATEGORY_W)[0]
    product, lo, hi = random.choice(PRODUCTS[category])
    unit_price = int(round(random.uniform(lo, hi) / 10.0) * 10 - 1)  # e.g. 1,299
    if category == "Grocery":
        quantity = random.choices([1, 2, 3], weights=[0.6, 0.3, 0.1])[0]
    else:
        quantity = random.choices([1, 2, 3], weights=[0.85, 0.12, 0.03])[0]

    # Discount: around the category average; deeper in festival months
    disc_mean = CATEGORY_DISCOUNT[category] + (8 if month in FESTIVAL_MONTHS else 0)
    discount = float(np.clip(np.random.normal(disc_mean, 8), 0, 60))
    discount = round(discount, 1)

    city = random.choices(CITY_NAMES, weights=CITY_W)[0]
    payment = random.choices(PAYMENTS, weights=PAYMENT_W)[0]

    base = CITY_DELIVERY[city]
    delivery_days = int(base + random.choices([0, 1, 2, 3],
                                              weights=[0.45, 0.3, 0.17, 0.08])[0])

    # --- order status: first cancelled or not, then returned or not ---
    cancel_p = 0.10 if payment == "COD" else 0.035
    if random.random() < cancel_p:
        status, reason = "Cancelled", ""
        delivery_days = np.nan  # nothing was ever shipped
    else:
        return_p = CATEGORY_RETURN_BASE[category]
        if payment == "COD":
            return_p += 0.06          # COD orders come back more
        if delivery_days > 4:
            return_p += (delivery_days - 4) * 0.018   # slow delivery hurts
        if discount > 40:
            return_p += 0.03          # very cheap deals get returned a bit more
        if random.random() < min(return_p, 0.60):
            status = "Returned"
            w = list(REASON_W[category])
            if delivery_days >= 6:
                w[5] *= 3             # "Late delivery" shows up when it was slow
            reason = random.choices(RETURN_REASONS, weights=w)[0]
            if random.random() < 0.06:
                reason = ""           # a few returns have no reason recorded
        else:
            status, reason = "Delivered", ""

    order_value = round(quantity * unit_price * (1 - discount / 100))
    shipping_fee = 0 if order_value >= 499 else 49

    return {
        "order_id": f"ORD-{i + 1:05d}",
        "order_date": order_date.strftime(random.choice(DATE_FORMATS)),
        "customer_id": f"CUST-{random.randint(1, N_CUSTOMERS):05d}",
        "city": messy_city(city),
        "state": CITY_STATE[city],
        "category": category,
        "product": product,
        "quantity": quantity,
        "unit_price": unit_price,
        "discount_pct": discount,
        "payment_mode": payment,
        "delivery_days": delivery_days,
        "order_status": status,
        "return_reason": reason,
        "shipping_fee": shipping_fee,
        "order_value": order_value,
    }


rows = [make_order(i) for i in range(N_ORDERS)]
df = pd.DataFrame(rows)

# ------------------------------------------------------- add realistic mess
# A few missing values here and there
def blank_out(col, frac):
    idx = df.sample(frac=frac, random_state=random.randint(0, 10 ** 6)).index
    df.loc[idx, col] = np.nan

blank_out("unit_price", 0.008)
blank_out("discount_pct", 0.015)
blank_out("shipping_fee", 0.010)
blank_out("order_value", 0.010)
blank_out("state", 0.007)
mask = df["order_status"] != "Cancelled"
idx = df[mask].sample(frac=0.012, random_state=7).index
df.loc[idx, "delivery_days"] = np.nan

# A few exact duplicate rows (double entries happen in real exports)
dups = df.sample(n=45, random_state=11)
df = pd.concat([df, dups], ignore_index=True)
df = df.sample(frac=1.0, random_state=3).reset_index(drop=True)  # shuffle

OUT.parent.mkdir(parents=True, exist_ok=True)
df.to_csv(OUT, index=False)
print(f"Wrote {len(df)} raw orders -> {OUT}")
print(df.head(3).to_string(index=False))
print("\nStatus mix:\n", df["order_status"].value_counts().to_string())
