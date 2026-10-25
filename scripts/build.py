#!/usr/bin/env python3
"""Build the static site into public/ from data/vendors.json.

  python3 scripts/build.py
  SITE_URL=https://your-domain.example python3 scripts/build.py   # adds canonical URLs + sitemap

The HTML, CSS and every inline SVG chart need only the Python standard library.
If Pillow is installed (pip install pillow), the PNG social cards and favicon PNGs are
regenerated from the same data by scripts/make_graphics.py; otherwise they are skipped
with a warning (set REQUIRE_GRAPHICS=1 to make that an error, e.g. in CI).
"""
import csv, html, json, math, os, shutil, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive import (FIELD_ORDER, SHORT, REGION_LABEL, TONES, TONE_LABEL, TONE_GLYPH, TONE_RANK,
                    TONE_RULES, trains_key, zdr_key, retention, fmt_days, domain, enrich, stats, load,
                    is_unverified, index_versions, history_from, newest_entries, apply_latest_run,
                    uptime, events)
import hashlib

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "public"
SITE_NAME = "Where Do My Prompts Go?"
SITE_URL = os.environ.get("SITE_URL", "").rstrip("/")
CONTACT_URL = os.environ.get("CONTACT_URL", "")  # optional extra correction link; the GitHub issues below always work
REPO_URL = "https://github.com/rebuildlab/where-do-my-prompts-go"
X_URL = "https://x.com/JeffreyD3V"
ISSUE_TOOL = REPO_URL + "/issues/new?template=suggest-a-tool.md&title=Suggest%20a%20tool%3A%20"
ISSUE_CHANGE = REPO_URL + "/issues/new?template=report-a-policy-change.md&title=Policy%20change%3A%20"
ISSUE_VENDOR = REPO_URL + "/issues/new?template=vendor-or-sponsor.md&title=Vendor%20or%20sponsor%3A%20"
ALERTS_ACTION = "https://buttondown.com/api/emails/embed-subscribe/wheredomypromptsgo"
ALERTS_CREDIT = "https://buttondown.com/refer/wheredomypromptsgo"
e = html.escape
LABELS = {}
HAVE_OG = False  # set in main() once the PNG cards exist


# ---------- small helpers ----------

def short_name(v):
    return v["name"].split(" (")[0]


def chip(t, text, cls=""):
    return (f'<span class="v {t} {cls}"><i class="led {t}" aria-hidden="true"></i>'
            f'<span>{e(text)}<span class="sr"> ({TONE_LABEL[t]})</span></span></span>')


def led(t, cls=""):
    return f'<i class="led {t} {cls}" aria-hidden="true"></i>'


def legend():
    return ('<ul class="legend" aria-label="Status key">' + "".join(
        f'<li>{led(t)}{TONE_LABEL[t]}</li>' for t in TONES)
        + '<li><a href="{rel}about/#colours">rules</a></li></ul>')


def human_size(n):
    return f"{n / 1024:.0f} KB" if n >= 1024 else f"{n} B"


def abs_url(path):
    return (SITE_URL + path) if SITE_URL else path


def panel(title, body, meta="", cls="", pid="", bcls="pn-b", foot="", tag="section", tools=""):
    hid = f"{pid}-h" if pid else ""
    side = ""
    if tools or meta:
        meta_html = f'<span class="pn-meta">{meta}</span>' if meta else ""
        side = f'<div class="pn-tools">{tools}{meta_html}</div>'
    return (f'<{tag} class="pn {cls}"{f" id={chr(34)}{pid}{chr(34)}" if pid else ""}'
            f'{f" aria-labelledby={chr(34)}{hid}{chr(34)}" if hid else ""}>'
            f'<header class="pn-h"><h2{f" id={chr(34)}{hid}{chr(34)}" if hid else ""}>{title}</h2>'
            f'{side}</header>'
            f'<div class="{bcls}">{body}</div>{f"<div class={chr(34)}pn-f{chr(34)}>{foot}</div>" if foot else ""}</{tag}>')


# ---------- page shell ----------

STATUS = {}  # filled in main(): numbers for the top status line


def page(title, body, desc, path, extra_head="", rel=None, og_image="/og.png", active=""):
    canonical = f'<link rel="canonical" href="{e(SITE_URL + path)}">' if SITE_URL else ""
    depth = path.strip("/").count("/") + (1 if path.strip("/") else 0)
    rel = rel or ("../" * depth or "./")
    if HAVE_OG and og_image:
        img = abs_url(og_image) if SITE_URL else rel + og_image.lstrip("/")
        og = (f'<meta property="og:image" content="{e(img)}">\n<meta property="og:image:width" content="1200">\n'
              f'<meta property="og:image:height" content="630">\n<meta name="twitter:card" content="summary_large_image">\n'
              f'<meta name="twitter:image" content="{e(img)}">')
    else:
        og = '<meta name="twitter:card" content="summary">'
    nav = [("", "Dashboard"), ("changelog/", "Changelog"), ("about/", "Method")]
    navhtml = "".join(f'<a href="{rel}{h}"{" aria-current=\"page\"" if active == h else ""}>{t}</a>' for h, t in nav)
    s = STATUS
    pt = "ok" if not s["errors"] else "mid"
    pill = (f'<a class="pill {pt}" href="{rel}changelog/#checks">{led(pt)}'
            f'{s["checked_n"]}<span class="sw"> sources</span> checked · {s["errors"]}<span class="sw"> fetch</span> error{"s" if s["errors"] != 1 else ""}</a>')
    body = body.replace("{rel}", rel)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(title)}</title>
<meta name="description" content="{e(desc)}">
<meta name="color-scheme" content="dark light">
<meta name="theme-color" content="#0a0c0f">
<script>try{{if(localStorage.getItem("theme")==="light")document.documentElement.setAttribute("data-theme","light")}}catch(_){{}}</script>
<meta property="og:title" content="{e(title)}">
<meta property="og:description" content="{e(desc)}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="{e(SITE_NAME)}">
{f'<meta property="og:url" content="{e(SITE_URL + path)}">' if SITE_URL else ''}
{og}
{canonical}
<link rel="icon" href="{rel}favicon.svg" type="image/svg+xml">
{f'<link rel="icon" href="{rel}favicon.ico" sizes="32x32">' if HAVE_OG else ''}
{f'<link rel="apple-touch-icon" href="{rel}apple-touch-icon.png">' if HAVE_OG else ''}
<link rel="preload" href="{rel}assets/fonts/plex-mono-Regular.woff2" as="font" type="font/woff2" crossorigin>
<link rel="stylesheet" href="{rel}assets/style.css">
{extra_head}
</head>
<body>
<a class="skip" href="#main">Skip to content</a>
<header class="top">
<div class="wrap bar">
<a class="brand" href="{rel}"><svg class="logo" viewBox="0 0 32 32" aria-hidden="true">{LOGO_PATHS}</svg><b>wdmpg</b><span>Where Do My Prompts Go?</span></a>
<nav class="nav" aria-label="Main">{navhtml}</nav>
<button type="button" class="theme" id="theme" aria-label="Light theme">Light<span class="tw"> theme</span></button>
</div>
<div class="wrap status" aria-label="Data status">
{pill}
<span>last check <b><time datetime="{s['last']}">{s['last']}</time></b></span>
<span class="ver">data <b>v{s['version']}</b> · sha256 <b>{s['sha']}</b></span>
<span class="dl"><a href="{rel}data.json" download>data.json</a><a href="{rel}data.csv" download>data.csv</a><a href="{rel}llms.txt">llms.txt</a></span>
</div>
</header>
<main id="main" class="wrap">
{body}
</main>
<footer class="foot"><div class="wrap">
<p><strong>Independent.</strong> Every value links to the vendor's own page. Not legal advice; check the source and your contract before you sign anything.</p>
<p class="mono">data: <a href="{rel}data.json">data.json</a> · <a href="{rel}data.csv">data.csv</a> · <a href="{rel}llms.txt">llms.txt</a> · <a href="{rel}about/">method</a> · <a href="{rel}changelog/">changelog</a> · <a href="{rel}funding/">funding</a></p>
<p class="mono">Code <a href="https://github.com/rebuildlab/where-do-my-prompts-go/blob/main/LICENSE">MIT</a> · Data <a href="https://creativecommons.org/licenses/by/4.0/">CC BY 4.0</a></p>
</div></footer>
<script src="{rel}assets/app.js" defer></script>
<!-- Cloudflare Web Analytics --><script type='module' src='https://static.cloudflareinsights.com/beacon.min.js' data-cf-beacon='{{"token": "d85896aec39e4edca687df91995c013d"}}'></script><!-- End Cloudflare Web Analytics -->
</body>
</html>
"""


# Favicon / logo: a prompt caret over three status cells (good / caution / bad).
LOGO_PATHS = ('<rect x=".5" y=".5" width="31" height="31" rx="5" class="lg-bg"/>'
              '<path d="M8 8.5l7 5.5-7 5.5" fill="none" class="lg-fg" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>'
              '<rect x="17.5" y="17.5" width="7" height="3" rx="1.5" class="lg-fg"/>'
              '<rect x="8" y="23.5" width="5" height="3" rx="1" class="lg-ok"/>'
              '<rect x="14" y="23.5" width="5" height="3" rx="1" class="lg-mid"/>'
              '<rect x="20" y="23.5" width="5" height="3" rx="1" class="lg-bad"/>')

FAVICON_SVG = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">
<style>.lg-bg{{fill:#10141a;stroke:#323b47}}.lg-fg{{fill:#d9dee5;stroke:#d9dee5}}.lg-ok{{fill:#2ea043}}.lg-mid{{fill:#c99a2e}}.lg-bad{{fill:#e5534b}}</style>
{LOGO_PATHS}</svg>
"""


