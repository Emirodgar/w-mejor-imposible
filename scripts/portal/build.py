#!/usr/bin/env python3
"""Genera las páginas del portal (home, rankings, planes y directorio) en todos los idiomas publicados.

Uso:  python scripts/portal/build.py

Datos (un archivo por elemento, con referencias cruzadas por id "categoria/slug"):
  data/portal/categorias.json          metadatos de cada ranking
  data/portal/items/<cat>/<slug>.json  un lugar (campo, restaurante...)
  data/portal/rankings/<cat>.json      orden del ranking (lista de ids)
  data/portal/planes/<slug>.json       un plan completo; sus pasos apuntan a ítems por id
  data/portal/aeropuertos.json         aeropuertos con coordenadas ("Lo mejor cerca" se calcula con ellas)
Las coordenadas se obtienen con scripts/portal/geocode.py; "Lo mejor cerca" (hotel, restaurante, golf, aeropuerto)
se calcula por distancia a partir de ellas, salvo que el ítem lo fije a mano en "cerca".

Idiomas:
  - Los textos van en español en los datos ({"es": "..."} o cadenas sueltas).
  - data/portal/i18n/ui.json        textos de la interfaz en los 6 idiomas (clave -> {es, en, fr, de, pt, it}).
  - data/portal/i18n/<idioma>.json  traducción del contenido: {"texto en español": "traducción"}.
  - PUBLISHED (abajo) lista los idiomas que se generan. Un idioma solo debe entrar ahí cuando no le falte
    ninguna traducción: el script lo avisa y escribe las que faltan en data/portal/i18n/_pendiente-<idioma>.json.
  - es vive en la raíz; el resto bajo /<idioma>/. Cada página lleva canonical, hreflang y x-default.
  - También se genera sitemap-portal.xml (con alternativas por idioma), referenciado desde robots.txt.
  - HOME y NOINDEX controlan la ruta de la home y si las páginas llevan noindex (borrador).
"""
import datetime
import html
import json
import math
import os
import re

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
DATA = os.path.join(ROOT, 'data', 'portal')
SITE = 'https://mejorimposible.es'
HOME = '/index2.html'      # cuando el portal sustituya a la home, cambiar a '/'
NOINDEX = True             # quitar al lanzar el portal
LANGS = [('es', 'ES'), ('en', 'EN'), ('fr', 'FR'), ('de', 'DE'), ('pt', 'PT'), ('it', 'IT')]
PUBLISHED = ['es', 'en', 'fr', 'de', 'pt', 'it']   # idiomas que se generan y aparecen en el selector
LANG = 'es'

ZONE_KEYS = ['todas', 'andalucia', 'cataluna', 'baleares', 'canarias', 'resto']
TONES = ['', ' t3', '', ' t3', '']
STRIP_TONES = ['', ' t2', ' t3', ' t4', '']
LABEL_TIPO = {'Hotel': 'hotel', 'Restaurante': 'restaurante', 'Golf': 'golf', 'Aeropuerto': 'aeropuerto',
              'Spa': 'spa', 'Puerto': 'puerto', 'Bodega': 'bodega'}
CAT_SCHEMA = {'golf': 'GolfCourse', 'restaurantes': 'Restaurant', 'hoteles-de-lujo': 'Hotel',
              'bodegas': 'Winery', 'spas': 'HealthAndBeautyBusiness'}
HOME_STRIPS = [('hoteles-de-lujo', 'hoteles', 'r-hoteles'), ('golf', 'golf', 'r-golf'),
               ('restaurantes', 'restaurantes', 'r-mesas'), ('casas-de-lujo', 'casas', 'r-casas')]
HOME_CHIPS = ['hoteles-de-lujo', 'golf', 'restaurantes', 'casas-de-lujo', 'bodegas', 'spas', 'yates-y-calas', 'motor']


def e(s):
    return html.escape(str(s), quote=True)


def load(rel):
    with open(os.path.join(DATA, *rel.split('/')), encoding='utf-8') as f:
        return json.load(f)


def exists(rel):
    return os.path.exists(os.path.join(DATA, *rel.split('/')))


# ---------------- Idiomas ----------------
UI = load('i18n/ui.json')
TEXT = {c: (load(f'i18n/{c}.json') if exists(f'i18n/{c}.json') else {}) for c, _ in LANGS if c != 'es'}
MISSING = {c: set() for c, _ in LANGS}


def ui(key, **kw):
    s = UI[key][LANG]
    return s.format(**kw) if kw else s


def tr(es):
    """Traduce una cadena en español al idioma actual; anota las que faltan."""
    if LANG == 'es' or not es:
        return es
    v = TEXT[LANG].get(es)
    if v is None:
        MISSING[LANG].add(es)
        return es
    return v


def t(x):
    """Texto traducible: {"es": ...} (o {"es": ..., "en": ...}) o cadena suelta -> cadena en el idioma actual."""
    if isinstance(x, dict):
        return x[LANG] if LANG in x else tr(x.get('es', ''))
    return tr(x)


def prefix(lang):
    return '' if lang == 'es' else f'/{lang}'


def u(path):
    """Enlace interno en el idioma actual. La guía Porsche (/porsche/, solo en español) y las anclas no cambian."""
    if not path.startswith('/') or path == '/':
        return path
    return prefix(LANG) + path


def write(path, content):
    if path.endswith('/'):
        path += 'index.html'
    full = os.path.join(ROOT, *(prefix(LANG) + path).strip('/').split('/'))
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, 'w', encoding='utf-8', newline='\n') as f:
        f.write(content)


CATS = load('categorias.json')
ITEMS = {}
for _cat in os.listdir(os.path.join(DATA, 'items')):
    for _fn in os.listdir(os.path.join(DATA, 'items', _cat)):
        _item = load(f'items/{_cat}/{_fn}')
        ITEMS[_item['id']] = _item
PAGES = []  # rutas (en español) de las páginas generadas, para el sitemap
USED = []   # ítems cuya foto se muestra en la página en curso (para la sección de créditos)


def photo_img(item, eager=False, cls=''):
    """Etiqueta <img> de la foto real del ítem (vacía si no tiene) y la anota para los créditos."""
    fr = (item or {}).get('foto_real')
    if not fr:
        return ''
    if item not in USED:
        USED.append(item)
    return (f'<img{f" class={chr(34)}{cls}{chr(34)}" if cls else ""} src="{e(fr["archivo"])}" alt="{e(item["nombre"])}, {e(item["lugar"])}" '
            f'{"" if eager else "loading=" + chr(34) + "lazy" + chr(34) + " "}decoding="async">')


def ph_box(item, extra=''):
    """Recuadro de foto: con la foto real si existe; si no, un bloque neutro sin texto."""
    img = photo_img(item)
    cls = ' '.join(x for x in ('ph', extra.strip(), 'has-img' if img else '') if x)
    return f'<div class="{cls}"{"" if img else " aria-hidden=" + chr(34) + "true" + chr(34)}>{img}</div>'


