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
              'bodegas': 'Winery', 'spas': 'HealthAndBeautyBusiness', 'vida-nocturna': 'NightClub', 'bares-de-cocteleria': 'BarOrPub', 'alojamientos-historicos': 'Hotel', 'museos': 'Museum', 'helicopteros': 'Organization'}
HOME_STRIPS = [('hoteles-de-lujo', 'hoteles', 'r-hoteles'), ('golf', 'golf', 'r-golf'),
               ('restaurantes', 'restaurantes', 'r-mesas'), ('casas-de-lujo', 'casas', 'r-casas')]
HOME_CHIPS = ['hoteles-de-lujo', 'golf', 'restaurantes', 'casas-de-lujo', 'compras-de-lujo', 'bodegas', 'spas', 'yates-y-calas', 'motor', 'vida-nocturna', 'bares-de-cocteleria', 'alojamientos-historicos', 'helicopteros', 'museos']


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
        <a href="@@SEARCH@@">@@N_SEARCH@@</a>
        <a href="@@TRIP@@">@@N_TRIP@@<span class="trip-count" hidden></span></a>
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
            <a href="@@EVENTS@@">@@N_EVENTS@@</a>
            <a href="@@CHANGES@@">@@N_CHANGES@@</a>
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


ORG_ID = SITE + '/#organization'
SITE_ID = SITE + '/#website'
# Perfiles oficiales de la marca (LinkedIn, Instagram, Wikidata...). Añadirlos aquí los emite en sameAs.
SAME_AS = []


def entity_nodes():
    """Organización y sitio web: se emiten en todas las páginas para que los @id de publisher/isPartOf se resuelvan."""
    org = {"@type": "Organization", "@id": ORG_ID, "name": "Mejor Imposible", "url": SITE + '/',
           "logo": {"@type": "ImageObject", "url": SITE + '/img/logo_mi_transparent.png'}}
    if SAME_AS:
        org["sameAs"] = SAME_AS
    person = {"@type": "Person", "@id": SITE + '/#autor', "name": "Emilio Rodríguez García", "alternateName": "Emirodgar",
              "sameAs": ["https://x.com/emirodgar", "https://www.linkedin.com/in/emirodgar/"]}
    site = {"@type": "WebSite", "@id": SITE_ID, "name": "Mejor Imposible", "url": SITE + prefix(LANG) + '/',
            "inLanguage": LANG, "publisher": {"@id": ORG_ID}}
    return [org, person, site]


def webpage(kind, path, name, desc, **extra):
    """Nodo WebPage (o subtipo) de la página, enlazado al sitio y a la organización."""
    return {"@type": kind, "@id": SITE + u(path) + '#webpage', "url": SITE + u(path), "name": name,
            "description": desc, "inLanguage": LANG, "isPartOf": {"@id": SITE_ID}, "publisher": {"@id": ORG_ID},
            "author": {"@id": SITE + '/#autor'}, "dateModified": datetime.date.today().isoformat(), **extra}


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
           '@@LD@@': ld(*lds, *entity_nodes()), '@@HOME@@': u(HOME), '@@DEST@@': u('/destinos/'), '@@SEARCH@@': u('/buscar/'), '@@TRIP@@': u('/mi-viaje/'), '@@N_TRIP@@': e(ui('nav.trip')), '@@N_SEARCH@@': e(ui('nav.search')), '@@METHOD@@': u('/metodologia/'), '@@CHANGES@@': u('/novedades/'), '@@EVENTS@@': u('/eventos/'), '@@N_EVENTS@@': e(ui('nav.events')), '@@N_CHANGES@@': e(ui('nav.changes')),
           '@@ARIA_MAIN@@': e(ui('aria.main')), '@@ARIA_LANG@@': e(ui('aria.lang')), '@@ARIA_FOOT@@': e(ui('aria.footer')),
           '@@N_RANK@@': e(ui('nav.rankings')), '@@N_PLANS@@': e(ui('nav.plans')), '@@N_DEST@@': e(ui('nav.destinations')),
           '@@N_PORSCHE@@': e(ui('nav.porsche')), '@@N_METHOD@@': e(ui('nav.method')), '@@LANG@@': lang_html(path)}
    h, f = HEAD, FOOT
    for k, v in rep.items():
        h, f = h.replace(k, v), f.replace(k, v)
    return h + body + credits_html() + f + (SCRIPT if 'data-zone' in body else '') + '\n<script src="/assets/viaje.js" defer></script>\n</body>\n</html>\n'


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


def item_extra(cat, f):
    """Propiedades schema.org (premios y datos de ficha) de un lugar, a partir de su ficha."""
    awards, props = [], []

    def prop(name, v, unit=None):
        p = {"@type": "PropertyValue", "name": name, "value": v}
        if unit:
            p["unitCode"] = unit
        props.append(p)

    if f.get('estrellas'):
        awards.append(f"Michelin: {fval(f['estrellas'])}")
    if f.get('llaves'):
        awards.append(f"Michelin: {fval(f['llaves'])}")
    for k in ('galardon', 'puesto'):
        if f.get(k):
            awards.append(fval(f[k]))
    if f.get('hoyos'):
        prop('Holes', f['hoyos'])
    if f.get('par'):
        prop('Par', f['par'])
    if f.get('arquitecto'):
        prop('Architect', f['arquitecto'])
    if f.get('denominacion'):
        prop('Appellation', f['denominacion'])
    if f.get('anio'):
        prop('Year opened', f['anio'])
    if f.get('longitud'):
        prop('Track length', float(str(f['longitud']).replace(',', '.')), 'KMT')
    if f.get('tipo'):
        prop('Type', fval(f['tipo']))
    out = {}
    if awards:
        out["award"] = awards
    if props:
        out["additionalProperty"] = props
    if f.get('chef'):
        out["employee"] = {"@type": "Person", "name": f['chef'], "jobTitle": "Chef"}
    return out


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


