import requests
import time
import sys
from datetime import datetime, timedelta
from ics import Calendar, Event, DisplayAlarm

# --- GESTION ROBUSTE DES TIMEZONES ---
try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

# ==========================================
# 1. CONFIGURATION
# ==========================================

CALENDAR_NAME = "🌴 Djerba Tracker (Kilos Cumulés) ✈️"

API_KEY = "d63d9c3353mshba1a97be0e24b1dp15148ajsn4d780c446e3a"
HOST = "google-flights2.p.rapidapi.com"
URL = f"https://{HOST}/api/v1/searchFlights"

HEADERS = {
    "x-rapidapi-key": API_KEY,
    "x-rapidapi-host": HOST
}

MOIS_ETE = [7, 8]
DUREE_VACANCES_ETE = 14  

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
# 2. LOGIQUE INTELLIGENTE (PRIX & POIDS)
# ==========================================

def calculer_vrai_prix(compagnie_nom, prix_brut):
    nom_upper = compagnie_nom.upper().strip()
    
    # --- A. TRANSAVIA (Le Champion du Poids en option Max) ---
    if "TRANSAVIA" in nom_upper:
        suppl_cabine = 48 
        suppl_soute = 105 
        
        prix_cabine = prix_brut + suppl_cabine
        prix_full = prix_brut + suppl_soute
        
        description_bagages = (
            f"⚠️ ATTENTION TRANSAVIA (Prix ajustés) :\n"
            f"❌ Base Google ({prix_brut}€) = Sac à dos (0kg garantis)\n"
            f"🛄 OPTION CABINE (Tarif Smart) : {prix_cabine}€\n"
            f"   ⚖️ TOTAL : 10 KG (1 valise cabine)\n"
            f"🛄🗃️ OPTION LOURDE (Tarif Max) : {prix_full}€\n"
            f"   ⚖️ TOTAL CUMULÉ : 40 KG !!! (10kg Cabine + 30kg Soute)"
        )

    # --- B. NOUVELAIR (Bon rapport Poids/Prix) ---
    elif "NOUVELAIR" in nom_upper:
        suppl_cabine = 0
        suppl_soute = 40
        
        prix_cabine = prix_brut
        prix_full = prix_brut + suppl_soute
        
        description_bagages = (
            f"✅ NOUVELAIR (Transparent) :\n"
            f"🛄 CABINE (Inclus) : {prix_cabine}€\n"
            f"   ⚖️ TOTAL : 8 KG (1 valise cabine)\n"
            f"🛄🗃️ OPTION LOURDE (Tarif Easy) : {prix_full}€\n"
            f"   ⚖️ TOTAL CUMULÉ : 33 KG (8kg Cabine + 25kg Soute)"
        )

    # --- C. TUNISAIR (Standard) ---
    elif "TUNISAIR" in nom_upper:
        suppl_cabine = 0
        suppl_soute = 36
        
        prix_cabine = prix_brut
        prix_full = prix_brut + suppl_soute
        
        description_bagages = (
            f"✅ TUNISAIR (Classique) :\n"
            f"🛄 CABINE (Inclus) : {prix_cabine}€\n"
            f"   ⚖️ TOTAL : 8 KG (1 valise cabine)\n"
            f"🛄🗃️ OPTION LOURDE (Tarif Classic) : {prix_full}€\n"
            f"   ⚖️ TOTAL CUMULÉ : 31 KG (8kg Cabine + 23kg Soute)"
        )

    # --- D. AUTRES ---
    else:
        prix_cabine = prix_brut
        prix_full = prix_brut + 50
        description_bagages = (
            f"❓ COMPAGNIE INCONNUE ({compagnie_nom})\n"
            f"   ⚖️ Poids non garanti par le script."
        )
    
    return prix_cabine, prix_full, description_bagages

# ==========================================
# 3. FONCTIONS UTILITAIRES
# ==========================================

def get_next_30_days():
    dates = []
    today = datetime.now()
    current = today + timedelta(days=1)
    for _ in range(30):
        dates.append(current.strftime("%Y-%m-%d"))
        current += timedelta(days=1)
    return dates

def safe_get_price(vol):
    try:
        p_val = vol.get('price')
        if isinstance(p_val, int) or isinstance(p_val, float):
            return int(p_val)
        elif isinstance(p_val, dict):
            return int(p_val.get('raw', 9999))
        return 9999
    except:
        return 9999

# ==========================================
# 4. SCANNER
# ==========================================

