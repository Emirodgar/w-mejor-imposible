#!/usr/bin/env python3
"""Vigilancia de eventos de alto standing en España.

Uso (desde la carpeta mejor-imposible):
    python scripts/vigilancia/vigilancia.py semanal     # recoge noticias y escribe el informe (por defecto)
    python scripts/vigilancia/vigilancia.py opml        # genera vigilancia-feeds.opml
    python scripts/vigilancia/vigilancia.py terminos    # genera terminos-google-alerts.md
    python scripts/vigilancia/vigilancia.py opml terminos semanal   # varios a la vez

Solo biblioteca estándar (Python 3.9+). No modifica eventos.json ni cambios.json:
el informe es una propuesta y cada cambio se verifica en la fuente oficial antes
de pasarlo a las fichas. Lo ya visto se acumula en vistos.json y nunca se borra.
"""
import datetime as dt
import email.utils
import json
import os
import re
import sys
import unicodedata
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from xml.sax.saxutils import quoteattr

ROOT = Path(__file__).resolve().parents[2]
DIR = ROOT / "data" / "portal" / "vigilancia"
ALERTAS = DIR / "alertas.json"
VISTOS = DIR / "vistos.json"
INFORMES = DIR / "informes"
EVENTOS = ROOT / "data" / "portal" / "eventos.json"

DIAS_VENTANA = 10          # noticias más antiguas se ignoran
UA = "Mozilla/5.0 (compatible; vigilancia-portal/1.0)"
GNEWS = "https://news.google.com/rss/search?q={q}&hl=es&gl=ES&ceid=ES:es"

# Palabras que delatan un evento con fecha, aunque no esté en nuestras fichas
PALABRAS_EVENTO = re.compile(
    r"\b(festival|torneo|gran premio|gp|regata|copa|open|feria|salon|salón|gala|congreso|"
    r"semana|concurso|cartel|edici[oó]n|inaugura|apertura|abre sus puertas|entradas|"
    r"exposici[oó]n|masters|championship|boat show|fashion week|retiro|cena)\b", re.I)
# Palabras que sugieren un cambio relevante en un evento ya conocido
PALABRAS_CAMBIO = re.compile(
    r"(cancel|aplaz|suspend|nueva fecha|cambio de fecha|agotad|cartel|ponentes|"
    r"entradas|sede|regresa|vuelve|calendario 20)", re.I)


def norm(s):
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9 ]+", " ", s)


def cargar(path, defecto):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return defecto


