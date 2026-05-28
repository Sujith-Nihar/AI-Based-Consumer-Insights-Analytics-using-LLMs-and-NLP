#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
uoaa_analyzer_gemini_only_vader_schema_v3.py
--------------------------------------------
Gemini-only analyzer with **no post-processing** of sentiment scores.
- Gemini must output VADER-style fields: neg, neu, pos (in [0,1]) and compound (in [-1,1]).
- Gemini must ensure the 3 scores sum ~1.0 and that compound aligns with them.
- overall_sentiment must be determined **by Gemini from the text** (positive|negative|neutral|mixed).
- We **do not** clamp/renormalize/flip/derive anything after Gemini returns.
- Emotion analysis (GoEmotions) and aspect extraction kept.

Quickstart
----------
pip install google-generativeai python-dotenv transformers torch
export GEMINI_API_KEY="YOUR_KEY"
"""
print("🧩 RUNNING ACTIVE SCRIPT:", __file__)

# 🟢 Run Command Example (for VS Code PowerShell)
# & "C:\Program Files\Python313\python.exe" `
#   "c:/Users/nnaay/AppData/Local/Temp/f789cb08-4a38-42d7-8817-d5d52849ca54_v3_uoaa_analysis.zip.a54/v3_UOAA_analysis.py" `
#   --input "C:/Users/nnaay/OneDrive/Desktop/UOAA CLENAED/uoaa_hollistercleaned_updated.json" `
#   --output "C:/Users/nnaay/OneDrive/Desktop/UOAA CLENAED/uoaa_hollister_results.json" `
#   --batch-size 200 `
#   --workers 4


import os
import re
import json
import argparse
import threading
from typing import List, Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed


# -------------------- Optional VADER verification/override --------------------
USE_REAL_VADER = True  # set False to disable
VADER_TOL_COMPOUND = 0.05
VADER_TOL_PARTS = 0.10

def compute_vader_scores(text):
    try:
        from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
        analyzer = SentimentIntensityAnalyzer()
        vs = analyzer.polarity_scores(text or "")
        # Map to our expected keys
        return {
            "neg": float(vs.get("neg", 0.0)),
            "neu": float(vs.get("neu", 0.0)),
            "pos": float(vs.get("pos", 0.0)),
            "compound": float(vs.get("compound", 0.0))
        }
    except Exception as e:
        return None

def reconcile_with_vader(text, analysis_dict):
    """
    If VADER library is available, compute true VADER on the text and
    force Gemini scores to match within tolerance; if outside tolerance,
    snap to VADER scores.
    """
    if not isinstance(analysis_dict, dict):
        return analysis_dict

    if not USE_REAL_VADER:
        return analysis_dict

    vader = compute_vader_scores(text)
    if vader is None:
        return analysis_dict

    # Compare and adjust if outside tolerance
    changed = False
    for k in ("neg","neu","pos"):
        v = float(analysis_dict.get(k, 0.0))
        if abs(v - vader[k]) > VADER_TOL_PARTS:
            analysis_dict[k] = vader[k]
            changed = True
    comp = float(analysis_dict.get("compound", 0.0))
    if abs(comp - vader["compound"]) > VADER_TOL_COMPOUND:
        analysis_dict["compound"] = vader["compound"]
        changed = True

    # Renormalize parts to ~1.0 if needed
    s = sum(float(analysis_dict.get(k,0.0)) for k in ("neg","neu","pos"))
    if s > 0:
        for k in ("neg","neu","pos"):
            analysis_dict[k] = max(0.0, min(1.0, float(analysis_dict[k]) / s))
    # Adjust overall_sentiment if semantic label conflicts badly with compound sign
    # (still semantic-first, but if label contradicts strong VADER sign and text lacks clear polarity, nudge)
    try:
        label = analysis_dict.get("overall_sentiment")
        comp = float(analysis_dict.get("compound", 0.0))
        if label in ("positive","negative","neutral"):
            if label == "neutral" and abs(comp) >= 0.35:
                # Allow semantic-first; only adjust if no pros/cons and no clear quotes present
                if not analysis_dict.get("pros_aspects") and not analysis_dict.get("cons_aspects"):
                    analysis_dict["overall_sentiment"] = "positive" if comp > 0 else "negative"
            if label == "positive" and comp <= -0.35:
                if not analysis_dict.get("pros_aspects") and analysis_dict.get("cons_aspects"):
                    analysis_dict["overall_sentiment"] = "negative"
            if label == "negative" and comp >= 0.35:
                if not analysis_dict.get("cons_aspects") and analysis_dict.get("pros_aspects"):
                    analysis_dict["overall_sentiment"] = "positive"
    except Exception:
        pass
    return analysis_dict
# -----------------------------------------------------------------------------


# Third-party
from dotenv import load_dotenv
import google.generativeai as genai
from google.generativeai.types import GenerationConfig
from transformers import pipeline

# ----------------------------
# Config & Globals
# ----------------------------

VALID_PROS = [
    "skin_tolerance",
    "adhesion_reliability",
    "filter_effectiveness",
    "contour_conformity",
    "pouch_usability"
]
VALID_CONS = [
    "adhesive_irritation",
    "seal_compromise",
    "barrier_degradation",
    "pouch_functionality_issues",
    "product_durability_concerns"
]

EMOTION_MAPPING = {
    "joy": ["joy", "amusement", "excitement", "gratitude", "love", "optimism", "pride", "relief", "admiration", "approval", "caring", "desire"],
    "sadness": ["sadness", "disappointment", "grief", "remorse"],
    "fear": ["fear", "nervousness"],
    "disgust": ["disgust", "embarrassment"],
    "anger": ["anger", "annoyance", "disapproval"],
    "neutral": ["neutral", "confusion", "curiosity", "realization", "surprise"]
}

DEFAULT_BATCH_SIZE = 200
MAX_WORKERS = 4

# Disable parallelism warnings from tokenizers
os.environ["TOKENIZERS_PARALLELISM"] = "false"

# Precompiled regex helpers
EMOJI_PATTERN = re.compile(
    "["
    "\U0001F600-\U0001F64F"
    "\U0001F300-\U0001F5FF"
    "\U0001F680-\U0001F6FF"
    "\U0001F1E0-\U0001F1FF"
    "\U00002702-\U000027B0"
    "\U000024C2-\U0001F251"
    "]+"
)
URL_PATTERN = re.compile(r'http[s]?://\S+')
WHITESPACE_PATTERN = re.compile(r'\s+')

file_write_lock = threading.Lock()

# ----------------------------
# Helpers
# ----------------------------

def clean_text(text: str) -> str:
    """Basic forum text cleanup: drop emojis/URLs, normalize whitespace."""
    if not isinstance(text, str):
        return ""
    text = EMOJI_PATTERN.sub("", text)
    text = URL_PATTERN.sub("", text)
    text = WHITESPACE_PATTERN.sub(" ", text).strip()
    return text

def collapse_go_emotions(raw: List[Dict[str, Any]]) -> Dict[str, float]:
    """Map GoEmotions labels into 6 buckets and normalize to sum to 1.0 (if >0)."""
    buckets = {k: 0.0 for k in EMOTION_MAPPING.keys()}
    for item in raw or []:
        label = str(item.get("label", "")).lower()
        score = float(item.get("score", 0.0))
        for bucket, labels in EMOTION_MAPPING.items():
            if label in labels:
                buckets[bucket] += score
                break
    total = sum(buckets.values())
    if total > 0:
        for k in buckets:
            buckets[k] /= total
    return buckets

def load_uoaa_posts(json_path: str) -> List[Dict[str, Any]]:
    """
    Load UOAA data. Works for nested, flat, or JSONL formats.
    Compatible with files like uoaa_hollistercleaned_updated.json.
    """
    posts = []

    # Try to load normal JSON
    with open(json_path, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError:
            # Fallback for JSON Lines
            f.seek(0)
            for line in f:
                try:
                    obj = json.loads(line.strip())
                    if isinstance(obj, dict) and "text" in obj:
                        posts.append(obj)
                except json.JSONDecodeError:
                    continue
            return posts

    # ✅ Case 1: list of posts (your file type)
    if isinstance(data, list):
        if all("text" in d for d in data):
            return data
        # nested topics
        for topic in data:
            if "posts" in topic:
                for p in topic["posts"]:
                    p["topic_title"] = topic.get("topic_title")
                    p["topic_url"] = topic.get("topic_url")
                    posts.append(p)
        return posts

    # ✅ Case 2: single post dict
    if isinstance(data, dict) and "text" in data:
        return [data]

    return posts



# ----------------------------
# Models
# ----------------------------

def init_models():
    """Return (emotion_pipeline, gemini_model)."""
    print("🧠 Loading RoBERTa (GoEmotions) ...")
    emo = pipeline(
        task="text-classification",
        model="SamLowe/roberta-base-go_emotions",
        top_k=None,
        device=-1
    )
    print("✅ RoBERTa ready")

    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise EnvironmentError("Missing GEMINI_API_KEY in environment or .env")
    genai.configure(api_key=api_key)
    gem = genai.GenerativeModel(
        "gemini-2.0-flash",
        generation_config=GenerationConfig(temperature=0.2, top_p=1.0, top_k=40)
    )
    print("✅ Gemini model ready")

    return emo, gem

# ----------------------------
# Gemini Prompt
# ----------------------------

SYSTEM_PREAMBLE = """ROLE & DOMAIN
You are an expert in high-accuracy sentiment, emotion, and product-experience analysis for ostomy care discussions. Your task is to analyze forum posts and return results in a strictly structured JSON format.

