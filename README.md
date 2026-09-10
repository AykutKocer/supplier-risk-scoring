# Supplier Risk & Performance Scoring

A sector-independent (non-defense) supply chain analytics project. Synthetic Turkish
supplier data is generated, cleaned with pandas, and scored with a custom, configurable
weighted risk algorithm — producing a 0-100 risk score and a Low/Medium/High label per
supplier — then visualized in a Power BI dashboard.

![Risk level distribution](docs/images/risk_distribution.png)
![Top 10 highest-risk suppliers](docs/images/top10_risk.png)

## Motivation

I have a Business Administration and Economics background, not an engineering one. But
through the experience I gained at defense industry companies and the reading I've done,
I kept noticing the same gap in procurement and supply chain work: reliable, clean
supplier data. This project is a self-designed, end-to-end attempt at the kind of tool
that observation pointed toward: turning messy, real-world-style supplier data into a
risk score that can actually be explained and defended, not just computed.

## Pipeline

```
generate_suppliers.py  →  clean_suppliers.py  →  score_suppliers.py  →  Power BI
(synthetic messy data)    (pandas cleaning)       (weighted risk score)   (dashboard)
```

1. **Data generation** (`src/generate_suppliers.py`) — builds 85 synthetic suppliers for a
   Turkish SME/large-industry context, with realistic company names, sectors, and provinces.
   The raw output is *intentionally* messy: mixed date formats, mixed decimal separators
   (Turkish `1.234,56` vs plain `1234.56`), inconsistent/bilingual category labels, missing
   cells — the kind of mess a real multi-source Excel export actually has.
