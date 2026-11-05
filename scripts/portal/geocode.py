#!/usr/bin/env python3
"""Añade coordenadas (OpenStreetMap / Nominatim) a los ítems y aeropuertos que aún no las tienen.

Uso:  python scripts/portal/geocode.py [--force]

Cada ítem de data/portal/items/**, cada aeropuerto de data/portal/aeropuertos.json y cada
concesionario de data/portal/concesionarios/lujo.json
puede traer "busqueda" (texto exacto para Nominatim). Se guarda "coordenadas": {"lat", "lon"}
y "geo_fuente" con el nombre que devolvió el servicio, para poder revisarlo a ojo.
Respeta el límite de 1 petición por segundo de Nominatim.
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
DATA = os.path.join(ROOT, 'data', 'portal')
UA = 'mejorimposible-portal-build/1.0'
# Caja aproximada de España (incluye Baleares y Canarias)
BBOX = (27.4, 43.9, -18.5, 4.5)  # lat_min, lat_max, lon_min, lon_max


def geocode(q):
    url = 'https://nominatim.openstreetmap.org/search?' + urllib.parse.urlencode(
        {'q': q, 'format': 'json', 'limit': 1})
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=20) as r:
        res = json.load(r)
    if not res:
        return None
    lat, lon = float(res[0]['lat']), float(res[0]['lon'])
    if not (BBOX[0] <= lat <= BBOX[1] and BBOX[2] <= lon <= BBOX[3]):
        return None
    return round(lat, 5), round(lon, 5), res[0]['display_name']


def fill(obj, force):
    if obj.get('coordenadas') and not force:
        return False
    q = obj.get('busqueda')
    if not q:
        print(f"  sin 'busqueda': {obj.get('id') or obj.get('nombre')}")
        return False
    got = geocode(q)
    time.sleep(1.1)
    if not got:
        print(f"  NO ENCONTRADO: {q}")
        return False
    obj['coordenadas'] = {'lat': got[0], 'lon': got[1]}
    obj['geo_fuente'] = got[2][:90]
    print(f"  {obj.get('id') or obj.get('nombre')}: {got[0]}, {got[1]}  <- {got[2][:70]}")
    return True


def save(path, obj):
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write('\n')


if __name__ == '__main__':
    force = '--force' in sys.argv
    air_path = os.path.join(DATA, 'aeropuertos.json')
    with open(air_path, encoding='utf-8') as f:
        air = json.load(f)
    if any([fill(a, force) for a in air['aeropuertos']]):
        save(air_path, air)
    dl_path = os.path.join(DATA, 'concesionarios', 'lujo.json')
    with open(dl_path, encoding='utf-8') as f:
        dl = json.load(f)
    if any([fill(d, force) for d in dl['concesionarios']]):
        save(dl_path, dl)
    sp_path = os.path.join(DATA, 'tiendas', 'lujo.json')
    if os.path.exists(sp_path):
        with open(sp_path, encoding='utf-8') as f:
            sp = json.load(f)
        if any([fill(d, force) for d in sp['tiendas']]):
            save(sp_path, sp)
    for cat in sorted(os.listdir(os.path.join(DATA, 'items'))):
        for fn in sorted(os.listdir(os.path.join(DATA, 'items', cat))):
            p = os.path.join(DATA, 'items', cat, fn)
            with open(p, encoding='utf-8') as f:
                item = json.load(f)
            if fill(item, force):
                save(p, item)
