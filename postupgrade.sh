#!/bin/bash
# Läuft als Benutzer "loxberry" als letzter Schritt eines Upgrades (nach postinstall.sh).
# Spielt die in preupgrade.sh gesicherten Dateien zurück.
# Argumente: <TEMPFILE> <NAME> <FOLDER> <VERSION> <LBHOMEDIR> <TEMPFOLDER>
PTEMPFILE=$1
PDIR=$3
LBHOMEDIR=${5:-$LBHOMEDIR}

BACKUP="/tmp/${PTEMPFILE}_upgrade"

if [ ! -d "$BACKUP" ]; then
    echo "<WARNING> Keine Sicherung gefunden ($BACKUP) – Standardeinstellungen bleiben aktiv"
    exit 1
fi

echo "<INFO> Stelle Konfiguration und Daten wieder her"
cp -p -r "$BACKUP/config/." "$LBHOMEDIR/config/plugins/$PDIR/"
cp -p -r "$BACKUP/data/." "$LBHOMEDIR/data/plugins/$PDIR/"
rm -rf "$BACKUP"

# Neue Pflichtwerte ergänzen und Dateirechte von credentials.json sicherstellen
python3 "$LBHOMEDIR/bin/plugins/$PDIR/pakettracker.py" init || echo "<WARNING> Nachinitialisierung fehlgeschlagen"

echo "<OK> Konfiguration wiederhergestellt"
exit 0
