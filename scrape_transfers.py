#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MANAGER26 - Sync rose reali da TRANSFERMARKT (via transfermarkt-api).

IMPORTANTE: Transfermarkt BLOCCA gli IP di GitHub (403). Percio' NON facciamo lo
scraping da GitHub: usiamo un'istanza gia' ospitata di 'transfermarkt-api' che
scarica dai propri IP. Default: l'istanza pubblica di prova.
  TM_API = https://transfermarkt-api.fly.dev  (default)
Se la pubblica e' lenta/limitata, ospitane una tua (fly.io/render) e metti il suo
indirizzo nella variabile TM_API dentro update-transfers.yml.

Produce data/market_updates.json = [{player, to}, ...] con le rose reali attuali.
"""
import os, json, time, urllib.request, urllib.parse, urllib.error, datetime

TM_API = os.environ.get("TM_API", "https://transfermarkt-api.fly.dev").rstrip("/")
SEASON = os.environ.get("SEASON", "").strip()   # vuoto = stagione corrente (consigliato)
COMPS = [x.strip() for x in os.environ.get("COMPS", "IT1,GB1,ES1,L1,FR1").split(",") if x.strip()]
SLEEP = float(os.environ.get("SLEEP", "1.2"))    # pausa tra le richieste (istanza pubblica limitata)

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

def api(path, tries=4):
    url = TM_API + path
    for attempt in range(tries):
        req = urllib.request.Request(url, headers={
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
        })
        try:
            with urllib.request.urlopen(req, timeout=45) as r:
                return json.loads(r.read().decode("utf-8")), r.status
        except urllib.error.HTTPError as e:
            b = ""
            try: b = e.read().decode("utf-8")[:160]
            except Exception: pass
            if e.code in (429, 500, 502, 503, 504) and attempt < tries - 1:
                wait = 3 * (attempt + 1)
                print("    ...", e.code, "riprovo tra", wait, "s")
                time.sleep(wait); continue
            return {"_http": e.code, "_body": b}, e.code
        except Exception as e:
            if attempt < tries - 1:
                time.sleep(3); continue
            return {"_err": str(e)}, 0
    return {}, 0

def season_qs():
    return ("?season_id=" + SEASON) if SEASON else ""

def write(moves):
    os.makedirs("data", exist_ok=True)
    with open("data/market_updates.json", "w", encoding="utf-8") as f:
        json.dump(moves, f, ensure_ascii=False, indent=1)

def main():
    print("=== MANAGER26 sync Transfermarkt ===")
    print("TM_API:", TM_API, "| Stagione:", (SEASON or "corrente"), "| Competizioni:", COMPS)
    # warm-up: Render free si sveglia dal sonno alla prima chiamata
    _, code = api("/docs", tries=5)
    print("Health check API (/docs) HTTP:", code, "(se 0/errore si sta svegliando: procedo comunque)")

    moves = []; seen = set(); nclubs = 0; nloans = 0; sampled = False
    for comp in COMPS:
        d, c = api("/competitions/" + comp + "/clubs" + season_qs())
        clubs = (d.get("clubs") if isinstance(d, dict) else None) or []
        if not clubs:
            print("  Competizione", comp, "-> 0 club. Risposta:", json.dumps(d, ensure_ascii=False)[:200]); continue
        print("  Competizione", comp, "-> club:", len(clubs))
        for cl in clubs:
            cid = cl.get("id"); cname = clean_team(cl.get("name"))
            if not cid: continue
            pd, pc = api("/clubs/" + str(cid) + "/players" + season_qs())
            players = (pd.get("players") if isinstance(pd, dict) else None) or []
            if not players:
                print("    club", cname, "-> 0 giocatori (", pc, json.dumps(pd, ensure_ascii=False)[:120], ")"); time.sleep(SLEEP); continue
            nclubs += 1
            if not sampled and players:
                print("SAMPLE PLAYER JSON:", json.dumps(players[0], ensure_ascii=False)[:600]); sampled = True
            for pl in players:
                nm = (pl.get("name") or "").strip()
                if not nm: continue
                k = nm + "->" + cname
                if k in seen: continue
                seen.add(k)
                mv = {"player": nm, "to": cname}
                # rilevamento prestito (euristico su piu' campi + eventuale flag)
                owner = pl.get("signedFrom") or ""
                if isinstance(owner, dict): owner = owner.get("name") or ""
                blob = " ".join(str(pl.get(f) or "") for f in ("status","contract","signedFrom","joinedOn","loan","marketValue")).lower()
                is_loan = (pl.get("loan") is True) or any(w in blob for w in ("loan","prest","leih","cedido","prêt","emprunt"))
                if is_loan:
                    mv["loan"] = True; nloans += 1
                    if owner: mv["from"] = clean_team(owner)
                    cend = pl.get("contract") or ""
                    if cend: mv["until"] = str(cend)
                moves.append(mv)
            time.sleep(SLEEP)
    print("RIEPILOGO -> club sincronizzati:", nclubs, "| giocatori:", len(moves), "| prestiti rilevati:", nloans)
    if not moves:
        print(">>> Vuoto: vedi il Ping/le risposte sopra. Se '403 Forbidden' = IP bloccato da Transfermarkt")
        print(">>> (serve un'istanza propria); se '429' = troppo veloce (aumenta SLEEP); se 'giu' = istanza offline.")
    write(moves)
    print("Scritto data/market_updates.json con", len(moves), "voci.")

if __name__ == "__main__":
    main()