def others_html(slug):
    """Apartado "Otros": lugares fuera del TOP10 con premio o presentes en los planes (ítem con ficha o solo nombre)."""
    rk = load(f'rankings/{slug}.json')
    if not rk.get('otros'):
        return ''
    guia = load('michelin/guia-2026.json')['restaurantes'] if slug == 'restaurantes' else []
    plans = {p['slug']: p for p in all_plans()}
    rows = ''
    for o in rk['otros']:
        if o.get('ref'):
            it = ITEMS[o['ref']]
            name, place = it['nombre'], it['lugar']
            m = next((r for r in guia if r.get('ref') == o['ref']), None)
            href = item_url(o['ref'])
        else:
            m = next((r for r in guia if r['nombre'] == o['nombre']), None)
            name, place, href = o['nombre'], (m['ciudad'] if m else o.get('lugar', '')), None
        stars = m['estrellas'] if m else 0
        badge = ui('michelin.star1' if stars == 1 else 'michelin.star2', n=stars) if stars else ''
        notes = ' · '.join(([badge] if badge else []) + [
            ui('rank.others_plan', plan=t(plans[sl]['titulo'])) for sl in o.get('planes', [])])
        inner = (f'<span class="nm">{e(name)}</span><span class="pl">{e(place)}</span>'
                 f'<span class="note">{e(notes)}</span>')
        if href:
            rows += f'''
            <li><a href="{href}">{inner}<span class="arrow" aria-hidden="true">→</span></a></li>'''
        else:
            rows += f'''
            <li><div class="row">{inner}</div></li>'''
    return f'''
    <section class="wrap rest others-more" id="otros" aria-labelledby="otros-h">
        <h2 id="otros-h">{e(ui('rank.others_h'))}</h2>
        <p class="others-lead">{e(ui('rank.others_lead'))}</p>
        <ol class="compact-list">{rows}
        </ol>
    </section>
'''


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
                  if slug == 'motor' else
                  f'\n        <p class="hero-link"><a href="{u("/ranking/compras-de-lujo/tiendas/")}">{e(ui("rank.shops_link"))}</a></p>'
                  if slug == 'compras-de-lujo' else '')
    crumb = [(ui('crumb.home'), u(HOME)), (ui('crumb.rankings'), u(HOME) + '#rankings'), (short, None)]
    schema = CAT_SCHEMA.get(slug)
    ld_items = []
    for n, en in enumerate(entries, 1):
        li = {"@type": "ListItem", "position": n, "name": en['nombre'], "url": SITE + item_url(en['item']['id'])}
        if schema:
            li["item"] = {"@type": schema, "name": en['nombre'],
                          "address": {"@type": "PostalAddress", "addressLocality": en['lugar'], "addressCountry": "ES"}}
            if coords(en['item']):
                li["item"]["geo"] = {"@type": "GeoCoordinates", "latitude": coords(en['item'])[0],
                                     "longitude": coords(en['item'])[1]}
            li["item"].update(item_extra(slug, en['item']['ficha']))
        ld_items.append(li)
    itemlist = {"@type": "ItemList", "name": h1, "inLanguage": LANG, "itemListOrder": "https://schema.org/ItemListOrderAscending",
                "numberOfItems": len(entries), "itemListElement": ld_items}
    itemlist = webpage('CollectionPage', f'/ranking/{slug}/', h1, ui('rank.desc', h1=h1), mainEntity=itemlist)
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
{others_html(slug)}
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
    'compras': '<path d="M5 8h14l-1 12H6z"></path><path d="M9 8V6a3 3 0 0 1 6 0v2"></path>',
    'cena': '<path d="M7 3v8"></path><path d="M5 3v4a2 2 0 0 0 4 0V3"></path><path d="M7 11v10"></path><path d="M17 21V3c-2 1-3 4-3 7h3"></path>',
    'descanso': '<path d="M12 3c3 4 3 8 0 11-3-3-3-7 0-11z"></path><path d="M4 17c4 0 6 2 8 4 2-2 4-4 8-4"></path>',
    'mesa': '<path d="M7 3v8"></path><path d="M5 3v4a2 2 0 0 0 4 0V3"></path><path d="M7 11v10"></path><path d="M17 21V3c-2 1-3 4-3 7h3"></path>',
    'bodega': '<path d="M8 3h8l-1 7a3 3 0 0 1-6 0z"></path><path d="M12 13v8"></path><path d="M8 21h8"></path>',
    'barco': '<path d="M3 17l2 3h14l2-3z"></path><path d="M12 3v11"></path><path d="M12 4l6 8h-6"></path>',
    'cala': '<path d="M3 9c3 0 3 2 6 2s3-2 6-2 3 2 6 2"></path><path d="M3 15c3 0 3 2 6 2s3-2 6-2 3 2 6 2"></path>',
}
# tipo de paso de la ruta -> categoría de ranking enlazada (None: ancla "cómo llegar")
ROUTE_CAT = {'llegada': None, 'coche': 'motor', 'hotel': 'hoteles-de-lujo', 'golf': 'golf', 'cena': 'restaurantes',
             'descanso': 'spas', 'mesa': 'restaurantes', 'bodega': 'bodegas', 'barco': 'yates-y-calas', 'cala': 'yates-y-calas', 'compras': 'compras-de-lujo'}
# el paso destacado (círculo oscuro) de la ruta
HIGHLIGHT = ('golf', 'bodega', 'cala', 'mesa', 'compras')


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

    def add(name, c, kind, icon):
        if c and name not in seen:
            seen.add(name)
            pts.append({'n': name, 'lat': c[0], 'lon': c[1], 'k': kind, 'i': icon})
    for r in p['llegar']:
        rn = r['nombre']['es']
        a = next((a for a in sorted(AIRPORTS, key=lambda x: -len(x['nombre'])) if a['nombre'] in rn or rn in a['nombre']), None)
        if a:
            add(t(r['nombre']), coords(a), 'a', 'airport')
    for d in p['dias']:
        for s in d['pasos']:
            it = ITEMS.get(s.get('ref'))
            if it:
                add(it['nombre'], coords(it), 'p', s['ref'].split('/')[0])
    return pts


