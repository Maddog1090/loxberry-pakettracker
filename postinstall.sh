#!/bin/bash
# Läuft als Benutzer "loxberry", nachdem alle Plugin-Dateien kopiert und die
# Pakete aus dpkg/apt installiert wurden (bei Upgrades VOR postupgrade.sh).
# Argumente: <TEMPFILE> <NAME> <FOLDER> <VERSION> <LBHOMEDIR> <TEMPFOLDER>
# Exit 0 = ok, 1 = Warnung, 2 = Installation abbrechen
PDIR=$3
PVERSION=$4
LBHOMEDIR=${5:-$LBHOMEDIR}

PBIN="$LBHOMEDIR/bin/plugins/$PDIR"

echo "<INFO> Initialisiere Konfiguration (credentials.json mit 0600, REST-Token)"
if ! python3 "$PBIN/pakettracker.py" init; then
    echo "<ERROR> Initialisierung fehlgeschlagen – siehe Ausgabe oben"
    exit 1
fi

# MQTT ist optional: ein fehlendes Modul oder ein fehlender Broker
# verhindert die Installation nicht, sondern wird nur gemeldet.
if python3 -c 'import paho.mqtt.client' 2>/dev/null; then
    echo "<OK> python3-paho-mqtt ist installiert"
else
    echo "<WARNING> python3-paho-mqtt fehlt – MQTT-Ausgabe ist deaktiviert, bis das Paket installiert ist (apt install python3-paho-mqtt)"
fi

echo "<OK> Pakettracker $PVERSION installiert (Neuinstallationen starten im Testmodus)"
exit 0
