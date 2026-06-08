import requests
import feedparser
from datetime import datetime
import html
import json

# ---------- HELPERS ----------

def clean_html(text: str) -> str:
    if not text:
        return ""
    # Remove basic HTML tags from WP excerpts
    return html.unescape(
        text.replace("<p>", "")
            .replace("</p>", "")
            .replace("<br>", " ")
            .replace("<br/>", " ")
            .replace("<br />", " ")
            .strip()
    )

def iso_now():
    return datetime.utcnow().isoformat()

# ---------- WATERFORD WHISPERS (WORDPRESS API) ----------

def fetch_wwn(limit=10):
    url = "https://waterfordwhispersnews.com/wp-json/wp/v2/posts"
    params = {"per_page": limit}
    resp = requests.get(url, params=params, timeout=10)
    resp.raise_for_status()
    posts = resp.json()

    items = []
    for post in posts:
        headline = html.unescape(post["title"]["rendered"]).strip()
        excerpt = clean_html(post["excerpt"]["rendered"])
        link = post["link"]
        published = post.get("date_gmt") or post.get("date") or iso_now()

        items.append({
            "source": "Waterford Whispers",
            "headline": headline,
            "excerpt": excerpt,
            "link": link,
            "published_at": published,
        })
    return items

# ---------- GENERIC RSS → JSON (THE ONION, DAILY MASH, ETC.) ----------

def fetch_rss(source_name, feed_url, limit=10):
    feed = feedparser.parse(feed_url)
    items = []

    for entry in feed.entries[:limit]:
        headline = entry.get("title", "").strip()
        link = entry.get("link", "")
        summary = entry.get("summary", "") or entry.get("description", "")
        excerpt = clean_html(summary)

        # Try to get a published date
        published = None
        if "published" in entry:
            published = entry.published
        elif "updated" in entry:
            published = entry.updated
        else:
            published = iso_now()

        items.append({
            "source": source_name,
            "headline": headline,
            "excerpt": excerpt,
            "link": link,
            "published_at": published,
        })

    return items

# ---------- AGGREGATOR ----------

def fetch_all_sources():
    all_items = []

    # Waterford Whispers (WordPress API)
    try:
        all_items.extend(fetch_wwn(limit=10))
    except Exception as e:
        print(f"[WWN] Error: {e}")

    # The Onion (RSS)
    try:
        all_items.extend(
            fetch_rss(
                source_name="The Onion",
                feed_url="https://www.theonion.com/rss",
                limit=10,
            )
        )
    except Exception as e:
        print(f"[The Onion] Error: {e}")

    # The Daily Mash (RSS)
    try:
        all_items.extend(
            fetch_rss(
                source_name="The Daily Mash",
                feed_url="https://www.thedailymash.co.uk/feed",
                limit=10,
            )
        )
    except Exception as e:
        print(f"[The Daily Mash] Error: {e}")

    return all_items

# ---------- MAIN ----------

if __name__ == "__main__":
    items = fetch_all_sources()

    print(f"Total items fetched: {len(items)}\n")

    for i, item in enumerate(items, start=1):
        print(f"{i}. [{item['source']}] {item['headline']}")
        print(f"   Link: {item['link']}")
        print(f"   Excerpt: {item['excerpt'][:140]}...")
        print(f"   Published: {item['published_at']}\n")

    # Optional: write to JSON feed file
    with open("headlines.json", "w", encoding="utf-8") as f:
        json.dump(items, f, indent=2, ensure_ascii=False)

    print("headlines.json written.")
    
import traceback

try:
    items = fetch_all_sources()
    with open("headlines.json", "w", encoding="utf-8") as f:
        json.dump(items, f, indent=2, ensure_ascii=False)
except Exception as e:
    with open("headlines.json", "w", encoding="utf-8") as f:
        f.write(str(e) + "\n")
        f.write(traceback.format_exc() + "\n")
    
