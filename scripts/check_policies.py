#!/usr/bin/env python3
"""Fetch every source URL in data/vendors.json, reduce each page to its main
text, store a snapshot, and write a diff report to changes/YYYY-MM-DD.md when
a page's text has changed since the last snapshot.

Usage:
  python3 scripts/check_policies.py            # check all sources
  python3 scripts/check_policies.py --only cursor.com   # URLs containing a substring
  python3 scripts/check_policies.py --dry-run  # don't write snapshots/report

Exit code is 0 even when changes are found (so CI doesn't go red); the report
file is the signal. Use --fail-on-change to exit 1 instead.

Pages that come back as an empty JavaScript shell (HTTP 200 but almost no text)
are fetched a second time in headless Chromium, if Playwright is installed
(pip install playwright && python -m playwright install --with-deps chromium).
The index records "method": "rendered" for those pages. Without Playwright, or
if the rendered page is still empty, the page is reported as a fetch error,
exactly as before. Use --no-render to skip the browser step.
"""
import argparse, datetime, difflib, hashlib, json, re, sys, time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "vendors.json"
SNAP = ROOT / "snapshots"
CHANGES = ROOT / "changes"
CONFIG = ROOT / "scripts" / "checker_config.json"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/126 Safari/537.36")
DROP_TAGS = ["script", "style", "noscript", "svg", "nav", "footer", "header",
             "form", "iframe", "button", "template"]


def load_config():
    if CONFIG.exists():
        return json.loads(CONFIG.read_text())
    return {"ignore_patterns": [], "extra_urls": []}


def source_urls():
    data = json.loads(DATA.read_text())
    urls = {}
    for v in data["vendors"]:
        for field in v["fields"].values():
            u = field.get("source")
            if u:
                urls.setdefault(u, set()).add(v["slug"])
    for u in load_config().get("extra_urls", []):
        urls.setdefault(u, set())
    return {u: sorted(s) for u, s in sorted(urls.items())}


def url_key(url):
    base = re.sub(r"[^a-z0-9]+", "_", url.lower().split("://", 1)[-1]).strip("_")[:80]
    return f"{base}_{hashlib.sha1(url.encode()).hexdigest()[:8]}"


def _extract(html, drop, prefer_main):
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(drop):
        tag.decompose()
    node = (soup.find("main") or soup.find("article")) if prefer_main else None
    node = node or soup.body or soup
    lines = (re.sub(r"\s+", " ", ln).strip() for ln in node.get_text("\n").split("\n"))
    return "\n".join(ln for ln in lines if ln)


def main_text(html):
    """Main content only. If that comes out nearly empty (some sites wrap the
    whole page in <header>/<form>, or render into odd containers), fall back to
    the whole body minus scripts and styles."""
    text = _extract(html, DROP_TAGS, True)
    if len(text) < 500:
        fallback = _extract(html, ["script", "style", "noscript", "svg", "template"], False)
        if len(fallback) > len(text):
            text = fallback
    return text


def normalise(text, patterns):
    out = []
    for ln in text.split("\n"):
        for p in patterns:
            ln = re.sub(p, "", ln)
        ln = ln.strip()
        if ln:
            out.append(ln)
    return "\n".join(out)


def fetch(url):
    r = requests.get(url, headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"},
                     timeout=45)
    return r.status_code, r.text


