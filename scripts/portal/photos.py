#!/usr/bin/env python3
"""Busca en Wikimedia Commons una foto con licencia libre para cada ítem y la descarga a img/portal/.

Uso:  python scripts/portal/photos.py [categoria/slug ...] [--force]

Para cada ítem sin foto:
  1. Busca su artículo en Wikipedia (es y en) y acepta la imagen principal solo si el artículo tiene
     coordenadas a menos de 5 km de las del ítem.
  2. Si no sirve, busca archivos de Commons geolocalizados a menos de 600 m y puntúa por nombre y tamaño.
Solo se aceptan JPEG horizontales de al menos 1000 px con licencia CC BY, CC BY-SA, CC0 o dominio público.
Guarda en el ítem "foto_real": {archivo, autor, licencia, licencia_url, fuente, titulo}; el build la muestra
con su crédito. Es reanudable y respeta 1 petición cada ~0,4 s.
"""
import html
import io
import json
import math
import os
import re
import subprocess
import sys
import time
import urllib.parse

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
UA = 'mejorimposible-portal-build/1.0 (static site generator; Wikimedia API, low volume)'
OK_LICENSE = re.compile(r'^(CC BY(-SA)? [0-9.]+|CC0|Public domain|PD)', re.I)
MIN_W = 1000


def fetch(url):
    """Descarga con curl (el almacén de certificados de Python en Windows rechaza a veces el de Wikimedia).
    Ante un 429 espera y reintenta."""
    for _ in range(6):
        r = subprocess.run(['curl', '-s', '-L', '-m', '60', '-A', UA, '-w', '\n%{http_code}', url], capture_output=True)
        body, _, code = r.stdout.rpartition(b'\n')
        if code.strip() == b'200' and body:
            return body
        time.sleep(35 if code.strip() == b'429' else 3)
    return b''


def api(host, **params):
    params.update(format='json', formatversion=2)
    raw = fetch(f'https://{host}/w/api.php?' + urllib.parse.urlencode(params))
    time.sleep(1.5)
    try:
        return json.loads(raw)
    except ValueError:
        return {}


def km(a, b):
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


def strip(s):
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', '', s or ''))).strip()


def file_info(titles):
    """Metadatos y miniatura de 1200 px de archivos de Commons (dict título -> info) solo si cumplen los requisitos."""
    out = {}
    for i in range(0, len(titles), 20):
        d = api('commons.wikimedia.org', action='query', prop='imageinfo', titles='|'.join(titles[i:i + 20]),
                iiprop='url|size|mime|extmetadata', iiurlwidth=1200)
        for p in d.get('query', {}).get('pages', []):
            ii = (p.get('imageinfo') or [None])[0]
            if not ii or ii.get('mime') != 'image/jpeg' or ii['width'] < MIN_W or ii['height'] > ii['width']:
                continue
            md = ii.get('extmetadata', {})
            lic = strip(md.get('LicenseShortName', {}).get('value'))
            if not OK_LICENSE.match(lic):
                continue
            artist = strip(md.get('Artist', {}).get('value')) or strip(md.get('Credit', {}).get('value'))
            out[p['title']] = dict(
                titulo=p['title'], url=ii.get('thumburl') or ii['url'], ancho=ii['width'], autor=artist[:80],
                licencia=lic, licencia_url=md.get('LicenseUrl', {}).get('value', ''), fuente=ii['descriptionurl'])
    return out


BAD = re.compile(r'\b(map|mapa|logo|plan|plano|diagram|range|scorecard|escudo|flag|bandera|portrait|retrato|chef|poster|cartel|menu|carta|sign|firma)\b', re.I)


def tokens(name):
    n = re.sub(r'\(.*?\)', '', name).lower()
    n = n.translate(str.maketrans('áéíóúñü', 'aeiounu'))
    return [w for w in re.findall(r'[a-z]{4,}', n) if w not in ('real', 'club', 'hotel', 'golf', 'campo', 'bodegas', 'bodega')]


def score(title, inf, words, lead=False):
    t = title.lower().translate(str.maketrans('áéíóúñü', 'aeiounu'))
    s = (3 if lead else 0) + sum(3 for w in words if w in t) + (1 if inf['ancho'] >= 2000 else 0)
    return s - (6 if BAD.search(title) else 0)


