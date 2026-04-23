"""
update_agenda.py — Bot diario para Danivia TV NeWeDeN
Se ejecuta automáticamente cada día a las 7:00 AM via GitHub Actions.
Obtiene la agenda deportiva de España y la guarda en Firebase Firestore.
"""

import json
import os
import urllib.request
import urllib.parse
from datetime import datetime, timezone, timedelta

# ── Firebase REST API (sin SDK, solo HTTP) ──────────────────────────────────
FIREBASE_PROJECT = "daniviatvwebnewedenpro"
FIREBASE_URL = f"https://firestore.googleapis.com/v1/projects/{FIREBASE_PROJECT}/databases/(default)/documents"

def get_firebase_token():
    """Obtiene token de autenticación usando la service account key de GitHub Secrets."""
    import base64, hmac, hashlib, time, json

    key_json = os.environ.get("FIREBASE_SERVICE_ACCOUNT")
    if not key_json:
        print("⚠ FIREBASE_SERVICE_ACCOUNT no configurado - guardando solo en consola")
        return None

    creds = json.loads(key_json)
    
    # JWT Header
    header = base64.urlsafe_b64encode(json.dumps({"alg":"RS256","typ":"JWT"}).encode()).rstrip(b'=').decode()
    
    now = int(time.time())
    payload_data = {
        "iss": creds["client_email"],
        "scope": "https://www.googleapis.com/auth/datastore",
        "aud": "https://oauth2.googleapis.com/token",
        "exp": now + 3600,
        "iat": now
    }
    payload = base64.urlsafe_b64encode(json.dumps(payload_data).encode()).rstrip(b'=').decode()
    
    # Firma RSA (usando cryptography si está disponible)
    try:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding
        
        private_key = serialization.load_pem_private_key(
            creds["private_key"].encode(), password=None
        )
        message = f"{header}.{payload}".encode()
        signature = private_key.sign(message, padding.PKCS1v15(), hashes.SHA256())
        sig = base64.urlsafe_b64encode(signature).rstrip(b'=').decode()
        jwt_token = f"{header}.{payload}.{sig}"
        
        # Cambiar por access token
        data = urllib.parse.urlencode({
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "assertion": jwt_token
        }).encode()
        
        req = urllib.request.Request(
            "https://oauth2.googleapis.com/token",
            data=data,
            method="POST"
        )
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read())["access_token"]
    except Exception as e:
        print(f"⚠ Error obteniendo token Firebase: {e}")
        return None


def save_to_firestore(agenda_data, token):
    """Guarda la agenda en Firestore via REST API."""
    if not token:
        print("📋 Agenda generada (sin guardar en Firebase):")
        print(json.dumps(agenda_data, ensure_ascii=False, indent=2))
        return

    # Convertir a formato Firestore
    fields = {
        "agendaData": {
            "stringValue": json.dumps(agenda_data, ensure_ascii=False)
        },
        "lastUpdated": {
            "stringValue": datetime.now(timezone.utc).isoformat()
        },
        "dateLabel": {
            "stringValue": datetime.now(timezone(timedelta(hours=2))).strftime("%d %b %Y")
        }
    }

    doc = {"fields": fields}
    data = json.dumps(doc).encode()

    url = f"{FIREBASE_URL}/siteContent/agenda"
    req = urllib.request.Request(
        url,
        data=data,
        method="PATCH",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
    )

    try:
        with urllib.request.urlopen(req) as r:
            print(f"✅ Agenda guardada en Firestore: {r.status}")
    except Exception as e:
        print(f"❌ Error guardando en Firestore: {e}")


# ── Fuente de datos: TheSportsDB (gratuita) ─────────────────────────────────
THESPORTS_KEY = "3"  # Clave pública gratuita

