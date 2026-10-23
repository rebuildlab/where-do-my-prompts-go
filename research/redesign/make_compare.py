"""Side-by-side before/after of the home page: desktop first screen on top, mobile below."""
import sys
from pathlib import Path
# usage: make_compare.py [A_prefix B_prefix out.png "A label" "B label"]
#   default: before after compare_home.png BEFORE AFTER
#   ops:     after after_ops compare_ops_home.png REDESIGN OPS
A, B, OUTN, LA, LB = (sys.argv[1:6] if len(sys.argv) >= 6 else ("before", "after", "compare_home.png", "BEFORE", "AFTER"))
from PIL import Image, ImageDraw, ImageFont
D = Path(__file__).resolve().parent
F = Path(__file__).resolve().parents[2] / "scripts" / "fonts"
font = ImageFont.truetype(str(F / "IBMPlexMono-SemiBold.ttf"), 26)
small = ImageFont.truetype(str(F / "IBMPlexMono-Regular.ttf"), 20)

def first(name, h):
    im = Image.open(D / name).convert("RGB")
    return im.crop((0, 0, im.width, min(h, im.height)))

dw = 1000
db, da = [first(n, 1000).resize((dw, round(1000 * dw / 1440))) for n in (f"{A}_home_desktop.png", f"{B}_home_desktop.png")]
mw = 390
mb, ma = [first(n, 1688 * 2).resize((mw, round(1688 * 2 * mw / 780))) for n in (f"{A}_home_mobile.png", f"{B}_home_mobile.png")]
pad, lab = 40, 56
W = pad * 3 + dw * 2
H = pad + lab + db.height + pad + lab + mb.height + pad + 40
out = Image.new("RGB", (W, H), "#14161a")
d = ImageDraw.Draw(out)
for i, (img, t) in enumerate(((db, LA), (da, LB))):
    x = pad + i * (dw + pad)
    d.text((x, pad), f"{t} · home · desktop 1440px", font=font, fill="#f2f1ec" if i else "#9aa1ad")
    out.paste(img, (x, pad + lab)); d.rectangle((x - 1, pad + lab - 1, x + dw, pad + lab + img.height), outline="#2f343c")
y2 = pad + lab + db.height + pad
for i, (img, t) in enumerate(((mb, LA), (ma, LB))):
    x = pad + i * (dw + pad) + (dw - mw) // 2
    d.text((pad + i * (dw + pad), y2), f"{t} · home · mobile 390px", font=font, fill="#f2f1ec" if i else "#9aa1ad")
    out.paste(img, (x, y2 + lab)); d.rectangle((x - 1, y2 + lab - 1, x + mw, y2 + lab + img.height), outline="#2f343c")
d.text((W - pad, H - 24), "Where Do My Prompts Go? · real screenshots of the local build", font=small, fill="#5d6470", anchor="rs")
out.save(D / OUTN, optimize=True)
print(out.size)
