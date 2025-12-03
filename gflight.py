import requests
import time
import sys
from datetime import datetime, timedelta
from ics import Calendar, Event, DisplayAlarm

# --- GESTION TIMEZONES ---
try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

# ==========================================
# 1. CONFIGURATION
# ==========================================

CALENDAR_NAME = "🌴 Djerba (Vols & Culture & Ramadan) ✈️"
ICS_RELIGIEUX_URL = "https://ics.calendarlabs.com/52/f96c26bf/Islam_Holidays.ics"
ICS_SCOLAIRE_URL = "https://fr.ftp.opendatasoft.com/openscol/fr-en-calendrier-scolaire/Zone-C.ics"

# 🔑 CLÉS API (Séparées pour doubler le quota : 150 Aller / 150 Retour)
API_KEY_ALLER = "8f656f24dbmsh228d41d26feed1ap158855jsnfde628f67f3e"
API_KEY_RETOUR = "5b83e86395msh225156d28d5f64bp1b703djsn6d5742f3048a"

HOST = "google-flights2.p.rapidapi.com"
URL = f"https://{HOST}/api/v1/searchFlights"

GPS_ADDRESSES = {
    "ORY": "Aéroport de Paris-Orly (ORY), 94390 Orly, France",
    "CDG": "Aéroport Paris-Charles de Gaulle (CDG), 95700 Roissy-en-France",
    "BVA": "Aéroport Paris-Beauvais (BVA), Route de l'Aéroport, 60000 Tillé, France",
    "DJE": "Aéroport International de Djerba-Zarzis (DJE), 4120 Mellita, Tunisie",
    "TUN": "Aéroport International de Tunis-Carthage (TUN), 1080 Tunis, Tunisie",
    "PAR": "Aéroports de Paris (Générique)"
}

TZ_PARIS = ZoneInfo("Europe/Paris")
TZ_TUNIS = ZoneInfo("Africa/Tunis")

# ==========================================
# 2. LOGIQUE CULTURELLE & RELIGIEUSE
# ==========================================

def get_custom_descriptions():
    return {
        "fitr": "🍪 Aïd el-Fitr\nFête de la rupture du jeûne (Marque la fin du Ramadan).",
        "kebir": "🐑 Aïd el-Kebir\nFête du sacrifice (Aïd al-Adha).",
        "mouled": "🥣 Le Mouled\nNaissance du Prophète (Assida Zgougou).",
        "ashura": "☪️ Achoura\nJour de jeûne et de commémoration.",
        "independance": "🇹🇳 Fête de l'indépendance\nCommémoration du 20 mars 1956.",
        "martyrs": "🇹🇳 Journée des martyrs\nSouvenir du sang versé pour l'indépendance (1938).",
        "republique": "🇹🇳 Fête de la République\nProclamation de la république (1957).",
        "evacuation": "🇹🇳 Fête de l’évacuation\nDépart des troupes françaises de Bizerte (1963).",
        "revolution": "🔥 Fête de la Révolution\nChute du régime précédent (14 janvier 2011)."
    }

