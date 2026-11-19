#!/usr/bin/env python3
"""Vigilancia diaria: del RSS a las fichas de evento (crear si no existe, enriquecer si existe).

Uso (desde la raíz del repositorio):
    python scripts/vigilancia/pipeline.py              # recoge, extrae con Gemini, aplica, traduce y reconstruye
    python scripts/vigilancia/pipeline.py --dry        # no llama a Gemini ni escribe nada: solo lista candidatos
    python scripts/vigilancia/pipeline.py --sin-build  # actualiza los datos pero no regenera las páginas

Variables de entorno:
    GEMINI_API_KEY         obligatoria (salvo --dry)
    GEMINI_MODEL           por defecto gemini-flash-latest
    GOOGLE_ALERTS_FEEDS    feeds de Google Alerts, uno por línea (en local, el archivo google-alerts-feeds.txt)
    MAX_ARTICULOS          tope de artículos que se analizan por ejecución (por defecto 30)

Reglas que no se rompen:
  * Solo se escribe lo que dice el artículo; el modelo no completa con conocimiento propio.
  * Nunca se borra nada: las novedades se acumulan y los cambios de datos van al historial.
  * Una ficha creada existe siempre (publicar=false mientras sea de confianza baja, pero no se pierde).
  * La confianza "alta" solo se concede con una fuente oficial (fuentes_oficiales.json o la web del evento).
"""
import datetime as dt
import hashlib
import html.parser
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import vigilancia as V  # noqa: E402

ROOT = V.ROOT
DATA = ROOT / "data" / "portal"
EVENTOS = DATA / "eventos.json"
CAMBIOS = DATA / "cambios.json"
VISTOS = V.VISTOS
OFICIALES = V.DIR / "fuentes_oficiales.json"
INFORMES = V.INFORMES

MODEL = os.environ.get("GEMINI_MODEL", "gemini-flash-latest")
MAX_ARTICULOS = int(os.environ.get("MAX_ARTICULOS", "30"))
HOY = dt.date.today()
UA = "Mozilla/5.0 (compatible; mejorimposible-vigilancia/1.0; +https://mejorimposible.es)"

CATEGORIAS = ["deporte", "motor", "vela", "golf", "cultura", "gastronomia", "vino", "moda", "musica", "fiesta"]
DESTINOS = [d["slug"] for d in json.loads((DATA / "destinos.json").read_text(encoding="utf-8"))["destinos"]]


def llave(clave):
    """vistos.json guarda una huella corta de cada artículo, no su URL, para que el archivo no crezca sin control."""
    return hashlib.sha1(clave.encode("utf-8")).hexdigest()[:16]


def log(*a):
    print(*a, flush=True)