def credits_html():
    """Sección de créditos de las fotos usadas en la página; vacía la lista."""
    if not USED:
        return ''
    lis = ''
    for it in sorted(USED, key=lambda x: x['nombre']):
        fr = it['foto_real']
        if fr.get('origen') == 'propia':
            lis += f'\n            <li>{e(it["nombre"])}: © {e(fr.get("autor") or "Mejor Imposible")}</li>'
            continue
        author = e(fr.get('autor') or 'Wikimedia Commons')
        lic = f'<a href="{e(fr["licencia_url"])}" rel="noopener">{e(fr["licencia"])}</a>' if fr.get('licencia_url') else e(fr['licencia'])
        lis += (f'\n            <li>{e(it["nombre"])}: <a href="{e(fr["fuente"])}" rel="noopener">{author}</a> · {lic}'
                f' · Wikimedia Commons</li>')
    USED.clear()
    return (f'\n<section class="wrap credits" aria-label="{e(ui("credits.h"))}">\n    <details>\n        <summary>{e(ui("credits.h"))}</summary>'
            f'\n        <ul>{lis}\n        </ul>\n    </details>\n</section>\n')


def item_url(ref):
    cat, slug = ref.split('/')
    return u(f'/ranking/{cat}/{slug}/')


# ---------------- Plantilla común ----------------
def lang_html(path):
    out = []
    for c, n in LANGS:
        if c not in PUBLISHED:
            continue
        cur = ' aria-current="true"' if c == LANG else ''
        out.append(f'        <a href="{prefix(c)}{path}" hreflang="{c}" lang="{c}"{cur}>{n}</a>')
    return '\n'.join(out)


def head_links(path):
    out = [f'    <link rel="canonical" href="{SITE}{prefix(LANG)}{path}">']
    for c in PUBLISHED:
        out.append(f'    <link rel="alternate" hreflang="{c}" href="{SITE}{prefix(c)}{path}">')
    out.append(f'    <link rel="alternate" hreflang="x-default" href="{SITE}{path}">')
    return '\n'.join(out)


HEAD = '''<!DOCTYPE html>
<html lang="@@L@@">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>@@TITLE@@</title>
    <meta name="description" content="@@DESC@@">
@@ROBOTS@@
@@LINKS@@
    <link rel="icon" type="image/svg+xml" href="/assets/favicon.svg">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,400;0,500;1,400&family=Inter:wght@400;500&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="/assets/portal.css">
@@LD@@
</head>
<body>

<header class="wrap site-header">
    <a class="brand" href="@@HOME@@">mejor imposible</a>
    <nav class="main-nav" aria-label="@@ARIA_MAIN@@">
        <a href="@@HOME@@#rankings">@@N_RANK@@</a>
        <a href="@@HOME@@#planes">@@N_PLANS@@</a>
        <a href="@@DEST@@">@@N_DEST@@</a>
        <a href="/">@@N_PORSCHE@@</a>
    </nav>
    <div class="lang" aria-label="@@ARIA_LANG@@">
@@LANG@@
    </div>
</header>
'''

FOOT = '''
<footer class="site-footer">
    <div class="wrap">
        <a class="brand" href="@@HOME@@">mejor imposible</a>
        <nav class="footer-links" aria-label="@@ARIA_FOOT@@">
            <a href="/">@@N_PORSCHE@@</a>
            <a href="@@METHOD@@">@@N_METHOD@@</a>
        </nav>
    </div>
</footer>
'''

SCRIPT = '''
<script>
(function () {
    var buttons = document.querySelectorAll('[data-filter]');
    var tops = document.querySelectorAll('.top-item');
    var rests = document.querySelectorAll('.compact-list li');
    var restSection = document.getElementById('rest');
    var emptyTop = document.getElementById('empty-top');
    function apply(zone) {
        var shownTop = 0, shownRest = 0;
        tops.forEach(function (el) { var on = zone === 'todas' || el.dataset.zone === zone; el.hidden = !on; if (on) shownTop++; });
        rests.forEach(function (el) { var on = zone === 'todas' || el.dataset.zone === zone; el.hidden = !on; if (on) shownRest++; });
        restSection.hidden = shownRest === 0;
        emptyTop.hidden = shownTop !== 0;
        buttons.forEach(function (b) { b.setAttribute('aria-pressed', String(b.dataset.filter === zone)); });
    }
    buttons.forEach(function (b) { b.addEventListener('click', function () { apply(b.dataset.filter); }); });
    var z = new URLSearchParams(location.search).get('zona');
    if (z && document.querySelector('[data-filter="' + z + '"]')) apply(z);
    if (location.hash) {
        var target = document.getElementById(location.hash.slice(1));
        if (target && target.hidden) apply('todas');
        if (target) target.scrollIntoView();
    }
})();
</script>'''


def crumbs(items):
    lis = ''.join(f'<li><a href="{u_}">{e(n)}</a></li>' if u_ else f'<li aria-current="page">{e(n)}</li>' for n, u_ in items)
    return f'<nav class="wrap crumbs" aria-label="{e(ui("aria.crumbs"))}"><ol>{lis}</ol></nav>'


def bc_ld(items):
    return {"@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": i + 1, "name": n, **({"item": SITE + u_} if u_ else {})}
        for i, (n, u_) in enumerate(items)]}


def ld(*objs):
    return '\n'.join('    <script type="application/ld+json">\n' + json.dumps(
        {"@context": "https://schema.org", **o}, ensure_ascii=False, indent=4) + '\n    </script>' for o in objs)


def page(path, title, desc, lds, body):
    """path: ruta de la página en español (con barra inicial); sirve para canonical, hreflang y selector de idioma."""
    if path not in PAGES:
        PAGES.append(path)
    if len(title) > 65:  # los títulos largos pierden la marca para no cortarse en los resultados
        title = title.replace(' · Mejor Imposible', '')
    robots = ('    <!-- Borrador del nuevo portal: no indexar hasta sustituir a index.html -->\n'
              '    <meta name="robots" content="noindex, nofollow">') if NOINDEX else ''
    rep = {'@@L@@': LANG, '@@TITLE@@': e(title), '@@DESC@@': e(desc), '@@ROBOTS@@': robots, '@@LINKS@@': head_links(path),
           '@@LD@@': ld(*lds), '@@HOME@@': u(HOME), '@@DEST@@': u('/destinos/'), '@@METHOD@@': u('/metodologia/'),
           '@@ARIA_MAIN@@': e(ui('aria.main')), '@@ARIA_LANG@@': e(ui('aria.lang')), '@@ARIA_FOOT@@': e(ui('aria.footer')),
           '@@N_RANK@@': e(ui('nav.rankings')), '@@N_PLANS@@': e(ui('nav.plans')), '@@N_DEST@@': e(ui('nav.destinations')),
           '@@N_PORSCHE@@': e(ui('nav.porsche')), '@@N_METHOD@@': e(ui('nav.method')), '@@LANG@@': lang_html(path)}
    h, f = HEAD, FOOT
    for k, v in rep.items():
        h, f = h.replace(k, v), f.replace(k, v)
    return h + body + credits_html() + f + (SCRIPT if 'data-zone' in body else '') + '\n</body>\n</html>\n'