# ---------- inline SVG charts (all from vendors.json) ----------

def svg_heatmap(vendors, cats, links=True):
    """Field heatmap. links=False is the decorative hero copy: no anchors, no duplicate ids."""
    LW, CW, RH, GH, TOP = 164, 46, 22, 24, 86
    W = LW + CW * len(FIELD_ORDER) + 34
    y = TOP
    parts = []
    for i, k in enumerate(FIELD_ORDER):
        cx = LW + i * CW + CW / 2
        parts.append(f'<text class="hm-col" transform="translate({cx + 4},{TOP - 8}) rotate(-50)">{e(SHORT[k])}</text>')
    for c in cats:
        parts.append(f'<text class="hm-cat" x="0" y="{y + 16}">{e(c.upper())}</text>'
                     f'<line class="hm-rule" x1="0" x2="{W}" y1="{y + 21.5}" y2="{y + 21.5}"/>')
        y += GH
        for v in [v for v in vendors if v["category"] == c]:
            name = f'<text class="hm-name" x="0" y="{y + 15}">{e(short_name(v))}</text>'
            parts.append(f'<a href="{{rel}}vendors/{v["slug"]}/">{name}</a>' if links else name)
            for i, k in enumerate(FIELD_ORDER):
                x = LW + i * CW
                f = v["fields"][k]
                t = f["_tone"]
                cell = (f'<title>{e(v["name"])}: {e(LABELS[k])} = {e(f["value"])} ({TONE_LABEL[t]})</title>'
                        f'<rect class="hm hm-{t}" x="{x + 2}" y="{y + 2}" width="{CW - 4}" height="{RH - 4}" rx="3"/>'
                        f'<text class="hm-g hm-g-{t}" x="{x + CW / 2}" y="{y + 15}">{TONE_GLYPH[t]}</text>')
                parts.append(f'<a href="{{rel}}vendors/{v["slug"]}/#{k}" tabindex="-1">{cell}</a>' if links else f'<g>{cell}</g>')
            y += RH
    H = y + 4
    counts = {t: sum(v["_counts"][t] for v in vendors) for t in TONES}
    desc = ", ".join(f"{counts[t]} {TONE_LABEL[t].lower()}" for t in TONES)
    if not links:
        return f'<svg class="chart heatmap" viewBox="0 0 {W} {H}" aria-hidden="true">{"".join(parts)}</svg>'
    return (f'<svg class="chart heatmap" viewBox="0 0 {W} {H}" role="group" aria-labelledby="hm-t hm-d">'
            f'<title id="hm-t">Status of {len(FIELD_ORDER)} policy fields for {len(vendors)} tools</title>'
            f'<desc id="hm-d">{len(vendors) * len(FIELD_ORDER)} cells: {desc}. The comparison table below has the same data as text.</desc>'
            + "".join(parts) + "</svg>")


RET_TICKS = [(0, "0"), (1, "1d"), (7, "7d"), (30, "30d"), (90, "90d"), (365, "1y"), (math.inf, "∞")]


def ret_x(d, xa, xb, xinf):
    if d == 0: return xa
    if d == math.inf: return xinf
    return xa + 30 + math.log10(max(d, 1)) / math.log10(365) * (xb - xa - 30)


def svg_retention(vendors):
    rows = sorted([v for v in vendors if v["_ret"]["kind"] == "range"],
                  key=lambda v: (v["_ret"]["lo"], v["_ret"]["hi"], v["name"]))
    LW, RH, TOP, W = 150, 22, 30, 600
    xa, xb, xinf = LW + 10, W - 110, W - 74
    H = TOP + RH * len(rows) + 10
    p = []
    for d, lab in RET_TICKS:
        x = ret_x(d, xa, xb, xinf)
        p.append(f'<line class="ax" x1="{x:.1f}" x2="{x:.1f}" y1="{TOP - 6}" y2="{H - 8}"/>'
                 f'<text class="ax-t" x="{x:.1f}" y="{TOP - 12}">{lab}</text>')
    y = TOP
    for v in rows:
        r, t = v["_ret"], v["fields"]["retention"]["_tone"]
        x1, x2 = ret_x(r["lo"], xa, xb, xinf), ret_x(r["hi"], xa, xb, xinf)
        cy = y + RH / 2
        lab = fmt_days(r["lo"]) if r["lo"] == r["hi"] else f'{fmt_days(r["lo"])}–{fmt_days(r["hi"])}'
        lab = lab.replace("until deleted", "∞")
        bar = (f'<rect class="rb rb-{t}" x="{x1 - 5:.1f}" y="{cy - 5}" width="{x2 - x1 + 10:.1f}" height="10" rx="5"/>'
               if x2 > x1 else f'<circle class="rb rb-{t}" cx="{x1:.1f}" cy="{cy}" r="5.5"/>')
        p.append(f'<a href="{{rel}}vendors/{v["slug"]}/#retention"><title>{e(v["name"])}: {e(v["fields"]["retention"]["value"])}</title>'
                 f'<rect class="row-hit" x="0" y="{y}" width="{W}" height="{RH}"/>'
                 f'<text class="hm-name" x="0" y="{cy + 4}">{e(short_name(v))}</text>{bar}'
                 f'<text class="rb-l" x="{W - 2}" y="{cy + 4}">{e(lab)}</text></a>')
        y += RH
    return (f'<svg class="chart retention" viewBox="0 0 {W} {H}" role="group" aria-labelledby="rt-t">'
            f'<title id="rt-t">Default retention for the {len(rows)} tools that state a period, log scale from 0 days to until deleted</title>'
            + "".join(p) + "</svg>"), rows


def svg_retention_mini(vendors, me):
    """One-line strip: every tool's stated retention as a faint tick, this tool highlighted."""
    W, H = 520, 46
    xa, xb, xinf = 12, W - 52, W - 14
    p = [f'<line class="ax" x1="{xa}" x2="{xinf}" y1="20" y2="20"/>']
    for d, lab in RET_TICKS:
        x = ret_x(d, xa, xb, xinf)
        p.append(f'<line class="ax" x1="{x:.1f}" x2="{x:.1f}" y1="15" y2="25"/><text class="ax-t" x="{x:.1f}" y="41">{lab}</text>')
    for v in vendors:
        r = v["_ret"]
        if r["kind"] != "range" or v is me: continue
        for d in {r["lo"], r["hi"]}:
            p.append(f'<circle class="mini-o" cx="{ret_x(d, xa, xb, xinf):.1f}" cy="20" r="3"/>')
    r, t = me["_ret"], me["fields"]["retention"]["_tone"]
    if r["kind"] == "range":
        x1, x2 = ret_x(r["lo"], xa, xb, xinf), ret_x(r["hi"], xa, xb, xinf)
        p.append(f'<rect class="rb rb-{t}" x="{x1 - 6:.1f}" y="14" width="{x2 - x1 + 12:.1f}" height="12" rx="6"/>')
        desc = f"{me['name']} stated retention {fmt_days(r['lo'])} to {fmt_days(r['hi'])}, shown against the other tools"
    else:
        desc = f"{me['name']} states no fixed retention period"
    return (f'<svg class="chart mini" viewBox="0 0 {W} {H}" role="img" aria-label="{e(desc)}">' + "".join(p) + "</svg>")


