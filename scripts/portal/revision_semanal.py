#!/usr/bin/env python3
"""Revisión semanal del portal: comprobación de páginas, enlaces de fuentes y calendario de caducidad.

Uso:  python scripts/portal/revision_semanal.py [--limite N] [--sin-red]

Lo ejecuta .github/workflows/revision-semanal.yml cada lunes, pero también sirve en local.
Hace cuatro cosas y lo deja todo en informe-revision.md (no se versiona):
  1. Ejecuta scripts/portal/check.py (enlaces internos, hreflang, datos estructurados).
  2. Comprueba cada URL de fuente de data/portal (fichas, metodología, calendario, destinos, eventos):
     marca como «rota» la que da 404/410 o no resuelve el dominio. Las que bloquean a los robots (403, 429) no cuentan.
  3. En las fuentes del calendario y de los eventos, busca el año más alto que menciona la página.
     Si sube respecto a la semana anterior (por ejemplo, de 2026 a 2027), es señal de edición nueva.
     La memoria está en data/portal/estado-fuentes.json (el flujo de GitHub la guarda).
  4. Ejecuta scripts/portal/caducidad.py y revisa los eventos cuya fecha ya pasó.
Escribe «problemas=N» en $GITHUB_OUTPUT si existe. Termina siempre con código 0: decide el flujo.
"""
import concurrent.futures
import datetime
import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
DATA = os.path.join(ROOT, 'data', 'portal')
ESTADO = os.path.join(DATA, 'estado-fuentes.json')
INFORME = os.path.join(ROOT, 'informe-revision.md')
UA = 'Mozilla/5.0 (compatible; MejorImposibleRevision/1.0; +https://mejorimposible.es/metodologia/)'
BLOQUEA = {401, 403, 405, 406, 429, 451, 999}
HOY = datetime.date.today()


def cargar(p):
    with open(os.path.join(DATA, p), encoding='utf-8') as f:
        return json.load(f)


def recoger_urls():
    """-> (todas, vigiladas): todas las URL de fuentes con dónde se usan; vigiladas = calendario y eventos."""
    todas, vig = {}, {}
    for dp, _, fns in os.walk(os.path.join(DATA, 'items')):
        for fn in fns:
            it = cargar(os.path.relpath(os.path.join(dp, fn), DATA))
            for u in it.get('fuentes', []):
                todas.setdefault(u, []).append(it['id'])
    for f in cargar('metodologia.json')['fuentes']:
        if f.get('url'):
            todas.setdefault(f['url'], []).append('metodologia')
    for f in cargar('calendario.json')['fuentes']:
        todas.setdefault(f['url'], []).append('calendario:' + f['id'])
        vig[f['url']] = 'calendario:' + f['id']
    for d in cargar('destinos.json')['destinos']:
        for u in d.get('fuentes', []):
            todas.setdefault(u, []).append('destino:' + d['slug'])
    if os.path.exists(os.path.join(DATA, 'eventos.json')):
        for ev in cargar('eventos.json')['eventos']:
            if ev.get('fuente_url'):
                todas.setdefault(ev['fuente_url'], []).append('evento:' + ev['id'])
                vig[ev['fuente_url']] = 'evento:' + ev['id']
    return todas, vig


