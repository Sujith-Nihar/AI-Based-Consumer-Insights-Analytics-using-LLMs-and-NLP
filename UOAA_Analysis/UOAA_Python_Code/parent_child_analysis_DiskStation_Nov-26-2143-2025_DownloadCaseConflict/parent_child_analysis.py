#!/usr/bin/env python
"""
UOAA Ostomy Forum Analysis with Topic Content

1) Reads nested JSON: topics -> posts, with keys:
   - topic_title
   - topic_url
   - topic_content  (NEW: full OP text / description)
   - posts: [ { post_url, user, date, text, brands, match, index, ... }, ... ]

2) For each post, calls Gemini to get:
   - topic_sentiment (based on topic_title + topic_content)
   - post_sentiment  (based on post text)
   - stance          (agree / disagree / mixed / unknown) of post vs topic

3) Aggregates per topic:
   - stance counts: agree / disagree / mixed / unknown
   - post sentiment counts: positive / negative / neutral / unknown
   - topic_sentiment_final (topic-level final label)

Outputs:
   - Per-post JSON with stance + sentiment
   - Per-topic CSV summary

Usage:

  pip install google-generativeai
  export GOOGLE_API_KEY="your_api_key_here"

  python uoaa_topic_content_stance_pipeline.py \
      --input uoaa_coloplast_with_topic_content.json

"""

import argparse
import csv
import json
import os
from collections import Counter, defaultdict
from typing import Any, Dict, List, Tuple

import google.generativeai as genai


# ----------------------------
# Gemini Prompt Template
# ----------------------------

STANCE_SENTIMENT_PROMPT_TEMPLATE = """
ROLE & EXPERTISE
You are an expert in analyzing ostomy-related forum posts, medical product discussions, patient experiences, sentiment classification, and stance detection.

OVERALL TASK
Your job is to:
1) Determine the sentiment of the TOPIC using BOTH the topic title and the full topic content (OP text).
2) Determine the sentiment of the REPLY POST based on its full text.
3) Determine the stance of the REPLY POST relative to the TOPIC: whether the post agrees, disagrees, is mixed, or unknown.
4) Return ONLY one minified JSON object in the required format. No extra commentary.

IMPORTANT DISTINCTION
- SENTIMENT = emotional tone of each text by itself (topic vs post).
- STANCE = relationship between the POST and the TOPIC (do they express the same opinion/experience or the opposite?).

──────────────── SENTIMENT RULES ────────────────
You must output sentiment for BOTH:
- topic_sentiment  → based on TOPIC_TITLE + TOPIC_CONTENT together.
- post_sentiment   → based ONLY on POST_TEXT.

For each (topic and post):

1) Semantic sentiment (primary):
   - "positive":
       praise, satisfaction, relief, good outcomes, gratitude, things working well.
       Examples: "works great", "no leaks", "very happy", "finally solved it".
   - "negative":
       complaints, problems, frustration, pain, leaks, failures, irritation, fear.
       Examples: "keeps leaking", "terrible", "hurts", "not working well at all".
   - "neutral":
       mostly informational, factual, or question-style text with little or no emotion.
       Examples: "What pouch size do you use?", "I switched brands last month."

2) VADER-style scores (supportive, not primary):
   - Provide "neg", "neu", "pos" ∈ [0,1] and "compound" ∈ [-1,1].
   - These scores should be consistent with the semantic sentiment.

3) Final sentiment resolution ("final"):
   - Start from the semantic sentiment based on meaning.
   - Use VADER scores to check for major conflicts.
   - If semantic and numeric conflict strongly, adjust to the label that best matches the actual text meaning and the overall numeric pattern.
   - As a numeric fallback:
       • compound > 0.25 → positive
       • compound < -0.25 → negative
       • otherwise → neutral

Do NOT hallucinate emotion:
- If tone is not clearly emotional, choose "neutral".
- Do NOT guess sentiment based on your own knowledge of brands or products.

──────────────── STANCE RULES (AGREE/DISAGREE/MIXED/UNKNOWN) ────────────────
Stance compares the meaning of POST_TEXT to the meaning of the TOPIC (TOPIC_TITLE + TOPIC_CONTENT).

Allowed stance labels:
- "agree"
- "disagree"
- "mixed"
- "unknown"

Definitions:

• "agree"
  - The post clearly confirms, supports, or reports a similar experience/opinion as the topic.
  - Example:
      Topic: title + content complain that "Coloplast products are leaking / not working well."
      Post:  "I used these Coloplast products and they are not working well either."
      → stance = "agree"

• "disagree"
  - The post clearly contradicts or rejects the topic’s main claim.
  - Example:
      Topic: title + content say "Coloplast products are leaking and bad."
      Post:  "I've used Coloplast for years and never had leaks; they work great."
      → stance = "disagree"

• "mixed"
  - The post expresses both agreement and disagreement in a meaningful way.
  - Example:
      Topic: "Coloplast is terrible."
      Post:  "Some Coloplast bags leaked for me, but others worked really well."
      → stance = "mixed"

• "unknown"
  - The post does not clearly agree or disagree with the topic.
  - The post might:
      - be off-topic,
      - only ask questions,
      - only give neutral advice,
      - or be too vague to determine stance.

CRITICAL:
- Do NOT infer stance from sentiment alone.
  - A negative post about Coloplast can still AGREE with a negative topic about Coloplast.
  - A positive post about Coloplast can DISAGREE with a negative topic about Coloplast.
- Always compare the *meaning* of POST_TEXT to the *combined meaning* of TOPIC_TITLE + TOPIC_CONTENT.

──────────────── INPUT ────────────────
TOPIC_TITLE: {topic_title}
TOPIC_URL: {topic_url}

TOPIC_CONTENT:
<<<
{topic_content}
>>>

POST_URL: {post_url}
USER: {user}

POST_TEXT:
<<<
{post_text}
>>>

──────────────── OUTPUT FORMAT (STRICT) ────────────────
Return exactly ONE minified JSON object with this structure:

{{
  "topic_meta":{{
    "topic_title":string|null,
    "topic_url":string|null
  }},
  "topic_sentiment":{{
    "semantic":"positive"|"negative"|"neutral",
    "vader":{{"neg":number,"neu":number,"pos":number,"compound":number}},
    "final":"positive"|"negative"|"neutral"
  }},
  "post_meta":{{
    "post_url":string|null,
    "user":string|null
  }},
  "post_sentiment":{{
    "semantic":"positive"|"negative"|"neutral",
    "vader":{{"neg":number,"neu":number,"pos":number,"compound":number}},
    "final":"positive"|"negative"|"neutral"
  }},
  "stance":{{
    "label":"agree"|"disagree"|"mixed"|"unknown",
    "confidence":number,
    "rationale_short":string
  }}
}}

CONSTRAINTS
- JSON must be valid and minified (no pretty printing).
- No markdown, no code fences, no text outside the JSON.
- Do NOT invent brands, products, or medical facts not present in the text.
"""


