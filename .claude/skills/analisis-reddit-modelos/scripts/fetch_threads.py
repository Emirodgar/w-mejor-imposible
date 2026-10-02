#!/usr/bin/env python3
"""Descubre hilos de Reddit sobre Porsche y vuelca sus comentarios en lotes para clasificar.

Reddit bloquea curl (403/429) y su navegador integrado, asi que se usa Arctic Shift
(archivo publico de Reddit, sin API key): https://arctic-shift.photon-reddit.com
Solo libreria estandar (Python 3.9+).

Uso:
  python fetch_threads.py --days 180 --max-threads 40            # descubre + descarga + lotes
  python fetch_threads.py --urls threads-seed.json               # anade hilos curados a mano
Salida en .claude/state/analisis-reddit/:
  threads.json     metadatos de cada hilo elegido
  comments.jsonl   comentarios filtrados (id, thread, autor hash, score, parent, body)
  batches/NNN.json lotes de ~120 comentarios para que Claude los clasifique
"""
import argparse, hashlib, json, os, re, sys, time, urllib.parse, urllib.request

API = "https://arctic-shift.photon-reddit.com/api"
UA = "Mozilla/5.0 (compatible; mejorimposible-bot/1.0)"
HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
ROOT = os.path.abspath(os.path.join(SKILL, "..", "..", ".."))
STATE = os.path.join(ROOT, ".claude", "state", "analisis-reddit")
BOTS = {"automoderator", "[deleted]", "deleted", "porschebot", "repostsleuthbot", "savevideo", "sneakpeekbot"}


def get(path, params, retries=4):
    url = API + path + "?" + urllib.parse.urlencode(params)
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=90) as r:
                d = json.loads(r.read().decode("utf-8"))
            if d.get("error"):
                raise RuntimeError(d["error"])
            return d.get("data") or []
        except Exception as e:  # 422 "Timeout" del servidor, 429, red...
            wait = 3 * (i + 1)
            print(f"  ! {path} {e} -> reintento en {wait}s", file=sys.stderr)
            time.sleep(wait)
    return None


def load_models():
    with open(os.path.join(SKILL, "models.json"), encoding="utf-8") as f:
        return json.load(f)


def discover(cfg, days, min_comments, pages_per_sub, title_regex=None):
    fam = re.compile("|".join(p for ps in cfg["family_patterns"].values() for p in ps), re.I)
    opin = re.compile(title_regex or cfg["opinion_title_regex"], re.I)
    since = int(time.time()) - days * 86400
    found = {}
    subs = [(s, True) for s in cfg["subreddits"]["por_modelo"]] + [(s, False) for s in cfg["subreddits"]["generales"]]
    for sub, model_sub in subs:
        before, n_pages = None, 0
        print(f"[descubrir] r/{sub}", file=sys.stderr)
        while n_pages < pages_per_sub:
            p = {"subreddit": sub, "after": since, "limit": 100, "sort": "desc"}
            if before:
                p["before"] = before
            posts = get("/posts/search", p)
            n_pages += 1
            if not posts:
                break
            for x in posts:
                text = (x.get("title") or "") + " " + (x.get("selftext") or "")
                if x.get("num_comments", 0) < min_comments:
                    continue
                if not model_sub and not fam.search(x.get("title") or ""):
                    continue  # en subreddits generales el modelo debe aparecer en el titulo (evita hilos de otras marcas)
                if not opin.search(x.get("title") or "") and not (model_sub and len(x.get("selftext") or "") > 300):
                    continue
                found[x["id"]] = {"id": x["id"], "sub": x["subreddit"], "title": x["title"],
                                  "num_comments": x["num_comments"], "score": x.get("score", 0),
                                  "created": x["created_utc"], "url": "https://www.reddit.com" + x.get("permalink", f"/comments/{x['id']}/")}
            before = posts[-1]["created_utc"]
            if len(posts) < 100:
                break
            time.sleep(1.2)
    return found


def pick_balanced(cand, cfg, limit):
    """Reparte el cupo entre familias (911, 718, Macan...) para que una sola no copie el ranking.
    Los hilos curados a mano entran siempre primero; dentro de cada familia, los mas comentados."""
    fams = {f: re.compile("|".join(ps), re.I) for f, ps in cfg["family_patterns"].items()}
    buckets = {}
    curated = [t for t in cand if t.get("curated")]
    for t in sorted((t for t in cand if not t.get("curated")), key=lambda t: -t["num_comments"]):
        fam = next((f for f, rx in fams.items() if rx.search(t["title"] or "")), None)
        if fam is None:  # hilo de subreddit de modelo sin pista en el titulo
            fam = next((f for f, rx in fams.items() if rx.search(t["sub"] or "")), "otros")
        buckets.setdefault(fam, []).append(t)
    out = curated[:limit]
    while len(out) < limit and any(buckets.values()):
        for fam in list(buckets):
            if buckets[fam] and len(out) < limit:
                out.append(buckets[fam].pop(0))
    return out


def flatten(nodes, out):
    for n in nodes or []:
        c = n.get("data", n)
        out.append(c)
        r = c.get("replies")
        if isinstance(r, dict):
            flatten(r.get("data", {}).get("children", []), out)
        elif isinstance(r, list):
            flatten(r, out)