def injecter_fetes_hybrides(cal):
    """Mélange ICS dynamique (Religieux) et Dates fixes (Nationales)"""
    descs = get_custom_descriptions()
    today = datetime.now().date()
    limit = today + timedelta(days=700)
    
    # A. FÊTES RELIGIEUSES (ICS)
    print(f"🌍 Récupération des données religieuses...", end=" ")
    try:
        r = requests.get(ICS_RELIGIEUX_URL)
        external_cal = Calendar(r.text)
        count = 0
        
        for event in external_cal.events:
            evt_date = event.begin.date()
            if evt_date < today or evt_date > limit: continue
            name = event.name.lower()
            
            # 1. RAMADAN (PÉRIODE + NUITS IMPAIRES)
            if "ramadan" in name and "end" not in name:
                # La période globale
                e = Event()
                e.name = "🌙 Mois de Ramadan"
                e.begin = evt_date
                e.duration = timedelta(days=30)
                e.make_all_day()
                e.description = "Mois de jeûne et de recueillement."
                e.uid = f"ramadan-{evt_date}@allofly"
                cal.events.add(e)
                
                # Les 5 nuits impaires (Calculées)
                nuits = [21, 23, 25, 27, 29]
                for n in nuits:
                    d_nuit = evt_date + timedelta(days=n-1)
                    enuit = Event()
                    enuit.name = f"✨ Nuit {n} (Laylat al-Qadr ?)"
                    enuit.begin = d_nuit
                    enuit.make_all_day()
                    enuit.description = "Une des nuits impaires sacrées (Nuit du Destin)."
                    enuit.uid = f"laylat-{n}-{evt_date}@allofly"
                    cal.events.add(enuit)
                count += 1

            # 2. AUTRES FÊTES RELIGIEUSES
            elif "fitr" in name or "end of ramadan" in name:
                ajouter_event_simple(cal, evt_date, "🍪 Aïd el-Fitr", descs["fitr"])
                count += 1
            elif "adha" in name or "kebir" in name:
                ajouter_event_simple(cal, evt_date, "🐑 Aïd el-Kebir", descs["kebir"])
                count += 1
            elif "mawlid" in name or "prophet" in name:
                ajouter_event_simple(cal, evt_date, "🥣 Le Mouled", descs["mouled"])
                count += 1
            elif "ashura" in name:
                ajouter_event_simple(cal, evt_date, "☪️ Achoura", descs["ashura"])
                count += 1
        print(f"✅ OK")

    except Exception as e:
        print(f"❌ Erreur ICS: {e}")

    # B. FÊTES NATIONALES (FIXES)
    print("🇹🇳 Génération des fêtes nationales...", end=" ")
    dates_fixes = [
        (1, 14, "🔥 Révolution", descs["revolution"]),
        (3, 20, "🇹🇳 Indépendance", descs["independance"]),
        (4, 9,  "🇹🇳 Martyrs", descs["martyrs"]),
        (5, 6,  "✡️ Ghriba (Est.)", "Pèlerinage à Djerba (Date approx)."), 
        (7, 25, "🇹🇳 République", descs["republique"]),
        (8, 13, "🇹🇳 Fête de la Femme", "Code du statut personnel."),
        (10, 15, "🇹🇳 Évacuation", descs["evacuation"])
    ]
    
    for year in [today.year, today.year + 1]:
        for m, d, tit, desc in dates_fixes:
            try:
                dt = datetime(year, m, d).date()
                if dt >= today:
                    ajouter_event_simple(cal, dt, tit, desc)
            except: pass
    print("✅ OK")

def ajouter_event_simple(cal, date_obj, titre, desc):
    e = Event()
    e.name = titre
    e.begin = date_obj
    e.make_all_day()
    e.description = desc
    e.location = "Tunisie"
    e.uid = f"evt-{titre}-{date_obj}@allofly"
    cal.events.add(e)

# ==========================================
# 3. LOGIQUE VOLS
# ==========================================

def get_target_dates_vacances():
    """Zone C + extensions"""
    print(f"🎓 Analyse vacances Zone C...", end=" ")
    dates_cibles = set()
    today = datetime.now().date()
    
    try:
        r = requests.get(ICS_SCOLAIRE_URL)
        r.encoding = 'utf-8'
        c = Calendar(r.text)
        for e in c.events:
            if e.end.date() >= today:
                # Vacances +/- 7 jours
                start = e.begin.date() - timedelta(days=7)
                end = e.end.date() + timedelta(days=7)
                curr = start
                while curr <= end:
                    if curr >= today: dates_cibles.add(curr.strftime("%Y-%m-%d"))
                    curr += timedelta(days=1)
        
        final = sorted(list(dates_cibles))
        # Note : On ne coupe pas ici, on coupe dans le main pour avoir le log
        print(f"✅ {len(final)} jours potentiels trouvés.")
        return final
    except:
        return [datetime.now().strftime("%Y-%m-%d")]

def scanner_vol(date, api_key, depart, arrivee, sens):
    headers = {"x-rapidapi-key": api_key, "x-rapidapi-host": HOST}
    q = {"departure_id": depart, "arrival_id": arrivee, "outbound_date": date, 
         "currency": "EUR", "travel_class": "ECONOMY", "adults": "1", "search_type": "cheap", 
         "language_code": "fr", "country_code": "FR"}
    try:
        prefix = "🛫" if sens == "aller" else "🔙"
        print(f"{prefix} {date}...", end=" ", flush=True)
        r = requests.get(URL, headers=headers, params=q, timeout=15)
        
        if r.status_code == 200:
            data = r.json().get('data', {})
            raw = (data.get('itineraries', {}).get('topFlights') or []) + (data.get('itineraries', {}).get('otherFlights') or [])
            if not raw: 
                print("❌")
                return None
            
            candidats = []
            for vol in raw:
                # Extraction prix
                try:
                    p = vol['price']['raw'] if isinstance(vol['price'], dict) else int(vol['price'])
                except: p = 9999
                
                segs = vol.get('flights', [])
                if not segs: continue
                cie = segs[0].get('airline', 'Inconnue')
                
                # Calcul Prix Soute
                p_full = p + 50
                if "TRANSAVIA" in cie.upper(): p_full = p + 105
                elif "NOUVELAIR" in cie.upper(): p_full = p + 40
                elif "TUNISAIR" in cie.upper(): p_full = p + 36
                
                candidats.append({"vol": vol, "p": p, "p_full": p_full, "cie": cie})
            
            if not candidats: return None
            # On prend le moins cher bagage inclus
            best = min(candidats, key=lambda x: x['p_full'])
            
            print(f"✅ {best['cie']} ({best['p_full']}€)")
            
            seg = best['vol']['flights'][0]
            return {
                "date": date, "sens": sens, "cie": best['cie'], 
                "p": best['p'], "p_full": best['p_full'],
                "dep": seg['departure_airport']['time'].split(' ')[1],
                "arr": seg['arrival_airport']['time'].split(' ')[1],
                "code_dep": seg['departure_airport']['airport_code'],
                "num": seg['flight_number']
            }
        elif r.status_code == 429: print("⛔ Quota"); return None
    except Exception as e: print(f"Err: {e}")
    return None

