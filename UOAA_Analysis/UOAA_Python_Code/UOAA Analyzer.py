
# -----------------------------------------------------------
# UOAA Coloplast Forum Supervised Topic + Emotion Analyzer (Gemini 2.5 Flash)
# With tqdm progress bar + autosave + resume checkpoint
# -----------------------------------------------------------

import os
import json
import pandas as pd
import logging
from google import genai
from google.genai import types
from dotenv import load_dotenv
from datetime import datetime
from pathlib import Path
from tqdm import tqdm

# ===============================
# ⚙️ Setup
# ===============================
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Load environment (.env)
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

# Gemini setup
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise ValueError("❌ GEMINI_API_KEY not found.")
client = genai.Client(api_key=api_key)
print("🔑 Gemini API key loaded successfully!")

# ===============================
# 📂 Load Dataset (Handles JSON arrays correctly)
# ===============================
DATA_FILE = r"C:\Users\nnaay\OneDrive\Desktop\UOAA CLENAED\uoaa_coloplast_cleaned.json"
DATE_SUFFIX = datetime.now().strftime("%Y-%m-%d")

data = []
with open(DATA_FILE, "r", encoding="utf-8") as f:
    content = f.read().strip()
    try:
        loaded = json.loads(content)
        if isinstance(loaded, list):
            data = loaded
        elif isinstance(loaded, dict):
            data = [loaded]
        else:
            print("⚠️ Unexpected JSON structure — check file format.")
    except json.JSONDecodeError:
        f.seek(0)
        for line in f:
            line = line.strip()
            if line:
                try:
                    data.append(json.loads(line))
                except json.JSONDecodeError:
                    pass

df = pd.DataFrame(data)
if "body" in df.columns:
    df = df.rename(columns={"body": "text"})
print(f"✅ Loaded {len(df)} forum posts from {DATA_FILE}")
print("🧾 Columns detected:", df.columns.tolist())
print(df.head(2)[["text"]])

# ===============================
# 🔍 Gemini Prompt + JSON Extractor
# ===============================
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

def extract_json_from_response(response_text):
    """Robust JSON extraction with bracket counting."""
    response_text = response_text.strip()
    try:
        return json.loads(response_text)
    except json.JSONDecodeError:
        pass
    start_idx = response_text.find("{")
    if start_idx == -1:
        return None
    bracket_count = 0
    in_string = False
    escape_next = False
    for i in range(start_idx, len(response_text)):
        c = response_text[i]
        if escape_next:
            escape_next = False
            continue
        if c == "\\":
            escape_next = True
            continue
        if c == '"' and not escape_next:
            in_string = not in_string
            continue
        if not in_string:
            if c == "{":
                bracket_count += 1
            elif c == "}":
                bracket_count -= 1
                if bracket_count == 0:
                    json_str = response_text[start_idx:i + 1]
                    try:
                        return json.loads(json_str)
                    except:
                        return None
    return None

