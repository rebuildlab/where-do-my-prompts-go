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


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True  # a meta refresh fires a second request while the first is still being read


srv = Server(("127.0.0.1", 0), functools.partial(H, directory=str(ROOT)))
base = f"http://127.0.0.1:{srv.server_address[1]}"
threading.Thread(target=srv.serve_forever, daemon=True).start()

pages = sorted("/" + str(p.relative_to(ROOT)).removesuffix("index.html") for p in ROOT.rglob("*.html"))
problems, ext, checked_targets = [], set(), {}
method_html = ROOT / "method" / "index.html"
if not method_html.exists():
    problems.append("/method/: page was not built")
else:
    method_text = method_html.read_text()
    if 'http-equiv="refresh"' not in method_text or "url=../about/" not in method_text:
        problems.append("/method/: missing meta refresh to ../about/")
    canon = method_text.split('rel="canonical"', 1)[-1][:220] if 'rel="canonical"' in method_text else ""
    if "/about/" not in canon:
        problems.append("/method/: canonical does not point at /about/")
for html_path in ROOT.rglob("index.html"):
    nav = re.search(r'<nav class="nav" aria-label="Main">(.*?)</nav>', html_path.read_text())
    if not nav:
        problems.append(f"{html_path.relative_to(ROOT)}: missing main nav")
        continue
    if not re.search(r'href="(?:\./|\.\./)*about/"', nav.group(1)):
        problems.append(f"{html_path.relative_to(ROOT)}: Method nav does not point at about/")
    if re.search(r'href="[^"]*method/"', nav.group(1)):
        problems.append(f"{html_path.relative_to(ROOT)}: nav links to /method/")
home_html = (ROOT / "index.html").read_text() if (ROOT / "index.html").exists() else ""
if 'href="#compare"' not in home_html or "Browse" not in home_html:
    problems.append("home: missing browse CTA")
if "<summary" not in home_html or ">Export data<" not in home_html:
    problems.append("home: missing Export menu")
if 'class="acts"' in home_html or '>get</span>' in home_html:
    problems.append("home: old equal-weight button row still present")
if 'type="email"' in home_html or "you@company.com" in home_html:
    problems.append("home: email signup still looks live")
for needle in ("https://x.com/JeffreyD3V", "suggest-a-tool.md", "report-a-policy-change.md",
               "vendor-or-sponsor.md", "https://github.com/rebuildlab/where-do-my-prompts-go"):
    if needle not in home_html:
        problems.append(f"home: missing link {needle}")
vendor_pages = list((ROOT / "vendors").glob("*/index.html")) if (ROOT / "vendors").exists() else []
if vendor_pages and "suggest-a-tool.md" not in vendor_pages[0].read_text():
    problems.append("vendor page: missing CTA strip")
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
            pg.wait_for_load_state("networkidle")  # /method/ meta-refreshes to /about/ after the first load
            if not r or r.status != 200 and not path.endswith("404.html"):
                problems.append(f"{path}: HTTP {r.status if r else '??'}")
            if scheme == "light":
                links = pg.eval_on_selector_all("a[href], link[href], script[src], img[src]",
                                                "els => els.map(e => e.getAttribute('href') || e.getAttribute('src'))")
                for href in links:
                    u = urljoin(pg.url, href)  # the document the links were read from (after any meta refresh)
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
    pg.goto(base + "/", wait_until="networkidle")
    pg.click("details.menu summary")
    if pg.locator("details.menu[open]").count() != 1:
        problems.append("export menu did not open")
    if pg.locator("details.menu .menu-pop a").count() != 3:
        problems.append("export menu should list json, csv and llms.txt")
    sw = pg.evaluate("document.documentElement.scrollWidth")
    if sw > 390:
        problems.append(f"export menu overflows at 390px ({sw}px)")
    pg.keyboard.press("Escape")
    if pg.locator("details.menu[open]").count():
        problems.append("export menu did not close on Escape")
    pg.click("a.btn.pri")
    pg.wait_for_function("() => location.hash === '#compare'")
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
            ("zdr:yes", "r.dataset.zdr==='available'", ("#f-zdr", "available")),
            ("zdr:available", "r.dataset.zdr==='available'", ("#f-zdr", "available")),
            ("zdr:partial", "r.dataset.zdr==='partial'", ("#f-zdr", "partial")),
            ("zdr:not-offered", "r.dataset.zdr==='not offered'", ("#f-zdr", "not offered")),
            ("zdr:no", "r.dataset.zdr==='not offered'", ("#f-zdr", "not offered")),
            ("zdr:n/a", "r.dataset.zdr==='n/a'", ("#f-zdr", "n/a")),
            ("zdr:unverified", "r.dataset.zdr==='unverified'", ("#f-zdr", "unverified")),
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
