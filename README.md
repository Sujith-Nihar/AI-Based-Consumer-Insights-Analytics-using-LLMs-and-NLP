# AI-Based Patient Feedback Analytics for Ostomy Product Insights

**Author:** Sujith Thota  
**Time period analyzed:** 2016–2025 patient discussions  
**Brands:** Hollister and Coloplast (ostomy care)

---

## 1. Project Overview

This project turns scattered patient conversations into structured, decision-ready insights about **Hollister** and **Coloplast** ostomy products. It analyzes discussions from **Reddit** and the **United Ostomy Associations of America (UOAA)** forum—two places where patients share real experiences about leakage, adhesives, skin comfort, fit, odor control, and daily reliability.

The work is an **end-to-end batch analytics and research pipeline**, not a deployed web application. There is no live frontend or REST API. Instead, the system:

1. Collects or loads patient text (Reddit via API; UOAA from exported forum datasets in this repo).
2. Cleans and structures data as JSON/CSV.
3. Runs **Google Gemini** for sentiment, product-attribute (pros/cons) extraction, quotes, and unsupervised topic discovery.
4. Runs **RoBERTa (GoEmotions)** for emotion signals on the primary UOAA analyzer.
5. Produces analytical files for **Power BI** dashboards used in stakeholder reporting.

The outcome is a repeatable way to measure patient perception, compare brands, and connect sentiment to **specific product experiences**—not just positive/negative labels.

---

## 2. Business Problem

Patient feedback about ostomy products does not sit in one place. It is spread across Reddit threads, UOAA topics, and long comment chains. Manual review is slow, inconsistent, and hard to scale across thousands of posts spanning many years.

Hollister needs a clearer picture of:

- How patients talk about its products **compared to Coloplast**
- Which product attributes drive satisfaction or frustration
- Whether perception is shifting over time (useful for pre/post product launch benchmarking)

This pipeline addresses that gap by converting unstructured patient language into **quantified sentiment**, **emotion context**, **recurring themes**, and **attribute-level drivers** that product, marketing, and patient-support teams can act on.

---

## 3. Project Objectives

| Objective | How it is addressed in this repo |
|-----------|----------------------------------|
| Scrape and collect patient discussions | Reddit: `reddit_scraper_rebuilt.py` (PRAW). UOAA: analyzed from exported JSON in `UOAA_Analysis/` |
| Clean and prepare unstructured text | Cleaned/merged JSON & CSV under `Reddit_Analysis/` and UOAA exports |
| Identify brand mentions | Brand-tagged datasets (`Data_Merged_Hollister`, `Data_Merged_Coloplast`, both, neither) |
| Perform sentiment analysis | Gemini prompts in `FINAL_reddit_analyzer.py`, `v4_UOAA_analysis.py` |
| Detect emotions | RoBERTa GoEmotions in `v4_UOAA_analysis.py` (UOAA); Gemini also returns a primary emotion label |
| Extract product attributes linked to sentiment | Structured `pros_aspects` / `cons_aspects` in Gemini JSON outputs |
| Topic modeling / theme discovery | `Reddit_Unsupervised_Analyzer.py`, `UOAA Unsupervised.py` + JSON topic outputs |
| Compare Hollister vs Coloplast | Merged brand datasets + comparative slides/Power BI reports |
| Communicate insights visually | `Reddit_BI_Visualizations/` and `UOAA_BI_Visualizations/` (`.pbix`) |

---

## 4. End-to-End Pipeline

### 1. Data Collection

- **Reddit:** Collected with **PRAW** (`Reddit_Analysis/Reddit_Scraper+Results/reddit_scraper_rebuilt.py`) from ostomy-related subreddits (e.g. `ostomy`, `OstomyCare`, `Crohns`, `UlcerativeColitis`, and related communities). Outputs timestamped JSON/CSV under `outputs/run_*`.
- **UOAA:** Forum discussions are provided as **exported structured JSON** in the repository (and in `2025 UOAA Final Deliverables.zip`). There is no UOAA scraper script in this repo; analysis runs on prepared exports.
- **Content:** Posts, comments, thread metadata, brand mentions, dates, and patient narratives about product use.

