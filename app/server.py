import sqlite3
import socket
from contextlib import asynccontextmanager
import bcrypt
import logging
import threading
import uvicorn
import base64
import os
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from dotenv import load_dotenv
import time
import redis
import json
print("loading configuration ...")
# 1. Konfiguration & Umgebungsvariablen
load_dotenv()
ADMIN_KEY = os.getenv("ADMIN_KEY", "7588")
VERSION = "3.4-canary"
DB_PATH = "richard.db"
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_DB = int(os.getenv("REDIS_DB", 0))
CSS_PATH = "webdata/style.css"
HTML_PATH = "webdata/index.html"
IMG_DIR = "webdata/img"
print("configuration complete")

def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # Verbindung zu einer nicht erreichbaren IP herstellen, um die Standard-Route zu ermitteln
        s.connect(('10.254.254.254', 1))
        ip = s.getsockname()[0]
    except Exception:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip

def admin_warning():
    if ADMIN_KEY == "7588":
        print("!!PLEASE CHANGE ADMIN KEY IN .env FILE AND REBOOT SERVER!!")
    else:
        print("ADMIN KEY OK...")
        
admin_warning()

print("initializing redis ...")
# Redis Initialisierung
try:
    redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, decode_responses=True)
    redis_client.ping()
    print(f"RICHARD > Redis verbunden ({REDIS_HOST}:{REDIS_PORT})")
except Exception as e:
    print(f"RICHARD > Redis Verbindung fehlgeschlagen: {e}")
    redis_client = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Datenbank initialisieren
    init_db()
    yield
    # Shutdown: Nachricht ausgeben
    print("RICHARD > Shutdown-Prozess gestartet.")

app = FastAPI(lifespan=lifespan)

# BASE_DIR bestimmen
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
IMG_DIR = os.path.join(BASE_DIR, "img")

# Verzeichnis für Bilder erstellen & mounten
if not os.path.exists(IMG_DIR):
    os.makedirs(IMG_DIR)
app.mount("/img", StaticFiles(directory=IMG_DIR), name="img")

# Jinja2 Setup
env = Environment(loader=FileSystemLoader(BASE_DIR))

# --- VERSCHLÜSSELUNGS-LOGIK ---
def get_cipher():
    salt = b'richard_secure_salt_88' 
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100000,
    )
    key = base64.urlsafe_b64encode(kdf.derive(ADMIN_KEY.encode()))
    return Fernet(key)

cipher = get_cipher()

