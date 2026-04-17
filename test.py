import requests
import sys
import os

# Adresse deines Servers
URL = "http://192.168.178.55:8000/send"

def send_message(text):
    payload = {"text": text}
    try:
        response = requests.post(URL, json=payload, timeout=5)
        if response.status_code == 200:
            # Wir geben nur bei normalen Nachrichten eine Bestätigung
            if text.lower() != "clear":
                print(f"✅ Erfolgreich gesendet: {text}")
        else:
            print(f"❌ Fehler vom Server: {response.status_code}")
    except Exception as e:
        print(f"💥 Verbindung fehlgeschlagen: {e}")

if __name__ == "__main__":
    # Einmalig den Screen leeren für den Profi-Look
    os.system('cls' if os.name == 'nt' else 'clear')
    
    print("--- RICHARD REMOTE MESSENGER ---")
    print("Befehle: 'clear' zum Leeren, 'exit' zum Beenden")
    print("--------------------------------")
    
    while True:
        try:
            user_input = input("> ").strip()
            
            if not user_input:
                continue

            # COMMAND SUPPORT
            cmd = user_input.lower()
            
            if cmd == 'exit':
                print("Bye!")
                break
            
            if cmd == 'clear':
                # 1. Lokal am PC leeren
                os.system('cls' if os.name == 'nt' else 'clear')
                print("--- RICHARD REMOTE MESSENGER (Cleared) ---")
                # 2. Den Befehl trotzdem an den Server senden
                send_message("clear")
                continue

            # NORMALE NACHRICHT SENDEN
            send_message(user_input)
            
        except KeyboardInterrupt:
            print("\nAbgebrochen.")
            break