### 2. Data Cleaning and Preprocessing

- Removed noise (URLs, emojis where applicable), normalized whitespace, and standardized fields for NLP.
- Consolidated multi-source Reddit archives into cleaned JSON (e.g. `Reddit_Analysis/Cleaned_Reddit_Posts/`, `Reddit_Cleaned+Merged_Archives/`).
- Split or tagged records by brand visibility: **Hollister-only**, **Coloplast-only**, **both brands**, or **neither/other** (`Reddit_Analysis/Analyzed_&_Filtered_Data/Data_Merged_*`).
- Prepared text fields (`body`, `text`, `title`) for model input.

### 3. Sentiment Analysis

- **Google Gemini** classifies each post into **positive**, **negative**, or **neutral** (semantic-first rules in the prompt).
- Models also return **VADER-style** `neg` / `neu` / `pos` / `compound` scores so intensity can be compared over time.
- Outputs are stored per record in JSON and flattened into CSV columns such as `gemini.analysis.overall_sentiment` (see `merged_all_cleaned__hollister_only.csv`).

### 4. Emotion Analysis

- **UOAA (canonical):** `v4_UOAA_analysis.py` loads **`SamLowe/roberta-base-go_emotions`** via Hugging Face Transformers, collapses labels into six buckets (joy, sadness, anger, fear, disgust, neutral), and stores `roberta_emotions` alongside Gemini output.
- **Reddit:** The main Reddit analyzer (`FINAL_reddit_analyzer.py`) uses **Gemini-only** for `primary_emotion`; RoBERTa is not wired into that script today.
- **Why it matters:** Sentiment alone does not explain *how* patients feel. The same negative sentiment can reflect **frustration** (leaks, adhesive failure) or **concern** (skin damage), which matters for product prioritization.

### 5. Product Attribute Extraction

Gemini maps text to controlled aspect lists—for example:

| UOAA (`v4_UOAA_analysis.py`) | Reddit (`FINAL_reddit_analyzer.py`) |
|-------------------------------|-------------------------------------|
| `skin_tolerance`, `adhesion_reliability`, `filter_effectiveness`, … | `product_range`, `customer_support`, `adhesive_issues`, `skin_irritation`, … |

This step ties sentiment to **actionable product dimensions**: leakage, adhesive performance, skin irritation, comfort, fit, wear time, odor control, pouch usability, and support.

### 6. Topic Modeling / Theme Discovery

- Implemented as **Gemini-based unsupervised topic discovery** (not classical LDA in code).
- Scripts sample up to 1,000 posts, send combined text to Gemini, and return `positive_topics` / `negative_topics` with keywords and summaries.
- Example output: `Reddit_Analysis/Analyzed_&_Filtered_Data/Topic_Modeling_Code&Output/Ostomy_submissions_Hollister_Unsupervised_Topics_2025-11-10.json`.

### 7. Comparative Brand Analysis

- Hollister and Coloplast are compared on sentiment mix, emotions, topics, and attribute-level pros/cons.
- **Parent–child analysis** (`Parent_child_analysis/parent_child_analysis.py`) adds topic-level stance (agree/disagree) between original posts and replies on UOAA.
- **Dual-brand posts** can be analyzed with `Analysing_dual_branded_data/coloplast_hollister_analysis.py`.

### 8. Visualization and Dashboarding

- Analyzed CSV/JSON feeds **Power BI** reports in `Reddit_BI_Visualizations/` and `UOAA_BI_Visualizations/`.
- Dashboards cover sentiment trends, brand comparison, topic/emotion breakdowns, and attribute-level pain points.
- Presentation visuals are also exported to `docs/images/` for documentation (sourced from `Presentation_slides/AI-based-Analytics Presentation.pptx`).

