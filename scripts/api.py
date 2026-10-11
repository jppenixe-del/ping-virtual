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
_dorme = time.sleep
pp.time = type("T", (), {"sleep": staticmethod(lambda s: _dorme(min(s, 0.4)))})   # pedidos seguidos (um de cada vez), sem as pausas longas do cron

ORIGENS = {"https://jppenixe-del.github.io", "http://localhost:8767"}
TRAVA = threading.Lock()
CACHE = {}

def publica(lic):
    with TRAVA:
        subprocess.run(["bash", "-c", f"""cd {REPO} && git pull -q --rebase && (grep -qx {lic} licences.txt || echo {lic} >> licences.txt)
            && git add licences.txt data && (git diff --cached --quiet || git -c user.name=ping-virtual-bot
            -c user.email=ping-virtual-bot@users.noreply.github.com commit -qm 'Ajout de la licence {lic}') && git push -q"""], timeout=120)

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
        m = re.fullmatch(r"/api/joueur/(\d{5,8})", self.path.split("?")[0])
        if not m: return self.responde(404, {"erreur": "inconnu"})
        lic = m.group(1)
        try:
            with TRAVA: pp.main([lic])
            d = json.load(open(f"data/{lic}.json"))
        except BaseException: return self.responde(502, {"erreur": "Ping Pocket ne répond pas"})
        threading.Thread(target=publica, args=(lic,), daemon=True).start()
        self.responde(200, d)
    def log_message(self, *a): pass

if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", 8790), H).serve_forever()
