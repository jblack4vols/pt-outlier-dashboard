"""
Daily rotator cuff / shoulder recovery YouTube outlier scan.

What this does, in order:
1. Picks 10-15 channels in the shoulder surgery recovery / physical therapy /
   orthopedic rehab space, favoring channels under 100k subscribers, and
   avoiding channels scanned in the last 4 weeks (see data/channels_seen.json).
2. For each channel, pulls long-form videos (Shorts excluded) posted in the
   last 60 days and their view counts.
3. Computes each channel's baseline = median views of those videos.
4. Flags any video doing 3x or more its own channel's baseline.
5. For each flagged outlier, asks Claude to break down why the title/idea
   worked and to write a rewritten title + hook for the rotator cuff
   recovery audience.
6. Writes the result to data/outliers.json, ranked biggest multiplier first.

Requires two environment variables (set as GitHub Actions repo secrets):
  YOUTUBE_API_KEY   - YouTube Data API v3 key
  ANTHROPIC_API_KEY - Claude API key

Run manually with: python scripts/scan_channels.py
"""

import json
import os
import statistics
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
OUTLIERS_PATH = DATA_DIR / "outliers.json"
SEEN_PATH = DATA_DIR / "channels_seen.json"

YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")

# Search queries used to discover candidate channels each week. The script
# rotates through these and skips anything already scanned in the last
# 4 weeks, so the list refreshes over time instead of repeating.
SEARCH_QUERIES = [
    "rotator cuff surgery recovery",
    "shoulder surgery recovery journey",
    "rotator cuff repair rehab",
    "post op shoulder physical therapy",
    "shoulder replacement recovery vlog",
    "torn rotator cuff surgery",
    "physical therapy for shoulder pain",
    "frozen shoulder recovery",
    "shoulder impingement rehab",
    "labrum repair recovery",
]

MAX_CHANNELS = 15
MIN_CHANNELS = 10
MAX_SUBS_PRIORITY = 100_000
LOOKBACK_DAYS = 60
OUTLIER_MULTIPLIER = 3.0
MIN_VIDEOS_FOR_BASELINE = 3