---

## 5. Architecture Overview

```
Raw Patient Discussions
        ↓
Reddit Scraper (PRAW) / UOAA Forum Exports (JSON)
        ↓
Data Cleaning and Preprocessing
        ↓
Brand Filtering and Structured Dataset Creation
        ↓
Gemini Sentiment + Aspect Analysis (+ quotes)
        ↓
RoBERTa Emotion Analysis (UOAA v4 analyzer)
        ↓
Gemini Unsupervised Topic Discovery
        ↓
CSV / JSON Analytical Outputs
        ↓
Power BI Dashboards (.pbix)
        ↓
Business Insights and Brand Comparison
```

**Design notes**

- **No** live frontend, backend API, SQL database, or vector database.
- **Offline** batch pipeline: run Python scripts locally, refresh data files, open Power BI Desktop.
- **APIs used:** Reddit API (scraping), Google Gemini API (NLP). Models are called per post (supervised) or on sampled batches (topics).

### Pipeline architecture (from project presentation)

![End-to-end pipeline architecture](docs/images/pipeline-architecture.png)

*Five-stage flow: data collection → preprocessing → NLP (Gemini + RoBERTa) → comparative analysis → Power BI.*

### NLP workflow (Gemini + RoBERTa)

![NLP workflow](docs/images/nlp-workflow-gemini-roberta.png)

*Cleaned JSON feeds Gemini for sentiment/aspects and RoBERTa for emotion scoring before results are merged for reporting.*

---

## 6. Technical Stack

| Category | Tools / Technologies | Purpose |
|----------|----------------------|---------|
| Programming | Python 3 | Data processing and NLP pipeline |
| Data collection | PRAW, Reddit API | Reddit scraping (`reddit_scraper_rebuilt.py`) |
| Data handling | JSON, CSV, pandas | Storage, merging, unsupervised sampling |
| LLM analysis | Google Gemini (`google.generativeai`, `google.genai`) | Sentiment, aspects, quotes, topics, stance |
| Emotion analysis | RoBERTa GoEmotions (`transformers`, `SamLowe/roberta-base-go_emotions`) | Emotion buckets on UOAA v4 pipeline |
| Sentiment scoring support | VADER-style fields via Gemini; optional `vaderSentiment` in v4 | Intensity scores aligned with VADER conventions |
| Topic modeling | Gemini unsupervised scripts | Recurring positive/negative themes |
| Visualization | Power BI (`.pbix`) | Interactive dashboards for stakeholders |
| Configuration | `python-dotenv`, `.env` | API keys for Gemini and Reddit |

**Not used in this repository:** FastAPI, React, SQL/NoSQL databases, vector DBs, PySpark, Docker/Kubernetes deployment, or Jupyter notebooks (despite being mentioned in early drafts elsewhere).

**Implementation note:** README and slides sometimes refer to “Vertex AI” or “Gemini 2.5.” In code, analyzers primarily use the **Google Generative AI SDK** with models such as **`gemini-2.0-flash`** (v4, Reddit) and **`gemini-2.5-flash`** (unsupervised topic scripts).

---

## 7. Repository Structure

