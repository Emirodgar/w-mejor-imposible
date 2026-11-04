#!/usr/bin/env python3
"""Añade coordenadas a data/portal/michelin/guia-2026.json (OpenStreetMap / Nominatim).

Uso:  python scripts/portal/geocode_michelin.py [--force]

Para cada restaurante busca "<nombre>, <ciudad>"; el resultado solo se acepta si cae a menos de
25 km del centro de su ciudad. Si no aparece (OpenStreetMap no tiene todos los locales) se usa el
centro de la ciudad y se marca "geo_precision": "localidad". Es reanudable: guarda tras cada
restaurante y se salta los que ya tienen coordenadas. Tarda unos 10 minutos (1 petición/segundo).
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from geocode import BBOX, UA, geocode, save  # noqa: E402
import math  # noqa: E402
import urllib.parse  # noqa: E402
import urllib.request  # noqa: E402

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
PATH = os.path.join(ROOT, 'data', 'portal', 'michelin', 'guia-2026.json')
ANDORRA = {'Soldeu'}


def search(q, country):
    url = 'https://nominatim.openstreetmap.org/search?' + urllib.parse.urlencode(
        {'q': q, 'format': 'json', 'limit': 1, 'countrycodes': country})
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=25) as r:
                res = json.load(r)
            break
        except Exception:
            time.sleep(3)
    else:
        return None
    time.sleep(1.1)
    if not res:
        return None
    lat, lon = float(res[0]['lat']), float(res[0]['lon'])
    if country == 'es' and not (BBOX[0] <= lat <= BBOX[1] and BBOX[2] <= lon <= BBOX[3]):
        return None
    return round(lat, 5), round(lon, 5), res[0]['display_name']


def km(a, b):
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


if __name__ == '__main__':
    force = '--force' in sys.argv
    with open(PATH, encoding='utf-8') as f:
        data = json.load(f)
    cities = {}
    todo = [r for r in data['restaurantes'] if force or not r.get('coordenadas')]
    print(f'{len(todo)} por geocodificar')
    for n, r in enumerate(todo, 1):
        country = 'ad' if r['ciudad'] in ANDORRA else 'es'
        city = r['ciudad']
        if city not in cities:
            cities[city] = search(f'{city}, {"Andorra" if country == "ad" else "España"}', country)
        c = cities[city]
        hit = search(f"{r['nombre']}, {city}", country)
        if hit and c and km(hit[:2], c[:2]) <= 25:
            r['coordenadas'], r['geo_precision'] = {'lat': hit[0], 'lon': hit[1]}, 'local'
        elif c:
            r['coordenadas'], r['geo_precision'] = {'lat': c[0], 'lon': c[1]}, 'localidad'
        else:
            print(f"  SIN COORDENADAS: {r['nombre']} ({city})")
            continue
        if n % 10 == 0:
            save(PATH, data)
            print(f'  {n}/{len(todo)}')
    save(PATH, data)
    ok = [r for r in data['restaurantes'] if r.get('coordenadas')]
    loc = sum(1 for r in ok if r['geo_precision'] == 'local')
    print(f'listo: {len(ok)} con coordenadas ({loc} del local, {len(ok) - loc} del centro de la ciudad)')
