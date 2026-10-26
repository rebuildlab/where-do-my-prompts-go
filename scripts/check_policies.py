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

Pages that come back as an empty JavaScript shell (HTTP 200 but almost no text),
and pages a bot wall rejects (HTTP 401, 403, 429, or 503), are fetched again in
headless Chromium, if Playwright is installed
(pip install playwright && python -m playwright install --with-deps chromium).
The browser waits until the document has real text, because some apps (the
Vanta trust center at trust.mistral.ai, for one) never go network-idle. The
index records "method": "rendered" for those pages. Without Playwright, or if
the rendered page is still empty, the page is reported as a fetch error,
exactly as before. Use --no-render to skip the browser step.

Every URL already stored in snapshots/index.json is checked too, even when no
current field cites it. Otherwise a dropped source stays frozen on its old
last_checked date and never appears in the run summary. Those URLs are printed
with a STALE line.
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
# Below this, a 200 response is treated as an empty shell and rendered.
MIN_TEXT = 200
# Statuses that usually mean a bot wall rather than a missing page. A browser
# often gets the real document (x.ai/security is HTTP 403 to requests).
RENDER_STATUSES = (401, 403, 429, 503)


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


def needs_render(status, text_len):
    """Plain HTTP did not yield a document: empty shell, or a bot wall."""
    return (status == 200 and text_len < MIN_TEXT) or status in RENDER_STATUSES


def is_challenge(text):
    """A long Cloudflare interstitial is not the page we asked for."""
    head = text[:800].lower()
    return ("attention required" in head and "cloudflare" in head) or "just a moment" in head


def merge_index_urls(urls, index):
    """Add snapshot-index URLs that no current field cites.

    The checker used to fetch only vendors.json and extra_urls, then write the
    whole index back. Pages that had left the source list kept their old
    last_checked and were never mentioned, so a failure or a gap could sit
    there for every later run.
    """
    for u, prev in index.items():
        if u in urls:
            continue
        urls[u] = sorted(prev.get("vendors") or [])
    return urls


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
            # Vanta (trust.mistral.ai) keeps the network busy, so networkidle
            # fires while the shell is still empty. Wait until the body has text
            # and that text has stopped growing, then read the document.
            try:
                page.wait_for_function(
                    """() => {
                        const n = document.body ? document.body.innerText.trim().length : 0;
                        if (n < 200) return false;
                        const now = Date.now();
                        const prev = window.__wdmpgText || {n: -1, t: now};
                        if (n !== prev.n) { window.__wdmpgText = {n, t: now}; return false; }
                        return now - prev.t >= 1500;
                    }""",
                    timeout=25000,
                )
            except Exception:
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
    cited = set(urls)
    urls = dict(sorted(merge_index_urls(dict(urls), index).items()))
    stale_n = 0

    def note_failure(url, slugs, why, path):
        failed.append((url, slugs, why))
        print(f"FAIL  {url}  ({why})")
        # keep the previous good snapshot; don't overwrite it with nothing
        if not args.dry_run:
            index.setdefault(url, {}).update({"last_attempt": today, "last_error": why, "file": path.name})

    for i, (url, slugs) in enumerate(urls.items()):
        if args.only and args.only not in url:
            continue
        key = url_key(url)
        path = SNAP / f"{key}.txt"
        try:
            if url not in cited:
                prev_meta = index.get(url, {})
                when = prev_meta.get("last_checked") or prev_meta.get("last_attempt") or "never"
                err = prev_meta.get("last_error")
                extra = f"; {err}" if err else ""
                stale_n += 1
                print(f"STALE {url}  (in snapshots/index.json, not cited by a current field; last {when}{extra})")
            try:
                status, html = fetch(url)
            except requests.RequestException as e:
                note_failure(url, slugs, f"request error: {e.__class__.__name__}", path)
                continue
            text = normalise(main_text(html), patterns) if status == 200 else ""
            method = "http"
            rwhy = None
            tried_render = False
            if needs_render(status, len(text)) and renderer:
                # Empty shell, or a bot wall. A real browser can still read the page.
                tried_render = True
                plain_len, orig_status = len(text), status
                rhtml, rwhy = renderer.html(url)
                rtext = normalise(main_text(rhtml), patterns) if rhtml else ""
                if rtext and is_challenge(rtext):
                    rwhy = "rendered page is a bot check, not the document"
                    rtext = ""
                if len(rtext) >= MIN_TEXT:
                    text, method, status = rtext, "rendered", 200
                    print(f"REND  {url}  (plain HTTP {orig_status}, {plain_len} chars; rendered {len(text)} chars)")
                elif rhtml and not rwhy:
                    rwhy = f"rendered page has only {len(rtext)} chars of text"
            if status != 200 or len(text) < MIN_TEXT:
                why = (f"HTTP {status}" if status != 200
                       else f"only {len(text)} chars of text (likely JavaScript-rendered)")
                if tried_render and rwhy:
                    why += f"; {rwhy}"
                note_failure(url, slugs, why, path)
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
            if url not in cited:
                print(f"OK    {url}  ({len(text)} chars via {method})")
            if not args.dry_run:
                path.write_text(text)
                index[url] = {"file": path.name, "sha256": digest, "vendors": slugs,
                              "last_checked": today, "last_error": None}
                if method != "http":
                    index[url]["method"] = method
            time.sleep(args.delay)
        except Exception as e:
            note_failure(url, slugs, f"unexpected {type(e).__name__}: {e}"[:300], path)
            continue

    if renderer:
        renderer.close()

    if not args.dry_run:
        index_path.write_text(json.dumps(index, indent=2, sort_keys=True))

    print(f"\n{len(urls)} sources | {len(created)} new | {len(changed)} changed | "
          f"{same} unchanged | {len(failed)} failed | {stale_n} not cited by current fields")
    if not args.dry_run and not args.only:
        skipped = []
        for u, prev in sorted(index.items()):
            stamp = max(prev.get("last_checked") or "", prev.get("last_attempt") or "")
            if stamp < today:
                skipped.append((u, stamp or "never", prev.get("last_error")))
        if skipped:
            print(f"\nSKIPPED {len(skipped)} source(s) were not fetched and are still stale:")
            for u, when, err in skipped:
                extra = f"; {err}" if err else ""
                print(f"  SKIP  {u}  (last {when}{extra})")

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