# ---------------- Rankings ----------------
def fval(v):
    """Valor de ficha: números con coma decimal en español, punto en otros idiomas; textos traducidos."""
    if isinstance(v, str):
        if re.fullmatch(r'\d+,\d+', v):
            return v if LANG == 'es' else v.replace(',', '.')
        return tr(v)
    return v


def spec_text(cat, ficha):
    """Compone la línea de ficha; omite las partes cuyo dato falte."""
    parts = []
    for tpl in CATS[cat]['ficha']:
        fields = re.findall(r'\{(\w+)\}', tpl)
        if all(f in ficha for f in fields):
            parts.append(tr(tpl).format(**{f: fval(ficha[f]) for f in fields}))
        elif not fields:
            parts.append(tr(tpl))
    return ' · '.join(parts)


AIRPORTS = load('aeropuertos.json')['aeropuertos']
MICHELIN = [r for r in (load('michelin/guia-2026.json')['restaurantes'] if exists('michelin/guia-2026.json') else [])
            if r.get('coordenadas') and not r.get('ref')]  # los que ya son ítems del ranking salen como ítem
LLAVES = [r for r in (load('michelin/llaves-2026.json')['hoteles'] if exists('michelin/llaves-2026.json') else [])
          if r.get('coordenadas') and not r.get('ref')]
CAT_DE_TIPO = {'restaurante': 'restaurantes', 'golf': 'golf', 'hotel': 'hoteles-de-lujo'}
MAX_KM = 75  # radio máximo para sugerir un restaurante o un campo "cerca"


def coords(x):
    c = x.get('coordenadas')
    return (c['lat'], c['lon']) if c else None


def haversine_km(a, b):
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


def drive_min(km):
    """Estimación: trazado ~25 % más largo que la línea recta, a 70 km/h de media, más 5 min de salida/llegada; redondeo a 5 min."""
    return max(5, int(round((km * 1.25 / 70 * 60 + 5) / 5)) * 5)


def nearest(item, tipo):
    """Busca automáticamente lo más cercano a un ítem por coordenadas (None si no hay o está lejos)."""
    here = coords(item or {})
    if not here:
        return None
    if tipo == 'aeropuerto':
        pool = [(a['nombre'], None, a) for a in AIRPORTS if coords(a)]
    elif tipo in CAT_DE_TIPO:
        cat = CAT_DE_TIPO[tipo]
        pool = [(i['nombre'], i['id'], i) for i in ITEMS.values()
                if i['categoria'] == cat and i['id'] != item['id'] and coords(i)]
    else:
        return None
    best = min(((haversine_km(here, coords(x)), n, ref, None, x) for n, ref, x in pool), default=None)
    # la lista Michelin entra si no hay ítem del ranking a menos de 60 min, o si uno estrellado queda
    # al menos 15 min más cerca (por ejemplo, el restaurante de la propia bodega)
    extra = {'restaurante': (MICHELIN, 'estrellas', 'michelin.star'),
             'hotel': (LLAVES, 'llaves', 'michelin.key')}.get(tipo)
    if extra:
        mbest = min(((haversine_km(here, coords(r)), r['nombre'], None, r[extra[1]], r) for r in extra[0]), default=None)
        if mbest and (not best or drive_min(best[0]) > 60 or drive_min(mbest[0]) + 15 <= drive_min(best[0])):
            best = mbest if not best or mbest[0] < best[0] else best
    if not best or (tipo != 'aeropuerto' and best[0] > MAX_KM) or (tipo == 'aeropuerto' and drive_min(best[0]) > 150):
        return None
    name = tr(best[1]) if tipo == 'aeropuerto' else best[1]
    out = dict(tipo=tipo, nombre=name, ref=best[2], min=drive_min(best[0]), geo=coords(best[4]))
    mismo = best[1].lower() in item['nombre'].lower() or item['nombre'].lower() in best[1].lower()
    if best[0] < 0.3 and mismo and tipo in ('restaurante', 'hotel'):
        out['nota'] = ui('near.same')
        out['min'] = 0
    elif best[3]:
        out['nota'] = f"{ui(extra[2] + ('1' if best[3] == 1 else '2'), n=best[3])} · {ui('near.min', n=out['min'])}"
    return out


def near_tiles(cat, item):
    tiles = ''
    for label in CATS[cat]['cerca']:
        tipo = LABEL_TIPO.get(label, label.lower())
        name_l = ui('near.' + tipo)
        # lo escrito a mano en el ítem manda; si no hay, se calcula por coordenadas
        manual = next((c for c in (item or {}).get('cerca', []) if c['tipo'] == tipo and (c.get('ref') or c.get('nombre'))), None)
        entry = dict(manual, nota=tr(manual['nota'])) if manual and manual.get('nota') else manual
        entry = entry or nearest(item, tipo)
        name = href = None
        if entry:
            if entry.get('ref'):
                ref_item = ITEMS[entry['ref']]
                name, href = ref_item['nombre'], item_url(entry['ref'])
                if not entry.get('min') and coords(item) and coords(ref_item):
                    entry = dict(entry, min=drive_min(haversine_km(coords(item), coords(ref_item))))
            else:
                name = entry.get('nombre')
        if name:
            detail = entry.get('nota') or (ui('near.min', n=entry['min']) if entry.get('min') else '')
            k, tt = e(name), e(f'{name_l} · {detail}' if detail else name_l)
        else:
            continue  # sin sugerencia cercana: no se muestra el hueco
        tiles += f'<a href="{href or "#"}"><span class="sq"></span><span class="k">{k}</span><span class="t">{tt}</span></a>'
    return tiles


def ranking_entries(slug):
    """Lista de dicts normalizados del ranking y su fecha de actualización."""
    rk = load(f'rankings/{slug}.json')
    out = []
    for ref in rk['items']:
        it = ITEMS[ref]
        out.append(dict(slug=ref.split('/')[1], nombre=it['nombre'], lugar=it['lugar'], zona=it['zona'],
                        foto=t(it['foto']), why=t(it['por_que']), spec=spec_text(slug, it['ficha']), item=it))
    return out, t(rk['actualizado'])


