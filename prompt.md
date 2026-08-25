You're my YouTube research analyst for the rotator cuff recovery channel. This is a daily job — save this routine and run it every morning at 6am without me asking.

THE JOB:
Scan 10-15 YouTube channels in the shoulder surgery recovery / physical therapy / orthopedic rehab space. Mix of sizes, but prioritize smaller channels (under 100k subs). New ones each week, don't just recycle the same list.

For each channel, pull their recent long-form videos (last 2 months) and view counts. Calculate the channel's baseline = median views. Flag any video doing 3x+ its channel's baseline. Ignore Shorts.

THE RULE THAT MATTERS:
A 10x outlier on a 5k-sub channel beats a 2x outlier on a 500k channel. Small channels have no built-in audience — if their video blew up, the IDEA and TITLE did the work. That's the signal I want.

FOR EACH OUTLIER YOU FIND:
- Why did it work? Break down the title's promise and the psychological trigger (fear of re-injury, timeline anxiety, "am I normal," pain relief proof, doctor-said-this-but-really versus-battle).
- Is it riding a passing trend, or is the angle evergreen and repeatable for rotator cuff recovery specifically?
- Give me a rewritten, complete title and hook using the same angle but built for the rotator cuff recovery audience, start to close.
- Metrics: channel size, video views, baseline, multiplier, days since posted.

OUTPUT:
Don't just reply in chat. Write the result to data/outliers.json, ranked biggest multiplier first, in this shape:

{
  "generated_at": ISO timestamp,
  "channels_scanned": number,
  "outliers": [
    {
      "video_title", "video_url", "channel_name", "channel_url",
      "subscriber_count", "views", "channel_baseline_views", "multiplier",
      "published_at", "days_since_posted",
      "trigger", "why_it_worked", "trend_or_evergreen",
      "rewritten_title", "rewritten_hook"
    }
  ]
}

This feeds a dashboard (index.html) that reads data/outliers.json directly, so every morning's run replaces yesterday's report automatically — no manual copy/paste, no me asking. The dashboard, the scan script, and the daily 6am scheduler that runs this whole loop live in this same repo. See README.md for the one-time setup.