# ---------------------------------------------------------------- utilidades de texto y red
class _Texto(html.parser.HTMLParser):
    """Extrae título, fecha de publicación y párrafos de un HTML, sin dependencias."""
    SALTAR = {"script", "style", "nav", "footer", "header", "aside", "form", "noscript", "svg"}
    BLOQUES = {"p", "h1", "h2", "h3", "li", "time", "blockquote"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.profundidad_saltar = 0
        self.bloque = 0
        self.partes, self.meta = [], {}

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "meta":
            clave = a.get("property") or a.get("name")
            if clave in ("og:title", "og:description", "article:published_time", "description", "og:site_name"):
                self.meta.setdefault(clave, a.get("content", ""))
        if tag in self.SALTAR:
            self.profundidad_saltar += 1
        elif tag in self.BLOQUES:
            self.bloque += 1

    def handle_endtag(self, tag):
        if tag in self.SALTAR:
            self.profundidad_saltar = max(0, self.profundidad_saltar - 1)
        elif tag in self.BLOQUES:
            self.bloque = max(0, self.bloque - 1)
            self.partes.append("\n")

    def handle_data(self, data):
        if not self.profundidad_saltar and self.bloque:
            d = re.sub(r"\s+", " ", data).strip()
            if d:
                self.partes.append(d + " ")


def pagina(url, limite=7000):
    """Devuelve (url_final, titulo, fecha_publicacion, texto) o None si no se puede leer."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html,*/*", "Accept-Language": "es-ES,es;q=0.9"})
        with urllib.request.urlopen(req, timeout=25) as r:
            ctype = r.headers.get("Content-Type", "")
            if "html" not in ctype and "xml" not in ctype:
                return None
            raw = r.read(1_500_000)
            final = r.geturl()
            charset = r.headers.get_content_charset() or "utf-8"
    except Exception:
        return None
    try:
        doc = raw.decode(charset, errors="replace")
    except LookupError:
        doc = raw.decode("utf-8", errors="replace")
    p = _Texto()
    try:
        p.feed(doc)
    except Exception:
        pass
    texto = re.sub(r"\n\s*\n+", "\n", "".join(p.partes)).strip()
    texto = (p.meta.get("og:description", "") + "\n" + texto) if p.meta.get("og:description") and p.meta["og:description"] not in texto else texto
    if len(texto) < 200:
        return None
    return final, p.meta.get("og:title", ""), (p.meta.get("article:published_time") or "")[:10], texto[:limite]


def resolver_enlace(it):
    """Devuelve la URL real del artículo (desenvuelve los enlaces de Google Alerts) o None."""
    enlace = it["enlace"]
    host = urllib.parse.urlparse(enlace).netloc
    if host.endswith("google.com") or host.endswith("google.es"):
        if "/url?" in enlace:
            q = urllib.parse.parse_qs(urllib.parse.urlparse(enlace).query)
            real = (q.get("url") or q.get("q") or [""])[0]
            return real or None
        return None  # los enlaces de Google News no se resuelven: la vigilancia se apoya en Google Alerts y feeds directos
    return enlace


def limpiar_titulo(t):
    t = re.sub(r"<[^>]+>", "", t)
    t = t.replace("&amp;", "&").replace("&#39;", "'").replace("&quot;", '"')
    return re.sub(r"\s+", " ", t).strip()


def dominio(url):
    h = urllib.parse.urlparse(url).netloc.lower()
    return h[4:] if h.startswith("www.") else h


def slugify(s):
    s = V.norm(s).strip()
    s = re.sub(r"\s+", "-", s)
    return s[:60].strip("-")


def es_oficial(url, ev=None):
    d = dominio(url)
    lista = json.loads(OFICIALES.read_text(encoding="utf-8")).get("dominios", []) if OFICIALES.exists() else []
    if any(d == o or d.endswith("." + o) for o in lista):
        return True
    if ev and ev.get("fuente_url"):
        d0 = dominio(ev["fuente_url"])
        return d == d0 or d.endswith("." + d0)
    return False


# ---------------------------------------------------------------- Gemini
def gemini(prompt, schema, intentos=4):
    clave = os.environ.get("GEMINI_API_KEY")
    if not clave:
        raise SystemExit("Falta GEMINI_API_KEY")
    cuerpo = json.dumps({
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.1, "responseMimeType": "application/json", "responseSchema": schema},
    }).encode("utf-8")
    url = "https://generativelanguage.googleapis.com/v1beta/models/%s:generateContent" % urllib.parse.quote(MODEL)
    for n in range(intentos):
        try:
            req = urllib.request.Request(url, data=cuerpo, headers={"Content-Type": "application/json", "x-goog-api-key": clave})
            with urllib.request.urlopen(req, timeout=90) as r:
                data = json.loads(r.read().decode("utf-8"))
            texto = data["candidates"][0]["content"]["parts"][0]["text"]
            return json.loads(texto)
        except urllib.error.HTTPError as exc:
            if exc.code in (429, 500, 502, 503, 504) and n < intentos - 1:
                time.sleep(5 * (n + 1) ** 2)
                continue
            raise
        except (KeyError, IndexError, json.JSONDecodeError):
            if n < intentos - 1:
                time.sleep(3)
                continue
            raise
    raise RuntimeError("Gemini no respondió")


ESQUEMA_EXTRACCION = {
    "type": "OBJECT",
    "properties": {
        "accion": {"type": "STRING", "enum": ["ignorar", "actualizar", "crear"]},
        "motivo": {"type": "STRING"},
        "evento_id": {"type": "STRING"},
        "nombre": {"type": "STRING"},
        "categoria": {"type": "STRING", "enum": CATEGORIAS + [""]},
        "destino": {"type": "STRING", "enum": DESTINOS + ["ninguno"]},
        "lugar": {"type": "STRING"},
        "inicio": {"type": "STRING"},
        "fin": {"type": "STRING"},
        "mes_aprox": {"type": "STRING"},
        "que_es": {"type": "STRING"},
        "novedad": {"type": "STRING"},
        "confianza": {"type": "STRING", "enum": ["alta", "media", "baja"]},
    },
    "required": ["accion", "motivo", "evento_id", "nombre", "categoria", "destino", "lugar", "inicio", "fin", "mes_aprox", "que_es", "novedad", "confianza"],
}

REGLAS = """Eres el editor de mejorimposible.es, un repositorio de planes de lujo en España. Recibes UN artículo y decides si aporta información fiable sobre un evento de alto standing en España (torneos, regatas, salones, galas, congresos, festivales de primer nivel, exposiciones relevantes, grandes premios, aperturas con fecha, etc.).

Reglas:
1. Usa SOLO hechos que aparezcan en el texto del artículo. No completes con conocimiento propio ni deduzcas fechas. Si falta un dato, déjalo vacío ("").
2. Solo eventos en España, futuros o en curso (hoy es {hoy}). Ignora crónicas de eventos ya terminados, resultados deportivos, fichajes, política, sucesos, famosos y alfombras rojas, reventa de entradas, ofertas, empleo y actos locales sin proyección.
3. Si el artículo trata de un evento de la lista ACTUAL, devuelve accion "actualizar" con evento_id exacto. "novedad" debe contener solo lo que aún no sabemos (se muestra la ficha actual y sus últimas novedades). Si no aporta nada nuevo, devuelve "ignorar".
4. Si es un evento de alto standing que no está en la lista, devuelve "crear".
5. "novedad": una o dos frases en español neutro, sin adjetivos promocionales, con cifras, fechas y nombres tal cual aparecen. Máximo 280 caracteres. Vacío si ignoras.
6. Fechas en formato AAAA-MM-DD. Rellena inicio/fin solo si el texto da el día concreto y el año es inequívoco. Si solo hay mes, usa mes_aprox con formato AAAA-MM.
7. "confianza": alta = el texto da explícitamente nombre, fechas y lugar; media = falta alguno de ellos; baja = ambiguo o rumor.
8. "que_es": una frase que explique qué es el evento, solo con datos del texto. Vacío si actualizas.
9. "categoria" y "destino" solo cuando creas. Usa destino "ninguno" si el lugar no corresponde a ninguno de los destinos permitidos.
10. "lugar": el recinto o la ciudad tal como aparece en el texto."""


def resumen_eventos(eventos):
    return "\n".join("- %s | %s | %s | %s" % (e["id"], e["nombre"], ("%s a %s" % (e.get("inicio"), e.get("fin") or e.get("inicio"))) if e.get("inicio") else e.get("mes_aprox") or "?", e.get("lugar", "")) for e in eventos)


def prompt_articulo(eventos, art, ev_match):
    partes = [REGLAS.format(hoy=HOY.isoformat()), "\nEVENTOS ACTUALES (id | nombre | fechas | lugar):\n" + resumen_eventos(eventos)]
    if ev_match:
        ult = ev_match.get("novedades", [])[-6:]
        partes.append("\nFICHA ACTUAL DEL EVENTO RELACIONADO:\n" + json.dumps({k: ev_match.get(k) for k in ("id", "nombre", "inicio", "fin", "mes_aprox", "lugar", "que_es", "confianza")}, ensure_ascii=False)
                      + "\nÚltimas novedades ya registradas:\n" + ("\n".join("- %s: %s" % (n["fecha"], n["texto"]) for n in ult) or "(ninguna)"))
    partes.append("\nARTÍCULO\nURL: %s\nFuente: %s\nPublicado: %s\nTítulo: %s\nTexto:\n%s" % (art["url"], art["fuente"], art["fecha"], art["titulo"], art["texto"]))
    return "\n".join(partes)


# ---------------------------------------------------------------- validación y aplicación
def iso_ok(s, minimo=None, maximo=None):
    try:
        d = dt.date.fromisoformat(s)
    except (TypeError, ValueError):
        return None
    if minimo and d < minimo or maximo and d > maximo:
        return None
    return d


def mes_ok(s):
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", s or ""):
        return None
    y, m = int(s[:4]), int(s[5:])
    return s if HOY.year - 0 <= y <= HOY.year + 3 and (y, m) >= (HOY.year, HOY.month) else None


def nombre_en_texto(nombre, texto):
    t = V.norm(texto)
    toks = [k for k in V.norm(nombre).split() if len(k) > 3]
    return bool(toks) and sum(1 for k in toks if k in t) / len(toks) >= 0.6


def similar(a, b):
    A, B = set(V.norm(a).split()), set(V.norm(b).split())
    return bool(A and B) and len(A & B) / len(A | B) > 0.7


def aplicar(res, art, datos, informe):
    """Aplica una decisión de Gemini sobre eventos.json. Devuelve 'creado'/'actualizado'/None."""
    eventos = datos["eventos"]
    por_id = {e["id"]: e for e in eventos}
    accion = res["accion"]
    if accion == "ignorar":
        return None
    ev = por_id.get(res["evento_id"]) if accion == "actualizar" else None
    inicio = iso_ok(res["inicio"], HOY - dt.timedelta(days=1), HOY + dt.timedelta(days=900))
    fin = iso_ok(res["fin"], inicio or HOY - dt.timedelta(days=1), (inicio or HOY) + dt.timedelta(days=60)) if inicio else None
    mes = mes_ok(res["mes_aprox"])
    nombre = res["nombre"].strip()

    if accion == "actualizar" and not ev:
        informe.append("  ! actualizar con id inexistente (%s): descartado" % res["evento_id"])
        return None
    if accion == "actualizar" and inicio and ev.get("fin") and inicio > dt.date.fromisoformat(ev["fin"]) + dt.timedelta(days=60):
        # otra edición del mismo evento (el anterior ya pasó): ficha nueva, la antigua se conserva
        base, nombre = ev, res["nombre"].strip() or ev["nombre"]
        accion, ev = "crear", None
        res["categoria"] = res["categoria"] or base["categoria"]
        res["destino"] = res["destino"] if res["destino"] != "ninguno" else (base.get("destino") or "ninguno")
        res["lugar"] = res["lugar"] or base["lugar"]
        res["que_es"] = res["que_es"] or base["que_es"]

    oficial = es_oficial(art["url"], ev)
    if accion == "crear":
        if not (nombre and res["categoria"] in CATEGORIAS and (inicio or mes) and res["lugar"].strip() and res["que_es"].strip()):
            informe.append("  ! crear sin datos mínimos (%s): descartado" % nombre)
            return None
        if not nombre_en_texto(nombre, art["texto"] + " " + art["titulo"]):
            informe.append("  ! el nombre no aparece en el artículo (%s): descartado" % nombre)
            return None
        dup = next((e for e in eventos if V.coincide(nombre, {"norm": V.norm(e["nombre"]).strip(), "tokens": [t for t in V.norm(e["nombre"]).split() if len(t) > 3]}) and not
                    (inicio and e.get("fin") and inicio > dt.date.fromisoformat(e["fin"]) + dt.timedelta(days=60))), None)
        if dup:
            ev, accion = dup, "actualizar"
        else:
            slug = slugify(nombre)
            if (inicio or mes) and re.search(r"\b(19|20)\d\d\b", nombre) is None and slug in por_id:
                slug = "%s-%s" % (slug, (inicio.year if inicio else int(mes[:4])))
            if slug in por_id:
                informe.append("  ! id ya existe (%s): descartado" % slug)
                return None
            conf = "alta" if (oficial and res["confianza"] == "alta") else ("media" if res["confianza"] in ("alta", "media") else "baja")
            nuevo = {
                "id": slug, "nombre": nombre, "categoria": res["categoria"],
                "destino": None if res["destino"] == "ninguno" else res["destino"],
                "lugar": res["lugar"].strip(),
                "inicio": inicio.isoformat() if inicio else None, "fin": (fin or inicio).isoformat() if inicio else None,
                "mes_aprox": None if inicio else mes,
                "que_es": res["que_es"].strip(), "fuente_url": art["url"], "confianza": conf,
                "nota": "Alta automática desde %s el %s%s." % (art["fuente"] or dominio(art["url"]), HOY.isoformat(), "" if oficial else "; falta confirmarla en la web oficial"),
                "publicar": conf != "baja", "creado": HOY.isoformat(), "actualizado": HOY.isoformat(), "origen": "vigilancia",
                "novedades": [],
            }
            if res["novedad"].strip():
                nuevo["novedades"].append({"fecha": art["fecha"], "texto": res["novedad"].strip(), "fuente_url": art["url"], "fuente": art["fuente"] or dominio(art["url"])})
            eventos.append(nuevo)
            informe.append("  + CREADO %s (%s, %s)" % (slug, conf, nuevo["inicio"] or nuevo["mes_aprox"]))
            aplicar.ultimo = slug
            return "creado"

    # ---- actualizar
    cambios = False
    ev.setdefault("novedades", [])
    ev.setdefault("historial", [])
    novedad = res["novedad"].strip()
    nota_fechas = ""
    if inicio:
        nuevo_i, nuevo_f = inicio.isoformat(), (fin or inicio).isoformat()
        if not ev.get("inicio"):
            ev["inicio"], ev["fin"], ev["mes_aprox"] = nuevo_i, nuevo_f, None
            ev["historial"].append({"fecha": HOY.isoformat(), "campo": "fechas", "antes": ev.get("mes_aprox"), "despues": "%s a %s" % (nuevo_i, nuevo_f), "fuente_url": art["url"]})
            if ev["confianza"] == "baja":
                ev["confianza"] = "media"
            if oficial and res["confianza"] == "alta":
                ev["confianza"] = "alta"
            cambios = True
        elif (ev["inicio"], ev.get("fin") or ev["inicio"]) != (nuevo_i, nuevo_f):
            if oficial and res["confianza"] == "alta":
                ev["historial"].append({"fecha": HOY.isoformat(), "campo": "fechas", "antes": "%s a %s" % (ev["inicio"], ev.get("fin") or ev["inicio"]), "despues": "%s a %s" % (nuevo_i, nuevo_f), "fuente_url": art["url"]})
                ev["inicio"], ev["fin"] = nuevo_i, nuevo_f
                ev["confianza"] = "alta"
                nota_fechas = "Cambio de fechas confirmado por fuente oficial: %s a %s." % (nuevo_i, nuevo_f)
                cambios = True
            else:
                nota_fechas = "Otra fuente da fechas distintas (%s a %s); pendiente de confirmar en la web oficial." % (nuevo_i, nuevo_f)
    if not ev.get("lugar") and res["lugar"].strip():
        ev["lugar"] = res["lugar"].strip()
        cambios = True
    if ev.get("publicar") is False and ev["confianza"] != "baja":
        ev["publicar"] = True
        cambios = True
    textos = [t for t in (novedad, nota_fechas) if t]
    for texto in textos:
        if any(n.get("fuente_url") == art["url"] and similar(n["texto"], texto) or similar(n["texto"], texto) for n in ev["novedades"][-12:]):
            continue
        ev["novedades"].append({"fecha": art["fecha"], "texto": texto, "fuente_url": art["url"], "fuente": art["fuente"] or dominio(art["url"])})
        cambios = True
    if cambios:
        ev["actualizado"] = HOY.isoformat()
        informe.append("  ~ ACTUALIZADO %s: %s" % (ev["id"], "; ".join(textos)[:110] or "datos"))
        aplicar.ultimo = ev["id"]
        return "actualizado"
    informe.append("  = sin cambios en %s (nada nuevo)" % ev["id"])
    return None


def registrar_cambios(creados):
    if not creados:
        return
    datos = json.loads(CAMBIOS.read_text(encoding="utf-8"))
    hoy = HOY.isoformat()
    previo = next((c for c in datos["cambios"] if c.get("auto") and c["fecha"] == hoy), None)
    nombres = list(dict.fromkeys(((previo or {}).get("eventos") or []) + creados))
    titulo = "Calendario: %d evento%s nuevo%s" % (len(nombres), "" if len(nombres) == 1 else "s", "" if len(nombres) == 1 else "s")
    texto = "Entran en el calendario: %s. Salen de la vigilancia diaria de prensa y webs oficiales; los que aún no tienen fuente oficial figuran como «por confirmar»." % ", ".join(nombres)
    nuevo = {"fecha": hoy, "titulo": {"es": titulo}, "texto": {"es": texto}, "auto": True, "eventos": nombres}
    if previo:
        previo.update(nuevo)
    else:
        datos["cambios"].insert(0, nuevo)
    escribir_json(CAMBIOS, datos)


def escribir_json(path, datos, indent=2):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(datos, f, ensure_ascii=False, indent=indent)
        f.write("\n")


# ---------------------------------------------------------------- traducción de lo nuevo
IDIOMAS = {"en": "inglés", "fr": "francés", "de": "alemán", "pt": "portugués de Portugal", "it": "italiano"}


def traducir_pendientes():
    ok = True
    for lg, nombre in IDIOMAS.items():
        pend = DATA / "i18n" / ("_pendiente-%s.json" % lg)
        if not pend.exists():
            continue
        claves = list(json.loads(pend.read_text(encoding="utf-8")).keys())
        if not claves:
            continue
        destino = DATA / "i18n" / ("%s.json" % lg)
        tabla = json.loads(destino.read_text(encoding="utf-8"))
        for i in range(0, len(claves), 20):
            lote = claves[i:i + 20]
            prompt = ("Traduce del español al %s estos textos de un portal de planes de lujo en España. Conserva nombres propios, cifras, fechas y signos tal cual; "
                      "tono neutro e informativo; no añadas ni quites información. Devuelve un array JSON con las traducciones en el mismo orden.\n\n%s" % (nombre, json.dumps(lote, ensure_ascii=False)))
            try:
                out = gemini(prompt, {"type": "ARRAY", "items": {"type": "STRING"}})
            except (Exception, SystemExit) as exc:
                log("  ! traducción %s falló: %s" % (lg, exc))
                ok = False
                break
            if len(out) != len(lote) or any(not isinstance(x, str) or not x.strip() for x in out):
                log("  ! traducción %s con formato inesperado: se deja pendiente" % lg)
                ok = False
                continue
            tabla.update(dict(zip(lote, out)))
        escribir_json(destino, tabla, indent=1)
    return ok


# ---------------------------------------------------------------- build y limpieza de cambios solo de fecha
def correr(*args):
    r = subprocess.run([sys.executable, "-X", "utf8", *args], cwd=ROOT, env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    return r.returncode


def git(*args, check=False):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", check=check).stdout


RE_FECHAS = [re.compile(r'("dateModified"\s*:\s*")\d{4}-\d{2}-\d{2}'), re.compile(r"(<lastmod>)\d{4}-\d{2}-\d{2}")]


def sin_fechas(t):
    for r in RE_FECHAS:
        t = r.sub(r"\1X", t)
    return t.replace("\r\n", "\n")


def limpiar_cambios_de_fecha():
    """build.py pone la fecha de hoy en todas las páginas: se revierten las que no cambian en nada más."""
    modificados = [l[3:].strip().strip('"') for l in git("status", "--porcelain", "-uno").splitlines() if l[:2].strip() == "M"]
    revertidos = 0
    reales = set()
    for f in modificados:
        if not f.endswith((".html", ".xml")):
            continue
        antes = subprocess.run(["git", "show", "HEAD:" + f], cwd=ROOT, capture_output=True).stdout.decode("utf-8", errors="replace")
        ahora = (ROOT / f).read_text(encoding="utf-8", errors="replace")
        if sin_fechas(antes) == sin_fechas(ahora):
            git("checkout", "--", f)
            revertidos += 1
        else:
            reales.add(f)
    # sitemap: los URL que ya existían conservan su lastmod salvo que su página haya cambiado de verdad
    sm = ROOT / "sitemap-portal.xml"
    if sm.exists() and "sitemap-portal.xml" in reales:
        antes = subprocess.run(["git", "show", "HEAD:sitemap-portal.xml"], cwd=ROOT, capture_output=True).stdout.decode("utf-8")
        viejo = dict(re.findall(r"<loc>([^<]+)</loc>\s*<lastmod>([^<]+)</lastmod>", antes))

        def pagina_de(loc):
            ruta = urllib.parse.urlparse(loc).path.strip("/")
            return (ruta + "/index.html") if ruta else "index.html"
        ahora = sm.read_text(encoding="utf-8")

        def cambia(m):
            loc = m.group(1)
            if loc in viejo and pagina_de(loc) not in reales:
                return "<loc>%s</loc>\n    <lastmod>%s</lastmod>" % (loc, viejo[loc])
            return m.group(0)
        with open(sm, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(re.sub(r"<loc>([^<]+)</loc>\s*<lastmod>[^<]+</lastmod>", cambia, ahora))
    log("Build: %d páginas revertidas por cambiar solo la fecha; %d con cambios reales" % (revertidos, len(reales)))


def reconstruir():
    if correr("scripts/portal/build.py") != 0:
        raise SystemExit("build.py falló: no se sigue")
    if not traducir_pendientes():
        log("Hay traducciones pendientes (se mostrarán en español hasta la próxima ejecución).")
    else:
        if correr("scripts/portal/build.py") != 0:
            raise SystemExit("build.py falló tras traducir")
    for _ in range(6):  # en Windows falla a veces por bloqueos de archivo; es idempotente: se reintenta
        if correr("scripts/anade_opengraph.py") == 0:
            break
    else:
        raise SystemExit("anade_opengraph.py no terminó: no se publica sin Open Graph")
    escribir_llms()
    limpiar_cambios_de_fecha()


def escribir_llms():
    """llms.txt incluye las fichas de evento, con su resumen, para que los asistentes de IA las encuentren."""
    sys.path.insert(0, str(ROOT / "scripts"))
    import llms_y_feed
    with open(ROOT / "llms.txt", "w", encoding="utf-8", newline="\n") as f:
        f.write(llms_y_feed.llms(True))


# ---------------------------------------------------------------- enriquecimiento de la ficha (pensado para que lo citen los asistentes de IA)
DATOS_CLAVE = ["organizador", "edicion", "horario", "entradas", "web_oficial", "acceso"]
ENRIQUECER_MAX = int(os.environ.get("ENRIQUECER_MAX", "6"))
REFRESCO_DIAS = 30

ESQUEMA_ENRIQ = {
    "type": "OBJECT",
    "properties": {
        "resumen": {"type": "STRING"},
        "consiste": {"type": "ARRAY", "items": {"type": "STRING"}},
        "datos": {"type": "OBJECT", "properties": {k: {"type": "STRING"} for k in DATOS_CLAVE}, "required": DATOS_CLAVE},
        "faq": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {"p": {"type": "STRING"}, "r": {"type": "STRING"}}, "required": ["p", "r"]}},
        "inicio": {"type": "STRING"}, "fin": {"type": "STRING"}, "mes_aprox": {"type": "STRING"}, "lugar": {"type": "STRING"},
        "discrepancias": {"type": "STRING"},
    },
    "required": ["resumen", "consiste", "datos", "faq", "inicio", "fin", "mes_aprox", "lugar", "discrepancias"],
}

REGLAS_FICHA = """Eres el redactor de mejorimposible.es. Tu texto lo leerán personas y, sobre todo, lo citarán asistentes de IA (ChatGPT, Gemini, Perplexity, Google AI Overviews) cuando alguien pregunte por este evento. Escribe la ficha más completa y exacta posible a partir de las fuentes que recibes.

Reglas de contenido:
1. Usa SOLO hechos que aparezcan en las fuentes. No completes con conocimiento propio. Si un dato no aparece, déjalo vacío ("") o no lo menciones.
2. Si las fuentes discrepan (fechas, lugar, cifras), prefiere la fuente oficial, y anota la discrepancia en "discrepancias" (vacío si no hay).
3. No copies frases de las fuentes: reescribe con tus palabras. No uses adjetivos promocionales (imperdible, espectacular, único...).

Reglas de estilo (responder primero, párrafos cortos):
4. "resumen": 1 o 2 frases, máximo 280 caracteres, que respondan a qué es, cuándo y dónde. Empieza por el nombre completo del evento ("Madrid Fusión es...").
5. "consiste": entre 3 y 6 párrafos. Cada párrafo, una idea, máximo 2 frases y unas 35 palabras. Orden: qué es y para quién; qué ocurre o qué se ve; quién lo organiza o participa; contexto (edición, historia, novedades de esta edición); información práctica.
6. "datos": rellena solo lo que figure en las fuentes. "organizador": entidad organizadora. "edicion": número o año de edición. "horario": horarios de apertura o de las sesiones. "entradas": cómo y dónde se consiguen y precios, si constan. "web_oficial": URL oficial completa, solo si aparece literalmente en las fuentes. "acceso": cómo llegar (transporte, recinto).
7. "faq": entre 4 y 8 preguntas, formuladas como las haría una persona a un asistente ("¿Cuándo es...?", "¿Dónde se celebra...?", "¿Cuánto cuestan las entradas?", "¿Qué se puede ver...?", "¿Quién lo organiza?"). Solo preguntas que las fuentes permitan responder. Cada respuesta: 1 o 2 frases, autosuficiente (repite el nombre del evento) y con el dato concreto.
8. Fechas en AAAA-MM-DD en "inicio" y "fin" solo si las fuentes dan el día; si solo hay mes, "mes_aprox" AAAA-MM. Si no hay novedad respecto a la ficha actual, devuelve los mismos valores.
9. Todo en español neutro."""


def buscar_fuentes(ev, pool=(), maximo=6):
    """Reúne textos de varias fuentes sobre el evento: su web oficial, las fuentes ya citadas y prensa reciente."""
    urls, vistas = [], set()

    def anadir(u, etiqueta=""):
        if u and u not in vistas and len(urls) < 40:
            vistas.add(u)
            urls.append((u, etiqueta))
    anadir(ev.get("fuente_url"))
    for n in reversed(ev.get("novedades", [])[-8:]):
        anadir(n.get("fuente_url"), n.get("fuente", ""))
    for f in ev.get("fuentes", []):
        anadir(f.get("url"), f.get("nombre", ""))
    for it in pool:  # artículos de hoy (Google Alerts y feeds directos) cuyo título habla de este evento
        if V.coincide(it["titulo"], {"norm": V.norm(ev["nombre"]).strip(), "tokens": [t for t in V.norm(ev["nombre"]).split() if len(t) > 3]}):
            anadir(resolver_enlace(it), it["fuente"])
    textos, por_dominio = [], {}
    for u, etiqueta in urls:
        d = dominio(u)
        if por_dominio.get(d, 0) >= 2:
            continue
        pg = pagina(u, limite=5500)
        if not pg:
            continue
        url, titulo, fpub, texto = pg
        if not nombre_en_texto(ev["nombre"], titulo + " " + texto):
            continue
        por_dominio[d] = por_dominio.get(d, 0) + 1
        textos.append({"url": url, "nombre": etiqueta or dominio(url), "titulo": titulo, "fecha": fpub, "texto": texto, "oficial": es_oficial(url, ev)})
        if len(textos) >= maximo:
            break
    textos.sort(key=lambda t: not t["oficial"])  # primero las oficiales
    return textos


def prompt_ficha(ev, fuentes):
    actual = {k: ev.get(k) for k in ("nombre", "categoria", "inicio", "fin", "mes_aprox", "lugar", "que_es", "resumen", "consiste", "datos", "faq")}
    bloques = "\n\n".join("FUENTE %d%s\nURL: %s\nPublicada: %s\nTítulo: %s\n%s" % (i + 1, " (OFICIAL)" if f["oficial"] else "", f["url"], f["fecha"] or "?", f["titulo"], f["texto"]) for i, f in enumerate(fuentes))
    return "%s\n\nHoy es %s.\n\nFICHA ACTUAL (puedes ampliarla y corregirla):\n%s\n\n%s" % (REGLAS_FICHA, HOY.isoformat(), json.dumps(actual, ensure_ascii=False), bloques)


def url_valida(u, fuentes):
    """La web oficial debe ser una URL http(s) que figure en alguna fuente: así el modelo no puede inventarla."""
    if not re.match(r"https?://[^\s]+$", u or ""):
        return False
    return any(u.rstrip("/") in (f["texto"] + " " + f["url"]) or dominio(u) == dominio(f["url"]) for f in fuentes)


def fusionar_ficha(ev, res, fuentes, informe):
    """Suma lo nuevo a la ficha sin borrar nada: lo reemplazado va al historial."""
    hoy = HOY.isoformat()
    ev.setdefault("historial", [])
    cambios = False
    oficial = any(f["oficial"] for f in fuentes)
    r = res["resumen"].strip()
    if 60 <= len(r) <= 400 and r != ev.get("resumen"):
        if ev.get("resumen"):
            ev["historial"].append({"fecha": hoy, "campo": "resumen", "antes": ev["resumen"], "despues": r})
        ev["resumen"] = r
        cambios = True
    cur = ev.setdefault("consiste", [])
    for p in res["consiste"][:6]:
        p = re.sub(r"\s+", " ", p).strip()
        if 40 <= len(p) <= 420 and len(cur) < 10 and not any(similar(p, c) for c in cur):
            cur.append(p)
            cambios = True
    d = ev.setdefault("datos", {})
    for k in DATOS_CLAVE:
        v = (res["datos"].get(k) or "").strip()
        if not v or len(v) > 400 or (k == "web_oficial" and not url_valida(v, fuentes)):
            continue
        if not d.get(k):
            d[k] = v
            cambios = True
        elif d[k] != v and oficial and k != "web_oficial":
            ev["historial"].append({"fecha": hoy, "campo": "datos." + k, "antes": d[k], "despues": v})
            d[k] = v
            cambios = True
    faq = ev.setdefault("faq", [])
    for qa in res["faq"][:8]:
        p, r_ = qa["p"].strip(), qa["r"].strip()
        if len(p) > 8 and 20 <= len(r_) <= 500 and len(faq) < 12 and not any(similar(p, x["p"]) for x in faq):
            faq.append({"p": p, "r": r_})
            cambios = True
    if not ev.get("lugar") and res["lugar"].strip():
        ev["lugar"] = res["lugar"].strip()
        cambios = True
    if not ev.get("inicio"):
        i = iso_ok(res["inicio"], HOY - dt.timedelta(days=1), HOY + dt.timedelta(days=900))
        if i:
            f = iso_ok(res["fin"], i, i + dt.timedelta(days=60))
            ev["inicio"], ev["fin"], ev["mes_aprox"] = i.isoformat(), (f or i).isoformat(), None
            cambios = True
    fu = ev.setdefault("fuentes", [])
    for f in fuentes:
        if all(x["url"] != f["url"] for x in fu):
            fu.append({"url": f["url"], "nombre": f["nombre"]})
            cambios = True
    disc = res["discrepancias"].strip()
    if disc and not any(similar(n["texto"], disc) for n in ev.get("novedades", [])[-12:]):
        ev.setdefault("novedades", []).append({"fecha": hoy, "texto": "Las fuentes no coinciden en un dato: " + disc, "fuente_url": fuentes[0]["url"], "fuente": fuentes[0]["nombre"]})
        cambios = True
    ev["enriquecido"] = hoy
    if cambios:
        ev["actualizado"] = hoy
    return cambios


def cola_enriquecimiento(datos, tocados):
    """Primero lo que ha cambiado hoy; luego las fichas sin completar o con más de 30 días, las más próximas en el tiempo antes."""
    hoy = HOY.isoformat()
    por_id = {e["id"]: e for e in datos["eventos"]}
    cola = [por_id[i] for i in tocados if i in por_id]
    resto = [e for e in datos["eventos"] if e.get("publicar") and e not in cola and (e.get("fin") or e.get("inicio") or "9999") >= hoy
             and (not e.get("enriquecido") or (HOY - dt.date.fromisoformat(e["enriquecido"])).days >= REFRESCO_DIAS)]
    resto.sort(key=lambda e: (bool(e.get("enriquecido")), e.get("inicio") or (e.get("mes_aprox") or "9999") + "-01"))
    return (cola + resto)[:ENRIQUECER_MAX]


def enriquecer(datos, tocados, informe, pool=()):
    hechos = []
    for ev in cola_enriquecimiento(datos, tocados):
        fuentes = buscar_fuentes(ev, pool)
        if not fuentes:
            informe.append("- Ficha %s: sin fuentes legibles; se reintentará" % ev["id"])
            continue
        try:
            res = gemini(prompt_ficha(ev, fuentes), ESQUEMA_ENRIQ)
        except Exception as exc:
            informe.append("- Ficha %s: error de Gemini (%s)" % (ev["id"], exc))
            continue
        if fusionar_ficha(ev, res, fuentes, informe):
            hechos.append(ev["id"])
        informe.append("- Ficha %s enriquecida con %d fuentes (%d oficiales); %d párrafos, %d preguntas" % (ev["id"], len(fuentes), sum(f["oficial"] for f in fuentes), len(ev.get("consiste", [])), len(ev.get("faq", []))))
    return hechos


# ---------------------------------------------------------------- triaje: Gemini decide qué titulares interesan
ESQUEMA_TRIAJE = {"type": "ARRAY", "items": {"type": "INTEGER"}}
LOTE_TRIAJE = 120

REGLAS_TRIAJE = """Eres el editor de mejorimposible.es, un repositorio de planes de lujo y eventos de alto standing en España. Recibes una lista numerada de titulares de prensa y decides cuáles merece la pena leer entero para crear o enriquecer la ficha de un evento.

Interesan: eventos en España, futuros o en curso (hoy es {hoy}), de alto standing o gran proyección: torneos de golf, regatas y salones náuticos, grandes premios, ferias y salones, congresos de alta cocina, galas Michelin, festivales de primer nivel, exposiciones relevantes, aperturas con fecha, galas benéficas de alto nivel, eventos de marcas de lujo, cambios de fecha, cancelaciones, carteles y venta de entradas de estos eventos.
No interesan: crónicas y resultados de eventos ya terminados, fichajes, política, sucesos, famosos y alfombras rojas, concursos o actos locales sin proyección, ofertas, empleo, reventa, publirreportajes sin evento y noticias de fuera de España.
Ante la duda razonable, incluye el titular: es mejor leer uno de más que perder un evento.

Devuelve un array JSON con los números de los titulares que interesan (vacío si ninguno).

TITULARES:
{lista}"""


def triaje(cand):
    """Devuelve los índices de cand que Gemini considera de interés. Si falla, se usa el filtro por palabras clave."""
    elegidos = set()
    for ini in range(0, len(cand), LOTE_TRIAJE):
        lote = cand[ini:ini + LOTE_TRIAJE]
        lista = "\n".join("%d. %s (%s)" % (ini + k, c["titulo"][:160], c["fuente"] or c["alerta"]) for k, c in enumerate(lote))
        out = gemini(REGLAS_TRIAJE.format(hoy=HOY.isoformat(), lista=lista), ESQUEMA_TRIAJE)
        elegidos |= {i for i in out if isinstance(i, int) and ini <= i < ini + len(lote)}
    return elegidos


# ---------------------------------------------------------------- flujo principal
def main():
    dry = "--dry" in sys.argv
    sin_build = "--sin-build" in sys.argv
    cfg = V.cargar(V.ALERTAS, None)
    datos = json.loads(EVENTOS.read_text(encoding="utf-8"))
    vistos = V.cargar(VISTOS, {})
    conocidos = V.eventos_conocidos()
    recogidos, errores = V.recoger(cfg)
    n_gn = sum(1 for it in recogidos if urllib.parse.urlparse(it["enlace"]).netloc.startswith("news.google"))
    recogidos = [it for it in recogidos if not urllib.parse.urlparse(it["enlace"]).netloc.startswith("news.google")]
    log("Se omiten %d resultados de Google News (sin enlace al artículo); se usan Google Alerts y feeds directos" % n_gn)

    # candidatos nuevos, sin duplicados por título
    cand, titulos = [], set()
    for it in recogidos:
        clave = it["id"] or it["enlace"]
        tn = V.norm(re.sub(r" - [^-]+$", "", limpiar_titulo(it["titulo"])))[:90]
        if clave in vistos or llave(clave) in vistos or tn in titulos:
            continue
        titulos.add(tn)
        it["titulo"] = limpiar_titulo(it["titulo"])
        it["match"] = next((e for e in conocidos if V.coincide(it["titulo"], e)), None)
        it["evento"] = bool(V.PALABRAS_EVENTO.search(it["titulo"]))
        cand.append(it)
    # Gemini decide qué titulares interesan (los que hablan de un evento ya conocido pasan siempre).
    # Si el triaje falla o estamos en --dry, se usa el filtro por palabras clave de antes.
    if dry:
        interesan = {i for i, c in enumerate(cand) if c["match"] or c["evento"]}
    else:
        try:
            interesan = triaje([c for c in cand if not c["match"]])
            sin_match = [c for c in cand if not c["match"]]
            elegidos_ids = {id(sin_match[i]) for i in interesan}
            interesan = {i for i, c in enumerate(cand) if c["match"] or id(c) in elegidos_ids}
            log("Triaje con Gemini: %d de %d titulares interesan" % (len(interesan), len(cand)))
        except (Exception, SystemExit) as exc:
            log("Triaje con Gemini no disponible (%s): se usa el filtro por palabras clave" % exc)
            interesan = {i for i, c in enumerate(cand) if c["match"] or c["evento"]}
    ruido = [c for i, c in enumerate(cand) if i not in interesan]
    utiles = [c for i, c in enumerate(cand) if i in interesan]
    utiles.sort(key=lambda c: (0 if c["match"] else 1, 0 if c["directo"] and c["categoria"] == "google-alerts" else 1))
    lote = utiles[:MAX_ARTICULOS]
    log("Recogidas %d · nuevas %d · útiles %d · ruido %d · se analizan %d · fuentes caídas %d" % (len(recogidos), len(cand), len(utiles), len(ruido), len(lote), len(errores)))
    if dry:
        for c in lote:
            log(" -", c["titulo"][:110], "->", c["match"]["id"] if c["match"] else "(nuevo?)")
        return

    informe = ["# Vigilancia diaria %s" % HOY.isoformat(), "", "Analizados %d artículos (%d descartados por ruido)." % (len(lote), len(ruido)), ""]
    creados, actualizados, tocados = [], [], set()
    for it in lote:
        clave = it["id"] or it["enlace"]
        real = resolver_enlace(it)
        pg = pagina(real) if real else None
        informe.append("- [%s](%s)" % (it["titulo"][:100], real or it["enlace"]))
        if not pg:
            informe.append("  · no se pudo leer el artículo: se reintentará mañana")
            continue  # sin texto no se verifica nada y no se marca como visto
        url, titulo, fpub, texto = pg
        fecha = fpub if iso_ok(fpub) else (it["fecha"].date().isoformat() if it["fecha"] else HOY.isoformat())
        art = {"url": url, "titulo": titulo or it["titulo"], "fecha": fecha, "texto": texto, "fuente": it["fuente"] or it["alerta"].replace("Google Alerts", "").strip() or dominio(url)}
        ev_match = None
        if it["match"]:
            ev_match = next((e for e in datos["eventos"] if e["id"] == it["match"]["id"]), None)
        try:
            res = gemini(prompt_articulo(datos["eventos"], art, ev_match), ESQUEMA_EXTRACCION)
        except Exception as exc:
            informe.append("  ! error de Gemini: %s" % exc)
            continue
        estado = aplicar(res, art, datos, informe)
        if estado:
            tocados.add(aplicar.ultimo)
        if estado == "creado":
            creados.append(datos["eventos"][-1]["nombre"])
        elif estado == "actualizado":
            actualizados.append(res["evento_id"] or "?")
        elif res["accion"] == "ignorar":
            informe.append("  · ignorado: %s" % res["motivo"][:110])
        vistos[llave(clave)] = {"f": HOY.isoformat(), "t": it["titulo"][:90], "a": res["accion"], "r": estado or "nada"}
    for c in ruido:
        vistos[llave(c["id"] or c["enlace"])] = {"f": HOY.isoformat(), "a": "ruido"}

    enriquecidos = [] if "--sin-enriquecer" in sys.argv else enriquecer(datos, tocados, informe, [c for c in cand if c["enlace"]])
    if creados or actualizados or enriquecidos:
        datos["actualizado"] = HOY.isoformat()
        escribir_json(EVENTOS, datos)
        registrar_cambios(creados)
    # caché de deduplicación: el ruido y lo ignorado se olvida a los 60 días (ya no vuelve a salir en los feeds); lo que creó o enriqueció fichas se conserva
    corte = (HOY - dt.timedelta(days=60)).isoformat()
    vistos = {k: v for k, v in vistos.items() if not (isinstance(v, dict) and v.get("a") in ("ruido", "ignorar") and v.get("f", "9") < corte)}
    escribir_json(VISTOS, vistos, indent=0)
    informe += ["", "Resumen: %d creados, %d actualizados, %d fichas enriquecidas." % (len(creados), len(actualizados), len(enriquecidos))]
    if errores:
        informe += ["", "Fuentes caídas:"] + ["- " + e for e in errores]
    INFORMES.mkdir(parents=True, exist_ok=True)
    (INFORMES / ("%s-pipeline.md" % HOY.isoformat())).write_text("\n".join(informe) + "\n", encoding="utf-8")
    log("\n".join(informe[-12:]))
    if not sin_build:  # siempre: así también se traducen las cadenas pendientes de cualquier ficha
        reconstruir()
    # salida para el workflow
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as f:
            f.write("creados=%d\nactualizados=%d\nenriquecidos=%d\n" % (len(creados), len(actualizados), len(enriquecidos)))


if __name__ == "__main__":
    main()
