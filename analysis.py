"""
Indian E-Commerce Sales & Returns Analysis — cleaning + analysis script.

Loads the messy raw export (data/ecommerce_orders_raw.csv, synthetic data —
see generate_data.py), cleans it, works out the profit on every order with a
simple cost model, saves charts to charts/ and the key numbers to
findings.json (the README and notebook quote numbers from that file, so what
you read always matches the data).

Cost model (my assumptions, kept simple and stated openly):
- Product cost      = 62% of the listed selling price (quantity x unit price,
                      before discount). So a deep discount comes straight out
                      of the seller's pocket.
- Return logistics  = Rs 180 for every returned order (shipping it back).
- COD handling fee  = Rs 45 for every delivered COD order.
- Cancelled orders  = no revenue, no cost.
- Returned orders   = the customer is refunded, so no revenue is kept;
                      the seller still pays the return shipping.
- Profit on a delivered order = order value + shipping fee kept
                      - product cost - COD fee (if COD).

Run:  python analysis.py
"""

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

BASE = Path(__file__).parent
RAW = BASE / "data" / "ecommerce_orders_raw.csv"
CLEAN = BASE / "data" / "ecommerce_orders_clean.csv"
CHART_DIR = BASE / "charts"
CHART_DIR.mkdir(parents=True, exist_ok=True)

plt.rcParams.update({
    "figure.dpi": 120, "font.size": 10, "axes.spines.top": False,
    "axes.spines.right": False, "axes.grid": True, "grid.alpha": 0.3,
    "axes.axisbelow": True,
})
BLUE, RED, GREEN, ORANGE, GREY = "#2563eb", "#dc2626", "#16a34a", "#ea580c", "#6b7280"

PRODUCT_COST_PCT = 0.62
RETURN_LOGISTICS = 180
COD_FEE = 45

# ------------------------------------------------------------- cleaning
CITY_FIX = {
    "delhi": "Delhi", "new delhi": "Delhi",
    "bangalore": "Bengaluru", "bengaluru": "Bengaluru",
    "mumbai": "Mumbai", "hyderabad": "Hyderabad", "chennai": "Chennai",
    "pune": "Pune", "kolkata": "Kolkata", "ahmedabad": "Ahmedabad",
    "jaipur": "Jaipur", "lucknow": "Lucknow", "indore": "Indore",
    "patna": "Patna", "kochi": "Kochi", "surat": "Surat",
}
CITY_STATE = {
    "Delhi": "Delhi", "Mumbai": "Maharashtra", "Bengaluru": "Karnataka",
    "Hyderabad": "Telangana", "Chennai": "Tamil Nadu", "Pune": "Maharashtra",
    "Kolkata": "West Bengal", "Ahmedabad": "Gujarat", "Jaipur": "Rajasthan",
    "Lucknow": "Uttar Pradesh", "Indore": "Madhya Pradesh", "Patna": "Bihar",
    "Kochi": "Kerala", "Surat": "Gujarat",
}


