# daily_news_slack.py
import os, time, hashlib, re, textwrap, datetime as dt
from urllib.parse import quote_plus
import feedparser, requests
from dotenv import load_dotenv

load_dotenv()

JST = dt.timezone(dt.timedelta(hours=9))
NOW = dt.datetime.now(JST)
SINCE = NOW - dt.timedelta(hours=24)

# =====================
# ティッカー設定
# =====================
TICKERS = {
    "WCC":  {"company": "Wesco International, Inc.", "aliases": ["Wesco International", "Wesco"]},
    "URI":  {"company": "United Rentals, Inc.", "aliases": ["United Rentals"]},
    "HRI":  {"company": "Herc Holdings Inc.", "aliases": ["Herc Rentals", "Herc Holdings"]},
    "ATKR": {"company": "Atkore Inc.", "aliases": ["Atkore"]},
    "SEE":  {"company": "Sealed Air Corporation", "aliases": ["Sealed Air", "Cryovac"]},
    "GPK":  {"company": "Graphic Packaging Holding Company", "aliases": ["Graphic Packaging", "GPK"]},
    "MTX":  {"company": "Minerals Technologies Inc.", "aliases": ["Minerals Technologies", "MTI"]},
}

# =====================
# RSS 収集
# =====================
def google_news_rss(query, lang="en", country="US"):
    base = "https://news.google.com/rss/search"
    q = quote_plus(query)
    url = f"{base}?q={q}&hl={lang}&gl={country}&ceid={country}:{lang}"
    return feedparser.parse(url)

def normalize_ts(entry):
    if hasattr(entry, "published_parsed") and entry.published_parsed:
        ts = dt.datetime.fromtimestamp(time.mktime(entry.published_parsed), dt.timezone.utc).astimezone(JST)
        return ts
    return NOW

def clean_text(s):
    return re.sub(r"\s+", " ", s or "").strip()

def score_article(e, ticker, name, aliases):
    title = (e.get("title") or "").lower()
    summary = (e.get("summary") or "").lower()
    keys = [ticker.lower(), name.lower()] + [a.lower() for a in aliases]
    return sum(1 for k in keys if k in title or k in summary)

def fetch_news_for_ticker(ticker, meta, max_items=4):
    name = meta["company"]
    aliases = meta.get("aliases", [])
    q = f'"{name}" OR {ticker}'
    feed = google_news_rss(q)
    items = []
    seen = set()
    for e in feed.entries:
        ts = normalize_ts(e)
        if ts < SINCE:
            continue
        url = e.get("link") or ""
        key = hashlib.md5((e.get("title","") + url).encode()).hexdigest()
        if key in seen:
            continue
        seen.add(key)
        s = score_article(e, ticker, name, aliases)
        items.append({
            "ticker": ticker,
            "company": name,
            "published": ts,
            "title": clean_text(e.get("title")),
            "summary": clean_text(e.get("summary")),
            "url": url,
            "score": s
        })
    items.sort(key=lambda x: (x["score"], x["published"]), reverse=True)
    return items[:max_items]

# =====================
# Slack 送信
# =====================
def post_to_slack(blocks):
    url = os.getenv("SLACK_WEBHOOK_URL")
    if not url:
        raise ValueError("SLACK_WEBHOOK_URL missing in .env")
    payload = {"blocks": blocks}
    requests.post(url, json=payload, timeout=10)

def make_slack_blocks(all_items):
    blocks = [
        {"type": "header", "text": {"type": "plain_text", "text": f"📊 Daily Corporate News — {NOW.strftime('%Y-%m-%d')} (JST)"}}
    ]
    for ticker, items in all_items.items():
        if not items:
            continue
        blocks.append({"type": "divider"})
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": f"*{ticker} — {items[0]['company']}*"}})
        for x in items:
            when = x["published"].strftime("%H:%M")
            summary = textwrap.shorten(x["summary"], width=140, placeholder="…")
            blocks.append({
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"• *{x['title']}* ({when})\n{summary}\n<{x['url']}|Read more>"}
            })
    return blocks

# =====================
# メイン処理
# =====================
def main():
    all_items = {}
    for t, meta in TICKERS.items():
        news = fetch_news_for_ticker(t, meta)
        all_items[t] = news
    blocks = make_slack_blocks(all_items)
    post_to_slack(blocks)
    print(f"✅ Posted {sum(len(v) for v in all_items.values())} articles.")

if __name__ == "__main__":
    main()
