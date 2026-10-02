<?php
/**
 * Hilfe: Kurzanleitung aus templates/<sprache>/help_page.html (Fallback Deutsch).
 * Platzhalter {{…}} werden mit aktuellen, HTML-escapten Werten gefüllt.
 */

$lang = preg_replace('/[^a-z]/', '', (string)LBSystem::lblanguage());
$file = LBPTEMPLATEDIR . "/$lang/help_page.html";
if (!is_readable($file)) {
    $file = LBPTEMPLATEDIR . '/de/help_page.html';
}

$api = pt_api_base();
$rest = $describe['values']['rest'] ?? [];
if (!($rest['enabled'] ?? true)) {
    $rest_status = '<p class="pt-msg error">' . pt_h($L['HELP.REST_DISABLED']) . '</p>';
} elseif ($rest['require_token'] ?? true) {
    $rest_status = '<p class="pt-hint">' . pt_h($L['HELP.REST_TOKEN_ON']) . '</p>';
} else {
    $rest_status = '<p class="pt-hint">' . pt_h($L['HELP.REST_TOKEN_OFF']) . '</p>';
}
$replacements = [
    '{{BASE_TOPIC}}'  => pt_h($describe['values']['mqtt']['base_topic'] ?? 'pakettracker'),
    '{{API_URL}}'     => pt_h($api),
    '{{REST_STATUS}}' => $rest_status,
    '{{VERSION}}'     => pt_h($describe['version'] ?? ''),
    '{{MOCK}}'        => !empty($describe['values']['general']['mock_mode'])
        ? '<span class="pt-badge">' . pt_h($L['STATUS.MOCK_ACTIVE']) . '</span>' : '',
];
$content = is_readable($file) ? (string)file_get_contents($file) : '';

// {{REST:slot/1/eta}} → fertige Einzelwert-Adresse (mit Token, falls nötig), {{QUERY:slot/1/eta}} → nur die Abfrage
$content = preg_replace_callback('#\{\{(REST|QUERY):([a-z_]+(?:/\d+)?/[a-z_]+)\}\}#', function ($m) use ($api, $rest) {
    $query = pt_rest_value_query($m[2]);
    if ($m[1] === 'QUERY') {
        return '<code>?' . pt_h($query) . '</code>';
    }
    $url = pt_rest_url($api, $query, $rest);
    return '<a href="' . pt_h($url) . '" target="_blank" rel="noopener" data-ajax="false"><code>' . pt_h($url) . '</code></a>';
}, $content);

// Ausführliche Anleitung: wird mit dem Plugin installiert (webfrontend/htmlauth/anleitung.html,
// erzeugt aus docs/ANLEITUNG_DE.md) und liegt damit neben dieser Seite.
if (is_readable(LBPHTMLAUTHDIR . '/anleitung.html')) {
    $guide = '<p class="pt-guide"><a href="anleitung.html" target="_blank" rel="noopener" data-ajax="false"'
        . ' class="ui-btn ui-btn-inline ui-btn-b ui-corner-all ui-icon-info ui-btn-icon-left">'
        . pt_h($L['HELP.OPEN_GUIDE']) . '</a><br><span class="pt-hint">' . pt_h($L['HELP.GUIDE_HINT']) . '</span></p>';
} else {
    $guide = '<p class="pt-msg error">' . pt_h($L['HELP.GUIDE_MISSING']) . '</p>';
}

// Knopf direkt unter den Einleitungsabsatz setzen
$content = strtr($content, $replacements);
$pos = strpos($content, '</p>');
echo $pos === false ? $guide . $content : substr($content, 0, $pos + 4) . "\n" . $guide . substr($content, $pos + 4);