def clean(df: pd.DataFrame) -> pd.DataFrame:
    n_start = len(df)
    df = df.drop_duplicates().copy()          # exact double entries
    n_dupes = n_start - len(df)

    # City names: trim spaces, fix case and the known other spellings
    df["city"] = (df["city"].astype(str).str.strip().str.lower()
                  .map(CITY_FIX).fillna(df["city"].str.strip()))
    # State: take it from the (now clean) city wherever it is missing
    df["state"] = df["state"].fillna(df["city"].map(CITY_STATE))

    # Dates arrived in 4 different formats — parse them all to real dates
    df["order_date"] = pd.to_datetime(df["order_date"], format="mixed",
                                      dayfirst=True, errors="coerce")
    df = df.dropna(subset=["order_date"])

    # Numbers as numbers
    for c in ["quantity", "unit_price", "discount_pct", "delivery_days",
              "shipping_fee", "order_value"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    # Rows with no price can't be fixed honestly — drop them (very few)
    n_no_price = int(df["unit_price"].isna().sum())
    df = df.dropna(subset=["unit_price", "quantity"])

    # Missing discount -> the usual discount for that category
    df["discount_pct"] = df.groupby("category")["discount_pct"] \
        .transform(lambda s: s.fillna(s.median()))
    # Missing order value -> rebuild it from price, quantity and discount
    rebuilt = (df["quantity"] * df["unit_price"]
               * (1 - df["discount_pct"] / 100)).round()
    df["order_value"] = df["order_value"].fillna(rebuilt)
    # Missing shipping fee -> the seller's rule: free above Rs 499, else Rs 49
    df["shipping_fee"] = df["shipping_fee"].fillna(
        pd.Series(np.where(df["order_value"] >= 499, 0, 49), index=df.index))
    # Missing delivery days (shipped orders) -> usual days for that city
    shipped = df["order_status"] != "Cancelled"
    med_days = df[shipped].groupby("city")["delivery_days"].median()
    df.loc[shipped, "delivery_days"] = df[shipped].apply(
        lambda r: med_days[r["city"]] if pd.isna(r["delivery_days"])
        else r["delivery_days"], axis=1)

    df["return_reason"] = df["return_reason"].fillna("").str.strip()
    df.loc[(df["order_status"] == "Returned") & (df["return_reason"] == ""),
           "return_reason"] = "Not recorded"

    df["month"] = df["order_date"].dt.to_period("M").astype(str)
    df.attrs["cleaning"] = {"raw_rows": n_start, "duplicates_removed": n_dupes,
                            "rows_dropped_no_price": n_no_price}
    return df


raw = pd.read_csv(RAW)
df = clean(raw)
info = df.attrs["cleaning"]
df.to_csv(CLEAN, index=False)
print(f"Raw rows: {info['raw_rows']} | duplicates removed: "
      f"{info['duplicates_removed']} | dropped (no price): "
      f"{info['rows_dropped_no_price']} | clean rows: {len(df)}")

# ------------------------------------------------------------ cost model
df["selling_price"] = df["quantity"] * df["unit_price"]  # before discount
df["product_cost"] = (PRODUCT_COST_PCT * df["selling_price"]).round(2)
df["is_cod"] = df["payment_mode"] == "COD"


def profit(r):
    if r["order_status"] == "Delivered":
        p = r["order_value"] + r["shipping_fee"] - r["product_cost"]
        return p - (COD_FEE if r["is_cod"] else 0)
    if r["order_status"] == "Returned":
        return -RETURN_LOGISTICS
    return 0.0  # Cancelled


df["profit"] = df.apply(profit, axis=1)

shipped = df[df["order_status"].isin(["Delivered", "Returned"])].copy()
delivered = df[df["order_status"] == "Delivered"]
returned = df[df["order_status"] == "Returned"]


def rate(part, whole):
    return round(float(part / whole * 100), 1) if whole else 0.0


overall_return_rate = rate(len(returned), len(shipped))
cancel_rate = rate(len(df) - len(shipped), len(df))
total_revenue = float(delivered["order_value"].sum())
total_profit = float(df["profit"].sum())

ret_by_cat = (shipped.assign(ret=shipped["order_status"] == "Returned")
              .groupby("category")["ret"].mean().mul(100).round(1)
              .sort_values(ascending=False))
ret_by_pay = (shipped.assign(ret=shipped["order_status"] == "Returned")
              .groupby("payment_mode")["ret"].mean().mul(100).round(1)
              .sort_values(ascending=False))
prepaid = shipped[shipped["payment_mode"] != "COD"]
cod_return_rate = ret_by_pay.get("COD", 0.0)
prepaid_return_rate = rate((prepaid["order_status"] == "Returned").sum(),
                           len(prepaid))

ret_by_city = (shipped.assign(ret=shipped["order_status"] == "Returned")
               .groupby("city")["ret"].mean().mul(100).round(1)
               .sort_values(ascending=False))
profit_by_cat = df.groupby("category")["profit"].sum().sort_values(ascending=False)
revenue_by_cat = delivered.groupby("category")["order_value"].sum()
margin_by_cat = (profit_by_cat / revenue_by_cat * 100).round(1)
orders_by_cat = df["category"].value_counts()

reason_counts = returned["return_reason"].value_counts()
reason_share = (reason_counts / len(returned) * 100).round(1)

# Discount bands: does a bigger discount actually make money?
df["discount_band"] = pd.cut(df["discount_pct"], bins=[-0.1, 10, 25, 40, 60],
                             labels=["0–10%", "10–25%", "25–40%", "40%+"])
disc = df.groupby("discount_band", observed=True).agg(
    orders=("order_id", "count"), profit=("profit", "sum"),
    avg_profit=("profit", "mean")).round(1)
disc_ret = (shipped.assign(ret=shipped["order_status"] == "Returned",
                           band=pd.cut(shipped["discount_pct"],
                                       bins=[-0.1, 10, 25, 40, 60],
                                       labels=["0–10%", "10–25%", "25–40%", "40%+"]))
            .groupby("band", observed=True)["ret"].mean().mul(100).round(1))
disc["return_rate_pct"] = disc_ret
disc["orders_share_pct"] = (disc["orders"] / len(df) * 100).round(1)

# Delivery time vs returns
shipped["delivery_bucket"] = pd.cut(
    shipped["delivery_days"], bins=[0, 2, 4, 6, 30],
    labels=["1–2 days", "3–4 days", "5–6 days", "7+ days"])
deliv = (shipped.assign(ret=shipped["order_status"] == "Returned")
         .groupby("delivery_bucket", observed=True)["ret"]
         .mean().mul(100).round(1))

# Monthly trend
monthly = df.groupby("month").agg(orders=("order_id", "count")).copy()
monthly["revenue"] = [float(delivered[delivered["month"] == m]["order_value"].sum())
                      for m in monthly.index]
monthly["profit"] = [float(df[df["month"] == m]["profit"].sum())
                     for m in monthly.index]
monthly["returns"] = [int((df[df["month"] == m]["order_status"] == "Returned").sum())
                      for m in monthly.index]

# Weakest combinations: category x payment (only the ones with real volume),
# and the lowest-earning products
combo_tbl = df.groupby(["category", "payment_mode"]).agg(
    orders=("order_id", "count"), profit=("profit", "sum"),
    avg_profit=("profit", "mean"))
combo = combo_tbl[combo_tbl["orders"] >= 150] \
    .sort_values("avg_profit").head(5)
prod = df.groupby("product").agg(orders=("order_id", "count"),
                                 profit=("profit", "sum"))
worst_products = prod[prod["orders"] >= 30].sort_values("profit").head(5)
best_products = prod.sort_values("profit", ascending=False).head(5)

avg_delivery_worst_city = round(float(
    shipped.groupby("city")["delivery_days"].mean().loc[ret_by_city.index[0]]), 1)

# ---------------------------------------------------------------- charts
def save(fig, name):
    fig.tight_layout()
    fig.savefig(CHART_DIR / name, bbox_inches="tight")
    plt.close(fig)
    print("chart:", name)


def bar_labels(ax, values, fmt="{:,.0f}", dy=0.3, horizontal=False):
    for i, v in enumerate(values):
        if horizontal:
            ax.text(v + dy, i, fmt.format(v), va="center", fontsize=9)
        else:
            ax.text(i, v + dy, fmt.format(v), ha="center", fontsize=9)


# 1. Monthly orders and revenue
fig, ax1 = plt.subplots(figsize=(10, 5))
x = range(len(monthly))
ax1.bar(x, monthly["orders"], color=BLUE, alpha=0.75, label="Orders")
ax1.set_ylabel("Orders")
ax1.set_xticks(x)
ax1.set_xticklabels([m[5:] + "\n" + m[:4] for m in monthly.index], fontsize=8)
ax1.set_xlabel("Month (2025)")
ax2 = ax1.twinx()
ax2.plot(x, monthly["revenue"] / 1e5, color=RED, marker="o", linewidth=2,
         label="Revenue kept (₹ lakh)")
ax2.set_ylabel("Revenue kept (₹ lakh)")
ax2.grid(False)
ax1.set_title("Monthly Orders and Revenue Kept (delivered orders only)")
save(fig, "monthly_trend.png")

# 2. Return rate by category
s = ret_by_cat.sort_values()
fig, ax = plt.subplots(figsize=(9, 5))
ax.barh(s.index, s.values, color=RED, alpha=0.8)
ax.set_xlabel("Return rate (% of shipped orders)")
ax.set_title(f"Return Rate by Category (overall: {overall_return_rate}%)")
bar_labels(ax, s.values, fmt="{:.1f}%", dy=0.4, horizontal=True)
ax.set_xlim(0, s.values.max() * 1.18)
save(fig, "return_rate_by_category.png")

# 3. Return rate by payment mode
s = ret_by_pay.sort_values()
colors = [RED if i == "COD" else BLUE for i in s.index]
fig, ax = plt.subplots(figsize=(8, 5))
ax.bar(s.index, s.values, color=colors)
ax.set_ylabel("Return rate (% of shipped orders)")
ax.set_title("Return Rate by Payment Mode — COD vs Prepaid")
bar_labels(ax, s.values, fmt="{:.1f}%", dy=0.4)
ax.set_ylim(0, s.values.max() * 1.2)
save(fig, "return_rate_by_payment.png")

# 4. Profit by category
s = profit_by_cat.sort_values()
colors = [GREEN if v >= 0 else RED for v in s.values]
fig, ax = plt.subplots(figsize=(9, 5))
ax.barh(s.index, s.values / 1e5, color=colors)
ax.set_xlabel("Total profit (₹ lakh), Jan–Dec 2025")
ax.set_title("Profit by Category (after product cost, returns and COD fees)")
bar_labels(ax, s.values / 1e5, fmt="₹{:.1f}L", dy=0.15, horizontal=True)
ax.set_xlim(min(0, (s.values / 1e5).min() * 1.25), (s.values / 1e5).max() * 1.3)
save(fig, "profit_by_category.png")

# 5. Return reasons
s = reason_share.sort_values()
fig, ax = plt.subplots(figsize=(9, 5))
ax.barh(s.index, s.values, color=ORANGE, alpha=0.85)
ax.set_xlabel("Share of all returns (%)")
ax.set_title("Why Customers Send Things Back")
bar_labels(ax, s.values, fmt="{:.1f}%", dy=0.5, horizontal=True)
ax.set_xlim(0, s.values.max() * 1.2)
save(fig, "return_reasons.png")

# 6. Delivery days vs return rate
fig, ax = plt.subplots(figsize=(8, 5))
ax.bar(deliv.index.astype(str), deliv.values, color=BLUE)
ax.plot(deliv.index.astype(str), deliv.values, color=RED, marker="o")
ax.set_ylabel("Return rate (%)")
ax.set_xlabel("How long the delivery took")
ax.set_title("The Longer the Wait, the More Returns")
bar_labels(ax, deliv.values, fmt="{:.1f}%", dy=0.5)
ax.set_ylim(0, deliv.values.max() * 1.25)
save(fig, "delivery_vs_returns.png")

# -------------------------------------------------------------- findings
findings = {
    "raw_rows": info["raw_rows"],
    "clean_rows": int(len(df)),
    "duplicates_removed": info["duplicates_removed"],
    "rows_dropped_no_price": info["rows_dropped_no_price"],
    "date_range": [str(df["order_date"].min().date()),
                   str(df["order_date"].max().date())],
    "orders_by_status": {k: int(v) for k, v in
                         df["order_status"].value_counts().items()},
    "overall_return_rate_pct": overall_return_rate,
    "cancel_rate_pct": cancel_rate,
    "total_revenue_kept_inr": round(total_revenue),
    "total_profit_inr": round(total_profit),
    "overall_margin_pct": round(total_profit / total_revenue * 100, 1),
    "return_rate_by_category_pct": {k: float(v) for k, v in ret_by_cat.items()},
    "return_rate_by_payment_pct": {k: float(v) for k, v in ret_by_pay.items()},
    "cod_return_rate_pct": float(cod_return_rate),
    "prepaid_return_rate_pct": prepaid_return_rate,
    "return_rate_by_city_pct": {k: float(v) for k, v in ret_by_city.items()},
    "worst_return_city": {"name": ret_by_city.index[0],
                          "return_rate_pct": float(ret_by_city.iloc[0]),
                          "avg_delivery_days": avg_delivery_worst_city},
    "best_return_city": {"name": ret_by_city.index[-1],
                         "return_rate_pct": float(ret_by_city.iloc[-1])},
    "profit_by_category_inr": {k: round(float(v)) for k, v in profit_by_cat.items()},
    "margin_by_category_pct": {k: float(v) for k, v in margin_by_cat.items()},
    "orders_by_category": {k: int(v) for k, v in orders_by_cat.items()},
    "top_return_reason": {"reason": reason_counts.index[0],
                          "share_pct": float(reason_share.iloc[0])},
    "return_reason_share_pct": {k: float(v) for k, v in reason_share.items()},
    "discount_bands": {b: {"orders": int(r["orders"]),
                           "orders_share_pct": float(r["orders_share_pct"]),
                           "return_rate_pct": float(r["return_rate_pct"]),
                           "avg_profit_inr": float(r["avg_profit"]),
                           "total_profit_inr": round(float(r["profit"]))}
                       for b, r in disc.iterrows()},
    "delivery_bucket_return_rate_pct": {k: float(v) for k, v in deliv.items()},
    "monthly": {m: {"orders": int(r["orders"]),
                    "revenue_inr": round(float(r["revenue"])),
                    "profit_inr": round(float(r["profit"])),
                    "returns": int(r["returns"])}
                for m, r in monthly.iterrows()},
    "worst_category_payment_combos": [
        {"category": c, "payment_mode": p, "orders": int(r["orders"]),
         "profit_inr": round(float(r["profit"])),
         "avg_profit_inr": round(float(r["avg_profit"]), 1)}
        for (c, p), r in combo.iterrows()],
    "worst_products": [{"product": p, "orders": int(r["orders"]),
                        "profit_inr": round(float(r["profit"]))}
                       for p, r in worst_products.iterrows()],
    "best_products": [{"product": p, "orders": int(r["orders"]),
                       "profit_inr": round(float(r["profit"]))}
                      for p, r in best_products.iterrows()],
    "returns_total": int(len(returned)),
    "return_logistics_cost_inr": int(len(returned) * RETURN_LOGISTICS),
    "cod_orders_delivered": int(((df["order_status"] == "Delivered")
                                 & df["is_cod"]).sum()),
    "assumptions": {
        "product_cost_pct_of_selling_price": 62,
        "return_logistics_inr_per_return": RETURN_LOGISTICS,
        "cod_fee_inr_per_delivered_cod_order": COD_FEE,
    },
}

with open(BASE / "findings.json", "w") as f:
    json.dump(findings, f, indent=2)

print("\n================ KEY FINDINGS ================")
print(f"Clean orders analysed : {len(df)}")
print(f"Overall return rate   : {overall_return_rate}%  | cancel rate: {cancel_rate}%")
print(f"Revenue kept          : Rs {total_revenue:,.0f}")
print(f"Total profit          : Rs {total_profit:,.0f} "
      f"({total_profit / total_revenue * 100:.1f}% margin)")
print(f"COD return rate       : {cod_return_rate}%  vs prepaid {prepaid_return_rate}%")
print("Return rate by category:")
for c, v in ret_by_cat.items():
    print(f"  {c:16s} {v:.1f}%")
print("Profit by category:")
for c, v in profit_by_cat.items():
    print(f"  {c:16s} Rs {v:,.0f}")
print(f"Top return reason     : {reason_counts.index[0]} ({reason_share.iloc[0]}%)")
print(f"Worst city for returns: {ret_by_city.index[0]} ({ret_by_city.iloc[0]}%)")
print("findings.json written.")