def scanner_vol(date_aller):
    dt_aller = datetime.strptime(date_aller, "%Y-%m-%d")

    querystring = {
        "departure_id": "PAR",
        "arrival_id": "DJE",
        "outbound_date": date_aller,
        "currency": "EUR",
        "travel_class": "ECONOMY",
        "adults": "1",
        "search_type": "cheap",
        "language_code": "fr",
        "country_code": "FR"
    }

    if dt_aller.month in MOIS_ETE:
        mode_voyage = f"AR ({DUREE_VACANCES_ETE}j)"
        dt_retour = dt_aller + timedelta(days=DUREE_VACANCES_ETE)
        querystring["return_date"] = dt_retour.strftime("%Y-%m-%d")
    else:
        mode_voyage = "Aller Simple"

    try:
        print(f"🔎 {date_aller}...", end=" ", flush=True)
        response = requests.get(URL, headers=HEADERS, params=querystring, timeout=15)

        if response.status_code == 200:
            data = response.json().get('data', {})
            itineraries = data.get('itineraries', {})
            vols = (itineraries.get('topFlights') or []) + (itineraries.get('otherFlights') or [])

            if vols:
                best_vol = min(vols, key=safe_get_price)
                prix = safe_get_price(best_vol)
                segments = best_vol.get('flights', [])
                if not segments: return None

                seg_aller = segments[0]
                compagnie = seg_aller.get('airline', 'N/A')
                num_vol = seg_aller.get('flight_number', '')

                t_dep = seg_aller.get('departure_airport', {}).get('time', '')
                t_arr = seg_aller.get('arrival_airport', {}).get('time', '')
                code_dep = seg_aller.get('departure_airport', {}).get('airport_code', 'PAR')

                heure_dep = t_dep.split(' ')[1] if ' ' in t_dep else "00:00"
                heure_arr = t_arr.split(' ')[1] if ' ' in t_arr else "00:00"

                info_retour = ""
                if "return_date" in querystring and len(segments) > 1:
                    seg_retour = segments[-1]
                    date_ret_raw = seg_retour.get('departure_airport', {}).get('time', '').split(' ')[0]
                    h_dep_r = seg_retour.get('departure_airport', {}).get('time', '').split(' ')[1]
                    h_arr_r = seg_retour.get('arrival_airport', {}).get('time', '').split(' ')[1]
                    info_retour = f"\n🔙 RETOUR ({date_ret_raw}) : {h_dep_r} -> {h_arr_r}"

                print(f"✅ {prix}€ ({compagnie})")

                return {
                    "date": date_aller,
                    "prix": prix,
                    "compagnie": compagnie,
                    "num_vol": num_vol,
                    "heure_dep": heure_dep,
                    "heure_arr": heure_arr,
                    "code_dep": code_dep,
                    "info_retour": info_retour,
                    "mode": mode_voyage
                }
            else:
                print("❌ Vide")
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
    dates_a_scanner = get_next_30_days()

    print("=" * 50)
    print(f"🚀 {CALENDAR_NAME}")
    print("=" * 50)

    for date in dates_a_scanner:
        info = scanner_vol(date)

        if info:
            e = Event()
            
            p_cabine, p_total, texte_bagages = calculer_vrai_prix(info['compagnie'], info['prix'])

            str_start = f"{info['date']} {info['heure_dep']}"
            str_end = f"{info['date']} {info['heure_arr']}"
            if info['heure_arr'] < info['heure_dep']:
                dt_arr_temp = datetime.strptime(info['date'], "%Y-%m-%d") + timedelta(days=1)
                str_end = f"{dt_arr_temp.strftime('%Y-%m-%d')} {info['heure_arr']}"

            e.begin = datetime.strptime(str_start, "%Y-%m-%d %H:%M").replace(tzinfo=TZ_PARIS)
            e.end = datetime.strptime(str_end, "%Y-%m-%d %H:%M").replace(tzinfo=TZ_TUNIS)

            # TITRE
            icon_deal = "🔥" if p_cabine < 150 else "✈️"
            e.name = f"{icon_deal} 🛄{p_cabine}€ | 🛄🗃️{p_total}€ • {info['compagnie']}"

            # DESCRIPTION
            desc = (
                f"📊 POIDS & PRIX (Cabine vs Soute)\n"
                f"----------------------------------\n"
            )
            desc += texte_bagages + "\n"
            desc += f"----------------------------------\n"
            desc += (
                f"🎫 {info['mode']}\n"
                f"🛫 {info['heure_dep']} ({info['code_dep']}) -> {info['heure_arr']} (DJE)\n"
                f"🏢 {info['compagnie']} ({info['num_vol']})\n"
            )
            
            if info['info_retour']:
                desc += info['info_retour'] + "\n"
            
            e.description = desc
            e.location = GPS_ADDRESSES.get(info['code_dep'], info['code_dep'])
            e.alarms.append(DisplayAlarm(trigger=timedelta(days=-1)))
            e.uid = f"{info['num_vol']}-{info['date']}@allofly"

            cal.events.add(e)

        time.sleep(1.2)

    nom_fichier = "vols_djerba_kilos.ics"
    ics_content = cal.serialize()
    
    if "X-WR-CALNAME" not in ics_content:
        ics_content = ics_content.replace("VERSION:2.0", f"VERSION:2.0\nX-WR-CALNAME:{CALENDAR_NAME}")

    with open(nom_fichier, 'w', encoding='utf-8') as f:
        f.write(ics_content)

    print("\n" + "=" * 50)
    print(f"✨ TERMINÉ ! Fichier généré : {nom_fichier}")

if __name__ == "__main__":
    main()