# --- DATENBANK FUNKTIONEN ---
def init_db():
    print("initializing database ...")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS users 
                      (username TEXT PRIMARY KEY, password_hash TEXT)''')
    print("database initialized")
    # Vorhandene Spalten (Migration)
    columns = [
        ("chat_bg", "TEXT"),
        ("accent_color", "TEXT"),
        ("transparency", "INTEGER"),
        ("font_size", "INTEGER"),
        ("msg_radius", "INTEGER"),
        ("msg_spacing", "INTEGER"),
        ("bg_blur", "INTEGER"),
        ("chat_width", "INTEGER"),
        ("animations", "INTEGER"),
        ("timestamps", "INTEGER"),
        ("autoscroll", "INTEGER"),
        ("privacy_mode", "INTEGER"),
        ("sound_enabled", "INTEGER")
    ]
    
    for col_name, col_type in columns:
        try:
            cursor.execute(f"ALTER TABLE users ADD COLUMN {col_name} {col_type}")
        except sqlite3.OperationalError:
            pass
            
    cursor.execute('''CREATE TABLE IF NOT EXISTS messages 
                      (id INTEGER PRIMARY KEY AUTOINCREMENT, content TEXT)''')
    conn.commit()
    conn.close()

def save_message(text):
    encrypted_text = cipher.encrypt(text.encode()).decode()
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT INTO messages (content) VALUES (?)", (encrypted_text,))
    conn.commit()
    conn.close()
    
    # Redis Integration
    if redis_client:
        try:
            msg_obj = {"text": text}
            # Als List für schnelles Abrufen (Caching)
            redis_client.rpush("chat_messages", json.dumps(msg_obj))
            # Nur die letzten 100 Nachrichten im Cache behalten
            redis_client.ltrim("chat_messages", -100, -1)
            # Pub/Sub für Echtzeit-Übertragung
            redis_client.publish("chat_channel", json.dumps(msg_obj))
        except Exception as e:
            print(f"RICHARD > Redis Save-Fehler: {e}")

def clear_database():
    print("clearing database ...")
    """Löscht alle Nachrichten und setzt den ID-Zähler zurück."""
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute("DELETE FROM messages")
        conn.execute("DELETE FROM sqlite_sequence WHERE name='messages'")
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Fehler beim Löschen der DB: {e}")
        return False
    finally:
        if redis_client:
            try:
                redis_client.delete("chat_messages")
            except Exception:
                pass

def get_all_messages():
    # Zuerst in Redis nachsehen
    if redis_client:
        try:
            cached_msgs = redis_client.lrange("chat_messages", 0, -1)
            if cached_msgs:
                return [json.loads(m) for m in cached_msgs]
        except Exception as e:
            print(f"RICHARD > Redis Get-Fehler: {e}")

    # Fallback auf SQLite
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT content FROM messages").fetchall()
    conn.close()
    
    decrypted = []
    for row in rows:
        try:
            msg = cipher.decrypt(row[0].encode()).decode()
            decrypted.append({"text": msg})
        except Exception:
            decrypted.append({"text": "[Kryptofehler: Nachricht unlesbar]"})
    
    # Cache befüllen falls leer
    if redis_client and decrypted:
        try:
            # Nur die letzten 100 in den Cache
            to_cache = decrypted[-100:]
            redis_client.delete("chat_messages")
            for m in to_cache:
                redis_client.rpush("chat_messages", json.dumps(m))
        except Exception:
            pass
            
    return decrypted

# --- API ENDPUNKTE ---

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    try:
        template = env.get_template(HTML_PATH)
        return HTMLResponse(content=template.render(request=request))
    except Exception:
        if os.path.exists(HTML_PATH):
            with open(HTML_PATH, "r", encoding="utf-8") as f:
                return HTMLResponse(content=f.read())
        return HTMLResponse(content="<h1>Index.html nicht gefunden</h1>")
        print("html not found check paths...")
@app.get("/style.css")
async def get_style():
    return FileResponse(CSS_PATH)
    print("css not found check paths...")

@app.post("/register")
async def register(request: Request):
    data = await request.json()
    username, password = data.get("username"), data.get("password")
    
    if not username or not password:
        raise HTTPException(status_code=400, detail="Felder leer")
    
    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)", (username, hashed))
        conn.commit()
        conn.close()
        return {"status": "User registriert"}
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="Nutzername vergeben")


@app.post("/login")
async def login(request: Request):
    user, pw = request.headers.get("X-User"), request.headers.get("X-Pass")
    if not user or not pw:
        raise HTTPException(status_code=400, detail="Zugangsdaten fehlen")
        
    if user == "Admin" and pw == ADMIN_KEY:
        return {"status": "ok", "user": "Admin"}
        
    conn = sqlite3.connect(DB_PATH)
    res = conn.execute("SELECT password_hash FROM users WHERE username=?", (user,)).fetchone()
    conn.close()
    
    if res and bcrypt.checkpw(pw.encode(), res[0].encode()):
        return {"status": "ok", "user": user}
        
    raise HTTPException(status_code=401, detail="Falsche Zugangsdaten")

@app.post("/upload_bg")
async def upload_bg(request: Request):
    data = await request.json()
    bg_data = data.get("bg", "")
    user, pw = request.headers.get("X-User"), request.headers.get("X-Pass")
    
    if user and pw and bg_data.startswith("data:image"):
        conn = sqlite3.connect(DB_PATH)
        res = conn.execute("SELECT password_hash FROM users WHERE username=?", (user,)).fetchone()
        if res and bcrypt.checkpw(pw.encode(), res[0].encode()):
            try:
                # Bild speichern
                header, encoded = bg_data.split(",", 1)
                img_data = base64.b64decode(encoded)
                filename = f"bg_{user}.jpg"
                filepath = os.path.join(IMG_DIR, filename)
                
                with open(filepath, "wb") as f:
                    f.write(img_data)
                
                conn.execute("UPDATE users SET chat_bg=? WHERE username=?", (filename, user))
                conn.commit()
            except Exception as e:
                print(f"Error saving BG: {e}")
        conn.close()

    return {"status": "ok"}

@app.post("/delete_account")
async def delete_account(request: Request):
    user, pw = request.headers.get("X-User"), request.headers.get("X-Pass")
    if not user or not pw or user == "Admin":
        raise HTTPException(status_code=401)
        
    is_valid = False
    conn = sqlite3.connect(DB_PATH)
    res = conn.execute("SELECT password_hash FROM users WHERE username=?", (user,)).fetchone()
    if res and bcrypt.checkpw(pw.encode(), res[0].encode()):
        is_valid = True
        # Hintergrund-Datei löschen
        filepath = os.path.join(IMG_DIR, f"bg_{user}.jpg")
        if os.path.exists(filepath):
            os.remove(filepath)
            
        conn.execute("DELETE FROM users WHERE username=?", (user,))
        conn.commit()
    conn.close()

    return {"status": "ok"}

@app.post("/reset_bg")
async def reset_bg(request: Request):
    user, pw = request.headers.get("X-User"), request.headers.get("X-Pass")
    if not user or not pw:
        raise HTTPException(status_code=401)
        
    is_valid = False
    conn = sqlite3.connect(DB_PATH)
    res = conn.execute("SELECT password_hash FROM users WHERE username=?", (user,)).fetchone()
    if res and bcrypt.checkpw(pw.encode(), res[0].encode()):
        is_valid = True
        # Hintergrund-Datei löschen
        filepath = os.path.join(IMG_DIR, f"bg_{user}.jpg")
        if os.path.exists(filepath):
            os.remove(filepath)
            
        conn.execute("UPDATE users SET chat_bg = NULL WHERE username=?", (user,))
        conn.commit()
    conn.close()

    return {"status": "ok"}

@app.post("/change_password")
async def change_password(request: Request):
    user, pw = request.headers.get("X-User"), request.headers.get("X-Pass")
    data = await request.json()
    new_pw = data.get("new_password")
    
    if not user or not pw or not new_pw or user == "Admin":
        raise HTTPException(status_code=400)
        
    is_valid = False
    conn = sqlite3.connect(DB_PATH)
    res = conn.execute("SELECT password_hash FROM users WHERE username=?", (user,)).fetchone()
    if res and bcrypt.checkpw(pw.encode(), res[0].encode()):
        is_valid = True
        new_hash = bcrypt.hashpw(new_pw.encode(), bcrypt.gensalt()).decode()
        conn.execute("UPDATE users SET password_hash = ? WHERE username=?", (new_hash, user))
        conn.commit()
    conn.close()

    if not is_valid:
        raise HTTPException(status_code=401)
    return {"status": "ok"}

@app.post("/change_username")
async def change_username(request: Request):
    user, pw = request.headers.get("X-User"), request.headers.get("X-Pass")
    data = await request.json()
    new_name = data.get("new_username")
    
    if not user or not pw or not new_name or user == "Admin":
        raise HTTPException(status_code=400)
    
    # Prüfen ob Name existiert
    conn = sqlite3.connect(DB_PATH)
    exists = conn.execute("SELECT 1 FROM users WHERE username=?", (new_name,)).fetchone()
    if exists:
        conn.close()
        return {"status": "error", "message": "Name bereits vergeben"}

    is_valid = False
    res = conn.execute("SELECT password_hash FROM users WHERE username=?", (user,)).fetchone()
    if res and bcrypt.checkpw(pw.encode(), res[0].encode()):
        is_valid = True
        conn.execute("UPDATE users SET username = ? WHERE username=?", (new_name, user))
        conn.commit()
    conn.close()

    if not is_valid:
        raise HTTPException(status_code=401)
    return {"status": "ok", "new_name": new_name}

@app.get("/get_stats")
async def get_stats():
    conn = sqlite3.connect(DB_PATH)
    msg_count = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
    user_count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    conn.close()
    return {"messages": msg_count, "users": user_count}

@app.get("/get_user_settings")
async def get_user_settings(request: Request):
    user, pw = request.headers.get("X-User"), request.headers.get("X-Pass")
    settings = {
        "bg": None, 
        "accent": "#38bdf8", 
        "transparency": 60,
        "font_size": 16,
        "msg_radius": 16,
        "msg_spacing": 12,
        "bg_blur": 0,
        "chat_width": 100,
        "animations": 1,
        "timestamps": 1,
        "autoscroll": 1,
        "privacy_mode": 0,
        "sound_enabled": 1
    }
    if user and pw:
        try:
            conn = sqlite3.connect(DB_PATH)
            # Alle Spalten abrufen
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE username=?", (user,))
            row = cursor.fetchone()
            names = [description[0] for description in cursor.description]
            conn.close()
            
            if row:
                user_data = dict(zip(names, row))
                if bcrypt.checkpw(pw.encode(), user_data["password_hash"].encode()):
                    if user_data.get("chat_bg"):
                        settings["bg"] = f"/img/{user_data['chat_bg']}?v={int(time.time())}"
                    
                    if user_data.get("accent_color"): settings["accent"] = user_data["accent_color"]
                    if user_data.get("transparency") is not None: settings["transparency"] = user_data["transparency"]
                    
                    # Neue Einstellungen mappen
                    for key in settings.keys():
                        if key in user_data and user_data[key] is not None:
                            settings[key] = user_data[key]
        except Exception as e:
            print(f"Error fetching settings: {e}")
    return settings

@app.post("/update_design")
async def update_design(request: Request):
    user, pw = request.headers.get("X-User"), request.headers.get("X-Pass")
    data = await request.json()
    
    if not user or not pw:
        raise HTTPException(status_code=400)
        
    is_valid = False
    conn = sqlite3.connect(DB_PATH)
    res = conn.execute("SELECT password_hash FROM users WHERE username=?", (user,)).fetchone()
    if res and bcrypt.checkpw(pw.encode(), res[0].encode()):
        is_valid = True
        
        allowed_keys = [
            "accent_color", "transparency", "font_size", "msg_radius", 
            "msg_spacing", "bg_blur", "chat_width", "animations", 
            "timestamps", "autoscroll", "privacy_mode", "sound_enabled"
        ]
        
        # Mapping von Frontend-Keys zu DB-Keys
        key_map = {
            "accent": "accent_color",
            "transparency": "transparency",
            "font_size": "font_size",
            "msg_radius": "msg_radius",
            "msg_spacing": "msg_spacing",
            "bg_blur": "bg_blur",
            "chat_width": "chat_width",
            "animations": "animations",
            "timestamps": "timestamps",
            "autoscroll": "autoscroll",
            "privacy_mode": "privacy_mode",
            "sound_enabled": "sound_enabled"
        }
        
        for json_key, db_key in key_map.items():
            if json_key in data:
                val = data[json_key]
                conn.execute(f"UPDATE users SET {db_key} = ? WHERE username=?", (val, user))
        
        conn.commit()
    conn.close()

    if not is_valid:
        raise HTTPException(status_code=401)
    return {"status": "ok"}


@app.get("/get")
async def get_msgs(request: Request, last_id: int = 0):
    user, pw = request.headers.get("X-User"), request.headers.get("X-Pass")
    is_valid = False

    if user == "Admin" and pw == ADMIN_KEY:
        is_valid = True
    elif user and pw:
        try:
            conn = sqlite3.connect(DB_PATH)
            res = conn.execute("SELECT password_hash FROM users WHERE username=?", (user,)).fetchone()
            conn.close()
            if res and bcrypt.checkpw(pw.encode(), res[0].encode()):
                is_valid = True
        except Exception:
            pass

    if not is_valid:
        raise HTTPException(status_code=401)

    msgs = get_all_messages()
    return {"messages": msgs[last_id:], "total": len(msgs)}

@app.post("/send")
async def send_msg(request: Request):
    user, pw = request.headers.get("X-User"), request.headers.get("X-Pass")
    data = await request.json()
    text = data.get("text", "").strip()

    # REMOTE COMMAND: CLEAR (Nur Admin!)
    if text.lower() == "clear":
        if user == "Admin" and pw == ADMIN_KEY:
            clear_database()
            print("RICHARD > Datenbank via API (Remote) geleert.")
            return {"status": "ok", "action": "cleared"}
        else:
            raise HTTPException(status_code=403)

    save_message(text)
    return {"status": "ok"}

# --- KONSOLEN STEUERUNG ---
def console_input():
    logging.getLogger("uvicorn").setLevel(logging.ERROR)
    logging.getLogger("uvicorn.access").setLevel(logging.ERROR)
    
    print(f"\n" + "="*40)
    print(f"   RICHARD v{VERSION} ONLINE")
    print(f"   ADMIN: Admin / {ADMIN_KEY}")
    print("="*40 + "\n")
    
    while True:
        try:
            cmd = input("RICHARD > ").strip()
            if not cmd: continue

            if cmd == "clear":
                auth = input("Admin-Key zur Bestätigung: ")
                if auth == ADMIN_KEY:
                    if clear_database():
                        # Optional: Konsole im Terminal optisch leeren
                        os.system('clear')
                        print("[*] Datenbank und Konsole geleert.")
                else:
                    print("[!] Falscher Key.")
            
            elif cmd.startswith("msg "):
                save_message(f"[SERVER]: {cmd[4:]}")
                print(f"[*] Gesendet.")

            elif cmd == "exit":
                print("Beende...")
                os._exit(0)

            elif cmd == "show ip":
                hostname = socket.gethostname()
                ip_address = socket.gethostbyname(hostname)
                print(f"RICHARD > IP: {ip_address}")
                print("For more ip infrmation use [ip a] if linux or [ipconfig] if windows")
                


            
                

        except EOFError:
            break

# --- START ---
if __name__ == "__main__":
    # Konsolen-Thread starten
    threading.Thread(target=console_input, daemon=True).start()
    # Webserver starten (Wichtig: host="0.0.0.0" für Docker!)
    uvicorn.run(app, host="0.0.0.0", port=8000, log_config=None)
    