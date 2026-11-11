"""Genera img/og-default.jpg (1200x630), imagen estándar para compartir en redes."""
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import os
W, H = 1200, 630
root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
F = 'C:/Windows/Fonts/'
RED, GOLD = (177, 43, 40), (227, 171, 55)

# fondo: degradado diagonal negro -> marrón muy oscuro
bg = Image.new('RGB', (W, H))
px = bg.load()
for y in range(H):
    for x in range(W):
        t = (x / W * 0.6 + y / H * 0.4)
        px[x, y] = (int(10 + 24 * t), int(9 + 15 * t), int(8 + 10 * t))
# resplandor dorado y rojo suaves
glow = Image.new('RGB', (W, H), (0, 0, 0))
g = ImageDraw.Draw(glow)
g.ellipse((700, -250, 1450, 400), fill=(70, 50, 16))
g.ellipse((-300, 400, 400, 900), fill=(60, 14, 13))
glow = glow.filter(ImageFilter.GaussianBlur(120))
from PIL import ImageChops
bg = ImageChops.add(bg, glow)
d = ImageDraw.Draw(bg)

# marco fino dorado
d.rectangle((36, 36, W - 37, H - 37), outline=(227, 171, 55), width=1)
# barra roja lateral
d.rectangle((36, 36, 44, H - 37), fill=RED)

# logo
logo = Image.open(os.path.join(root, 'img/logo_mi_inverso_transparent.png')).convert('RGBA')
lh = 150
logo = logo.resize((int(logo.width * lh / logo.height), lh), Image.LANCZOS)
bg.paste(logo, (100, 92), logo)

def spaced(text, xy, font, fill, sp):
    x, y = xy
    for ch in text:
        d.text((x, y), ch, font=font, fill=fill)
        x += d.textlength(ch, font=font) + sp
    return x

kick = ImageFont.truetype(F + 'segoeuib.ttf', 22)
spaced('PORSCHE  ·  LUJO  ·  ESPAÑA', (100, 290), kick, GOLD, 5)

title = ImageFont.truetype(F + 'georgiab.ttf', 96)
d.text((98, 335), 'Mejor Imposible', font=title, fill=(247, 243, 236))

d.line((100, 470, 220, 470), fill=GOLD, width=3)
sub = ImageFont.truetype(F + 'georgia.ttf', 33)
d.text((100, 490), 'Solo lo mejor de España, con datos y sin ruido.', font=sub, fill=(214, 205, 190))

url = ImageFont.truetype(F + 'segoeui.ttf', 24)
d.text((100, 556), 'mejorimposible.es', font=url, fill=(150, 142, 128))

out = os.path.join(root, 'img/og-default.jpg')
bg.save(out, 'JPEG', quality=90, optimize=True, progressive=True)
print(out, os.path.getsize(out))
