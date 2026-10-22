#!/usr/bin/env python3
"""Build the static site into public/ from data/vendors.json.

  python3 scripts/build.py
  SITE_URL=https://your-domain.example python3 scripts/build.py   # adds canonical URLs + sitemap

No dependencies beyond the Python standard library.
"""
import csv, html, json, os, shutil
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "public"
SITE_NAME = "Where Do My Prompts Go?"
SITE_URL = os.environ.get("SITE_URL", "").rstrip("/")
CONTACT_URL = os.environ.get("CONTACT_URL", "")  # e.g. a form or mailto: link; empty = "coming soon"


def site_path_prefix():
    """Path under the host, e.g. /where-do-my-prompts-go. Empty when the site is at the domain root."""
    if not SITE_URL:
        return ""
    return urlparse(SITE_URL).path.rstrip("/")


FIELD_ORDER = ["trains_by_default", "retention", "zdr", "abuse_monitoring",
               "residency", "certifications", "hipaa_baa", "self_host"]
REGION_LABEL = {"sg": "Singapore option", "apac": "APAC, not Singapore",
                "none": "No APAC option", "unverified": "Unverified"}
e = html.escape


def trains_key(v):
    s = v.lower()
    for k in ("unverified", "depends", "yes", "no"):
        if s.startswith(k):
            return k
    return "depends"


def zdr_key(v):
    s = v.lower()
    if s.startswith("unverified"): return "unverified"
    if s.startswith("n/a"): return "n/a"
    if s.startswith("no"): return "not offered"
    if s.startswith("partial"): return "partial"
    return "available"


def tone(field, value):
    s = value.lower()
    if s.startswith("unverified"): return "unk"
    if field == "trains_by_default":
        return {"no": "ok", "yes": "bad"}.get(trains_key(value), "mid")
    if field == "zdr":
        return {"available": "ok", "not offered": "bad", "partial": "mid"}.get(zdr_key(value), "")
    return ""


def page(title, body, desc, path, extra_head="", rel=None):
    canonical = f'<link rel="canonical" href="{e(SITE_URL + path)}">' if SITE_URL else ""
    depth = path.strip("/").count("/") + (1 if path.strip("/") else 0)
    rel = rel or ("../" * depth or "./")
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(title)}</title>
<meta name="description" content="{e(desc)}">
<meta property="og:title" content="{e(title)}">
<meta property="og:description" content="{e(desc)}">
<meta property="og:type" content="website">
<meta name="twitter:card" content="summary">
{canonical}
<link rel="stylesheet" href="{rel}assets/style.css">
{extra_head}
</head>
<body>
<header class="top"><div class="wrap">
<a class="brand" href="{rel}">Where Do My Prompts Go?</a>
<nav><a href="{rel}">Tracker</a><a href="{rel}changelog/">Changelog</a><a href="{rel}about/">Method</a><a href="{rel}data.csv" download>CSV</a><a href="{rel}data.json" download>JSON</a></nav>
</div></header>
<main class="wrap">
{body}
</main>
<footer class="wrap foot">
<p>Independent. Every claim links to the vendor's own page. Not legal advice; check the source and your contract before you sign anything.</p>
</footer>
</body>
</html>
"""


def signup_box():
    return """<section class="signup" aria-labelledby="signup-h">
