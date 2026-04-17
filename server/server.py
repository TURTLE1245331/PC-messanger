import logging
import sys
import threading
import uvicorn
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles  # <--- NEU: Import für statische Dateien
from jinja2 import Environment, FileSystemLoader

app = FastAPI()

# --- NEU: Ordner "img" für den Browser freigeben ---
# Das sorgt dafür, dass url("img/b.png") in deiner CSS funktioniert.
app.mount("/img", StaticFiles(directory="img"), name="img")

storage = []  # Hier liegen alle Nachrichten
env = Environment(loader=FileSystemLoader("."))

ADMIN_USER = "Admin"
ADMIN_PASS = "1234"

version = "1.0"

@app.post("/send")
async def send_msg(request: Request):
    data = await request.json()
    storage.append(data)
    return {"status": "ok"}

@app.get("/get")
async def get_msgs(request: Request, last_id: int = 0):
    if request.headers.get("X-User") != ADMIN_USER or request.headers.get("X-Pass") != ADMIN_PASS:
        raise HTTPException(status_code=401)

    global storage
    if last_id > len(storage):
        return {
            "messages": [{"text": "__CLEAR__"}],
            "total": 0
        }

    return {
        "messages": storage[last_id:],
        "total": len(storage)
    }

@app.get("/", response_class=HTMLResponse)
async def read_item(request: Request):
    template = env.get_template("index.html")
    return HTMLResponse(content=template.render(request=request))

@app.get("/style.css")
async def get_style():
    return FileResponse("style.css")

def console_input():
    global storage
    logging.getLogger("uvicorn").disabled = True
    logging.getLogger("uvicorn.access").disabled = True
    print("\n" + "="*20 + "\nRICHARD " + version + " BEREIT\n" + "="*20)
    
    while True:
        cmd = input("> ").strip()
        if cmd == "clear":
            storage.clear()
            print("[*] Server-Speicher wurde geleert.")
        elif cmd.startswith("msg "):
            storage.append({"text": f"[SERVER]: {cmd[4:]}"})
        elif cmd == "exit":
            import os; os._exit(0)

if __name__ == "__main__":
    threading.Thread(target=console_input, daemon=True).start()
    uvicorn.run(app, host="127.0.0.1", port=8000, log_config=None)