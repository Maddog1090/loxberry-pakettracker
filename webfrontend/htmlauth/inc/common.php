<?php
/**
 * Gemeinsame Helfer für Weboberfläche (index.php) und REST-API (api.php).
 * Voraussetzung: loxberry_system.php ist bereits eingebunden (definiert die
 * Konstanten LBPCONFIGDIR, LBPDATADIR, LBPLOGDIR, LBPBINDIR, LBPHTMLAUTHDIR).
 *
 * Aufgabenteilung: Das Python-Backend liefert Schema und aktuelle Werte
 * (`pakettracker.py describe`); PHP rendert daraus die Formulare und schreibt
 * settings.json bzw. credentials.json. Geheimnisse gehen nie an den Browser.
 */

function pt_path(string $name): string
{
    $map = [
        'settings'    => LBPCONFIGDIR . '/settings.json',
        'credentials' => LBPCONFIGDIR . '/credentials.json',
        'tracked'     => LBPDATADIR . '/tracked.json',
        'state'       => LBPDATADIR . '/state.json',
        'log'         => LBPLOGDIR . '/pakettracker.log',
        'backend'     => LBPBINDIR . '/pakettracker.py',
    ];
    if (!isset($map[$name])) {
        throw new InvalidArgumentException("Unbekannter Pfad: $name");
    }
    return $map[$name];
}

function pt_h($value): string
{
    return htmlspecialchars((string)$value, ENT_QUOTES, 'UTF-8');
}

function pt_read_json(string $file, $default = [])
{
    if (!is_readable($file)) {
        return $default;
    }
    $data = json_decode((string)file_get_contents($file), true);
    return is_array($data) ? $data : $default;
}