def svg_field_bars(vendors):
    LW, RH, W = 150, 26, 600
    n = len(vendors)
    span = W - LW - 4
    p = []
    y = 4
    order = ["ok", "mid", "na", "bad", "unk"]
    for k in FIELD_ORDER:
        x = LW
        p.append(f'<text class="hm-name" x="0" y="{y + 16}">{e(LABELS[k] if len(LABELS[k]) < 22 else SHORT[k])}</text>')
        for t in order:
            c = sum(1 for v in vendors if v["fields"][k]["_tone"] == t)
            if not c: continue
            w = c / n * span
            p.append(f'<g><title>{e(LABELS[k])}: {c} of {n} {TONE_LABEL[t].lower()}</title>'
                     f'<rect class="hm hm-{t}" x="{x:.1f}" y="{y + 3}" width="{w - 2:.1f}" height="{RH - 8}" rx="3"/>'
                     + (f'<text class="hm-g hm-g-{t}" x="{x + w / 2 - 1:.1f}" y="{y + 16}">{c}</text>' if w >= 16 else "")
                     + "</g>")
            x += w
        y += RH
    return (f'<svg class="chart bars" viewBox="0 0 {W} {y + 4}" role="img" aria-label="How the {n} tools split on each field, by colour status">'
            + "".join(p) + "</svg>")


def tone_strip(counts, total, cls="strip"):
    segs = "".join(f'<span class="seg {t}" style="flex:{counts[t]}" title="{counts[t]} {TONE_LABEL[t].lower()}"></span>'
                   for t in ["ok", "mid", "na", "bad", "unk"] if counts.get(t))
    return f'<span class="{cls}" aria-hidden="true">{segs}</span>'


# ---------- pages ----------

def ext_a(url, text, cls=""):
    c = f' class="{cls}"' if cls else ""
    return f'<a{c} href="{e(url)}" rel="noopener noreferrer">{e(text)}</a>'


def hero(vendors, st, cats):
    """Centred banner, then a tilted picture of this page's own numbers.

    The picture is the same KPI counts and the same heatmap SVG as the dashboard
    below (links stripped so it is not a second set of controls). It is rebuilt
    by scripts/build.py on every run, so it stays in step with the data.
    """
    s = st
    n = s["n"]
    word = "tool" if n == 1 else "tools"
    ok_src = s["monitored_pages"] - s["monitor_errors"]
    src_tone = "ok" if not s["monitor_errors"] else "mid"
    tiles = [
        ("ok", "trains by default", f'{s["trains_no"]}/{n}', "don't train by default"),
        ("ok", "zero data retention", f'{s["zdr_available"]}/{s["zdr_applicable"]}', "offer ZDR"),
        ("mid", "default retention", f'{len(s["zero_retention"])}/{n}', "keep nothing"),
        (src_tone, "source monitor", f'{ok_src}/{s["monitored_pages"]}', f'ok on {s["monitor_last"]}'),
    ]
    cards = "".join(
        f'<div class="hb-card"><span class="k">{led(t)}{label}</span>'
        f'<span class="num">{num}</span><span class="sub">{sub}</span></div>'
        for t, label, num, sub in tiles)
    fields = len(FIELD_ORDER)
    return f'''<section class="hero">
<div class="hero-copy">
<h1>What happens to your prompts after you hit enter</h1>
<p class="lede">Training, retention, ZDR and residency for {n} AI tools, quoted from each vendor.</p>
<div class="hero-actions">
<a class="btn pri" href="#compare">Browse {n} {word}</a>
<details class="menu">
<summary class="btn">Export data</summary>
<div class="menu-pop" role="group" aria-label="Download the data">
<a href="{{rel}}data.json" download>data.json<small>full dataset</small></a>
<a href="{{rel}}data.csv" download>data.csv<small>one row per tool</small></a>
<a href="{{rel}}llms.txt">llms.txt<small>plain text for agents</small></a>
</div>
</details>
</div>
<p class="hero-quiet"><a href="#alerts">Email alerts</a>{ext_a(X_URL, "Follow on X")}{ext_a(REPO_URL, "GitHub")}</p>
</div>
<div class="hero-stage">
<div class="hero-board" aria-hidden="true">
<div class="hb-kpis">{cards}</div>
<div class="hb-heat"><div class="hb-cap"><span class="k">Field status heatmap</span><span>{n} × {fields} cells</span></div>{svg_heatmap(vendors, cats, links=False)}</div>
</div>
</div>
</section>'''


def cta_strip(n):
    """Quiet text row for the bottom of a page. Internal links use the {{rel}} placeholder."""
    word = "tool" if n == 1 else "tools"
    return f'''<nav class="cta-line" aria-label="More actions">
<p class="cta-links"><a href="{{rel}}#compare">Browse {n} {word}</a><a href="{{rel}}data.json" download>data.json</a><a href="{{rel}}data.csv" download>data.csv</a><a href="{{rel}}llms.txt">llms.txt</a>{ext_a(X_URL, "Follow on X")}{ext_a(ISSUE_TOOL, "Suggest a tool")}{ext_a(ISSUE_CHANGE, "Report a change")}{ext_a(REPO_URL, "GitHub")}</p>
<p class="cta-note">Vendor or sponsor? {ext_a(ISSUE_VENDOR, "Open an issue")} or DM {ext_a(X_URL, "@JeffreyD3V")}.</p>
</nav>'''


def alert_form():
    """Plain Buttondown signup. Posts in a new tab; no script."""
    return f'''<form class="alert" id="alerts" action="{e(ALERTS_ACTION)}" method="post" target="_blank">
<label class="sr" for="alerts-email">Email</label>
<input id="alerts-email" name="email" type="email" required autocomplete="email" placeholder="you@example.com" inputmode="email">
<button type="submit">Get weekly alerts</button>
<p class="alert-note">Weekly policy changes. Confirm by email. Unsubscribe anytime.</p>
<p class="alert-by">{ext_a(ALERTS_CREDIT, "Powered by Buttondown")}</p>
</form>'''


def contribute_panel():
    def row(url, label, hint):
        return f'<li><a href="{e(url)}" rel="noopener noreferrer">{e(label)}<small>{e(hint)}</small></a></li>'
    rows = "".join([
        row(ISSUE_TOOL, "Suggest a tool", "open an issue"),
        row(ISSUE_CHANGE, "Report a policy change", "open an issue"),
        row(REPO_URL, "Star on GitHub", "the repo"),
        row(X_URL, "Follow on X", "@JeffreyD3V"),
    ])
    return panel("Contribute", f'''<ul class="rows">{rows}</ul>
{alert_form()}''', meta="issues", pid="contribute", bcls="pn-b flush")


def terminal_card(v):
    f = v["fields"]["trains_by_default"]
    obj = {k: f[k] for k in ("value", "quote", "source", "checked")}
    js = json.dumps(obj, indent=2, ensure_ascii=False)
    q = f".vendors[] | select(.slug==\"{v['slug']}\") | .fields.trains_by_default"
    cmd = f"curl -s {SITE_URL}/data.json | jq '{q}'" if SITE_URL else f"jq '{q}' data.json"
    out = e(js).replace(e(f'"{f["value"]}"'), f'<b class="t-{f["_tone"]}">{e(chr(34) + f["value"] + chr(34))}</b>', 1)
    return f'<pre class="term" tabindex="0" aria-label="Example query against data.json"><code><span class="t-mut">$</span> {e(cmd)}\n{out}</code></pre>'


SEV_ORDER = ["ERROR", "WARN", "CHANGE", "INFO"]


def event_lines(evs, vendors, limit=None):
    slugs = {v["slug"] for v in vendors}
    out = []
    for x in evs[:limit] if limit else evs:
        who = x["vendor"]
        parts = []
        for w in who.split(","):
            if w in slugs:
                href = f'{{rel}}vendors/{w}/' + (f'#{x["field"]}' if x["field"] in FIELD_ORDER else "")
                parts.append(f'<a href="{href}">{e(w)}</a>')
            else:
                parts.append(e(w))
        src = (f'<a class="src" href="{e(x["src"])}" rel="nofollow noopener">{e(domain(x["src"]))}</a>'
               if x.get("src") and x["sev"] == "ERROR" else "")
        out.append(f'<li class="ln {x["sev"]}" data-sev="{x["sev"]}"><time datetime="{x["date"]}">{x["date"]}</time>'
                   f'<span class="tag">{x["sev"]}</span><span class="who">{",".join(parts)}</span>'
                   f'<span class="fld">{e(x["field"])}</span><span class="msg">{e(x["msg"])}{src}</span></li>')
    return "".join(out)