def build_rank(slug):
    c = CATS[slug]
    entries, updated = ranking_entries(slug)
    top, rest = entries[:5], entries[5:]
    items = ''
    for i, en in enumerate(top):
        anchor = f' id="{en["slug"]}"' if en['slug'] else ''
        plan = (f'\n                    <a class="plan-link" href="{u("/planes/golf-en-sotogrande/")}">{e(ui("rank.plan_link"))}</a>'
                if en['slug'] == 'real-club-valderrama' else '')
        items += f'''
        <li class="top-item"{anchor} data-zone="{en['zona']}" data-rank="{i+1}">
            <div class="num" aria-hidden="true">{i+1:02d}</div>
            {ph_box(en['item'], 'photo' + TONES[i])}
            <div class="info">
                <p class="place">{e(en['lugar'])}</p>
                <h2><span class="visually-hidden">{i+1}. </span><a href="{item_url(en['item']['id'])}">{e(en['nombre'])}</a></h2>
                <p class="why">{e(en['why'])}</p>
                <p class="spec">{e(en['spec'])}</p>
                <div class="near">
                    <p class="label">{e(ui('rank.near'))}</p>
                    <div class="near-grid">{near_tiles(slug, en['item'])}</div>
                    <a class="plan-link" href="{item_url(en['item']['id'])}">{e(ui('item.full'))}</a>{plan}
                </div>
            </div>
        </li>'''
    restli = ''.join(f'''
            <li id="{en["slug"]}" data-zone="{en['zona']}"><a href="{item_url(en['item']['id'])}"><span class="n">{i+6:02d}</span><span class="thumb"></span><span class="nm">{e(en['nombre'])}</span><span class="pl">{e(en['lugar'])}</span><span class="arrow" aria-hidden="true">→</span></a></li>'''
                     for i, en in enumerate(rest))
    chips = ''.join(
        f'<button type="button" data-filter="{k}" aria-pressed="{"true" if k == "todas" else "false"}">{e(ui("zone." + k))}</button>'
        for k in ZONE_KEYS)
    short, h1 = t(c['corto']), t(c['titulo'])
    extra_link = (f'\n        <p class="hero-link"><a href="{u("/motor/marcas/")}">{e(ui("rank.motor_link"))}</a></p>'
                  if slug == 'motor' else '')
    crumb = [(ui('crumb.home'), u(HOME)), (ui('crumb.rankings'), u(HOME) + '#rankings'), (short, None)]
    schema = CAT_SCHEMA.get(slug)
    ld_items = []
    for n, en in enumerate(entries, 1):
        li = {"@type": "ListItem", "position": n, "name": en['nombre'], "url": SITE + item_url(en['item']['id'])}
        if schema:
            li["item"] = {"@type": schema, "name": en['nombre'],
                          "address": {"@type": "PostalAddress", "addressLocality": en['lugar'], "addressCountry": "ES"}}
        ld_items.append(li)
    itemlist = {"@type": "ItemList", "name": h1, "inLanguage": LANG, "itemListOrder": "https://schema.org/ItemListOrderAscending",
                "numberOfItems": len(entries), "itemListElement": ld_items}
    body = f'''
{crumbs(crumb)}

<main>
    <section class="wrap rank-hero">
        <p class="eyebrow">{e(ui('rank.eyebrow', short=short, updated=updated))}</p>
        <h1>{e(h1)}</h1>
        <div class="chips left" role="group" aria-label="{e(ui('rank.filter_aria'))}">{chips}</div>{extra_link}
    </section>

    <ol class="wrap top-list" id="top">{items}
    </ol>
    <p class="wrap empty" id="empty-top" hidden>{e(ui('rank.empty'))}</p>

    <section class="wrap rest" id="rest" aria-labelledby="rest-h">
        <h2 id="rest-h">{e(ui('rank.rest_h', last=len(entries)))}</h2>
        <ol class="compact-list">{restli}
        </ol>
    </section>

    <section class="wrap method" id="metodologia">
        <div class="box">
            <div>
                <p class="eyebrow">{e(ui('rank.how'))}</p>
                <p class="txt">{e(t(c['como_ordenamos']))}</p>
            </div>
            <a href="{u('/metodologia/')}">{e(ui('rank.method_link'))}</a>
        </div>
    </section>
</main>
'''
    write(f'/ranking/{slug}/index.html', page(
        f'/ranking/{slug}/', f'{h1} · Mejor Imposible', ui('rank.desc', h1=h1), [itemlist, bc_ld(crumb)], body))


# ---------------- Planes ----------------
ICONS = {
    'llegada': '<path d="M2 12h20"></path><path d="M13 4l7 8-7 8"></path><path d="M6 8l-3 4 3 4"></path>',
    'coche': '<path d="M3 16v-3l2-5h14l2 5v3"></path><path d="M3 16h18"></path><circle cx="7" cy="17" r="2"></circle><circle cx="17" cy="17" r="2"></circle>',
    'hotel': '<path d="M3 18V8"></path><path d="M3 14h18v4"></path><path d="M7 14v-3h10a4 4 0 0 1 4 4"></path>',
    'golf': '<path d="M8 21V3l9 4-9 4"></path><path d="M4 21h12"></path>',
    'cena': '<path d="M7 3v8"></path><path d="M5 3v4a2 2 0 0 0 4 0V3"></path><path d="M7 11v10"></path><path d="M17 21V3c-2 1-3 4-3 7h3"></path>',
    'descanso': '<path d="M12 3c3 4 3 8 0 11-3-3-3-7 0-11z"></path><path d="M4 17c4 0 6 2 8 4 2-2 4-4 8-4"></path>',
    'mesa': '<path d="M7 3v8"></path><path d="M5 3v4a2 2 0 0 0 4 0V3"></path><path d="M7 11v10"></path><path d="M17 21V3c-2 1-3 4-3 7h3"></path>',
    'bodega': '<path d="M8 3h8l-1 7a3 3 0 0 1-6 0z"></path><path d="M12 13v8"></path><path d="M8 21h8"></path>',
    'barco': '<path d="M3 17l2 3h14l2-3z"></path><path d="M12 3v11"></path><path d="M12 4l6 8h-6"></path>',
    'cala': '<path d="M3 9c3 0 3 2 6 2s3-2 6-2 3 2 6 2"></path><path d="M3 15c3 0 3 2 6 2s3-2 6-2 3 2 6 2"></path>',
}
# tipo de paso de la ruta -> categoría de ranking enlazada (None: ancla "cómo llegar")
ROUTE_CAT = {'llegada': None, 'coche': 'motor', 'hotel': 'hoteles-de-lujo', 'golf': 'golf', 'cena': 'restaurantes',
             'descanso': 'spas', 'mesa': 'restaurantes', 'bodega': 'bodegas', 'barco': 'yates-y-calas', 'cala': 'yates-y-calas'}
# el paso destacado (círculo oscuro) de la ruta
HIGHLIGHT = ('golf', 'bodega', 'cala', 'mesa')


def all_plans():
    plans = [load(f'planes/{fn}') for fn in os.listdir(os.path.join(DATA, 'planes'))]
    return sorted(plans, key=lambda p: p.get('orden', 99))


def other_plans(slug):
    return [p for p in all_plans() if p['slug'] != slug]


def plan_cover(p):
    """Ítem cuya foto ilustra el plan: 'portada_ref' del plan o el primero con foto."""
    if p.get('portada_ref'):
        return ITEMS[p['portada_ref']]
    for d in p['dias']:
        for s in d['pasos']:
            it = ITEMS.get(s.get('ref'))
            if it and it.get('foto_real'):
                return it
    return None


def plan_points(p):
    """Puntos del mapa: aeropuertos de 'llegar' y lugares con ficha, con coordenadas."""
    pts, seen = [], set()

    def add(name, c, kind):
        if c and name not in seen:
            seen.add(name)
            pts.append({'n': name, 'lat': c[0], 'lon': c[1], 'k': kind})
    for r in p['llegar']:
        rn = r['nombre']['es']
        a = next((a for a in sorted(AIRPORTS, key=lambda x: -len(x['nombre'])) if a['nombre'] in rn or rn in a['nombre']), None)
        if a:
            add(t(r['nombre']), coords(a), 'a')
    for d in p['dias']:
        for s in d['pasos']:
            it = ITEMS.get(s.get('ref'))
            if it:
                add(it['nombre'], coords(it), 'p')
    return pts