def pedir(url, cuerpo=False):
    """-> (estado, texto). estado: código HTTP, 'dns', 'tiempo' o 'error'."""
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept': 'text/html,*/*;q=0.8', 'Accept-Language': 'es,en;q=0.7'})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            txt = r.read(1_500_000).decode('utf-8', 'ignore') if cuerpo else ''
            return r.status, txt
    except urllib.error.HTTPError as e:
        return e.code, ''
    except urllib.error.URLError as e:
        if isinstance(e.reason, socket.gaierror):
            return 'dns', ''
        if isinstance(e.reason, socket.timeout) or 'timed out' in str(e.reason):
            return 'tiempo', ''
        return 'error', ''
    except (socket.timeout, TimeoutError):
        return 'tiempo', ''
    except Exception:
        return 'error', ''


def anio_max(txt):
    ys = [int(y) for y in re.findall(r'(?<!\d)(20[2-3]\d)(?!\d)', re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', txt, flags=re.S))]
    ys = [y for y in ys if y <= HOY.year + 2]
    return max(ys) if ys else None


def revisar_url(args):
    url, vigilada = args
    estado, txt = pedir(url, cuerpo=vigilada)
    if estado in ('tiempo', 'error'):  # un segundo intento
        time.sleep(2)
        estado, txt = pedir(url, cuerpo=vigilada)
    return url, estado, (anio_max(txt) if (vigilada and txt) else None)


def correr(cmd):
    r = subprocess.run([sys.executable, *cmd], cwd=ROOT, capture_output=True, text=True, encoding='utf-8', errors='replace')
    return r.stdout + r.stderr


def main():
    limite = int(sys.argv[sys.argv.index('--limite') + 1]) if '--limite' in sys.argv else None
    sin_red = '--sin-red' in sys.argv
    out, problemas = [f'# Revisión semanal del portal · {HOY.isoformat()}\n'], 0

    # 1. comprobación de páginas
    chk = correr(['scripts/portal/check.py'])
    ultima = [l for l in chk.strip().splitlines() if l.strip()][-1] if chk.strip() else 'sin salida'
    malas = [l for l in chk.splitlines() if l.startswith('PROBLEMA')]
    out.append('## 1. Páginas del portal\n')
    out.append(f'{ultima}\n')
    if malas:
        problemas += 1
        out += ['```'] + malas[:40] + (['… (hay más)'] if len(malas) > 40 else []) + ['```\n']

    # 2 y 3. enlaces y fuentes vigiladas
    if not sin_red:
        todas, vig = recoger_urls()
        urls = sorted(todas)[:limite] if limite else sorted(todas)
        estado_prev = json.load(open(ESTADO, encoding='utf-8')) if os.path.exists(ESTADO) else {}
        estado_new = dict(estado_prev)
        rotas, bloqueadas, inestables, nuevas = [], 0, [], []
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
            for url, st, anio in ex.map(revisar_url, [(u, u in vig) for u in urls]):
                prev = estado_prev.get(url, {})
                if st in (404, 410, 'dns'):
                    rotas.append((url, st))
                elif st in ('tiempo', 'error'):
                    inestables.append((url, st))
                elif isinstance(st, int) and st in BLOQUEA:
                    bloqueadas += 1
                if url in vig:
                    if anio and prev.get('anio') and anio > prev['anio'] and anio >= HOY.year:
                        nuevas.append((url, vig[url], prev['anio'], anio))
                    if anio or url in estado_new:
                        estado_new[url] = {'anio': anio or prev.get('anio'), 'visto': HOY.isoformat()}
        out.append(f'## 2. Enlaces de fuentes ({len(urls)} comprobados)\n')
        out.append(f'Bloquean a los robots (no cuentan como rotos): {bloqueadas}. No respondieron: {len(inestables)}.\n')
        if rotas:
            problemas += 1
            out.append('**Enlaces rotos** (404, 410 o dominio inexistente):\n')
            for url, st in rotas:
                out.append(f'- {url} → {st} · usado en: {", ".join(sorted(set(todas[url]))[:4])}')
            out.append('')
        else:
            out.append('No hay enlaces rotos.\n')
        out.append('## 3. Señales de edición nueva en las fuentes vigiladas\n')
        if nuevas:
            problemas += 1
            for url, donde, a, b in nuevas:
                out.append(f'- {donde}: la página pasó de mencionar {a} a mencionar {b} → revisar si hay edición nueva ({url})')
            out.append('')
        else:
            out.append('Sin señales nuevas (se compara el año más alto que menciona cada página con el de la semana anterior).\n')
        if estado_new != estado_prev:
            with open(ESTADO, 'w', encoding='utf-8', newline='\n') as f:
                json.dump(estado_new, f, ensure_ascii=False, indent=1, sort_keys=True)
                f.write('\n')

    # 4. caducidad y eventos
    cad = correr(['scripts/portal/caducidad.py', '45'])
    out.append('## 4. Calendario de revisión\n')
    out.append('```\n' + cad.strip() + '\n```\n')
    if 'ESTE MES' in cad or re.search(r'en \d+ días', cad.split('== Fuentes sin mes fijo')[0]):
        problemas += 1
    if 'EVENTOS' in cad and 'pasaron' in cad:
        problemas += 1

    with open(INFORME, 'w', encoding='utf-8', newline='\n') as f:
        f.write('\n'.join(out) + '\n')
    print('\n'.join(out))
    salida = os.environ.get('GITHUB_OUTPUT')
    if salida:
        with open(salida, 'a', encoding='utf-8') as f:
            f.write(f'problemas={problemas}\n')
    print(f'problemas={problemas}')


if __name__ == '__main__':
    main()
