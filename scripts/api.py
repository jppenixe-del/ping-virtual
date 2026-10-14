#!/usr/bin/env python3
"""Backoffice da Ping Virtual (corre no ob1, atras do Caddy em HTTPS).
  GET  /api/joueur/<lic>/apercu  -> verifica a licenca na Ping Pocket: nome, clube, categoria, pontos (para confirmar)
  POST /api/joueur/<lic>         -> confirmado: vai buscar os jogos, guarda data/<lic>.json, passa a seguir a licenca
                                    (licences.txt) e publica no GitHub em segundo plano; devolve os dados logo
Uma recolha de cada vez (a Ping Pocket nao e' martelada); verificacoes em cache 10 min."""
import json, os, re, sys, time, threading, subprocess
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
REPO = "/root/ping-virtual"
sys.path.insert(0, REPO + "/scripts")
os.chdir(REPO)
import pingpocket as pp
_get = pp.get
pp.get = lambda u, essais=2: _get(u, essais)       # pedidos interativos: no maximo 2 tentativas
_dorme = time.sleep
pp.time = type("T", (), {"sleep": staticmethod(lambda s: _dorme(min(s, 0.4)))})   # pedidos seguidos (um de cada vez), sem as pausas longas do cron

ORIGENS = {"https://jppenixe-del.github.io", "http://localhost:8767", "https://appassets.androidplatform.net"}
PC_BOLA = "http://10.0.0.2:8791"     # IA da bola na RTX do PC do Joao (pelo tunel WireGuard)
TRAVA = threading.Lock()
CACHE = {}
ADV = {}; EM_CURSO = set()
FICHAS_D = "/root/ping-virtual-cache/fiches"
CLAS_F = "/root/ping-virtual-cache/classement_bretagne.json"; CLAS = None
TOPV_F = "/root/ping-virtual-cache/top_virtuel.json"

def publica(lic):
    with TRAVA:
        # primeiro grava o commit, depois junta o que veio do GitHub (--autostash: nada local bloqueia a publicacao)
        subprocess.run(["bash", "-c", f"""cd {REPO} && (grep -qx {lic} licences.txt || echo {lic} >> licences.txt)
            && git add licences.txt data && (git diff --cached --quiet || git -c user.name=ping-virtual-bot
            -c user.email=ping-virtual-bot@users.noreply.github.com commit -qm 'Ajout de la licence {lic}')
            && git pull -q --rebase --autostash && git push -q"""], timeout=120)

def calcula_ficha(lic):
    try:
        with TRAVA:
            f = pp.fiche(lic)
            if not f.get("nom") or f.get("mensuels") is None: return {"erreur": "Licence introuvable"}
            ms = pp.completa(pp.matchs(lic), f.get("mensuels"), ADV)
    except BaseException: return {"erreur": "Ping Pocket ne répond pas"}
    mens = f.get("mensuels") or 0; val = sum(m["pts"] for m in ms if m["officiel"]); ref = mens + val; pend = 0.0
    for m in ms:
        if m["officiel"]: continue
        m["ptsVirt"] = pp.base(ref, m["advPts"], m["v"])*m.get("coef", 1) if m.get("advPts") is not None and m.get("v") is not None else m["pts"]
        pend += m["ptsVirt"]
    r = {"licence": lic, **f, "valides": val, "attente": pend, "virtuels": round(ref + pend, 2), "matchs": ms,
         "suivi": os.path.exists(f"data/{lic}.json")}
    os.makedirs(FICHAS_D, exist_ok=True)
    tmp = f"{FICHAS_D}/{lic}.json.tmp"; json.dump(r, open(tmp, "w"), ensure_ascii=False); os.replace(tmp, f"{FICHAS_D}/{lic}.json")
    return r