CORE RULES & VERIFICATION REQUIREMENTS:
- NO HALLUCINATIONS: Do not invent brands, products, events, or facts not present in the text.
- EXPLICIT INFORMATION ONLY for brands, product names, product features, prices, and claims. If not literally written in the text, do not include it.
- INFERENCE ALLOWED ONLY for sentiment, emotional tone, and pros/cons classification. Never infer brands, product details, or factual information.
- CONFIDENCE THRESHOLD RULE:
    • 90%+ confidence (clearly stated in text) → include value
    • 70–89% confidence (implied but not explicit) → return "unknown"
    • <70% confidence (ambiguous or assumption-based) → return "unknown"
  This rule applies to ALL categorical fields except numeric sentiment scores.
- NO EXTERNAL KNOWLEDGE: Do not invent brand traits, product features, medical claims, or personal advice not in the text.
- STRICT JSON FORMAT: Use the exact structure requested. No added or missing keys.
- END RESPONSE immediately after the final closing brace. No explanation, no commentary, no apologies.

OVERALL SENTIMENT DECISION LOGIC (SEMANTIC-FIRST):
- Determine "overall_sentiment" primarily from the meaning of the text (praise/relief/satisfaction → positive; complaints/problems/pain/leaks/irritation/frustration → negative).
- The compound score is secondary support and must not override clear semantic polarity.
- Only choose "neutral" when the post is informational or lacks clear praise or complaint.
- When computing neg/neu/pos and compound, weight emotionally positive/negative experiences more strongly than neutral description; do not treat product failure or strong praise as neutral.

