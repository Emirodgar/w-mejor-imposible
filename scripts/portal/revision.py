#!/usr/bin/env python3
"""Revisión nativa de las traducciones del portal.

Uso:
  python scripts/portal/revision.py exportar     -> crea revision-traducciones/<idioma>.xlsx (uno por idioma) y auditoria.md
  python scripts/portal/revision.py aplicar      -> lee las columnas «Corrección» rellenadas y actualiza data/portal/i18n/
  python scripts/portal/revision.py aplicar en   -> solo un idioma

Cada Excel lleva el texto original en español, la traducción actual, dónde aparece y dos columnas para el revisor:
«Corrección» (el texto definitivo) y «Comentario». «aplicar» solo toca las filas con «Corrección» rellena.
Después hay que regenerar el portal: python scripts/portal/build.py
La carpeta revision-traducciones/ no se versiona (está en .gitignore).
"""
import json
import os
import re
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
DATA = os.path.join(ROOT, 'data', 'portal')
OUT = os.path.join(ROOT, 'revision-traducciones')
LANGS = {'en': 'Inglés', 'fr': 'Francés', 'de': 'Alemán', 'pt': 'Portugués', 'it': 'Italiano'}
GLOSARIO = {  # término español -> traducción de referencia por idioma (convención del portal)
    'Llave Michelin': dict(en='Michelin Key', fr='Clé Michelin', de='Michelin-Schlüssel', pt='Chave Michelin', it='Chiave Michelin'),
    'estrella Michelin': dict(en='Michelin star', fr='étoile Michelin', de='Michelin-Stern', pt='estrela Michelin', it='stella Michelin'),
    'plan': dict(en='itinerary', fr='séjour', de='Reiseplan', pt='plano', it='itinerario'),
    'ranking': dict(en='ranking', fr='classement', de='Ranking', pt='ranking', it='classifica'),
    'Milla de Oro': dict(en='Golden Mile', fr="Mille d'Or", de='Goldene Meile', pt='Milha de Ouro', it="Miglio d'Oro"),
    'Por verificar': dict(en='To be verified', fr='À vérifier', de='Zu prüfen', pt='Por verificar', it='Da verificare'),
}


def load(p):
    with open(os.path.join(DATA, p), encoding='utf-8') as f:
        return json.load(f)


def contextos():
    """texto español -> dónde aparece (primer sitio encontrado en los datos)."""
    ctx = {}

    def walk(o, ruta):
        if isinstance(o, dict):
            if set(o) == {'es'} and isinstance(o['es'], str):
                ctx.setdefault(o['es'], ruta)
            else:
                for k, v in o.items():
                    walk(v, ruta + [k])
        elif isinstance(o, list):
            for i, v in enumerate(o):
                walk(v, ruta)
        elif isinstance(o, str) and len(o) > 2 and not o.startswith(('http', '/', 'data')):
            ctx.setdefault(o, ruta)
    for dp, _, fns in os.walk(DATA):
        if os.sep + 'i18n' in dp:
            continue
        for fn in sorted(fns):
            if not fn.endswith('.json'):
                continue
            rel = os.path.relpath(os.path.join(dp, fn), DATA).replace(os.sep, '/')
            walk(load(rel), [rel[:-5]])
    return ctx


def etiqueta(ruta):
    if not ruta:
        return 'Interfaz'
    f = ruta[0]
    campo = ' › '.join(str(x) for x in ruta[1:])
    cat = f.split('/')[0]
    tipo = {'items': 'Ficha de lugar', 'planes': 'Plan', 'categorias': 'Categoría', 'metodologia': 'Metodología',
            'rankings': 'Ranking', 'tiendas': 'Directorio de tiendas', 'concesionarios': 'Directorio de concesionarios',
            'destinos': 'Destinos', 'aeropuertos': 'Aeropuertos'}.get(cat, cat)
    return f'{tipo}: {f.split("/", 1)[-1]}' + (f' › {campo}' if campo else '')


def prioridad(k, es, ctx):
    if k.startswith('ui:'):
        return 'Alta'
    c = ctx.get(es)
    if c and c[0].split('/')[0] in ('categorias', 'metodologia', 'planes', 'destinos'):
        return 'Alta'
    return 'Media'


