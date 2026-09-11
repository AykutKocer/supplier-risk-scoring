# -*- coding: utf-8 -*-
"""
Generate a synthetic, intentionally messy supplier dataset for a Turkish
supply chain context (small, medium, and large companies).

Design notes (why this is NOT just faker.company() / faker.city()):
- Faker's tr_TR company provider ships a hardcoded list of ~100 REAL Turkish
  companies (Capital 500). Using it would put real company names into a
  synthetic risk-scoring dataset, which is misleading. Company names are
  built here from generic surnames + sector keywords + legal suffixes instead.
- Faker's tr_TR locale has no address provider, so faker.city() falls back to
  broken English-style placeholder names. Real Turkish province names (from
  faker's geo provider) are used instead, weighted toward industrial regions.

The output mimics a messy real-world export (mixed date formats, mixed
decimal separators, inconsistent casing, missing cells) so the next pipeline
stage (cleaning) has real problems to solve.
"""

import random
import sys

import numpy as np
import pandas as pd
from faker import Faker

sys.path.append(".")  # lets `python src/generate_suppliers.py` find the cleaning package
from cleaning import vkn

RANDOM_SEED = 42
N_SUPPLIERS = 85
OUTPUT_PATH = "data/raw/suppliers_raw.csv"

random.seed(RANDOM_SEED)
np.random.seed(RANDOM_SEED)
fake = Faker("tr_TR")
Faker.seed(RANDOM_SEED)

# ---------------------------------------------------------------------------
# Reference data
# ---------------------------------------------------------------------------

# Company size tiers follow Turkey's official KOSGEB SME classification
# (employee count + annual revenue/balance sheet thresholds), not an
# invented split — see docs/research_v2.md section 0.1 for the source
# regulation. Weights are skewed toward smaller tiers (most real Turkish
# enterprises are SMEs) but less extreme than the national distribution,
# since a company substantial enough to be a supplier to a mid/large buyer
# skews a bit larger than the economy-wide average.
COMPANY_SIZES = ["Mikro", "Kucuk", "Orta", "Buyuk"]
COMPANY_SIZE_WEIGHTS = [0.20, 0.40, 0.30, 0.10]

# Sector-independent (non-defense) industries relevant to Turkish supply chains.
SECTORS = {
    "Tekstil": ["Tekstil", "Konfeksiyon", "İplik"],
    "Otomotiv Yan Sanayi": ["Otomotiv", "Oto Yedek Parça"],
    "Gıda ve İçecek": ["Gıda", "İçecek"],
    "Elektronik": ["Elektronik", "Elektrik"],
    "Kimya": ["Kimya", "Kimyasal Ürünler"],
    "Metal ve Çelik": ["Metal", "Çelik", "Demir Çelik"],
    "İnşaat Malzemeleri": ["Yapı", "İnşaat Malzemeleri"],
    "Ambalaj": ["Ambalaj", "Karton"],
    "Lojistik": ["Lojistik", "Nakliyat", "Taşımacılık"],
    "Mobilya": ["Mobilya"],
    "Plastik ve Kauçuk": ["Plastik", "Kauçuk"],
    "Makine İmalat": ["Makine", "Makine İmalat"],
}
SECTOR_NAMES = list(SECTORS.keys())

# Turkish provinces weighted toward well-known industrial hubs. Names are
# taken as-is from faker's tr_TR geo provider (real, correctly spelled).
INDUSTRIAL_CITIES = [
    "İstanbul", "Bursa", "Kocaeli", "İzmir", "Ankara", "Gaziantep", "Konya",
    "Denizli", "Kayseri", "Adana", "Manisa", "Tekirdağ", "Sakarya", "Mersin",
]
OTHER_CITIES = [
    "Eskişehir", "Antalya", "Samsun", "Trabzon", "Malatya", "Kahramanmaraş",
    "Van", "Diyarbakır", "Şanlıurfa", "Balıkesir", "Aydın", "Çorum",
]
CITY_POOL = INDUSTRIAL_CITIES * 3 + OTHER_CITIES  # weighted pool for random.choice

COMPANY_SUFFIXES_BY_SIZE = {
    "Mikro": ["Ltd. Şti.", "Tic."],
    "Kucuk": ["Ltd. Şti.", "Tic."],
    "Orta": ["San. Tic. Ltd. Şti.", "San. ve Tic. A.Ş."],
    "Buyuk": ["Holding A.Ş.", "San. ve Tic. A.Ş.", "Grup A.Ş."],
}

