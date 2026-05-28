#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
from typing import Any, Dict, List

from dotenv import load_dotenv
import google.generativeai as genai
from google.generativeai.types import GenerationConfig

# ===================== CONFIG =====================

# 1) Paths – CHANGE INPUT_PATH to your file
# For you, this is likely "both_brands_filtered.json"
INPUT_PATH = "both_brands_filtered.json"
OUTPUT_PATH = "hollister_coloplast_data_with_user_preference.json"

# 2) Gemini model
GEMINI_MODEL_NAME = "gemini-2.0-flash"  # or "gemini-1.5-pro"

# ==================================================

# ---------- Load API key & model ----------

def init_gemini():
    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not found in environment or .env file")

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(
        GEMINI_MODEL_NAME,
        generation_config=GenerationConfig(
            temperature=0.2,
            top_p=1.0,
            top_k=40,
        ),
    )
    print("✅ Gemini model ready:", GEMINI_MODEL_NAME)
    return model


# ---------- Helper: dataset sentiment from your results ----------

def get_dataset_sentiment(post: Dict[str, Any]) -> str:
    """
    Use the sentiment already computed in your analysis results.
    Priority:
      1) post["resolved_overall"]["overall_sentiment"]
      2) post["gemini"]["analysis"]["overall_sentiment"]
      3) "unknown"
    """
    resolved = post.get("resolved_overall") or {}
    if isinstance(resolved, dict) and "overall_sentiment" in resolved:
        return resolved["overall_sentiment"]

    g_analysis = post.get("gemini", {}).get("analysis", {})
    if isinstance(g_analysis, dict) and "overall_sentiment" in g_analysis:
        return g_analysis["overall_sentiment"]

    return "unknown"


def get_brands_from_post(post: Dict[str, Any]) -> List[str]:
    """
    Get brands from your analysis results:
      post["gemini"]["targets"]["brands_mentioned"]
    """
    tgt = post.get("gemini", {}).get("targets", {})
    brands = tgt.get("brands_mentioned", []) if isinstance(tgt, dict) else []
    if not isinstance(brands, list):
        return []
    return [b for b in brands if isinstance(b, str)]


# ---------- Preference prompt ----------

PREFERENCE_PROMPT_TEMPLATE = """
ROLE & TASK
You are an expert in analysis of ostomy forums and product comparisons.
Your job is to carefully read a single forum POST_TEXT plus existing sentiment,
and decide:
1) Which brand the author prefers in this post.
2) Which key product attributes/keywords the preference is based on.

IMPORTANT — SENTIMENT IS FIXED
- You are NOT allowed to infer or change the sentiment.
- SENTIMENT is already computed in the dataset.
- Simply REPEAT the EXACT SENTIMENT provided in INPUT_SENTIMENT.
- Do NOT modify it. Do NOT reinterpret it.

NO HALLUCINATIONS (CRITICAL)
- Do NOT invent any new brand names, products, or companies.
- You may ONLY reason about brands present in BRANDS_MENTIONED.
- "user_preference" MUST be one of:
    "hollister", "coloplast", "both", "neither", "unknown"

INPUTS
- POST_TEXT: the full content of the user's post.
- BRANDS_MENTIONED: list of brands in the post (e.g., ["hollister","coloplast"]).
- INPUT_SENTIMENT: sentiment from the dataset (e.g., "positive", "negative", "neutral").
- SENTIMENT_RATIONALE: optional short rationale from the dataset (can be empty).

USER_PREFERENCE DEFINITIONS
- "hollister"  → The post clearly favors Hollister over Coloplast overall.
- "coloplast"  → The post clearly favors Coloplast over Hollister overall.
- "both"       → The post expresses similarly positive views of BOTH brands.
- "neither"    → The post is negative or dissatisfied with BOTH brands overall.
- "unknown"    → No clear preference signal, mixed/confusing, or mostly informational.

PREFERENCE_KEYWORDS
Return 1–5 short, lower_snake_case product attributes such as:
- adhesion_reliability
- skin_tolerance
- odor_control
- seal_compromise
- product_durability
- pouch_functionality_issues
- ease_of_use
- cost_affordability
- filter_effectiveness

Use simple, reusable tokens that capture why the user prefers (or dislikes) a brand.

OUTPUT
Return ONLY this exact JSON structure:

{
  "user_preference": "<hollister|coloplast|both|neither|unknown>",
  "preference_confidence": <number between 0 and 1>,
  "preference_reason": "<short natural language explanation>",
  "sentiment": "<EXACT INPUT_SENTIMENT>",
  "preference_keywords": ["<keyword1>", "<keyword2>", "..."]
}

RULES
- Do NOT infer or change sentiment; "sentiment" MUST equal INPUT_SENTIMENT.
- Do NOT add extra fields.
- Do NOT add commentary outside the JSON.
- Do NOT wrap the JSON in markdown fences.
- The JSON must be strictly valid.
"""