def full_check_sentence(st):
    """One sentence for the status bar's source of truth: the newest checker run."""
    n, err = st["monitored_pages"], st["monitor_errors"]
    return (f"Last full check {st['full_check']}: {n} source{'s' if n != 1 else ''} fetched, "
            f"{err} failed.")


def event_panel(evs, vendors, pid="events", limit=None, extra_meta=""):
    counts = {s: sum(1 for x in evs if x["sev"] == s) for s in SEV_ORDER}
    btns = (f'<button type="button" data-sev="" aria-pressed="true">all {len(evs)}</button>'
            + "".join(f'<button type="button" data-sev="{s}" aria-pressed="false">{s.lower()} {counts[s]}</button>'
                      for s in SEV_ORDER))
    shown = evs[:limit] if limit else evs
    body = (f'<div class="logbar" role="group" aria-label="Filter events by severity">{btns}</div>'
            f'<ol class="log scroll" tabindex="0" aria-label="Policy events, newest first">{event_lines(shown, vendors)}</ol>')
    srcs = "changelog.json · snapshots/index.json · vendors.json"
    foot = (f'<p>Every line comes from a file in the repo ({srcs}). Dates only: the checker records the day, not the time. '
            + (f'Showing the newest {len(shown)} of {len(evs)}. <a href="{{rel}}changelog/#events">Full stream</a>.' if len(shown) < len(evs) else "")
            + extra_meta + '</p>')
    return panel("Policy event stream", body, meta=f"{len(evs)} events", pid=pid, bcls="pn-b flush", foot=foot)


CELL_GLYPH = {"ok": "✓", "mid": "!", "bad": "×", "none": "–"}
CELL_LABEL = {"ok": "all sources fetched", "mid": "some sources failed", "bad": "all sources failed",
              "none": "no source in the checker index"}


def uptime_panel(dates, rows, pid="checks"):
    lis = []
    for r in rows:
        cells = "".join(
            f'<span class="cell {c["state"]}" title="{c["date"]}: {c["ok"]}/{c["n"]} ok">'
            f'<span aria-hidden="true">{CELL_GLYPH[c["state"]]}</span><span class="sr">{c["date"]}: {CELL_LABEL[c["state"]]}</span></span>'
            for c in r["cells"])
        last = r["cells"][-1] if r["cells"] else None
        ratio = f'{last["ok"]}/{last["n"]}' if last and last["n"] else "–"
        lis.append(f'<li><a class="nm" href="{{rel}}vendors/{r["slug"]}/#sources">{e(r["name"])}</a><span class="cells">{cells}</span>'
                   f'<span class="ratio">{ratio}</span><span class="unm">{len(r["unmonitored"]) or "–"}</span></li>')
    start = dates[0] if dates else "n/a"
    head = ('<div class="up-head" aria-hidden="true"><span>tool</span><span>runs</span><span>last ok</span><span>not idx</span></div>')
    leg = " · ".join(f'<span class="cell {k}" style="display:inline-grid;width:16px;height:12px" aria-hidden="true">{g}</span> {CELL_LABEL[k]}'
                     for k, g in CELL_GLYPH.items())
    foot = (f'<p class="note-line"><strong class="mono">history starts {start}</strong> · {len(dates)} run{"s" if len(dates) != 1 else ""} on record</p>'
            f'<p>One cell per nightly run, read from snapshots/index.json and its git history. Older runs are not reconstructed. '
            f'“not idx” = pages a field cites that the checker has not fetched yet.</p><p>{leg}</p>')
    return panel("Source checks by tool", head + f'<ul class="up scroll" tabindex="0" aria-label="Source check results per tool">{"".join(lis)}</ul>',
                 meta=f"{len(rows)} tools · {len(dates)} run{'s' if len(dates) != 1 else ''}", pid=pid, bcls="pn-b flush", foot=foot)


def stat_panel(href, k, t, num, lbl, strip, sub, cls="c2"):
    return (f'<div class="pn {cls}"><a class="stat" href="{href}"><span class="k">{led(t)}{k}</span>'
            f'<span class="num">{num}</span><span class="lbl">{lbl}</span>{strip}<span class="sub">{sub}</span></a></div>')


