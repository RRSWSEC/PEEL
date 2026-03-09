#!/usr/bin/env python3
"""
PEEL — Parse, Enumerate, Enrich, Log

Give PEEL a database, any file, a URL, or a single .onion address.
It finds every valid onion, checks if it's alive through Tor, scrapes
all text metadata, and writes a fully enriched CSV — one row per onion.

Usage:
  ./peel.py onions.db                        # pull alive from SQLite DB
  ./peel.py targets.txt                      # parse onions from any file
  ./peel.py dump.csv                         # csv, html, json — anything works
  ./peel.py https://dark.fail                # fetch URL through Tor, parse onions
  ./peel.py abc123...xyz.onion               # single address
  ./peel.py targets.txt --out results.csv    # custom output path
  ./peel.py onions.db --workers 30           # more parallel workers
  ./peel.py targets.txt --timeout 20         # shorter timeout per request
  ./peel.py targets.txt --no-scrape          # alive check only, skip HTML

Output:
  enriched_<source>_<timestamp>.csv
  Columns: address, alive, status_code, response_time_s, title,
           h1, h2, h3, meta_description, meta_keywords,
           server, content_type, redirect_url, scraped_at, error
"""

import argparse
import csv
import queue
import re
import sqlite3
import sys
import threading
import time
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

try:
    import requests
except ImportError:
    sys.exit("Missing: pip install requests PySocks --break-system-packages")

# ── Constants ─────────────────────────────────────────────────────────────────

VERSION    = "2.0.0"
TOR_PROXY  = "socks5h://127.0.0.1:9050"
PROXIES    = {"http": TOR_PROXY, "https": TOR_PROXY}
MAX_BYTES  = 512 * 1024
USER_AGENT = "Mozilla/5.0 (compatible; PEEL/2.0)"

# v2 = 16 chars, v3 = 56 chars, base32 alphabet (a-z, 2-7)
# Negative lookbehind prevents partial match of longer strings
_ONION_RE = re.compile(
    r'(?<![a-z2-7])([a-z2-7]{56}|[a-z2-7]{16})\.onion',
    re.IGNORECASE
)

CSV_FIELDS = [
    "address", "alive", "status_code", "response_time_s",
    "title", "h1", "h2", "h3",
    "meta_description", "meta_keywords",
    "server", "content_type", "redirect_url",
    "scraped_at", "error",
]

# ── Banner ────────────────────────────────────────────────────────────────────

BANNER = """
\033[32m
  ██████╗ ███████╗███████╗██╗
  ██╔══██╗██╔════╝██╔════╝██║
  ██████╔╝█████╗  █████╗  ██║
  ██╔═══╝ ██╔══╝  ██╔══╝  ██║
  ██║     ███████╗███████╗███████╗
  ╚═╝     ╚══════╝╚══════╝╚══════╝
\033[0m\033[90m  Parse · Enumerate · Enrich · Log\033[0m
"""

# ── Onion parser ──────────────────────────────────────────────────────────────

def parse_onions(text: str) -> list:
    """
    Extract all valid v2/v3 onion addresses from any blob of text.
    Handles: bare addresses, http:// prefixes, comma/space/newline separated,
    end-to-end with no delimiter, mixed with total garbage.
    Returns sorted, deduplicated list.
    """
    found = set()
    for m in _ONION_RE.finditer(text.lower()):
        found.add(m.group(0))
    return sorted(found)

# ── HTML scraper ──────────────────────────────────────────────────────────────

