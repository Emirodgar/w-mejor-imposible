#!/usr/bin/env python3
"""Genera las páginas del portal (rankings, planes y tiras de la home) desde data/portal/.

Uso:  python scripts/portal/build.py

Datos (un archivo por elemento, con referencias cruzadas por id "categoria/slug"):
  data/portal/categorias.json          metadatos de cada ranking y placeholders mientras no esté relleno
  data/portal/items/<cat>/<slug>.json  un lugar (campo, restaurante...)
  data/portal/rankings/<cat>.json      orden del top 10 (lista de ids); si no existe, se usan placeholders
  data/portal/planes/<slug>.json       un plan completo; sus pasos apuntan a ítems por id
  data/portal/aeropuertos.json         aeropuertos con coordenadas ("Lo mejor cerca" se calcula con ellas)
Las coordenadas se obtienen con scripts/portal/geocode.py; "Lo mejor cerca" (restaurante, golf, aeropuerto)
se calcula por distancia a partir de ellas, salvo que el ítem lo fije a mano en "cerca".
Los textos van como {"es": "..."} para añadir en/fr/de/pt/it sin cambiar la estructura.
"""
import html
import json
import math
import os
import re

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
DATA = os.path.join(ROOT, 'data', 'portal')
SITE = 'https://mejorimposible.es'
LANG = 'es'

LANGS = [('es', 'ES'), ('en', 'EN'), ('fr', 'FR'), ('de', 'DE'), ('pt', 'PT'), ('it', 'IT')]
ZONES = [('todas', 'Toda España'), ('andalucia', 'Andalucía'), ('cataluna', 'Cataluña'),
         ('baleares', 'Baleares'), ('canarias', 'Canarias'), ('resto', 'Resto')]
ZONE_NAMES = dict(ZONES)
TONES = ['', ' t3', '', ' t3', '']
STRIP_TONES = ['', ' t2', ' t3', ' t4', '']
LABEL_TIPO = {'Hotel 5*': 'hotel', 'Restaurante': 'restaurante', 'Golf': 'golf', 'Aeropuerto': 'aeropuerto',
              'Spa': 'spa', 'Puerto': 'puerto', 'Bodega': 'bodega'}
CAT_SCHEMA = {'golf': 'GolfCourse', 'restaurantes': 'Restaurant', 'hoteles-5-estrellas': 'Hotel',
              'bodegas': 'Winery', 'spas': 'HealthAndBeautyBusiness'}


def e(s):
    return html.escape(str(s), quote=True)


def t(x):
    """Texto traducible: {"es": ...} -> cadena."""
    if isinstance(x, dict):
        return x.get(LANG) or x.get('es') or ''
    return x


def load(rel):
    with open(os.path.join(DATA, *rel.split('/')), encoding='utf-8') as f:
        return json.load(f)


def exists(rel):
    return os.path.exists(os.path.join(DATA, *rel.split('/')))


def write(path, content):
    full = os.path.join(ROOT, *path.split('/'))
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, 'w', encoding='utf-8', newline='\n') as f:
        f.write(content)


CATS = load('categorias.json')
ITEMS = {}
for cat in os.listdir(os.path.join(DATA, 'items')):
    for fn in os.listdir(os.path.join(DATA, 'items', cat)):
        item = load(f'items/{cat}/{fn}')
        ITEMS[item['id']] = item


def item_url(ref):
    cat, slug = ref.split('/')
    return f'/ranking/{cat}/#{slug}'


# ---------------- Plantilla común ----------------
def lang_html():
    out = []
    for c, n in LANGS:
        href = '#' if c == 'es' else f'/{c}/'
        cur = ' aria-current="true"' if c == 'es' else ''
        out.append(f'        <a href="{href}" hreflang="{c}" lang="{c}"{cur}>{n}</a>')
    return '\n'.join(out)


HEAD = '''<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>@@TITLE@@</title>
    <meta name="description" content="@@DESC@@">
    <!-- Borrador del nuevo portal: no indexar hasta sustituir a index.html -->
    <meta name="robots" content="noindex, nofollow">
    <link rel="icon" type="image/svg+xml" href="/assets/favicon.svg">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,400;0,500;1,400&family=Inter:wght@400;500&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="/assets/portal.css">
@@LD@@
</head>
<body>

<header class="wrap site-header">
    <a class="brand" href="/index2.html">mejor imposible</a>
    <nav class="main-nav" aria-label="Principal">
        <a href="/index2.html#rankings">Rankings</a>
        <a href="/index2.html#planes">Planes completos</a>
        <a href="/destinos/">Destinos</a>
        <a href="/">Guía Porsche</a>
    </nav>
    <div class="lang" aria-label="Idioma">
@@LANG@@
    </div>
</header>
'''