def yt_get(endpoint: str, params: dict) -> dict:
    params = {**params, "key": YOUTUBE_API_KEY}
    resp = requests.get(f"https://www.googleapis.com/youtube/v3/{endpoint}", params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def load_seen() -> dict:
    if SEEN_PATH.exists():
        return json.loads(SEEN_PATH.read_text())
    return {"note": "", "weeks": {}}


def save_seen(seen: dict) -> None:
    cutoff = datetime.now(timezone.utc) - timedelta(weeks=4)
    pruned = {
        week: ids
        for week, ids in seen.get("weeks", {}).items()
        if datetime.fromisoformat(week) >= cutoff
    }
    seen["weeks"] = pruned
    SEEN_PATH.write_text(json.dumps(seen, indent=2))


def recently_seen_ids(seen: dict) -> set:
    ids = set()
    for week_ids in seen.get("weeks", {}).values():
        ids.update(week_ids)
    return ids


def discover_channels(exclude_ids: set) -> list:
    """Search-discover candidate channel IDs, prioritizing smaller channels."""
    candidates = {}
    for query in SEARCH_QUERIES:
        try:
            result = yt_get(
                "search",
                {"part": "snippet", "q": query, "type": "channel", "maxResults": 10},
            )
        except requests.HTTPError as exc:
            print(f"Search failed for '{query}': {exc}", file=sys.stderr)
            continue
        for item in result.get("items", []):
            channel_id = item["snippet"]["channelId"]
            if channel_id not in exclude_ids:
                candidates[channel_id] = item["snippet"]["title"]
        if len(candidates) >= MAX_CHANNELS * 3:
            break

    if not candidates:
        return []

    ids = list(candidates.keys())
    channel_details = []
    for i in range(0, len(ids), 50):
        batch = ids[i : i + 50]
        result = yt_get(
            "channels",
            {"part": "statistics,contentDetails,snippet", "id": ",".join(batch)},
        )
        channel_details.extend(result.get("items", []))

    small = [c for c in channel_details if int(c["statistics"].get("subscriberCount", 0)) < MAX_SUBS_PRIORITY]
    large = [c for c in channel_details if int(c["statistics"].get("subscriberCount", 0)) >= MAX_SUBS_PRIORITY]

    small.sort(key=lambda c: int(c["statistics"].get("subscriberCount", 0)))
    large.sort(key=lambda c: int(c["statistics"].get("subscriberCount", 0)))

    picked = (small + large)[:MAX_CHANNELS]
    if len(picked) < MIN_CHANNELS:
        print(f"Warning: only found {len(picked)} candidate channels this run.", file=sys.stderr)
    return picked


def get_recent_long_form_videos(channel: dict) -> list:
    """Return (video_id, title, published_at, view_count) for long-form videos in the lookback window."""
    uploads_playlist = channel["contentDetails"]["relatedPlaylists"]["uploads"]
    cutoff = datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)

    video_ids = []
    page_token = None
    while True:
        result = yt_get(
            "playlistItems",
            {
                "part": "snippet,contentDetails",
                "playlistId": uploads_playlist,
                "maxResults": 50,
                "pageToken": page_token or "",
            },
        )
        for item in result.get("items", []):
            published = datetime.fromisoformat(item["contentDetails"]["videoPublishedAt"].replace("Z", "+00:00"))
            if published < cutoff:
                return _hydrate_videos(video_ids)
            video_ids.append(item["contentDetails"]["videoId"])
        page_token = result.get("nextPageToken")
        if not page_token:
            break
    return _hydrate_videos(video_ids)


def _hydrate_videos(video_ids: list) -> list:
    videos = []
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i : i + 50]
        result = yt_get(
            "videos",
            {"part": "snippet,statistics,contentDetails", "id": ",".join(batch)},
        )
        for item in result.get("items", []):
            duration = item["contentDetails"]["duration"]
            if _is_short(duration):
                continue
            videos.append(
                {
                    "video_id": item["id"],
                    "title": item["snippet"]["title"],
                    "published_at": item["snippet"]["publishedAt"],
                    "views": int(item["statistics"].get("viewCount", 0)),
                }
            )
    return videos


def _is_short(iso_duration: str) -> bool:
    """Rough Shorts filter: anything 60 seconds or under, ISO 8601 duration like PT45S."""
    import re

    match = re.match(r"PT(?:(\d+)M)?(?:(\d+)S)?", iso_duration)
    if not match:
        return False
    minutes = int(match.group(1) or 0)
    seconds = int(match.group(2) or 0)
    total = minutes * 60 + seconds
    return total <= 60


def find_outliers(channel: dict, videos: list) -> list:
    if len(videos) < MIN_VIDEOS_FOR_BASELINE:
        return []
    baseline = statistics.median(v["views"] for v in videos)
    if baseline <= 0:
        return []
    outliers = []
    for v in videos:
        multiplier = v["views"] / baseline
        if multiplier >= OUTLIER_MULTIPLIER:
            published = datetime.fromisoformat(v["published_at"].replace("Z", "+00:00"))
            days_since = (datetime.now(timezone.utc) - published).days
            outliers.append(
                {
                    "video_title": v["title"],
                    "video_url": f"https://www.youtube.com/watch?v={v['video_id']}",
                    "channel_name": channel["snippet"]["title"],
                    "channel_url": f"https://www.youtube.com/channel/{channel['id']}",
                    "subscriber_count": int(channel["statistics"].get("subscriberCount", 0)),
                    "views": v["views"],
                    "channel_baseline_views": int(baseline),
                    "multiplier": round(multiplier, 1),
                    "published_at": v["published_at"][:10],
                    "days_since_posted": days_since,
                }
            )
    return outliers


