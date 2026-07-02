#!/bin/bash
DEBUG=false
if [ "$1" = "--debug" ] || [ "$1" = "-d" ]; then
    DEBUG=true
    echo "=== DEBUG MODE AKTIVIERT ==="
fi

echo "============================================================"
echo "THERESE - Produktionsstart (Gunicorn)"
echo "============================================================"

cd /home/therese/therese

if [ "$DEBUG" = true ]; then
    echo "Aktuelles Verzeichnis: $(pwd)"
    echo "User: $(whoami)"
fi

# Lade .env falls vorhanden (für CERT_FILE / KEY_FILE etc.)
if [ -f .env ]; then
    set -a
    . .env
    set +a
fi

# Alte Instanzen beenden
echo "Beende alte eigene Gunicorn-Instanzen..."
pkill -f "gunicorn.*therese_prod" 2>/dev/null || true
sleep 2
# Falls noch welche laufen, hart beenden
pkill -9 -f "gunicorn.*therese_prod" 2>/dev/null || true
sleep 1

# Virtuelle Umgebung
source /home/therese/venv/bin/activate

# Logs + Media
mkdir -p logs
chmod 755 logs
mkdir -p media
chmod 755 media

IP=$(hostname -I | awk '{print $1}')
FQDN=$(hostname -f)
echo "Server IP : $IP"
echo "Server FQDN: $FQDN"
echo "Server URL (empfohlen): https://$FQDN:8000"
echo "============================================================"

# HTTPS / SSL Zertifikate
# Bevorzugt vorhandene institutseigene Zertifikate (ieekf-web2)
# Kann über Umgebungsvariablen überschrieben werden, z.B. in .env:
#   CERT_FILE=... KEY_FILE=...
INST_CERT="${CERT_FILE:-/etc/ssl/certs/ieekf-web2-cert.pem}"
INST_KEY="${KEY_FILE:-/etc/ssl/private/ieekf-web2-key.pem}"

if [ -r "$INST_CERT" ] && [ -r "$INST_KEY" ]; then
    CERT_FILE="$INST_CERT"
    KEY_FILE="$INST_KEY"
    echo "Verwende vorhandene Zertifikate:"
    echo "  CERT: $CERT_FILE"
    echo "  KEY : $KEY_FILE"
else
    # Fallback: self-signed
    CERT_DIR="certs"
    CERT_FILE="$CERT_DIR/cert.pem"
    KEY_FILE="$CERT_DIR/key.pem"
    mkdir -p "$CERT_DIR"

    if [ ! -f "$CERT_FILE" ] || [ ! -f "$KEY_FILE" ]; then
        echo "Keine lesbaren institutseigenen Zertifikate gefunden (oder keine Leseberechtigung)."
        echo "Erstelle self-signed HTTPS-Zertifikat in $CERT_DIR/ ..."
        openssl req -x509 -nodes -days 3650 -newkey rsa:2048 \
            -keyout "$KEY_FILE" -out "$CERT_FILE" \
            -subj "/C=DE/CN=$IP" 2>/dev/null || echo "Warnung: OpenSSL nicht verfügbar oder Fehler beim Erstellen des Zertifikats"
    else
        echo "Verwende selbst-signierte Zertifikate aus $CERT_DIR/"
    fi
fi

# Prüfe Lesbarkeit der finalen Zertifikate
if [ ! -r "$CERT_FILE" ] || [ ! -r "$KEY_FILE" ]; then
    echo "FEHLER: Kann Zertifikat oder Key nicht lesen: $CERT_FILE / $KEY_FILE"
    echo "Tipp:  sudo usermod -aG ssl-cert therese   # dann neu einloggen"
    exit 1
fi

export DJANGO_SETTINGS_MODULE=therese.settings.base
export PYTHONUNBUFFERED=1

echo "Führe Datenbank-Migrationen aus..."
python manage.py migrate --noinput

echo "Stelle Gruppen + Berechtigungen sicher (auch bei 'No migrations to apply')..."
python -c '
import os, django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "therese.settings.base")
django.setup()
from apps.accounts.permissions import get_or_create_default_groups, assign_permissions_to_groups
get_or_create_default_groups()
assign_permissions_to_groups()
print("  [Groups] Gruppen und Berechtigungen sind aktuell.")
' 2>&1 || echo "  [WARN] Konnte Gruppen-Setup nicht ausführen"

echo "Sammle statische Dateien (collectstatic)..."
python manage.py collectstatic --noinput

# URL files aktualisieren
echo "https://$FQDN:8000" > current_demo_url.txt
echo "https://$FQDN:8000/admin" > current_admin_url.txt

echo "============================================================"
echo "Starte Gunicorn (Produktion mit HTTPS)..."
echo "  → Server läuft unter https://$FQDN:8000 (HTTPS)"
echo "  → Empfohlene Zugriffs-URL: https://$FQDN:8000"
echo "  → (alternativ IP: https://$IP:8000 – aber nur wenn im Zertifikat enthalten)"
echo "  → Verwendetes Zertifikat: $CERT_FILE"
echo "  → Wichtige Logs:"
echo "      tail -f logs/error.log"
echo "      tail -f logs/access.log"
echo "  → Zum Stoppen: Strg + C"
if [[ "$CERT_FILE" == *certs/cert.pem ]]; then
    echo "  → Hinweis: Selbst-signiertes Zertifikat – Browser-Warnung akzeptieren."
else
    echo "  → Hinweis: Institutszertifikat – CA ggf. im Browser installieren für 'sicher'."
fi
echo "============================================================"

gunicorn therese.wsgi:application \
    --name therese_prod \
    --workers 3 \
    --threads 2 \
    --bind 0.0.0.0:8000 \
    --certfile "$CERT_FILE" \
    --keyfile "$KEY_FILE" \
    --log-level info \
    --log-file logs/gunicorn.log \
    --access-logfile logs/access.log \
    --error-logfile - \
    --capture-output
