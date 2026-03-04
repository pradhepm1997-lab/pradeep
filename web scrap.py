"""
SEO Web Scraper
===============
Scrapes a website URL and extracts key SEO data including:
- Title tag, meta description, meta keywords
- Heading tags (H1–H6)
- Canonical URL
- Open Graph / Twitter Card tags
- Image alt attributes
- Internal vs external links
- Page word count
- Robots meta tag
- Schema.org structured data (JSON-LD)
- Page load time
- HTTP status code

Usage:
    python seo_scraper.py <url> [--output report.json] [--crawl <depth>]

Requirements:
    pip install requests beautifulsoup4 lxml colorama
"""

import sys
import json
import time
import argparse
from urllib.parse import urljoin, urlparse
from collections import defaultdict

try:
    import requests
    from bs4 import BeautifulSoup
    from colorama import Fore, Style, init as colorama_init
    colorama_init(autoreset=True)
except ImportError:
    print("Missing dependencies. Run:\n  pip install requests beautifulsoup4 lxml colorama")
    sys.exit(1)


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; SEOScraper/1.0; "
        "+https://github.com/seo-scraper)"
    )
}


# ─────────────────────────────────────────────
# Core scraping logic
# ─────────────────────────────────────────────

def fetch_page(url: str, timeout: int = 15) -> dict:
    """Fetch a URL and return response metadata."""
    start = time.time()
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
        elapsed = round(time.time() - start, 3)
        return {
            "url": resp.url,
            "status_code": resp.status_code,
            "load_time_seconds": elapsed,
            "content_type": resp.headers.get("Content-Type", ""),
            "html": resp.text,
            "error": None,
        }
    except requests.RequestException as e:
        return {"url": url, "status_code": None, "load_time_seconds": None,
                "content_type": None, "html": None, "error": str(e)}


def parse_seo(url: str, html: str) -> dict:
    """Extract all SEO signals from raw HTML."""
    soup = BeautifulSoup(html, "lxml")
    base_domain = urlparse(url).netloc

    # ── Title ──
    title_tag = soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else None

    # ── Meta tags ──
    def get_meta(name=None, prop=None):
        if name:
            tag = soup.find("meta", attrs={"name": name})
        else:
            tag = soup.find("meta", attrs={"property": prop})
        return tag["content"].strip() if tag and tag.get("content") else None

    meta_description = get_meta(name="description")
    meta_keywords    = get_meta(name="keywords")
    robots_meta      = get_meta(name="robots")
    viewport         = get_meta(name="viewport")

    # ── Canonical ──
    canonical_tag = soup.find("link", rel="canonical")
    canonical = canonical_tag["href"] if canonical_tag and canonical_tag.get("href") else None

    # ── Open Graph ──
    og = {
        "og:title":       get_meta(prop="og:title"),
        "og:description": get_meta(prop="og:description"),
        "og:image":       get_meta(prop="og:image"),
        "og:url":         get_meta(prop="og:url"),
        "og:type":        get_meta(prop="og:type"),
    }

    # ── Twitter Card ──
    twitter = {
        "twitter:card":        get_meta(name="twitter:card"),
        "twitter:title":       get_meta(name="twitter:title"),
        "twitter:description": get_meta(name="twitter:description"),
        "twitter:image":       get_meta(name="twitter:image"),
    }

    # ── Headings ──
    headings = defaultdict(list)
    for level in range(1, 7):
        for tag in soup.find_all(f"h{level}"):
            text = tag.get_text(strip=True)
            if text:
                headings[f"h{level}"].append(text)

    # ── Images ──
    images = []
    for img in soup.find_all("img"):
        images.append({
            "src": img.get("src", ""),
            "alt": img.get("alt", ""),
            "missing_alt": not bool(img.get("alt", "").strip()),
        })
    missing_alt_count = sum(1 for i in images if i["missing_alt"])

    # ── Links ──
    internal_links = []
    external_links = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith("#") or href.startswith("mailto:") or href.startswith("tel:"):
            continue
        absolute = urljoin(url, href)
        parsed = urlparse(absolute)
        link_info = {
            "href": absolute,
            "text": a.get_text(strip=True),
            "nofollow": "nofollow" in (a.get("rel") or []),
        }
        if parsed.netloc == base_domain:
            internal_links.append(link_info)
        else:
            external_links.append(link_info)

    # ── Word count (body text) ──
    body = soup.find("body")
    body_text = body.get_text(separator=" ") if body else ""
    word_count = len(body_text.split())

    # ── JSON-LD structured data ──
    schema_items = []
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
            schema_items.append(data)
        except (json.JSONDecodeError, TypeError):
            pass

    # ── hreflang ──
    hreflang = []
    for link in soup.find_all("link", rel="alternate"):
        if link.get("hreflang"):
            hreflang.append({"lang": link["hreflang"], "href": link.get("href", "")})

    return {
        "title": title,
        "title_length": len(title) if title else 0,
        "meta_description": meta_description,
        "meta_description_length": len(meta_description) if meta_description else 0,
        "meta_keywords": meta_keywords,
        "robots_meta": robots_meta,
        "viewport": viewport,
        "canonical": canonical,
        "open_graph": og,
        "twitter_card": twitter,
        "headings": dict(headings),
        "h1_count": len(headings.get("h1", [])),
        "images": {
            "total": len(images),
            "missing_alt_count": missing_alt_count,
            "details": images[:50],  # cap at 50 for readability
        },
        "links": {
            "internal_count": len(internal_links),
            "external_count": len(external_links),
            "internal": internal_links[:50],
            "external": external_links[:30],
        },
        "word_count": word_count,
        "schema_org": schema_items,
        "hreflang": hreflang,
    }


