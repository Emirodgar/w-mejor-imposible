#!/usr/bin/env python3
"""Incorpora fotos propias a las fichas del portal.

Uso:
  python scripts/portal/ingest_photos.py            # procesa fotos-propias/ y regenera la lista de pendientes
  python scripts/portal/ingest_photos.py --list     # solo escribe fotos-propias/PENDIENTES.txt

Cómo se usa:
  1. Deja las fotos en fotos-propias/<categoria>/<slug>.jpg (también .jpeg, .png o .webp). El nombre es el
     del archivo de la ficha, por ejemplo fotos-propias/golf/real-club-valderrama.jpg.
     fotos-propias/PENDIENTES.txt lista las fichas que aún no tienen foto y el nombre que debe tener cada una.
  2. (Opcional) fotos-propias/creditos.json con el autor de cada foto: {"golf/real-club-valderrama": "Nombre Apellido"}.
     Si no se indica, el crédito es "Mejor Imposible".
  3. Ejecuta este script y luego scripts/portal/build.py.

El script reduce cada foto a 1200 px de ancho, la guarda como JPEG en img/portal/<categoria>/<slug>.jpg
(sin metadatos EXIF, también sin la ubicación GPS) y apunta "foto_real" en la ficha, con origen "propia".
Una foto propia sustituye a la de Wikimedia Commons que hubiera. Las fotos de menos de 1000 px de ancho se
rechazan. Las originales de fotos-propias/ no se suben al repositorio.
"""
import glob
import json
import os
import sys

from PIL import Image, ImageOps

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
SRC = os.path.join(ROOT, 'fotos-propias')
ITEMS = os.path.join(ROOT, 'data', 'portal', 'items')
EXT = ('.jpg', '.jpeg', '.png', '.webp')
MIN_W = 1000


def items():
    for path in sorted(glob.glob(os.path.join(ITEMS, '*', '*.json'))):
        with open(path, encoding='utf-8') as f:
            yield path, json.load(f)


def usage():
    """Dónde se muestra la foto de cada ficha: puestos 1-5 de su ranking (los demás no llevan foto) y pasos de planes."""
    where = {}
    for path in glob.glob(os.path.join(ROOT, 'data', 'portal', 'rankings', '*.json')):
        with open(path, encoding='utf-8') as f:
            rk = json.load(f)
        for pos, ref in enumerate(rk['items'][:5], 1):
            where.setdefault(ref, []).append(f'puesto {pos} de su ranking')
    for path in glob.glob(os.path.join(ROOT, 'data', 'portal', 'planes', '*.json')):
        with open(path, encoding='utf-8') as f:
            plan = json.load(f)
        for day in plan['dias']:
            for st in day['pasos']:
                if st.get('ref'):
                    where.setdefault(st['ref'], []).append('plan ' + plan['slug'])
    return where


def write_pending():
    os.makedirs(SRC, exist_ok=True)
    where = usage()
    prio, resto, con = [], [], []
    for _, it in items():
        fr = it.get('foto_real')
        if fr and fr.get('origen') == 'propia':
            continue
        line = f'{it["id"]}.jpg   {it["nombre"]}, {it["lugar"]}'
        if fr:
            con.append(line)
        elif it['id'] in where:
            prio.append(line + '   [' + '; '.join(sorted(set(where[it['id']]))) + ']')
        else:
            resto.append(line)
    with open(os.path.join(SRC, 'PENDIENTES.txt'), 'w', encoding='utf-8', newline='\n') as f:
        f.write('Fotos pendientes. Guarda cada una en fotos-propias/ con la ruta indicada (categoria/slug.jpg).\n'
                'Las fichas del puesto 6 en adelante no muestran foto, así que no hace falta cubrirlas.\n\n')
        f.write(f'1. SIN FOTO Y SE MUESTRA YA ({len(prio)})\n' + '\n'.join(prio) + '\n\n')
        f.write(f'2. SIN FOTO, SIN HUECO EN LA WEB TODAVÍA ({len(resto)})\n' + '\n'.join(resto) + '\n\n')
        f.write(f'3. CON FOTO DE WIKIMEDIA COMMONS, SUSTITUIBLE ({len(con)})\n' + '\n'.join(con) + '\n')
    print(f'PENDIENTES.txt: {len(prio)} sin foto y visibles, {len(resto)} sin foto no visibles, {len(con)} con foto de Commons')


def find_source(cat, slug):
    for ext in EXT:
        for cand in (slug + ext, slug + ext.upper()):
            p = os.path.join(SRC, cat, cand)
            if os.path.exists(p):
                return p
    return None


def main():
    if '--list' in sys.argv:
        write_pending()
        return
    creditos = {}
    cp = os.path.join(SRC, 'creditos.json')
    if os.path.exists(cp):
        with open(cp, encoding='utf-8') as f:
            creditos = json.load(f)
    done = 0
    for path, it in items():
        cat, slug = it['id'].split('/')
        src = find_source(cat, slug)
        if not src:
            continue
        im = ImageOps.exif_transpose(Image.open(src)).convert('RGB')
        if im.width < MIN_W or im.height > im.width:
            print(f'  RECHAZADA {it["id"]}: {im.width}x{im.height} (hace falta horizontal y de al menos {MIN_W} px de ancho)')
            continue
        if im.width > 1200:
            im = im.resize((1200, round(im.height * 1200 / im.width)), Image.LANCZOS)
        rel = f'/img/portal/{cat}/{slug}.jpg'
        dest = os.path.join(ROOT, *rel.strip('/').split('/'))
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        im.save(dest, 'JPEG', quality=82, optimize=True, progressive=True)
        it['foto_real'] = {'archivo': rel, 'autor': creditos.get(it['id'], 'Mejor Imposible'),
                           'licencia': 'Propia', 'origen': 'propia'}
        with open(path, 'w', encoding='utf-8', newline='\n') as f:
            json.dump(it, f, ensure_ascii=False, indent=2)
            f.write('\n')
        done += 1
        print(f'  ok  {it["id"]}  <- {os.path.relpath(src, ROOT)}')
    print(f'{done} fotos incorporadas')
    write_pending()


if __name__ == '__main__':
    main()
