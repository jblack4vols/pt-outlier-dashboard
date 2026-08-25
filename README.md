# Rotator Cuff Channel — Daily Outlier Dashboard

Every morning at 6am ET, this scans 10-15 YouTube channels in the shoulder
surgery recovery / PT rehab space, finds videos outperforming their own
channel's baseline by 3x or more, and publishes the ranked results to a
dashboard. No manual trigger needed once it's set up.

## What runs where

- `scripts/scan_channels.py` — does the actual work: discovers channels,
  pulls video stats, computes baselines, flags outliers, asks Claude for
  the title/hook breakdown, writes `data/outliers.json`.
- `.github/workflows/daily-scan.yml` — the cron job. Runs the script every
  morning, commits the updated data, and publishes the dashboard to GitHub
  Pages.
- `index.html` — the dashboard itself. Reads `data/outliers.json` and
  renders it. No build step, no framework.

## One-time setup (about 10 minutes)

1. **Create a new GitHub repo** and push this folder to it (e.g.
   `pt-outlier-dashboard`, public or private — Pages works either way on a
   paid plan, public repos get Pages free).

2. **Get a YouTube Data API key.**
   - Go to console.cloud.google.com, create a project (or use an existing
     one), enable "YouTube Data API v3," then create an API key under
     Credentials.
   - Free tier is 10,000 units/day. This scan uses roughly 100-150 units
     per channel scanned, so a 12-channel run costs well under the daily
     quota.

3. **Get a Claude API key** from console.anthropic.com if you don't
   already have one for another project.

4. **Add both keys as repo secrets.**
   In the repo: Settings → Secrets and variables → Actions → New repository
   secret.
   - `YOUTUBE_API_KEY`
   - `ANTHROPIC_API_KEY`

5. **Turn on GitHub Pages.**
   Settings → Pages → Source → set to "GitHub Actions."

6. **Run it once manually** to confirm it works before waiting for 6am:
   Actions tab → "Daily rotator cuff outlier scan" → Run workflow.

That's it. From here it runs itself every morning and the dashboard updates
in place at `https://<your-username>.github.io/<repo-name>/`.

## Adjusting the scan

- **Channel discovery queries** — edit `SEARCH_QUERIES` in
  `scripts/scan_channels.py` if you want to steer toward a narrower or
  broader slice of the niche.
- **Outlier threshold** — `OUTLIER_MULTIPLIER` in the same file (default 3.0).
- **Subscriber priority cutoff** — `MAX_SUBS_PRIORITY` (default 100,000).
- **Lookback window** — `LOOKBACK_DAYS` (default 60).

## Costs

- GitHub Actions: free tier covers this easily (one ~2-minute run per day).
- GitHub Pages: free for public repos.
- YouTube Data API: free tier, well under quota at this scan size.
- Claude API: a few cents per day — only the flagged outliers get sent for
  the breakdown, not every video scanned.

## If a morning run comes up empty

Some mornings won't clear a 3x outlier across the whole batch — that's
expected, not a bug. The dashboard will say so instead of showing stale
data.
