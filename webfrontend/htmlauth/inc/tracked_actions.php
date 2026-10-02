<?php
/**
 * POST-Aktionen für manuell erfasste Sendungsnummern (data/tracked.json).
 * Wird aus index.php eingebunden; $describe, $L und $messages sind gesetzt.
 */

$tracked = pt_read_json(pt_path('tracked'));
$provider_ids = ['auto'];
foreach ($describe['sections'] as $section) {
    if (isset($section['provider_id'])) {
        $provider_ids[] = $section['provider_id'];
    }
}

if ($_POST['action'] === 'add_tracking') {
    $number = strtoupper(preg_replace('/[\s-]+/', '', (string)($_POST['tracking_number'] ?? '')));
    $provider = (string)($_POST['provider'] ?? 'auto');
    $description = mb_substr(trim((string)($_POST['description'] ?? '')), 0, 100);

    if (!preg_match('/^[A-Z0-9-]{6,40}$/', $number) || !in_array($provider, $provider_ids, true)) {
        $messages[] = ['error', $L['SHIPMENTS.INVALID']];
    } elseif (in_array($number, array_column($tracked, 'tracking_number'), true)) {
        $messages[] = ['error', $L['SHIPMENTS.DUPLICATE']];
    } else {
        $note = '';
        if ($provider === 'auto') {
            // Erkennung durch das Backend; das Ergebnis wird fest gespeichert, damit sich die
            // Zuordnung nicht ändert, wenn später weitere Anbieter aktiviert werden.
            $detected = pt_backend_json(['detect', $number], 20);
            $names = array_column($detected['candidates'] ?? [], 'name');
            if (empty($detected['best'])) {
                $messages[] = ['error', $L['SHIPMENTS.UNKNOWN_PROVIDER']];
                return;
            }
            $provider = (string)$detected['best'];
            $note = ' ' . sprintf($L['SHIPMENTS.DETECTED'], $names[0] ?? $provider);
            if (!empty($detected['ambiguous'])) {
                $note .= ' ' . sprintf($L['SHIPMENTS.AMBIGUOUS'], implode(', ', array_slice($names, 1)));
            }
        }
        $tracked[] = ['provider' => $provider, 'tracking_number' => $number, 'description' => $description];
        $ok = pt_write_json(pt_path('tracked'), $tracked);
        $messages[] = $ok ? [!empty($detected['ambiguous']) ? 'error' : 'ok', $L['SHIPMENTS.ADDED'] . $note]
                          : ['error', $L['COMMON.SAVE_FAILED']];
    }
} else {
    $number = (string)($_POST['tracking_number'] ?? '');
    $tracked = array_values(array_filter($tracked, function ($e) use ($number) {
        return ($e['tracking_number'] ?? '') !== $number;
    }));
    $ok = pt_write_json(pt_path('tracked'), $tracked);
    $messages[] = $ok ? ['ok', $L['SHIPMENTS.REMOVED']] : ['error', $L['COMMON.SAVE_FAILED']];
}
