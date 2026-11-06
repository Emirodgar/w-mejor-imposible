#!/usr/bin/env python3
"""Calendario de revisión de los rankings: qué fuentes tocan pronto y qué rankings hay que actualizar.

Uso:  python scripts/portal/caducidad.py [días]      (por defecto, 45 días de margen)

Lee data/portal/calendario.json (fuentes, mes habitual de publicación y rankings que dependen de cada una)
y data/portal/rankings/*.json (fecha de la última actualización de cada ranking).
No cambia nada: solo imprime lo que hay que revisar.
"""
import datetime
import json
import os
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
DATA = os.path.join(ROOT, 'data', 'portal')
MESES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre']
SEIS_MESES = 183


def main():
    margen = int(sys.argv[1]) if len(sys.argv) > 1 else 45
    hoy = datetime.date.today()
    cal = json.load(open(os.path.join(DATA, 'calendario.json'), encoding='utf-8'))['fuentes']
    print(f'Hoy: {hoy.isoformat()}  ·  margen: {margen} días\n')
    proximas, sin_mes = [], []
    for f in cal:
        if f.get('mes'):
            y = hoy.year if datetime.date(hoy.year, f['mes'], 1) >= hoy.replace(day=1) else hoy.year + 1
            inicio = datetime.date(y, f['mes'], 1)
            fin = (datetime.date(y + (f['mes'] == 12), f['mes'] % 12 + 1, 1)) - datetime.timedelta(days=1)
            dias = max(0, (inicio - hoy).days)
            en_curso = inicio <= hoy <= fin
            proximas.append((0 if en_curso else dias, f, inicio, en_curso))
        else:
            sin_mes.append(f)
    print('== Fuentes que publican pronto (o este mes) ==')
    hay = False
    for dias, f, inicio, en_curso in sorted(proximas, key=lambda x: x[0]):
        if en_curso or dias <= margen:
            hay = True
            cuando = 'ESTE MES' if en_curso else f'en {dias} días ({MESES[inicio.month - 1]} de {inicio.year})'
            print(f'- {f["fuente"]}: {cuando}')
            print(f'    actualizar: {", ".join(f["categorias"])}  ·  confianza de la fecha: {f["confianza"]}')
            print(f'    nota: {f["nota_interna"]}')
    if not hay:
        print('- Ninguna dentro del margen.')
    print('\n== Fuentes sin mes fijo: revisar cada seis meses ==')
    for f in sin_mes:
        print(f'- {f["fuente"]} → {", ".join(f["categorias"])}  ({f["nota_interna"]})')
    print('\n== Rankings por antigüedad ==')
    filas = []
    for fn in sorted(os.listdir(os.path.join(DATA, 'rankings'))):
        r = json.load(open(os.path.join(DATA, 'rankings', fn), encoding='utf-8'))
        filas.append((r['categoria'], r.get('actualizado', {}).get('es', '?')))
    for cat, act in filas:
        print(f'- {cat}: {act}')
    print('\nRecuerda: al actualizar un ranking, cambia «actualizado» en data/portal/rankings/<cat>.json y añade una línea en data/portal/cambios.json.')


if __name__ == '__main__':
    main()
