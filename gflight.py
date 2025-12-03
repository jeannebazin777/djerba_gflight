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

CALENDAR_NAME = "🌴 Djerba (Aller 30j / Retour Vacances) ✈️"

# CLÉ 1 : Pour l'ALLER (30 jours glissants)
API_KEY_ALLER = "8f656f24dbmsh228d41d26feed1ap158855jsnfde628f67f3e"

# CLÉ 2 : Pour le RETOUR (Vacances Zone C)
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
# 2. GÉNÉRATEURS DE DATES
# ==========================================

def get_next_30_days():
    """
    Génère les 30 prochains jours pour l'aller.
    """
    print(f"📅 Calcul des dates ALLER (30 jours glissants)...")
    dates = []
    today = datetime.now()
    current = today + timedelta(days=1)
    
    for _ in range(30):
        dates.append(current.strftime("%Y-%m-%d"))
        current += timedelta(days=1)
        
    return dates

def get_dates_vacances_pour_retour():
    """
    Télécharge l'ICS Zone C et cible les périodes de vacances pour le RETOUR.
    On prend large : semaine avant + vacances + semaine après.
    """
    url_ics = "https://fr.ftp.opendatasoft.com/openscol/fr-en-calendrier-scolaire/Zone-C.ics"
    print(f"🎓 Analyse des vacances Zone C pour le RETOUR...", end=" ")
    
    dates_cibles = set()
    today = datetime.now().date()
    
    try:
        r = requests.get(url_ics)
        r.encoding = 'utf-8'
        c = Calendar(r.text)
        
        for e in c.events:
            # Si les vacances finissent dans le futur
            if e.end.date() >= today:
                # Période de scan : Vacances +/- 7 jours
                start_window = e.begin.date() - timedelta(days=7)
                end_window = e.end.date() + timedelta(days=7)
                
                current = start_window
                while current <= end_window:
                    if current >= today:
                        dates_cibles.add(current.strftime("%Y-%m-%d"))
                    current += timedelta(days=1)
        
        sorted_dates = sorted(list(dates_cibles))
        # Limitation technique pour ne pas griller la clé 2 (145 requêtes max)
        final_dates = sorted_dates[:145]
        
        print(f"✅ OK ! ({len(final_dates)} jours de scan identifiés)")
        return final_dates

    except Exception as e:
        print(f"❌ Erreur ICS ({e}). Fallback sur 30 jours.")
        return get_next_30_days()

# ==========================================
# 3. LOGIQUE PRIX & POIDS
# ==========================================

def calculer_infos_completes(compagnie_nom, prix_brut):
    nom_upper = compagnie_nom.upper().strip()
    p_cabine = prix_brut
    p_full = prix_brut + 50
    details = ""

    if "TRANSAVIA" in nom_upper:
        p_cabine = prix_brut + 48
        p_full = prix_brut + 105
        details = (
            f"⚠️ ATTENTION TRANSAVIA (Prix ajustés) :\n"
            f"❌ Base Google ({prix_brut}€) = Sac à dos (0kg)\n"
            f"🛄 OPTION CABINE (Tarif Smart) : {p_cabine}€\n"
            f"   ⚖️ TOTAL : 10 KG\n"
            f"🛄🗃️ OPTION LOURDE (Tarif Max) : {p_full}€\n"
            f"   ⚖️ TOTAL CUMULÉ : 40 KG !!! (30kg soute)"
        )
    elif "NOUVELAIR" in nom_upper:
        p_cabine = prix_brut 
        p_full = prix_brut + 40
        details = (
            f"✅ NOUVELAIR (Transparent) :\n"
            f"🛄 CABINE (Inclus) : {p_cabine}€\n"
            f"   ⚖️ TOTAL : 8 KG\n"
            f"🛄🗃️ OPTION LOURDE (Tarif Easy) : {p_full}€\n"
            f"   ⚖️ TOTAL CUMULÉ : 33 KG (25kg soute)"
        )
    elif "TUNISAIR" in nom_upper:
        p_cabine = prix_brut
        p_full = prix_brut + 36
        details = (
            f"✅ TUNISAIR (Classique) :\n"
            f"🛄 CABINE (Inclus) : {p_cabine}€\n"
            f"   ⚖️ TOTAL : 8 KG\n"
            f"🛄🗃️ OPTION LOURDE (Tarif Classic) : {p_full}€\n"
            f"   ⚖️ TOTAL CUMULÉ : 31 KG (23kg soute)"
        )
    else:
        details = f"❓ {compagnie_nom} : Prix soute estimé (+50€)"

    return {"prix_cabine": p_cabine, "prix_full": p_full, "details": details}

# ==========================================
# 4. SCANNER
# ==========================================

def safe_get_price(vol):
    try:
        p_val = vol.get('price')
        if isinstance(p_val, int) or isinstance(p_val, float): return int(p_val)
        elif isinstance(p_val, dict): return int(p_val.get('raw', 9999))
        return 9999
    except: return 9999