MAP_JS = '''
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.css">
<script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.js"></script>
<script>
(function () {
    var el = document.getElementById('plan-map');
    if (!el || !window.L) return;
    var G = {
        'hoteles-de-lujo': 'M2 4v16M2 8h18a2 2 0 0 1 2 2v10M2 17h20M6 8v9',
        hotel: 'M2 4v16M2 8h18a2 2 0 0 1 2 2v10M2 17h20M6 8v9',
        'alojamientos-historicos': 'M3 22h18M6 18v-7M10 18v-7M14 18v-7M18 18v-7M12 2l8 5H4z',
        restaurantes: 'M3 2v7c0 1.1.9 2 2 2h4a2 2 0 0 0 2-2V2M7 2v20M21 15V2a5 5 0 0 0-5 5v6c0 1.1.9 2 2 2h3zm0 0v7',
        restaurante: 'M3 2v7c0 1.1.9 2 2 2h4a2 2 0 0 0 2-2V2M7 2v20M21 15V2a5 5 0 0 0-5 5v6c0 1.1.9 2 2 2h3zm0 0v7',
        golf: 'M12 3v14M12 3l7 3.5-7 3.5M7 19.5c0-1.1 2.2-2 5-2s5 .9 5 2-2.2 2-5 2-5-.9-5-2z',
        'casas-de-lujo': 'M15 21v-8a1 1 0 0 0-1-1h-4a1 1 0 0 0-1 1v8M3 10a2 2 0 0 1 .7-1.5l7-6a2 2 0 0 1 2.6 0l7 6A2 2 0 0 1 21 10v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z',
        bodegas: 'M8 22h8M7 10h10M12 15v7M12 15a5 5 0 0 0 5-5c0-2-.5-4-2-8H9c-1.5 4-2 6-2 8a5 5 0 0 0 5 5z',
        spas: 'M11 20A7 7 0 0 1 9.8 6.1C15.5 5 17 4.5 19 2c1 2 2 4.2 2 8 0 5.5-4.8 10-10 10zM2 21c0-3 1.9-5.4 5.1-6C9.5 14.5 12 13 13 12',
        'yates-y-calas': 'M22 18H2a4 4 0 0 0 4 4h12a4 4 0 0 0 4-4zM21 14L10 2 3 14zM10 2v16',
        motor: 'M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20zM12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6zM12 2v7M12 15v7M2 12h7M15 12h7',
        'compras-de-lujo': 'M6 2L3 6v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6l-3-4zM3 6h18M16 10a4 4 0 0 1-8 0',
        'vida-nocturna': 'M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9z',
        helicopteros: 'M3 5h18M12 5v4M5 12h9a5 5 0 0 1 5 5v1H8a3 3 0 0 1-3-3zM19 14h3M8 21h9',
        museos: 'M3 3h18v18H3zM8 8h8v8H8z',
        'bares-de-cocteleria': 'M8 22h8M12 11v11M19 3l-7 8-7-8z',
        airport: 'M17.8 19.2L16 11l3.5-3.5C21 6 21.5 4 21 3c-1-.5-3 0-4.5 1.5L13 8 4.8 6.2c-.5-.1-.9.1-1.1.5l-.3.5c-.2.5-.1 1 .3 1.3L9 12l-2 3H4l-1 1 3 2 2 3 1-1v-3l3-2 3.5 5.3c.3.4.8.5 1.3.3l.5-.2c.4-.3.6-.7.5-1.2z'
    };
    var pts = JSON.parse(el.dataset.points);
    var map = L.map(el, { scrollWheelZoom: false, zoomControl: false });
    L.control.zoom({ position: 'bottomright' }).addTo(map);
    L.tileLayer('https://{s}.basemaps.cartocdn.com/rastertiles/light_all/{z}/{x}/{y}{r}.png?key=cb1_2izw_1_55d93b51ded1dcecfa044181', {
        subdomains: 'abcd', maxZoom: 19,
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/attributions">CARTO</a>'
    }).addTo(map);
    var ll = pts.map(function (p) {
        var main = p.k !== 'a';
        var svg = '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="' + (G[p.i] || G.hotel) + '"/></svg>';
        var icon = L.divIcon({ className: 'mi-pin' + (main ? ' mi-pin-main' : ''), html: svg, iconSize: main ? [36, 36] : [30, 30], iconAnchor: main ? [18, 18] : [15, 15] });
        L.marker([p.lat, p.lon], { icon: icon, keyboard: false, riseOnHover: true, zIndexOffset: main ? 500 : 0 })
            .bindTooltip(p.n, { direction: 'top', offset: [0, main ? -18 : -15], className: 'mi-tip' }).addTo(map);
        return [p.lat, p.lon];
    });
    if (ll.length > 1) map.fitBounds(ll, { padding: [48, 48], maxZoom: 12 }); else map.setView(ll[0], 11);
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
        li = {"@type": "ListItem", "position": len(route_ld) + 1, "name": f'{label}: {name}'}
        if s.get('ref'):
            ref_it = ITEMS[s['ref']]
            li["url"] = SITE + item_url(s['ref'])
            li["item"] = {"@type": SCHEMA_OF.get(ref_it['categoria'], 'Place'), "name": ref_it['nombre'],
                          "url": SITE + item_url(s['ref'])}
        route_ld.append(li)

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
    trip = {"@type": "TouristTrip", "@id": SITE + u(f'/planes/{slug}/') + '#trip', "name": title, "inLanguage": LANG,
            "description": t(p['lead']), "url": SITE + u(f'/planes/{slug}/'),
            "touristType": t(p.get("tipo_turista", "Golf")), "provider": {"@id": ORG_ID},
            "mainEntityOfPage": {"@id": SITE + u(f'/planes/{slug}/') + '#webpage'},
            "itinerary": {"@type": "ItemList", "numberOfItems": len(route_ld), "itemListElement": route_ld}}
    if len(p['dias']) > 0:
        trip["duration"] = f"P{len(p['dias'])}D"
    cover = plan_cover(p)
    if cover and cover.get('foto_real'):
        trip["image"] = SITE + cover['foto_real']['archivo']
    plan_page = webpage('WebPage', f'/planes/{slug}/', f'{ui("plan.title", title=title)}', f'{t(p["meta"])}: {t(p["lead"])}',
                        mainEntity={"@id": trip["@id"]})
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
                     f'{t(p["meta"])}: {t(p["lead"])}', [plan_page, trip, bc_ld(crumb)], body)
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
            pts.append({'n': name, 'lat': c[0], 'lon': c[1], 'k': 'a', 'i': 'airport' if tipo == 'aeropuerto' else (entry['ref'].split('/')[0] if entry.get('ref') else tipo)})
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
    pts = [{'n': name, 'lat': coords(it)[0], 'lon': coords(it)[1], 'k': 'p', 'i': cat}] if coords(it) else []
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
    ld_obj = {"@type": it.get('schema') or SCHEMA_OF.get(cat, 'Place'), "name": name, "description": why, "inLanguage": LANG,
              "url": SITE + u(path), "address": {"@type": "PostalAddress", "addressLocality": it['lugar'], "addressCountry": "ES"}}
    if coords(it):
        ld_obj["geo"] = {"@type": "GeoCoordinates", "latitude": coords(it)[0], "longitude": coords(it)[1]}
    ld_obj["@id"] = SITE + u(path) + '#entity'
    ld_obj["mainEntityOfPage"] = {"@id": SITE + u(path) + '#webpage'}
    ld_obj.update(item_extra(cat, it['ficha']))
    if it.get('foto_real'):
        fr = it['foto_real']
        img = {"@type": "ImageObject", "url": SITE + fr['archivo'], "creditText": fr.get('autor', '')}
        if fr.get('autor'):
            img["creator"] = {"@type": "Person", "name": fr['autor']}
        if fr.get('licencia_url'):
            img["license"] = fr['licencia_url']
        ld_obj["image"] = img
    page_node = webpage('ItemPage', path, title, desc, mainEntity={"@id": ld_obj["@id"]})
    if it.get('fuentes'):
        page_node["citation"] = it['fuentes']
    if it.get('foto_real'):
        page_node["primaryImageOfPage"] = {"@id": SITE + u(path) + '#image'}
        ld_obj["image"]["@id"] = SITE + u(path) + '#image'
    ctx_block = ''
    if it.get('contexto'):
        paras = ''.join(f'\n            <p>{e(t(c))}</p>' for c in it['contexto'])
        ctx_block = f'\n    <section class="wrap prose item-ctx">\n        <h2>{e(ui("item.context"))}</h2>{paras}\n    </section>'
    body = f'''
{crumbs(crumb)}

<main>
    <section class="wrap rank-hero item-hero">
        <p class="eyebrow">{e(short)} · {e(it['lugar'])}</p>
        <h1>{e(name)}</h1>
        <p class="lead-text">{e(why)}</p>
        <p class="item-spec">{e(spec)}</p>{rank_line}
        {save_btn(it['id'])}
    </section>{photo}{ctx_block}
    <section class="wrap near item-near">
        <p class="label">{e(ui('rank.near'))}</p>
        <div class="near-grid">{tiles}</div>
    </section>{map_block}{plans_block}{src}{nav}