def enrich_with_claude(outlier: dict) -> dict:
    """Ask Claude for the why-it-worked breakdown and a rewritten title/hook."""
    if not ANTHROPIC_API_KEY:
        outlier.update(
            {
                "trigger": "(set ANTHROPIC_API_KEY to auto-generate this)",
                "why_it_worked": "(set ANTHROPIC_API_KEY to auto-generate this)",
                "trend_or_evergreen": "(set ANTHROPIC_API_KEY to auto-generate this)",
                "rewritten_title": "(set ANTHROPIC_API_KEY to auto-generate this)",
                "rewritten_hook": "(set ANTHROPIC_API_KEY to auto-generate this)",
            }
        )
        return outlier

    prompt = f"""A YouTube video is outperforming its channel's normal views by {outlier['multiplier']}x.

Channel: {outlier['channel_name']} ({outlier['subscriber_count']} subscribers)
Video title: "{outlier['video_title']}"
Views: {outlier['views']} vs. channel baseline of {outlier['channel_baseline_views']}

This channel covers shoulder surgery recovery, rotator cuff rehab, or physical therapy. I run a YouTube channel in the same niche focused on rotator cuff recovery specifically.

Return only a JSON object with these keys, no other text:
- "trigger": the single psychological trigger the title uses (e.g. "fear of re-injury", "timeline anxiety", "money proof / hard evidence", "versus-battle", "curiosity gap")
- "why_it_worked": 2-3 sentences on why the title's promise pulled clicks
- "trend_or_evergreen": either "evergreen" or "trend" plus a short reason
- "rewritten_title": a rewritten title using the same angle, built for a rotator cuff recovery audience
- "rewritten_hook": one sentence describing how to open the video (first 3 seconds) using the same angle
"""

    resp = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": "claude-sonnet-4-6",
            "max_tokens": 500,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=60,
    )
    resp.raise_for_status()
    text = resp.json()["content"][0]["text"]
    text = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        parsed = json.loads(text)
        outlier.update(parsed)
    except json.JSONDecodeError:
        outlier.update(
            {
                "trigger": "(Claude response could not be parsed this run)",
                "why_it_worked": text[:400],
                "trend_or_evergreen": "",
                "rewritten_title": "",
                "rewritten_hook": "",
            }
        )
    return outlier


def main() -> None:
    if not YOUTUBE_API_KEY:
        print("YOUTUBE_API_KEY is not set. Add it as a repo secret.", file=sys.stderr)
        sys.exit(1)

    seen = load_seen()
    exclude_ids = recently_seen_ids(seen)

    channels = discover_channels(exclude_ids)
    if not channels:
        print("No candidate channels found this run.", file=sys.stderr)
        sys.exit(1)

    this_week = datetime.now(timezone.utc).date().isoformat()
    seen.setdefault("weeks", {})[this_week] = [c["id"] for c in channels]
    save_seen(seen)

    all_outliers = []
    for channel in channels:
        try:
            videos = get_recent_long_form_videos(channel)
            outliers = find_outliers(channel, videos)
            all_outliers.extend(outliers)
        except requests.HTTPError as exc:
            print(f"Skipping channel {channel['snippet']['title']}: {exc}", file=sys.stderr)
            continue

    for outlier in all_outliers:
        enrich_with_claude(outlier)

    all_outliers.sort(key=lambda o: o["multiplier"], reverse=True)

    now = datetime.now(timezone.utc)
    output = {
        "generated_at": now.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "next_run": (now + timedelta(days=1)).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "channels_scanned": len(channels),
        "outliers": all_outliers,
    }
    OUTLIERS_PATH.write_text(json.dumps(output, indent=2))
    print(f"Wrote {len(all_outliers)} outliers from {len(channels)} channels to {OUTLIERS_PATH}")


if __name__ == "__main__":
    main()