# Ranges of key business metrics per company size (min, max), used to keep
# generated numbers internally plausible (a "Buyuk" supplier ships more units
# and moves more money than a "Kucuk" one).
#
# employee_count and supplier_annual_revenue_tl are sized to fall inside
# their tier's official KOSGEB bounds (see COMPANY_SIZES comment above) —
# these represent the SUPPLIER'S OWN total headcount/revenue, which is a
# different thing from annual_purchase_volume_tl (how much of that revenue
# comes specifically from selling to the buyer running this analysis).
# annual_purchase_volume_tl is derived as a fraction of
# supplier_annual_revenue_tl at generation time (see generate_clean_supplier)
# rather than sampled independently, so the two numbers stay realistically
# related instead of potentially self-contradictory (e.g. a supplier whose
# sales to us alone would exceed their entire company revenue).
RANGES = {
    "Mikro": {
        "founded_year": (2000, 2023),
        "employee_count": (1, 9),
        "supplier_annual_revenue_tl": (500_000, 10_000_000),
        "purchase_share_of_revenue": (0.05, 0.35),
        "total_orders": (5, 30),
        "unit_price": (10, 200),
        "units_shipped": (100, 5_000),
        "delay_rate_mean": 0.20,
        "return_rate_mean": 0.06,
    },
    "Kucuk": {
        "founded_year": (1985, 2018),
        "employee_count": (10, 49),
        "supplier_annual_revenue_tl": (10_000_000, 100_000_000),
        "purchase_share_of_revenue": (0.03, 0.25),
        "total_orders": (10, 60),
        "unit_price": (20, 400),
        "units_shipped": (500, 15_000),
        "delay_rate_mean": 0.16,
        "return_rate_mean": 0.05,
    },
    "Orta": {
        "founded_year": (1975, 2012),
        "employee_count": (50, 249),
        "supplier_annual_revenue_tl": (100_000_000, 1_000_000_000),
        "purchase_share_of_revenue": (0.01, 0.15),
        "total_orders": (40, 150),
        "unit_price": (50, 1200),
        "units_shipped": (10_000, 120_000),
        "delay_rate_mean": 0.11,
        "return_rate_mean": 0.035,
    },
    "Buyuk": {
        "founded_year": (1950, 2005),
        "employee_count": (250, 3000),
        "supplier_annual_revenue_tl": (1_000_000_000, 8_000_000_000),
        "purchase_share_of_revenue": (0.005, 0.08),
        "total_orders": (100, 400),
        "unit_price": (100, 5000),
        "units_shipped": (80_000, 900_000),
        "delay_rate_mean": 0.06,
        "return_rate_mean": 0.02,
    },
}

DATE_FORMATS = ["%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%y"]


# ---------------------------------------------------------------------------
# Clean data generation (one "true" record per supplier)
# ---------------------------------------------------------------------------

def build_company_name(sector: str, size: str) -> str:
    keyword = random.choice(SECTORS[sector])
    suffix = random.choice(COMPANY_SUFFIXES_BY_SIZE[size])
    if size == "Buyuk" and random.random() < 0.4:
        # Large companies are often named after the founding family only
        # ("Aydın Holding A.Ş.") rather than the sector keyword.
        surname = fake.last_name()
        return f"{surname} {suffix}"
    if random.random() < 0.5:
        surname = fake.last_name()
        return f"{surname} {keyword} {suffix}"
    surname1, surname2 = fake.last_name(), fake.last_name()
    return f"{surname1} {surname2} {keyword} {suffix}"