</main>
'''
    html_page = page(path, title, desc, [page_node, ld_obj, bc_ld(crumb)], body)
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
        bid = re.sub('[^a-z]', '', brand.lower().replace('&', 'and'))
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
    itemlist = webpage('CollectionPage', '/motor/marcas/', ui('dir.title'), ui('dir.desc'), mainEntity=itemlist)
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



# ---------------- Directorio de tiendas insignia (compras) ----------------
SHOP_BRANDS = ['Louis Vuitton', 'Hermès', 'Chanel', 'Cartier', 'Rolex', 'Gucci', 'Dior', 'Loewe', 'Prada', 'Bulgari', 'Tiffany & Co.']
SHOP_CITIES = {'Madrid': 'madrid', 'Barcelona': 'barcelona', 'Marbella': 'marbella', 'Palma': 'palma', 'Sevilla': 'sevilla', 'Bilbao': 'bilbao'}


def build_tiendas():
    data = load('tiendas/lujo.json')
    rows = data['tiendas']
    cities = sorted({r['ciudad'] for r in rows}, key=lambda c: list(SHOP_CITIES).index(c) if c in SHOP_CITIES else 99)
    chips = f'<button type="button" data-ciudad="todas" aria-pressed="true">{e(ui("zone.todas"))}</button>' + ''.join(
        f'<button type="button" data-ciudad="{SHOP_CITIES.get(c, c.lower())}" aria-pressed="false">{e(c)}</button>' for c in cities)
    sections = ''
    for brand in SHOP_BRANDS:
        stores = [r for r in rows if r['marca'] == brand]
        if not stores:
            continue
        bid = re.sub('[^a-z]', '', brand.lower().replace('&', 'and'))
        cards = ''
        for r in stores:
            ok = r['estado'].startswith(('verificado', 'contrastado'))
            badge = (f'<span class="badge ok">{e(ui("dir.verified"))}</span>' if ok else f'<span class="badge">{e(ui("dir.unverified"))}</span>')
            lines = [f'<p class="addr">{e(r["direccion"])}</p>']
            if r.get('telefono'):
                digits = re.sub(r'[^+0-9]', '', r['telefono'])
                lines.append(f'<p class="tel"><a href="tel:{digits}">{e(r["telefono"])}</a></p>')
            if r.get('horario'):
                lines.append(f'<p class="muted">{e(tr(r["horario"]))}</p>')
            if r.get('notas'):
                lines.append(f'<p class="muted">{e(tr(r["notas"]))}</p>')
            slug = SHOP_CITIES.get(r['ciudad'], r['ciudad'].lower())
            cards += (f'\n            <li class="dealer" id="{r["id"]}" data-c="{slug}">'
                      f'\n                <p class="city">{e(r["ciudad"])} {badge}</p>'
                      f'\n                <h3>{e(r["nombre"])}</h3>'
                      f'\n                {"".join(lines)}\n            </li>')
        sections += (f'\n    <section class="wrap dir-brand" aria-labelledby="m-{bid}">'
                     f'\n        <h2 id="m-{bid}">{e(brand)}</h2>'
                     f'\n        <ul class="dealers">{cards}\n        </ul>\n    </section>')
    crumb = [(ui('crumb.home'), u(HOME)), (t(CATS['compras-de-lujo']['corto']), u('/ranking/compras-de-lujo/')), (ui('shop.crumb'), None)]
    ld_items = []
    for n, r in enumerate(rows, 1):
        item = {"@type": "Store", "name": r['nombre'], "brand": {"@type": "Brand", "name": r['marca']},
                "address": {"@type": "PostalAddress", "streetAddress": r['direccion'], "addressCountry": "ES"}}
        if r.get('telefono'):
            item["telephone"] = r['telefono']
        if coords(r):
            item["geo"] = {"@type": "GeoCoordinates", "latitude": r['coordenadas']['lat'], "longitude": r['coordenadas']['lon']}
        ld_items.append({"@type": "ListItem", "position": n, "item": item})
    itemlist = {"@type": "ItemList", "name": ui('shop.title'), "inLanguage": LANG, "itemListElement": ld_items}
    body = f'''
{crumbs(crumb)}

<main>
    <section class="wrap rank-hero">
        <p class="eyebrow">{e(ui('shop.eyebrow', updated=data['actualizado']))}</p>
        <h1>{e(ui('shop.h1'))}</h1>
        <p class="lead-text">{e(ui('shop.lead'))}</p>
        <div class="chips left" role="group" aria-label="{e(ui('dir.filter_aria'))}">{chips}</div>
    </section>
{sections}
    <section class="wrap method">
        <div class="box">
            <div>
                <p class="eyebrow">{e(ui('dir.about'))}</p>
                <p class="txt">{e(ui('shop.about_txt'))}</p>
            </div>
            <a href="{u('/ranking/compras-de-lujo/')}">{e(ui('shop.back'))}</a>
        </div>
    </section>
</main>
'''
    path = '/ranking/compras-de-lujo/tiendas/'
    html_page = page(path, f'{ui("shop.title")} · Mejor Imposible', ui('shop.desc'), [itemlist, bc_ld(crumb)], body)
    write(path + 'index.html', html_page.replace('</body>', DIR_SCRIPT + '\n</body>'))


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
        <h1>{e(ui('home.eyebrow'))}.<br>{e(ui('home.h1'))}</h1>
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

{interests_home()}
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
    home_page = webpage('WebPage', HOME, ui('home.title'), ui('home.desc'))
    write(HOME, page(HOME, ui('home.title'), ui('home.desc'), [home_page], body))


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
    dataset = {"@type": "Dataset", "name": t(m['titulo']), "description": t(m['meta']), "inLanguage": LANG,
               "url": SITE + u('/metodologia/'), "creator": {"@id": ORG_ID}, "publisher": {"@id": ORG_ID},
               "spatialCoverage": {"@type": "Country", "name": "España"},
               "isBasedOn": [f['url'] for f in m['fuentes'] if f.get('url')],
               "hasPart": [{"@type": "ItemList", "name": t(CATS[c]['titulo']), "url": SITE + u(f'/ranking/{c}/')}
                           for c in CATS]}
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
                                           [webpage('AboutPage', '/metodologia/', t(m['titulo']), t(m['meta'])),
                                            dataset, bc_ld(crumb)], body))


def build_destinos():
    crumb = [(ui('crumb.home'), u(HOME)), (ui('dest.h1'), None)]
    plans = all_plans()
    sections = ''
    gchips = ''.join(f'\n            <a href="{u("/destinos/" + d["slug"] + "/")}">{e(tr(d["nombre"]))} · {len(dest_items(d))}</a>' for d in DESTS)
    guides = (f'    <section class="wrap dir-brand" aria-labelledby="g-guias">\n        <h2 id="g-guias">{e(ui("dest.guides_h"))}</h2>\n        <nav class="chips" aria-label="{e(ui("dest.guides_h"))}">{gchips}\n        </nav>\n    </section>')
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
{guides}
{sections}
</main>
'''
    write('/destinos/index.html', page('/destinos/', f'{ui("dest.title")} · Mejor Imposible', ui('dest.desc'),
                                        [webpage('CollectionPage', '/destinos/', ui('dest.title'), ui('dest.desc')), bc_ld(crumb)], body))