2. **Cleaning** (`src/clean_suppliers.py`) — parses and standardizes every column with an
   explicit rule, not a generic guess. See [Notable design decisions](#notable-design-decisions)
   below for the two genuine bugs this surfaced.
3. **Scoring** (`src/score_suppliers.py`) — computes four risk metrics, min-max normalizes
   each to 0-100, and combines them with weights read from `config/scoring_weights.yaml`.
4. **Dashboard** (`reports/supplier_risk_dashboard.pbix`) — Power BI report built on
   `reports/supplier_risk_scores.csv`.

## Scoring methodology

| Criterion | What it measures | Default weight |
|---|---|---|
| Delivery delay rate | Share of orders delivered late | 35% |
| Price volatility | Coefficient of variation of quarterly unit price | 25% |
| Supplier dependency ratio | This supplier's share of total purchase volume (concentration risk) | 25% |
| Quality / return rate | Share of shipped units returned | 15% |

These four categories mirror standard supplier-scorecard practice (OTIF delivery
performance, purchase-price variance, supplier concentration risk as used in Peter
Kraljic's 1983 supplier-segmentation framework, and PPM defect/return rate) rather than
being invented for this project. The specific **weights are a configurable default**, not
a fixed industry rule — real companies calibrate weights to their own priorities, and so
can anyone reusing this project, by editing `config/scoring_weights.yaml` (validated to
always sum to 100%).

References for the underlying framework:
- Kraljic, P. (1983). ["Purchasing Must Become Supply Management"](https://hbr.org/1983/09/purchasing-must-become-supply-management), *Harvard Business Review*.
- [Supplier Scorecard: Definition, KPIs, and implementation in procurement](https://www.tacto.ai/en/procurement-glossary/supplier-scorecard) — Tacto
- [Supplier Risk Scorecard: How to Build One That Works](https://www.atlassystems.com/blog/supplier-risk-scorecard) — Atlas Systems
- [Vendor Scorecards: Complete Guide For Procurement Teams](https://www.ivalua.com/blog/vendor-scorecard/) — Ivalua
- [The Kraljic Matrix: A Procurement Leader's Guide](https://business.amazon.com/en/blog/kraljic-matrix) — Amazon Business

**Why these specific default weights?** Delivery delay is weighted highest (35%) because a
late delivery stops production or sales immediately — usually the most operationally urgent
risk. Price volatility and supplier dependency ratio (25% each) are both financial/strategic
risks, weighted equally by default. Quality/return rate is weighted lowest (15%) because
quality issues are typically caught and corrected faster than a missed delivery. None of
this is a fixed rule — it's the starting rationale documented in
`config/scoring_weights.yaml`, meant to be adjusted (e.g. a price-sensitive retail business
would raise price volatility; a business with many single-sourced critical parts would raise
supplier dependency ratio).

Risk level (Low/Medium/High) is assigned by **percentile**, not a fixed score cutoff: the
riskiest ~15% and safest ~60% of the *current* supplier population, also configurable. A
fixed cutoff was tried first and produced zero High-risk suppliers — combining four
independently normalized metrics regresses combined scores toward the middle, so a fixed
absolute threshold can simply never be reached.

## Project structure

```
config/
  scoring_weights.yaml   # editable risk weights + risk-level thresholds
data/
  raw/                   # synthetic, intentionally messy generated data
  processed/             # cleaned, standardized data used for scoring
src/
  generate_suppliers.py  # synthetic data generator
  clean_suppliers.py     # cleaning / standardization
  score_suppliers.py     # risk scoring engine
notebooks/
  supplier_risk_analysis.ipynb   # step-by-step walkthrough with charts
reports/
  supplier_risk_scores.csv       # scored output (Power BI data source)
  supplier_risk_dashboard.pbix   # Power BI dashboard
  dax_measures.txt               # reference DAX measures used in the dashboard
docs/images/              # chart exports used in this README
```

## Setup

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

## Running the pipeline

```bash
python src/generate_suppliers.py   # -> data/raw/suppliers_raw.csv
python src/clean_suppliers.py      # -> data/processed/suppliers_clean.csv
python src/score_suppliers.py      # -> reports/supplier_risk_scores.csv
```

Generation uses a fixed random seed (42), so re-running the pipeline reproduces the same
85 suppliers and the same scores every time.

Then open `notebooks/supplier_risk_analysis.ipynb` (kernel: "Python (supplier-risk-scoring)")
for the full walkthrough with charts, or open `reports/supplier_risk_dashboard.pbix` in
Power BI Desktop for the dashboard.

## Dashboard

Three pages: **Overview** (KPI cards, risk-level distribution, top 10 riskiest suppliers),
**Sector & Geography** (average risk by sector / city / company size), and **Supplier
Detail** (slicers, a full detail table, top 10 by supplier concentration).

![Average risk score by sector](docs/images/avg_risk_by_sector.png)
![Supplier dependency ratio vs. risk score](docs/images/dependency_vs_risk.png)

## Notable design decisions

- **Faker's `tr_TR` locale isn't safe to use directly for this dataset.** Its `company()`
  provider ships ~100 hardcoded *real* Turkish companies (from a Capital 500 list) — using
  it would put real company names into a synthetic dataset. Company names are instead built
  from generic surnames + sector keywords + legal suffixes (Ltd. Şti. / A.Ş. / Holding A.Ş.),
  scaled to company size. Its `city()`/`address()` providers also have no real Turkish data
  and fall back to broken English-style placeholders — real province names are used instead.
- **A genuine Unicode bug:** Python's locale-unaware `str.lower()` turns `'İ'` into `'i'`
  plus an invisible combining-dot character (U+0307) instead of a plain `'i'`, which silently
  broke category matching during cleaning until explicitly stripped.
- **A genuine Power BI import bug:** without an explicit locale, Power BI parsed this
  project's period-decimal CSV numbers using the (Turkish) system locale's comma-decimal
  convention, inflating every numeric column by 10x–10,000x. Fixed in Power Query by
  re-typing the raw text columns with an explicit `en-US` locale — a fix that's portable
  regardless of which machine's regional settings opens the file next.

## Limitations & possible extensions

Documented here deliberately, rather than left implicit:

- **Supplier dependency ratio is computed against total portfolio spend**, not per
  product/commodity category. A supplier that's 12% of *all* purchasing looks riskier than
  one that's 60% of a single, less-critical category — in a real deployment, computing this
  per category would usually be more decision-useful.
- **Price volatility is based on 4 quarterly price points per supplier** — enough to
  illustrate the method, but a small sample for a real volatility estimate; more frequent
  price history would make this metric more robust.
- **Missing raw inputs are median-imputed**, and every supplier with at least one imputed
  value is flagged in `has_estimated_inputs` (26 of 85 in the current dataset) rather than
  silently treated as equally reliable — but the imputation itself is a simplification; a
  real deployment might instead exclude those suppliers from ranking or impute by
  sector/segment.
- **The scoring method (min-max normalization + weighted sum) is a simple, standard
  multi-criteria approach** — transparent and easy to explain, which matters for a risk
  score people need to trust, but more advanced weighting methods (e.g. AHP, entropy
  weighting) exist and could replace it without changing the rest of the pipeline.
- **This has not been validated against real outcomes** — the data is synthetic by design,
  so there's no ground truth to check the score against (e.g. "did High-risk suppliers
  actually cause more disruptions"). That validation is exactly what a real deployment
  would need before being trusted operationally.

## Adapting this to your own company's data

The **scoring engine is reusable**: if your data has the same column names as
`data/processed/suppliers_clean.csv`, you can run `src/score_suppliers.py` directly on it,
and the weights in `config/scoring_weights.yaml` are meant to be edited without touching
any code.

The **cleaning script is not a drop-in tool** — `src/clean_suppliers.py` was written for
this project's specific synthetic messiness (its exact date formats, its exact category
label variants, its exact sector/city list). A real company's export will be messy in its
own way, so adapting the cleaning step to real data is expected follow-up work, not
something this script does automatically.

## Status

Complete: data generation, cleaning, scoring, notebook, dashboard. Pending: none — first release.