```
AI-Based-Consumer-Insights-Analytics-using-LLMs-and-NLP/
├── README.md                          # This file
├── requirements.txt                   # Python dependencies
├── .env.example                       # API key template
├── docs/images/                       # README visuals (from presentation)
├── Presentation_slides/               # Full slide deck (.pptx)
│
├── Reddit_Analysis/                     # Reddit scrape, clean, analyze (~119 MB)
│   ├── Reddit_Scraper+Results/        # PRAW scraper + raw scrape samples
│   ├── Cleaned_Reddit_Posts/          # Per-source cleaned JSON by brand
│   ├── Reddit_Cleaned+Merged_Archives/# Merged Hollister/Coloplast/unbranded
│   ├── Archived_Reddit_Posts/         # Historical .jsonl archives
│   └── Analyzed_&_Filtered_Data/
│       ├── Analyzer/                  # FINAL_reddit_analyzer.py, prompts
│       ├── Topic_Modeling_Code&Output/# Unsupervised topics + JSON outputs
│       ├── Data_Merged_Hollister/     # Analyzed Hollister CSV/JSON
│       ├── Data_Merged_Coloplast/     # Analyzed Coloplast CSV/JSON
│       ├── Data_Merged_Both_Orgs/     # Dual-brand mentions
│       ├── Data_Merged_neither-other_orgs/
│       └── ALL_Data_Merged/           # Combined cleaned + analyzed sets
│
├── UOAA_Analysis/                     # UOAA NLP scripts + results (~45 MB)
│   ├── UOAA_Python_Code/
│   │   ├── v4_UOAA_analysis.py        # ★ Canonical UOAA analyzer (Gemini + RoBERTa)
│   │   ├── v3_UOAA_analysis.py        # Earlier version (superseded by v4)
│   │   ├── Parent_child_analysis/     # Topic/post stance + aggregation CSV
│   │   ├── Analysing_dual_branded_data/
│   │   └── UOAA Unsupervised.py       # Gemini topic discovery
│   ├── 2025 UOAA Final Deliverables.zip
│   └── UOAA_code_POC/uoaa.zip
│
├── Reddit_BI_Visualizations/          # Power BI reports for Reddit insights
├── UOAA_BI_Visualizations/            # Power BI reports for UOAA insights
```

### Canonical scripts (recommended entry points)

| Task | Script |
|------|--------|
| Scrape Reddit | `Reddit_Analysis/Reddit_Scraper+Results/reddit_scraper_rebuilt.py` |
| Analyze Reddit posts | `Reddit_Analysis/Analyzed_&_Filtered_Data/Analyzer/FINAL_reddit_analyzer.py` |
| Analyze UOAA posts | `UOAA_Analysis/UOAA_Python_Code/v4_UOAA_analysis.py` |
| UOAA topic/post stance | `UOAA_Analysis/UOAA_Python_Code/Parent_child_analysis/parent_child_analysis.py` |
| Unsupervised topics | `Reddit_Analysis/.../Reddit_Unsupervised_Analyzer.py` or `UOAA_Analysis/.../UOAA Unsupervised.py` |

---

## 8. Key Analysis Performed

### Sentiment Analysis

Each patient text is classified as **positive**, **negative**, or **neutral** using Gemini with strict JSON schema and anti-hallucination rules (brands and product claims must appear in text). VADER-style numeric scores (`neg`, `neu`, `pos`, `compound`) support trend charts and intensity comparisons in Power BI.

This answers: *“How do patients feel about this brand or experience?”*

### Emotion Analysis

RoBERTa (GoEmotions) on UOAA adds a layer beyond polarity—e.g. **joy** when a product “finally works,” **anger** during adhesive failure, **sadness** around complications, or **neutral** informational posts.

![RoBERTa emotion approach](docs/images/roberta-emotion-model.png)

*Six emotion buckets derived from GoEmotions; dominant emotion supports filtering complaint vs. relief narratives.*

**Insight:** Sentiment tells direction; emotion explains the patient’s reaction and helps prioritize fixes (leak frustration vs. mild dissatisfaction).

### Attribute-Level Analysis

Pros and cons are constrained to predefined aspect lists so outputs aggregate cleanly in BI tools. Negative sentiment often clusters around **adhesive issues**, **leakage/seal failure**, **skin irritation**, and **pouch functionality**; positive sentiment around **reliability**, **wear time**, **comfort**, **odor control**, and **support**.

This is one of the most actionable parts of the project: it links scores to **product features**, not just brand names.

### Topic Modeling