# ---------------- Guías por destino y buscador ----------------
DESTS = load('destinos.json')['destinos']


def dest_items(d):
    # lugares dentro del radio del destino; cada uno va al destino más cercano en proporción a su radio
    out = []
    for it in ITEMS.values():
        c = coords(it)
        if not c:
            continue
        best = min(((haversine_km(c, tuple(x['centro'])) / x['radio'], x['slug']) for x in DESTS), default=None)
        if best and best[0] <= 1 and best[1] == d['slug']:
            out.append(it)
    return out


def build_dest(d):
    items = dest_items(d)
    name = tr(d['nombre'])
    by_cat = {}
    for it in items:
        by_cat.setdefault(it['categoria'], []).append(it)
    for lst in by_cat.values():
        lst.sort(key=lambda i: (RANK_POS.get(i['id'], ('', 99))[1], i['nombre']))
    here = {'coordenadas': {'lat': d['centro'][0], 'lon': d['centro'][1]}, 'nombre': '', 'id': ''}
    ap = nearest(here, 'aeropuerto')
    ncat = len(by_cat)
    lead = ui('dest.guide.lead', c=len(items), k=ncat, a=ap['nombre'], m=ap['min']) if ap else ui('dest.guide.lead0', c=len(items), k=ncat)
    sections, ld_items, pts = '', [], []
    for cat in HOME_CHIPS:
        lst = by_cat.get(cat)
        if not lst:
            continue
        cards = ''
        for it in lst:
            rk = RANK_POS.get(it['id'])
            rank = f'<span class="badge ok">{e(ui("dest.rank", n=rk[1], t=rk[2]))}</span>' if rk else ''
            spec = spec_text(cat, it['ficha'])
            cards += (f'\n            <li class="dealer">\n                <p class="city">{e(it["lugar"])} {rank}</p>'
                      f'\n                <h3><a href="{item_url(it["id"])}">{e(it["nombre"])}</a></h3>'
                      f'\n                <p>{e(t(it["por_que"]))}</p>'
                      + (f'\n                <p class="muted">{e(spec)}</p>' if spec else '') + f'\n                {save_btn(it["id"])}\n            </li>')
            ld_items.append({"@type": "ListItem", "position": len(ld_items) + 1, "url": SITE + item_url(it['id']), "name": it['nombre']})
            c = coords(it)
            if c:
                pts.append({'n': it['nombre'], 'lat': c[0], 'lon': c[1], 'k': 'p', 'i': cat})
        sections += f'''
    <section class="wrap dir-brand" aria-labelledby="c-{cat}">
        <h2 id="c-{cat}"><a href="{u(f"/ranking/{cat}/")}">{e(t(CATS[cat]["corto"]))}</a></h2>
        <ul class="dealers">{cards}
        </ul>
    </section>'''
    if ap and ap.get('geo'):
        pts.append({'n': ap['nombre'], 'lat': ap['geo'][0], 'lon': ap['geo'][1], 'k': 'a', 'i': 'airport'})
    ids = {i['id'] for i in items}
    zplans = [p for p in all_plans() if any((s.get('ref') in ids) for dd in p['dias'] for s in dd['pasos'])]
    extra = ''
    if zplans:
        chips = ''.join(f'\n            <a href="{u("/planes/" + p["slug"] + "/")}">{e(t(p["titulo"]))}</a>' for p in zplans)
        extra += f'\n        <p class="label">{e(ui("nav.plans"))}</p>\n        <nav class="chips" aria-label="{e(ui("nav.plans"))}">{chips}\n        </nav>'
    links = ''
    if d.get('tiendas'):
        links += f'\n            <a href="{u("/ranking/compras-de-lujo/tiendas/")}?ciudad={d["tiendas"]}">{e(ui("dest.guide.shops"))}</a>'
    if d.get('concesionarios'):
        links += f'\n            <a href="{u("/motor/marcas/")}?ciudad={d["concesionarios"]}">{e(ui("dest.guide.dealers"))}</a>'
    if links:
        extra += f'\n        <p class="label">{e(ui("dest.guide.more"))}</p>\n        <nav class="chips" aria-label="{e(ui("dest.guide.more"))}">{links}\n        </nav>'
    mp = (f'<div class="map live" id="plan-map" role="region" aria-label="{e(ui("dest.guide.map_aria", n=name))}" '
          f'data-points="{e(json.dumps(pts, ensure_ascii=False))}"></div>') if pts else ''
    about = ''
    if d.get('contexto'):
        paras = ''.join(f'\n            <p>{e(t(c))}</p>' for c in d['contexto'])
        srcs = ''.join(f'<li><a href="{e(x)}" rel="noopener">{e(x.split("/")[2].replace("www.", ""))}</a></li>' for x in d.get('fuentes', []))
        about = (f'\n    <section class="wrap prose item-ctx">\n        <h2>{e(ui("dest.guide.about"))}</h2>{paras}'
                 + (f'\n        <ul class="sources">{srcs}</ul>' if srcs else '') + '\n    </section>')
    path = f'/destinos/{d["slug"]}/'
    crumb = [(ui('crumb.home'), u(HOME)), (ui('dest.h1'), u('/destinos/')), (name, None)]
    title = ui('dest.guide.title', n=name)
    desc = ui('dest.guide.desc', n=name)
    body = f'''
{crumbs(crumb)}

<main>
    <section class="wrap rank-hero">
        <p class="eyebrow">{e(ui('dest.guide.eyebrow'))}</p>
        <h1>{e(name)}</h1>
        <p class="lead-text">{e(lead)}</p>
    </section>
{about}
    <section class="wrap">{mp}</section>{sections}
    <section class="wrap dir-brand">{extra}
        <p><a href="{u('/destinos/')}">{e(ui('dest.guide.back'))}</a></p>
    </section>
</main>
'''
    lds = [webpage('CollectionPage', path, title, desc), {"@type": "ItemList", "name": title, "inLanguage": LANG, "itemListElement": ld_items}, bc_ld(crumb)]
    html_page = page(path, f'{title} · Mejor Imposible', desc, lds, body)
    write(path + 'index.html', html_page.replace('</body>', MAP_JS + '\n</body>') if mp else html_page)


