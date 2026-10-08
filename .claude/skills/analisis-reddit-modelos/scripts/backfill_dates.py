#!/usr/bin/env python3
"""Añade `created` (fecha del comentario, epoch UTC) a los comentarios ya guardados.

Es solo aditivo: no quita ni cambia ningun campo existente, solo rellena `created` donde falta,
en comments.jsonl (local, con texto) y comments-index.jsonl (versionado, sin texto). Vuelve a pedir
a Arctic Shift los comentarios de cada hilo guardado, asi que tarda unos minutos.
Antes de reescribir deja copia en .claude/state/analisis-reddit/archivo/ (nunca se borra nada).
Uso: python backfill_dates.py
"""
import json, os, shutil, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fetch_threads import STATE, flatten, get  # reutiliza cliente, reintentos y rutas


def main():
    threads = json.load(open(os.path.join(STATE, "threads.json"), encoding="utf-8"))
    dates = {}
    for i, t in enumerate(threads, 1):
        tree = get("/comments/tree", {"link_id": t["id"], "limit": 2000})
        if tree is None:
            print(f"  [{i}/{len(threads)}] {t['id']}: sin respuesta, se reintentara en otra pasada", file=sys.stderr)
            continue
        cs = []
        flatten(tree, cs)
        for c in cs:
            if c.get("created_utc"):
                dates[c["id"]] = c["created_utc"]
        print(f"  [{i}/{len(threads)}] {t['title'][:50]!r}: {len(cs)} fechas", file=sys.stderr)
        time.sleep(1.2)

    arch = os.path.join(STATE, "archivo")
    os.makedirs(arch, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    for fn in ("comments.jsonl", "comments-index.jsonl"):
        path = os.path.join(STATE, fn)
        if not os.path.exists(path):
            continue
        shutil.copy2(path, os.path.join(arch, f"{fn[:-6]}-antes-de-fechas-{stamp}.jsonl"))
        rows, filled, missing = [], 0, 0
        for line in open(path, encoding="utf-8"):
            c = json.loads(line)
            if not c.get("created"):
                if c["id"] in dates:
                    c["created"] = dates[c["id"]]
                    filled += 1
                else:
                    missing += 1
            rows.append(c)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            for c in rows:
                f.write(json.dumps(c, ensure_ascii=False if fn == "comments.jsonl" else True) + "\n")
        os.replace(tmp, path)
        print(f"[fechas] {fn}: {filled} rellenadas, {missing} sin fecha disponible, {len(rows)} filas", file=sys.stderr)


if __name__ == "__main__":
    main()
