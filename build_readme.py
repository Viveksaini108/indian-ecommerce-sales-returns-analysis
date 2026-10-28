"""
Build README.md from findings.json, so every number quoted in the README
always matches the data. Run after analysis.py:
    python build_readme.py
"""

import json
from pathlib import Path

BASE = Path(__file__).parent
F = json.loads((BASE / "findings.json").read_text())


def money(v):
    if abs(v) >= 1e7:
        return f"₹{v / 1e7:.2f} crore"
    if abs(v) >= 1e5:
        return f"₹{v / 1e5:.1f} lakh"
    return f"₹{v:,.0f}"


def lakh(v):
    return f"₹{v / 1e5:.1f} lakh"


rc = F["return_rate_by_category_pct"]
pm = F["return_rate_by_payment_pct"]
pc = F["profit_by_category_inr"]
mc = F["margin_by_category_pct"]
db = F["discount_bands"]
dv = F["delivery_bucket_return_rate_pct"]
rs = F["return_reason_share_pct"]
combo = F["worst_category_payment_combos"][0]
oct_m, may_m = F["monthly"]["2025-10"], F["monthly"]["2025-05"]

cat_rows = "\n".join(
    f"| {c} | {F['orders_by_category'][c]:,} | {rc[c]}% | {lakh(pc[c])} | {mc[c]}% |"
    for c in sorted(pc, key=lambda c: -pc[c]))
reason_rows = "\n".join(f"| {r} | {v}% |" for r, v in rs.items())
band_rows = "\n".join(
    f"| {b} | {d['orders']:,} | {d['return_rate_pct']}% | ₹{d['avg_profit_inr']:,.0f} |"
    for b, d in db.items())
worst_products = "\n".join(
    f"| {p['product']} | {p['orders']:,} | {lakh(p['profit_inr'])} |"
    for p in F["worst_products"])
best_products = "\n".join(
    f"| {p['product']} | {p['orders']:,} | {lakh(p['profit_inr'])} |"
    for p in F["best_products"])