def thread_comments(tid):
    tree = get("/comments/tree", {"link_id": tid, "limit": 2000})
    out = []
    flatten(tree, out)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=180)
    ap.add_argument("--min-comments", type=int, default=15)
    ap.add_argument("--max-threads", type=int, default=40)
    ap.add_argument("--pages-per-sub", type=int, default=40, help="paginas de 100 posts por subreddit")
    ap.add_argument("--urls", help="JSON con lista de URLs/ids de hilos curados a mano")
    ap.add_argument("--batch-size", type=int, default=150)
    ap.add_argument("--min-chars", type=int, default=80, help="descarta comentarios mas cortos (casi nunca aportan experiencia)")
    ap.add_argument("--title-regex", help="sustituye opinion_title_regex de models.json (p. ej. solo hilos de problemas)")
    ap.add_argument("--skip-discovery", action="store_true")
    a = ap.parse_args()

    os.makedirs(os.path.join(STATE, "batches"), exist_ok=True)
    cfg = load_models()
    seen_path = os.path.join(STATE, "threads-done.json")
    done = set(json.load(open(seen_path, encoding="utf-8"))) if os.path.exists(seen_path) else set()

    found = {} if a.skip_discovery else discover(cfg, a.days, a.min_comments, a.pages_per_sub, a.title_regex)
    if a.urls:
        for u in json.load(open(a.urls, encoding="utf-8")):
            m = re.search(r"comments/([a-z0-9]+)", u) or re.match(r"^([a-z0-9]+)$", u)
            if m:
                tid = m.group(1)
                found.setdefault(tid, {"id": tid, "sub": "", "title": "", "num_comments": 999, "score": 0, "created": 0,
                                       "url": f"https://www.reddit.com/comments/{tid}/", "curated": True})
    cand = [t for t in found.values() if t["id"] not in done]
    chosen = pick_balanced(cand, cfg, a.max_threads)
    print(f"[hilos] {len(found)} candidatos, {len(cand)} nuevos, se procesan {len(chosen)}", file=sys.stderr)

    all_comments = []
    for i, t in enumerate(chosen, 1):
        cs = thread_comments(t["id"])
        if cs is None:
            continue
        by_id = {c["id"]: c for c in cs}
        kept = 0
        for c in cs:
            au = (c.get("author") or "").lower()
            body = (c.get("body") or "").strip()
            if au in BOTS or au.endswith("bot") or body in ("[deleted]", "[removed]") or len(body) < a.min_chars:
                continue
            pid = (c.get("parent_id") or "")
            parent = by_id.get(pid.split("_")[-1]) if pid.startswith("t1_") else None
            all_comments.append({
                "id": c["id"], "thread": t["id"], "user": hashlib.sha1(au.encode()).hexdigest()[:10],
                "score": c.get("score", 0), "body": body[:900],
                "parent": ((parent or {}).get("body") or t["title"])[:160].replace("\n", " "),
            })
            kept += 1
        t["comments_kept"] = kept
        done.add(t["id"])
        print(f"  [{i}/{len(chosen)}] {t['title'][:60]!r}: {kept} comentarios", file=sys.stderr)
        time.sleep(1.2)

    # persistencia (las carpetas se crean aqui, justo antes de escribir)
    os.makedirs(os.path.join(STATE, "batches"), exist_ok=True)
    tpath = os.path.join(STATE, "threads.json")
    old = json.load(open(tpath, encoding="utf-8")) if os.path.exists(tpath) else []
    ids = {t["id"] for t in old}
    json.dump(old + [t for t in chosen if t["id"] not in ids], open(tpath, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    with open(os.path.join(STATE, "comments.jsonl"), "a", encoding="utf-8") as f:
        for c in all_comments:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    with open(os.path.join(STATE, "comments-index.jsonl"), "a", encoding="utf-8") as f:  # version publica, sin texto
        for c in all_comments:
            f.write(json.dumps({k: c[k] for k in ("id", "thread", "user", "score")}) + "\n")
    json.dump(sorted(done), open(seen_path, "w", encoding="utf-8"))

    # lotes pendientes de clasificar (los que aun no tienen resultado)
    classified, first_no = set(), 1
    cdir = os.path.join(STATE, "classified")
    if os.path.isdir(cdir):
        nums = [int(fn[:-5]) for fn in os.listdir(cdir) if fn[:-5].isdigit()]
        first_no = max(nums, default=0) + 1  # sigue la numeracion para no pisar lotes ya clasificados
        for fn in os.listdir(cdir):
            for e in json.load(open(os.path.join(cdir, fn), encoding="utf-8")):
                classified.add(e["id"])
    titles = {t["id"]: t["title"] for t in old + chosen}
    bdir = os.path.join(STATE, "batches")
    # Un comentario "revisado" es todo el que iba en un lote ya clasificado, haya dado entrada o no.
    # Sin esto, los descartados (la mayoria) volverian a encolarse en cada ejecucion.
    rpath = os.path.join(STATE, "reviewed.json")
    reviewed = set(json.load(open(rpath, encoding="utf-8"))) if os.path.exists(rpath) else set()
    for fn in os.listdir(bdir):
        if os.path.exists(os.path.join(cdir, fn)):
            reviewed.update(e["id"] for e in json.load(open(os.path.join(bdir, fn), encoding="utf-8")))
    json.dump(sorted(reviewed), open(rpath, "w"))
    pend = [c for c in (json.loads(l) for l in open(os.path.join(STATE, "comments.jsonl"), encoding="utf-8"))
            if c["id"] not in classified and c["id"] not in reviewed]
    for fn in os.listdir(bdir):
        os.remove(os.path.join(bdir, fn))
    for k in range(0, len(pend), a.batch_size):
        batch = [{"id": c["id"], "hilo": titles.get(c["thread"], ""), "responde_a": c["parent"], "texto": c["body"]}
                 for c in pend[k:k + a.batch_size]]
        json.dump(batch, open(os.path.join(bdir, f"{first_no + k // a.batch_size:03d}.json"), "w", encoding="utf-8"), ensure_ascii=False)
    print(f"[lotes] {len(pend)} comentarios pendientes en {(len(pend) + a.batch_size - 1) // a.batch_size} lotes -> {bdir}", file=sys.stderr)


if __name__ == "__main__":
    main()
