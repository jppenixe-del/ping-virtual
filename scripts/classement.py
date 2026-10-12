#!/usr/bin/env python3
"""Ranking regional por categoria (corre no ob1, 1 vez por semana): percorre os clubes dos comites da Bretanha na
Ping Pocket (um pedido de cada vez, com pausa) e guarda, para cada jogador com pontos, a categoria, o sexo e os pontos
mensais. O ficheiro fica no ob1 (nao vai para o GitHub publico: sao nomes de milhares de jovens); a app pede-o ao
backoffice (scripts/api.py, /api/classement)."""
import json, re, sys, time, html, datetime, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pingpocket as pp

COMITES = {"22": "Côtes-d'Armor", "29": "Finistère", "35": "Ille-et-Vilaine", "56": "Morbihan"}
SAIDA = "/root/ping-virtual-cache/classement_bretagne.json"

def clubes(ct):
    t = pp.get(f"https://www.pingpocket.fr/app/fftt/comites/{ct}/clubs")
    vistos = {}
    for cid, nome in re.findall(r'href="/app/fftt/clubs/(\d+)\?CLUB_NAME=([^"]*)"', t):
        vistos[cid] = html.unescape(nome).replace("+", " ")
    return vistos

def jogadores(cid, clube, ct):
    t = pp.get(f"https://www.pingpocket.fr/app/fftt/clubs/{cid}/licencies?SORT=CATEGORY")
    out, cat = [], ""
    for b in re.split(r"<li ", t)[1:]:
        if b.startswith('class="sep"'):
            sp = re.findall(r"<span>([^<]*)</span>", b); cat = pp.conserta(html.unescape(sp[0]).strip()) if sp else cat; continue
        lic = re.search(r'href="/app/fftt/licencies/(\d+)', b); nome = re.search(r'<div class="labels">\s*<p>([^<]*)</p>', b)
        pts = re.search(r'<small class="counter[^"]*">([^<]*)</small>', b)
        if not (lic and nome and pts): continue
        bruto = pts.group(1).strip()
        if re.fullmatch(r"N\d+", bruto):        # numerotes (top nacional): a lista mostra "N25", nao os pontos
            try: p = pp.fiche(lic.group(1)).get("mensuels"); time.sleep(1.5)
            except SystemExit: p = None
            if p is None: continue
            bruto = str(p)
        p = pp.num(bruto); loisir = p is None and bruto == "L"
        if p is None and not loisir: continue
        out.append({"lic": lic.group(1), "nom": pp.conserta(html.unescape(nome.group(1)).strip()), "cat": cat,
                    "sexe": "F" if "fa-female" in b else "H", "pts": 500.0 if loisir else p, "club": clube, "dep": ct,
                    **({"loisir": True} if loisir else {})})   # licence loisir: 500 pontos fixos, nao joga competicao
    return out

def main():
    todos, n = [], 0
    for ct in COMITES:
        cs = clubes(ct); time.sleep(2)
        for cid, nome in cs.items():
            try: todos += jogadores(cid, nome, ct)
            except SystemExit as e: print("clube falhou", cid, e, file=sys.stderr)
            n += 1; time.sleep(2)
        print(ct, len(cs), "clubes", len(todos), "jogadores", flush=True)
    os.makedirs(os.path.dirname(SAIDA), exist_ok=True)
    doc = {"maj": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%MZ"), "region": "Bretagne",
           "comites": COMITES, "clubs": n, "joueurs": todos}
    tmp = SAIDA + ".tmp"; json.dump(doc, open(tmp, "w"), ensure_ascii=False); os.replace(tmp, SAIDA)

if __name__ == "__main__":
    main()
