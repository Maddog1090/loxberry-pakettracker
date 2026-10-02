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

$host = $_SERVER['HTTP_HOST'] ?? 'loxberry';
$replacements = [
    '{{BASE_TOPIC}}' => pt_h($describe['values']['mqtt']['base_topic'] ?? 'pakettracker'),
    '{{API_URL}}'    => pt_h("http://$host/plugins/" . LBPPLUGINDIR . '/api.php'),
    '{{VERSION}}'    => pt_h($describe['version'] ?? ''),
    '{{MOCK}}'       => !empty($describe['values']['general']['mock_mode'])
        ? '<span class="pt-badge">' . pt_h($L['STATUS.MOCK_ACTIVE']) . '</span>' : '',
];
$content = is_readable($file) ? (string)file_get_contents($file) : '';

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
