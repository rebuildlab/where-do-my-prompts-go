#!/usr/bin/env python3
"""PNG graphics generated from data/vendors.json: social cards and favicon PNGs.

Called by build.py when Pillow is installed; can also run on its own:
  python3 scripts/make_graphics.py            # writes into public/
Outputs: og.png (1200x630, home), og/<slug>.png (one per tool), favicon.ico, apple-touch-icon.png.
Fonts: IBM Plex Mono (SIL OFL 1.1), bundled in scripts/fonts/.
"""
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive import FIELD_ORDER, SHORT, REGION_LABEL, load, enrich, stats

FONTS = Path(__file__).resolve().parent / "fonts"
W, H = 1200, 630
BG, PANEL, LINE = "#0a0c0f", "#10141a", "#2a323d"
FG, MUTED, DIM = "#d9dee5", "#8d97a5", "#6b7480"
TONE_FILL = {"ok": "#2ea043", "mid": "#c99a2e", "bad": "#e5534b", "unk": "#6b7480", "na": "#2b323c"}
TONE_TEXT = {"ok": "#5fd37a", "mid": "#e8b84a", "bad": "#ff8077", "unk": "#a9b1bc", "na": "#8d97a5"}


def font(size, weight="Regular"):
    return ImageFont.truetype(str(FONTS / f"IBMPlexMono-{weight}.ttf"), size)


def fit(draw, text, f, maxw):
    if draw.textlength(text, font=f) <= maxw:
        return text
    while text and draw.textlength(text + "…", font=f) > maxw:
        text = text[:-1]
    return text.rstrip(" ,;(") + "…"


def wrap(draw, text, f, maxw, max_lines=2):
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if draw.textlength(t, font=f) <= maxw:
            cur = t
        else:
            lines.append(cur); cur = w
    lines.append(cur)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = fit(draw, lines[-1] + " …", f, maxw)
    return lines


def led(d, t, cx, cy, r=7):
    """Status light with its own shape, matching the site: circle, triangle, square, ring, dash."""
    c = TONE_FILL[t] if t != "na" else DIM
    if t == "ok":
        d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=c)
    elif t == "mid":
        d.polygon([(cx, cy - r), (cx + r, cy + r), (cx - r, cy + r)], fill=c)
    elif t == "bad":
        d.rectangle((cx - r + 1, cy - r + 1, cx + r - 1, cy + r - 1), fill=c)
    elif t == "unk":
        d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=c, width=3)
    else:
        d.line((cx - r, cy, cx + r, cy), fill=c, width=3)


def panel(d, box, title, meta=""):
    x0, y0, x1, y1 = box
    d.rectangle(box, fill=PANEL, outline=LINE, width=1)
    d.line((x0, y0 + 30, x1, y0 + 30), fill=LINE, width=1)
    d.text((x0 + 12, y0 + 9), title.upper(), font=font(13, "SemiBold"), fill=MUTED)
    if meta:
        d.text((x1 - 12, y0 + 9), meta, font=font(13), fill=DIM, anchor="ra")


def frame(site_url, st, right):
    """Top bar + status line like the site header; all numbers from the data and checker index."""
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    d.rectangle((0, 0, W, 50), fill=BG)
    d.line((0, 50, W, 50), fill=LINE)
    d.text((24, 15), "wdmpg", font=font(20, "SemiBold"), fill=FG)
    d.text((104, 17), "Where Do My Prompts Go?", font=font(17), fill=MUTED)
    d.text((W - 24, 17), right, font=font(15), fill=DIM, anchor="ra")
    err = st["monitor_errors"]
    pill = f"{st['monitored_pages']} sources checked · {err} fetch error{'s' if err != 1 else ''}"
    pw = d.textlength(pill, font=font(14)) + 44
    d.rounded_rectangle((24, 60, 24 + pw, 86), radius=13, fill=PANEL, outline=TONE_FILL["mid" if err else "ok"])
    led(d, "mid" if err else "ok", 40, 73, 6)
    d.text((54, 64), pill, font=font(14), fill=FG)
    d.text((40 + pw, 64), f"last check {st['monitor_last']}", font=font(14), fill=MUTED)
    d.line((0, 96, W, 96), fill=LINE)
    foot = (site_url.split("://", 1)[-1] if site_url else "every value cites the vendor's own policy page")
    d.text((W - 24, H - 30), foot, font=font(15), fill=DIM, anchor="ra")
    return im, d