VADER-STYLE SCORING REQUIREMENT:
- Compute neg/neu/pos and compound **as VADER would** (polarity intensifiers, negations, punctuation/emphasis, mixed sentiment, contrastive conjunctions, etc.).
- Your numeric scores must be consistent with true VADER outputs within a small tolerance (±0.05 on compound; ±0.10 on neg/neu/pos). If unsure, emulate VADER defaults."""


# No examples; Gemini must produce VADER-style numbers natively.
INSTRUCTION_TEMPLATE = """Return a **single minified JSON object**. Do not use code fences. Exact keys only:

"post_meta": {{
  "topic_title": string|null,
  "topic_url": string|null,
  "post_url": string|null,
  "user": string|null,
  "date": string|null
}},
"targets": {{
  "brands_mentioned": string[],          // explicit only, no inference
  "explicit_product_terms": string[]     // pouches, filters, etc., only if text mentions them
}},
"analysis": {{
  "overall_sentiment": "positive"|"negative"|"neutral",   // semantic-first; compound is secondary
  "neg": number,                        // [0,1], VADER-like
  "neu": number,                        // [0,1], VADER-like
  "pos": number,                        // [0,1], VADER-like
  "compound": number,                   // [-1,1], VADER-like compound
  "primary_emotion": "joy"|"sadness"|"anger"|"fear"|"disgust"|"neutral"|"unknown",  // single dominant emotion
  "pros_aspects": string[],             // ONLY from: {pros_list}
  "cons_aspects": string[],             // ONLY from: {cons_list}
  "key_quotes": string[]                // 1–3 short verbatim spans, no stitching, no paraphrasing
}},
"rationale": string                     // 1–2 sentences, explain uncertainty if applicable

