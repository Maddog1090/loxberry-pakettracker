<?php
/**
 * REST/HTTP-Schnittstelle (ohne LoxBerry-Login erreichbar, daher Token-geschützt).
 *
 *   /plugins/pakettracker/api.php?q=summary|slots|slot|shipments|all [&n=1] [&format=json|text] &token=…
 *
 * format=text liefert "schluessel=wert"-Zeilen – ideal für virtuelle HTTP-Eingänge
 * in Loxone (Befehlserkennung z.B. "summary.active=\v").
 */
require_once "loxberry_system.php";
require_once LBPHTMLAUTHDIR . "/inc/common.php";

function pt_respond(int $code, $payload, string $format): void
{
    http_response_code($code);
    header('Cache-Control: no-store');
    if ($format === 'text') {
        header('Content-Type: text/plain; charset=utf-8');
        echo is_array($payload) ? pt_flatten($payload) : $payload . "\n";
    } else {
        header('Content-Type: application/json; charset=utf-8');
        echo json_encode(is_array($payload) ? $payload : ['error' => $payload], JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
    }
    exit;
}

function pt_flatten(array $data, string $prefix = ''): string
{
    $out = '';
    foreach ($data as $key => $value) {
        $name = $prefix === '' ? (string)$key : "$prefix.$key";
        if (is_array($value)) {
            $out .= pt_flatten($value, $name);
        } else {
            $out .= $name . '=' . (is_bool($value) ? (int)$value : str_replace(["\r", "\n"], ' ', (string)$value)) . "\n";
        }
    }
    return $out;
}

$format = ($_GET['format'] ?? 'json') === 'text' ? 'text' : 'json';
$settings = pt_read_json(pt_path('settings'));
$rest = $settings['rest'] ?? [];

if (!($rest['enabled'] ?? true)) {
    pt_respond(404, 'REST-Schnittstelle deaktiviert', $format);
}
if ($rest['require_token'] ?? true) {
    $token = (string)(pt_read_json(pt_path('credentials'))['rest']['token'] ?? '');
    if ($token === '') {
        pt_respond(503, 'Kein Token konfiguriert', $format);
    }
    if (!hash_equals($token, (string)($_GET['token'] ?? ''))) {
        pt_respond(403, 'Ungültiger Token', $format);
    }
}

$state = pt_read_json(pt_path('state'), null);
if ($state === null) {
    pt_respond(503, 'Noch keine Daten vorhanden', $format);
}

$meta = ['updated' => $state['updated'], 'updated_epoch' => $state['updated_epoch'], 'mock_mode' => $state['mock_mode']];
switch ($_GET['q'] ?? 'summary') {
    case 'summary':
        pt_respond(200, $meta + ['summary' => $state['summary'], 'providers' => $state['providers']], $format);
    case 'slots':
        pt_respond(200, $meta + ['slots' => $state['slots']], $format);
    case 'slot':
        $n = (int)($_GET['n'] ?? 1);
        $slot = $state['slots'][$n - 1] ?? null;
        $slot === null ? pt_respond(404, 'Slot nicht vorhanden', $format) : pt_respond(200, $slot, $format);
    case 'shipments':
        pt_respond(200, $meta + ['shipments' => $state['shipments']], $format);
    case 'all':
        pt_respond(200, $state, $format);
    default:
        pt_respond(400, 'Unbekannte Abfrage', $format);
}