def og_home(vendors, st, path, site_url, evs=None):
    im, d = frame(site_url, st, f"newest field check {st['checked']}")
    d.text((24, 110), "What happens to your prompts", font=font(40, "Bold"), fill=FG)
    stats_ = [("trains: no", f"{st['trains_no']}/{st['n']}", "ok"),
              ("zdr offered", f"{st['zdr_available']}/{st['zdr_applicable']}", "ok"),
              ("keep nothing", f"{len(st['zero_retention'])}/{st['n']}", "mid"),
              ("unverified", f"{st['unverified']}/{st['total_fields']}", "unk")]
    pw = 168
    for i, (lab, num, t) in enumerate(stats_):
        x = 24 + i * (pw + 10)
        panel(d, (x, 176, x + pw, 276), lab)
        led(d, t, x + 20, 236, 7)
        d.text((x + 36, 220), num, font=font(30, "Bold"), fill=FG)
    # event stream: newest real events only (no invented lines)
    panel(d, (24, 290, 726, 590), "policy event stream", f"{len(evs or [])} events")
    sev_col = {"INFO": "#79b8ff", "WARN": TONE_FILL["mid"], "ERROR": "#ff8077", "CHANGE": "#c8a2ff"}
    y = 330
    for x in (evs or [])[:8]:
        d.text((36, y), x["date"], font=font(14), fill=DIM)
        d.text((136, y), x["sev"], font=font(14, "SemiBold"), fill=sev_col[x["sev"]])
        d.text((206, y), fit(d, x["vendor"], font(14), 120), font=font(14), fill=FG)
        d.text((336, y), fit(d, x["field"] + "  " + x["msg"], font(14), 378), font=font(14), fill=MUTED)
        y += 31
    # heatmap: 25 tools x 8 fields, straight from the data
    panel(d, (740, 110, W - 24, 590), "field status", f"{st['n']} × {len(FIELD_ORDER)}")
    x0, y0, cw, ch, gap = 760, 152, 44, 12, 3
    for r, v in enumerate(vendors):
        for c, k in enumerate(FIELD_ORDER):
            t = v["fields"][k]["_tone"]
            xx, yy = x0 + c * (cw + gap), y0 + r * (ch + gap)
            d.rectangle((xx, yy, xx + cw, yy + ch), fill=TONE_FILL[t])
    lx, ly = 760, y0 + len(vendors) * (ch + gap) + 10
    for t, lab in (("ok", "ok"), ("mid", "caution"), ("bad", "bad"), ("unk", "unverif."), ("na", "n/a")):
        led(d, t, lx + 6, ly + 8, 6)
        d.text((lx + 16, ly), lab, font=font(13), fill=MUTED)
        lx += 22 + d.textlength(lab, font=font(13)) + 10
    im.save(path, optimize=True)


def og_tool(v, path, site_url, st=None):
    f = v["fields"]
    checked = max(x["checked"] for x in f.values())
    im, d = frame(site_url, st, f"checked {checked}")
    d.text((24, 108), f"service {v['slug']} · vendor {v['vendor']} · {v['category']}", font=font(16), fill=MUTED)
    noun = "your code" if v["category"] == "Coding tools" else "your data"
    tf = font(40, "Bold")
    y = 134
    lines = wrap(d, f"Does {v['name']} train on {noun}?", tf, W - 48)
    for line in lines:
        d.text((24, y), line, font=tf, fill=FG)
        y += 50
    y = max(y + 16, 250)
    cols, gap = 4, 10
    pw = (W - 48 - gap * (cols - 1)) // cols
    ph = (H - 60 - y - gap) // 2
    for i, k in enumerate(FIELD_ORDER):
        col, row = i % cols, i // cols
        x, yy = 24 + col * (pw + gap), y + row * (ph + gap)
        t = f[k]["_tone"]
        d.rectangle((x, yy, x + pw, yy + ph), fill=PANEL, outline=LINE)
        d.line((x, yy, x + pw, yy), fill=TONE_FILL[t] if t != "na" else LINE, width=3)
        led(d, t, x + 18, yy + 24, 6)
        d.text((x + 32, yy + 15), SHORT[k].upper(), font=font(14, "SemiBold"), fill=MUTED)
        val = REGION_LABEL[v["region_filter"]] if k == "residency" else f[k]["value"]
        for j, line in enumerate(wrap(d, val, font(20, "SemiBold"), pw - 28, 3)):
            d.text((x + 14, yy + 46 + j * 26), line, font=font(20, "SemiBold"), fill=TONE_TEXT[t] if t != "na" else FG)
    im.save(path, optimize=True)


def icons(out):
    """Favicon PNG/ICO drawn to match favicon.svg (dark tile, caret, three status cells)."""
    S = 256
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    k = S / 32
    d.rounded_rectangle((0, 0, S - 1, S - 1), radius=int(5 * k), fill=PANEL, outline="#323b47", width=int(k))
    d.line([(8 * k, 8.5 * k), (15 * k, 14 * k), (8 * k, 19.5 * k)], fill=FG, width=int(3 * k), joint="curve")
    for cx, cy in ((8 * k, 8.5 * k), (8 * k, 19.5 * k), (15 * k, 14 * k)):
        r = 1.5 * k
        d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=FG)
    d.rounded_rectangle((17.5 * k, 17.5 * k, 24.5 * k, 20.5 * k), radius=int(1.5 * k), fill=FG)
    for x, c in ((8, TONE_FILL["ok"]), (14, TONE_FILL["mid"]), (20, TONE_FILL["bad"])):
        d.rounded_rectangle((x * k, 23.5 * k, (x + 5) * k, 26.5 * k), radius=int(k), fill=c)
    im.save(out / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)])
    bg = Image.new("RGBA", (180, 180), PANEL)
    bg.alpha_composite(im.resize((180, 180), Image.LANCZOS))
    bg.convert("RGB").save(out / "apple-touch-icon.png", optimize=True)


def render_all(vendors, st, out, site_url="", evs=None):
    out = Path(out)
    (out / "og").mkdir(parents=True, exist_ok=True)
    og_home(vendors, st, out / "og.png", site_url, evs)
    for v in vendors:
        og_tool(v, out / "og" / f"{v['slug']}.png", site_url, st)
    icons(out)


if __name__ == "__main__":
    import os
    from derive import check_history, events
    data, chl, snaps = load()
    vs = enrich(data["vendors"])
    evs = events(vs, chl, snaps, check_history(snaps), data["field_labels"])
    render_all(vs, stats(vs, snaps), Path(__file__).resolve().parent.parent / "public", os.environ.get("SITE_URL", ""), evs)
    print("graphics written to public/")