class H(BaseHTTPRequestHandler):
    def cors(self):
        o = self.headers.get("Origin", "")
        if o in ORIGENS: self.send_header("Access-Control-Allow-Origin", o); self.send_header("Vary", "Origin")
    def responde(self, code, obj):
        b = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code); self.cors()
        self.send_header("Content-Type", "application/json; charset=utf-8"); self.send_header("Content-Length", str(len(b)))
        self.end_headers(); self.wfile.write(b)
    def do_OPTIONS(self):
        self.send_response(204); self.cors()
        self.send_header("Access-Control-Allow-Methods", "GET, POST"); self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
    def do_GET(self):
        if self.path.startswith("/api/ia/ping"): return self.ia_ping()
        if self.path.startswith("/api/classement"): return self.classement()
        mf = re.fullmatch(r"/api/joueur/(\d{5,8})/fiche", self.path.split("?")[0])
        if mf: return self.ficha(mf.group(1))
        m = re.fullmatch(r"/api/joueur/(\d{5,8})/apercu", self.path.split("?")[0])
        if not m: return self.responde(404, {"erreur": "inconnu"})
        lic = m.group(1); c = CACHE.get(lic)
        if c and time.time() - c[0] < 600: return self.responde(200, c[1])
        try:
            with TRAVA: f = pp.fiche(lic)
        except BaseException: return self.responde(502, {"erreur": "Ping Pocket ne répond pas"})
        if not f.get("nom") or f.get("mensuels") is None: return self.responde(404, {"erreur": "Licence introuvable"})
        r = {"licence": lic, **f, "suivi": os.path.exists(f"data/{lic}.json")}
        CACHE[lic] = (time.time(), r); self.responde(200, r)
    def do_POST(self):
        if self.path.startswith("/api/ia/analisa"): return self.ia_analisa()
        mm = re.fullmatch(r"/api/maj/(\d{5,8})", self.path.split("?")[0])
        if mm: return self.maj(mm.group(1))
        m = re.fullmatch(r"/api/joueur/(\d{5,8})", self.path.split("?")[0])
        if not m: return self.responde(404, {"erreur": "inconnu"})
        lic = m.group(1)
        try:
            with TRAVA: pp.main([lic])
            d = json.load(open(f"data/{lic}.json"))
        except BaseException: return self.responde(502, {"erreur": "Ping Pocket ne répond pas"})
        threading.Thread(target=publica, args=(lic,), daemon=True).start()
        self.responde(200, d)
    def classement(self):
        """?cat=Benjamin (prefixo: Benjamin 1 + 2) &sexe=H|F &dep=35 -> lista ordenada pelos pontos mensais"""
        from urllib.parse import urlparse, parse_qs
        q = {k: v[0] for k, v in parse_qs(urlparse(self.path).query).items()}
        global CLAS
        try:
            mt = os.path.getmtime(CLAS_F)
            if CLAS is None or CLAS[0] != mt: CLAS = (mt, json.load(open(CLAS_F)))
        except OSError: return self.responde(503, {"erreur": "Classement en préparation, réessaie plus tard"})
        doc = CLAS[1]; cat = q.get("cat", "").lower(); sexe = q.get("sexe", ""); dep = q.get("dep", "")
        if q.get("mode") == "virtuel": return self.top_virtuel(cat, sexe, dep)
        loisir = q.get("loisir") == "1"
        js = [j for j in doc["joueurs"] if (not cat or j["cat"].lower().startswith(cat)) and (not sexe or j["sexe"] == sexe) and (not dep or j["dep"] == dep)
              and (loisir or not j.get("loisir"))]
        vistos, lista = set(), []
        for j in sorted(js, key=lambda j: -j["pts"]):
            if j["lic"] in vistos: continue          # um jogador pode aparecer em 2 clubes (mutacao)
            vistos.add(j["lic"]); lista.append(j)
        for i, j in enumerate(lista): j["rang"] = lista[i-1]["rang"] if i and lista[i-1]["pts"] == j["pts"] else i + 1   # ex aequo
        self.responde(200, {"maj": doc["maj"], "region": doc["region"], "comites": doc["comites"], "total": len(lista), "joueurs": lista})
    def top_virtuel(self, cat, sexe, dep):
        try: doc = json.load(open(TOPV_F))
        except OSError: return self.responde(503, {"erreur": "Top virtuel en préparation, réessaie plus tard"})
        fonte = next((v for k, v in doc["categories"].items() if cat.startswith(k.lower())), None)
        if fonte is None: return self.responde(404, {"erreur": "Top virtuel disponible seulement pour les Benjamins"})
        js = [dict(j) for j in fonte if (not cat or j["cat"].lower().startswith(cat)) and (not sexe or j["sexe"] == sexe) and (not dep or j["dep"] == dep)]
        js.sort(key=lambda j: -j["virtuels"])
        for i, j in enumerate(js): j["rang"] = i + 1; j["pts"] = j["virtuels"]
        self.responde(200, {"maj": doc["maj"], "total": len(js), "virtuel": True, "joueurs": js})
    def ficha(self, lic):
        """ficha de um jogador qualquer: dados + jogos + virtuais. Guardada em disco: fresca (< 12 h) devolve-se logo;
        mais velha devolve-se tambem logo (marcada) e refaz-se em segundo plano"""
        fx = f"{FICHAS_D}/{lic}.json"
        if os.path.exists(fx):
            idade = time.time() - os.path.getmtime(fx)
            r = json.load(open(fx)); r["idade_h"] = round(idade/3600, 1)
            if idade > 12*3600 and lic not in EM_CURSO:
                EM_CURSO.add(lic); threading.Thread(target=lambda: (calcula_ficha(lic), EM_CURSO.discard(lic)), daemon=True).start()
            return self.responde(200, r)
        r = calcula_ficha(lic)
        self.responde(200 if "erreur" not in r else (404 if r["erreur"] == "Licence introuvable" else 502), r)
    def maj(self, lic):
        """atualizacao imediata de um favorito (botao da app): dados frescos da Ping Pocket; nao repete se < 10 min"""
        f = f"data/{lic}.json"
        try:
            if os.path.exists(f) and time.time() - os.path.getmtime(f) < 600: return self.responde(200, json.load(open(f)))
            with TRAVA: pp.main([lic])
            d = json.load(open(f))
        except BaseException: return self.responde(502, {"erreur": "Ping Pocket ne répond pas, réessaie plus tard"})
        threading.Thread(target=publica, args=(lic,), daemon=True).start()
        self.responde(200, d)
    def ia_ping(self):
        import urllib.request
        try:
            with urllib.request.urlopen(PC_BOLA + "/ping", timeout=3) as r: return self.responde(200, json.load(r))
        except Exception: return self.responde(503, {"ok": False, "erreur": "PC éteint"})
    def ia_analisa(self):
        """o video vai inteiro para o PC; a RTX devolve as detecoes da bola em todas as imagens"""
        import urllib.request
        n = int(self.headers.get("Content-Length") or 0)
        if not n or n > 200 * 2**20: return self.responde(413, {"erreur": "vidéo trop grande (max 200 Mo)"})
        corpo = self.rfile.read(n)
        try:
            req = urllib.request.Request(PC_BOLA + "/analisa", data=corpo, headers={"Content-Type": "application/octet-stream"})
            with urllib.request.urlopen(req, timeout=240) as r: b = r.read()
        except Exception: return self.responde(503, {"erreur": "PC injoignable"})
        self.send_response(200); self.cors()
        self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(b)))
        self.end_headers(); self.wfile.write(b)
    def log_message(self, *a): pass

if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", 8790), H).serve_forever()