def build_search():
    idx = []
    for it in ITEMS.values():
        cat = it['categoria']
        idx.append({'id': it['id'], 'n': it['nombre'], 'p': it['lugar'], 'c': cat, 'z': it['zona'], 'u': item_url(it['id']),
                    's': spec_text(cat, it['ficha']), 'w': t(it['por_que'])})
    idx.sort(key=lambda x: (HOME_CHIPS.index(x['c']) if x['c'] in HOME_CHIPS else 99, x['n']))
    write('/buscar/indice.json', json.dumps(idx, ensure_ascii=False, separators=(',', ':')))
    cat_opts = f'<option value="">{e(ui("search.all_cats"))}</option>' + ''.join(
        f'<option value="{c}">{e(t(CATS[c]["corto"]))}</option>' for c in HOME_CHIPS if c in CATS)
    zone_opts = ''.join(f'<option value="{"" if z == "todas" else z}">{e(ui("zone." + z))}</option>' for z in ZONE_KEYS)
    labels = {t(CATS[c]['corto']): c for c in HOME_CHIPS if c in CATS}
    cat_names = json.dumps({c: t(CATS[c]['corto']) for c in HOME_CHIPS if c in CATS}, ensure_ascii=False)
    zone_names = json.dumps({z: ui('zone.' + z) for z in ZONE_KEYS if z != 'todas'}, ensure_ascii=False)
    crumb = [(ui('crumb.home'), u(HOME)), (ui('search.h1'), None)]
    body = f'''
{crumbs(crumb)}

<main>
    <section class="wrap rank-hero">
        <h1>{e(ui('search.h1'))}</h1>
        <p class="lead-text">{e(ui('search.lead'))}</p>
        <form class="search" id="search" role="search" data-index="{u('/buscar/')}indice.json" data-cats="{e(cat_names)}" data-zones="{e(zone_names)}"
              data-save="{e(ui('save.off'))}" data-saved="{e(ui('save.on'))}" data-none="{e(ui('search.none'))}" data-count="{e(ui('search.count'))}" data-count1="{e(ui('search.count1'))}">
            <label class="sr" for="q">{e(ui('search.label'))}</label>
            <input id="q" name="q" type="search" autocomplete="off" placeholder="{e(ui('search.placeholder'))}">
            <label class="sr" for="cat">{e(ui('search.cat'))}</label>
            <select id="cat" name="cat">{cat_opts}</select>
            <label class="sr" for="zone">{e(ui('search.zone'))}</label>
            <select id="zone" name="zone">{zone_opts}</select>
        </form>
        <p class="muted count" id="count" aria-live="polite"></p>
    </section>
    <section class="wrap">
        <ul class="dealers results" id="results"></ul>
        <noscript><p>{e(ui('search.noscript'))}</p></noscript>
    </section>
</main>
<script src="/assets/buscar.js" defer></script>
'''
    write('/buscar/index.html', page('/buscar/', f'{ui("search.title")} · Mejor Imposible', ui('search.desc'),
                                     [webpage('WebPage', '/buscar/', ui('search.title'), ui('search.desc')), bc_ld(crumb)], body))



def save_btn(ref):
    return (f'<button type="button" class="save" data-ref="{ref}" data-on="{e(ui("save.on"))}" data-off="{e(ui("save.off"))}" '
            f'aria-pressed="false">{e(ui("save.off"))}</button>')


def build_trip():
    cat_names = json.dumps({c: t(CATS[c]['corto']) for c in HOME_CHIPS if c in CATS}, ensure_ascii=False)
    crumb = [(ui('crumb.home'), u(HOME)), (ui('trip.h1'), None)]
    body = f'''
{crumbs(crumb)}

<main>
    <section class="wrap rank-hero">
        <h1>{e(ui('trip.h1'))}</h1>
        <p class="lead-text">{e(ui('trip.lead'))}</p>
        <div id="trip" data-index="{u('/buscar/')}indice.json" data-cats="{e(cat_names)}" data-count="{e(ui('trip.count'))}" data-count1="{e(ui('trip.count1'))}"
             data-rm="{e(ui('trip.remove'))}" data-copied="{e(ui('trip.copied'))}">
            <p class="muted" id="trip-shared" hidden>{e(ui('trip.shared'))}</p>
            <div class="trip-actions" id="trip-actions" hidden>
                <button type="button" id="trip-print">{e(ui('trip.print'))}</button>
                <button type="button" id="trip-copy">{e(ui('trip.copy'))}</button>
                <button type="button" id="trip-save" hidden>{e(ui('trip.save_shared'))}</button>
                <button type="button" id="trip-clear">{e(ui('trip.clear'))}</button>
            </div>
            <p class="muted" id="trip-count" aria-live="polite" hidden></p>
        </div>
    </section>
    <section class="wrap">
        <p id="trip-msg">{e(ui('trip.empty'))}</p>
        <ul id="trip-list"></ul>
        <noscript><p>{e(ui('trip.noscript'))}</p></noscript>
    </section>
</main>
'''
    write('/mi-viaje/index.html', page('/mi-viaje/', f'{ui("trip.title")} · Mejor Imposible', ui('trip.desc'),
                                       [webpage('WebPage', '/mi-viaje/', ui('trip.title'), ui('trip.desc')), bc_ld(crumb)], body))



MESES = {
    'es': ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'],
    'en': ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'],
    'fr': ['janvier', 'février', 'mars', 'avril', 'mai', 'juin', 'juillet', 'août', 'septembre', 'octobre', 'novembre', 'décembre'],
    'de': ['Januar', 'Februar', 'März', 'April', 'Mai', 'Juni', 'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember'],
    'pt': ['janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho', 'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro'],
    'it': ['gennaio', 'febbraio', 'marzo', 'aprile', 'maggio', 'giugno', 'luglio', 'agosto', 'settembre', 'ottobre', 'novembre', 'dicembre'],
}


def fmt_fecha(iso):
    y, m, d_ = (int(x) for x in iso.split('-'))
    mes = MESES[LANG][m - 1]
    return {'es': f'{d_} de {mes} de {y}', 'pt': f'{d_} de {mes} de {y}', 'en': f'{mes} {d_}, {y}', 'fr': f'{d_} {mes} {y}' if d_ > 1 else f'1er {mes} {y}',
            'de': f'{d_}. {mes} {y}', 'it': f'{d_} {mes} {y}'}[LANG]


def cal_fecha(x):
    if x.get('texto'):
        return tr(x['texto'])
    y, m = (int(v) for v in x['ym'].split('-'))
    txt = f"{MESES[LANG][m - 1]} {y}" if LANG != 'en' else f"{MESES['en'][m - 1]} {y}"
    return txt + (' ' + ui('chg.est') if x.get('est') else '')


