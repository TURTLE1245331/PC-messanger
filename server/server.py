import sqlite3
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

# 1. Konfiguration & Umgebungsvariablen
load_dotenv()
ADMIN_KEY = os.getenv("ADMIN_KEY", "7588")
VERSION = "3.1"
DB_PATH = "richard.db"

app = FastAPI()

# Verzeichnis für Bilder erstellen & mounten
if not os.path.exists("img"):
    os.makedirs("img")
app.mount("/img", StaticFiles(directory="img"), name="img")

# Jinja2 Setup
env = Environment(loader=FileSystemLoader("."))

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
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS users 
                      (username TEXT PRIMARY KEY, password_hash TEXT)''')
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

def clear_database():
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

def get_all_messages():
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
    return decrypted

# --- API ENDPUNKTE ---

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    try:
        template = env.get_template("index.html")
        return HTMLResponse(content=template.render(request=request))
    except Exception:
        if os.path.exists("index.html"):
            with open("index.html", "r", encoding="utf-8") as f:
                return HTMLResponse(content=f.read())
        return HTMLResponse(content="<h1>Index.html nicht gefunden</h1>")

@app.get("/style.css")
async def get_style():
    return FileResponse("style.css")

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

@app.get("/get")
async def get_msgs(request: Request, last_id: int = 0):
    user, pw = request.headers.get("X-User"), request.headers.get("X-Pass")
    is_valid = False

    if user == "Admin" and pw == ADMIN_KEY:
        is_valid = True
    elif user and pw:
        conn = sqlite3.connect(DB_PATH)
        res = conn.execute("SELECT password_hash FROM users WHERE username=?", (user,)).fetchone()
        conn.close()
        if res and bcrypt.checkpw(pw.encode(), res[0].encode()):
            is_valid = True

    if not is_valid:
        raise HTTPException(status_code=401)

    msgs = get_all_messages()
    return {"messages": msgs[last_id:], "total": len(msgs)}

@app.post("/send")
async def send_msg(request: Request):
    data = await request.json()
    text = data.get("text", "").strip()

    # REMOTE COMMAND: CLEAR
    if text.lower() == "clear":
        clear_database()
        print("RICHARD > Datenbank via API (Remote) geleert.")
        return {"status": "ok", "action": "cleared"}

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

        except EOFError:
            break

# --- START ---
if __name__ == "__main__":
    init_db()
    # Konsolen-Thread starten
    threading.Thread(target=console_input, daemon=True).start()
    # Webserver starten (Wichtig: host="0.0.0.0" für Docker!)
    uvicorn.run(app, host="0.0.0.0", port=8000, log_config=None)