"""Render every built page in headless Chrome and check internal links, #anchors,
console errors, horizontal overflow at 390px, and axe-core accessibility (light + dark).

  /workspace/.venv-pw/bin/python research/redesign/check_site.py [path/to/axe.min.js]
"""
import sys, threading, functools, http.server, socketserver, re
from pathlib import Path
from urllib.parse import urljoin, urlparse
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2] / "public"
AXE = Path(sys.argv[1]).read_text() if len(sys.argv) > 1 else None


class H(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a): pass


srv = socketserver.TCPServer(("127.0.0.1", 0), functools.partial(H, directory=str(ROOT)))
base = f"http://127.0.0.1:{srv.server_address[1]}"
threading.Thread(target=srv.serve_forever, daemon=True).start()

pages = sorted("/" + str(p.relative_to(ROOT)).removesuffix("index.html") for p in ROOT.rglob("*.html"))
problems, ext, checked_targets = [], set(), {}
with sync_playwright() as p:
    b = p.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"])
    for scheme in ("light", "dark"):
        ctx = b.new_context(viewport={"width": 1280, "height": 900}, color_scheme=scheme)
        if scheme == "light":  # the ops theme is dark by default; light is a saved choice
            ctx.add_init_script("try{localStorage.setItem('theme','light')}catch(e){}")
        pg = ctx.new_page()
        errs = []
        pg.on("console", lambda m: m.type == "error" and errs.append(m.text))
        pg.on("pageerror", lambda x: errs.append(str(x)))
        for path in pages:
            errs.clear()
            r = pg.goto(base + path, wait_until="networkidle")
            if not r or r.status != 200 and not path.endswith("404.html"):
                problems.append(f"{path}: HTTP {r.status if r else '??'}")
            if scheme == "light":
                links = pg.eval_on_selector_all("a[href], link[href], script[src], img[src]",
                                                "els => els.map(e => e.getAttribute('href') || e.getAttribute('src'))")
                for href in links:
                    u = urljoin(base + path, href)
                    if not u.startswith(base):
                        if u.startswith("http"): ext.add(u)
                        continue
                    pu = urlparse(u)
                    key = pu.path
                    if key not in checked_targets:
                        rr = pg.request.get(base + key)
                        checked_targets[key] = rr.status
                    if checked_targets[key] != 200:
                        problems.append(f"{path}: broken link {href} -> {checked_targets[key]}")
                    elif pu.fragment and key.endswith("/"):
                        target = (ROOT / key.lstrip("/") / "index.html").read_text()
                        if f'id="{pu.fragment}"' not in target:
                            problems.append(f"{path}: missing anchor {href}")
            if errs:
                problems.append(f"{path} [{scheme}]: console errors {errs}")
            if AXE and (scheme == "dark" and path in ("/", "/vendors/openai-api/", "/changelog/", "/about/") or scheme == "light"):
                pg.add_script_tag(content=AXE)
                res = pg.evaluate("async () => (await axe.run(document, {runOnly: ['wcag2a','wcag2aa','best-practice']})).violations.map(v => [v.id, v.impact, v.nodes.length, v.nodes.slice(0,2).map(n=>n.target.join(' '))])")
                for v in res:
                    problems.append(f"{path} [{scheme}] axe: {v}")
        ctx.close()
    # mobile overflow
    ctx = b.new_context(viewport={"width": 390, "height": 844})
    pg = ctx.new_page()
    for path in pages:
        pg.goto(base + path, wait_until="networkidle")
        sw = pg.evaluate("document.documentElement.scrollWidth")
        if sw > 390:
            problems.append(f"{path}: horizontal overflow at 390px ({sw}px)")
    # keyboard: tab order reaches search and sort buttons on home
    pg.goto(base + "/")
    pg.keyboard.press("/")
    if pg.evaluate("document.activeElement.id") != "q":
        problems.append("/ : '/' shortcut did not focus search")
    pg.fill("#q", "groq")
    n = pg.evaluate("[...document.querySelectorAll('#t tbody tr')].filter(r=>!r.hidden).length")
    if n != 1: problems.append(f"search 'groq' showed {n} rows")
    vis = "[...document.querySelectorAll('#t tbody tr')].filter(r=>!r.hidden)"
    def expect(js_filter):
        return pg.evaluate(f"[...document.querySelectorAll('#t tbody tr')].filter(r=>{js_filter}).length")
    for query, filt, sel in [
            ("vendor:openai trains:no", "r.dataset.search.includes('openai')&&r.dataset.trains==='no'", ("#f-trains", "no")),
            ("zdr:not-offered", "r.dataset.zdr==='not offered'", ("#f-zdr", "not offered")),
            ("cat:coding region:none", "r.dataset.cat==='Coding tools'&&r.dataset.region==='none'", ("#f-region", "none")),
            ("baa:yes", "r.dataset.baa==='ok'", None)]:
        pg.fill("#q", query)
        got = pg.evaluate(f"{vis}.length")
        want = expect(filt)
        if got != want: problems.append(f"query '{query}': {got} rows, expected {want}")
        if sel and pg.eval_on_selector(sel[0], "e=>e.value") != sel[1]:
            problems.append(f"query '{query}' did not sync {sel[0]}")
        print(f"query {query!r}: {got} rows (expected {want}); parsed: {pg.inner_text('#qparsed')}")
    pg.fill("#q", "foo:bar")
    if "unknown key" not in pg.inner_text("#qparsed"): problems.append("unknown key not flagged")
    # old URL params still work and fill the query bar
    pg.goto(base + "/?trains=no&zdr=available&baa=1&q=api", wait_until="networkidle")
    qv = pg.input_value("#q")
    got = pg.evaluate(f"{vis}.length")
    want = expect("r.dataset.trains==='no'&&r.dataset.zdr==='available'&&r.dataset.baa==='ok'&&r.dataset.search.includes('api')")
    print(f"legacy params -> q={qv!r}, {got} rows (expected {want})")
    if got != want or "trains:no" not in qv: problems.append("legacy URL params broken")
    pg.goto(base + "/?cat=Coding+tools&region=none", wait_until="networkidle")
    pg.select_option("#f-trains", "depends")
    print(f"select sync -> q={pg.input_value('#q')!r}, url={pg.url.split('/',3)[3]}")
    if "trains:depends" not in pg.input_value("#q"): problems.append("select did not update query bar")
    # theme toggle persists
    pg.click("#theme")
    pg.reload(wait_until="networkidle")
    if pg.evaluate("document.documentElement.dataset.theme") != "light": problems.append("theme toggle not persisted")
    # severity filter
    pg.click("#events .logbar button[data-sev=ERROR]")
    shown = pg.evaluate("[...document.querySelectorAll('#events .log li')].filter(l=>!l.hidden).map(l=>l.dataset.sev)")
    if not shown or set(shown) != {"ERROR"}: problems.append(f"severity filter shows {set(shown)}")
    b.close()
srv.shutdown()
print(f"{len(pages)} pages rendered; {len(checked_targets)} internal targets checked; {len(ext)} external URLs (not fetched)")
print("\n".join(problems) if problems else "No problems found.")
Path(__file__).with_name("external_links.txt").write_text("\n".join(sorted(ext)) + "\n")