FOOT = '''
<footer class="site-footer">
    <div class="wrap">
        <a class="brand" href="/index2.html">mejor imposible</a>
        <nav class="footer-links" aria-label="Pie">
            <a href="/">Guía Porsche</a>
            <a href="/metodologia/">Metodología</a>
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
    lis = ''.join(f'<li><a href="{u}">{e(n)}</a></li>' if u else f'<li aria-current="page">{e(n)}</li>' for n, u in items)
    return f'<nav class="wrap crumbs" aria-label="Migas de pan"><ol>{lis}</ol></nav>'


def bc_ld(items):
    return {"@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": i + 1, "name": n, **({"item": SITE + u} if u else {})}
        for i, (n, u) in enumerate(items)]}


def ld(*objs):
    return '\n'.join('    <script type="application/ld+json">\n' + json.dumps(
        {"@context": "https://schema.org", **o}, ensure_ascii=False, indent=4) + '\n    </script>' for o in objs)


def page(title, desc, lds, body):
    h = (HEAD.replace('@@TITLE@@', e(title)).replace('@@DESC@@', e(desc))
         .replace('@@LD@@', ld(*lds)).replace('@@LANG@@', lang_html()))
    return h + body + FOOT + (SCRIPT if 'data-zone' in body else '') + '\n</body>\n</html>\n'


# ---------------- Rankings ----------------
def spec_text(cat, ficha):
    """Compone la línea de ficha; omite las partes cuyo dato falte."""
    parts = []
    for tpl in CATS[cat]['ficha']:
        fields = re.findall(r'\{(\w+)\}', tpl)
        if all(f in ficha for f in fields):
            parts.append(tpl.format(**ficha))
        elif not fields:
            parts.append(tpl)
    return ' · '.join(parts)


AIRPORTS = load('aeropuertos.json')['aeropuertos']
MICHELIN = [r for r in (load('michelin/guia-2026.json')['restaurantes'] if exists('michelin/guia-2026.json') else [])
            if r.get('coordenadas') and not r.get('ref')]  # los que ya son ítems del ranking salen como ítem
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
    elif tipo in ('restaurante', 'golf'):
        cat = 'restaurantes' if tipo == 'restaurante' else 'golf'
        pool = [(i['nombre'], i['id'], i) for i in ITEMS.values()
                if i['categoria'] == cat and i['id'] != item['id'] and coords(i)]
    else:
        return None
    best = min(((haversine_km(here, coords(x)), n, ref, None) for n, ref, x in pool), default=None)
    if tipo == 'restaurante':
        # si ningún restaurante del ranking queda cerca, se recurre al estrellado más próximo
        for r in ([] if best and best[0] <= MAX_KM else MICHELIN):
            d = haversine_km(here, coords(r))
            if not best or d < best[0]:
                best = (d, r['nombre'], None, r['estrellas'])
    if not best or (tipo != 'aeropuerto' and best[0] > MAX_KM):
        return None
    out = dict(tipo=tipo, nombre=best[1], ref=best[2], min=drive_min(best[0]))
    if best[3]:
        out['nota'] = f"{best[3]} {'estrella' if best[3] == 1 else 'estrellas'} Michelin · a ~{out['min']} min"
    return out


def near_tiles(cat, item):
    tiles = ''
    for label in CATS[cat]['cerca']:
        tipo = LABEL_TIPO.get(label, label.lower())
        # lo escrito a mano en el ítem manda; si no hay, se calcula por coordenadas
        entry = next((c for c in (item or {}).get('cerca', []) if c['tipo'] == tipo), None) or nearest(item, tipo)
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
            detail = entry.get('nota') or (f"a ~{entry['min']} min" if entry.get('min') else '')
            k, tt = e(name), e(f'{label} · {detail}' if detail else label)
        else:
            k, tt = e(label), 'a [X] min'
        tiles += f'<a href="{href or "#"}"><span class="sq"></span><span class="k">{k}</span><span class="t">{tt}</span></a>'
    return tiles


def ranking_entries(slug):
    """Devuelve lista de dicts normalizados (reales o placeholders) y el aviso de actualización."""
    c = CATS[slug]
    if exists(f'rankings/{slug}.json'):
        rk = load(f'rankings/{slug}.json')
        out = []
        for ref in rk['items']:
            it = ITEMS[ref]
            out.append(dict(slug=ref.split('/')[1], nombre=it['nombre'], lugar=it['lugar'], zona=it['zona'],
                            foto=t(it['foto']), why=t(it['por_que']), spec=spec_text(slug, it['ficha']), item=it))
        return out, t(rk['actualizado'])
    out = []
    for p in c['placeholder']:
        out.append(dict(slug=None, nombre=t(c['nombre_placeholder']), lugar=p['lugar'], zona=p['zona'],
                        foto=t(c['foto_placeholder']), why='[Una frase: por qué está en este puesto.]',
                        spec=' · '.join(c['ficha']), item=None))
    return out, '[MES AÑO]'


def build_rank(slug):
    c = CATS[slug]
    entries, updated = ranking_entries(slug)
    top, rest = entries[:5], entries[5:]
    items = ''
    for i, en in enumerate(top):
        anchor = f' id="{en["slug"]}"' if en['slug'] else ''
        plan = (f'\n                    <a class="plan-link" href="/planes/golf-en-sotogrande/">Ver el plan completo →</a>'
                if en['slug'] == 'real-club-valderrama' else '')
        items += f'''
        <li class="top-item"{anchor} data-zone="{en['zona']}" data-rank="{i+1}">
            <div class="num" aria-hidden="true">{i+1:02d}</div>
            <div class="ph photo{TONES[i]}">[FOTO · {e(en['foto'])}]</div>
            <div class="info">
                <p class="place">{e(en['lugar'])}</p>
                <h2><span class="visually-hidden">{i+1}. </span>{e(en['nombre'])}</h2>
                <p class="why">{e(en['why'])}</p>
                <p class="spec">{e(en['spec'])}</p>
                <div class="near">
                    <p class="label">Lo mejor cerca</p>
                    <div class="near-grid">{near_tiles(slug, en['item'])}</div>{plan}
                </div>
            </div>
        </li>'''
    restli = ''.join(f'''
            <li{f' id="{en["slug"]}"' if en['slug'] else ''} data-zone="{en['zona']}"><a href="#"><span class="n">{i+6:02d}</span><span class="thumb"></span><span class="nm">{e(en['nombre'])}</span><span class="pl">{e(en['lugar'])}</span><span class="arrow" aria-hidden="true">→</span></a></li>'''
                     for i, en in enumerate(rest))
    chips = ''.join(
        f'<button type="button" data-filter="{k}" aria-pressed="{"true" if k == "todas" else "false"}">{n}</button>'
        for k, n in ZONES)
    short, h1 = t(c['corto']), t(c['titulo'])
    crumb = [('Inicio', '/index2.html'), ('Rankings', '/index2.html#rankings'), (short, None)]
    schema = CAT_SCHEMA.get(slug)
    ld_items = []
    for n, en in enumerate(entries, 1):
        li = {"@type": "ListItem", "position": n, "name": en['nombre']}
        if en['slug']:
            li["url"] = f"{SITE}/ranking/{slug}/#{en['slug']}"
            if schema:
                li["item"] = {"@type": schema, "name": en['nombre'],
                              "address": {"@type": "PostalAddress", "addressLocality": en['lugar'], "addressCountry": "ES"}}
        ld_items.append(li)
    itemlist = {"@type": "ItemList", "name": h1, "itemListOrder": "https://schema.org/ItemListOrderAscending",
                "numberOfItems": len(entries), "itemListElement": ld_items}
    body = f'''
{crumbs(crumb)}

