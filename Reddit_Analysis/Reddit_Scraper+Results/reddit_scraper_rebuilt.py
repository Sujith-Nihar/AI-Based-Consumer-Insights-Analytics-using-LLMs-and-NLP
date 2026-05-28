#!/usr/bin/env python3
"""
Reddit Scraper (rebuilt) — posts (+ optional comments) to JSON & CSV
--------------------------------------------------------------------
- Scrapes one or more subreddits (default: ostomy-related list)
- Saves timestamped outputs under outputs/run_YYYYMMDD_HHMMSS/
- Produces:
    * reddit_<scope>_<YYYYMMDD_HHMMSS>.json
    * reddit_<scope>_<YYYYMMDD_HHMMSS>.csv
    * reddit_<scope>_<YYYYMMDD_HHMMSS>_with_comments.json  (if --include-comments)
- Handles rate limits (HTTP 429) and transient errors with exponential backoff
- Uses environment variables for credentials:
    REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USER_AGENT
Usage examples (Windows PowerShell):
    $env:REDDIT_CLIENT_ID="your_id"
    $env:REDDIT_CLIENT_SECRET="your_secret"
    $env:REDDIT_USER_AGENT="RedditScraper/1.0 by u/yourusername"
    python reddit_scraper_rebuilt.py --subs "ostomy,OstomyCare,Ileostomy" --limit 500 --include-comments
"""

from __future__ import annotations
import os
import sys
import csv
import time
import json
import math
import argparse
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Iterable, Optional

try:
    import praw
    import prawcore
except Exception as e:
    print("PRAW is required. Install with: pip install praw", file=sys.stderr)
    raise

# ---------------------------
# Helpers
# ---------------------------

def ts_now() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")

def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)

def setup_logging(log_path: Path) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_path, encoding="utf-8")
        ],
    )

def redact(s: Optional[str]) -> str:
    if not s:
        return ""
    if len(s) <= 6:
        return "***"
    return s[:3] + "..." + s[-3:]

# ---------------------------
# Core Scraper
# ---------------------------

class RedditScraper:
    def __init__(self, client_id: str, client_secret: str, user_agent: str, read_only: bool = True):
        self.reddit = praw.Reddit(
            client_id=client_id,
            client_secret=client_secret,
            user_agent=user_agent,
            ratelimit_seconds=5,  # small safety buffer
        )
        self.reddit.read_only = read_only
        logging.info("Initialized Reddit client (read_only=%s).", read_only)

    def _backoff_sleep(self, attempt: int, base: float = 2.0, cap: float = 120.0) -> None:
        # Exponential backoff with jitter
        delay = min(cap, (base ** attempt)) + (0.1 * attempt)
        delay = max(delay, 1.0)
        logging.warning("Backing off for %.1f seconds (attempt %d)...", delay, attempt)
        time.sleep(delay)

    def _fetch_submissions(self, subreddit: str, limit: int) -> Iterable[Any]:
        """Fetch 'new' submissions from a subreddit with retry/backoff."""
        attempt = 0
        while True:
            try:
                return self.reddit.subreddit(subreddit).new(limit=limit)
            except (prawcore.exceptions.RequestException,
                    prawcore.exceptions.ServerError,
                    prawcore.exceptions.ResponseException) as e:
                attempt += 1
                logging.error("Transient error on subreddit '%s': %s", subreddit, repr(e))
                self._backoff_sleep(attempt)
            except Exception as e:
                logging.exception("Unexpected error while fetching from '%s': %s", subreddit, repr(e))
                raise

    def _flatten_comment(self, c) -> Dict[str, Any]:
        return {
            "id": c.id,
            "parent_id": c.parent_id,
            "link_id": c.link_id,
            "author": getattr(c.author, "name", None),
            "created_utc": getattr(c, "created_utc", None),
            "body": getattr(c, "body", None),
            "score": getattr(c, "score", None),
            "permalink": f"https://www.reddit.com{getattr(c, 'permalink', '')}",
            "is_submitter": getattr(c, "is_submitter", None),
            "distinguished": getattr(c, "distinguished", None),
            "stickied": getattr(c, "stickied", None),
            "controversiality": getattr(c, "controversiality", None),
        }

    def _flatten_submission(self, s) -> Dict[str, Any]:
        return {
            "id": s.id,
            "title": s.title,
            "author": getattr(s.author, "name", None),
            "created_utc": getattr(s, "created_utc", None),
            "selftext": getattr(s, "selftext", ""),
            "url": getattr(s, "url", None),
            "permalink": f"https://www.reddit.com{getattr(s, 'permalink', '')}",
            "subreddit": str(getattr(s, "subreddit", "")),
            "upvote_ratio": getattr(s, "upvote_ratio", None),
            "score": getattr(s, "score", None),
            "num_comments": getattr(s, "num_comments", 0),
            "over_18": getattr(s, "over_18", None),
            "spoiler": getattr(s, "spoiler", None),
            "stickied": getattr(s, "stickied", None),
            "author_flair_text": getattr(s, "author_flair_text", None),
            "link_flair_text": getattr(s, "link_flair_text", None),
        }

    def fetch_posts(
        self, subreddit: str, limit: int, include_comments: bool = False
    ) -> List[Dict[str, Any]]:
        logging.info("Fetching up to %d posts from r/%s (include_comments=%s)...", limit, subreddit, include_comments)
        posts = []
        attempt = 0
        submissions_iter = self._fetch_submissions(subreddit, limit=limit)
        for s in submissions_iter:
            while True:
                try:
                    post = self._flatten_submission(s)
                    if include_comments:
                        # Load all comments without MoreComments
                        s.comments.replace_more(limit=0)
                        post["comments"] = [self._flatten_comment(c) for c in s.comments.list()]
                    posts.append(post)
                    break  # success, move to next submission
                except (prawcore.exceptions.RequestException,
                        prawcore.exceptions.ServerError,
                        prawcore.exceptions.ResponseException) as e:
                    attempt += 1
                    logging.error("Error processing submission %s: %s", getattr(s, "id", "?"), repr(e))
                    self._backoff_sleep(attempt)
                except Exception as e:
                    logging.exception("Unexpected error on submission %s: %s", getattr(s, "id", "?"), repr(e))
                    # Skip this submission but continue
                    break
        logging.info("Fetched %d posts from r/%s.", len(posts), subreddit)
        return posts

