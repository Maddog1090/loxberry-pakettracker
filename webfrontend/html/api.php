<?php
/**
 * REST/HTTP-Schnittstelle (ohne LoxBerry-Login erreichbar, daher Token-geschützt, nur lesend).
 *
 *   /plugins/pakettracker/api.php?q=summary|slots|slot|shipments|all [&n=1] [&field=…] [&format=json|text] &token=…
 *
 * format=text ohne field liefert "schluessel=wert"-Zeilen (Befehlserkennung in Loxone z.B. "summary.active=\v").
 * Mit field kommt genau ein Wert – für Loxone ohne JSON-Auswertung:
 *   api.php?q=summary&field=active&format=text         → 2
 *   api.php?q=slot&n=1&field=description&format=text   → Druckerpatronen
 *
 * Antwortcodes: 200 OK · 400 unbekannte Abfrage/unbekanntes Feld/ungültiger Slot · 403 REST aus oder Token
 * falsch · 404 Slot nicht vorhanden (nur ohne field, wie bis 0.2.2) · 405 nicht GET · 503 keine Daten/kein Token.
 * Der Token wird nie geloggt oder ausgegeben.
 */

// Loxone darf nie PHP-Warnungen oder HTML-Fehlerseiten erhalten: Fehler nicht anzeigen,
// alle Ausgaben puffern und bei einem fatalen Fehler eine schlichte 500-Antwort senden.
ini_set('display_errors', '0');
ini_set('html_errors', '0');
ob_start();
register_shutdown_function(function () {
    $error = error_get_last();
    if ($error !== null && in_array($error['type'], [E_ERROR, E_PARSE, E_CORE_ERROR, E_COMPILE_ERROR], true)) {
        while (ob_get_level() > 0) {
            ob_end_clean();
        }
        if (!headers_sent()) {
            http_response_code(500);
            header('Content-Type: text/plain; charset=utf-8');
            header('Cache-Control: no-store');
        }
        echo "Interner Fehler\n";
    }
});

require_once "loxberry_system.php";
require_once LBPHTMLAUTHDIR . "/inc/common.php";

function pt_respond(int $code, $payload, string $format): void
{
    while (ob_get_level() > 0) {
        ob_end_clean();
    }
    http_response_code($code);
    header('Cache-Control: no-store');
    header('X-Content-Type-Options: nosniff');
    if ($code === 405) {
        header('Allow: GET, HEAD');
    }
    if ($format === 'text') {
        header('Content-Type: text/plain; charset=utf-8');
        echo is_array($payload) ? pt_flatten($payload) : pt_plain($payload) . "\n";
    } else {
        header('Content-Type: application/json; charset=utf-8');
        echo json_encode(is_array($payload) ? $payload : ['error' => $payload],
            JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES | JSON_INVALID_UTF8_SUBSTITUTE);
    }
    exit;
}

/**
 * Ein Wert als Klartext für Loxone: gültiges UTF-8, HTML-Entities aufgelöst (auch doppelt
 * kodierte wie "&amp;#x20;"), Zeilenumbrüche/Steuerzeichen/Sonderleerzeichen zu einem Leerzeichen,
 * ohne führende und nachgestellte Leerzeichen. Wahrheitswerte als 1/0.
 */
function pt_plain($value): string
{
    if (is_bool($value)) {
        return $value ? '1' : '0';
    }
    if ($value === null || is_array($value)) {
        return '';
    }
    $text = (string)$value;
    if (!mb_check_encoding($text, 'UTF-8')) {
        $text = mb_convert_encoding($text, 'UTF-8', 'UTF-8');
    }
    for ($i = 0; $i < 3 && strpos($text, '&') !== false; $i++) {
        $decoded = html_entity_decode($text, ENT_QUOTES | ENT_HTML5, 'UTF-8');
        if ($decoded === $text) {
            break;
        }
        $text = $decoded;
    }
    $text = preg_replace('/[\p{Cc}\p{Z}\x{00AD}\x{200B}-\x{200D}\x{2060}\x{FEFF}]+/u', ' ', $text);
    return trim((string)$text, ' ');
}

