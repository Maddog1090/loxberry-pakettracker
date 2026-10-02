#!/bin/bash
# Läuft als Benutzer "loxberry" VOR dem Kopieren der Plugin-Dateien.
# Argumente: <TEMPFILE> <NAME> <FOLDER> <VERSION> <LBHOMEDIR> <TEMPFOLDER>
# Exit 0 = ok, 1 = Warnung, 2 = Installation abbrechen

if ! command -v python3 >/dev/null 2>&1; then
    echo "<FAIL> python3 wurde nicht gefunden."
    exit 2
fi

if ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)'; then
    echo "<FAIL> Python >= 3.9 wird benötigt, gefunden: $(python3 --version 2>&1)"
    exit 2
fi

echo "<OK> $(python3 --version 2>&1) gefunden"
exit 0