def build_index(vendors, st, files, evs, up):
    cats = list(dict.fromkeys(v["category"] for v in vendors))
    rows = []
    for v in vendors:
        f = v["fields"]

        def cell(k, text=None):
            t = f[k]["_tone"]
            return f'<td data-label="{e(SHORT[k])}" data-rank="{TONE_RANK[t]}">{chip(t, text or f[k]["value"])}</td>'
        rows.append(
            f'<tr data-cat="{e(v["category"])}" data-trains="{trains_key(f["trains_by_default"]["value"])}" '
            f'data-zdr="{zdr_key(f["zdr"]["value"])}" data-region="{e(v["region_filter"])}" '
            f'data-baa="{f["hipaa_baa"]["_tone"]}" data-unk="{v["_counts"]["unk"]}" data-name="{e(v["name"].lower())}" '
            f'data-search="{e((v["slug"] + " " + v["name"] + " " + v["vendor"] + " " + v["category"]).lower())}">'
            f'<th scope="row" data-rank="0"><a href="vendors/{v["slug"]}/">{e(v["name"])}</a>'
            f'<small>{e(v["vendor"])} · {e(v["category"])}</small>{tone_strip(v["_counts"], 8)}</th>'
            + cell("trains_by_default") + cell("retention") + cell("zdr") + cell("abuse_monitoring")
            + cell("residency", REGION_LABEL[v["region_filter"]])
            + cell("certifications") + cell("hipaa_baa") + cell("self_host") + "</tr>")
    opt = lambda vals: "".join(f'<option value="{e(a)}">{e(b)}</option>' for a, b in vals)
    heads = [("Service", "name")] + [(SHORT[k] if k != "residency" else "SG / APAC", k) for k in FIELD_ORDER]
    thead = "".join(
        f'<th scope="col" aria-sort="none"><button type="button" data-col="{i}">{e(h)}<span class="arr" aria-hidden="true"></span></button></th>'
        for i, (h, _) in enumerate(heads))
    s = st
    ret_svg, ret_rows = svg_retention(vendors)
    no_number = [v for v in vendors if v["_ret"]["kind"] != "range"]
    stat_trains = {"ok": s["trains_no"], "mid": s["trains_depends"], "bad": s["trains_yes"], "unk": s["trains_unverified"]}
    zk = [zdr_key(v["fields"]["zdr"]["value"]) for v in vendors]
    zdr_counts = {"ok": s["zdr_available"], "mid": zk.count("partial"), "bad": zk.count("not offered"), "unk": zk.count("unverified")}
    ret_counts = {t: sum(1 for v in vendors if v["fields"]["retention"]["_tone"] == t) for t in TONES}
    unk_counts = {"unk": s["unverified"], "na": s["total_fields"] - s["unverified"]}
    reg_counts = {t: sum(1 for v in vendors if v["fields"]["residency"]["_tone"] == t) for t in TONES}
    ok_src = s["monitored_pages"] - s["monitor_errors"]
    src_counts = {"ok": ok_src, "bad": s["monitor_errors"]}
    unidx = len({u for r in up[1] for u in r["unmonitored"]})
    stats_html = "".join([
        stat_panel("?trains=no#compare", "trains by default", "ok", f"{s['trains_no']}<small>/{s['n']}</small>",
                   "don't train on your data by default", tone_strip(stat_trains, s["n"]),
                   f"{s['trains_depends']} depend · {s['trains_unverified']} unverified · {s['trains_yes']} yes"),
        stat_panel("?zdr=available#compare", "zero data retention", "ok", f"{s['zdr_available']}<small>/{s['zdr_applicable']}</small>",
                   "offer ZDR in some form", tone_strip(zdr_counts, s["zdr_applicable"]),
                   f"{s['n'] - s['zdr_applicable']} observability tools: n/a"),
        stat_panel("#retention", "default retention", "mid", f"{len(s['zero_retention'])}<small>/{s['n']}</small>",
                   "keep nothing by default", tone_strip(ret_counts, s["n"]),
                   f"{len(s['longest_retention'])} keep data until deleted"),
        stat_panel("?region=sg#compare", "sg / apac region", "mid", f"{s['sg_region']}<small>/{s['n']}</small>",
                   f"offer a Singapore region; {s['apac_region']} offer APAC", tone_strip(reg_counts, s["n"]),
                   f"{sum(1 for v in vendors if v['region_filter'] == 'unverified')} region unverified"),
        stat_panel("about/#unverified", "unverified fields", "unk", f"{s['unverified']}<small>/{s['total_fields']}</small>",
                   "no official page said it clearly", tone_strip(unk_counts, s["total_fields"]),
                   "WARN lines in the event stream"),
        stat_panel("#checks", "source monitor", "mid" if s["monitor_errors"] else "ok",
                   f"{ok_src}<small>/{s['monitored_pages']}</small>", f"pages fetched OK on {s['monitor_last']}",
                   tone_strip(src_counts, s["monitored_pages"]),
                   f"{s['monitor_errors']} fetch errors · {unidx} cited pages not indexed yet"),
    ])
    body = f"""
{hero(vendors, s, cats)}
<div class="grid" role="list" aria-label="Key numbers">{stats_html.replace('<div class="pn c2">', '<div class="pn c2" role="listitem">')}</div>
<div class="grid">
{panel("Field status heatmap", f'<div class="scroll-x">{svg_heatmap(vendors, cats)}</div>', meta=f"{s['n']} × {len(FIELD_ORDER)} cells", cls="c7", pid="heatmap", tools=legend(), foot="Hover or focus a cell for the exact value. Each cell links to its evidence.")}
<div class="c5 stack">{panel("Default retention", f'<div class="scroll-x">{ret_svg}</div><p class="fn">Log scale. Bars span the shortest to longest period in the value; ∞ = until you delete it. No fixed number: ' + "; ".join(f'<a href="vendors/{v["slug"]}/#retention">{e(short_name(v))}</a> “{e(v["fields"]["retention"]["value"])}”' for v in no_number) + '.</p>', meta=f"{len(ret_rows)} with a stated period", pid="retention")}
{panel("Field split", svg_field_bars(vendors), meta=f"{s['n']} tools per field", pid="split")}</div>
</div>
<div class="grid">
<div class="c7" style="display:flex">{event_panel(evs, vendors, limit=40, extra_meta=" " + full_check_sentence(st))}</div>
<div class="c5" style="display:flex">{uptime_panel(*up)}</div>
</div>
<section id="compare" class="pn" aria-labelledby="compare-h" style="margin-bottom:var(--s3)">
<header class="pn-h"><h2 id="compare-h">Services</h2><span id="count" class="pn-meta" aria-live="polite"></span></header>
<div class="pn-b" role="search" aria-label="Filter services">
<div class="qbar"><label for="q">query&gt;</label><input id="q" type="text" spellcheck="false" autocomplete="off" placeholder="vendor:openai trains:no region:sg" aria-describedby="qhelp"><kbd aria-hidden="true">/</kbd><button type="button" id="reset">clear</button></div>
<p class="qhelp" id="qhelp">keys: <code>vendor:</code> <code>cat:</code> <code>trains:</code>no|depends|yes|unverified <code>zdr:</code>yes|available|partial|not-offered|n/a|unverified <code>region:</code>sg|apac|none|unverified <code>baa:yes</code> · other words search names</p>
<p class="qparsed" id="qparsed" aria-live="polite"></p>
<div class="facets">
<select id="f-cat" aria-label="Category"><option value="">cat: any</option>{opt((c, c) for c in cats)}</select>
<select id="f-trains" aria-label="Trains by default"><option value="">trains: any</option>{opt([("no","trains: no"),("depends","trains: depends"),("yes","trains: yes"),("unverified","trains: unverified")])}</select>
<select id="f-zdr" aria-label="Zero data retention"><option value="">zdr: any</option>{opt([("available","zdr: available"),("partial","zdr: partial"),("not offered","zdr: not offered"),("n/a","zdr: n/a"),("unverified","zdr: unverified")])}</select>
<select id="f-region" aria-label="Region"><option value="">region: any</option>{opt((k, "region: " + k) for k in REGION_LABEL)}</select>
<label class="toggle"><input type="checkbox" id="f-baa"> baa: yes</label>
</div>
</div>
<div class="pn-b flush" style="border-top:1px solid var(--line)">
<table id="t">
<caption class="sr">{s['n']} AI tools compared on {len(FIELD_ORDER)} data-policy fields</caption>
<thead><tr>{thead}</tr></thead>
<tbody>
{''.join(rows)}
</tbody>
</table>
<p id="none" class="empty" hidden>0 rows match. <button type="button" class="linkish" data-reset>Clear the query</button></p>
</div>
</section>
<div class="grid">
{panel("Data endpoints", f'''<ul class="ep">
<li><span class="m">GET</span><a href="data.json" download>/data.json<small>full dataset, nested by tool and field</small></a><span class="sz">{human_size(files['data.json'])}</span></li>
<li><span class="m">GET</span><a href="data.csv" download>/data.csv<small>one row per tool, 5 columns per field</small></a><span class="sz">{human_size(files['data.csv'])}</span></li>
<li><span class="m">GET</span><a href="llms.txt">/llms.txt<small>plain-text map for agents and LLM tools</small></a><span class="sz">{human_size(files['llms.txt'])}</span></li>
</ul>{terminal_card(vendors[0])}''', meta="free to reuse", cls="c8", pid="data", bcls="pn-b flush")}
<div class="c4" style="display:flex;flex-direction:column">{contribute_panel()}</div>
</div>
{cta_strip(s['n'])}
"""
    desc = f"Sourced comparison of how {s['n']} AI tools handle your data: training defaults, retention, ZDR, regions, SOC 2, HIPAA BAA. Checked {s['baseline']}."
    ld = {"@context": "https://schema.org", "@type": "Dataset", "name": SITE_NAME,
          "description": desc, "dateModified": s["checked"], "isAccessibleForFree": True,
          "distribution": [{"@type": "DataDownload", "encodingFormat": "application/json", "contentUrl": abs_url("/data.json")},
                           {"@type": "DataDownload", "encodingFormat": "text/csv", "contentUrl": abs_url("/data.csv")}]}
    head = f'<script type="application/ld+json">{json.dumps(ld, ensure_ascii=False)}</script>'
    return page(f"{SITE_NAME} AI data retention and training tracker", body, desc, "/", head, active="")