function pt_flatten(array $data, string $prefix = ''): string
{
    $out = '';
    foreach ($data as $key => $value) {
        $name = $prefix === '' ? (string)$key : "$prefix.$key";
        if (is_array($value)) {
            $out .= pt_flatten($value, $name);
        } else {
            $out .= $name . '=' . pt_plain($value) . "\n";
        }
    }
    return $out;
}

/** GET-Parameter als String (Arrays wie q[]=… gelten als nicht gesetzt). */
function pt_param(string $name, string $default = ''): string
{
    $value = $_GET[$name] ?? $default;
    return is_string($value) ? $value : $default;
}

/** Einzelwert aus einem Datensatz; unbekannte oder zusammengesetzte Felder → 400. */
function pt_field_value(array $record, string $field, string $format)
{
    if (!preg_match('/^[a-z_]{1,40}$/', $field) || !array_key_exists($field, $record) || is_array($record[$field])) {
        pt_respond(400, 'Unbekanntes Feld', $format);
    }
    return $record[$field];
}

function pt_respond_field(array $context, $value, string $format): void
{
    pt_respond(200, $format === 'text' ? pt_plain($value) : $context + ['value' => $value], $format);
}

$format = pt_param('format', 'json') === 'text' ? 'text' : 'json';
if (!in_array($_SERVER['REQUEST_METHOD'] ?? 'GET', ['GET', 'HEAD'], true)) {
    pt_respond(405, 'Nur GET erlaubt', $format);
}

$settings = pt_read_json(pt_path('settings'));
$rest = $settings['rest'] ?? [];

if (!($rest['enabled'] ?? true)) {
    pt_respond(403, 'REST-Schnittstelle deaktiviert', $format);
}
if ($rest['require_token'] ?? true) {
    $token = (string)(pt_read_json(pt_path('credentials'))['rest']['token'] ?? '');
    if ($token === '') {
        pt_respond(503, 'Kein Token konfiguriert', $format);
    }
    if (!hash_equals($token, pt_param('token'))) {
        pt_respond(403, 'Ungültiger Token', $format);
    }
}

$state = pt_read_json(pt_path('state'), null);
if ($state === null) {
    pt_respond(503, 'Noch keine Daten vorhanden', $format);
}

$field = pt_param('field');
$meta = ['updated' => $state['updated'] ?? '', 'updated_epoch' => $state['updated_epoch'] ?? 0,
         'mock_mode' => $state['mock_mode'] ?? false];
switch ($q = pt_param('q', 'summary')) {
    case 'summary':
        if ($field !== '') {
            pt_respond_field(['q' => $q, 'field' => $field],
                pt_field_value($state['summary'] ?? [], $field, $format), $format);
        }
        pt_respond(200, $meta + ['summary' => $state['summary'] ?? [], 'providers' => $state['providers'] ?? []], $format);
    case 'slots':
        pt_respond(200, $meta + ['slots' => $state['slots'] ?? []], $format);
    case 'slot':
        $slots = $state['slots'] ?? [];
        if ($field !== '') {
            $n = filter_var(pt_param('n', '1'), FILTER_VALIDATE_INT, ['options' => ['min_range' => 1]]);
            if ($n === false || !isset($slots[$n - 1]) || !is_array($slots[$n - 1])) {
                pt_respond(400, 'Ungültiger Slot', $format);
            }
            pt_respond_field(['q' => $q, 'n' => $n, 'field' => $field],
                pt_field_value($slots[$n - 1], $field, $format), $format);
        }
        $slot = $slots[(int)pt_param('n', '1') - 1] ?? null;
        $slot === null ? pt_respond(404, 'Slot nicht vorhanden', $format) : pt_respond(200, $slot, $format);
    case 'shipments':
        pt_respond(200, $meta + ['shipments' => $state['shipments'] ?? []], $format);
    case 'all':
        pt_respond(200, $state, $format);
    default:
        pt_respond(400, 'Unbekannte Abfrage', $format);
}
