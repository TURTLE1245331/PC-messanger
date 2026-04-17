import requests
import sys

# Adresse deines Servers
URL = "http://127.0.0.1:8000/send"

def send_message(text):
    payload = {"text": text}
    try:
        response = requests.post(URL, json=payload, timeout=5)
        if response.status_code == 200:
            print(f"✅ Erfolgreich gesendet: {text}")
        else:
            print(f"❌ Fehler vom Server: {response.status_code}")
    except Exception as e:
        print(f"💥 Verbindung fehlgeschlagen: {e}")

if __name__ == "__main__":
    print("--- PC Messenger Test-Sender ---")
    print("Tippe deine Nachricht ein und drücke Enter (oder 'exit' zum Beenden)")
    
    while True:
        user_input = input("> ")
        if user_input.lower() == 'exit':
            break
        if user_input.strip():
            send_message(user_input)