Gemini summarizes large samples into named themes with keywords—for example Hollister positive topics such as **customer support/samples**, **extended wear adhesion**, and **odor control (M9 drops)**; negative topics such as **leakage and seal issues** (see topic JSON in `Topic_Modeling_Code&Output/`).

**Insight:** Thousands of posts collapse into a reviewable set of themes for clinical, product, and marketing stakeholders.

### Brand Comparison

Compared Hollister vs Coloplast on:

- Sentiment distribution (positive / neutral / negative share)
- Platform differences (UOAA vs Reddit tone)
- Top positive and negative aspects
- Emotion mix by product category (bags, wafers, accessories)

Presentation sample sizes (branded posts used in comparative charts):

| Platform | Hollister (n) | Coloplast (n) |
|----------|---------------|---------------|
| UOAA | 645 | 420 |
| Reddit | 1,245 | 1,334 |

*Repository merged CSVs can be larger (e.g. 5,294 Hollister / 4,223 Coloplast rows in `merged_all_cleaned__*_only.csv`) because they include broader mention-level records—not only the strict branded subset used in some slides.*

---

## 9. Visual Insights from Presentation Slides

The figures below are exported from `Presentation_slides/AI-based-Analytics Presentation.pptx` into `docs/images/`.

### Hollister sentiment trends over time (UOAA)

**What it shows (presentation slide 13):** Year-over-year sentiment balance for Hollister on the UOAA forum.  
**Key insight:** Negative sentiment stays relatively low while positive/neutral discussion remains steady from **2016–2025**—useful as a **baseline** before new product launches.  
*Full chart: see `Presentation_slides/AI-based-Analytics Presentation.pptx` (slide 13).*

### Top positive and negative aspects (UOAA – Hollister)

![UOAA Hollister top aspects](docs/images/uoaa-hollister-top-aspects.png)

**What it shows:** Leading drivers of positive vs negative Hollister discussion on UOAA.  
**Key insight:** Presentation notes **adhesive failure** among top complaints, while **system security** and **skin tolerance** appear among strengths.

### Sentiment distribution by product area (UOAA – Hollister)

![UOAA Hollister sentiment distribution](docs/images/uoaa-hollister-sentiment-distribution.png)

**What it shows:** How positive/neutral/negative sentiment splits across product categories (e.g. bags/pouches, skin barriers/wafers).  
**Key insight:** Overall sentiment skews positive/neutral, but **bags/pouches** and **skin barriers/wafers** contribute a large share of negative responses.

### Emotion distribution (UOAA – Hollister)

![UOAA Hollister emotion distribution](docs/images/uoaa-hollister-emotion-distribution.png)

**What it shows:** Dominant emotions (e.g. joy, neutral) and where sadness/anger concentrate by product type.  
**Key insight:** **Joy** and **neutral** dominate; stronger negative emotions cluster around problem-prone categories like pouches and wafers.

### Reddit – Hollister sentiment trends

![Reddit Hollister sentiment trends over time](docs/images/reddit-hollister-sentiment-trends.png)

**What it shows:** Reddit sentiment for Hollister over time.  
**Key insight:** **Positive sentiment increases over time** while negative remains comparatively low in the presented analysis.

### Reddit – Top aspects (Hollister)

![Reddit Hollister top aspects](docs/images/reddit-hollister-top-aspects.png)

**What it shows:** Top five positive and negative themes on Reddit.  
**Key insight:** Patients praise **product range** and **support**; criticisms focus heavily on **adhesive issues** and **skin irritation**.

### Reddit – Sentiment distribution (Hollister)

![Reddit Hollister sentiment distribution](docs/images/reddit-hollister-sentiment-distribution.png)

**What it shows:** Sentiment split across Hollister product categories on Reddit.  
**Key insight:** Mostly positive overall for bags/wafers, with persistent adhesive-related concerns.

### Reddit – Hollister vs Coloplast sentiment comparison

![Reddit brand sentiment comparison](docs/images/reddit-brand-sentiment-comparison.png)