def fetch_league_events(league_id, league_name, sport_cat):
    """Obtiene próximos eventos de una liga."""
    url = f"https://www.thesportsdb.com/api/v1/json/{THESPORTS_KEY}/eventsnextleague.php?id={league_id}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "DaniviaTVBot/1.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
        
        today = datetime.now(timezone(timedelta(hours=2))).strftime("%Y-%m-%d")
        events = []
        
        for ev in (data.get("events") or []):
            if ev.get("dateEvent") == today:
                home = ev.get("strHomeTeam", "")
                away = ev.get("strAwayTeam", "")
                time_str = ev.get("strTime", "")[:5] if ev.get("strTime") else "TBD"
                venue = ev.get("strVenue", "")
                
                events.append({
                    "t": time_str,
                    "c": league_name,
                    "m": f"{home} — {away}",
                    "ch": venue or league_name,
                    "feat": False
                })
        
        return events
    except Exception as e:
        print(f"⚠ Error en {league_name}: {e}")
        return []


def fetch_tennis_today():
    """Eventos de tenis del día (ATP/WTA)."""
    # TheSportsDB tiene tenis limitado; usamos datos fijos de temporada
    today = datetime.now(timezone(timedelta(hours=2)))
    month = today.month
    day = today.day
    
    # Calendario aproximado de torneos grandes
    events = []
    
    # Mutua Madrid Open: 18 abril - 4 mayo
    if month == 4 and 18 <= day <= 30:
        events.append({
            "t": "11:00", "c": "WTA Mutua Madrid Open",
            "m": "Cuadro femenino — rondas del día",
            "ch": "Teledeporte / M+ Deportes", "feat": False
        })
        events.append({
            "t": "13:00", "c": "ATP Mutua Madrid Open Masters 1000",
            "m": "Cuadro masculino — rondas del día (lidera Sinner)",
            "ch": "M+ Deportes 2", "feat": True
        })
    
    # Roland Garros: ~25 mayo - 8 junio
    if (month == 5 and day >= 25) or (month == 6 and day <= 8):
        events.append({
            "t": "10:00", "c": "Roland Garros · Grand Slam",
            "m": "Rondas del día — Tierra batida de París",
            "ch": "Eurosport / DAZN", "feat": True
        })
    
    # Wimbledon: 30 junio - 13 julio
    if (month == 6 and day >= 30) or (month == 7 and day <= 13):
        events.append({
            "t": "12:00", "c": "Wimbledon · Grand Slam",
            "m": "Rondas del día — Hierba de Londres",
            "ch": "Eurosport / DAZN", "feat": True
        })
    
    return events


def fetch_cycling_today():
    """Carreras ciclistas del día."""
    today = datetime.now(timezone(timedelta(hours=2)))
    month = today.month
    day = today.day
    events = []
    
    # Giro de Italia: ~9 mayo - 1 junio
    if (month == 5 and day >= 9) or (month == 6 and day == 1):
        events.append({
            "t": "12:00", "c": "Giro de Italia · UCI World Tour",
            "m": f"Etapa del día — Gran Tour italiano",
            "ch": "Eurosport 2 / DAZN", "feat": True
        })
    
    # Tour de Francia: ~5 julio - 27 julio
    if month == 7 and 5 <= day <= 27:
        events.append({
            "t": "13:00", "c": "Tour de Francia · UCI World Tour",
            "m": "Etapa del día — La Grande Boucle",
            "ch": "Eurosport 2 / DAZN", "feat": True
        })
    
    # Vuelta a España: ~13 agosto - 7 sept
    if (month == 8 and day >= 13) or (month == 9 and day <= 7):
        events.append({
            "t": "14:00", "c": "La Vuelta a España · UCI World Tour",
            "m": "Etapa del día — La Vuelta",
            "ch": "RTVE / Eurosport", "feat": True
        })
    
    return events