def build_vendor(v, vendors, idx, snapshots, uprow):
    f = v["fields"]
    noun = "your code" if v["category"] == "Coding tools" else "your data"
    checked = max(x["checked"] for x in f.values())
    title = f"Does {v['name']} train on {noun}? Data retention and privacy (checked {checked})"
    tr = f["trains_by_default"]
    answer = f"{tr['value'].capitalize()}. {tr['detail']}".strip()
    srcs = sorted({x["source"] for x in f.values() if x["source"]})
    c = v["_counts"]
    worst = "bad" if c["bad"] else "mid" if c["mid"] else "unk" if c["unk"] else "ok"
    tally = "".join(f'<span class="tally">{led(t)}{c[t]} {TONE_LABEL[t].lower()}</span>' for t in TONES if c[t])
    last = uprow["cells"][-1] if uprow["cells"] else None
    mon = (f'{last["ok"]}/{last["n"]} ok on {last["date"]}' if last and last["n"] else "not in checker index")
    tiles = "".join(
        f'<div class="pn {f[k]["_tone"]} c3"><a class="fp {f[k]["_tone"]}" href="#{k}"><span class="k">{led(f[k]["_tone"])}{e(SHORT[k])}</span>'
        f'<span class="val">{e(REGION_LABEL[v["region_filter"]] if k == "residency" else f[k]["value"])}'
        f'<span class="sr"> ({TONE_LABEL[f[k]["_tone"]]})</span></span>'
        f'<span class="st">{TONE_LABEL[f[k]["_tone"]].lower()} · checked {f[k]["checked"]}</span></a></div>' for k in FIELD_ORDER)
    TAG = {"ok": "OK", "mid": "WARN", "bad": "FAIL", "unk": "UNVERIF", "na": "N/A"}
    entries = []
    for k in FIELD_ORDER:
        x = f[k]
        t = x["_tone"]
        if x["source"]:
            d = domain(x["source"])
            src = (f'<a href="{e(x["source"])}" rel="nofollow noopener" target="_blank">'
                   f'{e(d)}<span class="path">{e(x["source"].split(d, 1)[-1][:80])}</span> ↗</a>')
        else:
            src = '<span>no source page</span>'
        cite = (f'{e(v["name"])}: {e(LABELS[k])} = {e(x["value"])}. &quot;{e(x["quote"])}&quot; '
                f'Source: {e(x["source"])} (checked {e(x["checked"])})')
        body = (f'<blockquote{f" cite={chr(34)}{e(x["source"])}{chr(34)}" if x["source"] else ""}><p>{e(x["quote"])}</p></blockquote>'
                if x["quote"] else
                f'<p class="none">{"no official page stated this clearly" if t == "unk" else "no quote stored for this field"}</p>')
        extra = ""
        if k == "retention":
            extra = (f'<div class="mini-wrap"><p>Against the {sum(1 for o in vendors if o["_ret"]["kind"] == "range")} tools that state a period (grey dots):</p>{svg_retention_mini(vendors, v)}</div>'
                     if v["_ret"]["kind"] == "range" else
                     '<p class="none">No fixed period stated, so this tool isn\'t plotted on the <a href="../../#retention">retention chart</a>.</p>')
        entries.append(f"""<article class="ev {t}" id="{k}" aria-labelledby="h-{k}">
<div class="ev-line"><time datetime="{e(x['checked'])}">{e(x['checked'])}</time><span class="tag">{TAG[t]}</span>
<h2 id="h-{k}">{e(LABELS[k])}</h2><span class="kv-val">= {chip(t, x['value'])}</span></div>
{f'<p class="detail">{e(x["detail"])}</p>' if x['detail'] else ''}{body}{extra}
<div class="ev-src"><span>src</span>{src}{f'<button type="button" class="copy" data-cite="{cite}">Copy citation</button>' if x['quote'] else ''}</div>
</article>""")
    snaps = snapshots or {}
    src_items = []
    for u in srcs:
        x = snaps.get(u)
        if not x:
            stt = '<span class="s-none">NOT IDX</span>'
            why = "cited, not fetched by the checker yet"
        elif x.get("last_error") and (x.get("last_attempt") or "") >= (x.get("last_checked") or ""):
            stt = '<span class="s-bad">× ERROR</span>'
            why = f'{e(x["last_error"])} on {e(x.get("last_attempt", ""))}'
        else:
            stt = '<span class="s-ok">✓ OK</span>'
            why = f'fetched {e(x.get("last_checked", ""))}'
        flds = ", ".join(SHORT[k] for k in FIELD_ORDER if f[k]["source"] == u)
        src_items.append(f'<li>{stt}<span><a href="{e(u)}" rel="nofollow noopener">{e(domain(u))}{e(u.split(domain(u), 1)[-1][:60])}</a>'
                         f'<small>{why} · {e(flds)}</small></span></li>')
    toc = "".join(f'<li><a href="#{k}">{led(f[k]["_tone"])}{e(SHORT[k])}</a></li>' for k in FIELD_ORDER)
    prev_v, next_v = vendors[idx - 1], vendors[(idx + 1) % len(vendors)]
    faq = {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
        {"@type": "Question", "name": f"Does {v['name']} train on {noun}?",
         "acceptedAnswer": {"@type": "Answer", "text": answer}},
        {"@type": "Question", "name": f"How long does {v['name']} retain prompts?",
         "acceptedAnswer": {"@type": "Answer", "text": f"{f['retention']['value']}. {f['retention']['detail']}".strip()}}]}
    head = f'<script type="application/ld+json">{json.dumps(faq, ensure_ascii=False)}</script>'
    cat_q = v["category"]
    body = f"""
<nav class="crumb" aria-label="Breadcrumb"><a href="../../">dashboard</a> / <a href="../../?cat={e(cat_q)}#compare">{e(cat_q.lower())}</a> / <span aria-current="page">{e(v['slug'])}</span></nav>
<section class="pn {worst}" aria-label="Service status" style="margin-bottom:var(--s3)">
<div class="svc">
<p class="svc-id"><span>service <b>{e(v['slug'])}</b></span><span>vendor <b>{e(v['vendor'])}</b></span><span>category <b>{e(v['category'])}</b></span></p>
<h1>Does {e(v['name'])} train on {noun}?</h1>
<p class="answer">{chip(tr['_tone'], tr['value'].capitalize(), 'big')}<span>{e(tr['detail'])}</span></p>
</div>
<dl class="kv">
<div><dt>fields</dt><dd>{tally}</dd></div>
<div><dt>sources cited</dt><dd>{len(srcs)} page{'s' if len(srcs) != 1 else ''}</dd></div>
<div><dt>source monitor</dt><dd>{e(mon)}</dd></div>
<div><dt>last field check</dt><dd><time datetime="{checked}">{checked}</time></dd></div>
</dl>
</section>
{f'<aside class="notice" role="note"><strong>NOTICE</strong><p>{e(v["notes"])}</p></aside>' if v.get("notes") else ""}
<div class="grid" role="list" aria-label="Field status">{tiles.replace('c3"><a', 'c3" role="listitem"><a')}</div>
<div class="grid">
<div class="c8">{panel("Evidence log", "".join(entries), meta=f"{len(FIELD_ORDER)} entries · newest check {checked}", pid="evidence", bcls="pn-b flush")}</div>
<div class="c4"><div class="side">
{panel("Fields", f'<ol class="toc">{toc}</ol>', bcls="pn-b flush", tag="nav")}
{panel("Source checks", f'<ul class="srcs">{"".join(src_items)}</ul>', meta=f"{len(srcs)} pages", pid="sources", bcls="pn-b flush")}
</div></div>
</div>
<nav class="pager" aria-label="Other tools"><a href="../{prev_v['slug']}/"><span>← previous</span>{e(prev_v['name'])}</a><a href="../{next_v['slug']}/"><span>next →</span>{e(next_v['name'])}</a></nav>
<p class="fix">Spotted something wrong or out of date? Corrections are welcome; see <a href="../../about/#corrections">how to send one</a>. <a href="../../about/#colours">How statuses are assigned</a>.</p>
<div class="alert-wrap">{alert_form()}</div>
{cta_strip(len(vendors))}
"""
    desc = f"{v['name']}: {tr['value']} on training by default; retention {f['retention']['value']}; ZDR {f['zdr']['value']}. Sourced from official pages, checked {checked}."
    return page(title, body, desc[:300], f"/vendors/{v['slug']}/", head, og_image=f"/og/{v['slug']}.png")


def build_changelog(entries, vendors, st, n_reports, evs, up):
    by_slug = {v["slug"]: v for v in vendors}
    items = []
    for x in sorted(entries, key=lambda x: x["date"], reverse=True):
        name = x.get("vendor", "")
        link = f'<a href="../vendors/{x["slug"]}/">{e(name)}</a>' if x.get("slug") in by_slug else e(name)
        items.append(f'<li class="ln CHANGE"><time datetime="{e(x["date"])}">{e(x["date"])}</time><span class="tag">CHANGE</span>'
                     f'<span class="who">{link}</span><span class="fld">{e(x.get("field", ""))}</span><span class="msg">{e(x["summary"])}'
                     + (f' <a class="src" href="{e(x["source"])}" rel="nofollow noopener">source</a>' if x.get("source") else "")
                     + '</span></li>')
    confirmed = (f'<ol class="log">{"".join(items)}</ol>' if items else
                 '<p class="empty-note">0 entries in data/changelog.json. When a nightly diff turns into a confirmed change, '
                 'it lands here with the date, the tool and a link to the source. A raw page diff on its own is not enough.</p>')
    body = f"""<div class="head"><div><p class="eyebrow">changelog · events</p><h1>Policy changes and checker events</h1>
<p class="lede">Confirmed policy changes, nightly checker results, fetch errors and unverified fields, newest first. {full_check_sentence(st)} Baseline {st['baseline']}; {n_reports} diff report{'s' if n_reports != 1 else ''} on file.</p></div></div>
<div class="grid"><div class="c12">{panel("Confirmed policy changes", confirmed, meta=f"{len(entries)} entr{'y' if len(entries) == 1 else 'ies'}", pid="confirmed", bcls="pn-b flush")}</div></div>
<div class="grid">
<div class="c7" style="display:flex">{event_panel(evs, vendors, extra_meta=" " + full_check_sentence(st))}</div>
<div class="c5" style="display:flex">{uptime_panel(*up)}</div>
</div>"""
    return page(f"Changelog · {SITE_NAME}", body, "Confirmed changes to AI vendor data retention and training policies, plus nightly source-check results.", "/changelog/", active="changelog/")