<main>
    <section class="wrap rank-hero">
        <p class="eyebrow">Ranking · {e(short)} · Actualizado {e(updated)}</p>
        <h1>{e(h1)}</h1>
        <div class="chips left" role="group" aria-label="Filtrar por zona">{chips}</div>
    </section>

    <ol class="wrap top-list" id="top">{items}
    </ol>
    <p class="wrap empty" id="empty-top" hidden>Ningún elemento de la zona seleccionada está entre los cinco primeros.</p>

    <section class="wrap rest" id="rest" aria-labelledby="rest-h">
        <h2 id="rest-h">Del 6 al 10</h2>
        <ol class="compact-list">{restli}
        </ol>
    </section>

    <section class="wrap method" id="metodologia">
        <div class="box">
            <div>
                <p class="eyebrow">Cómo ordenamos</p>
                <p class="txt">{e(t(c['como_ordenamos']))}</p>
            </div>
            <a href="/metodologia/">Metodología completa →</a>
        </div>
    </section>
</main>
'''
    write(f'ranking/{slug}/index.html', page(
        f'{h1} · Mejor Imposible',
        f'{h1}: top 5 con lo mejor cerca y del 6 al 10 en formato compacto, con filtro por zona.',
        [itemlist, bc_ld(crumb)], body))


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
# tipo de paso de la ruta -> (etiqueta, categoría de ranking enlazada, texto del enlace)
ROUTE = {
    'llegada': ('Llegada', None, 'Ver cómo llegar'),
    'coche': ('Coche', 'motor', 'Ver experiencias de motor en {z}'),
    'hotel': ('Hotel 5*', 'hoteles-5-estrellas', 'Ver hoteles 5* en {z}'),
    'golf': ('Golf', 'golf', 'Ver campos de golf en {z}'),
    'cena': ('Cena', 'restaurantes', 'Ver restaurantes en {z}'),
    'descanso': ('Descanso', 'spas', 'Ver spas en {z}'),
    'mesa': ('Mesa', 'restaurantes', 'Ver restaurantes en {z}'),
    'bodega': ('Bodega', 'bodegas', 'Ver bodegas en {z}'),
    'barco': ('Barco', 'yates-y-calas', 'Ver calas y rutas en barco en {z}'),
    'cala': ('Cala', 'yates-y-calas', 'Ver calas y rutas en barco en {z}'),
}
# el paso destacado (círculo oscuro) de la ruta
HIGHLIGHT = ('golf', 'bodega', 'cala', 'mesa')


def all_plans():
    plans = [load(f'planes/{fn}') for fn in os.listdir(os.path.join(DATA, 'planes'))]
    return sorted(plans, key=lambda p: p.get('orden', 99))


def other_plans(slug):
    return [p for p in all_plans() if p['slug'] != slug]


def build_plan(slug):
    p = load(f'planes/{slug}.json')
    zona = p['zona']
    zn = ZONE_NAMES[zona]
    title = t(p['titulo'])

    def step_name(s):
        return ITEMS[s['ref']]['nombre'] if s.get('ref') else t(s['nombre'])

    route_html, route_ld = '', []
    for s in p['ruta']:
        label, cat, txt = ROUTE[s['tipo']]
        name = step_name(s)
        href = '#llegar-h' if cat is None else f'/ranking/{cat}/?zona={zona}'
        on = s['tipo'] in HIGHLIGHT and not any(r['tipo'] in HIGHLIGHT for r in p['ruta'][:p['ruta'].index(s)])
        stroke = '#F6F3EE' if on else '#16140F'
        route_html += f'''
            <li><a href="{href}" aria-label="{e(txt.format(z=zn))}"><span class="dot{' on' if on else ''}"><svg aria-hidden="true" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="{stroke}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">{ICONS[s['tipo']]}</svg></span><span class="k">{label}</span><span class="v">{e(name)}</span></a></li>'''
        route_ld.append({"@type": "ListItem", "position": len(route_ld) + 1, "name": f'{label}: {name}'})

    days_html = ''
    for n, d in enumerate(p['dias'], 1):
        steps = ''
        for s in d['pasos']:
            tone = ' t3' if s.get('tono') == 'oscuro' else ''
            if s.get('ref'):
                it = ITEMS[s['ref']]
                name = f'<a href="{item_url(s["ref"])}">{e(it["nombre"])}</a>'
                foto, why = t(it['foto']), t(s['por_que']) if s.get('por_que') else t(it['por_que'])
            else:
                name, foto, why = e(t(s['nombre'])), t(s['foto']), t(s['por_que'])
            if s.get('alternativas'):
                alts = ' · '.join(f'<a href="#">{e(t(a))}</a>' for a in s['alternativas'])
            else:
                alts = '<a href="#">[Opción 2]</a> · <a href="#">[Opción 3]</a>'
            steps += f'''
                <article>
                    <div class="ph{tone}">[FOTO · {e(foto)}]</div>
                    <p class="kind">{e(s['tipo'])}</p>
                    <h3>{name}</h3>
                    <p class="why">{e(why)}</p>
                    <p class="alt">Alternativas: {alts}</p>
                </article>'''
        days_html += f'''
    <section class="wrap day" aria-labelledby="dia-{n:02d}">
        <div class="day-head"><span class="dn" aria-hidden="true">{n:02d}</span><h2 id="dia-{n:02d}">Día {n} · {e(t(d['titulo']))}</h2></div>
        <div class="steps">{steps}
        </div>
    </section>