def filas(lang):
    ui = load('i18n/ui.json')
    tr = load(f'i18n/{lang}.json')
    ctx = contextos()
    rows = []
    for k in sorted(ui):
        rows.append(('ui:' + k, ui[k].get('es', ''), ui[k].get(lang, ''), 'Interfaz › ' + k))
    for es in sorted(tr, key=lambda s: (etiqueta(ctx.get(s)) if ctx.get(s) else 'zzz', s)):
        rows.append(('tx:' + es, es, tr[es], etiqueta(ctx.get(es)) if ctx.get(es) else 'Texto compuesto por el generador'))
    return rows, ctx


# ---------------- auditoría automática ----------------
PH = re.compile(r'\{[a-z_0-9]+\}')
NUM = re.compile(r'\d[\d.,]*')
ES_WORDS = re.compile(r'\b(de la|de los|del|para|con|los|las|una|según|entre|desde|hasta|más)\b', re.I)


def nums(s):
    return sorted(re.sub(r'[.,\s]', '', n) for n in NUM.findall(s))


def auditar(lang, rows):
    probs = []
    for k, es, tr, ctx in rows:
        if not tr.strip():
            probs.append((k, es, tr, 'Traducción vacía'))
            continue
        if sorted(PH.findall(es)) != sorted(PH.findall(tr)):
            probs.append((k, es, tr, 'Los marcadores {…} no coinciden'))
        if nums(es) != nums(tr) and not re.search(r'siglo|siècle|century|Jahrhundert|século|secolo|\d:\d\d|decim|tercer|puesto|número|n\.º', es + tr):
            probs.append((k, es, tr, 'Las cifras no coinciden'))
        if tr != tr.strip() or '  ' in tr:
            probs.append((k, es, tr, 'Espacios sobrantes'))
        if es == tr and ES_WORDS.search(es) and len(es) > 25 and not all(w[0].isupper() for w in es.split() if len(w) > 3):
            probs.append((k, es, tr, 'Igual que el español y con palabras españolas: ¿sin traducir?'))
        if len(es) > 30 and not (0.45 <= len(tr) / len(es) <= 2.3):
            probs.append((k, es, tr, f'Longitud muy distinta ({len(tr)} frente a {len(es)} caracteres)'))
        if lang != 'es' and re.search(r'\b(Llave|llaves|estrella[s]?|Aeropuerto|Compras|Hotel de)\b', tr) and lang in ('en', 'de'):
            probs.append((k, es, tr, 'Contiene una palabra española'))
    for term, tr_map in GLOSARIO.items():
        for k, es, tr, ctx in rows:
            if re.search(r'' + re.escape(term.lower()) + r'(es)?', es.lower()) and tr_map[lang].lower() not in tr.lower() and len(es) < 120:
                probs.append((k, es, tr, f'Glosario: «{term}» debería aparecer como «{tr_map[lang]}»'))
    return probs


