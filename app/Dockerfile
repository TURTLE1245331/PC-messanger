FROM python:3.11-slim

# Arbeitsverzeichnis setzen
WORKDIR /app

# Abhängigkeiten kopieren und installieren
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Den restlichen Code kopieren
COPY . .

# Verzeichnis für Bilder erstellen
RUN mkdir -p /app/server/img

# Port freigeben
EXPOSE 8000

# Server starten
CMD ["python", "server.py"]
