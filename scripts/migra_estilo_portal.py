#!/usr/bin/env python3
"""Migra páginas de la guía Porsche a la identidad visual del portal (portal.css).
Idempotente: salta las páginas que ya cargan /assets/porsche.css.
Uso: python scripts/migra_estilo_portal.py [--dry]"""
import glob, re, sys, io
DRY = '--dry' in sys.argv
SECCIONES = [('Herramientas','/porsche/#tools',None),('Modelos','/porsche/modelos','modelos'),('Precios','/porsche/precios','precios'),
             ('Tendencias','/porsche/tendencias','tendencias'),('Opiniones','/porsche/analisis','analisis'),
             ('Concesionarios','/porsche/concesionarios','concesionarios'),('Blog','/porsche/blog','blog')]
FONT = ('<link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,400;0,500;1,400&family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">\n'
        '    <link rel="stylesheet" href="/assets/portal.css">')

def header(seccion):
    sub = ''.join('\n    <a href="%s"%s>%s</a>' % (u, ' aria-current="page"' if k and k == seccion else '', n) for n, u, k in SECCIONES)
    return '''<header class="wrap site-header">
        <a class="brand" href="/">mejor imposible</a>
        <nav class="main-nav" aria-label="Principal">
            <a href="/#rankings">Rankings</a>
            <a href="/#planes">Planes completos</a>
            <a href="/destinos/">Destinos</a>
            <a href="/buscar/">Buscar</a>
            <a href="/mi-viaje/">Mi viaje<span class="trip-count" hidden></span></a>
            <a href="/porsche/" aria-current="true">Guía Porsche</a>
        </nav>
    </header>
    <nav class="wrap porsche-sub" aria-label="Guía Porsche">
        <a class="lbl" href="/porsche/">Guía Porsche</a>%s
    </nav>''' % sub.replace('\n    ', '\n        ')

FOOTER = '''<footer class="site-footer">
        <div class="wrap">
            <a class="brand" href="/">mejor imposible</a>
            <nav class="footer-links" aria-label="Pie">
                <a href="/porsche/">Guía Porsche</a>
                <a href="/metodologia/">Metodología</a>
                <a href="/eventos/">Eventos</a>
                <a href="/novedades/">Qué ha cambiado</a>
            </nav>
        </div>
        <div class="wrap" style="padding-top:0;padding-bottom:32px;font-size:13px;color:var(--muted)">
            <p>&copy; <span id="current-year"></span> mejorimposible.es · Guía no oficial creada por y para entusiastas de Porsche. Todos los nombres de productos, logotipos y marcas son propiedad de sus respectivos dueños.</p>
        </div>
    </footer>'''

def seccion_de(path):
    p = path.replace(chr(92), '/')
    for _, _, k in SECCIONES:
        if k and ('/' + k) in p.replace('porsche/', '/porsche/'):
            return k
    return None

OLD_RULE = re.compile(r'[ \t]*\.(?:site-header|site-logo|site-nav|site-footer|nav-toggle)[^{}]*\{[^{}]*\}[ \t]*\n?')

def migra(path, seccion):
    s = io.open(path, encoding='utf8', newline='').read()
    if '/assets/porsche.css' in s or '</head>' not in s: return None
    crlf = '\r\n' in s
    s = s.replace('\r\n', '\n')
    orig = s
    # 1. fuentes + portal.css (antes del <style> propio)
    s, n = re.subn(r'<link href="https://fonts.googleapis.com/css2\?family=Inter[^>]*>', FONT, s, count=1)
    if n != 1:
        s, n = re.subn(r'</head>', '    ' + FONT + '\n</head>', s, count=1)  # dealer: sin fuente propia
    # 2. quitar reglas de cabecera/pie antiguas dentro de <style>
    def limpia(m):
        css = m.group(0)
        for _ in range(3): css = OLD_RULE.sub('', css)
        return css
    s = re.sub(r'<style>.*?</style>', limpia, s, flags=re.S)
    # 3. porsche.css después del último </style> del <head>
    head_end = s.index('</head>')
    last_style = s.rfind('</style>', 0, head_end)
    ins = '\n    <link rel="stylesheet" href="/assets/porsche.css">'
    if last_style == -1:
        s = s[:head_end] + ins.lstrip('\n') + '\n' + s[head_end:]
    else:
        k = last_style + len('</style>')
        s = s[:k] + ins + s[k:]
    # 4. cabecera, pie, script del menú móvil
    s, n1 = re.subn(r'<header class="site-header">.*?</header>', lambda m: header(seccion), s, count=1, flags=re.S)
    s, n2 = re.subn(r'<footer class="site-footer">.*?</footer>', lambda m: FOOTER, s, count=1, flags=re.S)
    s = re.sub(r'[ \t]*<script>\s*\(function \(\) \{\s*var toggle = document.getElementById\(\'nav-toggle\'\);.*?</script>\n?', '', s, count=1, flags=re.S)
    s = s.replace('</body>', '    <script src="/assets/viaje.js" defer></script>\n</body>', 1)
    # 5. colores de marca hardcodeados (gráficos) -> paleta del portal
    for a, b in (('#B12B28', '#7A5E32'), ('#b12b28', '#7A5E32'), ('#E3AB37', '#D9C39A'), ('#e3ab37', '#D9C39A'),
                 ('rgba(177, 43, 40', 'rgba(122, 94, 50'), ('rgba(177,43,40', 'rgba(122,94,50'),
                 ('rgba(227, 171, 55', 'rgba(217, 195, 154'), ('rgba(227,171,55', 'rgba(217,195,154')):
        s = s.replace(a, b)
    if crlf: s = s.replace('\n', '\r\n')
    if not DRY and s != orig.replace('\n', '\r\n' if crlf else '\n'):
        io.open(path, 'w', encoding='utf8', newline='').write(s)
    return (n1, n2)

if __name__ == '__main__':
    files = sorted(glob.glob('porsche/**/*.html', recursive=True)) + glob.glob('_layouts/*.html')
    for f in files:
        sec = seccion_de(f)
        r = migra(f, sec)
        print(('SKIP ' if r is None else ('OK   ' if r == (1, 1) else 'REVISAR %s ' % (r,))) + f)