def exportar():
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    os.makedirs(OUT, exist_ok=True)
    resumen = ['# Auditoría automática de las traducciones\n']
    for lang, nombre in LANGS.items():
        rows, ctx = filas(lang)
        probs = auditar(lang, rows)
        marcados = {p[0] for p in probs}
        motivos = {}
        for p in probs:
            motivos.setdefault(p[0], []).append(p[3])
        wb = Workbook()
        ws = wb.active
        ws.title = 'Instrucciones'
        txt = [
            f'Revisión de las traducciones al {nombre.lower()} de Mejor Imposible',
            '',
            'Qué es: un portal de rankings de lujo en España. Información y rankings, sin precios ni reservas.',
            'Tono: sobrio, elegante y claro; frases cortas. Sin exageraciones ni lenguaje publicitario.',
            '',
            'Cómo revisar (hoja «Textos»):',
            '1. Lee el español original, la traducción actual y «Dónde aparece» para entender el contexto.',
            '2. Si la traducción es correcta, no hagas nada.',
            '3. Si hay que cambiarla, escribe el texto definitivo completo en la columna «Corrección». No hace falta comentar.',
            '4. Usa «Comentario» solo para dudas o para explicar un cambio que afecte a más de una fila.',
            '5. Respeta los marcadores como {n} o {a}: se sustituyen por números y nombres.',
            '6. Los nombres propios (hoteles, restaurantes, marcas) no se traducen.',
            '',
            'Prioridad «Alta»: textos que se ven en muchas páginas (menús, títulos, descripciones de rankings y planes). Empieza por ahí.',
            'La columna «Aviso» indica lo que ha detectado una comprobación automática; son pistas, no errores seguros.',
            '',
            'Glosario de referencia (convención del portal):',
        ] + [f'  {es}  →  {m[lang]}' for es, m in GLOSARIO.items()]
        for i, line in enumerate(txt, 1):
            ws.cell(i, 1, line)
        ws['A1'].font = Font(bold=True, size=14)
        ws.column_dimensions['A'].width = 120
        w2 = wb.create_sheet('Textos')
        head = ['ID', 'Prioridad', 'Dónde aparece', 'Español (original)', f'{nombre} (actual)', 'Corrección', 'Comentario', 'Aviso']
        w2.append(head)
        for c in w2[1]:
            c.font = Font(bold=True, color='FFFFFF')
            c.fill = PatternFill('solid', fgColor='16140F')
        for k, es, tr, c in rows:
            w2.append([k, prioridad(k, es, ctx), c, es, tr, None, None, ' · '.join(motivos.get(k, []))])
        for col, wd in zip('ABCDEFGH', (10, 10, 36, 60, 60, 60, 36, 40)):
            w2.column_dimensions[col].width = wd
        w2.column_dimensions['A'].hidden = True
        for r in w2.iter_rows(min_row=2):
            for c in r:
                c.alignment = Alignment(wrap_text=True, vertical='top')
            if r[7].value:
                r[7].fill = PatternFill('solid', fgColor='FFF2CC')
            r[5].fill = PatternFill('solid', fgColor='E2EFDA')
        w2.freeze_panes = 'A2'
        w2.auto_filter.ref = f'A1:H{w2.max_row}'
        wb.save(os.path.join(OUT, f'{lang}.xlsx'))
        resumen.append(f'\n## {nombre} ({lang}): {len(rows)} textos, {len(marcados)} con aviso\n')
        for k, es, tr, mot in probs[:60]:
            resumen.append(f'- `{k[:70]}` — {mot}\n  - ES: {es[:110]}\n  - {lang.upper()}: {tr[:110]}')
        if len(probs) > 60:
            resumen.append(f'- … y {len(probs) - 60} avisos más (columna «Aviso» del Excel)')
    with open(os.path.join(OUT, 'auditoria.md'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(resumen) + '\n')
    print('Creado en', OUT)


def aplicar(solo=None):
    from openpyxl import load_workbook
    ui_path = os.path.join(DATA, 'i18n', 'ui.json')
    ui = load('i18n/ui.json')
    cambios = 0
    for lang in LANGS:
        if solo and lang != solo:
            continue
        fx = os.path.join(OUT, f'{lang}.xlsx')
        if not os.path.exists(fx):
            continue
        tp = os.path.join(DATA, 'i18n', f'{lang}.json')
        tr = load(f'i18n/{lang}.json')
        ws = load_workbook(fx)['Textos']
        n = 0
        for row in ws.iter_rows(min_row=2, values_only=True):
            k, corr = row[0], row[5]
            if not corr or not str(corr).strip():
                continue
            corr = str(corr).strip()
            if k.startswith('ui:'):
                key = k[3:]
                if key in ui and ui[key].get(lang) != corr:
                    ui[key][lang] = corr
                    n += 1
            elif k.startswith('tx:'):
                es = k[3:]
                if es in tr and tr[es] != corr:
                    tr[es] = corr
                    n += 1
        with open(tp, 'w', encoding='utf-8', newline='\n') as f:
            json.dump(tr, f, ensure_ascii=False, indent=1)
        print(f'{lang}: {n} correcciones aplicadas')
        cambios += n
    with open(ui_path, 'w', encoding='utf-8', newline='\n') as f:
        json.dump(ui, f, ensure_ascii=False, indent=2)
    print('Total:', cambios, '— ahora ejecuta: python scripts/portal/build.py')


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else ''
    if cmd == 'exportar':
        exportar()
    elif cmd == 'aplicar':
        aplicar(sys.argv[2] if len(sys.argv) > 2 else None)
    else:
        print(__doc__)