def ajouter_event_vol(cal, i):
    e = Event()
    start = datetime.strptime(f"{i['date']} {i['dep']}", "%Y-%m-%d %H:%M")
    end = datetime.strptime(f"{i['date']} {i['arr']}", "%Y-%m-%d %H:%M")
    if end < start: end += timedelta(days=1)
    
    if i['sens'] == "aller":
        start = start.replace(tzinfo=TZ_PARIS)
        end = end.replace(tzinfo=TZ_TUNIS)
        titre = f"🛫 {i['p']}€ | 🛄{i['p_full']}€ • {i['cie']}"
    else:
        start = start.replace(tzinfo=TZ_TUNIS)
        end = end.replace(tzinfo=TZ_PARIS)
        titre = f"🔙 {i['p']}€ | 🛄{i['p_full']}€ • {i['cie']}"

    e.begin = start
    e.end = end
    e.name = titre
    
    desc = (
        f"💰 PRIX: {i['p']}€ (Sac) / {i['p_full']}€ (Valise)\n"
        f"✈️ VOL: {i['cie']} ({i['num']})\n"
        f"📍 {i['code_dep']} -> {i['arr']}"
    )
    e.description = desc
    e.location = GPS_ADDRESSES.get(i['code_dep'], i['code_dep'])
    e.uid = f"vol-{i['date']}-{i['sens']}@allofly"
    cal.events.add(e)

# ==========================================
# 4. MAIN
# ==========================================

def main():
    cal = Calendar()
    print("="*60)
    print(f"🚀 {CALENDAR_NAME}")
    print("="*60)

    # 1. CULTURE & RELIGION
    injecter_fetes_hybrides(cal)

    # 2. DATES (AVEC SÉCURITÉ QUOTA)
    raw_dates = get_target_dates_vacances()
    
    # --- LA PROTECTION EST ICI ---
    # On garde seulement les 35 premières dates
    # 35 * 4 lundis = 140 requêtes (Quota API = 150)
    dates = raw_dates[:35]
    
    if len(raw_dates) > 35:
        print(f"\n⚠️ ATTENTION: {len(raw_dates)} dates trouvées.")
        print(f"✂️ SÉCURITÉ ACTIVÉE : On scanne uniquement les 35 prochaines pour protéger le quota API.")
    
    # 3. SCANS
    print(f"\n🔎 Scan ALLER ({len(dates)} dates)")
    for d in dates:
        res = scanner_vol(d, API_KEY_ALLER, "PAR", "DJE", "aller")
        if res: ajouter_event_vol(cal, res)
        time.sleep(1.1)

    print(f"\n🔎 Scan RETOUR ({len(dates)} dates)")
    for d in dates:
        res = scanner_vol(d, API_KEY_RETOUR, "DJE", "PAR", "retour")
        if res: ajouter_event_vol(cal, res)
        time.sleep(1.1)

    # 4. EXPORT
    ics_data = cal.serialize()
    if "X-WR-CALNAME" not in ics_data:
        ics_data = ics_data.replace("VERSION:2.0", f"VERSION:2.0\nX-WR-CALNAME:{CALENDAR_NAME}")
        
    with open("planning_djerba_complet.ics", "w", encoding="utf-8") as f:
        f.write(ics_data)
        
    print("\n" + "="*60)
    print("✨ TERMINÉ ! Fichier : planning_djerba_complet.ics")

if __name__ == "__main__":
    main()