def build_novedades():
    cam = sorted(load('cambios.json')['cambios'], key=lambda c: c['fecha'], reverse=True)
    cal = load('calendario.json')['fuentes'] if exists('calendario.json') else []
    news = ''.join(
        f'\n        <article class="chg"><p class="eyebrow"><time datetime="{c["fecha"]}">{e(fmt_fecha(c["fecha"]))}</time></p>'
        f'<h3>{e(t(c["titulo"]))}</h3><p>{e(t(c["texto"]))}</p></article>' for c in cam)
    rows = ''
    for f in [c for c in cal if not c.get('interno')]:
        name = e(f['fuente'])
        if f.get('url'):
            name = f'<a href="{e(f["url"])}" rel="noopener">{name}</a>'
        rows += (f'\n            <tr><th scope="row">{name}</th><td>{e(t(f["que_publica"]))}</td>'
                 f'<td>{e(cal_fecha(f["ultima"]))}</td><td>{e(cal_fecha(f["proxima"]))}</td></tr>')
    table = ''
    if rows:
        table = f'''
    <section class="wrap prose" aria-labelledby="h-cal">
        <h2 id="h-cal">{e(ui('chg.cal_h'))}</h2>
        <p>{e(ui('chg.cal_lead'))}</p>
        <div class="table-wrap"><table class="cal">
            <thead><tr><th scope="col">{e(ui('chg.col_source'))}</th><th scope="col">{e(ui('chg.col_what'))}</th><th scope="col">{e(ui('chg.col_last'))}</th><th scope="col">{e(ui('chg.col_next'))}</th></tr></thead>
            <tbody>{rows}
            </tbody></table></div>
        <p class="muted">{e(ui('chg.cal_note'))}</p>
    </section>'''
    crumb = [(ui('crumb.home'), u(HOME)), (ui('chg.h1'), None)]
    body = f'''
{crumbs(crumb)}

<main>
    <section class="wrap rank-hero">
        <h1>{e(ui('chg.h1'))}</h1>
        <p class="lead-text">{e(ui('chg.lead'))}</p>
    </section>
    <section class="wrap prose" aria-labelledby="h-news">
        <h2 id="h-news">{e(ui('chg.news'))}</h2>{news}
    </section>{table}
</main>
'''
    write('/novedades/index.html', page('/novedades/', f'{ui("chg.title")} · Mejor Imposible', ui('chg.desc'),
                                        [webpage('WebPage', '/novedades/', ui('chg.title'), ui('chg.desc')), bc_ld(crumb)], body))



INTERESES = load('intereses.json')['intereses']


def interes_datos(x):
    lugares = []
    for cat, n in x['lugares']:
        entries, _ = ranking_entries(cat)
        lugares += [(cat, en['item']) for en in entries[:n]]
    if x.get('planes'):
        planes = [p for p in all_plans() if p['slug'] in x['planes']]
        planes.sort(key=lambda p: x['planes'].index(p['slug']))
    else:
        planes = [p for p in all_plans() if len(p['dias']) <= x.get('planes_max_dias', 2)]
    return lugares, planes


def build_interes(x):
    lugares, planes = interes_datos(x)
    name = t(x['nombre'])
    cards, ld_items = '', []
    for cat, it in lugares:
        rk = RANK_POS.get(it['id'])
        rank = f'<span class="badge ok">{e(ui("dest.rank", n=rk[1], t=rk[2]))}</span>' if rk else ''
        spec = spec_text(cat, it['ficha'])
        cards += (f'\n            <li class="dealer">\n                <p class="city">{e(t(CATS[cat]["corto"]))} · {e(it["lugar"])} {rank}</p>'
                  f'\n                <h3><a href="{item_url(it["id"])}">{e(it["nombre"])}</a></h3>'
                  f'\n                <p>{e(t(it["por_que"]))}</p>'
                  + (f'\n                <p class="muted">{e(spec)}</p>' if spec else '') + f'\n                {save_btn(it["id"])}\n            </li>')
        ld_items.append({"@type": "ListItem", "position": len(ld_items) + 1, "url": SITE + item_url(it['id']), "name": it['nombre']})
    cats_used = []
    for cat, _ in x['lugares']:
        if cat not in cats_used:
            cats_used.append(cat)
    more = ''.join(f'\n            <a href="{u(f"/ranking/{c}/")}">{e(ui("int.ranking", c=t(CATS[c]["corto"])))}</a>' for c in cats_used)
    plan_cards = ''.join(
        f'\n                <a href="{u("/planes/" + p["slug"] + "/")}">{ph_box(plan_cover(p), "t3")}<p class="meta">{e(t(p["meta_corta"]))}</p><p class="ptitle">{e(t(p["titulo"]))}</p></a>'
        for p in planes)
    plans_html = ''
    if planes:
        plans_html = f'''
    <section class="plans" aria-labelledby="int-planes">
        <div class="wrap">
            <h2 id="int-planes">{e(ui('nav.plans'))}</h2>
            <div class="plan-grid">{plan_cards}
            </div>
        </div>
    </section>'''
    path = f'/intereses/{x["slug"]}/'
    crumb = [(ui('crumb.home'), u(HOME)), (name, None)]
    title, desc = ui('int.title', n=name), ui('int.desc', n=name.lower() if LANG != 'de' else name)
    body = f'''
{crumbs(crumb)}

<main>
    <section class="wrap rank-hero">
        <p class="eyebrow">{e(ui('int.eyebrow'))}</p>
        <h1>{e(name)}</h1>
        <p class="lead-text">{e(t(x['lead']))}</p>
    </section>
    <section class="wrap dir-brand" aria-labelledby="int-lugares">
        <h2 id="int-lugares">{e(ui('int.places'))}</h2>
        <ul class="dealers">{cards}
        </ul>
        <nav class="chips" aria-label="{e(ui('int.places'))}">{more}
        </nav>
    </section>{plans_html}
    <section class="wrap dir-brand"><p><a href="{u(HOME)}">{e(ui('int.back'))}</a></p></section>
</main>
'''
    lds = [webpage('CollectionPage', path, title, desc), {"@type": "ItemList", "name": title, "inLanguage": LANG, "itemListElement": ld_items}, bc_ld(crumb)]
    write(path + 'index.html', page(path, f'{title} · Mejor Imposible', desc, lds, body))


def interests_home():
    cards = ''
    for x in INTERESES:
        lugares, planes = interes_datos(x)
        cards += (f'\n            <a href="{u("/intereses/" + x["slug"] + "/")}"><span class="ititle">{e(t(x["nombre"]))}</span>'
                  f'<span class="itxt">{e(t(x["lead"]))}</span><span class="icount">{e(ui("int.count", p=len(lugares), q=len(planes)))}</span></a>')
    return f'''
    <section class="wrap interests" aria-labelledby="intereses-h">
        <h2 id="intereses-h">{e(ui('home.interests_h'))}</h2>
        <p class="lead">{e(ui('home.interests_lead'))}</p>
        <div class="interest-grid">{cards}
        </div>
    </section>
'''