# ===============================
# 🧠 Gemini Analyzer
# ===============================
def analyze_post_with_gemini(post_text):
    """Classify forum post into topics + detect emotion (Gemini 2.5 Flash)."""
    prompt = f"""
You are an expert healthcare forum analyst. 
You MUST return only valid JSON — no explanations, no commentary.

We have 10 exact discussion topics about Coloplast ostomy products:

Positive:
{', '.join(VALID_PROS)}

Negative:
{', '.join(VALID_CONS)}

TASK:
1. Assign the following forum post to exactly ONE of those topics.
2. Set sentiment = "positive" if topic from Positive list, else "negative".
3. Generate a short reason (<=2 sentences).
4. Estimate emotion intensities (joy, sadness, fear, disgust, anger, neutral) as floats summing to ~1.0.
5. Return only valid JSON — do NOT include text outside curly braces.

Forum Post:
\"\"\"{post_text[:1500]}\"\"\" 

Return this JSON ONLY:
{{
  "best_topic": "one_of_{VALID_PROS + VALID_CONS}",
  "sentiment": "positive" or "negative",
  "confidence": 0.0–1.0,
  "reason": "1–2 sentences",
  "emotions": {{
    "joy": float,
    "sadness": float,
    "fear": float,
    "disgust": float,
    "anger": float,
    "neutral": float
  }},
  "dominant_emotion": "one_of_the_above"
}}
If you cannot decide, pick the closest topic (never 'unknown').
Output only the JSON — nothing else.
"""

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.2)
        )
        raw_output = response.text.strip()
        print("\n🔹 Gemini raw output preview:", raw_output[:350], "\n")
        clean_text = raw_output.replace("```json", "").replace("```", "").strip()
        try:
            parsed = json.loads(clean_text)
        except Exception:
            parsed = extract_json_from_response(clean_text)

        if not parsed or not isinstance(parsed, dict):
            print("⚠️ Gemini did not return valid JSON — fallback applied.")
            parsed = {
                "best_topic": "unknown",
                "sentiment": "unknown",
                "confidence": 0.0,
                "reason": "parse_error_or_non_json_response",
                "emotions": {
                    "joy": 0.0, "sadness": 0.0, "fear": 0.0,
                    "disgust": 0.0, "anger": 0.0, "neutral": 1.0
                },
                "dominant_emotion": "neutral"
            }
        return parsed

    except Exception as e:
        print(f"❌ Gemini call failed: {e}")
        return {
            "best_topic": "unknown",
            "sentiment": "unknown",
            "confidence": 0.0,
            "reason": str(e),
            "emotions": {
                "joy": 0.0, "sadness": 0.0, "fear": 0.0,
                "disgust": 0.0, "anger": 0.0, "neutral": 1.0
            },
            "dominant_emotion": "neutral"
        }

# ===============================
# 🔄 Resume from checkpoint
# ===============================
CHECKPOINT_FILE = "checkpoint_Coloplast_uoaa.json"
output_records = []

if os.path.exists(CHECKPOINT_FILE):
    with open(CHECKPOINT_FILE, "r", encoding="utf-8") as f:
        output_records = json.load(f)
    processed_ids = {r["post_id"] for r in output_records if "post_id" in r}
    print(f"🔁 Resuming from checkpoint — {len(processed_ids)} posts already done.")
else:
    processed_ids = set()
    print("🚀 Starting fresh — no checkpoint found.")

# ===============================
# 🧾 Run Analysis with tqdm + autosave
# ===============================
for i, row in tqdm(df.iterrows(), total=len(df), desc="🔍 Analyzing posts", unit="post"):
    post_id = row.get("id", i)
    if post_id in processed_ids:
        continue  # skip already done

    post_text = str(row.get("text", "")).strip()
    brand = row.get("brand", "")
    match = row.get("match", "")

    result = analyze_post_with_gemini(post_text)

    result.update({
        "post_id": post_id,
        "brand": brand,
        "match": match,
        "text": post_text,
        "topic_url": row.get("topic_url", ""),
        "topic_title": row.get("topic_title", ""),
        "post_index": row.get("post_index", ""),
        "user": row.get("user", ""),
        "date": row.get("date", ""),
        "post_url": row.get("post_url", "")
    })
    output_records.append(result)

    # 💾 Save every 25 posts to avoid data loss
    if len(output_records) % 25 == 0:
        with open(CHECKPOINT_FILE, "w", encoding="utf-8") as f:
            json.dump(output_records, f, indent=2, ensure_ascii=False)
        pd.DataFrame(output_records).to_csv("checkpoint_uoaa.csv", index=False, encoding="utf-8-sig")
        logging.info(f"💾 Saved checkpoint at {len(output_records)} posts.")

# ===============================
# 🎉 Final Save
# ===============================
final_json = f"UOAA_Coloplast_Gemini_Supervised_Emotion_{DATE_SUFFIX}.json"
final_csv = f"UOAA_Coloplast_Gemini_Supervised_Emotion_{DATE_SUFFIX}.csv"

with open(final_json, "w", encoding="utf-8") as f:
    json.dump(output_records, f, indent=2, ensure_ascii=False)
pd.DataFrame(output_records).to_csv(final_csv, index=False, encoding="utf-8-sig")

print(f"\n✅ Final results saved:")
print(f"   • JSON: {final_json}")
print(f"   • CSV:  {final_csv}")
print("🎉 Analysis complete — all posts classified, autosaved, and checkpointed.")