MAP_JS = '''
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.css">
<script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.js"></script>
<script>
(function () {
    var el = document.getElementById('plan-map');
    if (!el || !window.L) return;
    var pts = JSON.parse(el.dataset.points);
    var map = L.map(el, { scrollWheelZoom: false });
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom: 18, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
    }).addTo(map);
    var ll = pts.map(function (p) {
        L.circleMarker([p.lat, p.lon], { radius: 8, weight: 2, color: '#16140F', fillColor: p.k === 'a' ? '#16140F' : '#7A5E32', fillOpacity: 1 })
            .bindTooltip(p.n).addTo(map);
        return [p.lat, p.lon];
    });
    if (ll.length > 1) map.fitBounds(ll, { padding: [40, 40], maxZoom: 12 }); else map.setView(ll[0], 11);
})();
</script>'''


def map_html(p):
    """Mapa interactivo (Leaflet + OpenStreetMap) con los puntos del plan."""
    pts = plan_points(p)
    if not pts:
        return ''
    return (f'<div class="map live" id="plan-map" role="region" aria-label="{e(ui("plan.map_aria"))}" '
            f'data-points="{e(json.dumps(pts, ensure_ascii=False))}"><noscript>{e(ui("plan.map_aria"))}</noscript></div>')


def build_plan(slug):
    p = load(f'planes/{slug}.json')
    zona = p['zona']
    zn = ui('zone.' + zona)
    title = t(p['titulo'])

    def step_name(s):
        return ITEMS[s['ref']]['nombre'] if s.get('ref') else t(s['nombre'])

    route_html, route_ld = '', []
    for s in p['ruta']:
        label, txt = ui('route.' + s['tipo']), ui('route.' + s['tipo'] + '.link', z=zn)
        cat = ROUTE_CAT[s['tipo']]
        name = step_name(s)
        href = '#llegar-h' if cat is None else f'{u(f"/ranking/{cat}/")}?zona={zona}'
        on = s['tipo'] in HIGHLIGHT and not any(r['tipo'] in HIGHLIGHT for r in p['ruta'][:p['ruta'].index(s)])
        stroke = '#F6F3EE' if on else '#16140F'
        route_html += f'''
            <li><a href="{href}" aria-label="{e(txt)}"><span class="dot{' on' if on else ''}"><svg aria-hidden="true" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="{stroke}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">{ICONS[s['tipo']]}</svg></span><span class="k">{e(label)}</span><span class="v">{e(name)}</span></a></li>'''
        route_ld.append({"@type": "ListItem", "position": len(route_ld) + 1, "name": f'{label}: {name}'})

    days_html = ''
    for n, d in enumerate(p['dias'], 1):
        steps = ''
        for s in d['pasos']:
            tone = ' t3' if s.get('tono') == 'oscuro' else ''
            it = ITEMS.get(s.get('ref'))
            pic = ph_box(it, tone) if it and it.get('foto_real') else ''
            if s.get('ref'):
                it = ITEMS[s['ref']]
                name = f'<a href="{item_url(s["ref"])}">{e(it["nombre"])}</a>'
                foto, why = t(it['foto']), t(s['por_que']) if s.get('por_que') else t(it['por_que'])
            else:
                name, foto, why = e(t(s['nombre'])), t(s['foto']), t(s['por_que'])
                if s.get('enlace'):
                    name = f'<a href="{u(s["enlace"])}">{name}</a>'
            if s.get('alternativas'):
                alts = ' · '.join(f'<a href="#">{e(t(a))}</a>' for a in s['alternativas'])
            else:
                alts = ''
            steps += f'''
                <article>
                    {pic}
                    <p class="kind">{e(tr(s['tipo']))}</p>
                    <h3>{name}</h3>
                    <p class="why">{e(why)}</p>
                    {f'<p class="alt">{e(ui("plan.alts"))} {alts}</p>' if alts else ''}
                </article>'''
        days_html += f'''
    <section class="wrap day" aria-labelledby="dia-{n:02d}">
        <div class="day-head"><span class="dn" aria-hidden="true">{n:02d}</span><h2 id="dia-{n:02d}">{e(ui('plan.day', n=n, t=t(d['titulo'])))}</h2></div>
        <div class="steps">{steps}
        </div>
    </section>
'''

    llegar = ''
    for r in p['llegar']:
        val = f"~{r['min']} min" if r.get('min') else t(r['texto'])
        llegar += f'\n                    <div class="r"><dt>{e(t(r["nombre"]))}</dt><dd>{e(val)}</dd></div>'
    others = ''.join(
        f'\n            <a href="{u("/planes/" + o["slug"] + "/")}"><span class="thumb">{photo_img(plan_cover(o))}</span><span class="m">{e(t(o["meta_corta"]))}</span><span class="t">{e(t(o["titulo"]))}</span></a>'
        for o in other_plans(slug)[:3])
    crumb = [(ui('crumb.home'), u(HOME)), (ui('nav.plans'), u(HOME) + '#planes'), (title, None)]
    trip = {"@type": "TouristTrip", "name": title, "inLanguage": LANG, "description": t(p['lead']),
            "touristType": t(p.get("tipo_turista", "Golf")), "itinerary": {"@type": "ItemList", "itemListElement": route_ld}}
    body = f'''
{crumbs(crumb)}

<main>
    <section class="wrap">
        <div class="plan-hero">
            {photo_img(plan_cover(p), eager=True, cls='cover')}
            <p class="kicker">{e(t(p['meta']))}</p>
            <h1>{e(title)}</h1>
            <p class="lead">{e(t(p['lead']))}</p>
        </div>
    </section>

    <section class="wrap route" aria-label="{e(ui('plan.summary_aria'))}">
        <ol>{route_html}
        </ol>
    </section>
{days_html}
    <section class="wrap getting" aria-labelledby="llegar-h">
        <div class="cols">
            {map_html(p)}
            <div class="times">
                <h2 id="llegar-h">{e(ui('plan.getting'))}</h2>
                <dl>{llegar}
                </dl>
            </div>
        </div>
    </section>

    <section class="wrap others" aria-labelledby="otros-h">
        <h2 id="otros-h">{e(ui('plan.others'))}</h2>
        <div class="grid">{others}
        </div>
    </section>
</main>
'''
    html_page = page(f'/planes/{slug}/', f'{ui("plan.title", title=title)} · Mejor Imposible',
                     f'{t(p["meta"])}: {t(p["lead"])}', [trip, bc_ld(crumb)], body)
    write(f'/planes/{slug}/index.html', html_page.replace('</body>', MAP_JS + '\n</body>') if 'id="plan-map"' in body else html_page)



# ---------------- Fichas de cada lugar ----------------
SCHEMA_OF = dict(CAT_SCHEMA, **{'motor': 'SportsActivityLocation', 'casas-de-lujo': 'Place', 'yates-y-calas': 'Place'})