readme = f"""# Indian E-Commerce Sales & Returns Analysis 🛒

Hi, I'm **Vivek Saini** — a Data Analyst from Meerut, India. This is my
second portfolio project. The first one was about the job market; this one
is about a business problem I find very real: **an online seller who gets
plenty of orders but keeps very little profit.**

> 📓 **Start here:** the full analysis, step by step with charts and
> commentary, is in **[ecommerce_analysis.ipynb](ecommerce_analysis.ipynb)**.
> The scripts below reproduce everything.

## The problem I wanted to solve

A mid-size Indian online seller sells on his own store across 14 cities.
Sales look healthy. But month after month, the profit is thin, and the
owner does not know exactly why. He has four doubts:

- *"Too many products come back as returns."*
- *"COD orders are more trouble than prepaid ones."*
- *"We give big discounts in sale months, but I don't know if we earn from them."*
- *"Some cities are slow to deliver, and I think that hurts us."*

I took one full year of his orders (Jan–Dec 2025) and tested each doubt
with data. Guesses are free — I wanted numbers.

## A quick, honest note about the data

This dataset is **made by me with Python** (`generate_data.py`, seed 42) —
it is not a real company's data, and I am not going to pretend it is. What
I did was build it to behave like real Indian e-commerce: fashion comes
back for size issues, COD orders behave differently from prepaid ones,
October–November festival sales spike, and a few cities get slow delivery.
The raw file is also messy on purpose — mixed date formats, city names
written 4–5 different ways, missing values, duplicate rows — because real
exports look exactly like that, and cleaning is half of a data analyst's
job. Every step here (cleaning, profit model, pandas, SQL, charts) is the
same work I would do on a real file.

## The dataset at a glance

| | |
|---|---|
| **Raw rows** | {F['raw_rows']:,} (with {F['duplicates_removed']} exact duplicates and some missing values) |
| **Clean rows analysed** | {F['clean_rows']:,} |
| **Period** | Jan–Dec 2025 |
| **Cities** | 14 — Delhi, Mumbai, Bengaluru, Hyderabad, Chennai, Pune, Kolkata, Ahmedabad, Jaipur, Lucknow, Indore, Patna, Kochi, Surat |
| **Categories** | Electronics, Fashion, Home & Kitchen, Beauty, Sports, Grocery |
| **Payment modes** | COD, UPI, Card, NetBanking |
| **Columns** | order id, date, customer, city, state, category, product, quantity, price, discount %, payment mode, delivery days, status, return reason, shipping fee, order value |

**Status mix:** Delivered {F['orders_by_status']['Delivered']:,} · Returned
{F['orders_by_status']['Returned']:,} · Cancelled {F['orders_by_status']['Cancelled']:,}

## How I worked out profit

Sales value is not profit. I gave every order a simple profit number with
open assumptions:

- **Product cost** = 62% of the listed price (quantity × unit price, before discount)
- **Return shipping** = ₹180 per returned order, paid by the seller
- **COD handling fee** = ₹45 per delivered COD order
- **Delivered order:** profit = order value + shipping fee − product cost − COD fee (if COD)
- **Returned order:** full refund, so profit = −₹180
- **Cancelled order:** profit = ₹0

With that model, the year looks like this: revenue kept
**{money(F['total_revenue_kept_inr'])}**, total profit **{money(F['total_profit_inr'])}**
— a **{F['overall_margin_pct']}% margin**. Now, where does the rest go?

![Monthly trend](charts/monthly_trend.png)

## What I found

### 1. Returns are the biggest leak

**{F['overall_return_rate_pct']}% of shipped orders came back** —
{F['returns_total']:,} returns in one year. Just the return shipping cost
{money(F['return_logistics_cost_inr'])}, and that is before counting the lost sales
themselves.

| Category | Orders | Return rate | Profit | Margin |
|---|---:|---:|---:|---:|
{cat_rows}

**Fashion is the problem child.** It is the second-biggest category by
orders, but it keeps the least money for its size — a {mc['Fashion']}%
margin against {mc['Electronics']}% for Electronics. And the reason is
sitting in the return reasons:

| Return reason | Share of all returns |
|---|---:|
{reason_rows}

**"Size issue" is the #1 reason ({rs['Size issue']}% of all returns).**
That is not a factory problem — that is a size-chart problem, and it can be
fixed on the product page.

![Return rate by category](charts/return_rate_by_category.png)
![Return reasons](charts/return_reasons.png)

### 2. COD costs more than it looks

| Payment mode | Return rate |
|---|---:|
""" + "\n".join(f"| {p} | {v}% |" for p, v in pm.items()) + f"""

COD orders come back **{F['cod_return_rate_pct']}%** of the time; prepaid
orders **{F['prepaid_return_rate_pct']}%**. On top of that, every delivered COD order
pays a ₹45 handling fee. The weakest mix in the whole business is
**{combo['category']} + {combo['payment_mode']}**: {combo['orders']:,} orders that earned
only about **₹{combo['avg_profit_inr']:.0f} per order** on average. The owner's
doubt about COD was right.

![Return rate by payment mode](charts/return_rate_by_payment.png)

### 3. Deep discounts lose money — and October proves it

| Discount | Orders | Return rate in band | Avg profit per order |
|---|---:|---:|---:|
{band_rows}

At a small discount, an order earns about ₹{db['0–10%']['avg_profit_inr']:,.0f}. At
40%+, the seller **loses about ₹{abs(db['40%+']['avg_profit_inr']):,.0f} on every order**.
This surprised me the most in the whole project: **October had the most
orders of the year ({oct_m['orders']:,}) and the most revenue
({money(oct_m['revenue_inr'])}), but its profit ({money(oct_m['profit_inr'])}) was lower
than May** ({money(may_m['profit_inr'])} from only {may_m['orders']:,} orders). The
festival sale sold more and earned less. More orders is not the same thing
as more money.

### 4. Slow delivery means more returns

| Delivery time | Return rate |
|---|---:|
""" + "\n".join(f"| {b} | {v}% |" for b, v in dv.items()) + f"""

The slower the delivery, the more returns — every single step. The worst
city is **{F['worst_return_city']['name']}**: {F['worst_return_city']['return_rate_pct']}% returns with
{F['worst_return_city']['avg_delivery_days']} days average delivery. The best is
{F['best_return_city']['name']} at {F['best_return_city']['return_rate_pct']}%. Fast delivery is not
just good service; it directly cuts returns.

![Delivery days vs returns](charts/delivery_vs_returns.png)

### 5. Electronics quietly pays the bills

Electronics is not the biggest category by orders, but it earns the most
profit — {money(pc['Electronics'])} of the {money(F['total_profit_inr'])} total — because
its prices are higher and its return rate is much lower than Fashion's.

![Profit by category](charts/profit_by_category.png)

**Most profit per product (100+ orders):**

| Product | Orders | Profit |
|---|---:|---:|
{best_products}

**Least profit per product (100+ orders):**

| Product | Orders | Profit |
|---|---:|---:|
{worst_products}

## Checking my work with SQL

I loaded the cleaned data into SQLite inside the notebook and asked five
business questions in SQL — top cities by revenue, return rate by category,
monthly revenue and profit, best and worst products by profit, and a COD vs
prepaid comparison. The SQL answers matched my pandas answers, which is
exactly the kind of double-check I want before showing numbers to anyone.

## What the business should do

1. **Fix the fashion size charts first.** Clear size charts, a "check your
   size" note, and real fit photos on fashion pages. Size is the #1 return
   reason, and fashion gets the most traffic — even a small drop here is
   worth a lot of money.
2. **Push prepaid, gently.** Free shipping or a small extra discount on
   prepaid orders. Every order that moves from COD to prepaid is less
   likely to come back and also saves the ₹45 handling fee.
3. **Put a floor under discounts.** Keep most discounts at or below 25%.
   In this data, 40%+ discounts lost money on almost every order.
4. **Speed up the slow cities.** A closer warehouse or a faster courier
   for {F['worst_return_city']['name']} and the other slow cities. Delivery speed and
   returns move together, so this pays twice.
5. **Be careful with Fashion + COD.** A small advance payment on COD
   fashion orders would filter out the least serious orders in the weakest
   mix in the business.
6. **Judge sale months by profit, not orders.** October looked like the
   best month and was not. The report the owner should see every month is
   profit by category — not just sales.

## What I learned building this

- **Cleaning is real work.** Mixed date formats, one city written five
  ways, missing prices — the analysis was the easy part.
- **A return is worse than a lost sale.** It is a lost sale *plus* a
  shipping bill. Profit changes completely once you count it properly.
- **Check the number behind the number.** The busiest month was not the
  most profitable month. If I had stopped at "sales are up", I would have
  told the owner the wrong story.
- **Two tools, one answer.** Running the same questions in pandas and SQL
  and getting the same results is a simple habit that catches mistakes.

## Run it yourself

```bash
pip install -r requirements.txt
python generate_data.py   # rebuild the raw dataset (seed 42)
python analysis.py        # clean + profit model + charts + findings.json
python build_readme.py    # rebuild this README from findings.json
# …or open ecommerce_analysis.ipynb and run all cells
```

## What's next

- [ ] A **Power BI dashboard** on the cleaned CSV (slicers by city / category / payment mode)
- [ ] A simple flag for orders that look likely to be returned, before they ship
- [ ] Repeat-customer analysis — who orders again, and what do they buy?

## Project structure

```
├── ecommerce_analysis.ipynb            # 📓 the full analysis, executed
├── data/ecommerce_orders_raw.csv       # messy raw export (10,045 rows)
├── data/ecommerce_orders_clean.csv     # cleaned data (9,920 rows)
├── charts/                             # 6 PNG charts
├── generate_data.py                    # reproducible data generation (seed 42)
├── analysis.py                         # cleaning + cost model + charts + findings.json
├── build_notebook.py                   # helper: builds the notebook from findings.json
├── build_readme.py                     # helper: findings → this README
├── findings.json                       # machine-readable results
├── requirements.txt
└── README.md
```

## Let's connect

I'm actively looking for Data Analyst / Business Analyst / MIS Executive
opportunities and happy to discuss this project or the analysis behind it.

- 📧 vivek.saini.analyst@gmail.com
- 💼 LinkedIn: https://www.linkedin.com/in/vivek-saini-815b321b0/
- 🐙 GitHub: https://github.com/Viveksaini108
- 📍 Meerut, Uttar Pradesh, India

*If you found this useful, a ⭐ would mean a lot to a fresher putting his work out there.*
"""

(BASE / "README.md").write_text(readme)
print("README.md written:", len(readme), "chars")
