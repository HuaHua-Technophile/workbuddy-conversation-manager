"""Generate the README banner. Requires Pillow."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter

ROOT = Path(__file__).resolve().parent
W, H = 1280, 380
C1, C2 = (18, 62, 57), (8, 13, 23)

g = Image.new("RGB", (48, 48))
px = g.load()
for y in range(48):
    for x in range(48):
        t = (x + y) / 94.0
        px[x, y] = tuple(int(C1[i] + (C2[i] - C1[i]) * t) for i in range(3))
bg = g.resize((W, H), Image.Resampling.BICUBIC).convert("RGBA")

ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
od = ImageDraw.Draw(ov)
for x in range(0, W, 40):
    od.line([(x, 0), (x, H)], fill=(255, 255, 255, 10))
for y in range(0, H, 40):
    od.line([(0, y), (W, y)], fill=(255, 255, 255, 10))
bg = Image.alpha_composite(bg, ov)

rg = Image.radial_gradient("L").resize((1400, 1400), Image.Resampling.BILINEAR)
rg = Image.eval(rg, lambda v: int((255 - v) ** 2 / 255))
halo = Image.new("RGBA", (1400, 1400), (40, 210, 165, 0))
halo.putalpha(rg.point(lambda v: int(v * 0.30)))
bg.alpha_composite(halo, (600, -520))

cx, cy = 1192, 190
ring = Image.new("RGBA", (W, H), (0, 0, 0, 0))
rd = ImageDraw.Draw(ring)
for r, a in ((68, 96), (114, 70), (162, 50), (212, 32)):
    rd.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(128, 112, 245, a), width=2)
rd.ellipse([cx - 6, cy - 6, cx + 6, cy + 6], fill=(150, 134, 255, 160))
rd.line([(cx + 9, cy), (cx + 260, cy)], fill=(128, 112, 245, 42), width=1)
rd.line([(cx, cy - 9), (cx, cy - 300)], fill=(128, 112, 245, 30), width=1)
bg = Image.alpha_composite(bg, ring)

dots = Image.new("RGBA", (W, H), (0, 0, 0, 0))
dd = ImageDraw.Draw(dots)
for gy in range(56, 344, 26):
    for gx in range(985, 1272, 26):
        dist = ((gx - cx) ** 2 + (gy - cy) ** 2) ** 0.5
        if 228 < dist < 288:
            dd.ellipse([gx - 1.2, gy - 1.2, gx + 1.2, gy + 1.2], fill=(150, 134, 255, 58))
bg = Image.alpha_composite(bg, dots)

sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
ImageDraw.Draw(sh).rounded_rectangle([48, 58, 328, 338], 56, fill=(0, 0, 0, 140))
bg = Image.alpha_composite(bg, sh.filter(ImageFilter.GaussianBlur(22)))
ImageDraw.Draw(bg).rounded_rectangle([48, 50, 328, 330], 56, fill=(255, 255, 255, 255))

icon = Image.open(ROOT / "icon-512.png").convert("RGBA")
bg.alpha_composite(icon.resize((224, 224), Image.Resampling.LANCZOS), (76, 78))

line = Image.new("RGBA", (280, 5), (0, 0, 0, 0))
ld = ImageDraw.Draw(line)
for x in range(280):
    t = x / 279
    ld.line([(x, 0), (x, 4)], fill=(int(46 + (124 - 46) * t), int(210 + (108 - 210) * t), int(165 + (240 - 165) * t), 235))
bg.alpha_composite(line, (48, 346))

d = ImageDraw.Draw(bg)
F = lambda p, s: ImageFont.truetype(p, s)
f_label = F(r"C:\Windows\Fonts\segoeuib.ttf", 21)
f_title = F(r"C:\Windows\Fonts\segoeuib.ttf", 46)
f_sub = F(r"C:\Windows\Fonts\segoeui.ttf", 24)
f_tag = F(r"C:\Windows\Fonts\msyh.ttc", 19)
X = 380

def spaced(draw, pos, text, font, fill, gap=3):
    x, y = pos
    for ch in text:
        draw.text((x, y), ch, font=font, fill=fill)
        x += draw.textlength(ch, font=font) + gap

spaced(d, (X, 82), "AGENT SKILL", f_label, (74, 232, 183))
d.text((X, 114), "WorkBuddy Task Manager", font=f_title, fill=(255, 255, 255))
d.text((X, 196), "Local task & group management for WorkBuddy", font=f_sub, fill=(160, 169, 195))
d.text((X, 232), "rename · migrate · backup · rollback", font=f_sub, fill=(160, 169, 195))

tags = ["两步式重命名", "任务 / 分组迁移", "按对象备份"]
ty, th, pad, gapx = 292, 40, 22, 12
tx = X
for t in tags:
    bw = d.textlength(t, font=f_tag) + pad * 2
    d.rounded_rectangle([tx, ty, tx + bw, ty + th], radius=20, outline=(74, 138, 118), width=1)
    d.text((tx + pad, ty + (th - 26) / 2 - 1), t, font=f_tag, fill=(206, 240, 227))
    tx += bw + gapx

out = ROOT / "banner-1280-pil.png"
bg.convert("RGB").save(out, "PNG", optimize=True)
print("saved", out, out.stat().st_size, "bytes", bg.size)