REQUIREMENTS:
- You MUST manually estimate neg/neu/pos/compound based strictly on the text using **VADER-like rules**; do NOT call external tools.
- Ensure neg+neu+pos ≈ 1.0.
- "overall_sentiment" must be determined primarily from the meaning of the text; the compound score is secondary support and must NOT override clear semantic polarity.
- If confidence < 90% for "overall_sentiment", set it to "neutral" and briefly explain in "rationale".
- Use "unknown" when confidence < 90% for categorical fields other than "overall_sentiment" (e.g., primary_emotion, brands_mentioned, explicit_product_terms, pros_aspects, cons_aspects).
- Do not invent missing fields; leave arrays empty if not found.

DATA INPUT SCOPE:
- TEXT is the exact 'text' field from the provided JSON post object. Analyze ONLY the provided TEXT; do not infer context from URLs, prior posts, or external sources.

Now analyze the following post:

TOPIC: "{topic_title}"
TOPIC_URL: {topic_url}
POST_URL: {post_url}
USER: {user}
DATE: {date}

TEXT:
<<<
{text}
>>>"""


# ----------------------------
# Processing
# ----------------------------

def analyze_post(record: Dict[str, Any],
                 emo_pipe,
                 gem_model) -> Dict[str, Any]:
    """Analyze one post with RoBERTa + Gemini. No post-fixes of Gemini's scores."""
    text = clean_text(record.get("text", ""))

    # 1) Emotions (RoBERTa)
    try:
        emo_raw = emo_pipe(text, truncation=True)[0]
        emo_list = emo_raw if isinstance(emo_raw, list) else []
    except Exception:
        emo_list = []
    emo_buckets = collapse_go_emotions(emo_list)
    top3 = sorted(emo_buckets.items(), key=lambda kv: kv[1], reverse=True)[:3]
    primary_emotions = [k for k, v in top3 if v > 0]

    # 2) Gemini JSON with VADER-like schema (no post-normalization)
    # Handle flexible field names in user dataset
    brand_value = record.get("brand")
    brands_list = []
    if isinstance(brand_value, str):
        brands_list = [brand_value.lower()]
    elif isinstance(brand_value, list):
        brands_list = [b.lower() for b in brand_value]

    # Build prompt dynamically to handle your file structure
    prompt = (
        SYSTEM_PREAMBLE
        + "\n\n"
        + INSTRUCTION_TEMPLATE.format(
            pros_list=", ".join(VALID_PROS),
            cons_list=", ".join(VALID_CONS),
            topic_title=record.get("topic_title") or "unknown topic",
            topic_url=json.dumps(record.get("topic_url") or ""),
            post_url=json.dumps(record.get("post_url") or ""),
            user=json.dumps(record.get("user") or ""),
            date=json.dumps(record.get("date") or ""),
            text=text
        )
        + f"\n\n(Additional metadata for context: brand(s)={brands_list}, match={record.get('match')})"
    )

    def _call_gemini(prompt_text: str) -> Dict[str, Any]:
        resp = gem_model.generate_content(prompt_text)
        gtxt = (getattr(resp, "text", "") or "").strip()
        if gtxt.startswith("```"):
            gtxt = gtxt.strip("`")
            if gtxt.startswith("json"):
                gtxt = gtxt[4:]
        return json.loads(gtxt)

    try:
        gjson = _call_gemini(prompt)
    except Exception:
        try:
            gjson = _call_gemini(prompt + "\nReturn ONLY valid minified JSON without code fences.")
        except Exception as e2:
            gjson = {
                "error": f"Gemini failure: {e2}",
                "analysis": {
                    "overall_sentiment": "unknown",
                    "neg": None, "neu": None, "pos": None, "compound": None,
                    "primary_emotions": []
                },
                "rationale": "Model error."
            }

    # 3) Resolved overall comes **only** from Gemini
    try:
        g_analysis = gjson.get("analysis", {}) if isinstance(gjson, dict) else {}
    except Exception:
        g_analysis = {}
    resolved_overall = {
        "source": "gemini",
        "overall_sentiment": g_analysis.get("overall_sentiment", "unknown")
    }

    # 4) Merge results
    out = {
        "topic": record.get("topic_title"),
        "post_meta": {
            "topic_title": record.get("topic_title"),
            "topic_url": record.get("topic_url"),
            "post_url": record.get("post_url"),
            "user": record.get("user"),
            "date": record.get("date"),
        },
        "text": text,
        "gemini": gjson,
        "roberta_emotions": emo_buckets,
        "primary_emotions": primary_emotions,
        "resolved_overall": resolved_overall
    }
    return out