# ----------------------------
# Data loading & flattening
# ----------------------------

def load_input(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def flatten_topics(data: Any) -> List[Dict[str, Any]]:
    """
    Flatten nested topics JSON into a list of post-level records.

    Each output record has:
      - topic_title, topic_url, topic_content
      - post_url, user, date, text, brands, match, etc.
    """
    posts: List[Dict[str, Any]] = []

    if not isinstance(data, list):
        raise ValueError("Expected top-level list in input JSON (topics list).")

    is_topic_like = any(isinstance(item, dict) and "posts" in item for item in data)
    if not is_topic_like:
        raise ValueError("Input does not look like nested topic structure with 'posts'.")

    for topic in data:
        if not isinstance(topic, dict):
            continue

        topic_title = topic.get("topic_title")
        topic_url = topic.get("topic_url")
        topic_content = topic.get("topic_content") or ""

        topic_posts = topic.get("posts") or []
        if not topic_posts:
            continue

        for p in topic_posts:
            rec = dict(p)  # shallow copy of the post dict
            rec["topic_title"] = topic_title
            rec["topic_url"] = topic_url
            rec["topic_content"] = topic_content
            posts.append(rec)

    return posts


# ----------------------------
# Gemini helpers
# ----------------------------

def build_stance_prompt(record: Dict[str, Any]) -> str:
    topic_title = record.get("topic_title") or "unknown topic"
    topic_url_raw = record.get("topic_url") or ""
    topic_content = record.get("topic_content") or ""

    post_text = record.get("text") or ""
    post_url_raw = record.get("post_url") or ""
    user_raw = record.get("user") or ""

    return STANCE_SENTIMENT_PROMPT_TEMPLATE.format(
        topic_title=topic_title,
        topic_url=topic_url_raw,
        topic_content=topic_content,
        post_url=post_url_raw,
        user=user_raw,
        post_text=post_text,
    )


def call_gemini(model: genai.GenerativeModel, prompt: str) -> Dict[str, Any]:
    """
    Call Gemini and robustly parse the JSON output.
    """

    def _call(prompt_text: str) -> Dict[str, Any]:
        resp = model.generate_content(prompt_text)
        text = (getattr(resp, "text", "") or "").strip()

        # Strip code fences if any
        if text.startswith("```"):
            text = text.strip("`").strip()
            if text.lower().startswith("json"):
                text = text[4:].strip()
        return json.loads(text)

    try:
        return _call(prompt)
    except Exception:
        try:
            return _call(prompt + "\nReturn ONLY valid minified JSON without code fences.")
        except Exception as e:
            # Fallback if still fails
            return {
                "topic_meta": {
                    "topic_title": None,
                    "topic_url": None,
                },
                "topic_sentiment": {
                    "semantic": "neutral",
                    "vader": {"neg": 0.0, "neu": 1.0, "pos": 0.0, "compound": 0.0},
                    "final": "neutral",
                },
                "post_meta": {
                    "post_url": None,
                    "user": None,
                },
                "post_sentiment": {
                    "semantic": "neutral",
                    "vader": {"neg": 0.0, "neu": 1.0, "pos": 0.0, "compound": 0.0},
                    "final": "neutral",
                },
                "stance": {
                    "label": "unknown",
                    "confidence": 0.0,
                    "rationale_short": f"Fallback due to parsing error: {str(e)[:120]}",
                },
            }


# ----------------------------
# Aggregation helpers
# ----------------------------

def aggregate_by_topic(records: List[Dict[str, Any]]):
    """
    Group by (topic_title, topic_url) and count:
      - stance labels: agree/disagree/mixed/unknown
      - post sentiment labels: positive/negative/neutral/unknown
    Also keep topic-level final sentiment (from Gemini's topic_sentiment.final).
    """
    topics_stance: Dict[Tuple[str, str], Counter] = defaultdict(Counter)
    topics_sentiment: Dict[Tuple[str, str], Counter] = defaultdict(Counter)
    topic_post_counts: Dict[Tuple[str, str], int] = Counter()
    topic_final_sentiment: Dict[Tuple[str, str], str] = {}

    for rec in records:
        topic_title = rec.get("topic_title") or "unknown topic"
        topic_url = rec.get("topic_url") or ""
        key = (topic_title, topic_url)

        stance_analysis = rec.get("stance_analysis") or {}
        stance_block = stance_analysis.get("stance") or {}
        label = (stance_block.get("label") or "unknown").lower().strip()
        if label not in {"agree", "disagree", "mixed", "unknown"}:
            label = "unknown"
        topics_stance[key][label] += 1

        # Post-level sentiment
        post_sent_block = stance_analysis.get("post_sentiment") or {}
        post_final = (post_sent_block.get("final") or "unknown").lower().strip()
        if post_final not in {"positive", "negative", "neutral"}:
            post_final = "unknown"
        topics_sentiment[key][post_final] += 1

        # Topic-level sentiment (final)
        topic_sent_block = stance_analysis.get("topic_sentiment") or {}
        t_final = (topic_sent_block.get("final") or "").lower().strip()
        if t_final and key not in topic_final_sentiment:
            topic_final_sentiment[key] = t_final

        topic_post_counts[key] += 1

    return topics_stance, topics_sentiment, topic_post_counts, topic_final_sentiment


def write_topic_csv(
    csv_path: str,
    topics_stance: Dict[Tuple[str, str], Counter],
    topics_sentiment: Dict[Tuple[str, str], Counter],
    topic_post_counts: Dict[Tuple[str, str], int],
    topic_final_sentiment: Dict[Tuple[str, str], str],
) -> None:
    fieldnames = [
        "topic_title",
        "topic_url",
        "total_posts",
        # stance counts
        "agree",
        "disagree",
        "mixed",
        "unknown_stance",
        # sentiment counts
        "positive_posts",
        "negative_posts",
        "neutral_posts",
        "unknown_sentiment_posts",
        # topic-level sentiment
        "topic_sentiment_final",
    ]

    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for (title, url), stance_counts in topics_stance.items():
            sent_counts = topics_sentiment.get((title, url), Counter())
            total = topic_post_counts[(title, url)]
            row = {
                "topic_title": title,
                "topic_url": url,
                "total_posts": total,
                "agree": stance_counts.get("agree", 0),
                "disagree": stance_counts.get("disagree", 0),
                "mixed": stance_counts.get("mixed", 0),
                "unknown_stance": stance_counts.get("unknown", 0),
                "positive_posts": sent_counts.get("positive", 0),
                "negative_posts": sent_counts.get("negative", 0),
                "neutral_posts": sent_counts.get("neutral", 0),
                "unknown_sentiment_posts": sent_counts.get("unknown", 0),
                "topic_sentiment_final": topic_final_sentiment.get((title, url), "unknown"),
            }
            writer.writerow(row)


def print_topic_summary(
    topics_stance: Dict[Tuple[str, str], Counter],
    topics_sentiment: Dict[Tuple[str, str], Counter],
    topic_post_counts: Dict[Tuple[str, str], int],
    topic_final_sentiment: Dict[Tuple[str, str], str],
) -> None:
    print("\nPer-topic stance + sentiment summary (truncated titles):\n")
    header = [
        "Topic Title",
        "Total",
        "Agree",
        "Disagree",
        "Mixed",
        "UnknownSt",
        "Pos",
        "Neg",
        "Neu",
        "TopicSent",
    ]
    print(" | ".join(header))
    print("-" * 140)

    for (title, url), stance_counts in topics_stance.items():
        sent_counts = topics_sentiment.get((title, url), Counter())
        total = topic_post_counts[(title, url)]
        row = [
            title[:50].replace("\n", " "),
            str(total),
            str(stance_counts.get("agree", 0)),
            str(stance_counts.get("disagree", 0)),
            str(stance_counts.get("mixed", 0)),
            str(stance_counts.get("unknown", 0)),
            str(sent_counts.get("positive", 0)),
            str(sent_counts.get("negative", 0)),
            str(sent_counts.get("neutral", 0)),
            topic_final_sentiment.get((title, url), "unknown"),
        ]
        print(" | ".join(row))


# ----------------------------
# Main pipeline
# ----------------------------

def run_pipeline(
    input_path: str,
    post_output_path: str,
    topic_output_path: str,
    model_name: str,
) -> None:
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("GOOGLE_API_KEY environment variable is not set.")
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(model_name)

    print(f"[INFO] Loading input from: {input_path}")
    data = load_input(input_path)
    posts = flatten_topics(data)
    print(f"[INFO] Found {len(posts)} posts across topics.")

    results: List[Dict[str, Any]] = []

    for idx, rec in enumerate(posts, start=1):
        text = (rec.get("text") or "").strip()
        if not text:
            print(f"[WARN] Post {idx} has empty text; skipping.")
            continue

        prompt = build_stance_prompt(rec)
        stance_json = call_gemini(model, prompt)

        out_rec: Dict[str, Any] = {
            "topic_title": rec.get("topic_title"),
            "topic_url": rec.get("topic_url"),
            "topic_content": rec.get("topic_content"),
            "post_meta": {
                "post_url": rec.get("post_url"),
                "user": rec.get("user"),
                "date": rec.get("date"),
                "index": rec.get("index"),
                "brands": rec.get("brands"),
                "match": rec.get("match"),
            },
            "text": rec.get("text"),
            "stance_analysis": stance_json,
        }
        results.append(out_rec)

        if idx % 10 == 0:
            print(f"[INFO] Processed {idx} posts...")

    # Write per-post results
    print(f"[INFO] Writing per-post stance + sentiment results to: {post_output_path}")
    with open(post_output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    # Aggregate per topic
    topics_stance, topics_sentiment, topic_post_counts, topic_final_sentiment = aggregate_by_topic(results)
    print_topic_summary(topics_stance, topics_sentiment, topic_post_counts, topic_final_sentiment)

    # Write per-topic CSV
    print(f"[INFO] Writing per-topic stance + sentiment summary CSV to: {topic_output_path}")
    write_topic_csv(topic_output_path, topics_stance, topics_sentiment, topic_post_counts, topic_final_sentiment)

    print("\n[DONE] Full stance + sentiment pipeline complete.\n")


# ----------------------------
# CLI
# ----------------------------

def main():
    parser = argparse.ArgumentParser(
        description="UOAA ostomy forum stance + sentiment pipeline using topic content (Gemini per-post + per-topic aggregation)."
    )
    parser.add_argument(
        "--input",
        "-i",
        required=True,
        help="Input JSON (nested topics with topic_content, e.g., uoaa_coloplast_with_topic_content.json).",
    )
    parser.add_argument(
        "--post-output",
        "-p",
        help="Per-post JSON output path (default: <input_basename>_stance_posts.json).",
    )
    parser.add_argument(
        "--topic-output",
        "-t",
        help="Per-topic CSV output path (default: <input_basename>_topic_stance_summary.csv).",
    )
    parser.add_argument(
        "--model",
        "-m",
        default="gemini-2.0-flash",
        help="Gemini model name to use (default: gemini-2.0-flash).",
    )

    args = parser.parse_args()

    base, _ = os.path.splitext(args.input)
    post_output = args.post_output or f"{base}_stance_posts.json"
    topic_output = args.topic_output or f"{base}_topic_stance_summary.csv"

    run_pipeline(
        input_path=args.input,
        post_output_path=post_output,
        topic_output_path=topic_output,
        model_name=args.model,
    )


if __name__ == "__main__":
    main()
