#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import argparse
from datetime import datetime
from typing import List, Dict, Any

from dotenv import load_dotenv
import google.generativeai as genai
from google.generativeai.types import GenerationConfig


VALID_PROS = [
    "product_range",
    "customer_support",
    "belt_integration",
    "deep_convexity",
    "high_volume_bags"
]

VALID_CONS = [
    "skin_irritation",
    "adhesive_issues",
    "pouch_detachment",
    "filter_limitations",
    "barrier_comfort"
]

#gemini prompt!1!1!
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

INSTRUCTION_TEMPLATE = """Return a **single minified JSON object**. Do not use code fences. Exact keys only:

"id": string|null,
"stored_id": string|null,
"created_utc": string|null,
"body": string|null,
"targets": {
  "brands_mentioned": string[],
  "explicit_product_terms": string[]
},
"analysis": {
  "overall_sentiment": "positive"|"negative"|"neutral",
  "neg": number,
  "neu": number,
  "pos": number,
  "compound": number,
  "primary_emotion": "joy"|"sadness"|"anger"|"fear"|"disgust"|"neutral"|"unknown",
  "pros_aspects": string[],
  "cons_aspects": string[],
  "key_quotes": string[]
},
"rationale": string

REQUIREMENTS:
- You MUST manually estimate neg/neu/pos/compound based strictly on the text using **VADER-like rules**; do NOT call external tools.
- Ensure neg+neu+pos ≈ 1.0.
- "overall_sentiment" must be determined primarily from the meaning of the text; the compound score is secondary support and must NOT override clear semantic polarity.
- If confidence < 90% for "overall_sentiment", set it to "neutral" and briefly explain in "rationale".
- Use "unknown" when confidence < 90% for categorical fields other than "overall_sentiment".
- Do not invent missing fields; leave arrays empty if not found.

DATA INPUT SCOPE:
- TEXT is the exact 'text' field from the provided JSON post object. Analyze ONLY the provided TEXT; do not infer context from URLs, prior posts, or external sources.

Now analyze the following post:

ID: {id}
STORED_ID: {stored_id}
CREATED_UTC: {created_utc}

TEXT:
<<<
{text}
>>>"""
#end prompt

def load_reddit_posts(json_path: str) -> List[Dict[str, Any]]:
    with open(json_path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    if isinstance(raw, dict) and isinstance(raw.get("data"), list):
        data = raw["data"]
    elif isinstance(raw, list):
        data = raw
    else:
        raise ValueError("(¬▂¬) invalid JSON structure detected >:( expected a list or {'data': [...]} but received something cursed")

    print("loaded {} raw records!1! •⩊•".format(len(data)))
    posts = []

    for item in data:
        text = item.get("body") or item.get("selftext") or ""
        title = item.get("title") or ""
        if not (text or title):
            continue
        full_text = (title + "\n\n" + text).strip() if title and text else (text or title)

        post_id = str(item.get("id") or item.get("name") or "")
        if not post_id:
            continue
        stored_id = "reddit_{}".format(post_id)

        created = item.get("created_utc")
        if isinstance(created, (int, float)):
            created_iso = datetime.utcfromtimestamp(created).isoformat() + "Z"
        else:
            created_iso = created

        posts.append({
            "id": post_id,
            "stored_id": stored_id,
            "created_utc": created_iso,
            "body": full_text
        })

    print("{} posts are all shiny & ready for Gemini (˶ˆᗜˆ˵)".format(len(posts)))
    return posts


def init_gemini():
    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise EnvironmentError("no GEMINI_API_KEY found (ᗒᗣᗕ)՞")
    genai.configure(api_key=api_key)
    print("Gemini warmed up and caffeinated (╭☞ ͡ ͡°͜ ʖ ͡ ͡°)╭☞")
    return genai.GenerativeModel(
        "gemini-2.0-flash",
        generation_config=GenerationConfig(temperature=0.2, top_p=1.0, top_k=40)
    )


def build_prompt(post: Dict[str, Any]) -> str:
    # Start from the raw template
    tpl = INSTRUCTION_TEMPLATE

    # Replace only the placeholders we actually intend to fill
    tpl = tpl.replace("{id}", json.dumps(post.get("id")))
    tpl = tpl.replace("{stored_id}", json.dumps(post.get("stored_id")))
    tpl = tpl.replace("{created_utc}", json.dumps(post.get("created_utc")))
    tpl = tpl.replace("{text}", post.get("body") or "")

    # Prepend the system preamble
    return SYSTEM_PREAMBLE + "\n\n" + tpl


def call_gemini(model, prompt: str) -> Dict[str, Any]:
    resp = model.generate_content(prompt)
    t = (getattr(resp, "text", "") or "").strip()
    if t.startswith("```"):
        t = t.strip("`")
        if t.startswith("json"):
            t = t[4:]
    return json.loads(t)


def progress(idx, total):
    bar_len = 30
    frac = idx / total
    filled = int(bar_len * frac)
    bar = "[" + "#" * filled + "-" * (bar_len - filled) + "]"
    print("\r{} analyzing heck yeah :)) {}/{} ({}%)".format(bar, idx, total, int(frac*100)), end="", flush=True)


def analyze_file(input_path: str, output_path: str, max_posts: int = 50):
    posts = load_reddit_posts(input_path)

    # limit posts if max_posts is set
    if max_posts and max_posts > 0:
        posts = posts[:max_posts]

    if not posts:
        print("hellos there are no posts here :( ")
        return

    model = init_gemini()
    results = []

    total = len(posts)
    print("Commencing analysis blast-off (ง'̀-'́)ง (max_posts = {})".format(max_posts))

    for idx, post in enumerate(posts, start=1):
        try:
            prompt = build_prompt(post)
            gjson = call_gemini(model, prompt)
        except Exception as e:
            gjson = {"error": str(e) + " LOL Gemini said no xP"}

        results.append({
            "id": post.get("id"),
            "stored_id": post.get("stored_id"),
            "created_utc": post.get("created_utc"),
            "body": post.get("body"),
            "gemini": gjson
        })

        progress(idx, total)

    print("\nsaving results... *dramatic drum roll*")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print("DONE !1!1! file saved @ {} ≽^•⩊•^≼ ₊˚⊹♡".format(output_path))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", "-i", required=True)
    parser.add_argument("--output", "-o")
    parser.add_argument("--max-posts", "-m", type=int, default=50)
    args = parser.parse_args()

    in_file = args.input
    out_file = args.output or in_file.replace(".json", "_gemini_results.json")

    analyze_file(in_file, out_file, args.max_posts)
