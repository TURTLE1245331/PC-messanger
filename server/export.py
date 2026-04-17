import sqlite3
import base64
import os
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from dotenv import load_dotenv

# Passwort laden
load_dotenv()
ADMIN_KEY = os.getenv("ADMIN_KEY")

def get_cipher():
    # Muss exakt derselbe Salt wie in der server.py sein!
    salt = b'richard_secure_salt_88' 
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100000,
    )
    key = base64.urlsafe_b64encode(kdf.derive(ADMIN_KEY.encode()))
    return Fernet(key)

def export_messages():
    db_path = "richard.db"
    
    if not os.path.exists(db_path):
        print(f"[!] Fehler: {db_path} nicht gefunden. Starte erst den Server!")
        return

    cipher = get_cipher()
    conn = sqlite3.connect(db_path)
    rows = [] # Wir definieren rows hier als leer, damit der NameError verschwindet

    try:
        # Hier holen wir die Daten
        rows = conn.execute("SELECT content FROM messages").fetchall()
    except sqlite3.OperationalError:
        print("[!] Fehler: Die Tabelle 'messages' existiert nicht in der Datenbank.")
    finally:
        conn.close()

    # Wenn rows nicht leer ist, exportieren wir
    if rows:
        with open("export_chat.txt", "w", encoding="utf-8") as f:
            for row in rows:
                try:
                    decrypted = cipher.decrypt(row[0].encode()).decode()
                    f.write(decrypted + "\n")
                except Exception as e:
                    f.write(f"[Entschlüsselungsfehler]\n")
        print(f"[*] Erfolgreich {len(rows)} Nachrichten in 'export_chat.txt' gespeichert.")
    else:
        print("[?] Keine Nachrichten zum Exportieren gefunden.")

if __name__ == "__main__":
    export_messages()