def ranking_positions():
    pos = {}
    for cat in CATS:
        if exists(f'rankings/{cat}.json'):
            refs = load(f'rankings/{cat}.json')['items']
            for i, r in enumerate(refs):
                pos[r] = (cat, i + 1, len(refs), refs[i - 1] if i else None, refs[i + 1] if i + 1 < len(refs) else None)
    return pos


RANK_POS = ranking_positions()


def trim(text, n=170):
    if len(text) <= n:
        return text
    return text[:n].rsplit(' ', 1)[0].rstrip(',;:') + '…'


def near_points(cat, item):
    """Lugares cercanos con coordenadas, para el mapa de la ficha."""
    pts = []
    for label in CATS[cat]['cerca']:
        tipo = LABEL_TIPO.get(label, label.lower())
        manual = next((c for c in item.get('cerca', []) if c['tipo'] == tipo and c.get('ref')), None)
        entry = manual or nearest(item, tipo)
        if not entry:
            continue
        if entry.get('ref'):
            ref_item = ITEMS[entry['ref']]
            c = coords(ref_item)
            name = ref_item['nombre']
        else:
            c, name = entry.get('geo'), entry.get('nombre')
        if c and name:
            pts.append({'n': name, 'lat': c[0], 'lon': c[1], 'k': 'a'})
    return pts


def build_item(ref):
    it = ITEMS[ref]
    cat, slug = ref.split('/')
    rk = RANK_POS.get(ref)
    c = CATS[cat]
    short, h1 = t(c['corto']), t(c['titulo'])
    name, why, spec = it['nombre'], t(it['por_que']), spec_text(cat, it['ficha'])
    path = f'/ranking/{cat}/{slug}/'
    pos = rk[1] if rk else None
    title = (ui('item.title', name=name, n=pos, cat=short) if pos else f'{name} · {short}') + ' · Mejor Imposible'
    desc = trim(why if len(why) >= 60 else f'{why} {it["lugar"]} · {short}.')
    crumb = [(ui('crumb.home'), u(HOME)), (ui('crumb.rankings'), u(HOME) + '#rankings'), (short, u(f'/ranking/{cat}/')), (name, None)]
    photo = ''
    if it.get('foto_real'):
        photo = f'\n    <section class="wrap item-photo">{ph_box(it, "photo")}</section>'
    tiles = near_tiles(cat, it)
    pts = [{'n': name, 'lat': coords(it)[0], 'lon': coords(it)[1], 'k': 'p'}] if coords(it) else []
    pts += near_points(cat, it)
    map_block = ''
    if pts:
        aria = ui('item.map_aria', name=name)
        map_block = (f'\n    <section class="wrap item-map"><div class="map live" id="plan-map" role="region" aria-label="{e(aria)}" '
                     f'data-points="{e(json.dumps(pts, ensure_ascii=False))}"><noscript>{e(aria)}</noscript></div></section>')
    plans = [p for p in all_plans() if any(s.get('ref') == ref for d in p['dias'] for s in d['pasos'])]
    plans_block = ''
    if plans:
        lis = ''.join(f'\n            <li><a href="{u("/planes/" + p["slug"] + "/")}">{e(t(p["titulo"]))}</a></li>' for p in plans)
        plans_block = (f'\n    <section class="wrap prose"><h2>{e(ui("item.plans"))}</h2>\n        <ul class="sources">{lis}\n        </ul>\n    </section>')
    src = ''
    if it.get('fuentes'):
        lis = ''.join(f'\n            <li><a href="{e(url)}" rel="noopener">{e(url.split("/")[2].replace("www.", ""))}</a></li>' for url in it['fuentes'])
        src = (f'\n    <section class="wrap prose"><h2>{e(ui("item.sources"))}</h2>\n        <ul class="sources">{lis}\n        </ul>\n    </section>')
    nav = ''
    if rk:
        prev_l = f'<a href="{item_url(rk[3])}">{e(ui("item.prev"))} {e(ITEMS[rk[3]]["nombre"])}</a>' if rk[3] else '<span></span>'
        next_l = f'<a href="{item_url(rk[4])}">{e(ITEMS[rk[4]]["nombre"])} {e(ui("item.next"))}</a>' if rk[4] else '<span></span>'
        nav = f'\n    <nav class="wrap item-nav" aria-label="{e(h1)}">{prev_l}{next_l}</nav>'
    rank_line = ''
    if rk:
        rank_line = (f'\n        <p class="rank-line">{e(ui("item.position", n=rk[1], total=rk[2]))} · '
                     f'<a href="{u(f"/ranking/{cat}/")}#{slug}">{e(h1)}</a></p>')
    ld_obj = {"@type": SCHEMA_OF.get(cat, 'Place'), "name": name, "description": why, "inLanguage": LANG,
              "url": SITE + u(path), "address": {"@type": "PostalAddress", "addressLocality": it['lugar'], "addressCountry": "ES"}}
    if coords(it):
        ld_obj["geo"] = {"@type": "GeoCoordinates", "latitude": coords(it)[0], "longitude": coords(it)[1]}
    if it.get('foto_real'):
        ld_obj["image"] = SITE + it['foto_real']['archivo']
    body = f'''
{crumbs(crumb)}

<main>
    <section class="wrap rank-hero item-hero">
        <p class="eyebrow">{e(short)} · {e(it['lugar'])}</p>
        <h1>{e(name)}</h1>
        <p class="lead-text">{e(why)}</p>
        <p class="item-spec">{e(spec)}</p>{rank_line}
    </section>{photo}
    <section class="wrap near item-near">
        <p class="label">{e(ui('rank.near'))}</p>
        <div class="near-grid">{tiles}</div>
    </section>{map_block}{plans_block}{src}{nav}
</main>
'''
    html_page = page(path, title, desc, [ld_obj, bc_ld(crumb)], body)
    write(path + 'index.html', html_page.replace('</body>', MAP_JS + '\n</body>') if map_block else html_page)


# ---------------- Directorio de marcas de lujo (motor) ----------------
BRAND_ORDER = ['Ferrari', 'Lamborghini', 'Aston Martin', 'Bentley', 'Rolls-Royce', 'McLaren']
CITY_SLUG = {'Madrid': 'madrid', 'Barcelona': 'barcelona', 'Marbella': 'marbella', 'Valencia': 'valencia'}

DIR_SCRIPT = '''
<script>
(function () {
    var buttons = document.querySelectorAll('[data-ciudad]');
    var cards = document.querySelectorAll('.dealer');
    var sections = document.querySelectorAll('.dir-brand');
    function apply(c) {
        cards.forEach(function (el) { el.hidden = !(c === 'todas' || el.dataset.c === c); });
        sections.forEach(function (sec) { sec.hidden = !sec.querySelector('.dealer:not([hidden])'); });
        buttons.forEach(function (b) { b.setAttribute('aria-pressed', String(b.dataset.ciudad === c)); });
    }
    buttons.forEach(function (b) { b.addEventListener('click', function () { apply(b.dataset.ciudad); }); });
    var c = new URLSearchParams(location.search).get('ciudad');
    if (c && document.querySelector('[data-ciudad="' + c + '"]')) apply(c);
})();
</script>'''