<h2 id="signup-h">Get an email when a policy changes</h2>
<p>A nightly job diffs every source page. Sign-ups aren't live yet, so nothing you type here is sent anywhere.</p>
<form class="signup-form" onsubmit="event.preventDefault(); this.querySelector('.signup-note').hidden=false;">
<label class="sr" for="email">Email</label>
<input id="email" type="email" placeholder="you@company.com" autocomplete="email">
<button type="submit">Notify me</button>
<p class="signup-note" hidden>Not wired up yet. Nothing was sent or stored.</p>
</form>
</section>"""


def build_index(vendors, checked):
    rows = []
    for v in vendors:
        f = v["fields"]
        def cell(k):
            val = f[k]["value"]
            return f'<td data-label="{e(LABELS[k])}"><span class="v {tone(k, val)}">{e(val)}</span></td>'
        rows.append(
            f'<tr data-cat="{e(v["category"])}" data-trains="{trains_key(f["trains_by_default"]["value"])}" '
            f'data-zdr="{zdr_key(f["zdr"]["value"])}" data-region="{e(v["region_filter"])}" '
            f'data-search="{e((v["name"] + " " + v["vendor"] + " " + v["category"]).lower())}">'
            f'<th scope="row"><a href="vendors/{v["slug"]}/">{e(v["name"])}</a><small>{e(v["category"])}</small></th>'
            + cell("trains_by_default") + cell("retention") + cell("zdr")
            + f'<td data-label="APAC region"><span class="v">{e(REGION_LABEL[v["region_filter"]])}</span></td>'
            + cell("certifications") + cell("hipaa_baa") + cell("self_host") + "</tr>")
    cats = sorted({v["category"] for v in vendors}, key=lambda c: [x["category"] for x in vendors].index(c))
    opt = lambda vals: "".join(f'<option value="{e(a)}">{e(b)}</option>' for a, b in vals)
    body = f"""
<section class="intro">
<h1>What happens to your prompts after you hit enter</h1>
<p class="lede">Training defaults, retention, zero-data-retention, abuse-monitoring carve-outs, regions, certifications and BAAs for {len(vendors)} AI tools. Each cell links back to the vendor's own policy page with a quote and the date it was checked. Use it to get through security, legal or procurement review faster.</p>
<p class="meta">Last full check: {e(checked)} · <a href="data.csv" download>Download CSV</a> · <a href="data.json" download>JSON</a></p>
</section>
<section class="filters" aria-label="Filters">
<input id="q" type="search" placeholder="Search tools…" aria-label="Search tools">
<select id="f-cat" aria-label="Category"><option value="">All categories</option>{opt((c, c) for c in cats)}</select>
<select id="f-trains" aria-label="Trains by default"><option value="">Trains by default: any</option>{opt([("no","No"),("yes","Yes"),("depends","Depends on plan"),("unverified","Unverified")])}</select>
<select id="f-zdr" aria-label="Zero data retention"><option value="">ZDR: any</option>{opt([("available","Available"),("partial","Partial"),("not offered","Not offered"),("n/a","N/A (observability)"),("unverified","Unverified")])}</select>
<select id="f-region" aria-label="Region"><option value="">Region: any</option>{opt(REGION_LABEL.items())}</select>
<span id="count" class="count" aria-live="polite"></span>
</section>
<div class="tablewrap">
<table id="t">
<thead><tr><th scope="col">Tool</th><th scope="col">Trains by default</th><th scope="col">Default retention</th><th scope="col">ZDR</th><th scope="col">APAC region</th><th scope="col">SOC 2 / ISO 27001</th><th scope="col">HIPAA BAA</th><th scope="col">Self-host</th></tr></thead>
<tbody>
{''.join(rows)}
</tbody>
</table>
</div>
<p class="legend"><span class="v ok">green</span> = favourable default · <span class="v bad">red</span> = trains by default / no ZDR · <span class="v unk">unverified</span> = we couldn't confirm it from an official page, so we don't guess.</p>
{signup_box()}
<script src="assets/app.js" defer></script>
"""
    desc = f"Sourced comparison of how {len(vendors)} AI tools handle your data: training defaults, retention, ZDR, regions, SOC 2, HIPAA BAA. Checked {checked}."
    return page(f"{SITE_NAME} AI data retention and training tracker", body, desc, "/")


def build_vendor(v):
    f = v["fields"]
    noun = "your code" if v["category"] == "Coding tools" else "your data"
    checked = max(x["checked"] for x in f.values())
    title = f"Does {v['name']} train on {noun}? Data retention and privacy (checked {checked})"
    tr = f["trains_by_default"]
    answer = f"{tr['value'].capitalize()}. {tr['detail']}".strip()
    blocks = []
    for k in FIELD_ORDER:
        x = f[k]
        src = (f'<a href="{e(x["source"])}" rel="nofollow noopener" target="_blank">{e(x["source"])}</a>'
               if x["source"] else "none")
        quote = f'<blockquote>“{e(x["quote"])}”</blockquote>' if x["quote"] else ""
        blocks.append(f"""<section class="field" id="{k}">