def build_about(vendors, st):
    contact = f'<a href="{e(ISSUE_CHANGE)}" rel="noopener noreferrer">open a GitHub issue</a>'
    if CONTACT_URL:
        contact += f' or <a href="{e(CONTACT_URL)}">use this link</a>'
    rules = "".join(f"<tr><th scope='row'>{e(LABELS[k])}</th><td>{e(TONE_RULES[k])}</td></tr>" for k in FIELD_ORDER)
    shapes = {"ok": "filled circle", "mid": "triangle", "bad": "square", "unk": "hollow ring", "na": "dash"}
    leds = "".join(f"<tr><td>{led(t, 'big')}</td><th scope='row'>{TONE_LABEL[t]}</th><td>{shapes[t]}</td></tr>" for t in TONES)
    prose = f"""<h2>Where the data comes from</h2>
<p>Only the vendor's own pages: privacy policies, terms, trust and security pages, and product docs. No third-party blogs, no Reddit threads, no sales calls. Every field stores the URL, a short quote or paraphrase, and the date it was checked.</p>
<h2 id="unverified">What “unverified” means</h2>
<p>If an official page doesn't state something clearly, the field says {chip('unk', 'unverified')} with a note on what we looked at. We don't fill gaps with what a vendor is “known” to do. A blank is more useful in a security review than a confident wrong answer. Right now {st['unverified']} of {st['total_fields']} fields are unverified; each one is a WARN line in the <a href="../changelog/#events">event stream</a>.</p>
<h2>What's checked</h2>
<ul>
<li><strong>Trains by default</strong>: whether your inputs and outputs train models without you doing anything, and how to opt out.</li>
<li><strong>Default retention</strong>: how long prompts and outputs are kept if you change nothing.</li>
<li><strong>Zero data retention</strong>: whether it exists and how you get it (self-serve, by request, by approval).</li>
<li><strong>Abuse-monitoring exception</strong>: what can still be stored or human-reviewed when content is flagged, including under ZDR.</li>
<li><strong>Data residency</strong>: region options, with Singapore and APAC called out.</li>
<li><strong>SOC 2 / ISO 27001</strong>, <strong>HIPAA BAA</strong>, and <strong>self-host</strong> options.</li>
</ul>
<h2 id="colours">How statuses are assigned</h2>
<p>The status lights are a reading aid, not a score. They come from fixed rules applied to the value text at build time (see <code>scripts/derive.py</code>), so the same value always gets the same status. Each status has its own shape as well as its own colour, and the table and evidence log also spell it out in text. Read the quote before you rely on one.</p>
<div class="tablewrap"><table class="rules"><caption class="sr">Status lights</caption><thead><tr><th scope="col">Light</th><th scope="col">Status</th><th scope="col">Shape</th></tr></thead><tbody>{leds}</tbody></table></div>
<div class="tablewrap"><table class="rules"><caption class="sr">Rules per field</caption><thead><tr><th scope="col">Field</th><th scope="col">Rule</th></tr></thead><tbody>{rules}</tbody></table></div>
<p>Retention values are free text. To draw the retention chart, the build reads the numbers and units in the value (for example “14 days (base) / 180 days (extended)” becomes 14 to 180 days), treats “none by default”, “transient” or “not logged” as zero, and “until deleted” or “indefinite” as no limit. Values with no number, like “configurable”, are listed under the chart instead of drawn.</p>
<h2>How it stays current</h2>
<p>A script fetches every cited page nightly, strips it to the main text and diffs it against the last snapshot ({st['monitored_pages']} pages in the checker index at the last run, {st['monitor_last']}). A diff is a prompt to re-read the page, not an automatic update. Confirmed changes go in the <a href="../changelog/">changelog</a>.</p>
<h2>Where the event stream comes from</h2>
<p>Every line in the event stream is built from files in the repo: confirmed changes in <code>data/changelog.json</code> (CHANGE), checker runs and fetch failures in <code>snapshots/index.json</code> and its git history (INFO, ERROR), fields re-checked after the baseline (INFO), and unverified fields (WARN). The checker records dates, not times, so no times are shown. The per-tool source-check row shows one cell per run on record; nothing before the first run is filled in.</p>
<h2>Limits</h2>
<ul>
<li>Policies differ by plan. Where a tool has free, paid and enterprise tiers, the field says so.</li>
<li>Your signed contract, DPA or order form overrides any public page.</li>
<li>Some trust portals only render with JavaScript and couldn't be read; those fields stay unverified until there's a readable source.</li>
<li>This is not legal advice.</li>
</ul>
<h2 id="corrections">Corrections</h2>
<p>Corrections are welcome, especially from people who work at these vendors. Point to an official page that shows the right answer and the entry gets updated with the new source and date. To report one, {contact}. To ask for a tool that is not listed, <a href="{e(ISSUE_TOOL)}" rel="noopener noreferrer">suggest a tool</a>.</p>
<h2>Data</h2>
<p>{st['n']} tools, newest field check {e(st['checked'])}. Download the full dataset as <a href="../data.csv" download>CSV</a> or <a href="../data.json" download>JSON</a>.</p>
<p>This site counts visits with {ext_a("https://www.cloudflare.com/web-analytics/", "Cloudflare Web Analytics")}, which uses no cookies and does not track you across sites.</p>"""
    body = f"""<div class="head"><div><p class="eyebrow">method</p><h1>How this is sourced</h1>
<p class="lede">An independent tracker. No vendor pays for placement, reviews entries, or sees them before they're published. <a href="../funding/">How it is funded</a>.</p></div>{legend()}</div>
<div class="grid"><div class="c8">{panel("Method", prose, bcls="pn-b prose", pid="method")}</div>
<div class="c4"><div class="side">{panel("Field split", svg_field_bars(vendors), meta=f"{st['n']} tools", pid="split")}</div></div></div>"""
    return page(f"Method and sources · {SITE_NAME}", body,
                "How the AI data-policy tracker is sourced, what 'unverified' means, and how to send corrections.", "/about/", active="about/")


FUNDING_UPDATED = "2026-10-25"  # change when the sponsor log changes


def build_funding(vendors, st):
    rules = [
        ("Sponsors never touch the data.", "No sponsor, advertiser or affiliate partner can change, add, remove, delay or preview any value, status colour, changelog entry or newsletter item. Every value keeps its quote, source link and checked date."),
        ("Tracked vendors can't buy anything.", f"None of the {st['n']} tracked tools, and no company that owns one, can sponsor, advertise, buy a listing or be an affiliate link."),
        ("If a sponsor gets tracked, the sponsorship ends.", "If we add a sponsor's product to the tracker, or a tracked vendor buys the sponsor, we finish or refund the current booking and take no new ones. The new entry is researched like every other entry."),
        ("No paying to get in.", "Nobody can pay to be added to the tracker, to be reviewed faster, or to get a badge."),
        ("Paid things are labeled.", "Every paid spot says “Sponsored”. Every affiliate link says “Paid link” next to it and uses <code>rel=\"sponsored\"</code>. Paid spots never appear inside the tracker table."),
        ("One at a time.", "At most one sponsor per newsletter issue and one sponsor slot on the site."),
        ("No tracking.", "No tracking pixels and no ad scripts that follow readers. The subscriber list is never sold or shared."),
        ("Ads are checked.", "If an ad makes a claim about how the sponsor handles data, it must link to the sponsor's own policy page. We can refuse any ad."),
        ("Public log.", "Every sponsor and affiliate program is listed in the sponsor log with dates, and stays listed after it ends."),
    ]
    items = "".join(f"<li><strong>{t}</strong> {d}</li>" for t, d in rules)
    prose = f"""<h2 id="today">Money today: none</h2>
<p>There are no sponsors, no affiliate links and no paid listings. Nobody pays for this site. No vendor pays for placement, reviews entries, or sees them before they're published.</p>
<p>That may change one day. The site may later carry a sponsor or a few affiliate links. If it does, the rules below apply. They are written down now, before any money comes in, so you can hold us to them.</p>
<h2 id="rules">Rules for any future money</h2>
<ol>{items}</ol>
<h2 id="hosting">Hosting</h2>
<p>The site is hosted for free on GitHub Pages. GitHub is owned by Microsoft, and two Microsoft products, <a href="../vendors/github-copilot/">GitHub Copilot</a> and <a href="../vendors/azure-openai/">Azure OpenAI</a>, are tracked here. They are checked the same way as every other tool, and Microsoft has no say over any entry.</p>
<h2 id="problems">Found a problem?</h2>
<p>Every value links to its source. If an entry looks wrong, <a href="{e(ISSUE_CHANGE)}" rel="noopener noreferrer">open a GitHub issue</a>. If you think we broke one of these rules, or you have a question about sponsoring, <a href="{e(ISSUE_VENDOR)}" rel="noopener noreferrer">open a vendor or sponsor issue</a>.</p>"""
    log_rows = [("Current sponsors", "none"), ("Past sponsors", "none"), ("Affiliate programs", "none"), ("Paid listings", "none")]
    log = ("<div class=\"tablewrap\"><table class=\"rules\"><caption class=\"sr\">Sponsor log</caption><tbody>"
           + "".join(f"<tr><th scope='row'>{k}</th><td>{v}</td></tr>" for k, v in log_rows)
           + f"<tr><th scope='row'>Last updated</th><td><time datetime=\"{FUNDING_UPDATED}\">{FUNDING_UPDATED}</time></td></tr></tbody></table></div>")
    body = f"""<div class="head"><div><p class="eyebrow">funding</p><h1>Funding and independence</h1>
<p class="lede">Where Do My Prompts Go? is free to use, and the data is free to download and reuse. Here is how it is paid for, and the rules for any money in the future.</p></div></div>
<div class="grid"><div class="c8">{panel("Funding", prose, bcls="pn-b prose", pid="funding")}</div>
<div class="c4"><div class="side">{panel("Sponsor log", log, meta="0 sponsors", pid="log")}</div></div></div>"""
    return page(f"Funding and independence · {SITE_NAME}", body,
                "Who pays for this AI data-policy tracker (nobody yet), and the rules any future sponsor or affiliate link must follow.",
                "/funding/", active="funding/")  # not in the top nav; keeps Dashboard from showing as current