def build_directory():
    data = load('concesionarios/lujo.json')
    rows = data['concesionarios']
    cities = sorted({r['ciudad'] for r in rows}, key=lambda c: list(CITY_SLUG).index(c) if c in CITY_SLUG else 99)
    chips = f'<button type="button" data-ciudad="todas" aria-pressed="true">{e(ui("zone.todas"))}</button>' + ''.join(
        f'<button type="button" data-ciudad="{CITY_SLUG.get(c, c.lower())}" aria-pressed="false">{e(c)}</button>'
        for c in cities)
    sections = ''
    for brand in BRAND_ORDER:
        dealers = [r for r in rows if r['marca'] == brand]
        if not dealers:
            continue
        bid = re.sub('[^a-z]', '', brand.lower())
        cards = ''
        for r in dealers:
            ok = r['estado'].startswith(('verificado', 'contrastado', 'dirección verificada'))
            badge = (f'<span class="badge ok">{e(ui("dir.verified"))}</span>' if ok
                     else f'<span class="badge">{e(ui("dir.unverified"))}</span>')
            if r.get('direccion'):
                lines = [f'<p class="addr">{e(r["direccion"])}</p>']
            else:
                lines = [f'<p class="addr muted">{e(ui("dir.noaddr"))}</p>']
            if r.get('telefono'):
                digits = re.sub(r'[^+0-9]', '', r['telefono'])
                lines.append(f'<p class="tel"><a href="tel:{digits}">{e(r["telefono"])}</a></p>')
            if r.get('horario'):
                lines.append(f'<p class="muted">{e(tr(r["horario"]))}</p>')
            if r.get('notas'):
                lines.append(f'<p class="muted">{e(tr(r["notas"]))}</p>')
            slug = CITY_SLUG.get(r['ciudad'], r['ciudad'].lower())
            cards += (f'\n            <li class="dealer" id="{r["id"]}" data-c="{slug}">'
                      f'\n                <p class="city">{e(r["ciudad"])} {badge}</p>'
                      f'\n                <h3>{e(r["nombre"])}</h3>'
                      f'\n                {"".join(lines)}\n            </li>')
        sections += (f'\n    <section class="wrap dir-brand" aria-labelledby="m-{bid}">'
                     f'\n        <h2 id="m-{bid}">{e(brand)}</h2>'
                     f'\n        <ul class="dealers">{cards}\n        </ul>\n    </section>')
    crumb = [(ui('crumb.home'), u(HOME)), (t(CATS['motor']['corto']), u('/ranking/motor/')), (ui('dir.crumb'), None)]
    ld_items = []
    for n, r in enumerate([r for r in rows if r.get('direccion')], 1):
        item = {"@type": "AutoDealer", "name": r['nombre'], "brand": {"@type": "Brand", "name": r['marca']},
                "address": {"@type": "PostalAddress", "streetAddress": r['direccion'], "addressCountry": "ES"}}
        if r.get('telefono'):
            item["telephone"] = r['telefono']
        if coords(r):
            item["geo"] = {"@type": "GeoCoordinates", "latitude": r['coordenadas']['lat'],
                           "longitude": r['coordenadas']['lon']}
        ld_items.append({"@type": "ListItem", "position": n, "item": item})
    itemlist = {"@type": "ItemList", "name": ui('dir.title'), "inLanguage": LANG, "itemListElement": ld_items}
    body = f'''
{crumbs(crumb)}

<main>
    <section class="wrap rank-hero">
        <p class="eyebrow">{e(ui('dir.eyebrow', updated=data['actualizado']))}</p>
        <h1>{e(ui('dir.h1'))}</h1>
        <p class="lead-text">{e(ui('dir.lead'))}</p>
        <div class="chips left" role="group" aria-label="{e(ui('dir.filter_aria'))}">{chips}</div>
    </section>
{sections}
    <section class="wrap method">
        <div class="box">
            <div>
                <p class="eyebrow">{e(ui('dir.about'))}</p>
                <p class="txt">{e(ui('dir.about_txt'))}</p>
            </div>
            <a href="{u('/ranking/motor/')}">{e(ui('dir.back'))}</a>
        </div>
    </section>
</main>
'''
    html_page = page('/motor/marcas/', f'{ui("dir.title")} · Mejor Imposible', ui('dir.desc'), [itemlist, bc_ld(crumb)], body)
    write('/motor/marcas/index.html', html_page.replace('</body>', DIR_SCRIPT + '\n</body>'))


# ---------------- Home ----------------
def build_home():
    chips = ''.join(f'\n            <a href="{u(f"/ranking/{s}/")}">{e(t(CATS[s]["corto"]))}</a>' for s in HOME_CHIPS)
    strips = ''
    for slug, key, hid in HOME_STRIPS:
        entries, _ = ranking_entries(slug)
        lis = ''.join(
            f'\n                    <li><a href="{item_url(en["item"]["id"])}">{ph_box(en["item"], STRIP_TONES[i])}<div class="row"><span class="n">{i+1:02d}</span><span><span class="name">{e(en["nombre"])}</span><span class="place">{e(en["lugar"])}</span></span></div></a></li>'
            for i, en in enumerate(entries[:5]))
        strips += f'''
        <section class="wrap strip" aria-labelledby="{hid}">
            <div class="strip-head">
                <h2 id="{hid}">{e(ui('home.strip_' + key))}</h2>
                <a href="{u(f"/ranking/{slug}/")}">{e(ui('home.strip_full'))}</a>
            </div>
            <div class="strip-scroll">
                <ol>{lis}
                </ol>
            </div>
        </section>
'''
    cards = ''.join(
        f'\n                <a href="{u("/planes/" + p["slug"] + "/")}">{ph_box(plan_cover(p), "t3")}<p class="meta">{e(t(p["meta_corta"]))}</p><p class="ptitle">{e(t(p["titulo"]))}</p></a>'
        for p in all_plans())
    golf = u('/ranking/golf/')
    ENTRY_GOLF = ranking_entries('golf')[0][0]['item']
    body = f'''
<main>
    <section class="wrap hero">
        <p class="eyebrow">{e(ui('home.eyebrow'))}</p>
        <h1>{e(ui('home.h1'))}</h1>
        <p class="lead">{e(ui('home.lead'))}</p>
        <nav class="chips" aria-label="{e(ui('home.cats_aria'))}">{chips}
        </nav>
    </section>

    <section class="wrap" aria-label="{e(ui('home.featured_aria'))}">
        <a class="featured" href="{golf}">
            {photo_img(ENTRY_GOLF, eager=True, cls='cover')}
            <span class="kicker">{e(ui('home.kicker'))}</span>
            <span class="title">{e(t(CATS['golf']['titulo']))}</span>
            <span class="cta">{e(ui('home.cta'))}</span>
        </a>
    </section>

    <div id="rankings">{strips}    </div>

    <section id="planes" class="plans" aria-labelledby="planes-h">
        <div class="wrap">
            <p class="eyebrow">{e(ui('nav.plans'))}</p>
            <h2 id="planes-h">{e(ui('home.plans_h'))}</h2>
            <p class="lead">{e(ui('home.plans_lead'))}</p>
            <div class="plan-grid">{cards}
            </div>
        </div>
    </section>

    <section class="wrap trust">
        <h2>{ui('home.trust_h')}</h2>
        <a href="{u('/metodologia/')}">{e(ui('home.trust_link'))}</a>
    </section>
</main>
'''
    site = {"@type": "WebSite", "name": "Mejor Imposible", "url": SITE + prefix(LANG) + '/', "inLanguage": LANG}
    write(HOME, page(HOME, ui('home.title'), ui('home.desc'), [site], body))