def generate_clean_supplier(supplier_idx: int) -> dict:
    size = random.choices(COMPANY_SIZES, weights=COMPANY_SIZE_WEIGHTS, k=1)[0]
    sector = random.choice(SECTOR_NAMES)
    r = RANGES[size]

    total_orders = random.randint(*r["total_orders"])
    delay_prob = float(np.clip(np.random.beta(2, 2) * 0.5 + r["delay_rate_mean"] - 0.15, 0.01, 0.9))
    late_orders = int(np.random.binomial(total_orders, delay_prob))

    units_shipped = random.randint(*r["units_shipped"])
    return_prob = float(np.clip(np.random.beta(2, 3) * 0.3 + r["return_rate_mean"] - 0.05, 0.001, 0.5))
    units_returned = int(np.random.binomial(units_shipped, return_prob))

    base_price = round(random.uniform(*r["unit_price"]), 2)
    quarterly_prices = []
    price = base_price
    for _ in range(4):
        price = max(1.0, price * (1 + np.random.normal(0, 0.06)))
        quarterly_prices.append(round(price, 2))

    contract_start = fake.date_between(start_date="-10y", end_date="-1y")
    last_audit = fake.date_between(start_date="-2y", end_date="today")

    supplier_revenue = round(random.uniform(*r["supplier_annual_revenue_tl"]), 2)
    purchase_share = random.uniform(*r["purchase_share_of_revenue"])
    annual_purchase_volume = round(supplier_revenue * purchase_share, 2)

    iso_probability = {"Mikro": 0.05, "Kucuk": 0.15, "Orta": 0.40, "Buyuk": 0.75}[size]

    # Financial signals, conceptually inspired by the kind of data a real
    # Findeks Ticari Risk Raporu (Turkey's actual commercial credit bureau
    # product; see docs/research_v2.md section 0.3) would surface — payment
    # habits, overdue debt, leverage — NOT a reproduction of KKB's actual
    # proprietary scoring formula, which isn't publicly published. Smaller
    # companies get a somewhat worse mean on each signal, reflecting weaker
    # typical access to favorable credit terms, but with enough spread that
    # plenty of small suppliers still look financially solid and vice versa.
    financial_mean_shift = {"Mikro": 0.10, "Kucuk": 0.06, "Orta": 0.02, "Buyuk": -0.02}[size]
    overdue_debt_ratio = float(np.clip(np.random.beta(2, 5) * 0.4 + financial_mean_shift, 0.0, 0.95))
    debt_to_revenue_ratio = float(np.clip(np.random.beta(2, 4) * 1.2 + financial_mean_shift, 0.0, 3.0))
    default_probability = {"Mikro": 0.10, "Kucuk": 0.06, "Orta": 0.03, "Buyuk": 0.01}[size]
    payment_default_last_3y = random.random() < default_probability

    # Practitioner-grounded due-diligence red flags — not derived from a
    # formula, but from concrete qualitative criteria a real Turkish sourcing
    # consultant (25+ years experience) described using to vet Turkish
    # suppliers in practice (docs/research_v2.md section 4.3): no
    # factory-floor evidence, missing export documentation, demanding full
    # upfront payment. Smaller/newer, less established suppliers are more
    # likely to trip these — same size-tiered pattern as the other risk
    # signals, but these are binary presence/absence flags a due-diligence
    # checklist would record, not a continuous ratio.
    red_flag_probability = {"Mikro": 0.35, "Kucuk": 0.18, "Orta": 0.07, "Buyuk": 0.02}[size]
    has_export_documentation = random.random() > red_flag_probability
    requires_full_upfront_payment = random.random() < red_flag_probability
    site_visit_verified = random.random() > red_flag_probability * 1.2

    return {
        "supplier_id": f"SUP{supplier_idx:03d}",
        "company_name": build_company_name(sector, size),
        "sector": sector,
        "city": random.choice(CITY_POOL),
        "company_size": size,
        "founded_year": random.randint(*r["founded_year"]),
        "employee_count": random.randint(*r["employee_count"]),
        "vkn": vkn.generate(),
        "supplier_annual_revenue_tl": supplier_revenue,
        "annual_purchase_volume_tl": annual_purchase_volume,
        "total_orders_last_year": total_orders,
        "late_orders_last_year": late_orders,
        "price_q1": quarterly_prices[0],
        "price_q2": quarterly_prices[1],
        "price_q3": quarterly_prices[2],
        "price_q4": quarterly_prices[3],
        "units_shipped_last_year": units_shipped,
        "units_returned_last_year": units_returned,
        "contract_start_date": contract_start,
        "last_audit_date": last_audit,
        "payment_terms_days": random.choice([30, 45, 60, 90]),
        "iso_certified": random.random() < iso_probability,
        "overdue_debt_ratio": round(overdue_debt_ratio, 4),
        "debt_to_revenue_ratio": round(debt_to_revenue_ratio, 4),
        "payment_default_last_3y": payment_default_last_3y,
        "has_export_documentation": has_export_documentation,
        "requires_full_upfront_payment": requires_full_upfront_payment,
        "site_visit_verified": site_visit_verified,
    }


# ---------------------------------------------------------------------------
# Messiness injection (simulates a real-world messy Excel export)
# ---------------------------------------------------------------------------

def mess_up_text(value: str) -> str:
    """Randomly corrupts casing / whitespace / Turkish characters in a string."""
    choice = random.random()
    if choice < 0.15:
        return value.upper()
    if choice < 0.30:
        return value.lower()
    if choice < 0.40:
        return f"  {value}  "
    if choice < 0.50:
        # Common encoding-loss issue: Turkish characters dropped to ASCII
        # (happens when a file is saved/opened with the wrong encoding).
        return (
            value.replace("ş", "s").replace("Ş", "S")
            .replace("ç", "c").replace("Ç", "C")
            .replace("ğ", "g").replace("Ğ", "G")
            .replace("ü", "u").replace("Ü", "U")
            .replace("ö", "o").replace("Ö", "O")
            .replace("ı", "i").replace("İ", "I")
        )
    return value


def format_messy_number(value: float) -> str:
    """Formats a number the way it might come out of a Turkish-locale Excel
    (comma decimal separator, dot thousands separator) some of the time, and
    in plain international format the rest of the time."""
    if random.random() < 0.5:
        # Turkish style: 1.250.000,50
        text = f"{value:,.2f}"
        text = text.replace(",", "§").replace(".", ",").replace("§", ".")
        return text
    return f"{value:.2f}"