**What it shows:** Side-by-side positive / neutral / negative shares.

| Brand | Positive | Neutral | Negative |
|-------|----------|---------|----------|
| Hollister (n=1,245) | 50.53% | 26.12% | 23.35% |
| Coloplast (n=1,334) | 56.52% | 26.84% | 16.64% |

**Key insight:** Coloplast shows a **higher positive share** and **lower negative share** on Reddit in this branded subset.

### UOAA – Brand comparison

![UOAA brand comparison](docs/images/uoaa-brand-comparison.png)

**What it shows:** Comparative sentiment patterns for Hollister vs Coloplast on UOAA.  
**Key insight:** Coloplast trends **more positive but also more polarizing** on UOAA (higher positive and higher negative than Hollister in the presentation summary).

### Power BI dashboards

![Power BI visualization layer](docs/images/power-bi-dashboards.png)

**What it shows:** Examples of dashboard views used to communicate NLP outputs to non-technical stakeholders.  
**Key insight:** Technical JSON/CSV fields are transformed into **filters, trends, and brand comparisons** without requiring reviewers to read raw model output.

### Gemini prompt design (transparency)

![Gemini prompt example](docs/images/gemini-prompt-example.png)

**What it shows:** Structured prompt rules (no hallucination, JSON-only output, VADER-style scoring, aspect lists).  
**Key insight:** Consistent prompting improves reproducibility and keeps attributes aligned with business taxonomy.

### Insights and context slide

![Insights and context](docs/images/insights-context.png)

**What it shows:** High-level framing of quantitative and qualitative findings used in the final narrative.

---

## 10. Results and Insights

### What the pipeline delivered

- **Structured outputs** from raw patient text: every analyzed post can include sentiment, scores, aspects, emotions (UOAA), quotes, and metadata for BI.
- **Quantified brand perception** for Hollister and Coloplast on two distinct channels (supportive UOAA vs more varied Reddit).
- **Attribute-linked drivers** so teams see *why* sentiment is positive or negative—not just the label.

### Quantitative patterns (from presentation, branded subsets)

- **UOAA:** Coloplast shows about **+5.7 percentage points** higher positive sentiment and **+4.7 points** higher negative sentiment than Hollister—described as more **polarizing**.
- **Reddit:** Coloplast shows about **+6.0 points** higher positive and **~9.5 points** lower negative sentiment than Hollister in the same analysis.
- **Cross-platform:** Coloplast maintains a higher positive share on both channels; Hollister carries a **larger negative share on Reddit**.

### Qualitative patterns

**Strengths mentioned across platforms**

- **Hollister:** adhesion reliability, system stability, pouch usability, skin tolerance, familiarity.
- **Coloplast:** skin comfort, ease of use, seal performance, leak prevention.

**Pain points**

- Adhesive failure, leakage/seal issues, skin irritation, barrier comfort, filter limitations, pouch detachment (see negative topics in unsupervised JSON and aspect tags in analyzed CSVs).

**Emotional context**

- Discussions are often neutral-to-positive, but frustration and anger concentrate around **daily reliability problems** (leaks, wear time, skin damage).
- Relief and joy appear when patients find a workable fit, odor solution, or supportive supply experience.

### Topic modeling value

Unsupervised Gemini topics reduced large corpora into named themes—for example Hollister **extended wear adhesion** and **M9 odor control** as positives, and **leakage/seal issues** as a dominant negative theme—making forum noise navigable for product teams.

### Strategic takeaway (from presentation)

Hollister can build on **reliability and usability** while prioritizing innovation in **adhesive longevity**, **barrier resilience**, and **performance during movement**—areas repeatedly tied to negative sentiment and frustration in patient text.

---

## 11. Power BI Dashboard

Power BI is the stakeholder layer of this project. `.pbix` files connect to analyzed CSV/JSON produced by the Python pipeline.