<h2>{e(LABELS[k])}</h2>
<p class="answer"><span class="v {tone(k, x['value'])}">{e(x['value'])}</span></p>
{f'<p>{e(x["detail"])}</p>' if x['detail'] else ''}
{quote}
<p class="src">Source: {src} · checked {e(x['checked'])}</p>
</section>""")
    unver = sum(1 for x in f.values() if x["value"] == "unverified")
    faq = {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
        {"@type": "Question", "name": f"Does {v['name']} train on {noun}?",
         "acceptedAnswer": {"@type": "Answer", "text": answer}},
        {"@type": "Question", "name": f"How long does {v['name']} retain prompts?",
         "acceptedAnswer": {"@type": "Answer", "text": f"{f['retention']['value']}. {f['retention']['detail']}".strip()}}]}
    head = f'<script type="application/ld+json">{json.dumps(faq, ensure_ascii=False)}</script>'
    body = f"""
<p class="crumb"><a href="../../">Tracker</a> / {e(v['category'])}</p>
<h1>Does {e(v['name'])} train on {noun}?</h1>
<p class="lede"><strong>Short answer:</strong> {e(answer)}</p>
<p class="meta">Vendor: {e(v['vendor'])} · Checked {e(checked)} · {unver} of {len(FIELD_ORDER)} fields unverified</p>
{f'<p class="note"><strong>Note:</strong> {e(v["notes"])}</p>' if v.get("notes") else ""}
<nav class="toc">{''.join(f'<a href="#{k}">{e(LABELS[k])}</a>' for k in FIELD_ORDER)}</nav>
{''.join(blocks)}
<p class="fix">Spotted something wrong or out of date? Corrections are welcome; see <a href="../../about/">how to send one</a>.</p>
{signup_box()}
"""
    desc = f"{v['name']}: {tr['value']} on training by default; retention {f['retention']['value']}; ZDR {f['zdr']['value']}. Sourced from official pages, checked {checked}."
    return page(title, body, desc[:300], f"/vendors/{v['slug']}/", head)


def build_changelog(entries):
    if entries:
        items = "".join(f"<li><time>{e(x['date'])}</time> <strong>{e(x['vendor'])}</strong>: {e(x['summary'])}"
                        f"{' (<a href=\"' + e(x['source']) + '\">source</a>)' if x.get('source') else ''}</li>" for x in entries)
        lst = f"<ol class='changes'>{items}</ol>"
    else:
        lst = "<p class='empty'>No changes recorded yet. The first baseline was taken on the date shown on the tracker; this page will list policy changes as they're confirmed.</p>"
    body = f"""<h1>Changelog</h1>
<p class="lede">Confirmed changes to vendor data policies, newest first. Each entry is checked by hand against the vendor's page before it goes here, so a raw page diff on its own isn't enough to get listed.</p>
{lst}
{signup_box()}"""
    return page(f"Changelog · {SITE_NAME}", body, "Confirmed changes to AI vendor data retention and training policies.", "/changelog/")


def build_about(n, checked):
    contact = (f'<a href="{e(CONTACT_URL)}">send a correction</a>' if CONTACT_URL
               else "use the correction link (it goes live with the site)")
    body = f"""<h1>Method</h1>
