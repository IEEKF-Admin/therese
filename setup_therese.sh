#!/bin/bash
# setup_therese.sh — Ersteinrichtung für THERESE auf Linux (frischer Clone/Deploy)
#
# Verwendung:
#   chmod +x setup_therese.sh
#   ./setup_therese.sh              # Standard (Produktion: therese.settings.base)
#   ./setup_therese.sh --dev        # Entwicklung (therese.settings)
#   ./setup_therese.sh --demo       # Zusaetzlich Demo-Benutzer anlegen
#   ./setup_therese.sh --with-media-import  # Legacy-Dateien aus media/ importieren
#
# Voraussetzungen (nur bei MariaDB/MySQL):
#   Debian/Ubuntu: sudo apt install python3-venv python3-dev build-essential \
#                  default-libmysqlclient-dev pkg-config

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

USE_DEV_SETTINGS=false
WITH_DEMO=false
WITH_MEDIA_IMPORT=false

for arg in "$@"; do
    case "$arg" in
        --dev) USE_DEV_SETTINGS=true ;;
        --demo) WITH_DEMO=true ;;
        --with-media-import) WITH_MEDIA_IMPORT=true ;;
        -h|--help)
            echo "Verwendung: $0 [--dev] [--demo] [--with-media-import]"
            exit 0
            ;;
        *)
            echo "Unbekanntes Argument: $arg (nutze --help)"
            exit 1
            ;;
    esac
done

echo "============================================================"
echo "  THERESE — Ersteinrichtung (Linux)"
echo "============================================================"
echo "  Projekt: $(pwd)"
echo ""

# --- Python ---
if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN=python3
elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN=python
else
    echo "FEHLER: Python 3 nicht gefunden. Bitte python3 installieren."
    exit 1
fi

PY_VERSION=$("$PYTHON_BIN" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
PY_MAJOR=$("$PYTHON_BIN" -c 'import sys; print(sys.version_info.major)')
PY_MINOR=$("$PYTHON_BIN" -c 'import sys; print(sys.version_info.minor)')
if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 10 ]; }; then
    echo "FEHLER: Python 3.10+ erforderlich (gefunden: $PY_VERSION)"
    exit 1
fi
echo "[OK] Python $("$PYTHON_BIN" --version 2>&1 | head -1)"

# --- Virtuelle Umgebung ---
VENV_DIR="${VENV_DIR:-$SCRIPT_DIR/venv}"
if [ -x "$VENV_DIR/bin/python" ]; then
    PYTHON="$VENV_DIR/bin/python"
    echo "[OK] Virtuelle Umgebung: $VENV_DIR"
else
    echo "[..] Erstelle virtuelle Umgebung in $VENV_DIR ..."
    "$PYTHON_BIN" -m venv "$VENV_DIR"
    PYTHON="$VENV_DIR/bin/python"
    echo "[OK] Virtuelle Umgebung erstellt"
fi

echo "[..] Aktualisiere pip ..."
"$PYTHON" -m pip install --upgrade pip

echo "[..] Installiere Abhängigkeiten (requirements.txt) ..."
if ! "$PYTHON" -m pip install -r requirements.txt; then
    echo ""
    echo "HINWEIS: Installation fehlgeschlagen — bei MariaDB/MySQL fehlen evtl. Systempakete:"
    echo "  sudo apt install python3-dev build-essential default-libmysqlclient-dev pkg-config"
    exit 1
fi
echo "[OK] Python-Pakete installiert"

# --- .env ---
if [ -f .env ]; then
    echo "[OK] .env vorhanden"
else
    echo "[..] Erstelle .env aus Vorlage ..."
    "$PYTHON" create_env_template.py
    echo "[OK] .env erstellt — bitte bei Produktion SECRET_KEY und DB_* prüfen"
fi

set -a
# shellcheck disable=SC1091
[ -f .env ] && . .env
set +a

# --- Verzeichnisse ---
mkdir -p logs media staticfiles
chmod 755 logs media 2>/dev/null || true
echo "[OK] Verzeichnisse logs/, media/, staticfiles/"

# --- Django Settings ---
if [ "$USE_DEV_SETTINGS" = true ]; then
    export DJANGO_SETTINGS_MODULE=therese.settings
    echo "[OK] Settings: therese.settings (Entwicklung)"
else
    export DJANGO_SETTINGS_MODULE=therese.settings.base
    echo "[OK] Settings: therese.settings.base (Produktion)"
fi
export PYTHONUNBUFFERED=1

# --- Datenbank & Django-Setup ---
echo ""
echo "[..] Django Systemprüfung ..."
"$PYTHON" manage.py check

echo "[..] Datenbank-Migrationen ..."
"$PYTHON" manage.py migrate --noinput

echo "[..] Gruppen und Berechtigungen ..."
"$PYTHON" manage.py ensure_groups

echo "[..] Statische Dateien sammeln (collectstatic) ..."
"$PYTHON" manage.py collectstatic --noinput

# Legacy-Medien importieren (optional)
if [ "$WITH_MEDIA_IMPORT" = true ]; then
    echo "[..] Importiere Legacy-Dateien aus media/ ..."
    "$PYTHON" manage.py import_media_to_database
elif [ -d media ] && [ -n "$(find media -type f 2>/dev/null | head -1)" ]; then
    echo "[..] Dateien in media/ gefunden — importiere in Datenbank-Speicher ..."
    "$PYTHON" manage.py import_media_to_database
else
    echo "[OK] Kein Legacy-Medienimport nötig"
fi

# Demo-Benutzer
if [ "$WITH_DEMO" = true ]; then
    echo "[..] Erstelle Demo-Benutzer ..."
    DJANGO_SETTINGS_MODULE="$DJANGO_SETTINGS_MODULE" "$PYTHON" create_demo_users.py
    echo "[OK] Demo-Benutzer erstellt"
fi

# Produktions-Check
if [ "$USE_DEV_SETTINGS" = false ]; then
    echo ""
    echo "[..] Deployment-Pruefung ..."
    "$PYTHON" manage.py check --deploy 2>&1 || echo "  [WARN] Deployment-Pruefung meldet Hinweise (bei DEBUG=True normal)"
fi

echo ""
echo "[..] Admin-Benutzer anlegen (createsuperuser) ..."
set +e
"$PYTHON" manage.py createsuperuser
CREATE_SU_EXIT=$?
set -e
if [ "$CREATE_SU_EXIT" -ne 0 ]; then
    echo "  [HINWEIS] Superuser-Erstellung abgebrochen oder fehlgeschlagen."
fi

echo ""
echo "============================================================"
echo "  Ersteinrichtung abgeschlossen"
echo "============================================================"
echo ""
echo "Naechster Schritt - Server starten:"
if [ "$USE_DEV_SETTINGS" = true ]; then
    echo "       $PYTHON manage.py runserver 0.0.0.0:8000"
else
    echo "       ./start_therese_prod.sh"
fi
echo ""
if [ ! -f .env ] || grep -q 'change-me' .env 2>/dev/null; then
    echo "  Hinweis: .env prüfen (SECRET_KEY, DB_HOST, ALLOWED_HOSTS)"
    echo ""
fi
echo "Erneut ausführen ist sicher (Migrationen, Gruppen, collectstatic sind idempotent)."
echo "============================================================"