def build_preference_prompt(post: Dict[str, Any]) -> (str, str):
    """
    Build the full prompt text for Gemini for one post,
    and return (prompt, dataset_sentiment).
    """
    text = post.get("text", "")
    brands = get_brands_from_post(post)
    dataset_sentiment = get_dataset_sentiment(post)
    g_analysis = post.get("gemini", {}).get("analysis", {})
    sentiment_rationale = g_analysis.get("rationale", "")

    prompt = f"""{PREFERENCE_PROMPT_TEMPLATE}

POST_TEXT:
<<<
{text}
>>>

BRANDS_MENTIONED:
{brands}

INPUT_SENTIMENT:
"{dataset_sentiment}"

SENTIMENT_RATIONALE:
"{sentiment_rationale}"
"""
    return prompt, dataset_sentiment


# ---------- Gemini call with JSON parsing + fallback (similar style to your analyzer) ----------

def call_gemini_preference(model, prompt_text: str, dataset_sentiment: str) -> Dict[str, Any]:
    """
    Call Gemini and parse JSON. If anything fails, fall back to 'unknown' preference,
    but ALWAYS keep sentiment = dataset_sentiment.
    """

    def _call_once(p: str) -> Dict[str, Any]:
        resp = model.generate_content(p)
        gtxt = (getattr(resp, "text", "") or "").strip()
        if gtxt.startswith("```"):
            gtxt = gtxt.strip("`")
            if gtxt.startswith("json"):
                gtxt = gtxt[4:]
        return json.loads(gtxt)

    try:
        obj = _call_once(prompt_text)
    except Exception:
        # Retry with extra instruction (same style as your analysis file)
        try:
            obj = _call_once(prompt_text + "\nReturn ONLY valid minified JSON without code fences.")
        except Exception as e2:
            # Hard fallback
            obj = {
                "user_preference": "unknown",
                "preference_confidence": 0.0,
                "preference_reason": f"Gemini failure: {e2}",
                "sentiment": dataset_sentiment,
                "preference_keywords": []
            }

    # Enforce sentiment from dataset, regardless of what model says
    obj["sentiment"] = dataset_sentiment

    # Ensure all expected keys exist with correct types
    if "user_preference" not in obj or obj["user_preference"] not in (
        "hollister", "coloplast", "both", "neither", "unknown"
    ):
        obj["user_preference"] = "unknown"
    if "preference_confidence" not in obj:
        obj["preference_confidence"] = 0.0
    if "preference_reason" not in obj:
        obj["preference_reason"] = ""
    if "preference_keywords" not in obj or not isinstance(obj["preference_keywords"], list):
        obj["preference_keywords"] = []

    return obj


# ---------- Main pipeline ----------

def main():
    # 1) init model
    model = init_gemini()

    # 2) load your analysis results
    if not os.path.exists(INPUT_PATH):
        raise FileNotFoundError(f"Input file not found: {INPUT_PATH}")

    with open(INPUT_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    print(f"Loaded {len(data)} posts from {INPUT_PATH}")

    updated: List[Dict[str, Any]] = []

    for idx, post in enumerate(data):
        brands = [b.lower() for b in get_brands_from_post(post)]
        # Only analyze posts where BOTH Hollister & Coloplast are mentioned
        if "hollister" in brands and "coloplast" in brands:
            prompt, ds_sent = build_preference_prompt(post)
            pref_obj = call_gemini_preference(model, prompt, ds_sent)

            # Attach results at top-level
            post["user_preference"] = pref_obj["user_preference"]
            post["user_preference_confidence"] = pref_obj["preference_confidence"]
            post["user_preference_reason"] = pref_obj["preference_reason"]
            post["sentiment"] = pref_obj["sentiment"]
            post["preference_keywords"] = pref_obj["preference_keywords"]

            # OPTIONAL: also store under gemini.analysis for convenience
            g = post.get("gemini")
            if isinstance(g, dict):
                ga = g.get("analysis")
                if isinstance(ga, dict):
                    ga["user_preference"] = pref_obj["user_preference"]
                    ga["user_preference_confidence"] = pref_obj["preference_confidence"]
                    ga["preference_keywords"] = pref_obj["preference_keywords"]

        # Append post (modified or not) to final list
        updated.append(post)

    # 3) save output
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(updated, f, ensure_ascii=False, indent=2)

    print(f"✅ Saved {len(updated)} posts with preference info to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