def write_jsonl_batch(path: str, batch: List[Dict[str, Any]]):
    with file_write_lock:
        with open(path, "a", encoding="utf-8") as f:
            for row in batch:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

def run(input_path: str,
        output_path: Optional[str] = None,
        batch_size: int = DEFAULT_BATCH_SIZE,
        max_posts: int = 0,
        workers: int = MAX_WORKERS):
    print("DEBUG: running load_uoaa_posts from", os.path.abspath(__file__))
    posts = load_uoaa_posts(input_path)
    print("DEBUG: type of posts =", type(posts), "length =", len(posts))
    if len(posts) > 0:
        print("DEBUG: first record keys:", list(posts[0].keys()))
    if max_posts and max_posts > 0:
        posts = posts[:max_posts]

    total = len(posts)
    if total == 0:
        print("No posts found.")
        return


    emo_pipe, gem_model = init_models()

    if not output_path:
        base, _ = os.path.splitext(input_path)
        output_path = base + "_results.json"
    stream_path = output_path.replace(".json", ".jsonl")

    # Clear previous artifacts
    for p in (output_path, stream_path):
        if os.path.exists(p):
            os.remove(p)

    print(f"Processing {total} posts | batch={batch_size} | workers={workers} | Engine=Gemini-only (no post-fixes)")
    processed = 0
    all_results = []

    for start in range(0, total, batch_size):
        end = min(start + batch_size, total)
        batch = posts[start:end]
        print(f"→ Batch {start//batch_size+1}: {start+1}–{end}")

        indexed = list(enumerate(batch, start=start))
        out_batch = []

        with ThreadPoolExecutor(max_workers=workers) as ex:
            futures = {ex.submit(analyze_post, rec, emo_pipe, gem_model): idx for idx, rec in indexed}
            for fut in as_completed(futures):
                try:
                    out_batch.append(fut.result())
                except Exception as e:
                    out_batch.append({"error": f"worker failed: {e}"})

        write_jsonl_batch(stream_path, out_batch)
        all_results.extend(out_batch)
        processed += len(out_batch)
        print(f"✔ Batch done. {processed}/{total}")

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)

    print("✅ Completed.")
    print(f"- JSONL stream: {stream_path}")
    print(f"- Final JSON  : {output_path}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="UOAA forum analyzer (Gemini-only, VADER schema, no post-processing)")
    ap.add_argument("--input", "-i", required=True, help="Input JSON (UOAA export)")
    ap.add_argument("--output", "-o", help="Output JSON (default: <input>_results.json)")
    ap.add_argument("--batch-size", "-b", type=int, default=DEFAULT_BATCH_SIZE, help="Batch size")
    ap.add_argument("--max-posts", "-m", type=int, default=0, help="Max posts to process (0 = all)")
    ap.add_argument("--workers", "-w", type=int, default=MAX_WORKERS, help="Thread workers")
    args = ap.parse_args()

    run(
        input_path=args.input,
        output_path=args.output,
        batch_size=args.batch_size,
        max_posts=args.max_posts,
        workers=args.workers,
    )