def build_report(url: str) -> dict:
    """Full SEO report for a single URL."""
    print(f"{Fore.CYAN}Fetching: {url}")
    result = fetch_page(url)

    if result["error"]:
        return {"url": url, "error": result["error"]}

    print(f"{Fore.GREEN}  ✓ {result['status_code']} — {result['load_time_seconds']}s")
    seo = parse_seo(result["url"], result["html"])

    return {
        "url": result["url"],
        "status_code": result["status_code"],
        "load_time_seconds": result["load_time_seconds"],
        "content_type": result["content_type"],
        **seo,
        "issues": detect_issues(seo, result),
    }


# ─────────────────────────────────────────────
# Issue detection
# ─────────────────────────────────────────────

def detect_issues(seo: dict, fetch: dict) -> list:
    issues = []

    def warn(msg): issues.append({"severity": "warning", "message": msg})
    def error(msg): issues.append({"severity": "error",   "message": msg})
    def info(msg):  issues.append({"severity": "info",    "message": msg})

    # Title
    if not seo["title"]:
        error("Missing <title> tag")
    elif seo["title_length"] < 30:
        warn(f"Title is too short ({seo['title_length']} chars). Aim for 50–60.")
    elif seo["title_length"] > 60:
        warn(f"Title is too long ({seo['title_length']} chars). Keep under 60.")

    # Meta description
    if not seo["meta_description"]:
        error("Missing meta description")
    elif seo["meta_description_length"] < 70:
        warn(f"Meta description too short ({seo['meta_description_length']} chars). Aim for 120–160.")
    elif seo["meta_description_length"] > 160:
        warn(f"Meta description too long ({seo['meta_description_length']} chars). Keep under 160.")

    # H1
    if seo["h1_count"] == 0:
        error("No H1 heading found on page")
    elif seo["h1_count"] > 1:
        warn(f"Multiple H1 tags ({seo['h1_count']}). Use only one H1 per page.")

    # Canonical
    if not seo["canonical"]:
        warn("No canonical URL set")

    # Images
    if seo["images"]["missing_alt_count"] > 0:
        warn(f"{seo['images']['missing_alt_count']} image(s) missing alt text")

    # Open Graph
    if not seo["open_graph"]["og:title"]:
        info("Missing og:title (recommended for social sharing)")
    if not seo["open_graph"]["og:description"]:
        info("Missing og:description")
    if not seo["open_graph"]["og:image"]:
        info("Missing og:image")

    # Load time
    if fetch.get("load_time_seconds") and fetch["load_time_seconds"] > 3:
        warn(f"Slow page load: {fetch['load_time_seconds']}s (target < 2s)")

    # Robots
    robots = (seo["robots_meta"] or "").lower()
    if "noindex" in robots:
        error("Page is set to noindex — will not appear in search results")
    if "nofollow" in robots:
        warn("Page is set to nofollow — links won't be crawled")

    # Schema
    if not seo["schema_org"]:
        info("No JSON-LD structured data found")

    # Word count
    if seo["word_count"] < 300:
        warn(f"Low word count ({seo['word_count']} words). Thin content may rank poorly.")

    return issues


