#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MANAGER26 - Sync rose reali da TRANSFERMARKT (via transfermarkt-api, con diagnostica).

Usa un'istanza di 'transfermarkt-api' (progetto open-source che fa scraping di
Transfermarkt). Di default punta a  http://127.0.0.1:8000  perche' il workflow
GitHub avvia l'API dentro l'Action (nessun server da gestire).
Puoi anche puntare a un'istanza tua (fly.io/render) impostando la variabile TM_API.

Produce  data/market_updates.json  con { player, to } per ogni giocatore delle
rose reali: il gioco sposta ognuno nella sua squadra reale (corregge le differenze).
"""
import os, json, time, urllib.request, urllib.parse, urllib.error, datetime

TM_API = os.environ.get("TM_API", "http://127.0.0.1:8000").rstrip("/")
today = datetime.date.today()
SEASON = os.environ.get("SEASON", str(today.year if today.month >= 7 else today.year - 1))
# competizioni Transfermarkt: IT1=SerieA GB1=Premier ES1=LaLiga L1=Bundesliga FR1=Ligue1
COMPS = [x.strip() for x in os.environ.get("COMPS", "IT1,GB1,ES1,L1,FR1").split(",") if x.strip()]

# nomi squadra Transfermarkt -> nomi del gioco (aggiungine se qualcuno non combacia)
TEAM_MAP = {
  "Juventus FC": "Juventus", "Inter Milan": "Inter", "AC Milan": "AC Milan",
  "SSC Napoli": "Napoli", "AS Roma": "Roma", "Atalanta BC": "Atalanta",
  "FC Bayern Munich": "Bayern Munich", "Bayer 04 Leverkusen": "Bayer Leverkusen",
  "Real Madrid": "Real Madrid", "FC Barcelona": "FC Barcelona",
  "Atletico de Madrid": "Atl\u00e9tico Madrid", "Atl\u00e9tico de Madrid": "Atl\u00e9tico Madrid",
  "Manchester City": "Manchester City", "Manchester United": "Manchester Utd",
  "Paris Saint-Germain": "Paris SG", "Tottenham Hotspur": "Tottenham",
  "Wolverhampton Wanderers": "Wolves", "Newcastle United": "Newcastle",
}

def clean_team(n):
    n = (n or "").strip()
    if n in TEAM_MAP: return TEAM_MAP[n]
    for suf in [" FC", " CF", " AC", " SC"]:
        if n.endswith(suf): n = n[:-len(suf)].strip()
    return n

def api(path):
    url = TM_API + path
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "manager26-updater"})
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            return json.loads(r.read().decode("utf-8")), r.status
    except urllib.error.HTTPError as e:
        b = ""
        try: b = e.read().decode("utf-8")[:200]
        except Exception: pass
        return {"_http": e.code, "_body": b}, e.code
    except Exception as e:
        return {"_err": str(e)}, 0

def write(moves):
    os.makedirs("data", exist_ok=True)
    with open("data/market_updates.json", "w", encoding="utf-8") as f:
        json.dump(moves, f, ensure_ascii=False, indent=1)

def main():
    print("=== MANAGER26 sync Transfermarkt ===")
    print("TM_API:", TM_API, "| Stagione:", SEASON, "| Competizioni:", COMPS)
    # ping
    _, code = api("/")
    print("Ping API ("+TM_API+") HTTP:", code)

    moves = []; seen = set(); nclubs = 0
    for comp in COMPS:
        d, c = api("/competitions/" + comp + "/clubs?season_id=" + SEASON)
        clubs = (d.get("clubs") if isinstance(d, dict) else None) or []
        if not clubs:
            print("  Competizione", comp, "-> 0 club. Risposta:", json.dumps(d, ensure_ascii=False)[:200])
            continue
        print("  Competizione", comp, "-> club:", len(clubs))
        for cl in clubs:
            cid = cl.get("id"); cname = clean_team(cl.get("name"))
            if not cid: continue
            pd, pc = api("/clubs/" + str(cid) + "/players?season_id=" + SEASON)
            players = (pd.get("players") if isinstance(pd, dict) else None) or []
            if not players:
                continue
            nclubs += 1
            for pl in players:
                nm = (pl.get("name") or "").strip()
                if not nm: continue
                k = nm + "->" + cname
                if k in seen: continue
                seen.add(k)
                moves.append({"player": nm, "to": cname})
            time.sleep(0.2)
    print("RIEPILOGO -> club sincronizzati:", nclubs, "| giocatori:", len(moves))
    if not moves:
        print(">>> Vuoto. Controlla il ping API sopra: se HTTP != 200, l'API Transfermarkt non e' partita")
        print(">>> (guarda lo step 'Avvia transfermarkt-api' nel log) o Transfermarkt ha bloccato le richieste.")
    write(moves)
    print("Scritto data/market_updates.json con", len(moves), "voci.")

if __name__ == "__main__":
    main()
