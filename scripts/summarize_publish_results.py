"""Summarize persisted results only; never call a publishing API."""
import argparse
import json
import os
from pathlib import Path

RESULTS = {
    "instagram": ("instagram-publish-results.json", "instagram"),
    "instagram_reel": ("instagram-reel-publish-results.json", "instagram_reel"),
    "facebook": ("facebook-publish-results.json", "facebook"),
    "linkedin": ("linkedin-publish-results.json", "linkedin"),
    "linkedin_en": ("linkedin-english-publish-results.json", "linkedin"),
    "x": ("x-publish-results.json", "x"),
    "reddit": ("reddit-publish-results.json", "reddit"),
}


def inspect_result(payload, channel):
    if not isinstance(payload, dict):
        return "invalid result"
    if payload.get("errors"):
        return "API error (see publish-log)"
    result = payload.get(channel)
    if not isinstance(result, dict):
        return "missing channel result"
    if result.get("status") == "skipped":
        if result.get("reason") in {
            "duplicate_caption", "instagram_activity_cooldown",
        }:
            return "skipped"
        return "unrecognized skip"
    if result.get("id") or result.get("urn"):
        return "published"
    posts = result.get("posts")
    if isinstance(posts, list) and posts and all(
            isinstance(post, dict) and post.get("id") for post in posts):
        return "published"
    return "missing publication ID"


def summarize(content_dir, scope="all", dry_run=False, cooldown=False):
    if scope != "all" and scope not in RESULTS:
        raise ValueError("Unsupported publish scope")
    if dry_run:
        paths = [("validation", "github-actions-publish-results.json", None)]
    else:
        paths = [(label, *entry) for label, entry in RESULTS.items()
                 if scope == "all" or label == scope]
    rows = []
    for label, filename, channel in paths:
        # The workflow emits one shared cooldown result for both IG formats.
        if label == "instagram_reel" and cooldown:
            filename, channel = RESULTS["instagram"]
        try:
            payload = json.loads((content_dir / filename).read_text(encoding="utf-8"))
        except FileNotFoundError:
            status = "not completed (no result)"
        except (OSError, UnicodeError, ValueError):
            status = "unreadable result"
        else:
            if dry_run:
                status = ("validated only" if isinstance(payload, dict)
                          and payload.get("image_urls") and not payload.get("errors")
                          else "invalid validation result")
            else:
                status = inspect_result(payload, channel)
                if label == "instagram_reel" and cooldown and status != "skipped":
                    status = "missing cooldown result"
        rows.append((label, status))
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--content-dir", required=True)
    parser.add_argument("--scope", default="all")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--instagram-cooldown", action="store_true")
    args = parser.parse_args()
    rows = summarize(Path(args.content_dir), args.scope, args.dry_run,
                     args.instagram_cooldown)
    text = "## Publish results\n\n" + "\n".join(
        f"- {label}: {status}" for label, status in rows)
    text += ("\n\nPartial publication may have occurred. Do not rerun the whole "
             "publishing job without reconciling existing posts.\n")
    print(text)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as handle:
            handle.write(text)
    return int(any(status not in {"published", "skipped", "validated only"}
                   for _, status in rows))


if __name__ == "__main__":
    raise SystemExit(main())
