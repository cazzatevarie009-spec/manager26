#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MANAGER26 - Sincronizzazione ROSE REALI (con diagnostica).

Cosa fa: controlla le ROSE ATTUALI reali di ogni squadra (endpoint /players/squads)
e scrive  data/market_updates.json  con { player, to } per OGNI giocatore.
Il gioco, leggendolo, sposta ogni giocatore nella sua squadra reale -> corregge da
solo le differenze (compresi i vecchi prestiti "finti"). E' idempotente.

CHIAVE (fondamentale):
- Deve essere la chiave del sito DIRETTO  https://dashboard.api-football.com/  (api-sports.io).
- NON la chiave di RapidAPI (con RapidAPI host/headers sono diversi e l'API risponde
  'Missing application key', come nel tuo log).
- Mettila nel secret GitHub  APISPORTS_KEY.

Il log stampa /status (piano) ed errori: se vedi ancora 'Missing application key',
la chiave e' quella sbagliata.
"""
import os, json, time, datetime, urllib.request, urllib.parse, urllib.error

KEY = os.environ.get("APISPORTS_KEY", "").strip()
BASE = "https://v3.football.api-sports.io"
today = datetime.date.today()
SEASON = int(os.environ.get("SEASON", str(today.year if today.month >= 7 else today.year - 1)))
LEAGUES = [int(x) for x in os.environ.get("LEAGUES", "135,39,140,78,61").split(",") if x.strip()]
MAX_CALLS = int(os.environ.get("MAX_CALLS", "95"))  # piano free = 100/giorno

# nomi squadra API -> nomi usati nel database del gioco (aggiungine se non combaciano)
TEAM_MAP = {
  "Paris Saint Germain": "Paris SG", "Manchester United": "Manchester Utd",
  "Internazionale": "Inter", "Atletico Madrid": "Atl\u00e9tico Madrid",
  "Barcelona": "FC Barcelona", "Bayern M\u00fcnchen": "Bayern Munich",
}

_calls = 0
def api(path, **params):
    global _calls
    if _calls >= MAX_CALLS:
        return {}, 0
    _calls += 1
    url = BASE + path + (("?" + urllib.parse.urlencode(params)) if params else "")
    req = urllib.request.Request(url, headers={"x-apisports-key": KEY, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8")), r.status
    except urllib.error.HTTPError as e:
        b = ""
        try: b = e.read().decode("utf-8")[:300]
        except Exception: pass
        return {"_http": e.code, "_body": b}, e.code
    except Exception as e:
        return {"_err": str(e)}, 0

def tmap(n):
    n = (n or "").strip()
    return TEAM_MAP.get(n, n)

def write(moves):
    os.makedirs("data", exist_ok=True)
    with open("data/market_updates.json", "w", encoding="utf-8") as f:
        json.dump(moves, f, ensure_ascii=False, indent=1)

def main():
    print("=== MANAGER26 sync rose reali ===")
    print("Data:", today, "| Stagione:", SEASON, "| Leghe:", LEAGUES)
    print("APISPORTS_KEY presente:", bool(KEY), "| lunghezza:", len(KEY))
    if not KEY:
        print("ERRORE: manca APISPORTS_KEY. Scrivo file vuoto."); write([]); return

    st, code = api("/status")
    print("/status HTTP:", code, "| risposta:", json.dumps(st.get("response", st), ensure_ascii=False)[:500])
    if st.get("errors"):
        print("ERRORE /status:", st["errors"])
        print(">>> Se dice 'Missing application key' o 'token': la chiave e' sbagliata (probabilmente RapidAPI).")
        print(">>> Prendi la chiave da https://dashboard.api-football.com/ (My Access) e rimettila nel secret.")
        write([]); return

    def teams(season):
        out = []
        for lg in LEAGUES:
            if _calls >= MAX_CALLS: break
            d, c = api("/teams", league=lg, season=season)
            r = d.get("response") or []
            if d.get("errors"): print("  /teams", lg, "errors:", d["errors"])
            print("  Lega", lg, "stagione", season, "-> squadre:", len(r))
            for t in r:
                tm = t.get("team") or {}
                if tm.get("id"): out.append((tm["id"], tm.get("name")))
        return out

    tlist = teams(SEASON)
    if not tlist and _calls < MAX_CALLS:
        print("Nessuna squadra per", SEASON, "- riprovo", SEASON - 1)
        tlist = teams(SEASON - 1)

    moves = []; seen = set(); nteams = 0
    for tid, tname in tlist:
        if _calls >= MAX_CALLS:
            print("  (limite richieste giornaliere raggiunto: sincronizzate", nteams, "squadre)"); break
        d, c = api("/players/squads", team=tid)
        r = d.get("response") or []
        if not r: continue
        nteams += 1
        squad = (r[0].get("players") or [])
        club = tmap(tname)
        for pl in squad:
            nm = (pl.get("name") or "").strip()
            if not nm: continue
            key = nm + "->" + club
            if key in seen: continue
            seen.add(key)
            moves.append({"player": nm, "to": club})
        time.sleep(0.12)

    print("RIEPILOGO -> squadre sincronizzate:", nteams, "| giocatori:", len(moves), "| chiamate API:", _calls)
    if not moves:
        print(">>> Vuoto: controlla il messaggio /status qui sopra (quasi sempre e' la chiave).")
    write(moves)
    print("Scritto data/market_updates.json con", len(moves), "voci.")

if __name__ == "__main__":
    main()