def candidates(item, here):
    """Lista de (puntuación, info, origen) con archivos válidos para el ítem."""
    words = tokens(item['nombre'])
    q = re.sub(r'\(.*?\)', '', item['nombre']).strip()
    out = []
    for lang in ('es', 'en'):
        d = api(f'{lang}.wikipedia.org', action='query', generator='search', gsrsearch=q, gsrlimit=3,
                prop='coordinates|pageimages|images', piprop='name', imlimit=50)
        pool = []
        for p in d.get('query', {}).get('pages', []):
            co = (p.get('coordinates') or [None])[0]
            if not co or km(here, (co['lat'], co['lon'])) > 5:
                continue
            titles = [i['title'] for i in p.get('images', []) if i['title'].lower().endswith(('.jpg', '.jpeg'))]
            lead = 'File:' + p['pageimage'] if p.get('pageimage') else None
            if lead and lead not in titles:
                titles.append(lead)
            pool += [(t, t == lead, p['title']) for t in titles]
        pool.sort(key=lambda x: -score(x[0], {'ancho': 0}, words, x[1]))
        pool = pool[:15]
        if pool:
            origin = {t.replace('_', ' '): f'{lang}.wikipedia: {pt}' for t, _, pt in pool}
            lead_set = {t.replace('_', ' ') for t, ld, _ in pool if ld}
            for t, inf in file_info([t for t, _, _ in pool]).items():
                out.append((score(t, inf, words, t.replace('_', ' ') in lead_set), inf, origin.get(t.replace('_', ' '), lang + '.wikipedia')))
            if out:
                return out
    # búsqueda directa en Commons, con comprobación de coordenadas o de nombre
    d = api('commons.wikimedia.org', action='query', generator='search', gsrsearch=f'{q} filetype:bitmap',
            gsrnamespace=6, gsrlimit=20, prop='coordinates', colimit=20)
    pages = d.get('query', {}).get('pages', [])
    near = {p['title'] for p in pages if p.get('coordinates') and km(here, (p['coordinates'][0]['lat'], p['coordinates'][0]['lon'])) <= 5}
    infos = file_info([p['title'] for p in pages if p['title'].lower().endswith(('.jpg', '.jpeg'))])
    for t, inf in infos.items():
        sc = score(t, inf, words) + (3 if t in near else 0)
        if t in near or (words and sum(w in t.lower() for w in words) >= max(1, len(words) // 2 + len(words) % 2)):
            out.append((sc, inf, 'commons búsqueda'))
    return out


def save(info, dest):
    raw = fetch(info['url'])
    from PIL import Image
    im = Image.open(io.BytesIO(raw)).convert('RGB')
    if im.width > 1200:
        im = im.resize((1200, round(im.height * 1200 / im.width)))
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    im.save(dest, 'JPEG', quality=80, optimize=True, progressive=True)
    time.sleep(1.0)


def main():
    force = '--force' in sys.argv
    only = [a for a in sys.argv[1:] if not a.startswith('--')]
    base = os.path.join(ROOT, 'data', 'portal', 'items')
    ok = miss = 0
    for cat in sorted(os.listdir(base)):
        for fn in sorted(os.listdir(os.path.join(base, cat))):
            path = os.path.join(base, cat, fn)
            item = json.load(open(path, encoding='utf-8'))
            if only and item['id'] not in only:
                continue
            if item.get('foto_real') and not force:
                continue
            c = item.get('coordenadas')
            if not c:
                print('sin coordenadas:', item['id'])
                continue
            here = (c['lat'], c['lon'])
            cands = sorted(candidates(item, here), key=lambda x: -x[0])
            info, how = (cands[0][1], cands[0][2]) if cands and cands[0][0] >= 2 else (None, '')
            if not info:
                miss += 1
                print(f'  SIN FOTO  {item["id"]}')
                continue
            rel = f'/img/portal/{cat}/{fn[:-5]}.jpg'
            save(info, os.path.join(ROOT, *rel.strip('/').split('/')))
            item['foto_real'] = dict(archivo=rel, autor=info['autor'], licencia=info['licencia'],
                                     licencia_url=info['licencia_url'], fuente=info['fuente'], titulo=info['titulo'])
            with open(path, 'w', encoding='utf-8', newline='\n') as f:
                json.dump(item, f, ensure_ascii=False, indent=2)
                f.write('\n')
            ok += 1
            print(f'  ok  {item["id"]}  <- {info["titulo"]} ({info["licencia"]}; {how})')
    print(f'{ok} fotos, {miss} sin foto')


if __name__ == '__main__':
    main()
