# V2 Research: State of the Art, Gaps, and Opportunities

Research notes for extending the Supplier Risk & Performance Scoring project. Compiled
2026-09-11, updated continuously same day. All claims below are sourced; see links inline.

## 0. Turkey-grounded data authenticity — real institutions to build the synthetic model on

This section is the highest-value addition from the second research pass: real Turkish
institutions and mechanisms that let the synthetic dataset and scoring logic be grounded
in verifiable, official reality rather than plausible-sounding invention.

### 0.1 Official Turkish SME size classification (KOSGEB, updated 2025/2026)
Turkey's actual regulatory size tiers — should replace the project's current arbitrary
Small/Medium/Large revenue bands:

| Tier | Employees | Annual net sales OR balance sheet |
|---|---|---|
| Mikro (Micro) | < 10 | ≤ 10 million TL |
| Küçük (Small) | < 50 | ≤ 100 million TL |
| Orta (Medium) | < 250 | ≤ 1 billion TL |
| Büyük (Large) | ≥ 250 | > 1 billion TL |

The upper KOBİ threshold was raised from 500M to **1 billion TL** in the most recent
update. Note the real definition uses **employee count AND financials together** (not
revenue alone) — our current generator has no `employee_count` field at all. Adding one,
sized consistently with `company_size` per this table, would make the synthetic dataset
verifiably match real Turkish regulatory categories instead of an invented split.

