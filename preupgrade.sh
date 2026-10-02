#!/bin/bash
# Läuft als Benutzer "loxberry" als allererster Schritt eines Upgrades.
# Danach löscht der LoxBerry-Installer die Plugin-Ordner (inkl. config/ und data/).
# Konfiguration, Zugangsdaten und Sendungsliste werden daher gesichert und in
# postupgrade.sh zurückgespielt.
# Argumente: <TEMPFILE> <NAME> <FOLDER> <VERSION> <LBHOMEDIR> <TEMPFOLDER>
PTEMPFILE=$1
PDIR=$3
LBHOMEDIR=${5:-$LBHOMEDIR}

BACKUP="/tmp/${PTEMPFILE}_upgrade"
umask 077

echo "<INFO> Sichere Konfiguration und Daten nach $BACKUP"
mkdir -p "$BACKUP/config" "$BACKUP/data" || { echo "<FAIL> Backup-Ordner nicht anlegbar"; exit 2; }
if [ -d "$LBHOMEDIR/config/plugins/$PDIR" ]; then
    cp -p -r "$LBHOMEDIR/config/plugins/$PDIR/." "$BACKUP/config/" || { echo "<FAIL> Sicherung der Konfiguration fehlgeschlagen"; exit 2; }
fi
if [ -d "$LBHOMEDIR/data/plugins/$PDIR" ]; then
    cp -p -r "$LBHOMEDIR/data/plugins/$PDIR/." "$BACKUP/data/" || echo "<WARNING> Sicherung der Daten unvollständig"
fi

echo "<OK> Sicherung abgeschlossen"
exit 0
