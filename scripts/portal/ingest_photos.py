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


def write_pending():
    os.makedirs(SRC, exist_ok=True)
    lines = []
    for _, it in items():
        fr = it.get('foto_real')
        if not fr or fr.get('origen') != 'propia':
            estado = 'sin foto' if not fr else 'foto de Wikimedia Commons'
            lines.append(f'{it["id"]}.jpg   ({estado})   {it["nombre"]}, {it["lugar"]}')
    sin = [ln for ln in lines if '(sin foto)' in ln]
    con = [ln for ln in lines if '(sin foto)' not in ln]
    with open(os.path.join(SRC, 'PENDIENTES.txt'), 'w', encoding='utf-8', newline='\n') as f:
        f.write('Fotos pendientes. Guarda cada una en fotos-propias/ con la ruta indicada (categoria/slug.jpg).\n\n')
        f.write(f'SIN FOTO ({len(sin)})\n' + '\n'.join(sin) + '\n\n')
        f.write(f'CON FOTO DE WIKIMEDIA COMMONS, SUSTITUIBLE ({len(con)})\n' + '\n'.join(con) + '\n')
    print(f'PENDIENTES.txt: {len(sin)} sin foto, {len(con)} con foto de Commons')


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