<p class="lede">This is an independent tracker. No vendor pays for placement, reviews entries, or sees them before they're published.</p>
<h2>Where the data comes from</h2>
<p>Only the vendor's own pages: privacy policies, terms, trust and security pages, and product docs. No third-party blogs, no Reddit threads, no sales calls. Every field stores the URL, a short quote or paraphrase, and the date it was checked.</p>
<h2>What “unverified” means</h2>
<p>If an official page doesn't state something clearly, the field says <span class="v unk">unverified</span> with a note on what we looked at. We don't fill gaps with what a vendor is “known” to do. A blank is more useful in a security review than a confident wrong answer.</p>
<h2>What's checked</h2>
<ul>
<li><strong>Trains by default</strong>: whether your inputs and outputs train models without you doing anything, and how to opt out.</li>
<li><strong>Default retention</strong>: how long prompts and outputs are kept if you change nothing.</li>
<li><strong>Zero data retention</strong>: whether it exists and how you get it (self-serve, by request, by approval).</li>
<li><strong>Abuse-monitoring exception</strong>: what can still be stored or human-reviewed when content is flagged, including under ZDR.</li>
<li><strong>Data residency</strong>: region options, with Singapore and APAC called out.</li>
<li><strong>SOC 2 / ISO 27001</strong>, <strong>HIPAA BAA</strong>, and <strong>self-host</strong> options.</li>
</ul>
<h2>How it stays current</h2>
<p>A script fetches every cited page nightly, strips it to the main text and diffs it against the last snapshot. A diff is a prompt to re-read the page, not an automatic update. Confirmed changes go in the <a href="../changelog/">changelog</a>.</p>
<h2>Limits</h2>
<ul>
<li>Policies differ by plan. Where a tool has free, paid and enterprise tiers, the field says so.</li>
<li>Your signed contract, DPA or order form overrides any public page.</li>
<li>Some trust portals only render with JavaScript and couldn't be read; those fields stay unverified until there's a readable source.</li>
<li>This is not legal advice.</li>
</ul>
<h2>Corrections</h2>
<p>Corrections are welcome, especially from people who work at these vendors. Point to an official page that shows the right answer and the entry gets updated with the new source and date. To report one, {contact}.</p>
<h2>Data</h2>
<p>{n} tools, last checked {e(checked)}. Download the full dataset as <a href="../data.csv" download>CSV</a> or <a href="../data.json" download>JSON</a>.</p>
"""
    return page(f"Method and sources · {SITE_NAME}", body,
                "How the AI data-policy tracker is sourced, what 'unverified' means, and how to send corrections.", "/about/")


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
              f"- [Tracker]({u('/')}): comparison table of all tools",
              f"- [Method]({u('/about/')}): how values are sourced and what \"unverified\" means",
              f"- [Changelog]({u('/changelog/')}): confirmed policy changes", "", "## Tools", ""]
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
    global LABELS
    data = json.loads((ROOT / "data" / "vendors.json").read_text())
    LABELS = data["field_labels"]
    vendors = data["vendors"]
    changelog = json.loads((ROOT / "data" / "changelog.json").read_text())["entries"]
    checked = max(x["checked"] for v in vendors for x in v["fields"].values())

    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "assets").mkdir(parents=True)
    for a in (ROOT / "site" / "assets").iterdir():
        shutil.copy(a, OUT / "assets" / a.name)

    (OUT / "index.html").write_text(build_index(vendors, checked))
    for v in vendors:
        d = OUT / "vendors" / v["slug"]
        d.mkdir(parents=True)
        (d / "index.html").write_text(build_vendor(v))
    (OUT / "changelog").mkdir()
    (OUT / "changelog" / "index.html").write_text(build_changelog(changelog))
    (OUT / "about").mkdir()
    (OUT / "about" / "index.html").write_text(build_about(len(vendors), checked))
    # 404.html is served for any missing URL, so relative links would resolve against
    # the broken path. Root-absolute links must keep the project subpath.
    not_found_root = f"{site_path_prefix()}/" if site_path_prefix() else "/"
    (OUT / "404.html").write_text(page(
        f"Not found · {SITE_NAME}",
        f"<h1>Not found</h1><p><a href='{e(not_found_root)}'>Back to the tracker</a></p>",
        "Page not found", "/", rel=not_found_root))
    shutil.copy(ROOT / "data" / "vendors.json", OUT / "data.json")
    write_csv(vendors, OUT / "data.csv")
    (OUT / "llms.txt").write_text(build_llms(vendors, checked))
    (OUT / "robots.txt").write_text("User-agent: *\nAllow: /\n" + (f"Sitemap: {SITE_URL}/sitemap.xml\n" if SITE_URL else ""))
    if SITE_URL:
        paths = ["/", "/changelog/", "/about/"] + [f"/vendors/{v['slug']}/" for v in vendors]
        urls = "".join(f"<url><loc>{e(SITE_URL + p)}</loc><lastmod>{checked}</lastmod></url>" for p in paths)
        (OUT / "sitemap.xml").write_text(f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>')
    print(f"Built {len(vendors)} vendor pages into {OUT.relative_to(ROOT)}/" + ("" if SITE_URL else " (set SITE_URL to emit canonical links and sitemap.xml)"))


if __name__ == "__main__":
    main()