'''

    llegar = ''
    for r in p['llegar']:
        val = f"~{r['min']} min" if r.get('min') else t(r['texto'])
        llegar += f'\n                    <div class="r"><dt>{e(t(r["nombre"]))}</dt><dd>{e(val)}</dd></div>'
    others = ''.join(
        f'\n            <a href="/planes/{o["slug"]}/"><span class="thumb"></span><span class="m">{e(t(o["meta_corta"]))}</span><span class="t">{e(t(o["titulo"]))}</span></a>'
        for o in other_plans(slug)[:3])
    crumb = [('Inicio', '/index2.html'), ('Planes completos', '/index2.html#planes'), (title, None)]
    trip = {"@type": "TouristTrip", "name": title, "inLanguage": LANG, "description": t(p['lead']),
            "touristType": p.get("tipo_turista", "Golf"), "itinerary": {"@type": "ItemList", "itemListElement": route_ld}}
    body = f'''
{crumbs(crumb)}

<main>
    <section class="wrap">
        <div class="plan-hero">
            <span class="ph-label">[FOTO · {e(t(p['foto_portada']))}]</span>
            <p class="kicker">{e(t(p['meta']))}</p>
            <h1>{e(title)}</h1>
            <p class="lead">{e(t(p['lead']))}</p>
        </div>
    </section>

    <section class="wrap route" aria-label="Resumen del plan">
        <ol>{route_html}
        </ol>
    </section>
{days_html}
    <section class="wrap getting" aria-labelledby="llegar-h">
        <div class="cols">
            <div class="map">[MAPA · aeropuerto, hotel, campo y restaurante]</div>
            <div class="times">
                <h2 id="llegar-h">Cómo llegar</h2>
                <dl>{llegar}
                </dl>
            </div>
        </div>
    </section>

    <section class="wrap others" aria-labelledby="otros-h">
        <h2 id="otros-h">Otros planes completos</h2>
        <div class="grid">{others}
        </div>
    </section>