# ---------------------------
# I/O
# ---------------------------

def write_json(path: Path, data: Any) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def write_csv(path: Path, posts: List[Dict[str, Any]]) -> None:
    # Flatten for CSV (exclude comments)
    fieldnames = [
        "id","title","author","created_utc","selftext","url","permalink",
        "subreddit","upvote_ratio","score","num_comments","over_18","spoiler",
        "stickied","author_flair_text","link_flair_text"
    ]
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for p in posts:
            w.writerow(p)

# ---------------------------
# CLI
# ---------------------------

DEFAULT_SUBS = [
    "ostomy","OstomyCare","Ileostomy","Urostomy","CrohnsDisease","UlcerativeColitis","IBD",
    "colorectalcancer","coloncancer","Diverticulitis","InflammatoryBowelDisease","ColorectalSurgery",
    "nursing","woundcare","HomeHealthNursing","medicalsupplies","medicine","ChronicIllness","Disability",
    "AdaptiveFashion","BodyAcceptance","BodyPositive","AssistiveTechnology","medicaldevices","MedTech",
    "HealthInsurance","AskDocs","Surgery","WOCN","Endo","endometriosis","spinalcordinjuries","StomaLife"
]

def parse_args(argv: List[str]) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Reddit scraper for posts (and optional comments).")
    ap.add_argument("--subs", type=str, default=",".join(DEFAULT_SUBS),
                    help="Comma-separated list of subreddits (default is an ostomy-related list).")
    ap.add_argument("--subs-file", type=str, default=None,
                    help="Optional path to a file with one subreddit per line.")
    ap.add_argument("--limit", type=int, default=500, help="Max posts per subreddit (default 500).")
    ap.add_argument("--include-comments", action="store_true", help="Also fetch all comments for each post.")
    ap.add_argument("--outdir", type=str, default="outputs", help="Base output folder (default: outputs).")
    return ap.parse_args(argv)

def load_subs(args: argparse.Namespace) -> List[str]:
    if args.subs_file:
        path = Path(args.subs_file)
        if not path.exists():
            raise FileNotFoundError(f"subs-file not found: {path}")
        subs = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    else:
        subs = [s.strip() for s in args.subs.split(",") if s.strip()]
    # de-duplicate preserving order
    seen = set()
    uniq = []
    for s in subs:
        if s.lower() not in seen:
            seen.add(s.lower())
            uniq.append(s)
    return uniq

def main(argv: List[str]) -> int:
    args = parse_args(argv)

    client_id = os.getenv("REDDIT_CLIENT_ID")
    client_secret = os.getenv("REDDIT_CLIENT_SECRET")
    user_agent = os.getenv("REDDIT_USER_AGENT")

    if not all([client_id, client_secret, user_agent]):
        print("ERROR: Please set REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, and REDDIT_USER_AGENT env vars.", file=sys.stderr)
        return 2

    subs = load_subs(args)
    scope = subs[0] if len(subs) == 1 else "multi"

    run_stamp = ts_now()
    run_dir = Path(args.outdir) / f"run_{run_stamp}"
    ensure_dir(run_dir)

    log_path = run_dir / "scrape.log"
    setup_logging(log_path)

    logging.info("Starting scrape.")
    logging.info("Subs: %s", subs)
    logging.info("Limit per sub: %d", args.limit)
    logging.info("Include comments: %s", args.include_comments)
    logging.info("Outdir: %s", str(run_dir))
    logging.info("Auth: id=%s secret=%s ua=%s",
                 redact(client_id), redact(client_secret), user_agent)

    scraper = RedditScraper(client_id, client_secret, user_agent, read_only=True)

    all_posts: List[Dict[str, Any]] = []
    total_comments = 0
    for sub in subs:
        posts = scraper.fetch_posts(sub, limit=args.limit, include_comments=args.include_comments)
        all_posts.extend(posts)
        if args.include_comments:
            total_comments += sum(len(p.get("comments", [])) for p in posts)

    # Sort by created_utc desc for consistency
    all_posts.sort(key=lambda p: p.get("created_utc", 0) or 0, reverse=True)

    base_name = f"reddit_{scope}_{run_stamp}"
    json_path = run_dir / f"{base_name}.json"
    csv_path = run_dir / f"{base_name}.csv"
    write_json(json_path, all_posts)
    write_csv(csv_path, all_posts)

    if args.include_comments:
        comments_json_path = run_dir / f"{base_name}_with_comments.json"
        write_json(comments_json_path, all_posts)
        logging.info("Wrote posts+comments JSON: %s", str(comments_json_path))

    # Summary
    flat_count = len(all_posts)
    nested = flat_count
    if args.include_comments:
        nested = total_comments  # just to mirror your prior printout style where nested might reflect comments count

    print(f" Done!")
    print(f"  {json_path}")
    print(f"  {csv_path}")
    if args.include_comments:
        print(f"  {comments_json_path}")
    print(f"[scrape] posts={flat_count} | comments={total_comments if args.include_comments else 0}")
    print(f"Logs: {log_path}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
