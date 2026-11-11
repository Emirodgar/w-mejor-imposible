"""Inyecta Open Graph + Twitter Card en todos los .html estáticos del sitio.
Idempotente: si la página ya tiene og:title no la toca. Uso: python scripts/anade_opengraph.py [--dry]"""
import os, re, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = 'https://mejorimposible.es'
IMG = BASE + '/img/og-default.jpg'
ALT = 'Mejor Imposible: Porsche, lujo y España'
LOCALE = {'es': 'es_ES', 'en': 'en_US', 'fr': 'fr_FR', 'de': 'de_DE', 'pt': 'pt_PT', 'it': 'it_IT'}
SKIP_DIRS = {'.claude', '_layouts', '_includes', 'design', 'node_modules', '.git'}
dry = '--dry' in sys.argv

def esc(s):
    return s.replace('"', '&quot;').replace('<', '&lt;').replace('>', '&gt;').strip()

n = skipped = 0
for r, ds, fs in os.walk(ROOT):
    ds[:] = [d for d in ds if d not in SKIP_DIRS]
    for f in fs:
        if not f.endswith('.html'): continue
        p = os.path.join(r, f)
        t = open(p, encoding='utf-8', newline='').read()
        nl = chr(13)+chr(10) if chr(13)+chr(10) in t else chr(10)
        if 'property="og:title"' in t or '</head>' not in t or '<title' not in t or '{{' in t[:t.find('</head>')]:
            skipped += 1; continue
        head = t[:t.find('</head>')]
        title = re.search(r'<title[^>]*>(.*?)</title>', head, re.S).group(1)
        title = re.sub(r'\s+', ' ', title)
        m = re.search(r'<meta\s+name="description"\s+content="([^"]*)"', head)
        desc = m.group(1) if m else title
        m = re.search(r'<link\s+rel="canonical"\s+href="([^"]+)"', head)
        if m: url = m.group(1)
        else:
            rel = os.path.relpath(p, ROOT).replace(os.sep, '/')
            rel = re.sub(r'(^|/)index\.html$', r'\1', rel)
            url = BASE + '/' + rel
        m = re.search(r'<html[^>]*\blang="([a-z]{2})', t)
        loc = LOCALE.get(m.group(1) if m else 'es', 'es_ES')
        typ = 'article' if re.search(r'"@type"\s*:\s*"(Article|BlogPosting|NewsArticle|TechArticle)"', head) else 'website'
        i = re.search(r'^([ \t]*)</head>', t, re.M)
        ind = (i.group(1) if i else '') + '    '
        tags = [
            '<!-- Open Graph / Twitter -->',
            f'<meta property="og:type" content="{typ}">',
            '<meta property="og:site_name" content="Mejor Imposible">',
            f'<meta property="og:locale" content="{loc}">',
            f'<meta property="og:title" content="{esc(title)}">',
            f'<meta property="og:description" content="{esc(desc)}">',
            f'<meta property="og:url" content="{esc(url)}">',
            f'<meta property="og:image" content="{IMG}">',
            '<meta property="og:image:type" content="image/jpeg">',
            '<meta property="og:image:width" content="1200">',
            '<meta property="og:image:height" content="630">',
            f'<meta property="og:image:alt" content="{ALT}">',
            '<meta name="twitter:card" content="summary_large_image">',
            f'<meta name="twitter:title" content="{esc(title)}">',
            f'<meta name="twitter:description" content="{esc(desc)}">',
            f'<meta name="twitter:image" content="{IMG}">',
            f'<meta name="twitter:image:alt" content="{ALT}">',
        ]
        block = ''.join(ind + x + '\n' for x in tags)
        new = re.sub(r'^([ \t]*)</head>', lambda m: block + m.group(0), t, count=1, flags=re.M)
        if not dry:
            open(p, 'w', encoding='utf-8', newline='').write(new)
        n += 1
print('modificadas', n, 'omitidas', skipped)
