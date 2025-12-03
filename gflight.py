import requests
import time
import sys
from datetime import datetime, timedelta
from ics import Calendar, Event, DisplayAlarm

# --- GESTION ROBUSTE DES TIMEZONES ---
try:
    from zoneinfo import ZoneInfo
except ImportError:
    # Fallback pour les environnements plus anciens
    from backports.zoneinfo import ZoneInfo

# ==========================================
# 1. CONFIGURATION (NE PAS TOUCHER)
# ==========================================

# Clé API & Endpoints
API_KEY = "52a391eccbmsh9df81d221e7ee66p138217jsnde1e036469c9"
HOST = "google-flights2.p.rapidapi.com"
URL = f"https://{HOST}/api/v1/searchFlights"

HEADERS = {
    "x-rapidapi-key": API_KEY,
    "x-rapidapi-host": HOST
}

# Configuration Saisonnière
# Si le départ est en Juillet (7) ou Août (8) -> On cherche un Aller-Retour
MOIS_ETE = [7, 8]
DUREE_VACANCES_ETE = 14  # Durée du séjour en été (14 jours)

# Configuration Géographique (GPS Précis pour Waze/Google Maps)
GPS_ADDRESSES = {
    "ORY": "Aéroport de Paris-Orly (ORY), 94390 Orly, France",
    "CDG": "Aéroport Paris-Charles de Gaulle (CDG), 95700 Roissy-en-France",
    "BVA": "Aéroport Paris-Beauvais (BVA), Route de l'Aéroport, 60000 Tillé, France",
    "DJE": "Aéroport International de Djerba-Zarzis (DJE), 4120 Mellita, Tunisie",
    "TUN": "Aéroport International de Tunis-Carthage (TUN), 1080 Tunis, Tunisie",
    "PAR": "Aéroports de Paris (Générique)"
}

# Fuseaux Horaires (Crucial pour éviter les décalages)
TZ_PARIS = ZoneInfo("Europe/Paris")
TZ_TUNIS = ZoneInfo("Africa/Tunis")


# ==========================================
# 2. FONCTIONS UTILITAIRES
# ==========================================

def get_next_30_days():
    """Génère la liste des dates pour les 30 prochains jours (Fenêtre Glissante)."""
    dates = []
    today = datetime.now()
    # On commence à J+1 pour éviter les vols du jour même souvent hors de prix/déjà partis
    current = today + timedelta(days=1)

    for _ in range(30):
        dates.append(current.strftime("%Y-%m-%d"))
        current += timedelta(days=1)

    return dates


def safe_get_price(vol):
    """Extrait le prix proprement, peu importe le format renvoyé par l'API."""
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
# 3. CŒUR DU SYSTÈME (SCRAPER)
# ==========================================

def scanner_vol(date_aller):
    dt_aller = datetime.strptime(date_aller, "%Y-%m-%d")

    # --- A. PRÉPARATION DE LA REQUÊTE ---
    querystring = {
        "departure_id": "PAR",
        "arrival_id": "DJE",
        "outbound_date": date_aller,
        "currency": "EUR",
        "travel_class": "ECONOMY",
        "adults": "1",
        "search_type": "cheap",  # On force la recherche "Low Cost"
        "language_code": "fr",
        "country_code": "FR"
    }

    # --- B. LOGIQUE ÉTÉ (ALLER-RETOUR) ---
    mode_voyage = "Aller Simple"
    if dt_aller.month in MOIS_ETE:
        mode_voyage = f"AR ({DUREE_VACANCES_ETE}j)"
        # Calcul de la date de retour
        dt_retour = dt_aller + timedelta(days=DUREE_VACANCES_ETE)
        querystring["return_date"] = dt_retour.strftime("%Y-%m-%d")

    # --- C. APPEL API ---
    try:
        print(f"🔎 Scan du {date_aller} [{mode_voyage}]...", end=" ", flush=True)
        response = requests.get(URL, headers=HEADERS, params=querystring, timeout=15)

        if response.status_code == 200:
            data = response.json().get('data', {})
            itineraries = data.get('itineraries', {})

            # On combine Top Flights et Other Flights pour ne rien rater
            vols = (itineraries.get('topFlights') or []) + (itineraries.get('otherFlights') or [])

            if vols:
                # On trouve le vol le moins cher de la liste
                best_vol = min(vols, key=safe_get_price)
                prix = safe_get_price(best_vol)

                # Extraction des segments de vol
                segments = best_vol.get('flights', [])
                if not segments:
                    return None

                # INFOS ALLER (Toujours le 1er segment)
                seg_aller = segments[0]
                compagnie = seg_aller.get('airline', 'N/A')
                num_vol = seg_aller.get('flight_number', '')

                # Horaires & Aéroports
                t_dep = seg_aller.get('departure_airport', {}).get('time', '')  # Format: YYYY-MM-DD HH:MM
                t_arr = seg_aller.get('arrival_airport', {}).get('time', '')
                code_dep = seg_aller.get('departure_airport', {}).get('airport_code', 'PAR')

                # Nettoyage des heures (On garde HH:MM)
                heure_dep = t_dep.split(' ')[1] if ' ' in t_dep else "00:00"
                heure_arr = t_arr.split(' ')[1] if ' ' in t_arr else "00:00"

                # INFOS RETOUR (Seulement si AR détecté et plusieurs segments)
                info_retour = ""
                # Si c'est un AR, l'API renvoie souvent les segments aller puis les segments retour
                if "return_date" in querystring and len(segments) > 1:
                    seg_retour = segments[-1]  # Le dernier segment est souvent le retour
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
                print("❌ Aucun vol trouvé")
        else:
            print(f"⚠️ Erreur API {response.status_code}")

    except Exception as e:
        print(f"💥 Crash sur cette date : {e}")

    return None