# ─────────────────────────────────────────────
# Multi-page crawl
# ─────────────────────────────────────────────

def crawl(start_url: str, max_depth: int = 1) -> list:
    """BFS crawl of internal links up to max_depth."""
    visited = set()
    queue = [(start_url, 0)]
    reports = []
    base_domain = urlparse(start_url).netloc

    while queue:
        url, depth = queue.pop(0)
        if url in visited:
            continue
        visited.add(url)

        report = build_report(url)
        reports.append(report)

        if depth < max_depth and "links" in report:
            for link in report["links"].get("internal", []):
                href = link["href"]
                if href not in visited and urlparse(href).netloc == base_domain:
                    queue.append((href, depth + 1))

    return reports


# ─────────────────────────────────────────────
# Pretty print summary
# ─────────────────────────────────────────────

def print_summary(report: dict):
    sep = "─" * 60
    print(f"\n{Fore.YELLOW}{sep}")
    print(f"{Fore.YELLOW}  SEO REPORT: {report['url']}")
    print(f"{Fore.YELLOW}{sep}")

    def row(label, value, color=Fore.WHITE):
        print(f"  {Fore.CYAN}{label:<28}{color}{value}")

    row("Status Code",     report.get("status_code", "N/A"))
    row("Load Time",       f"{report.get('load_time_seconds', 'N/A')}s")
    row("Title",           report.get("title") or "⚠ MISSING", Fore.RED if not report.get("title") else Fore.WHITE)
    row("Title Length",    f"{report.get('title_length', 0)} chars")
    row("Meta Description",report.get("meta_description") or "⚠ MISSING", Fore.RED if not report.get("meta_description") else Fore.WHITE)
    row("Meta Desc Length",f"{report.get('meta_description_length', 0)} chars")
    row("Canonical",       report.get("canonical") or "⚠ Not set", Fore.YELLOW if not report.get("canonical") else Fore.WHITE)
    row("H1 Tags",         report.get("h1_count", 0))
    row("Word Count",      report.get("word_count", 0))
    row("Images (total)",  report.get("images", {}).get("total", 0))
    row("Images (no alt)", report.get("images", {}).get("missing_alt_count", 0))
    row("Internal Links",  report.get("links", {}).get("internal_count", 0))
    row("External Links",  report.get("links", {}).get("external_count", 0))
    row("Schema.org items",len(report.get("schema_org", [])))
    row("Robots Meta",     report.get("robots_meta") or "not set")

    issues = report.get("issues", [])
    if issues:
        print(f"\n{Fore.YELLOW}  Issues ({len(issues)}):")
        for issue in issues:
            sev = issue["severity"]
            color = Fore.RED if sev == "error" else Fore.YELLOW if sev == "warning" else Fore.BLUE
            icon  = "✖" if sev == "error" else "⚠" if sev == "warning" else "ℹ"
            print(f"    {color}{icon} [{sev.upper()}] {issue['message']}")

    print(f"{Fore.YELLOW}{sep}\n")


# ─────────────────────────────────────────────
# CLI entry point
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="SEO Web Scraper — extract SEO signals from any URL"
    )
    parser.add_argument("url", help="Target URL to scrape (include https://)")
    parser.add_argument(
        "--output", "-o", default=None,
        help="Save full JSON report to this file (e.g. report.json)"
    )
    parser.add_argument(
        "--crawl", "-c", type=int, default=0, metavar="DEPTH",
        help="Crawl internal links up to DEPTH levels (0 = single page)"
    )
    args = parser.parse_args()

    url = args.url
    if not url.startswith("http"):
        url = "https://" + url

    if args.crawl > 0:
        print(f"{Fore.CYAN}Crawling up to depth {args.crawl}...")
        reports = crawl(url, max_depth=args.crawl)
    else:
        reports = [build_report(url)]

    for report in reports:
        print_summary(report)

    if args.output:
        output_path = args.output
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(reports if len(reports) > 1 else reports[0], f, indent=2, ensure_ascii=False)
        print(f"{Fore.GREEN}✓ Report saved to: {output_path}")
    else:
        # Always print JSON to stdout for single page if no output file
        if len(reports) == 1:
            print(json.dumps(reports[0], indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()