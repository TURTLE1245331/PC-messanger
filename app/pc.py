import tkinter as tk
from tkinter import scrolledtext
import requests
import threading
import time

SERVER_URL = "http://127.0.0.1:8000"

class Messenger:
    def __init__(self, root):
        self.root = root
        self.root.title("Wayland Safe Messenger")
        self.root.geometry("400x600")
        self.root.configure(bg="#121212")

        # Header
        self.header = tk.Label(root, text="Nachrichten", bg="#121212", fg="#BB86FC", 
                               font=("Arial", 12, "bold"), pady=10)
        self.header.pack()

        # Chat-Bereich
        self.display = scrolledtext.ScrolledText(root, bg="#1e1e1e", fg="white", 
                                               font=("Arial", 12), padx=10, pady=10,
                                               borderwidth=0, highlightthickness=0)
        self.display.pack(expand=True, fill="both", padx=10, pady=10)
        self.display.config(state='disabled') # Nur Lesen

        # Polling Thread starten
        self.running = True
        self.thread = threading.Thread(target=self.poll, daemon=True)
        self.thread.start()

    def add_message(self, text):
        self.display.config(state='normal')
        self.display.insert(tk.END, f"➤ {text}\n\n")
        self.display.see(tk.END) # Automatisch nach unten scrollen
        self.display.config(state='disabled')

    def poll(self):
        while self.running:
            try:
                r = requests.get(f"{SERVER_URL}/get", timeout=1)
                if r.status_code == 200:
                    for m in r.json():
                        msg = m.get("text", "")
                        # Tkinter braucht diesen Befehl, um sicher aus Threads zu schreiben
                        self.root.after(0, self.add_message, msg)
            except:
                pass
            time.sleep(0.1)

if __name__ == "__main__":
    root = tk.Tk()
    app = Messenger(root)
    root.mainloop()