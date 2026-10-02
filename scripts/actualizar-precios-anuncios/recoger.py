#!/usr/bin/env python3
"""Recoge el precio de los anuncios de Porsche usados en España (AutoScout24.es) y añade
un punto mensual por serie a porsche/precios-anuncios.json.

Reglas:
- Acumulativo: solo se AÑADE el punto del mes en curso. Un mes ya presente no se toca
  (relanzar el script el mismo mes no cambia nada) y se comprueba antes de escribir que
  el histórico previo queda idéntico.
- Cada ejecución guarda además la instantánea anuncio a anuncio en snapshots/AAAA-MM.jsonl.gz,
  para poder recalcular métricas distintas (media, percentiles...) sin volver a recoger.
- Una serie que falla (bloqueo, HTML cambiado, 0 anuncios) se salta sin escribir nada;
  si fallan todas, sale con error.

Uso: python recoger.py [--solo ID ...] [--dry-run] [--mes AAAA-MM]
"""
import argparse
import copy
import datetime
import gzip
import json
import re
import statistics
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent.parent
DATOS = RAIZ / "porsche" / "precios-anuncios.json"
SNAPSHOTS = AQUI / "snapshots"
BASE = "https://www.autoscout24.es/lst/porsche/{modelo}"
FUENTE = "AutoScout24.es"
UA = "Mozilla/5.0 (compatible; MejorImposibleBot/1.0; +https://mejorimposible.es)"
PAUSA = 3.0          # segundos entre peticiones
MAX_PAGINAS = 20     # tope de paginación de AutoScout24
NEXT_DATA = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)


def descargar(url, intentos=3):
    ultimo = None
    for i in range(intentos):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "es-ES,es;q=0.9"})
            with urllib.request.urlopen(req, timeout=40) as r:
                return r.read().decode("utf-8", errors="replace")
        except (urllib.error.URLError, TimeoutError) as e:
            ultimo = e
            time.sleep(PAUSA * (i + 2))
    raise RuntimeError(f"no se pudo descargar {url}: {ultimo}")


def pagina(serie, n):
    qs = (f"cy=E&atype=C&ustate=U&damaged_listing=exclude&sort=standard&desc=0"
          f"&fregfrom={serie['desde']}&fregto={serie['hasta']}&page={n}")
    if serie.get("extra"):  # filtro adicional opcional de AutoScout24, p. ej. fuel=E (eléctricos)
        qs += "&" + serie["extra"]
    html = descargar(BASE.format(modelo=serie["modelo"]) + "?" + qs)
    m = NEXT_DATA.search(html)
    if not m:
        raise RuntimeError("sin __NEXT_DATA__ (¿bloqueo o cambio de plantilla?)")
    pp = json.loads(m.group(1))["props"]["pageProps"]
    return pp.get("listings") or [], int(pp.get("numberOfPages") or 1)


def kilometros(txt):
    d = re.sub(r"\D", "", txt or "")
    return int(d) if d else None


def recoger_serie(serie):
    vistos, filas = set(), []
    n, total = 1, 1
    while n <= min(total, MAX_PAGINAS):
        listings, total = pagina(serie, n)
        for l in listings:
            precio = (l.get("price") or {}).get("priceRaw")
            veh = l.get("vehicle") or {}
            if (not precio or l["id"] in vistos or veh.get("make") != "Porsche"
                    or (l.get("location") or {}).get("countryCode") != "ES"
                    or (l.get("price") or {}).get("isConditionalPrice")):
                continue
            vistos.add(l["id"])
            filas.append({
                "id": l["id"], "precio": int(precio), "km": kilometros(veh.get("mileageInKm")),
                "matric": (l.get("tracking") or {}).get("firstRegistration"),
                "modelo": veh.get("model"), "version": veh.get("modelVersionInput"),
                "vendedor": (l.get("seller") or {}).get("type"),
            })
        n += 1
        if n <= min(total, MAX_PAGINAS):
            time.sleep(PAUSA)
    return filas


def punto(mes, filas):
    p = sorted(f["precio"] for f in filas)
    q = statistics.quantiles(p, n=4) if len(p) >= 4 else [p[0], statistics.median(p), p[-1]]
    return {"mes": mes, "precio": round(statistics.median(p)), "n": len(p),
            "media": round(statistics.mean(p)), "p25": round(q[0]), "p75": round(q[2])}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--solo", nargs="*", help="ids de serie a recoger")
    ap.add_argument("--dry-run", action="store_true", help="no escribe nada")
    ap.add_argument("--mes", help="AAAA-MM (por defecto, el mes actual UTC)")
    a = ap.parse_args()
    mes = a.mes or datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m")

    series = json.loads((AQUI / "series.json").read_text(encoding="utf-8"))
    if a.solo:
        series = [s for s in series if s["id"] in a.solo]
    datos = json.loads(DATOS.read_text(encoding="utf-8"))
    previo = copy.deepcopy(datos)
    datos.setdefault("series", {})

    nuevos, snapshot, fallos = 0, [], []
    for s in series:
        if any(p["mes"] == mes for p in datos["series"].get(s["id"], [])):
            print(f"{s['id']}: {mes} ya existe, se respeta")
            continue
        try:
            filas = recoger_serie(s)
        except Exception as e:  # noqa: BLE001 - una serie rota no debe tumbar las demás
            fallos.append(s["id"])
            print(f"{s['id']}: ERROR {e}", file=sys.stderr)
            continue
        if not filas:
            fallos.append(s["id"])
            print(f"{s['id']}: 0 anuncios, se salta", file=sys.stderr)
            continue
        pt = punto(mes, filas)
        datos["series"].setdefault(s["id"], []).append(pt)
        snapshot += [{"serie": s["id"], "mes": mes, **f} for f in filas]
        nuevos += 1
        print(f"{s['id']}: {pt['n']} anuncios, mediana {pt['precio']} €")
        time.sleep(PAUSA)

    if fallos and nuevos == 0 and len(fallos) == len(series):
        sys.exit("Todas las series han fallado: no se escribe nada.")
    if not nuevos:
        print("Sin puntos nuevos.")
        return

    # Garantía de acumulación: lo que había antes sigue exactamente igual.
    for sid, pts in previo.get("series", {}).items():
        assert datos["series"][sid][:len(pts)] == pts, f"histórico alterado en {sid}"

    datos["actualizado"] = datetime.date.today().isoformat()
    datos["fuente"] = FUENTE
    if a.dry_run:
        print(f"[dry-run] {nuevos} puntos nuevos, {len(snapshot)} anuncios; no se escribe.")
        return
    DATOS.write_text(json.dumps(datos, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    SNAPSHOTS.mkdir(exist_ok=True)
    destino = SNAPSHOTS / f"{mes}.jsonl.gz"
    modo = "ab" if destino.exists() else "wb"   # si se relanza el mes, se añade, no se pisa
    with gzip.open(destino, modo) as f:
        for fila in snapshot:
            f.write((json.dumps(fila, ensure_ascii=False) + "\n").encode("utf-8"))
    print(f"Escritos {nuevos} puntos y {len(snapshot)} anuncios en {destino.name}.")
    if fallos:
        print("Series sin dato este mes: " + ", ".join(fallos), file=sys.stderr)


if __name__ == "__main__":
    main()
