#!/usr/bin/env python3
"""Genera llms.txt y feed.xml (Atom) a partir del front matter de blog/*.md y de las fichas de modelo.

Uso:  python scripts/llms_y_feed.py [--portal]

  --portal   añade al llms.txt el portal nuevo (rankings, planes, metodología). Usarlo cuando el portal
             deje de ser borrador: mientras tanto sus páginas llevan noindex y no se anuncian.
"""
import datetime
import glob
import html
import os
import re
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
SITE = 'https://mejorimposible.es'


def front(path):
    """Devuelve el front matter de un archivo como dict de cadenas (solo claves de primer nivel)."""
    txt = open(path, encoding='utf-8').read()
    m = re.match(r'---\r?\n(.*?)\r?\n---', txt, re.S)
    out = {}
    for line in (m.group(1).splitlines() if m else []):
        k = re.match(r'^([A-Za-z_]+):\s*(.*)$', line)
        if k:
            out[k.group(1)] = k.group(2).strip().strip('"\'')
    return out


def posts():
    rows = []
    for f in glob.glob(os.path.join(ROOT, 'blog', '*.md')):
        fm = front(f)
        if fm.get('feed') != '1' or not fm.get('permalink'):
            continue
        rows.append({'title': fm['title'], 'desc': fm.get('description', ''), 'date': fm.get('date', ''),
                     'url': f"{SITE}/{fm['permalink'].strip('/')}", 'tema': fm.get('folder', '')})
    return sorted(rows, key=lambda r: r['date'], reverse=True)


def models():
    rows = []
    for f in sorted(glob.glob(os.path.join(ROOT, 'porsche', 'modelos', '*.html'))):
        fm = front(f)
        rows.append({'title': fm.get('model_name', os.path.basename(f)[:-5]), 'desc': fm.get('description', ''),
                     'url': f"{SITE}/porsche/modelos/{os.path.basename(f)[:-5]}"})
    return rows


def dealers():
    return len(glob.glob(os.path.join(ROOT, 'porsche', 'concesionarios', '*.html')))


def llms(with_portal):
    ps, ms = posts(), models()
    out = ['# Mejor Imposible', '',
           '> Guías independientes en español para comprar y mantener un Porsche en España (modelos, fiabilidad, costes, '
           'segunda mano, concesionarios, comparativas) y, en el portal, rankings de lo mejor de España en hoteles, golf, '
           'restaurantes, bodegas, spas, casas, yates y motor. Nadie paga por aparecer. Idioma principal: español.', '',
           '## Modelos Porsche']
    out += [f"- [{m['title']}]({m['url']}): {m['desc']}" for m in ms]
    out += ['', '## Guías y artículos']
    out += [f"- [{p['title']}]({p['url']}): {p['desc']}" for p in ps]
    out += ['', '## Herramientas y datos',
            f'- [Concesionarios oficiales Porsche]({SITE}/porsche/concesionarios): {dealers()} centros con dirección, teléfono y valoración media en Google',
            f'- [Comparativas]({SITE}/porsche/comparativas): Porsche frente a sus rivales directos',
            f'- [Tendencias semanales]({SITE}/porsche/tendencias): resumen semanal de noticias sobre la marca']
    if with_portal:
        out += ['', '## Portal de rankings',
                f'- [Cómo elaboramos los rankings]({SITE}/metodologia/): criterios, fuentes y límites',
                f'- [Destinos]({SITE}/destinos/): rankings y planes por zona']
        for slug in sorted(os.listdir(os.path.join(ROOT, 'ranking'))):
            if os.path.isdir(os.path.join(ROOT, 'ranking', slug)):
                out.append(f'- [Ranking: {slug.replace("-", " ")}]({SITE}/ranking/{slug}/)')
        for slug in sorted(os.listdir(os.path.join(ROOT, 'planes'))):
            if os.path.isdir(os.path.join(ROOT, 'planes', slug)):
                out.append(f'- [Plan: {slug.replace("-", " ")}]({SITE}/planes/{slug}/)')
    out += ['', '## Contexto', '- Sitemap: ' + SITE + '/sitemap.xml',
            '- Traducciones del portal: /en/, /fr/, /de/, /it/, /pt/', '']
    return '\n'.join(out)


def feed():
    ps = posts()
    upd = (ps[0]['date'] if ps else datetime.date.today().isoformat()) + 'T00:00:00Z'
    e = html.escape
    ents = ''.join(
        f"\n  <entry>\n    <title>{e(p['title'])}</title>\n    <link href=\"{p['url']}\"/>\n    <id>{p['url']}</id>\n"
        f"    <updated>{p['date']}T00:00:00Z</updated>\n    <summary>{e(p['desc'])}</summary>\n"
        f"    <author><name>Emilio Rodríguez García</name><uri>https://www.linkedin.com/in/emirodgar/</uri></author>\n  </entry>" for p in ps)
    return ('<?xml version="1.0" encoding="UTF-8"?>\n<feed xmlns="http://www.w3.org/2005/Atom" xml:lang="es">\n'
            f'  <title>Mejor Imposible: guías Porsche</title>\n  <subtitle>Guías de compra, costes y novedades de Porsche en España</subtitle>\n'
            f'  <link href="{SITE}/feed.xml" rel="self"/>\n  <link href="{SITE}/porsche/blog"/>\n  <id>{SITE}/</id>\n'
            f'  <updated>{upd}</updated>{ents}\n</feed>\n')


if __name__ == '__main__':
    for name, content in (('llms.txt', llms('--portal' in sys.argv)), ('feed.xml', feed())):
        with open(os.path.join(ROOT, name), 'w', encoding='utf-8', newline='\n') as f:
            f.write(content)
        print('escrito', name)
