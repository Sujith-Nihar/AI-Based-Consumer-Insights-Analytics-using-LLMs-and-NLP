
# -----------------------------------------------------------
# Hollister Forum (UOAA) Unsupervised Topic Modeling via Gemini
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
FILE_PATH = r"/Users/johnny/Desktop/ostomywork/merged_coloplast_all_sources_UPDATED.json"
DATE_SUFFIX = datetime.now().strftime("%Y-%m-%d")

api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise ValueError("❌ GEMINI_API_KEY not found in environment.")

client = genai.Client(api_key=api_key)
print("🔑 Gemini API key loaded successfully!")

# ==========================
# 3️⃣ Load & Clean Dataset
# ==========================
data = []
with open(FILE_PATH, "r", encoding="utf-8") as f:
    first_line = f.readline().strip()
    f.seek(0)

    # detect if file is a JSON array or NDJSON
    if first_line.startswith("["):
        # Standard JSON array
        data = json.load(f)
    else:
        # NDJSON (one JSON object per line)
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                data.append(json.loads(line))
            except json.JSONDecodeError:
                # ignore any malformed lines
                continue

print(f"✅ Loaded {len(data)} forum posts from: {FILE_PATH}")
# --- Normalize structure ---
cleaned = []
for item in data:
    text = item.get("body") or item.get("text") or item.get("full_text") or ""
    text = " ".join(text.split())  # clean up whitespace
    cleaned.append({
        "id": item.get("id", ""),
        "author": item.get("author", "unknown"),
        "brands": item.get("brands", []),
        "source": "UOAA",
        "text": text.strip()
    })

df = pd.DataFrame(cleaned)
print(f"✅ Cleaned and structured {len(df)} posts")

# --- Optional sampling if file is large ---
sample_texts = random.sample(df["text"].tolist(), min(1000, len(df)))

# --- Combine posts for Gemini input ---
combined_text = "\n\n".join(sample_texts)
print(f"🧩 Prepared {len(sample_texts)} posts for Gemini analysis")


# ==========================
# 4️⃣ Gemini Prompt — UOAA Forum Topic Modeling
# ==========================
prompt = f"""
You are an expert social media and healthcare forum analyst specializing in ostomy products.

You are given text data from **UOAA (United Ostomy Association of America)** user discussions about **Hollister ostomy products**.

Your task:
1. Perform unsupervised topic modeling directly from the text.
2. Identify **5 positive topics** and **5 negative topics** based on user discussions.
3. Each topic must represent a clear aspect of user experience or product attribute — for example:
   - Positive examples: comfort, reliability, ease_of_use, customer_support, value
   - Negative examples: leakage_problems, skin_irritation, odor_issues, adhesive_failure, poor_fit
4. Use short, specific topic names (snake_case preferred, e.g., "skin_irritation").
5. Each topic must include:
   - "topic_name": one or two words only
   - "topic_summary": 1–2 sentences summarizing what users say
   - "representative_keywords": list of 3–6 related keywords
   - "sentiment": "positive" or "negative"
6. At the end, include two Python-style lists:
   - valid_pros = [list of all positive topic names only]
   - valid_cons = [list of all negative topic names only]

Return a **single valid JSON object only**, following this exact format:

{{
  "positive_topics": [
    {{
      "topic_name": "...",
      "topic_summary": "...",
      "representative_keywords": ["..."],
      "sentiment": "positive"
    }}
  ],
  "negative_topics": [
    {{
      "topic_name": "...",
      "topic_summary": "...",
      "representative_keywords": ["..."],
      "sentiment": "negative"
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

# --- Clean unknown values ---
if isinstance(topics_json, dict):
    if "valid_pros" in topics_json:
        topics_json["valid_pros"] = [t for t in topics_json["valid_pros"] if t.lower() != "unknown"]
    if "valid_cons" in topics_json:
        topics_json["valid_cons"] = [t for t in topics_json["valid_cons"] if t.lower() != "unknown"]
# ==========================
# 6️⃣ Save Results
# ==========================
output_json = f"Ostomy_submissions_Coloplast_Unsupervised_Topics_{DATE_SUFFIX}.json"
with open(output_json, "w", encoding="utf-8") as f:
    json.dump(topics_json, f, indent=2, ensure_ascii=False)

print(f"✅ Saved Gemini unsupervised topic results → {output_json}")
