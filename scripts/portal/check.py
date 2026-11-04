#!/usr/bin/env python3
"""Revisa las páginas generadas del portal: enlaces internos, JSON-LD, títulos, h1, hreflang e ids duplicados.

Uso:  python scripts/portal/check.py
Sale con código 1 si encuentra problemas.
"""
import json
import os
import re
import sys
from html.parser import HTMLParser

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build  # noqa: E402  (solo para leer PUBLISHED y la lista de páginas; no escribe nada)

SITE = build.SITE


class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links, self.ids, self.h1, self.ld, self.alternates = [], [], 0, [], {}
        self.title, self.desc, self.lang, self.robots, self.canonical = '', '', '', '', ''
        self._in_title = self._in_ld = False
        self._buf = ''

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if 'id' in a:
            self.ids.append(a['id'])
        if tag == 'html':
            self.lang = a.get('lang', '')
        if tag == 'h1':
            self.h1 += 1
        if tag in ('a', 'link') and a.get('href'):
            if tag == 'link' and a.get('rel') == 'alternate' and a.get('hreflang'):
                self.alternates[a['hreflang']] = a['href']
            elif tag == 'link' and a.get('rel') == 'canonical':
                self.canonical = a['href']
            elif tag == 'a':
                self.links.append(a['href'])
        if tag in ('img', 'script', 'source') and a.get('src'):
            self.links.append(a['src'])
        if tag == 'link' and a.get('rel') in ('stylesheet', 'icon') and a.get('href'):
            self.links.append(a['href'])
        if tag == 'meta':
            if a.get('name') == 'description':
                self.desc = a.get('content', '')
            if a.get('name') == 'robots':
                self.robots = a.get('content', '')
        if tag == 'title':
            self._in_title = True
        if tag == 'script' and a.get('type') == 'application/ld+json':
            self._in_ld = True
            self._buf = ''

    def handle_endtag(self, tag):
        if tag == 'title':
            self._in_title = False
        if tag == 'script' and self._in_ld:
            self._in_ld = False
            self.ld.append(self._buf)

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        if self._in_ld:
            self._buf += data


def file_for(url):
    """Ruta de archivo para un enlace interno (None si es externo o de otro tipo)."""
    url = url.split('#')[0].split('?')[0]
    if not url.startswith('/'):
        return None
    p = os.path.join(ROOT, *url.strip('/').split('/'))
    if url.endswith('/') or os.path.isdir(p):
        return os.path.join(p, 'index.html')
    return p if os.path.splitext(p)[1] else p + '.html'


def main():
    problems = []
    pages = {}
    for lang in build.PUBLISHED:
        for path in build.PAGE_PATHS:
            rel = (build.prefix(lang) + path).strip('/')
            f = os.path.join(ROOT, *rel.split('/')) if rel else ROOT
            if path.endswith('/'):
                f = os.path.join(f, 'index.html')
            pages[(lang, path)] = f
    for (lang, path), f in pages.items():
        name = f'{lang}:{path}'
        if not os.path.exists(f):
            problems.append(f'{name}: no existe {os.path.relpath(f, ROOT)}')
            continue
        p = Page()
        p.feed(open(f, encoding='utf-8').read())
        if p.lang != lang:
            problems.append(f'{name}: lang="{p.lang}"')
        if p.h1 != 1:
            problems.append(f'{name}: {p.h1} etiquetas h1')
        if not 10 <= len(p.title) <= 70:
            problems.append(f'{name}: título de {len(p.title)} caracteres ({p.title!r})')
        if not 50 <= len(p.desc) <= 200:
            problems.append(f'{name}: descripción de {len(p.desc)} caracteres')
        dup = {i for i in p.ids if p.ids.count(i) > 1}
        if dup:
            problems.append(f'{name}: ids duplicados {sorted(dup)}')
        for raw in p.ld:
            try:
                json.loads(raw)
            except ValueError as ex:
                problems.append(f'{name}: JSON-LD inválido ({ex})')
        if build.NOINDEX != ('noindex' in p.robots):
            problems.append(f'{name}: robots={p.robots!r} no coincide con NOINDEX={build.NOINDEX}')
        want = {c: SITE + build.prefix(c) + path for c in build.PUBLISHED}
        want['x-default'] = SITE + path
        if p.alternates != want:
            problems.append(f'{name}: hreflang distinto del esperado')
        if p.canonical != SITE + build.prefix(lang) + path:
            problems.append(f'{name}: canonical {p.canonical}')
        for link in p.links:
            target = file_for(link)
            if target and not os.path.exists(target):
                problems.append(f'{name}: enlace roto {link}')
            if target and '#' in link:
                anchor = link.split('#')[1]
                if anchor and os.path.exists(target) and target.endswith('.html') and target != f:
                    t = Page()
                    t.feed(open(target, encoding='utf-8').read())
                    if anchor not in t.ids:
                        problems.append(f'{name}: ancla inexistente {link}')
            if link.startswith('#') and len(link) > 1 and link[1:] not in p.ids:
                problems.append(f'{name}: ancla interna inexistente {link}')
    for p in problems:
        print('PROBLEMA', p)
    print(f'{len(pages)} páginas revisadas, {len(problems)} problemas')
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main())