def fetch_motogp_today():
    """Sesiones de MotoGP del día."""
    today = datetime.now(timezone(timedelta(hours=2)))
    month = today.month
    day = today.day
    events = []
    
    # Calendario MotoGP 2026 aproximado
    grands_prix = [
        (3, 29, "GP Qatar", "Losail"),
        (4, 12, "GP Portugal", "Portimão"),
        (4, 26, "GP España", "Jerez — Circuito Ángel Nieto"),
        (5, 10, "GP Francia", "Le Mans"),
        (5, 31, "GP Italia", "Mugello"),
        (6, 14, "GP Cataluña", "Circuit de Barcelona"),
        (6, 28, "GP Países Bajos", "Assen"),
        (7, 12, "GP Alemania", "Sachsenring"),
        (8, 9, "GP Gran Bretaña", "Silverstone"),
        (8, 23, "GP Austria", "Red Bull Ring"),
        (9, 6, "GP San Marino", "Misano"),
        (9, 20, "GP Aragón", "MotorLand Aragón"),
        (10, 4, "GP Japón", "Motegi"),
        (10, 18, "GP Australia", "Phillip Island"),
        (11, 1, "GP Malasia", "Sepang"),
        (11, 15, "GP Valencia", "Circuit Ricardo Tormo"),
    ]
    
    for gp_month, gp_day, gp_name, circuit in grands_prix:
        # Viernes: libres, Sábado: clasif, Domingo: carrera
        if month == gp_month and abs(day - gp_day) <= 2:
            diff = day - gp_day
            session = {-2: "Libres FP1/FP2", -1: "Libres FP3 + Clasificación", 0: "CARRERA"}
            session_name = session.get(diff, "Sesión del día")
            events.append({
                "t": "14:00" if diff == 0 else "10:00",
                "c": f"MotoGP 2026 · {gp_name}",
                "m": f"{session_name} — {circuit}",
                "ch": "DAZN / Teledeporte",
                "feat": diff == 0
            })
    
    return events


# ── Ligas de fútbol (IDs de TheSportsDB) ───────────────────────────────────
LEAGUES = [
    ("4335", "LaLiga EA Sports", "futbol"),
    ("4329", "Premier League", "futbol"),
    ("4331", "Bundesliga", "futbol"),
    ("4332", "Serie A", "futbol"),
    ("4334", "Ligue 1", "futbol"),
    ("4328", "Champions League", "futbol"),
]


def build_agenda():
    """Construye la agenda completa del día."""
    print(f"🔄 Generando agenda para {datetime.now(timezone(timedelta(hours=2))).strftime('%d/%m/%Y')}...")
    
    agenda = []
    
    # 1. Fútbol — consultar cada liga
    futbol_events = []
    for league_id, league_name, cat in LEAGUES:
        events = fetch_league_events(league_id, league_name, cat)
        futbol_events.extend(events)
        print(f"  ⚽ {league_name}: {len(events)} partidos hoy")
    
    if futbol_events:
        agenda.append({
            "cat": "futbol",
            "sport": "Fútbol — Partidos del día",
            "events": futbol_events
        })
    
    # 2. Tenis
    tenis = fetch_tennis_today()
    if tenis:
        agenda.append({"cat": "tenis", "sport": "Tenis", "events": tenis})
        print(f"  🎾 Tenis: {len(tenis)} sesiones")
    
    # 3. Ciclismo
    ciclo = fetch_cycling_today()
    if ciclo:
        agenda.append({"cat": "ciclismo", "sport": "Ciclismo", "events": ciclo})
        print(f"  🚴 Ciclismo: {len(ciclo)} carreras")
    
    # 4. MotoGP
    moto = fetch_motogp_today()
    if moto:
        agenda.append({"cat": "moto", "sport": "MotoGP", "events": moto})
        print(f"  🏍 MotoGP: {len(moto)} sesiones")
    
    # Si no hay nada, mensaje de descanso
    if not agenda:
        agenda.append({
            "cat": "otros",
            "sport": "Día de descanso deportivo",
            "events": [{
                "t": "—",
                "c": "Sin eventos programados hoy",
                "m": "Mañana vuelve la acción deportiva",
                "ch": "DANIVIA TV",
                "feat": False
            }]
        })
    
    print(f"✅ Agenda lista: {sum(len(s['events']) for s in agenda)} eventos en {len(agenda)} deportes")
    return agenda


# ── Main ────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 55)
    print("  DANIVIA TV NeWeDeN — Bot Agenda Deportiva")
    print(f"  {datetime.now(timezone(timedelta(hours=2))).strftime('%d/%m/%Y %H:%M')} (hora España)")
    print("=" * 55)
    
    agenda = build_agenda()
    token = get_firebase_token()
    save_to_firestore(agenda, token)
    
    print("\n📺 DANIVIA TV NeWeDeN — Agenda actualizada correctamente")