# ==========================================
# 4. EXÉCUTION PRINCIPALE
# ==========================================

def main():
    cal = Calendar()
    dates_a_scanner = get_next_30_days()

    print("=" * 50)
    print(f"🚀 DÉCOLLAGE : ALLOFLY BOT")
    print(f"📅 Période : 30 jours (Fenêtre Glissante)")
    print(f"💳 Crédits estimés : {len(dates_a_scanner)}")
    print("=" * 50)

    for date in dates_a_scanner:
        info = scanner_vol(date)

        if info:
            e = Event()

            # --- 4.1 CONSTRUCTION DES DATES (TIMEZONE AWARE) ---
            str_start = f"{info['date']} {info['heure_dep']}"
            str_end = f"{info['date']} {info['heure_arr']}"

            # Gestion basique si l'arrivée est le lendemain (Vol de nuit)
            if info['heure_arr'] < info['heure_dep']:
                dt_arr_temp = datetime.strptime(info['date'], "%Y-%m-%d") + timedelta(days=1)
                str_end = f"{dt_arr_temp.strftime('%Y-%m-%d')} {info['heure_arr']}"

            # Conversion en objets datetime
            dt_start = datetime.strptime(str_start, "%Y-%m-%d %H:%M").replace(tzinfo=TZ_PARIS)
            dt_end = datetime.strptime(str_end, "%Y-%m-%d %H:%M").replace(tzinfo=TZ_TUNIS)

            e.begin = dt_start
            e.end = dt_end

            # --- 4.2 VISUEL & CONTENU ---
            # Emoji 🔥 si prix < 150€ (Bon plan AR ou AS)
            icon = "🔥" if info['prix'] < 150 else "✈️"
            e.name = f"{icon} {info['prix']}€ Djerba ({info['mode']} - {info['compagnie']})"

            # Adresse GPS Magique
            e.location = GPS_ADDRESSES.get(info['code_dep'], f"Aéroport {info['code_dep']}")

            desc = (
                f"💰 PRIX : {info['prix']} €\n"
                f"🎫 TYPE : {info['mode']}\n"
                f"🛫 ALLER : {info['heure_dep']} ({info['code_dep']}) -> {info['heure_arr']} (DJE)\n"
                f"🏢 COMPAGNIE : {info['compagnie']} ({info['num_vol']})\n"
            )

            if info['info_retour']:
                desc += info['info_retour'] + "\n"

            desc += f"\n📍 GPS : {e.location}"

            e.description = desc

            # Alerte 24h avant
            e.alarms.append(DisplayAlarm(trigger=timedelta(days=-1)))

            # ID Unique pour éviter les doublons dans le calendrier
            e.uid = f"{info['num_vol']}-{info['date']}@allofly"

            cal.events.add(e)

        # Pause anti-blocage (1.2 seconde)
        time.sleep(1.2)

    # --- 4.3 SAUVEGARDE ---
    nom_fichier = "vols_djerba.ics"
    with open(nom_fichier, 'w', encoding='utf-8') as f:
        f.writelines(cal.serialize())

    print("\n" + "=" * 50)
    print(f"✨ TERMINÉ ! Fichier généré : {nom_fichier}")
    print("👉 Pense à l'automatiser 1 fois/semaine (Lundi) !")


if __name__ == "__main__":
    main()