[KOSGEB: KOBİ Tanımı Güncellendi](https://www.kosgeb.gov.tr/site/tr/genel/detay/9276/kobi-tanimi-guncellendi-daha-fazla-isletme-kamu-desteklerinden-yararlanabilecek) ·
[KOBİ Yönetmeliği (PDF)](https://webdosya.kosgeb.gov.tr/Content/Upload/Dosya/Mevzuat/2023/K%C3%BC%C3%A7%C3%BCk_ve_Orta_B%C3%BCy%C3%BCkl%C3%BCkteki_%C4%B0%C5%9Fletmeler_Y%C3%B6netmeli%C4%9Fi.pdf)

### 0.2 VKN (Vergi Kimlik Numarası) — a real, implementable checksum algorithm
Every Turkish company has a 10-digit tax ID (VKN), and **the last digit is a real
checksum computed from the first 9** (position-weighted, mod-10/mod-11 based — the exact
algorithm is documented and implementable). This is a genuine, non-trivial data
validation feature we currently have zero of:
- **Generation**: synthetic suppliers could get real, checksum-valid VKNs instead of
  arbitrary numbers — makes the synthetic data pass real-world validation, the way a
  well-built test fixture should.
- **Cleaning step**: implement the same checksum as an actual validation rule (analogous
  to IBAN or credit-card Luhn validation) — a concrete, "I implemented a real Turkish
  algorithm" talking point, not just formatting cleanup.
- VKN is legally required for invoicing, tenders, customs, banking — i.e. it's the
  identifier real Turkish procurement systems actually key suppliers on.

[VKN doğrulama algoritması (GitHub Gist)](https://gist.github.com/sadikay/7847f15100efbdaf036fbec937639857) ·
[VKN Doğrulama Aracı](https://www.tcknvkn.com/vkn-dogrulama.html)

### 0.3 Findeks / KKB — Turkey's real commercial credit bureau (the authentic financial-risk anchor)
**Findeks**, run by **KKB (Kredi Kayıt Bürosu)** — Turkey's actual credit bureau,
literally used by Yapı Kredi, Garanti BBVA, and TEB for exactly this use case — offers a
**"Ticari Risk Raporu" (Commercial Risk Report)**: a company's cash/non-cash limits and
debts broken down by bank, full credit/credit-card/overdraft account details, payment
habits, and a computed credit note (Ticari Kredi Notu). A business can request another
business's report (with that business's consent) via tax ID.
- **This should replace the Altman Z-Score idea from the first research pass** as our
  financial-risk anchor — Altman Z-Score is a legitimate but foreign (American academic)
  formula; Findeks is the actual product real Turkish banks and companies use for this
  exact purpose. Simulating a `findeks_credit_score`-style field is a far more
  authentic and defensible design choice for a Turkish-context tool.
- Exact score range/formula is proprietary (KKB doesn't publish it), so any synthetic
  version would need a documented, clearly-labeled *approximation*, not a claim of
  reproducing the real formula.

[Findeks Ticari Risk Raporu](https://www.findeks.com/urunler/ticari-risk-raporu) ·
[KKB Ticari Kredi Notu](https://www.kkb.com.tr/urunler/ticari-kredi-notu)

### 0.4 KGF (Kredi Garanti Fonu) — real public SME risk-evaluation criteria
KGF, Turkey's public loan-guarantee institution for SMEs lacking collateral, publishes
real evaluation criteria: eligibility around ≤125M TL asset size/turnover (KGF's own
program threshold, distinct from the general KOBİ definition above), and an assessment
based on **financial health, past credit performance, sector standing, and core
financial ratios** — another real, citable Turkish institutional framework for what
"financial risk" means in practice here, and a second real anchor point (alongside
Findeks) for a `financial_risk` scoring dimension.

[KGF Kredisi (Akbank)](https://www.akbank.com/blog/kgf-kredi-garanti-fonu-nedir)

### 0.5 Ticaret Sicili Gazetesi (TOBB) — the official company registry
Turkey's official Trade Registry Gazette, run by TOBB, offers **free lookup by company
name or registration number** (ticaretsicil.gov.tr, or via e-Devlet) — confirms a
company's legal existence, registration date, and official title. No public bulk/API
access was found in this pass (would need direct contact with TOBB for programmatic
access) — but even without an API, this is the authoritative source that "is this a real,
registered company" checks are grounded in, worth referencing in documentation as the
real-world equivalent of what a `company_verified` flag would represent.

[Ticaret Sicili Gazetesi Sorgulama (TOBB)](https://www.tobb.org.tr/TurkiyeTicaretSicilGazetesi/Sayfalar/Sorgulama.php)

### 0.6 e-Fatura mükellef sorgulama — a free, real "is this company digitally compliant" check
Turkey's e-invoice (e-Fatura) system has a public **registered-taxpayer lookup** —
instantly checking whether a given VKN is registered in the national e-invoice system.
Since e-Fatura registration is mandatory past certain revenue thresholds, "not
e-Fatura-registered despite being above the threshold" is itself a real, checkable red
flag signal (implies either a very small/informal operation or a compliance gap) —
another authentic, Turkey-specific data point beyond what generic international
procurement-tech content would ever surface.

[E-Fatura Mükellef Sorgulama Aracı](https://www.hesapcini.com/araclar/e-fatura-mukellef-sorgulama/)

### 0.7 Real Logo/Netsis integration pathways (confirms Section 4.1's premise, adds the "how")
- **Netsis's newer versions expose a RESTful API with JSON** — a modern, directly
  scriptable integration path (not just batch Excel/CSV import).
- Legacy/older Logo & Netsis installations are commonly integrated via **direct SQL
  Server database connections** (the most flexible method cited) or scheduled **Excel /
  XML / CSV batch exports** using Logo's "Exceltrans" or Netsis's "Toplu Aktarım" bulk-
  import tooling.
- **Concretely actionable for this project**: a realistic Logo/Netsis-style raw export
  simulation should look like an Excel template with Turkish field labels and Turkish
  locale number/date formatting (UTF-8, not the SAP-style column-per-field export we
  currently model) — a genuinely different messiness profile than what
  `generate_suppliers.py` currently produces.

[Netsis REST API entegrasyonu](https://ubsbilisim.com/blog/netsis-entegrasyon-rehberi/) ·
[Logo Exceltrans](https://www.logouzakdestek.com/single-post/logo-destek-exceltrans-veri-aktarimi-nedir-fiyat-listesi)

### 0.8 Currency/FX exposure — a risk dimension Western frameworks underweight, but is central in Turkey
None of the international frameworks in Section 3 treat currency risk as a first-class
supplier-risk dimension — but for Turkey specifically it's arguably more decision-relevant
than several dimensions they do include:
- **Import-input dependency is named directly as a primary driver of Turkish price
  volatility** — a supplier's own upstream costs (imported raw materials/components) pass
  through to what they charge you, even if your invoice is in TL.
- Real practitioner content exists specifically on this (Satınalma Dergisi has a
  dedicated article, *"İthalat ve İhracatçılarda Kur Riski"*), and Turkish academic
  literature has papers specifically on FX risk management techniques for supply chains.
- Real hedging instruments used by sophisticated Turkish firms: forward FX sales,
  futures, options, swaps — matching long/short FX positions to import/export payment
  timing.
- **Concrete, addable fields**: `invoice_currency` (TRY/USD/EUR), and a simple
  `import_input_dependency` flag/ratio (does this supplier's own cost base depend on
  imported inputs?) — this would make `price_volatility` causally explainable ("this
  supplier is volatile *because* they import raw materials priced in USD") rather than
  just an observed statistic, which is a meaningfully deeper story than what the current
  algorithm tells.

[İthalat ve İhracatçılarda Kur Riski (Satınalma Dergisi)](https://satinalmadergisi.com/ithalat-ve-ihracatcilarda-kur-riski/) ·
[Kur Riski Yönetim Teknikleri (DergiPark)](https://dergipark.org.tr/tr/download/article-file/641060)

### 0.9 IATF 16949 — the real global automotive supplier quality standard, used identically in Turkey
For the `Otomotiv Yan Sanayi` sector already in our synthetic dataset specifically: IATF
16949 is **the** real quality-management standard automotive OEMs require of their
supply chain, and **it's applied with the same criteria in Turkey as in Germany** — i.e.
a Turkish automotive supplier and a German one are literally held to the identical
certification bar. Our current `iso_certified` field is generic (plain ISO 9001-style);
for the automotive sector specifically, referencing IATF 16949 by name instead would be
more accurate to how that sector really qualifies suppliers, and is a good example of
where a *sector-specific* certification field (not one generic flag for all sectors)
would be more realistic.

[IATF 16949 Otomotiv Kalite Yönetim Sistemi (BSI Türkiye)](https://www.bsigroup.com/tr-TR/products-and-services/standards/iatf-16949-automotive-quality-management-system/)

### 0.10 KVKK — the real compliance layer a live deployment would need
Turkey's Law No. 6698 (KVKK, Turkey's GDPR-equivalent) explicitly applies here: **a
supplier company's employee names, work emails, and phone numbers count as personal
data**, so any real (non-synthetic) deployment of this project's cleaning/scoring
pipeline on an actual company's supplier list would need KVKK-compliant handling — data
minimization, transparency about why data is collected, and (per legal commentary found)
a proper data-processing agreement with defined breach-notification and liability terms
when a third party's data is processed on a company's behalf.
- **Not an issue for the current project** (all data is synthetic), but a real,
  citable, honest line for the README's "adapting to your own data" section: real
  deployment ⇒ real KVKK obligations, not just a data-cleaning exercise.

[Satın Alma Süreçlerinde KVKK ve Veri Güvenliği Rehberi](https://www.promena.net/makaleler/blog/satin-alma-sureclerinde-kvkk-ve-veri-guvenligi) ·
[Veri İşleyen Sözleşmesi (DPA) ve Tedarikçi Risk Yönetimi — KVKK m.12](https://www.lexidata.io/blog/veri-isleyen-dpa-tedarikci-risk-yonetimi)

### 0.11 Turkish academic literature already has real weighted/fuzzy supplier-risk models — this project sits in a real tradition, not a vacuum
- **Hacettepe University** (Yasemin Merzifonluoğlu Uzgören): *"Tedarikçi Seçimi İçin Risk
  Gözeten Karar Modelleri"* — risk-aware decision models for supplier selection aimed at
  reducing the impact of supply-demand imbalance disruptions.
- A Turkish **two-stage integrated Supply Chain Risk Management model** uses
  **Pythagorean Fuzzy AHP** to weight risk criteria — a genuinely more advanced technique
  than plain AHP (Section 3.3): fuzzy logic explicitly represents uncertainty/vagueness in
  the pairwise comparisons themselves, rather than assuming a decision-maker can always
  state a precise ratio.
- Düzce University: **Fuzzy DEMATEL** applied to risk-mitigation-strategy analysis in a
  Turkish defense-industry firm — a different MCDA family (DEMATEL maps *cause-effect*
  relationships between risk factors, not just ranks/weights them), relevant if a future
  version wanted to model which risk factors *drive* others rather than treating all four
  current criteria as independent.
- **Implication:** this project's weighted-sum approach is a legitimate, simpler entry
  point into a body of Turkish academic work that already goes as far as fuzzy AHP and
  fuzzy DEMATEL — a real, honest way to describe the project's place in the literature
  ("simpler and more transparent than the fuzzy-MCDA models in Turkish academic
  literature, by design, trading some sophistication for auditability") rather than
  either overclaiming novelty or ignoring prior art.

[Tedarikçi Seçimi İçin Risk Gözeten Karar Modelleri (Hacettepe Üniversitesi)](https://dergipark.org.tr/en/pub/huniibf/article/259133) ·
[Savunma Sanayinde Risk Azaltma Stratejileri — Bulanık DEMATEL (Düzce Üniversitesi)](https://dergipark.org.tr/en/pub/dubited/article/730052)

## 1. What's already solved — the commercial state of the art

Enterprise supplier-risk platforms are mature and well-funded. The major players and how
they actually work:

- **SAP Ariba Supplier Risk** — cloud-native, integrates directly into SAP's ERP/procurement
  stack; AI-driven scoring across compliance, financial, and sustainability domains.
- **Coupa (Risk Aware)** — spend-management-first, autonomous AI agents, continuous
  third-party monitoring via a 10M+ buyer/supplier network plus outside data sources.
- **Prewave** — AI/NLP over public + private data sources, monitors 150+ risk categories
  (ESG, financial, natural disaster), real-time alerts, integrates with SAP Ariba/Coupa.
- **Resilinc** — specializes in *sub-tier* (not just Tier 1) supplier mapping and event
  monitoring; "EventWatch AI" tracks news/geopolitics/disasters for predictive risk.
- **Sphera (formerly riskmethods)** — aggregates 100+ risk indicators from structured data,
  unstructured news (AI-curated), internal enterprise data, and supplier surveys into a
  360° view.

**Common pattern:** all of them combine (a) internal performance data, (b) external
public/commercial data feeds (news, financial, sanctions lists), and (c) AI/ML scoring,
continuously refreshed — not a one-time calculation.

[Top 10 Best Supply Chain Risk Management Solutions](https://cybersecuritynews.com/best-supply-chain-risk-management-solutions/) ·
[Gartner Peer Insights: Supplier Risk Management Solutions](https://www.gartner.com/reviews/market/supplier-risk-management-solutions) ·
[Sphera SCRM](https://sphera.com/supply-chain-risk-management/)

## 2. What's genuinely NOT solved — the real gaps

This is the most important section: despite mature commercial tooling, practitioner
literature is full of documented, persistent failure modes.

### 2.1 Data quality is still the bottleneck, everywhere
- **89% of operations leaders say technology investments haven't delivered expected
  results; 87% say poor data quality hampered digital progress.**
- Master data problems named repeatedly: duplication, non-standard naming, fragmentation
  across ERP/plants, outdated records. A concrete example found: *a European parent
  company's finance controller found the same Turkish supplier listed twice — once under
  its full legal name, once under a shortened trading name — splitting its true spend
  across two records.* This is exactly the class of problem this project's cleaning step
  (`clean_suppliers.py`) already targets.
- Companies manage data across an average of **17 different enterprise systems**, and
  **72% struggle to integrate legacy data.**

[Master Data Quality in ERP (Birasyo)](https://birasyo.com/en/blog/master-data-quality-erp-duplicate-vendor-incomplete-item-master/) ·
[Supply Chain Master Data Management (Profisee)](https://profisee.com/blog/supply-chain-master-data-management/)

### 2.2 Scoring is point-in-time; risk isn't
- **A point-in-time assessment tells you what was true on one day; continuous monitoring
  tells you what is true now** — and accuracy decays every week after the assessment.
- In practice: **"tiers rarely get revisited after onboarding"**; sanctions/export-control
  checks often run only once, against static lists. A supplier can move from low to high
  risk within weeks (acquisition, leadership change, new sanction) and nothing catches it.
- **42% of executives cite lack of real-time data as their primary limitation** when a
  disruption actually hits.
- Best practice per the same sources: periodic assessment *and* continuous monitoring
  together — periodic for control baselines, continuous for catching when those baselines
  shift.

[Supplier Risk Monitoring: Why Point-in-Time Reviews Fail](https://www.atlassystems.com/blog/supplier-risk-monitoring) ·
[Continuous vs. Point-in-Time (CyberSierra)](https://cybersierra.co/blog/comparing-security-assessments/)

### 2.3 Black-box interpretability is an active, unsolved research problem
- **"Limited interpretability of black-box machine learning algorithms posed a
  significant adoption barrier"** in real supply-chain deployments (cited example: JD.com).
- Industry response is to bolt explainability *onto* black-box models after the fact
  (SHAP, LIME) rather than start from an interpretable model.
- Academic response is an entire active research area — "neurosymbolic AI" (combining
  neural nets with logic-based reasoning) exists specifically because **"the majority of
  AI approaches in supply chain afford little to no explainability, which is a
  significant barrier to broader adoption."**
- **This directly validates this project's core design choice**: a transparent, min-max
  normalize + weighted-sum score that anyone can recompute by hand is not a limitation —
  it is exactly the property the field is trying to retrofit onto black-box models.

[Explainable AI in Supply Chain Management (Taylor & Francis)](https://www.tandfonline.com/doi/full/10.1080/00207543.2023.2281663) ·
[The Explainable AI Imperative (Censinet)](https://censinet.com/perspectives/explainable-ai-imperative-black-box-risk-management-nightmare)

### 2.4 Integration fragmentation
- **"A standalone SRM tool that cannot feed ServiceNow, Halo, or Freshservice leaves
  leadership blind at the moment they need action."** Point solutions that don't plug
  into the rest of the org's workflow tools get ignored operationally even when the
  scoring itself is fine.

[10 Best Supplier Risk Management Platforms 2026 (Mitratech)](https://mitratech.com/resource-hub/blog/10-best-platforms-for-managing-supplier-risk-throughout-the-lifecycle-in-2026/)

## 3. Rigorous methodological upgrades available (concrete, adoptable)

### 3.1 Herfindahl-Hirschman Index (HHI) for concentration/dependency risk
Real economics metric (used by the DOJ for antitrust), directly applicable to our
`supplier_dependency_ratio`. **HHI = sum of squared market shares.** For a buyer's
supplier base: `HHI = Σ (supplier_i_spend / total_spend)² × 10,000`.
- **< 1,500** = low concentration, **1,500–2,500** = moderate, **> 2,500** = high
  (DOJ thresholds, adopted in procurement contexts too).
- This is a strict upgrade over our current linear "share of spend" metric — HHI
  penalizes extreme concentration non-linearly (a single dominant supplier moves the
  index much more than the same share spread across two), which matches real risk
  behavior better.
- Can be computed **per category/commodity**, not just portfolio-wide — directly answers
  the limitation already flagged honestly in our current README.

[HHI in Procurement: A Complete Guide (Gatewit)](https://gatewit.com/2025/11/22/using-herfindahl-hirschman-index-hhi-in-procurement-a-complete-guide/) ·
[HHI Definition (CFI)](https://corporatefinanceinstitute.com/resources/valuation/herfindahl-hirschman-index-hhi/)

### 3.2 Financial risk scoring (a dimension we currently have zero of)
- **Altman Z-Score**: a public, well-documented formula (5 financial ratios) predicting
  bankruptcy likelihood within 2 years. Versions exist for public manufacturers (Z),
  private manufacturers (Z′), and non-manufacturing/emerging-market firms (Z″) — the Z″
  variant is the relevant one for Turkish SME suppliers.
- **Dun & Bradstreet SER (Supplier Evaluation Risk) Rating**: real commercial product,
  1–9 scale, probability of the business seeking creditor relief or ceasing operations
  within 12 months — the industry-standard reference point if we simulate a
  "credit_rating" field.
- To add this to the project: extend the synthetic generator with basic simulated
  financial statement fields (working capital, retained earnings, EBIT, equity, sales,
  liabilities) per supplier, sized realistically by `company_size`, and compute a Z″-Score
  as a genuinely new risk dimension.

[Altman Z-Score (Wikipedia)](https://en.wikipedia.org/wiki/Altman_Z-score) ·
[D&B Supplier Evaluation Risk Rating](https://www.dnb.com/en-us/smb/resources/credit-scores/supplier-evaluation-rating-declined-ser-info.html)

### 3.3 AHP (Analytic Hierarchy Process) for weight derivation
- Our current weights (35/25/25/15) are a defensible but *asserted* rationale. AHP
  derives weights from **pairwise comparisons** ("is delivery more important than price,
  and by how much?") with a **built-in mathematical consistency check** — a rigorous,
  academically standard way to justify weights instead of picking them.
- Commonly paired with **TOPSIS** (ranks suppliers by geometric distance to an "ideal"
  and "anti-ideal" supplier) as **AHP-TOPSIS**, one of the most-cited hybrid methods in
  supplier-selection literature — more robust to non-linear trade-offs than a plain
  weighted sum, while AHP's weights keep the whole thing explainable (not a step backward
  on the interpretability point above).

[AHP-TOPSIS in Supplier Evaluation (ResearchGate)](https://www.researchgate.net/publication/395949060_Integrating_AHP_and_TOPSIS_for_Evidence-Based_Supplier_Evaluation_in_the_Pharmaceutical_Industry) ·
[Science of Smarter Supply Chain Decisions](https://thesupplychainlead.substack.com/p/the-science-of-smarter-supply-chain)

### 3.4 Geopolitical risk — a real, citable academic index exists
- **Caldara & Iacoviello (2022) Geopolitical Risk (GPR) Index** — built from newspaper
  coverage of geopolitical tension, widely used in economics research, publicly available,
  covers many countries. Could back a `country_risk_score` field for suppliers outside
  Turkey, or a regional-tension adjustment.
- Commercial equivalents exist (Bloomberg's country-of-risk scores, BlackRock's
  Geopolitical Risk Dashboard, Maplecroft) confirming this is a standard, expected
  dimension in a "complete" risk model — currently entirely absent from our algorithm.

[Geopolitical Risk and Supply Chain Diversification (CEPR)](https://cepr.org/voxeu/columns/geopolitical-risk-and-supply-chain-diversification) ·
[Bloomberg Geopolitical Risk Scores](https://www.bloomberg.com/company/press/bloomberg-launches-company-level-geopolitical-risk-scores-quantifying-country-risk-built-with-seerist-threat-intelligence)

## 4. Turkey-specific context

### 4.1 ERP landscape — not everyone is on SAP
- Large industrials run SAP or Oracle. But the Turkish SME segment — which is most of
  the actual supplier base a mid-size Turkish buyer would deal with — runs **Logo
  (GO/Wings/Tiger, Netsis), Mikro, and Uyumsoft**. Logo alone is used by **85,000+
  companies**. These systems are deeply tied to Turkish tax/accounting regulations and
  export in their own formats, different from SAP/Oracle exports.
- **Implication for this project:** a truly "usable by any Turkish company" cleaning
  layer needs to eventually account for Logo/Netsis/Mikro-style exports, not just
  SAP/Oracle-style ones — a genuinely different (and under-served) problem than what most
  English-language procurement-tech content assumes.

[SAP/Logo/Netsis/Mikro Turkey ERP Comparison 2026](https://internative.net/tr/icgoruler/blog/logo-vs-netsis-vs-mikro-tr-erp-karsilastirma-2026)

### 4.2 CBAM/CSRD — a concrete, dated compliance risk specific to Turkish exporters
- The EU's Carbon Border Adjustment Mechanism (CBAM/SKDM) enters its **definitive regime
  in 2026**. Turkey is named specifically (alongside China and India) as among the
  countries most exposed, particularly for **steel and aluminum** exports to the EU.
- Non-compliance risk is not just administrative: **inaccurate/late embedded-carbon
  reporting, incomplete certificate obligations, or unverifiable emissions data from the
  supply chain can trigger EU financial penalties, import delays, and market-access
  restrictions.**
- CSRD reporting (first companies reported for FY2024 in 2025) means EU-facing buyers now
  ask their suppliers for **energy, emissions, workforce, supplier, and compliance data —
  not just price and quality.** Scope 3 emissions (supply-chain emissions) are explicitly
  called out as the hardest category to calculate.
- **Implication:** a `compliance_risk` or `esg_risk` dimension is not a nice-to-have for a
  Turkish-context tool — for any supplier feeding an EU-facing exporter, it's becoming a
  real, dated, financially-enforced requirement.

[CBAM 2026: Compliance Guide for Turkish Exporters](https://www.esenyelpartners.com/cbam-2026-compliance-for-turkish-exporters/) ·
[CBAM/SKDM Definitive Regime 2026 (KoçZer)](https://www.koczer.com/bilgi-merkezi/blog/cbam-skdm-nedir-kuresel-ticaret-etkileri-turkiye-ets-2026)

### 4.3 Practitioner-level red flags for Turkish/emerging-market suppliers
From a 25+-year Turkish sourcing/procurement consultant (LinkedIn): concrete, qualitative
red flags used in practice when qualifying Turkish suppliers —
- No factory-floor video/evidence
- Missing export documentation
- Demanding 100% upfront payment

These map naturally onto **new binary/categorical risk flags** our synthetic data model
could add (`has_export_documentation`, `requires_full_upfront_payment`,
`site_verified`), distinct from the purely numeric metrics we currently have.

### 4.4 Turkish academic literature exists and is citable
- ITU (İstanbul Teknik Üniversitesi), 2004 MSc thesis on procurement/risk management's
  place in supply chain management.
- Sakarya University thesis applying **Bayesian methods** to supply chain risk and
  mitigation strategy analysis.
- A study of **246 manufacturing firms in Gaziantep's organized industrial zones**
  measuring buyer-supplier digital integration levels (via Satınalma Dergisi).
- **Satınalma Dergisi** (satinalmadergisi.com) is an active, ongoing Turkish trade
  publication (August 2026 issue found) — a good recurring source for practitioner-level
  Turkish content going forward, including a "Sustainability Risks in Supply Chain: What
  does the SKA Index tell us" article.

[Satınalma ve Risk Yönetiminin Tedarik Zinciri Yönetimindeki Yeri (ITU)](https://polen.itu.edu.tr/items/d55ecdf9-91b6-4b43-bc58-4568b5584610) ·
[Satınalma Dergisi](https://satinalmadergisi.com/)

## 5. Directly comparable existing open-source project (worth studying, not copying)

**`akeDataAnalyst/Supplier-Risk-Assessment-Dashboard`** on GitHub — combines performance
metrics (on-time delivery, quality) with a *real-time geopolitical risk score derived
from NLP news-sentiment analysis*. Conceptually close to where a "v2" of this project
could head (adding a live/external risk signal on top of internal performance data) —
worth reading their approach before building our own version, to differentiate rather
than duplicate.

[GitHub: Supplier-Risk-Assessment-Dashboard](https://github.com/akeDataAnalyst/Supplier-Risk-Assessment-Dashboard)

## 6. Why this project can genuinely differentiate itself

Putting the above together, the honest positioning is:

1. **Commercial tools are powerful but opaque and expensive** — enterprise SaaS,
   subscription-priced, black-box AI scoring that even the vendors themselves patch with
   bolt-on explainability tools (SHAP/LIME) after the fact.
2. **The literature explicitly says interpretability is an unsolved adoption barrier** —
   this project's simple, auditable, min-max-normalize-and-weight approach is not a
   "toy" simplification; it's the property advanced research is trying to retrofit onto
   more complex models.
3. **Nobody serving the Turkish SME layer (Logo/Netsis/Mikro users) has this kind of
   accessible, free, explainable tool** — the commercial platforms above are built for
   large enterprises already on SAP/Oracle with big budgets.
4. **The specific failure modes identified in the literature (static point-in-time
   scoring, single-portfolio-wide concentration measurement, no financial/ESG/geopolitical
   dimension) are all concrete, addressable gaps** this project's architecture already
   supports extending into (the config-driven weight system, the modular scoring
   pipeline) without a redesign.

## 7. Candidate v2 extensions, roughly ordered by (impact ÷ effort)

Not a commitment — a menu to choose from and pace out over time, per the "no rush, take
a month" approach.

| Extension | What it adds | Rough effort | Status |
|---|---|---|---|
| Profile-driven, source-agnostic cleaning architecture | The actual prerequisite for "reusable" — new ERP = new YAML, not new code | — | ✅ Done (`src/cleaning/`, 37 tests) |
| KOSGEB-aligned company sizing + employee_count + supplier's own revenue | Real Turkish regulatory classification instead of invented tiers | Small | ✅ Done |
| VKN generation + real checksum validation | A genuine Turkish business-rule check, verified against published test vectors | Small | ✅ Done (`src/cleaning/vkn.py`) |
| HHI-based concentration risk (portfolio-wide) | Replaces the linear dependency_ratio's *scoring* with the real economics metric | Small | ✅ Done — per-sector HHI still open |
| AI-assisted source profile drafting | Prompt built from the real Pydantic schema; validates any AI response before trusting it | Medium | ✅ Done (`src/ai_draft_profile.py`, 14 tests) |
| Separate financial_risk_score axis (Findeks-inspired) | A genuinely new, independent risk dimension — verified top-5 lists are disjoint from operational risk | Medium | ✅ Done — not blended into risk_score, by design |
| Turkish-context binary red flags (export docs, upfront-payment demand, site verification) | Qualitative, practitioner-grounded signals, not just numeric ratios | Small | ✅ Done (size-tiered generation + cleaning, 5 tests) |
| Risk score trend over time (multiple synthetic time periods) | Addresses the "point-in-time vs continuous" gap without needing live data feeds | Medium | ⬜ Not started |
| AHP-derived weights (replacing asserted weights) | Rigorous, consistency-checked weight justification — strong interview talking point | Medium | ✅ Done (`src/ahp.py`, CR=0.004, 14 tests) — cross-check, `--apply` left opt-in |
| Geopolitical/country risk factor (GPR-index-style) | A real, citable academic data source, relevant once suppliers extend beyond Turkey | Medium | ⬜ Not started |
| ESG/CBAM compliance risk flag for EU-facing exporters | Directly tied to a dated 2026 regulatory requirement — strong "real-world relevance" story | Medium-Large | ⬜ Not started |
| Logo/Netsis/Mikro-style raw export format support in cleaning | Extends "adapting to your own data" from aspirational to actually demonstrated for the SME segment | Large | 🟡 Illustrative example profile exists (`logo_netsis_export_example.yaml`), not yet tested against a real export |
| Per-sector HHI (not just portfolio-wide) | Directly answers the v1 README's own documented limitation about portfolio-wide-only concentration | Small | ✅ Done (`compute_sector_hhi`, `reports/sector_concentration.csv`, 6 tests) — supplier-level `risk_score` still uses portfolio-wide dependency ratio only |
| Notebook / README / Power BI dashboard updated for all of the above | The new fields and scores aren't visible anywhere outside `reports/supplier_risk_scores.csv` yet | Medium | 🟡 Notebook + README done; `.pbix` needs a manual Power BI Desktop refresh (DAX measures ready in `reports/dax_measures.txt`) |