| Report (examples) | Location |
|-------------------|----------|
| Hollister UOAA analysis | `UOAA_BI_Visualizations/Hollister_analysis_UOAA.pbix` |
| Coloplast / combined UOAA | `UOAA_BI_Visualizations/V4_Coloplast.pbix`, `coloplast_hollister_combined_analysis-2.pbix` |
| Parent–child stance views | `UOAA_BI_Visualizations/coloplast_parent_child_analysis.pbix`, `Hollister_parent_child_visualization-2.pbix` |
| Reddit Hollister / Coloplast | `Reddit_BI_Visualizations/Copy of FINAL HOLLISTER.pbix`, `Copy of Reddit_Coloplast_visuals.pbix` |

**Typical dashboard capabilities**

- Sentiment overview and trends over time  
- Hollister vs Coloplast comparison  
- Topic/theme and attribute breakdowns  
- Emotion distribution by product category  
- Identification of top negative and positive aspects  
- Exploration of patient quotes (where loaded into the model)  
- Agree/disagree stance patterns on UOAA (from parent–child CSV summaries)

**Opening locally:** Install [Power BI Desktop](https://powerbi.microsoft.com/desktop/), open a `.pbix` file, and **refresh data source paths** if files moved—connections are machine-specific.

![Power BI reporting layer](docs/images/power-bi-dashboards.png)

---

## 12. How to Run the Project Locally

### Prerequisites

- Python 3.10+ recommended  
- Power BI Desktop (for dashboards only)  
- API keys: [Google AI Studio](https://aistudio.google.com/) (Gemini), [Reddit apps](https://www.reddit.com/prefs/apps) (PRAW)

### Setup

```bash
git clone <repository-url>
cd AI-Based-Consumer-Insights-Analytics-using-LLMs-and-NLP

python3 -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate

pip install -r requirements.txt
cp .env.example .env
# Edit .env with your keys
```

### Environment variables

| Variable | Used by |
|----------|---------|
| `GEMINI_API_KEY` | `v4_UOAA_analysis.py`, `FINAL_reddit_analyzer.py`, unsupervised scripts |
| `GOOGLE_API_KEY` | `parent_child_analysis.py` (same key as Gemini in practice) |
| `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, `REDDIT_USER_AGENT` | `reddit_scraper_rebuilt.py` |

### Run Reddit scraper (optional)

```bash
cd Reddit_Analysis/Reddit_Scraper+Results
python reddit_scraper_rebuilt.py \
  --subs "ostomy,Ostomy" \
  --limit 500 \
  --include-comments
```

Output: `outputs/run_<timestamp>/reddit_<scope>_<timestamp>.json`

### Run Reddit analyzer

```bash
cd Reddit_Analysis/Analyzed_&_Filtered_Data/Analyzer

python FINAL_reddit_analyzer.py \
  --input "../../Cleaned_Reddit_Posts/Ostomy_comments_Hollister_final.json" \
  --output "./hollister_gemini_results.json" \
  --max-posts 100
```

**Important:** `--max-posts` defaults to **50**. Pass a larger value (or modify the default) for full-corpus runs. Pre-analyzed CSVs already exist under `Data_Merged_Hollister/` and `Data_Merged_Coloplast/`.

### Run UOAA analyzer (canonical)

```bash
cd UOAA_Analysis/UOAA_Python_Code

python v4_UOAA_analysis.py \
  --input "/path/to/uoaa_hollister_cleaned.json" \
  --output "./uoaa_hollister_results.json" \
  --batch-size 200 \
  --workers 4
```

First run downloads the RoBERTa model from Hugging Face (~500MB+). Results are written as JSON and incremental JSONL.

Example result files already in repo:

- `uoaa_hollister_results (2).json` (1,210 records)  
- `uoaa_coloplast_results (2).json` (982 records)

### Run UOAA parent–child stance analysis

```bash
cd UOAA_Analysis/UOAA_Python_Code/Parent_child_analysis

export GOOGLE_API_KEY="your_key"
python parent_child_analysis.py \
  --input "/path/to/uoaa_topics_with_content.json"
```

Produces per-post JSON and topic summary CSV (examples: `uoaa_hollister_parent_child_results.csv`).

### Run unsupervised topic modeling

Edit the `FILE_PATH` at the top of:

- `Reddit_Analysis/Analyzed_&_Filtered_Data/Topic_Modeling_Code&Output/Reddit_Unsupervised_Analyzer.py`
- `UOAA_Analysis/UOAA_Python_Code/UOAA Unsupervised.py`

Then:

```bash
export GEMINI_API_KEY="your_key"
python Reddit_Unsupervised_Analyzer.py
```

### Open Power BI

Open any `.pbix` under `Reddit_BI_Visualizations/` or `UOAA_BI_Visualizations/` and point data sources to your local analyzed CSV paths.

---

## 13. Limitations

- **Batch/offline only** — not a deployed web app or real-time monitoring system.  
- **UOAA ingestion** — scraping/cleaning scripts for UOAA are not in-repo; analysis depends on exported JSON (e.g. inside deliverable zip files).  
- **Gemini cost and variability** — full re-runs over thousands of posts incur API cost; LLM topic summaries can shift slightly between runs.  
- **Reddit emotion gap** — RoBERTa is integrated on UOAA v4 but not on `FINAL_reddit_analyzer.py`.  
- **Hardcoded paths** — older scripts (`UOAA Analyzer.py`, unsupervised scripts) contain Windows paths; use v4/CLI args where possible.  
- **Power BI portability** — `.pbix` data connections may break on another machine until refreshed.  
- **Sample size definitions** — presentation n-counts (branded subsets) differ from full merged CSV row counts; document filters when publishing metrics.  
- **No automated tests** — quality relies on prompt design, schema validation, and manual BI review.

---

## 14. Future Improvements

- Standardize on **v4** + **FINAL_reddit_analyzer** and archive duplicate scripts (`v3`, `UOAA Analyzer.py`).  
- Add reproducible **merge/clean** Python modules for Reddit and UOAA (currently mostly artifact-driven).  
- Remove hardcoded paths; require `--input` / `--output` everywhere.  
- Add **RoBERTa emotion analysis to Reddit** for parity with slides.  
- LLM output **evaluation harness** (schema checks, spot samples, agreement stats).  
- **Automated report export** (PDF/HTML) from pipeline outputs.  
- Publish a **shared Power BI template** with relative data paths.  
- Optional lightweight **Streamlit** explorer for quotes and filters (not in scope today).

---

## 15. Final Summary

This repository demonstrates **end-to-end applied AI analytics** for patient voice: collecting community discussions, preparing unstructured text, applying **LLM-based sentiment and attribute extraction**, enriching UOAA data with **RoBERTa emotions**, discovering themes through **Gemini topic modeling**, comparing **Hollister and Coloplast** across platforms, and communicating findings through **Power BI**. It is built for research and business intelligence workflows—turning thousands of patient stories into measurable, explainable product insight—rather than serving as a production web product.

For the full narrative and additional charts, see `Presentation_slides/AI-based-Analytics Presentation.pptx`.

---

## Related Files

| Resource | Path |
|----------|------|
| Slide deck | `Presentation_slides/AI-based-Analytics Presentation.pptx` |
| README figures | `docs/images/` |
| Gemini prompt (Reddit) | `Reddit_Analysis/Analyzed_&_Filtered_Data/Analyzer/NEW# Gemini Prompt.txt` |
| Analyzed Hollister CSV | `Reddit_Analysis/Analyzed_&_Filtered_Data/Data_Merged_Hollister/merged_all_cleaned__hollister_only.csv` |
| Topic output example | `Reddit_Analysis/Analyzed_&_Filtered_Data/Topic_Modeling_Code&Output/Ostomy_submissions_Hollister_Unsupervised_Topics_2025-11-10.json` |