def fechas_evento(x):
    if x.get('inicio'):
        a = datetime.date.fromisoformat(x['inicio'])
        b = datetime.date.fromisoformat(x['fin']) if x.get('fin') else a
        ma, mb, y = MESES[LANG][a.month - 1], MESES[LANG][b.month - 1], b.year
        if a == b:
            return fmt_fecha(x['inicio'])
        same = (a.month == b.month and a.year == b.year)
        if LANG == 'es':
            return f'{a.day} al {b.day} de {ma} de {y}' if same else f'{a.day} de {ma} al {b.day} de {mb} de {y}'
        if LANG == 'pt':
            return f'{a.day} a {b.day} de {ma} de {y}' if same else f'{a.day} de {ma} a {b.day} de {mb} de {y}'
        if LANG == 'en':
            return f'{ma} {a.day}–{b.day}, {y}' if same else f'{ma} {a.day} – {mb} {b.day}, {y}'
        if LANG == 'fr':
            return f'du {a.day} au {b.day} {ma} {y}' if same else f'du {a.day} {ma} au {b.day} {mb} {y}'
        if LANG == 'de':
            return f'{a.day}.–{b.day}. {ma} {y}' if same else f'{a.day}. {ma} – {b.day}. {mb} {y}'
        return f'dal {a.day} al {b.day} {ma} {y}' if same else f'dal {a.day} {ma} al {b.day} {mb} {y}'
    return cal_fecha({'ym': x['mes_aprox']})


def fin_evento(x):
    if x.get('fin') or x.get('inicio'):
        return x.get('fin') or x['inicio']
    y, m = (int(v) for v in x['mes_aprox'].split('-'))
    nxt = datetime.date(y + (m == 12), m % 12 + 1, 1)
    return (nxt - datetime.timedelta(days=1)).isoformat()


EV_SCRIPT = '''
<script>
(function () {
    var today = new Date().toISOString().slice(0, 10), cat = 'todas';
    var items = document.querySelectorAll('.ev'), months = document.querySelectorAll('.ev-month'), none = document.getElementById('ev-none');
    function apply() {
        var shown = 0;
        items.forEach(function (el) {
            var show = el.dataset.end >= today && (cat === 'todas' || el.dataset.cat === cat);
            el.hidden = !show; if (show) shown++;
        });
        months.forEach(function (m) { m.hidden = !m.querySelector('.ev:not([hidden])'); });
        none.hidden = shown > 0;
        document.querySelectorAll('[data-ev-cat]').forEach(function (b) { b.setAttribute('aria-pressed', String(b.dataset.evCat === cat)); });
    }
    document.querySelectorAll('[data-ev-cat]').forEach(function (b) { b.addEventListener('click', function () { cat = b.dataset.evCat; apply(); }); });
    apply();
})();
</script>'''


def build_eventos():
    evs = [x for x in load('eventos.json')['eventos'] if x.get('publicar')]
    evs.sort(key=lambda x: x.get('inicio') or (x['mes_aprox'] + '-01'))
    dest_names = {d['slug']: tr(d['nombre']) for d in DESTS}
    cats = []
    for x in evs:
        if x['categoria'] not in cats:
            cats.append(x['categoria'])
    chips = f'<button type="button" data-ev-cat="todas" aria-pressed="true">{e(ui("ev.all"))}</button>' + ''.join(
        f'<button type="button" data-ev-cat="{c}" aria-pressed="false">{e(ui("ev.cat." + c))}</button>' for c in cats)
    sections, cur, buf, ld = '', None, '', []
    for x in evs + [None]:
        ym = None if x is None else (x.get('inicio') or x['mes_aprox'] + '-01')[:7]
        if cur and ym != cur:
            y, m = (int(v) for v in cur.split('-'))
            sections += (f'\n    <section class="wrap ev-month" aria-label="{MESES[LANG][m - 1]} {y}">\n        <h2>{e(MESES[LANG][m - 1].capitalize() if LANG != "en" else MESES[LANG][m - 1])} {y}</h2>'
                         f'\n        <div class="ev-list">{buf}\n        </div>\n    </section>')
            buf = ''
        cur = ym
        if x is None:
            break
        ok = x['confianza'] == 'alta'
        badge = f'<span class="badge{" ok" if ok else ""}">{e(ui("ev.confirmed" if ok else "ev.tbc"))}</span>'
        guide = (f' · <a href="{u("/destinos/" + x["destino"] + "/")}">{e(ui("ev.guide", n=dest_names[x["destino"]]))}</a>'
                 if x.get('destino') in dest_names else '')
        buf += (f'\n            <article class="ev" data-cat="{x["categoria"]}" data-end="{fin_evento(x)}">'
                f'\n                <p class="eyebrow">{e(fechas_evento(x))} {badge}</p>'
                f'\n                <h3>{e(x["nombre"])}</h3>'
                f'\n                <p class="city">{e(ui("ev.cat." + x["categoria"]))} · {e(tr(x["lugar"]))}</p>'
                f'\n                <p>{e(tr(x["que_es"]))}</p>'
                f'\n                <p class="muted"><a href="{e(x["fuente_url"])}" rel="noopener">{e(ui("ev.source"))}</a>{guide}</p>\n            </article>')
        ld.append({"@type": "Event", "name": x['nombre'], "location": {"@type": "Place", "name": tr(x['lugar']), "address": {"@type": "PostalAddress", "addressCountry": "ES"}},
                   **({"startDate": x['inicio']} if x.get('inicio') else {}), **({"endDate": x['fin']} if x.get('fin') else {}),
                   "description": tr(x['que_es']), "url": x['fuente_url'], "eventStatus": "https://schema.org/EventScheduled"})
    crumb = [(ui('crumb.home'), u(HOME)), (ui('ev.h1'), None)]
    body = f'''
{crumbs(crumb)}

<main>
    <section class="wrap rank-hero">
        <h1>{e(ui('ev.h1'))}</h1>
        <p class="lead-text">{e(ui('ev.lead'))}</p>
        <div class="chips left" role="group" aria-label="{e(ui('search.cat'))}">{chips}</div>
    </section>{sections}
    <section class="wrap prose">
        <p id="ev-none" hidden>{e(ui('ev.none'))}</p>
        <p class="muted">{e(ui('ev.note'))}</p>
    </section>
</main>
{EV_SCRIPT}
'''
    path = '/eventos/'
    lds = [webpage('CollectionPage', path, ui('ev.title'), ui('ev.desc')), {"@type": "ItemList", "name": ui('ev.title'), "numberOfItems": len(ld),
           "itemListElement": [{"@type": "ListItem", "position": i + 1, "item": ev} for i, ev in enumerate(ld)]}, bc_ld(crumb)]
    write(path + 'index.html', page(path, f'{ui("ev.title")} · Mejor Imposible', ui('ev.desc'), lds, body))


PAGE_PATHS = ([HOME] + [f'/ranking/{c}/' for c in CATS] + [f'/planes/{p["slug"]}/' for p in all_plans()]
              + ['/motor/marcas/', '/metodologia/', '/destinos/', '/buscar/', '/mi-viaje/', '/novedades/', '/eventos/'] + [f'/intereses/{x["slug"]}/' for x in INTERESES] + [f'/destinos/{d["slug"]}/' for d in DESTS]
              + ['/ranking/' + r + '/' for r in ITEMS] + ['/ranking/compras-de-lujo/tiendas/'])


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
        build_tiendas()
        build_method()
        build_destinos()
        for _d in DESTS:
            build_dest(_d)
        build_search()
        build_trip()
        build_novedades()
        build_eventos()
        for _x in INTERESES:
            build_interes(_x)
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
