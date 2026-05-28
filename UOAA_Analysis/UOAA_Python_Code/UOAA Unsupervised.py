
# -----------------------------------------------------------
# Coloplast Forum (UOAA) Unsupervised Topic Modeling via Gemini
# -----------------------------------------------------------

import os
import json
import pandas as pd
from google import genai
from google.genai import types
from dotenv import load_dotenv
from datetime import datetime
from pathlib import Path
import random

# ==========================
# 1️⃣ Load Environment
# ==========================
possible_paths = [
    Path(r"C:\Users\nnaay\Downloads\.env"),
    Path(r"C:\Users\nnaay\OneDrive\Desktop\.env"),
    Path.cwd() / ".env"
]
for path in possible_paths:
    if path.exists():
        load_dotenv(dotenv_path=path)
        print(f"✅ Loaded .env from: {path}")
        break
else:
    print("⚠️ No .env file found — using environment variables directly.")

# ==========================
# 2️⃣ Configuration
# ==========================
MODEL = "gemini-2.5-flash"
FILE_PATH = r"C:\Users\nnaay\OneDrive\Desktop\UOAA CLENAED\uoaa_coloplast_cleaned.json"
DATE_SUFFIX = datetime.now().strftime("%Y-%m-%d")

api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise ValueError("❌ GEMINI_API_KEY not found in environment.")

client = genai.Client(api_key=api_key)
print("🔑 Gemini API key loaded successfully!")

# ==========================
# 3️⃣ Load Dataset (UOAA Forum)
# ==========================
# Load JSON file safely (forum data should be an array)
with open(FILE_PATH, "r", encoding="utf-8") as f:
    data = json.load(f)

df = pd.DataFrame(data)
if "text" not in df.columns:
    raise ValueError("❌ Your JSON must include a 'text' field.")
print(f"✅ Loaded {len(df)} forum posts from: {FILE_PATH}")

# Optionally sample if file is large
sample_texts = random.sample(df["text"].tolist(), min(1000, len(df)))

# Combine posts for Gemini input
combined_text = "\n\n".join(sample_texts)

# ==========================
# 4️⃣ Gemini Prompt — UOAA Forum Topic Modeling
# ==========================
prompt = f"""
You are an expert social media and healthcare forum analyst specializing in ostomy products.

You are given text data from **UOAA (United Ostomy Association of America)** user discussions about **Hollister and Coloplast ostomy products**.

Your task:
1. Perform **unsupervised topic modeling** directly from the text.
2. Identify **5 positive topics** and **5 negative topics** based on user discussions.
3. Each topic must represent a **clear product attribute or user experience aspect**, not a brand name or general opinion.
4. Follow this structure carefully:
   - Use **short, specific topic names** in `snake_case` (e.g., `adhesive_strength`, `skin_gentleness`, `filter_performance`).
   - Focus on **attributes** like durability, adhesion, comfort, usability, design, and filter effectiveness.
   - Avoid combining attributes with conditions (e.g., "ileostomy_barrier_breakdown" → use "barrier_durability" with context "ileostomy").
   - Avoid user-specific words or conditions in topic_name; if relevant, place them under `"context_tags"`.

Each topic must include:
- `"topic_name"`: the product attribute or experience aspect (1–2 words)
- `"topic_summary"`: 1–2 sentences summarizing what users say
- `"representative_keywords"`: list of 3–6 related words or phrases
- `"sentiment"`: either "positive" or "negative"
- Optional `"outcome"`: describe if the topic refers to a failure or success outcome (e.g., "breakdown", "leakage")
- Optional `"context_tags"`: list of contextual factors like {{ "stoma_type": "ileostomy" }}, {{ "activity_level": "high" }}, {{ "climate": "humid" }}

Examples:
✅ Good topic names:
  - reliable_adhesion
  - barrier_durability
  - setup_convenience
  - filter_performance
  - skin_gentleness

❌ Bad topic names:
  - ileostomy_barrier_breakdown
  - poor_design_quality
  - happy_with_service

At the end, include **two Python-style lists** for your final classification schema:
- `valid_pros = [list of positive topic_name values]`
- `valid_cons = [list of negative topic_name values]`

Return a **single valid JSON object only**, following this exact format:

{{
  "positive_topics": [
    {{
      "topic_name": "...",
      "topic_summary": "...",
      "representative_keywords": ["..."],
      "sentiment": "positive",
      "outcome": "...",
      "context_tags": [{{"stoma_type": "..."}}]
    }}
  ],
  "negative_topics": [
    {{
      "topic_name": "...",
      "topic_summary": "...",
      "representative_keywords": ["..."],
      "sentiment": "negative",
      "outcome": "...",
      "context_tags": [{{"stoma_type": "..."}}]
    }}
  ],
  "valid_pros": ["..."],
  "valid_cons": ["..."]
}}

Analyze carefully and output only valid JSON.
"""


# ==========================
# 5️⃣ Call Gemini API
# ==========================
response = client.models.generate_content(
    model=MODEL,
    contents=prompt + "\n\nHere are the UOAA forum posts:\n" + combined_text[:25000],
    config=types.GenerateContentConfig(temperature=0.4)
)

text = response.text.strip()
if "```" in text:
    text = text.replace("```json", "").replace("```", "").strip()

try:
    topics_json = json.loads(text)
except Exception:
    print("⚠️ Could not parse JSON output. Saving raw text instead.")
    topics_json = {"raw_output": text}
    # 🧹 Remove any 'unknown' values if Gemini still includes them accidentally
if isinstance(topics_json, dict):
    if "valid_pros" in topics_json:
        topics_json["valid_pros"] = [t for t in topics_json["valid_pros"] if t.lower() != "unknown"]
    if "valid_cons" in topics_json:
        topics_json["valid_cons"] = [t for t in topics_json["valid_cons"] if t.lower() != "unknown"]

# ==========================
# 6️⃣ Save Results
# ==========================
output_json = f"UOAA_Coloplast_Unsupervised_Topics_{DATE_SUFFIX}.json"
with open(output_json, "w", encoding="utf-8") as f:
    json.dump(topics_json, f, indent=2, ensure_ascii=False)

print(f"✅ Saved Gemini unsupervised topic results → {output_json}")