def descargar(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/xml,text/xml,*/*"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.read()


def texto(el, nombre):
    for hijo in el:
        if hijo.tag.split("}")[-1] == nombre:
            return (hijo.text or "").strip(), hijo
    return "", None


def fecha(s):
    if not s:
        return None
    try:
        d = email.utils.parsedate_to_datetime(s)
    except (TypeError, ValueError):
        try:
            d = dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=dt.timezone.utc)
    return d


def parsear(xml_bytes):
    """Devuelve [{titulo, enlace, fecha, fuente, id}] de RSS o Atom."""
    raiz = ET.fromstring(xml_bytes)
    items = []
    for it in raiz.iter():
        if it.tag.split("}")[-1] not in ("item", "entry"):
            continue
        titulo, _ = texto(it, "title")
        enlace, el = texto(it, "link")
        if not enlace and el is not None:
            enlace = el.get("href", "")
        if not enlace:
            _, el = texto(it, "link")
            enlace = el.get("href", "") if el is not None else ""
        pub, _ = texto(it, "pubDate")
        if not pub:
            pub, _ = texto(it, "published") or ("", None)
        if not pub:
            pub, _ = texto(it, "updated")
        guid, _ = texto(it, "guid")
        fuente, _ = texto(it, "source")
        items.append({"titulo": re.sub(r"\s+", " ", titulo), "enlace": enlace,
                      "fecha": fecha(pub), "fuente": fuente, "id": guid or enlace})
    return items


GENERICAS = {"madrid", "barcelona", "week", "open", "festival", "gran", "premio", "copa", "internacional", "mutua", "espana",
             "alimentos", "show", "club", "trofeo", "campeonato", "semana", "feria", "sound", "world", "tour"}


def eventos_conocidos():
    datos = cargar(EVENTOS, {"eventos": []})
    out = []
    for e in datos.get("eventos", []):
        tokens = [t for t in norm(e["nombre"]).split() if len(t) > 3 and t not in ("mutua", "internacional", "espana")]
        out.append({"id": e["id"], "nombre": e["nombre"], "tokens": tokens, "norm": norm(e["nombre"]).strip()})
    return out


def coincide(titulo, ev):
    """El título habla de este evento: su nombre completo, o la mayoría de sus palabras con alguna distintiva."""
    t = norm(titulo)
    if ev["norm"] and ev["norm"] in t:
        return True
    toks = ev["tokens"]
    if len(toks) < 2:
        return False
    hit = [k for k in toks if k in t]
    return len(hit) / len(toks) >= 0.6 and any(k not in GENERICAS for k in hit)


def recoger(cfg):
    ahora = dt.datetime.now(dt.timezone.utc)
    corte = ahora - dt.timedelta(days=DIAS_VENTANA)
    recogidos, errores = [], []
    fuentes = []
    for a in cfg["alertas"]:
        q = a["consulta"] + " when:%dd" % DIAS_VENTANA
        fuentes.append((a["titulo"], a["categoria"], GNEWS.format(q=urllib.parse.quote(q)), True))
    for f in cfg.get("feeds_directos", []):
        fuentes.append((f["titulo"], f["categoria"], f["url"], False))
    # Feeds de Google Alerts propios (uno por línea) en un archivo local aparte
    # (en GitHub llegan por el secreto GOOGLE_ALERTS_FEEDS, con el mismo formato)
    ga = Path(__file__).with_name("google-alerts-feeds.txt")
    lineas = ga.read_text(encoding="utf-8").splitlines() if ga.exists() else []
    lineas += os.environ.get("GOOGLE_ALERTS_FEEDS", "").splitlines()
    vistos_ga = set()
    for linea in lineas:
        linea = linea.strip()
        if linea.startswith("http") and linea not in vistos_ga:
            vistos_ga.add(linea)
            fuentes.append(("Google Alerts #%d" % len(vistos_ga), "google-alerts", linea, False))
    for titulo, cat, url, es_news in fuentes:
        try:
            for it in parsear(descargar(url)):
                if it["fecha"] and it["fecha"] < corte:
                    continue
                it["alerta"], it["categoria"], it["directo"] = titulo, cat, not es_news
                recogidos.append(it)
        except Exception as exc:  # una fuente caída no debe tumbar el informe
            errores.append("%s: %s" % (titulo, exc))
    return recogidos, errores


def semanal():
    cfg = cargar(ALERTAS, None)
    if not cfg:
        sys.exit("Falta %s" % ALERTAS)
    vistos = cargar(VISTOS, {})
    conocidos = eventos_conocidos()
    recogidos, errores = recoger(cfg)

    nuevos, titulos_vistos = [], set()
    for it in recogidos:
        clave = it["id"] or it["enlace"]
        tn = norm(re.sub(r" - [^-]+$", "", it["titulo"]))[:90]
        if clave in vistos or tn in titulos_vistos:
            continue
        titulos_vistos.add(tn)
        nuevos.append(it)

    fichas, posibles, resto = {}, [], 0
    for it in nuevos:
        ev = next((e for e in conocidos if coincide(it["titulo"], e)), None)
        if ev:
            it["cambio"] = bool(PALABRAS_CAMBIO.search(it["titulo"]))
            fichas.setdefault(ev["id"], {"nombre": ev["nombre"], "items": []})["items"].append(it)
        elif PALABRAS_EVENTO.search(it["titulo"]):
            posibles.append(it)
        else:
            resto += 1

    hoy = dt.date.today().isoformat()
    L = ["# Vigilancia de eventos · %s" % hoy, "",
         "%d noticias nuevas de %d recogidas (ventana de %d días). %d sobre eventos de las fichas, "
         "%d posibles eventos nuevos, %d descartadas por ruido." % (
             len(nuevos), len(recogidos), DIAS_VENTANA, sum(len(v["items"]) for v in fichas.values()), len(posibles), resto),
         "", "> Propuesta, no verdad: cada dato se confirma en la fuente oficial antes de tocar `eventos.json` "
         "o `cambios.json` (confianza, fuente_url, y entrada nueva en cambios; nunca se borra lo anterior).", ""]

    def linea(it):
        f = it["fecha"].strftime("%d/%m") if it["fecha"] else "s/f"
        src = it["fuente"] or it["alerta"]
        return "- %s · [%s](%s) · _%s_" % (f, it["titulo"], it["enlace"], src)

    L.append("## 1. Eventos que ya tenemos en fichas")
    if fichas:
        for eid, v in sorted(fichas.items(), key=lambda kv: -sum(i["cambio"] for i in kv[1]["items"])):
            marca = " ⚠ posible cambio" if any(i["cambio"] for i in v["items"]) else ""
            L += ["", "### %s (`%s`)%s" % (v["nombre"], eid, marca)]
            L += [linea(i) + ("  **← revisar**" if i["cambio"] else "") for i in v["items"]]
    else:
        L += ["", "Sin novedades."]

    L += ["", "## 2. Posibles eventos nuevos (candidatos a ficha)"]
    por_cat = {}
    for it in posibles:
        por_cat.setdefault(it["categoria"], []).append(it)
    if por_cat:
        for cat in sorted(por_cat):
            L += ["", "### " + cat] + [linea(i) for i in por_cat[cat]]
    else:
        L += ["", "Nada nuevo."]

    if errores:
        L += ["", "## Fuentes que fallaron", ""] + ["- " + e for e in errores]

    INFORMES.mkdir(parents=True, exist_ok=True)
    out = INFORMES / ("%s.md" % hoy)
    out.write_text("\n".join(L) + "\n", encoding="utf-8")

    # Acumular lo visto (también el ruido, para no reprocesarlo) sin borrar nada
    for it in nuevos:
        vistos[it["id"] or it["enlace"]] = {"titulo": it["titulo"], "primera_vez": hoy}
    VISTOS.write_text(json.dumps(vistos, ensure_ascii=False, indent=1), encoding="utf-8")
    print("Informe:", out)
    print("Nuevas: %d · fichas: %d · posibles: %d · errores: %d" % (
        len(nuevos), sum(len(v["items"]) for v in fichas.values()), len(posibles), len(errores)))


def opml():
    cfg = cargar(ALERTAS, None)
    cats = {}
    for a in cfg["alertas"]:
        q = a["consulta"] + " when:7d"
        cats.setdefault(a["categoria"], []).append((a["titulo"], GNEWS.format(q=urllib.parse.quote(q)), "https://news.google.com/search?q=" + urllib.parse.quote(q)))
    directos = [(f["titulo"], f["url"], f["url"]) for f in cfg.get("feeds_directos", [])]
    L = ['<?xml version="1.0" encoding="UTF-8"?>', '<opml version="2.0">',
         "  <head><title>Vigilancia de eventos de alto standing en España</title></head>", "  <body>"]
    for cat in sorted(cats):
        L.append("    <outline text=%s title=%s>" % (quoteattr("Alertas · " + cat), quoteattr("Alertas · " + cat)))
        for t, x, h in cats[cat]:
            L.append("      <outline type=\"rss\" text=%s title=%s xmlUrl=%s htmlUrl=%s/>" % (quoteattr(t), quoteattr(t), quoteattr(x), quoteattr(h)))
        L.append("    </outline>")
    L.append("    <outline text=\"Fuentes directas\" title=\"Fuentes directas\">")
    for t, x, h in directos:
        L.append("      <outline type=\"rss\" text=%s title=%s xmlUrl=%s htmlUrl=%s/>" % (quoteattr(t), quoteattr(t), quoteattr(x), quoteattr(h)))
    L += ["    </outline>", "  </body>", "</opml>"]
    out = DIR / "vigilancia-feeds.opml"
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("OPML:", out)


def terminos():
    cfg = cargar(ALERTAS, None)
    L = ["# Alertas de Google a crear", "",
         "Crear en https://www.google.com/alerts con estos ajustes en **Mostrar opciones**:", "",
         "- Frecuencia: **Como máximo una vez al día** (o una vez a la semana en las de contexto)",
         "- Fuentes: **Automático**",
         "- Idioma: **español**", "- Región: **España**",
         "- Cuántas: **Solo los mejores resultados**",
         "- Enviar a: **fuente RSS** (si preferís correo, vuestra dirección)", "",
         "Copiar la consulta tal cual en el cuadro de búsqueda. Si Google la rechaza por larga, "
         "dividirla en dos alertas por el bloque entre paréntesis.", ""]
    cat_actual = None
    for a in sorted(cfg["alertas"], key=lambda x: (x["categoria"], x["id"])):
        if a["categoria"] != cat_actual:
            cat_actual = a["categoria"]
            L += ["## " + cat_actual.capitalize(), ""]
        L += ["**%s**" % a["titulo"], "", "```", a["consulta"], "```", ""]
    out = DIR / "terminos-google-alerts.md"
    out.write_text("\n".join(L), encoding="utf-8")
    print("Términos:", out, "(%d alertas)" % len(cfg["alertas"]))


if __name__ == "__main__":
    cmds = sys.argv[1:] or ["semanal"]
    for c in cmds:
        {"semanal": semanal, "opml": opml, "terminos": terminos}.get(c, lambda: sys.exit("Comando desconocido: " + c))()