# ---------------- Metodología y destinos ----------------
def build_method():
    m = load('metodologia.json')
    crumb = [(ui('crumb.home'), u(HOME)), (ui('nav.method'), None)]
    secs = ''
    for s in m['secciones']:
        paras = ''.join(f'\n            <p>{e(t(p))}</p>' for p in s['parrafos'])
        secs += (f'\n    <section class="wrap prose" id="{s["id"]}" aria-labelledby="h-{s["id"]}">'
                 f'\n        <h2 id="h-{s["id"]}">{e(t(s["titulo"]))}</h2>{paras}\n    </section>')
    lis = ''
    for f in m['fuentes']:
        txt = e(t(f['texto']))
        if f.get('url'):
            txt = f'<a href="{e(f["url"])}" rel="noopener">{txt}</a>'
        lis += f'\n            <li><strong>{e(t(CATS[f["cat"]]["corto"]))}.</strong> {txt}</li>'
    body = f'''
{crumbs(crumb)}

<main>
    <section class="wrap rank-hero">
        <p class="eyebrow">{e(ui('method.eyebrow', updated=t(m['actualizado'])))}</p>
        <h1>{e(t(m['titulo']))}</h1>
        <p class="lead-text">{e(t(m['lead']))}</p>
    </section>
{secs}
    <section class="wrap prose" id="fuentes" aria-labelledby="h-fuentes">
        <h2 id="h-fuentes">{e(t(m['fuentes_titulo']))}</h2>
        <ul class="sources">{lis}
        </ul>
    </section>
</main>
'''
    write('/metodologia/index.html', page('/metodologia/', f'{t(m["titulo"])} · Mejor Imposible', t(m['meta']),
                                           [{"@type": "WebPage", "name": t(m['titulo']), "inLanguage": LANG}, bc_ld(crumb)], body))


def build_destinos():
    crumb = [(ui('crumb.home'), u(HOME)), (ui('dest.h1'), None)]
    plans = all_plans()
    sections = ''
    for zk in ZONE_KEYS[1:]:
        counts = [(c, sum(1 for i in ITEMS.values() if i['categoria'] == c and i['zona'] == zk)) for c in HOME_CHIPS]
        counts = [(c, n) for c, n in counts if n]
        if not counts:
            continue
        name = ui('dest.resto') if zk == 'resto' else ui('zone.' + zk)
        chips = ''.join(f'\n            <a href="{u(f"/ranking/{c}/")}?zona={zk}">{e(t(CATS[c]["corto"]))} · {n}</a>' for c, n in counts)
        zplans = [p for p in plans if p['zona'] == zk]
        plan_html = ''
        if zplans:
            plan_chips = ''.join(f'\n            <a href="{u("/planes/" + p["slug"] + "/")}">{e(t(p["titulo"]))}</a>' for p in zplans)
            plan_html = f'\n        <p class="label">{e(ui("nav.plans"))}</p>\n        <nav class="chips" aria-label="{e(ui("nav.plans"))}">{plan_chips}\n        </nav>'
        sections += f'''
    <section class="wrap dir-brand" id="{zk}" aria-labelledby="z-{zk}">
        <h2 id="z-{zk}">{e(name)}</h2>
        <p class="label">{e(ui('dest.rankings'))}</p>
        <nav class="chips" aria-label="{e(ui('dest.rankings'))}">{chips}
        </nav>{plan_html}
    </section>'''
    body = f'''
{crumbs(crumb)}

<main>
    <section class="wrap rank-hero">
        <h1>{e(ui('dest.h1'))}</h1>
        <p class="lead-text">{e(ui('dest.lead'))}</p>
    </section>
{sections}
</main>
'''
    write('/destinos/index.html', page('/destinos/', f'{ui("dest.title")} · Mejor Imposible', ui('dest.desc'),
                                        [{"@type": "CollectionPage", "name": ui('dest.title'), "inLanguage": LANG}, bc_ld(crumb)], body))


PAGE_PATHS = ([HOME] + [f'/ranking/{c}/' for c in CATS] + [f'/planes/{p["slug"]}/' for p in all_plans()]
              + ['/motor/marcas/', '/metodologia/', '/destinos/']
              + ['/ranking/' + r + '/' for r in ITEMS])


# ---------------- Sitemap ----------------
def build_sitemap():
    today = datetime.date.today().isoformat()
    urls = ''
    for path in PAGES:
        loc = lambda c, path=path: SITE + prefix(c) + path
        for c in PUBLISHED:
            alts = ''.join(f'\n    <xhtml:link rel="alternate" hreflang="{a}" href="{loc(a)}"/>' for a in PUBLISHED)
            alts += f'\n    <xhtml:link rel="alternate" hreflang="x-default" href="{loc("es")}"/>'
            urls += f'\n  <url>\n    <loc>{loc(c)}</loc>\n    <lastmod>{today}</lastmod>{alts}\n  </url>'
    xml = ('<?xml version="1.0" encoding="UTF-8"?>\n'
           '<!-- Sitemap del portal nuevo. No se referencia desde robots.txt ni sitemap.xml hasta quitar el noindex. -->\n'
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:xhtml="http://www.w3.org/1999/xhtml">'
           f'{urls}\n</urlset>\n')
    with open(os.path.join(ROOT, 'sitemap-portal.xml'), 'w', encoding='utf-8', newline='\n') as f:
        f.write(xml)


if __name__ == '__main__':
    for lang in PUBLISHED:
        LANG = lang
        build_home()
        for slug in CATS:
            build_rank(slug)
        for ref in ITEMS:
            build_item(ref)
        for fn in os.listdir(os.path.join(DATA, 'planes')):
            build_plan(fn[:-5])
        build_directory()
        build_method()
        build_destinos()
    build_sitemap()
    bad = False
    for lang in PUBLISHED:
        if MISSING[lang]:
            bad = True
            pend = os.path.join(DATA, 'i18n', f'_pendiente-{lang}.json')
            with open(pend, 'w', encoding='utf-8', newline='\n') as f:
                json.dump({k: '' for k in sorted(MISSING[lang])}, f, ensure_ascii=False, indent=1)
            print(f'AVISO {lang}: faltan {len(MISSING[lang])} traducciones -> {os.path.relpath(pend, ROOT)}')
    print('portal generado' + (' (con traducciones pendientes)' if bad else ''))