def format_messy_date(value) -> str:
    fmt = random.choice(DATE_FORMATS)
    return value.strftime(fmt)


def messify(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    # Corrupt casing/whitespace/Turkish characters in text columns.
    for col in ["company_name", "sector", "city"]:
        df[col] = df[col].apply(mess_up_text)

    # Company size labels written inconsistently across rows.
    size_variants = {
        "Mikro": ["Mikro", "mikro", "MİKRO", "Micro"],
        "Kucuk": ["Küçük", "küçük", "KÜÇÜK", "Small"],
        "Orta": ["Orta", "orta", "ORTA", "Medium"],
        "Buyuk": ["Büyük", "büyük", "BÜYÜK", "Large"],
    }
    df["company_size"] = df["company_size"].apply(lambda s: random.choice(size_variants[s]))

    # VKN: a small fraction get a single-digit typo (breaks the checksum,
    # simulating manual entry error — a genuine data-quality issue the
    # cleaning step's VKN validator is meant to catch, not something the
    # generic engine can silently fix).
    def _maybe_corrupt_vkn(v):
        if random.random() < 0.08:
            pos = random.randint(0, 8)  # corrupt one of the first 9 digits, never the check digit itself
            digit = str((int(v[pos]) + random.randint(1, 9)) % 10)
            return v[:pos] + digit + v[pos + 1:]
        return v
    df["vkn"] = df["vkn"].apply(_maybe_corrupt_vkn)

    # ISO certification written as inconsistent yes/no representations.
    true_variants = ["Evet", "evet", "EVET", "Yes", "1", "true"]
    false_variants = ["Hayır", "hayır", "HAYIR", "No", "0", "false"]
    df["iso_certified"] = df["iso_certified"].apply(
        lambda b: random.choice(true_variants) if b else random.choice(false_variants)
    )
    df["payment_default_last_3y"] = df["payment_default_last_3y"].apply(
        lambda b: random.choice(true_variants) if b else random.choice(false_variants)
    )
    for col in ["has_export_documentation", "requires_full_upfront_payment", "site_visit_verified"]:
        df[col] = df[col].apply(
            lambda b: random.choice(true_variants) if b else random.choice(false_variants)
        )

    # Monetary / price columns: mixed decimal separators.
    for col in [
        "annual_purchase_volume_tl", "supplier_annual_revenue_tl",
        "price_q1", "price_q2", "price_q3", "price_q4",
        "overdue_debt_ratio", "debt_to_revenue_ratio",
    ]:
        df[col] = df[col].apply(format_messy_number)

    # Dates: mixed formats.
    for col in ["contract_start_date", "last_audit_date"]:
        df[col] = df[col].apply(format_messy_date)

    # founded_year sometimes stored as a float-like string (classic pandas/
    # Excel artifact once a column contains any missing numeric value).
    df["founded_year"] = df["founded_year"].apply(
        lambda y: f"{y}.0" if random.random() < 0.3 else str(y)
    )

    # Inject missing values at column-specific rates.
    missing_rates = {
        "founded_year": 0.10,
        "employee_count": 0.06,
        "supplier_annual_revenue_tl": 0.07,
        "annual_purchase_volume_tl": 0.05,
        "late_orders_last_year": 0.04,
        "price_q1": 0.06,
        "price_q2": 0.06,
        "price_q3": 0.06,
        "price_q4": 0.06,
        "units_returned_last_year": 0.04,
        "contract_start_date": 0.03,
        "last_audit_date": 0.20,  # not every supplier has been audited
        "payment_terms_days": 0.05,
        "iso_certified": 0.08,
        "city": 0.02,
        "overdue_debt_ratio": 0.10,
        "debt_to_revenue_ratio": 0.10,
        "payment_default_last_3y": 0.05,
        "has_export_documentation": 0.06,
        "requires_full_upfront_payment": 0.06,
        "site_visit_verified": 0.12,  # a site visit not yet happening is common, not an anomaly
    }
    n = len(df)
    for col, rate in missing_rates.items():
        n_missing = int(round(n * rate))
        idx = np.random.choice(df.index, size=n_missing, replace=False)
        df.loc[idx, col] = np.nan

    return df


def main():
    records = [generate_clean_supplier(i + 1) for i in range(N_SUPPLIERS)]
    clean_df = pd.DataFrame(records)
    messy_df = messify(clean_df)

    # Shuffle row order so the "size" pattern isn't trivially sorted.
    messy_df = messy_df.sample(frac=1, random_state=RANDOM_SEED).reset_index(drop=True)

    messy_df.to_csv(OUTPUT_PATH, index=False, encoding="utf-8-sig")
    print(f"Generated {len(messy_df)} suppliers -> {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