def build_llms(vendors, checked):
    """llms.txt (https://llmstxt.org): a plain-text map of the site for agents and LLM tools."""
    base = SITE_URL or ""
    u = lambda path: f"{base}{path}"
    total = len(vendors) * len(FIELD_ORDER)
    unver = sum(1 for v in vendors for k in FIELD_ORDER if v["fields"][k]["value"] == "unverified")
    lines = [f"# {SITE_NAME}", "",
             f"> A sourced tracker of how {len(vendors)} AI tools handle user data: training on your data, "
             "retention, zero data retention (ZDR), abuse-monitoring exceptions, data residency, "
             "SOC 2 / ISO 27001, HIPAA BAAs and self-host options. Every value links to the vendor's own page "
             f"with a quote and the date it was checked. Last full check: {checked}.", "",
             f"{total} fields in total ({len(vendors)} tools x {len(FIELD_ORDER)} fields). {unver} are marked "
             "\"unverified\": no official page stated it clearly, so there is no value. Policies differ by plan; "
             "a signed contract overrides public pages. This is not legal advice.", "",
             "## Data", "",
             f"- [data.json]({u('/data.json')}): full dataset. Each vendor has fields; each field has value, detail, quote, source (URL) and checked (date).",
             f"- [data.csv]({u('/data.csv')}): same data, one row per tool, five columns per field (value, detail, quote, source, checked).",
             "", "## Fields", ""]
    lines += [f"- {k}: {LABELS[k]}" for k in FIELD_ORDER]
    lines += ["", "## Pages", "",
              f"- [Dashboard]({u('/')}): status panels, policy event stream and comparison table of all tools",
              f"- [Method]({u('/about/')}): how values are sourced and what \"unverified\" means",
              f"- [Changelog]({u('/changelog/')}): confirmed policy changes, checker runs and fetch errors",
              f"- [Funding]({u('/funding/')}): who pays for the site (no one yet) and the rules for sponsors and affiliate links", "", "## Tools", ""]
    for v in vendors:
        f = v["fields"]
        lines.append(f"- [{v['name']}]({u('/vendors/' + v['slug'] + '/')}): {v['category']}; "
                     f"trains by default: {f['trains_by_default']['value']}; ZDR: {f['zdr']['value']}")
    return "\n".join(lines) + "\n"


def write_csv(vendors, path):
    cols = ["slug", "name", "category", "vendor", "region_filter"]
    for k in FIELD_ORDER:
        cols += [f"{k}", f"{k}_detail", f"{k}_quote", f"{k}_source", f"{k}_checked"]
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(cols)
        for v in vendors:
            row = [v["slug"], v["name"], v["category"], v["vendor"], v["region_filter"]]
            for k in FIELD_ORDER:
                x = v["fields"][k]
                row += [x["value"], x["detail"], x["quote"], x["source"], x["checked"]]
            w.writerow(row)


def main():
    global LABELS, HAVE_OG
    data, changelog, snapshots = load()
    LABELS = data["field_labels"]
    vendors = data["vendors"]
    raw_json = (ROOT / "data" / "vendors.json").read_bytes()
    enrich(vendors)
    versions = index_versions(snapshots)
    history = history_from(versions)
    latest_snaps = newest_entries(versions) or snapshots
    st = apply_latest_run(stats(vendors, snapshots), history)
    full_check = st["full_check"]
    up = uptime(vendors, latest_snaps, history)
    evs = events(vendors, changelog, latest_snaps, history, LABELS)
    STATUS.update({"checked_n": st["monitored_pages"], "errors": st["monitor_errors"], "last": full_check or "n/a",
                   "version": full_check or "n/a", "sha": hashlib.sha256(raw_json).hexdigest()[:8]})

    if OUT.exists():
        shutil.rmtree(OUT)
    shutil.copytree(ROOT / "site" / "assets", OUT / "assets")

    # data files first, so the home page can show their real sizes
    (OUT / "data.json").write_bytes(raw_json)
    write_csv(vendors, OUT / "data.csv")
    (OUT / "llms.txt").write_text(build_llms(vendors, full_check))
    files = {n: (OUT / n).stat().st_size for n in ("data.json", "data.csv", "llms.txt")}
    (OUT / "favicon.svg").write_text(FAVICON_SVG)

    try:
        import make_graphics
        make_graphics.render_all(vendors, st, OUT, SITE_URL, evs)
        HAVE_OG = True
    except ImportError as err:
        msg = f"PNG graphics skipped ({err}); pip install pillow to build og.png and favicon PNGs"
        if os.environ.get("REQUIRE_GRAPHICS"):
            sys.exit("error: " + msg)
        print("warning: " + msg)

    (OUT / "index.html").write_text(build_index(vendors, st, files, evs, up))
    for i, v in enumerate(vendors):
        d = OUT / "vendors" / v["slug"]
        d.mkdir(parents=True)
        (d / "index.html").write_text(build_vendor(v, vendors, i, latest_snaps, up[1][i]))
    n_reports = len(list((ROOT / "changes").glob("*.md"))) if (ROOT / "changes").exists() else 0
    (OUT / "changelog").mkdir()
    (OUT / "changelog" / "index.html").write_text(build_changelog(changelog, vendors, st, n_reports, evs, up))
    (OUT / "about").mkdir()
    (OUT / "about" / "index.html").write_text(build_about(vendors, st))
    (OUT / "funding").mkdir()
    (OUT / "funding" / "index.html").write_text(build_funding(vendors, st))
    # /method/ is the old path. Same depth as /about/, so the canonical path drives asset links.
    (OUT / "method").mkdir()
    (OUT / "method" / "index.html").write_text(page(
        f"Method · {SITE_NAME}",
        '<div class="head"><div><p class="eyebrow">redirect</p><h1>Method</h1>'
        '<p class="lede"><a href="{rel}about/">Continue to the method page</a>.</p></div></div>',
        "How the tracker is sourced.",
        "/about/",
        extra_head='<meta http-equiv="refresh" content="0; url=../about/">',
        active="about/"))
    home = (SITE_URL + "/") if SITE_URL else "/"
    nf_rel = (SITE_URL + "/") if SITE_URL else "/"
    (OUT / "404.html").write_text(page(f"Not found · {SITE_NAME}",
        f"<div class='head'><div><p class='eyebrow'>HTTP 404</p><h1>Not found</h1><p class='lede'>That page doesn't exist. <a href='{e(home)}'>Back to the dashboard</a>.</p></div></div>",
        "Page not found", "/404.html", rel=nf_rel))
    (OUT / "robots.txt").write_text("User-agent: *\nAllow: /\n" + (f"Sitemap: {SITE_URL}/sitemap.xml\n" if SITE_URL else ""))
    if SITE_URL:
        paths = ["/", "/changelog/", "/about/", "/method/", "/funding/"] + [f"/vendors/{v['slug']}/" for v in vendors]
        urls = "".join(f"<url><loc>{e(SITE_URL + p)}</loc><lastmod>{full_check}</lastmod></url>" for p in paths)
        (OUT / "sitemap.xml").write_text(f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>')
    print(f"Built {len(vendors)} vendor pages into {OUT.relative_to(ROOT)}/" + ("" if SITE_URL else " (set SITE_URL to emit canonical links and sitemap.xml)"))


if __name__ == "__main__":
    main()