</main>
'''
    write(f'planes/{slug}/index.html', page(
        f'{title}: plan completo · Mejor Imposible',
        f'{t(p["meta"])}: {t(p["lead"])}', [trip, bc_ld(crumb)], body))


# ---------------- Tiras de la home ----------------
def build_home_strips():
    path = os.path.join(ROOT, 'index2.html')
    with open(path, encoding='utf-8') as f:
        h = f.read()
    for slug in ('golf', 'restaurantes'):
        if not exists(f'rankings/{slug}.json'):
            continue
        entries, _ = ranking_entries(slug)
        lis = ''.join(
            f'\n                    <li><a href="/ranking/{slug}/#{en["slug"]}"><div class="ph{STRIP_TONES[i]}">[FOTO]</div><div class="row"><span class="n">{i+1:02d}</span><span><span class="name">{e(en["nombre"])}</span><span class="place">{e(en["lugar"])}</span></span></div></a></li>'
            for i, en in enumerate(entries[:5]))
        pat = re.compile(rf'(<!-- strip:{slug} -->).*?(<!-- /strip:{slug} -->)', re.S)
        h = pat.sub(lambda m: f'{m.group(1)}\n                <ol>{lis}\n                </ol>\n                {m.group(2)}', h)
    cards = ''.join(
        f'\n                <a href="/planes/{p["slug"]}/"><div class="ph t3">[FOTO · {e(t(p["foto_portada"]))}]</div><p class="meta">{e(t(p["meta_corta"]))}</p><p class="ptitle">{e(t(p["titulo"]))}</p></a>'
        for p in all_plans())
    h = re.sub(r'(<!-- strip:planes -->).*?(<!-- /strip:planes -->)',
               lambda m: f'{m.group(1)}{cards}\n                {m.group(2)}', h, flags=re.S)
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(h)


if __name__ == '__main__':
    for slug in CATS:
        build_rank(slug)
    for fn in os.listdir(os.path.join(DATA, 'planes')):
        build_plan(fn[:-5])
    build_home_strips()
    print('portal generado')