/** Atomar schreiben (temp-Datei + rename). */
function pt_write_json(string $file, $data, int $mode = 0644): bool
{
    $json = json_encode($data, JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
    $tmp = tempnam(dirname($file), '.pt');
    if ($json === false || $tmp === false) {
        return false;
    }
    if (file_put_contents($tmp, $json . "\n") === false || !chmod($tmp, $mode) || !rename($tmp, $file)) {
        @unlink($tmp);
        return false;
    }
    return true;
}

/** Ruft das Python-Backend auf. Liefert [Exit-Code, Ausgabe]. */
function pt_backend(array $args, int $timeout = 60, bool $with_stderr = true): array
{
    $cmd = 'timeout ' . $timeout . ' /usr/bin/python3 ' . escapeshellarg(pt_path('backend'));
    foreach ($args as $arg) {
        $cmd .= ' ' . escapeshellarg($arg);
    }
    $cmd .= $with_stderr ? ' 2>&1' : ' 2>/dev/null';
    exec($cmd, $out, $rc);
    return [$rc, implode("\n", $out)];
}

/** Backend-Befehl mit JSON-Ausgabe (detect, test). Fehler werden als ['ok' => false] gemeldet. */
function pt_backend_json(array $args, int $timeout = 60): array
{
    [$rc, $out] = pt_backend($args, $timeout, false);
    $data = json_decode($out, true);
    return is_array($data) ? $data : ['ok' => false, 'message' => "Backend lieferte keine gültige Antwort (rc=$rc)"];
}

/** Provider-Abschnitte aus describe, nach Provider-ID. */
function pt_providers(array $describe): array
{
    $providers = [];
    foreach ($describe['sections'] as $section) {
        if (isset($section['provider_id'])) {
            $providers[$section['provider_id']] = $section;
        }
    }
    return $providers;
}

function pt_fmt_time($iso): string
{
    $ts = $iso ? strtotime((string)$iso) : false;
    return $ts ? date('d.m.Y H:i', $ts) : '–';
}

/** Zugangsdatenstatus aus describe (Geheimnisse selbst kommen nie im Browser an). */
function pt_credentials_status(array $section, array $describe): string
{
    $required = $section['required_secrets'] ?? [];
    if (!$required) {
        return 'none';
    }
    foreach ($required as $key) {
        if (empty($describe['secrets_set'][$section['id']][$key])) {
            return 'missing';
        }
    }
    return 'ok';
}

function pt_label(array $L, string $key, string $fallback = ''): string
{
    return $L[$key] ?? ($fallback !== '' ? $fallback : $key);
}

function pt_health_badge(string $health, array $L): string
{
    $class = ['ok' => 'ok', 'error' => 'error', 'email_only' => 'warn', 'no_source' => 'warn'][$health] ?? 'idle';
    return '<span class="pt-health pt-health-' . $class . '">'
        . pt_h(pt_label($L, 'HEALTH.' . strtoupper($health), $health)) . '</span>';
}

function pt_describe(): array
{
    [$rc, $out] = pt_backend(['describe'], 20, false);
    $data = json_decode($out, true);
    if ($rc !== 0 || !is_array($data)) {
        throw new RuntimeException("describe fehlgeschlagen (rc=$rc)");
    }
    return $data;
}

/* --- CSRF ---------------------------------------------------------------- */

function pt_csrf_token(): string
{
    if (session_status() !== PHP_SESSION_ACTIVE) {
        session_start();
    }
    if (empty($_SESSION['pt_csrf'])) {
        $_SESSION['pt_csrf'] = bin2hex(random_bytes(16));
    }
    return $_SESSION['pt_csrf'];
}

function pt_csrf_valid(): bool
{
    return hash_equals(pt_csrf_token(), (string)($_POST['csrf'] ?? ''));
}

function pt_csrf_field(): string
{
    return '<input type="hidden" name="csrf" value="' . pt_h(pt_csrf_token()) . '">';
}

/* --- Einstellungen speichern --------------------------------------------- */

/** Setzt $data[a][b][key] für Section-ID "a.b". */
function pt_set(array &$data, string $section_id, string $key, $value): void
{
    $ref = &$data;
    foreach (explode('.', $section_id) as $part) {
        if (!isset($ref[$part]) || !is_array($ref[$part])) {
            $ref[$part] = [];
        }
        $ref = &$ref[$part];
    }
    $ref[$key] = $value;
}

function pt_coerce(array $field, $raw)
{
    switch ($field['type']) {
        case 'bool':
            return in_array($raw, ['1', 'on', 'true'], true);
        case 'int':
            $value = filter_var($raw, FILTER_VALIDATE_INT);
            if ($value === false) {
                $value = (int)$field['default'];
            }
            if ($field['min'] !== null) {
                $value = max($field['min'], $value);
            }
            if ($field['max'] !== null) {
                $value = min($field['max'], $value);
            }
            return $value;
        case 'select':
            return in_array($raw, $field['options'], true) ? $raw : $field['default'];
        default:
            return mb_substr(trim((string)$raw), 0, 255);
    }
}

/**
 * Übernimmt die per POST gesendeten Abschnitte (f[<section>][<key>]).
 * Leere Geheimnis-Felder bedeuten "unverändert lassen".
 */
function pt_save_sections(array $describe, array $posted): bool
{
    $settings = pt_read_json(pt_path('settings'));
    $secrets = pt_read_json(pt_path('credentials'));

    foreach ($describe['sections'] as $section) {
        $sid = $section['id'];
        if (!isset($posted[$sid]) || !is_array($posted[$sid])) {
            continue;
        }
        $in = $posted[$sid];
        foreach ($section['fields'] as $field) {
            $key = $field['key'];
            $raw = $in[$key] ?? null;
            if ($field['secret']) {
                if (!empty($in['__clear'][$key])) {
                    pt_set($secrets, $sid, $key, '');
                } elseif (is_string($raw) && trim($raw) !== '') {
                    pt_set($secrets, $sid, $key, trim($raw));
                }
                continue;
            }
            pt_set($settings, $sid, $key, pt_coerce($field, $raw));
        }
    }

    return pt_write_json(pt_path('settings'), $settings)
        && pt_write_json(pt_path('credentials'), $secrets, 0600);
}

/* --- Formular-Rendering --------------------------------------------------- */

function pt_render_field(string $sid, array $field, array $describe, array $L): string
{
    $key = $field['key'];
    $name = 'f[' . $sid . '][' . $key . ']';
    $id = 'f_' . preg_replace('/\W/', '_', $sid . '_' . $key);
    $value = $describe['values'][$sid][$key] ?? $field['default'];
    $label = '<label for="' . $id . '">' . pt_h($field['label']) . '</label>';
    $help = $field['help'] !== '' ? '<p class="pt-hint">' . pt_h($field['help']) . '</p>' : '';

    switch (true) {
        case $field['type'] === 'bool':
            $input = '<input type="hidden" name="' . pt_h($name) . '" value="0">'
                . '<input type="checkbox" data-role="flipswitch" id="' . $id . '" name="' . pt_h($name) . '" value="1"'
                . ($value ? ' checked' : '') . '>';
            break;
        case $field['type'] === 'select':
            $input = '<select id="' . $id . '" name="' . pt_h($name) . '">';
            foreach ($field['options'] as $opt) {
                $input .= '<option value="' . pt_h($opt) . '"' . ($opt === $value ? ' selected' : '') . '>'
                    . pt_h($opt) . '</option>';
            }
            $input .= '</select>';
            break;
        case $field['secret'] && !$field['reveal']:
            $is_set = !empty($describe['secrets_set'][$sid][$key]);
            $input = '<input type="password" autocomplete="new-password" id="' . $id . '" name="' . pt_h($name) . '" value=""'
                . ' placeholder="' . pt_h($is_set ? $L['SETTINGS.SECRET_SET'] : $L['SETTINGS.SECRET_UNSET']) . '">';
            if ($is_set) {
                $input .= '<label><input type="checkbox" name="f[' . pt_h($sid) . '][__clear][' . pt_h($key) . ']" value="1">'
                    . pt_h($L['SETTINGS.SECRET_CLEAR']) . '</label>';
            }
            break;
        case $field['type'] === 'int':
            $input = '<input type="number" id="' . $id . '" name="' . pt_h($name) . '" value="' . pt_h($value) . '"'
                . ($field['min'] !== null ? ' min="' . (int)$field['min'] . '"' : '')
                . ($field['max'] !== null ? ' max="' . (int)$field['max'] . '"' : '') . '>';
            break;
        default:
            $input = '<input type="text" id="' . $id . '" name="' . pt_h($name) . '" value="' . pt_h($value) . '">';
    }
    return '<div class="ui-field-contain">' . $label . $input . '</div>' . $help;
}

function pt_render_section(array $section, array $describe, array $L, bool $with_title = true): string
{
    $html = $with_title ? '<h3>' . pt_h($section['title']) . '</h3>' : '';
    foreach ($section['fields'] as $field) {
        $html .= pt_render_field($section['id'], $field, $describe, $L);
    }
    return $html;
}

function pt_tail(string $file, int $lines = 60): string
{
    if (!is_readable($file)) {
        return '';
    }
    $all = file($file, FILE_IGNORE_NEW_LINES) ?: [];
    return implode("\n", array_slice($all, -$lines));
}