class Renderer:
    """Headless Chromium for pages that need JavaScript. Started only when a page
    needs it, so a normal run never launches a browser."""

    def __init__(self):
        self._pw = self._browser = None
        self.unavailable = None  # reason string once we know we can't render

    def html(self, url):
        if self.unavailable:
            return None, self.unavailable
        if self._browser is None:
            try:
                from playwright.sync_api import sync_playwright
            except ImportError:
                self.unavailable = "Playwright not installed, could not render"
                return None, self.unavailable
            try:
                self._pw = sync_playwright().start()
                self._browser = self._pw.chromium.launch(headless=True)
            except Exception as e:  # e.g. browser binary missing
                self.unavailable = f"could not start headless Chromium ({e.__class__.__name__})"
                return None, self.unavailable
        page = self._browser.new_page(user_agent=UA, locale="en-US")
        try:
            resp = page.goto(url, wait_until="domcontentloaded", timeout=45000)
            try:
                page.wait_for_load_state("networkidle", timeout=10000)
            except Exception:
                pass
            status = resp.status if resp else None
            if status != 200:
                return None, f"rendered page returned HTTP {status}"
            return page.content(), None
        except Exception as e:
            return None, f"render error: {e.__class__.__name__}"
        finally:
            page.close()

    def close(self):
        if self._browser:
            self._browser.close()
        if self._pw:
            self._pw.stop()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="only URLs containing this substring")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--fail-on-change", action="store_true")
    ap.add_argument("--delay", type=float, default=1.0, help="seconds between requests")
    ap.add_argument("--no-render", action="store_true",
                    help="don't retry JavaScript-only pages in headless Chromium")
    args = ap.parse_args()

    cfg = load_config()
    patterns = cfg.get("ignore_patterns", [])
    today = datetime.date.today().isoformat()
    SNAP.mkdir(exist_ok=True)
    index_path = SNAP / "index.json"
    index = json.loads(index_path.read_text()) if index_path.exists() else {}

    changed, failed, created, same = [], [], [], 0
    renderer = None if args.no_render else Renderer()
    urls = source_urls()
    for i, (url, slugs) in enumerate(urls.items()):
        if args.only and args.only not in url:
            continue
        key = url_key(url)
        path = SNAP / f"{key}.txt"
        try:
            status, html = fetch(url)
        except requests.RequestException as e:
            failed.append((url, slugs, f"request error: {e.__class__.__name__}"))
            print(f"FAIL  {url}  ({e.__class__.__name__})")
            continue
        text = normalise(main_text(html), patterns) if status == 200 else ""
        method = "http"
        if status == 200 and len(text) < 200 and renderer:
            # HTTP 200 but an empty shell: the text is drawn by JavaScript. Try a real browser.
            rhtml, rwhy = renderer.html(url)
            rtext = normalise(main_text(rhtml), patterns) if rhtml else ""
            if len(rtext) >= 200:
                text, method = rtext, "rendered"
                print(f"REND  {url}  (plain HTTP gave {len(normalise(main_text(html), patterns))} chars)")
            elif rhtml:
                rwhy = f"rendered page has only {len(rtext)} chars of text"
        if status != 200 or len(text) < 200:
            why = f"HTTP {status}" if status != 200 else f"only {len(text)} chars of text (likely JavaScript-rendered)"
            if status == 200 and renderer and method == "http":
                why += f"; {rwhy}"
            failed.append((url, slugs, why))
            print(f"FAIL  {url}  ({why})")
            # keep the previous good snapshot; don't overwrite with nothing
            if not args.dry_run:
                index.setdefault(url, {}).update({"last_attempt": today, "last_error": why, "file": path.name})
            continue
        digest = hashlib.sha256(text.encode()).hexdigest()
        prev = path.read_text() if path.exists() else None
        if prev is None:
            created.append(url)
            print(f"NEW   {url}")
        elif prev != text:
            diff = list(difflib.unified_diff(prev.split("\n"), text.split("\n"),
                                             "previous", "current", lineterm="", n=2))
            changed.append((url, slugs, diff))
            print(f"DIFF  {url}  ({sum(1 for d in diff if d[:1] in '+-')} lines)")
        else:
            same += 1
        if not args.dry_run:
            path.write_text(text)
            index[url] = {"file": path.name, "sha256": digest, "vendors": slugs,
                          "last_checked": today, "last_error": None}
            if method != "http":
                index[url]["method"] = method
        time.sleep(args.delay)

    if renderer:
        renderer.close()

    if not args.dry_run:
        index_path.write_text(json.dumps(index, indent=2, sort_keys=True))

    print(f"\n{len(urls)} sources | {len(created)} new | {len(changed)} changed | "
          f"{same} unchanged | {len(failed)} failed")

    if changed and not args.dry_run:
        CHANGES.mkdir(exist_ok=True)
        out = CHANGES / f"{today}.md"
        parts = [f"# Policy page changes detected {today}\n",
                 f"{len(changed)} page(s) changed. Review each diff, then update "
                 "data/vendors.json and data/changelog.json if a fact changed.\n"]
        for url, slugs, diff in changed:
            parts.append(f"\n## {url}\n\nVendors: {', '.join(slugs) or '-'}\n")
            body = "\n".join(diff[:400])
            if len(diff) > 400:
                body += f"\n... ({len(diff) - 400} more diff lines truncated)"
            parts.append(f"\n```diff\n{body}\n```\n")
        if failed:
            parts.append("\n## Sources that could not be fetched\n")
            parts += [f"- {u} ({why})\n" for u, _, why in failed]
        out.write_text("".join(parts))
        print(f"Report written to {out.relative_to(ROOT)}")

    if failed:
        print("\nCould not snapshot:")
        for u, _, why in failed:
            print(f"  - {u}: {why}")
    return 1 if (changed and args.fail_on_change) else 0


if __name__ == "__main__":
    sys.exit(main())
