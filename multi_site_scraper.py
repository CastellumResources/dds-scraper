import re
import json
import html
from datetime import datetime

import requests
import feedparser

# ---------- CONFIG ----------

REQUEST_TIMEOUT = 10
USER_AGENT = "Mozilla/5.0 (compatible; DDS-Scraper/1.0; +https://ddsnews.org)"
HEADERS = {"User-Agent": USER_AGENT, "Accept": "text/html,application/json"}

# ---------- HELPERS ----------

def clean_html(text: str) -> str:
    """Strip all tags/entities from WordPress/RSS excerpts and collapse whitespace."""
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)      # remove every HTML tag
    text = html.unescape(text)                # decode &amp; etc.
    return re.sub(r"\s+", " ", text).strip()  # collapse whitespace


def iso_now() -> str:
    return datetime.utcnow().isoformat()


def first_or_none(value):
    if isinstance(value, list):
        return value[0] if value else None
    return value or None


def get_og_image(url: str):
    """Fallback: fetch the article page and pull its og:image / twitter:image."""
    if not url:
        return None
    try:
        resp = requests.get(url, timeout=REQUEST_TIMEOUT, headers=HEADERS)
        if resp.status_code != 200:
            return None
        for pattern in (
            r'<meta[^>]+property=["\']og:image(?::secure_url)?["\'][^>]+content=["\']([^"\']+)["\']',
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
            r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)["\']',
        ):
            match = re.search(pattern, resp.text, re.IGNORECASE)
            if match:
                return match.group(1)
    except Exception as exc:
        print(f"[og:image] {url} -> {exc}")
    return None


# ---------- WATERFORD WHISPERS (WORDPRESS API) ----------

def wp_featured_image(post: dict):
    """Featured image from an _embed-ed WordPress post, with sensible fallbacks."""
    try:
        media = post.get("_embedded", {}).get("wp:featuredmedia", [])
        if media and media[0].get("source_url"):
            return media[0]["source_url"]
    except Exception:
        pass
    return post.get("jetpack_featured_media_url") or None


def fetch_wwn(limit=10):
    url = "https://waterfordwhispersnews.com/wp-json/wp/v2/posts"
    params = {"per_page": limit, "_embed": 1}  # _embed pulls the featured image inline
    resp = requests.get(url, params=params, timeout=REQUEST_TIMEOUT, headers=HEADERS)
    resp.raise_for_status()
    posts = resp.json()

    items = []
    for post in posts:
        headline = html.unescape(post["title"]["rendered"]).strip()
        excerpt = clean_html(post["excerpt"]["rendered"])
        link = post["link"]
        published = post.get("date_gmt") or post.get("date") or iso_now()
        image = wp_featured_image(post) or get_og_image(link)

        items.append({
            "source": "Waterford Whispers",
            "headline": headline,
            "excerpt": excerpt,
            "link": link,
            "published_at": published,
            "image": image,
        })
    return items


# ---------- GENERIC RSS -> JSON (THE ONION, DAILY MASH, ETC.) ----------

def rss_image(entry):
    """Image from an RSS entry: media tags, then enclosures, then first inline <img>."""
    # media:content / media:thumbnail
    for key in ("media_content", "media_thumbnail"):
        media = first_or_none(entry.get(key))
        if isinstance(media, dict) and media.get("url"):
            return media["url"]

    # <enclosure> image links
    for link in entry.get("links", []):
        if link.get("rel") == "enclosure" and str(link.get("type", "")).startswith("image"):
            if link.get("href"):
                return link["href"]

    # first <img> inside the content/summary HTML
    blob = ""
    content = first_or_none(entry.get("content"))
    if isinstance(content, dict):
        blob = content.get("value", "")
    blob = blob or entry.get("summary", "") or entry.get("description", "")
    match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', blob, re.IGNORECASE)
    if match:
        return match.group(1)
    return None


def fetch_rss(source_name, feed_url, limit=10):
    feed = feedparser.parse(feed_url)
    items = []

    for entry in feed.entries[:limit]:
        headline = entry.get("title", "").strip()
        link = entry.get("link", "")
        summary = entry.get("summary", "") or entry.get("description", "")
        excerpt = clean_html(summary)
        published = entry.get("published") or entry.get("updated") or iso_now()
        image = rss_image(entry) or get_og_image(link)

        items.append({
            "source": source_name,
            "headline": headline,
            "excerpt": excerpt,
            "link": link,
            "published_at": published,
            "image": image,
        })
    return items


# ---------- AGGREGATOR ----------

SOURCES = [
    {"name": "The Onion", "feed": "https://www.theonion.com/rss"},
    {"name": "The Daily Mash", "feed": "https://www.thedailymash.co.uk/feed"},
]


def fetch_all_sources():
    all_items = []

    # Waterford Whispers (WordPress API)
    try:
        all_items.extend(fetch_wwn(limit=10))
    except Exception as exc:
        print(f"[WWN] Error: {exc}")

    # RSS sources (The Onion, The Daily Mash, ...)
    for src in SOURCES:
        try:
            all_items.extend(fetch_rss(src["name"], src["feed"], limit=10))
        except Exception as exc:
            print(f"[{src['name']}] Error: {exc}")

    return all_items


# ---------- MAIN ----------

if __name__ == "__main__":
    items = fetch_all_sources()

    print(f"Total items fetched: {len(items)}\n")
    for i, item in enumerate(items, start=1):
        print(f"{i}. [{item['source']}] {item['headline']}")
        print(f"   Link:  {item['link']}")
        print(f"   Image: {item['image']}")
        print(f"   Excerpt: {item['excerpt'][:140]}...\n")

    with open("headlines.json", "w", encoding="utf-8") as f:
        json.dump(items, f, indent=2, ensure_ascii=False)

    print("headlines.json written.")
