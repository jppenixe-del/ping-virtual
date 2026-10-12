#!/usr/bin/env python3
"""Backup diario (ob1, cron 04:30 UTC): junta tudo o que foi recolhido numa base SQLite unica e guarda um arquivo
comprimido de /root/ping-virtual-cache + data/ em /root/backups/ping-virtual (30 dias). Fica no ob1 (tem nomes de
milhares de jovens: nao vai para o GitHub)."""
import sqlite3, json, os, glob, tarfile, datetime, time
REPO = "/root/ping-virtual"; CACHE = "/root/ping-virtual-cache"; DEST = "/root/backups/ping-virtual"
os.makedirs(DEST, exist_ok=True)
hoje = datetime.date.today().isoformat()
db_path = f"{CACHE}/pv.db"; tmp = db_path + ".tmp"
if os.path.exists(tmp): os.remove(tmp)
db = sqlite3.connect(tmp)
db.executescript("""
CREATE TABLE joueurs (licence TEXT, nom TEXT, club TEXT, categorie TEXT, sexe TEXT, comite TEXT, points REAL, loisir INTEGER);
CREATE TABLE suivis (licence TEXT PRIMARY KEY, nom TEXT, club TEXT, categorie TEXT, mensuels REAL, classement REAL, maj TEXT);
CREATE TABLE matchs (licence TEXT, date TEXT, epreuve TEXT, adversaire TEXT, adv_licence TEXT, adv_points REAL,
                     victoire INTEGER, points REAL, coef REAL, valide INTEGER);
CREATE TABLE top_virtuel (categorie TEXT, licence TEXT, nom TEXT, club TEXT, mensuels REAL, valides REAL, attente REAL, virtuels REAL, maj TEXT);
CREATE TABLE info (cle TEXT, valeur TEXT);
""")
try:
    c = json.load(open(f"{CACHE}/classement_bretagne.json"))
    db.executemany("INSERT INTO joueurs VALUES (?,?,?,?,?,?,?,?)", [(j["lic"], j["nom"], j["club"], j["cat"], j["sexe"], j["dep"], j["pts"], 1 if j.get("loisir") else 0) for j in c["joueurs"]])
    db.execute("INSERT INTO info VALUES ('classement_maj', ?)", (c["maj"],))
except OSError: pass
for f in glob.glob(f"{REPO}/data/[0-9]*.json"):
    d = json.load(open(f))
    db.execute("INSERT OR REPLACE INTO suivis VALUES (?,?,?,?,?,?,?)", (d["licence"], d.get("nom"), d.get("club"), d.get("categorie"), d.get("mensuels"), d.get("classement"), d.get("maj")))
    db.executemany("INSERT INTO matchs VALUES (?,?,?,?,?,?,?,?,?,?)", [(d["licence"], m["date"], m["epreuve"], m.get("adv"), m.get("advLic"), m.get("advPts"),
        None if m.get("v") is None else int(m["v"]), m["pts"], m.get("coef"), int(m["officiel"])) for m in d["matchs"]])
try:
    t = json.load(open(f"{CACHE}/top_virtuel.json"))
    for cat, lista in t["categories"].items():
        db.executemany("INSERT INTO top_virtuel VALUES (?,?,?,?,?,?,?,?,?)", [(cat, j["lic"], j["nom"], j["club"], j["mensuels"], j["valides"], j["attente"], j["virtuels"], t["maj"]) for j in lista])
except OSError: pass
db.execute("INSERT INTO info VALUES ('backup', ?)", (datetime.datetime.now().isoformat(timespec="minutes"),))
db.commit(); db.close(); os.replace(tmp, db_path)
arq = f"{DEST}/ping-virtual-{hoje}.tgz"
with tarfile.open(arq, "w:gz") as tar:
    tar.add(CACHE, arcname="cache"); tar.add(f"{REPO}/data", arcname="data"); tar.add(f"{REPO}/licences.txt", arcname="licences.txt")
for f in sorted(glob.glob(f"{DEST}/ping-virtual-*.tgz"))[:-30]: os.remove(f)
n = sqlite3.connect(db_path).execute("SELECT (SELECT count(*) FROM joueurs), (SELECT count(*) FROM suivis), (SELECT count(*) FROM matchs)").fetchone()
print(hoje, "joueurs", n[0], "suivis", n[1], "matchs", n[2], "->", arq, os.path.getsize(arq)//1024, "Ko")