def scanner_vol(date, api_key_to_use, depart, arrivee, sens_voyage):
    headers = {"x-rapidapi-key": api_key_to_use, "x-rapidapi-host": HOST}
    querystring = {
        "departure_id": depart,
        "arrival_id": arrivee,
        "outbound_date": date,
        "currency": "EUR",
        "travel_class": "ECONOMY",
        "adults": "1",
        "search_type": "cheap",
        "language_code": "fr",
        "country_code": "FR"
    }

    try:
        prefix = "🛫 ALLER" if sens_voyage == "aller" else "🔙 RETOUR"
        print(f"{prefix} {date}...", end=" ", flush=True)
        response = requests.get(URL, headers=headers, params=querystring, timeout=15)

        if response.status_code == 200:
            data = response.json().get('data', {})
            itineraries = data.get('itineraries', {})
            raw_vols = (itineraries.get('topFlights') or []) + (itineraries.get('otherFlights') or [])

            if not raw_vols:
                print("❌ Vide")
                return None

            candidats = []
            for vol in raw_vols:
                prix_brut = safe_get_price(vol)
                segments = vol.get('flights', [])
                if not segments: continue
                compagnie = segments[0].get('airline', 'Inconnue')
                simu = calculer_infos_completes(compagnie, prix_brut)
                candidats.append({"vol": vol, "simu": simu, "compagnie": compagnie})

            if not candidats: return None

            # TRI INTELLIGENT : PRIORITÉ PRIX SOUTE
            best = min(candidats, key=lambda x: x['simu']['prix_full'])
            
            final_vol = best['vol']
            final_simu = best['simu']
            final_compagnie = best['compagnie']

            seg = final_vol.get('flights', [])[0]
            num_vol = seg.get('flight_number', '')
            t_dep = seg.get('departure_airport', {}).get('time', '').split(' ')[1]
            t_arr = seg.get('arrival_airport', {}).get('time', '').split(' ')[1]
            code_dep = seg.get('departure_airport', {}).get('airport_code', depart)

            print(f"✅ {final_compagnie} ({final_simu['prix_full']}€)")

            return {
                "date": date,
                "compagnie": final_compagnie,
                "num_vol": num_vol,
                "heure_dep": t_dep,
                "heure_arr": t_arr,
                "code_dep": code_dep,
                "simu": final_simu,
                "sens": sens_voyage
            }
        elif response.status_code == 429:
             print("⛔ STOP : QUOTA DÉPASSÉ !")
             return None
        else:
            print(f"⚠️ Err {response.status_code}")
    except Exception as e:
        print(f"💥 {e}")
    return None

# ==========================================
# 5. MAIN
# ==========================================

def main():
    cal = Calendar()

    print("=" * 60)
    print(f"🚀 {CALENDAR_NAME}")
    print("=" * 60)

    # --- PHASE 1 : ALLER (30 JOURS GLISSANTS) ---
    dates_aller = get_next_30_days()
    print(f"\n🛫 PHASE 1 : ALLER (Clé 1 - {len(dates_aller)} jours)")
    
    for date in dates_aller:
        info = scanner_vol(date, API_KEY_ALLER, "PAR", "DJE", "aller")
        if info: ajouter_evenement(cal, info)
        time.sleep(1.1) 

    # --- PHASE 2 : RETOUR (ZONES VACANCES UNIQUEMENT) ---
    print(f"\n🔙 PHASE 2 : RETOUR (Clé 2 - Zones Vacances)")
    
    dates_retour_vacances = get_dates_vacances_pour_retour()
    
    for date in dates_retour_vacances:
        info = scanner_vol(date, API_KEY_RETOUR, "DJE", "PAR", "retour")
        if info: ajouter_evenement(cal, info)
        time.sleep(1.1)

    # --- SAUVEGARDE ---
    nom_fichier = "vols_djerba_final.ics"
    ics_content = cal.serialize()
    if "X-WR-CALNAME" not in ics_content:
        ics_content = ics_content.replace("VERSION:2.0", f"VERSION:2.0\nX-WR-CALNAME:{CALENDAR_NAME}")

    with open(nom_fichier, 'w', encoding='utf-8') as f:
        f.write(ics_content)

    print("\n" + "=" * 60)
    print(f"✨ TERMINÉ ! Fichier généré : {nom_fichier}")

def ajouter_evenement(cal, info):
    e = Event()
    simu = info['simu']
    
    str_start = f"{info['date']} {info['heure_dep']}"
    str_end = f"{info['date']} {info['heure_arr']}"
    if info['heure_arr'] < info['heure_dep']:
        dt_arr_temp = datetime.strptime(info['date'], "%Y-%m-%d") + timedelta(days=1)
        str_end = f"{dt_arr_temp.strftime('%Y-%m-%d')} {info['heure_arr']}"

    dt_start = datetime.strptime(str_start, "%Y-%m-%d %H:%M")
    dt_end = datetime.strptime(str_end, "%Y-%m-%d %H:%M")

    if info['sens'] == "aller":
        dt_start = dt_start.replace(tzinfo=TZ_PARIS)
        dt_end = dt_end.replace(tzinfo=TZ_TUNIS)
        icon_sens = "🛫"
        trajet_txt = f"{info['code_dep']} -> DJE"
    else:
        dt_start = dt_start.replace(tzinfo=TZ_TUNIS)
        dt_end = dt_end.replace(tzinfo=TZ_PARIS)
        icon_sens = "🔙"
        trajet_txt = f"Djerba -> Paris"

    e.begin = dt_start
    e.end = dt_end
    
    e.name = f"{icon_sens} 🛄{simu['prix_cabine']}€ | 🛄🗃️{simu['prix_full']}€ • {info['compagnie']}"

    desc = (
        f"🏆 PRIX & POIDS ({info['sens'].upper()})\n"
        f"----------------------------------\n"
    )
    desc += simu['details'] + "\n"
    desc += f"----------------------------------\n"
    desc += (
        f"📍 {trajet_txt}\n"
        f"🕒 {info['heure_dep']} -> {info['heure_arr']}\n"
        f"🏢 {info['compagnie']} ({info['num_vol']})\n"
    )
    
    e.description = desc
    e.location = GPS_ADDRESSES.get(info['code_dep'], info['code_dep'])
    e.alarms.append(DisplayAlarm(trigger=timedelta(days=-1)))
    e.uid = f"{info['date']}-{info['sens']}@allofly"
    cal.events.add(e)

if __name__ == "__main__":
    main()