class _HTMLScraper(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title     = ""
        self.h1s       = []
        self.h2s       = []
        self.h3s       = []
        self.meta_desc = ""
        self.meta_kw   = ""
        self._tag      = None
        self._buf      = []

    def handle_starttag(self, tag, attrs):
        self._tag = tag.lower()
        self._buf = []
        if self._tag == "meta":
            d    = {k.lower(): v or "" for k, v in attrs}
            name = d.get("name", "").lower()
            if name == "description":
                self.meta_desc = d.get("content", "")[:500]
            elif name == "keywords":
                self.meta_kw = d.get("content", "")[:300]

    def handle_endtag(self, tag):
        t    = tag.lower()
        text = re.sub(r'\s+', ' ', " ".join(self._buf)).strip()
        if   t == "title" and not self.title: self.title = text[:300]
        elif t == "h1"    and text:           self.h1s.append(text[:200])
        elif t == "h2"    and text:           self.h2s.append(text[:200])
        elif t == "h3"    and text:           self.h3s.append(text[:200])
        self._tag = None
        self._buf = []

    def handle_data(self, data):
        if self._tag in ("title", "h1", "h2", "h3"):
            self._buf.append(data.strip())


def _scrape_html(html: str) -> dict:
    p = _HTMLScraper()
    try:
        p.feed(html)
    except Exception:
        pass
    return {
        "title":            p.title,
        "h1":               " | ".join(p.h1s[:3]),
        "h2":               " | ".join(p.h2s[:5]),
        "h3":               " | ".join(p.h3s[:5]),
        "meta_description": p.meta_desc,
        "meta_keywords":    p.meta_kw,
    }

# ── Fetcher ───────────────────────────────────────────────────────────────────

def _fetch(address: str, timeout: int, do_scrape: bool) -> dict:
    row = {f: "" for f in CSV_FIELDS}
    row["address"]    = address
    row["scraped_at"] = datetime.now(timezone.utc).isoformat()

    try:
        t0   = time.time()
        resp = requests.get(
            f"http://{address}",
            proxies=PROXIES,
            timeout=timeout,
            headers={"User-Agent": USER_AGENT},
            stream=True,
            allow_redirects=True,
        )
        elapsed = round(time.time() - t0, 2)

        row["alive"]           = "yes"
        row["status_code"]     = str(resp.status_code)
        row["response_time_s"] = str(elapsed)
        row["server"]          = resp.headers.get("Server", "")
        row["content_type"]    = resp.headers.get("Content-Type", "")

        if resp.url != f"http://{address}":
            row["redirect_url"] = resp.url

        if do_scrape and ("html" in row["content_type"].lower() or
                          row["content_type"] == ""):
            raw = b""
            for chunk in resp.iter_content(chunk_size=8192):
                raw += chunk
                if len(raw) >= MAX_BYTES:
                    break
            enc = resp.encoding or "utf-8"
            row.update(_scrape_html(raw.decode(enc, errors="replace")))

    except requests.exceptions.ConnectionError:
        row["alive"] = "no"
        row["error"] = "connection_refused"
    except requests.exceptions.Timeout:
        row["alive"] = "no"
        row["error"] = "timeout"
    except Exception as e:
        row["alive"] = "no"
        row["error"] = str(e)[:150]

    return row

# ── Worker pool ───────────────────────────────────────────────────────────────

def _worker(jq, rq, timeout, do_scrape):
    while True:
        item = jq.get()
        if item is None:
            break
        rq.put(_fetch(item, timeout, do_scrape))
        jq.task_done()

# ── Input loader ──────────────────────────────────────────────────────────────

def _load_db(db_path: Path) -> list:
    """Pull alive/auth_required addresses from a TCR SQLite database."""
    conn = sqlite3.connect(str(db_path))
    # Support both old schema (seen_at) and new schema (last_checked)
    try:
        rows = conn.execute(
            "SELECT address FROM onions "
            "WHERE status IN ('alive','auth_required') "
            "ORDER BY seen_at DESC"
        ).fetchall()
    except sqlite3.OperationalError:
        rows = conn.execute(
            "SELECT address FROM onions "
            "WHERE status IN ('alive','auth_required')"
        ).fetchall()
    conn.close()
    return [r[0] for r in rows]


def load_targets(source: str) -> tuple:
    """
    Returns (addresses: list, label: str).

    Accepts:
      - SQLite .db file    → reads alive rows from onions table
      - Any other file     → reads as text, parses out all onion addresses
      - URL                → fetches through Tor, parses onion addresses
      - Single .onion      → used directly
    """
    # Single onion address passed directly
    if _ONION_RE.fullmatch(source.lower().strip()):
        addr = source.lower().strip()
        if not addr.endswith(".onion"):
            addr += ".onion"
        return [addr], addr.split(".")[0][:16]

    # URL
    if source.startswith("http://") or source.startswith("https://"):
        print("  \033[90mFetching source URL through Tor...\033[0m")
        try:
            resp = requests.get(
                source, proxies=PROXIES, timeout=30,
                headers={"User-Agent": USER_AGENT}
            )
            text = resp.text
        except Exception as e:
            sys.exit(f"\033[31m  Failed to fetch URL: {e}\033[0m")
        label = re.sub(r'[^\w]', '_', source.split("//")[-1])[:40]
        return parse_onions(text), label

    path = Path(source)
    if not path.exists():
        sys.exit(f"\033[31m  Not found: {source}\033[0m")

    # SQLite DB — pull alive addresses directly
    if path.suffix == ".db":
        try:
            addrs = _load_db(path)
            if addrs:
                print(f"  \033[90mDatabase mode — {len(addrs)} alive/auth addresses loaded\033[0m")
                return addrs, path.stem
        except Exception:
            pass
        # Fall through: not a valid onions DB, parse as text

    # Everything else — read as text, parse onion addresses
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        sys.exit(f"\033[31m  Could not read file: {e}\033[0m")

    addrs = parse_onions(text)
    return addrs, path.stem

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(
        description="PEEL — Parse, Enumerate, Enrich, Log .onion addresses",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    ap.add_argument("source",
        help="SQLite .db, any file, URL, or single .onion address")
    ap.add_argument("--out",       type=Path, default=None,
        help="Output CSV path (default: enriched_<source>_<timestamp>.csv)")
    ap.add_argument("--workers",   type=int,  default=20,
        help="Parallel workers (default: 20)")
    ap.add_argument("--timeout",   type=int,  default=30,
        help="Per-request timeout seconds (default: 30)")
    ap.add_argument("--no-scrape", action="store_true",
        help="Alive check only — skip HTML scraping")
    ap.add_argument("--version",   action="version", version=f"PEEL {VERSION}")
    args = ap.parse_args()

    print(BANNER)

    addresses, label = load_targets(args.source)
    total = len(addresses)

    if not total:
        sys.exit("\033[31m  No valid .onion addresses found in source.\033[0m")

    stamp    = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = args.out or Path(f"enriched_{label}_{stamp}.csv")

    print(f"  \033[1mSource\033[0m   {args.source}")
    print(f"  \033[1mFound\033[0m    {total} unique addresses")
    print(f"  \033[1mWorkers\033[0m  {args.workers}")
    print(f"  \033[1mTimeout\033[0m  {args.timeout}s")
    print(f"  \033[1mScrape\033[0m   {'no — alive check only' if args.no_scrape else 'yes'}")
    print(f"  \033[1mOutput\033[0m   {out_path}")
    print(f"\033[90m  {'─' * 48}\033[0m\n")

    jq = queue.Queue()
    rq = queue.Queue()

    for addr in addresses:
        jq.put(addr)
    for _ in range(args.workers):
        jq.put(None)

    for _ in range(args.workers):
        threading.Thread(
            target=_worker,
            args=(jq, rq, args.timeout, not args.no_scrape),
            daemon=True
        ).start()

    done = alive = errors = 0
    t0 = time.time()

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        w.writeheader()

        while done < total:
            try:
                row = rq.get(timeout=args.timeout + 15)
            except queue.Empty:
                break
            w.writerow(row)
            f.flush()
            done += 1
            if row.get("alive") == "yes":
                alive += 1
            if row.get("error"):
                errors += 1
            elapsed = time.time() - t0
            rate    = done / elapsed if elapsed else 0
            eta     = int((total - done) / rate) if rate else 0
            mark    = "\033[32m+\033[0m" if row.get("alive") == "yes" else "\033[90m.\033[0m"
            print(
                f"  [{mark}] {done}/{total}  "
                f"\033[32malive={alive}\033[0m  "
                f"\033[31merr={errors}\033[0m  "
                f"{rate:.1f}/s  eta={eta}s  "
                f"\033[90m{row['address'][:48]}\033[0m",
                end="\r"
            )

    elapsed = time.time() - t0
    dead    = done - alive - errors

    print(f"\n\n\033[90m  {'─' * 48}\033[0m")
    print(f"  \033[1mDone\033[0m     {elapsed:.0f}s")
    print(f"  \033[32mAlive\033[0m    {alive}")
    print(f"  \033[90mDead\033[0m     {dead}")
    print(f"  \033[31mErrors\033[0m   {errors}")
    print(f"  \033[1mTotal\033[0m    {done}")
    print(f"  \033[1mSaved\033[0m    {out_path.resolve()}")
    print()


if __name__ == "__main__":
    main()
