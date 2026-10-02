<?php
require_once "loxberry_system.php";
require_once "loxberry_web.php";
require_once __DIR__ . "/inc/common.php";

$L = LBSystem::readlanguage("language.ini");
pt_csrf_token();  // Session vor jeder Ausgabe starten

$pages = [
    'status'    => $L['NAV.STATUS'],
    'shipments' => $L['NAV.SHIPMENTS'],
    'settings'  => $L['NAV.SETTINGS'],
    'providers' => $L['NAV.PROVIDERS'],
    'help'      => $L['NAV.HELP'],
];
$page = $_GET['page'] ?? 'status';
if (!isset($pages[$page])) {
    $page = 'status';
}

$messages = [];   // [Typ ('ok'|'error'), Text]
$run_output = null;

try {
    $describe = pt_describe();
} catch (RuntimeException $e) {
    $describe = null;
    $messages[] = ['error', $L['COMMON.BACKEND_ERROR']];
}

if ($_SERVER['REQUEST_METHOD'] === 'POST' && $describe !== null) {
    if (!pt_csrf_valid()) {
        $messages[] = ['error', $L['COMMON.CSRF_ERROR']];
    } else {
        $action = (string)($_POST['action'] ?? '');
        $test_target = '';
        if (strpos($action, 'test:') === 0) {
            // "Speichern & testen" bzw. reiner Test (Anbieter-Seite)
            $test_target = substr($action, 5);
            $action = 'test';
        }
        switch ($action) {
            case 'test':
                if ($test_target !== 'imap' && !isset(pt_providers($describe)[$test_target])) {
                    break;
                }
                if (!empty($_POST['f']) && !pt_save_sections($describe, $_POST['f'])) {
                    $messages[] = ['error', $L['COMMON.SAVE_FAILED']];
                    break;
                }
                $describe = pt_describe();
                $result = pt_backend_json(['test', $test_target], 90);
                $name = $test_target === 'imap' ? 'IMAP' : pt_providers($describe)[$test_target]['title'];
                $messages[] = [!empty($result['ok']) ? 'ok' : 'error',
                    sprintf($L['SETTINGS.TEST_RESULT'], $name, (string)($result['message'] ?? ''))];
                break;
            case 'save':
                $ok = pt_save_sections($describe, $_POST['f'] ?? []);
                $messages[] = $ok ? ['ok', $L['COMMON.SAVED']] : ['error', $L['COMMON.SAVE_FAILED']];
                $describe = pt_describe();
                break;
            case 'run':
                [$rc, $run_output] = pt_backend(['run', '--force', '--verbose'], 180);
                $messages[] = $rc === 0 ? ['ok', $L['STATUS.RUN_OK']] : ['error', $L['STATUS.RUN_FAILED']];
                break;
            case 'add_tracking':
            case 'remove_tracking':
                require __DIR__ . '/inc/tracked_actions.php';
                break;
        }
    }
}

$i = 1;
foreach ($pages as $id => $name) {
    $navbar[$i] = ['Name' => $name, 'URL' => "index.php?page=$id", 'active' => $id === $page];
    $i++;
}

LBWeb::lbheader($L['COMMON.TITLE'] . " " . LBSystem::pluginversion(), "", "help.html");
?>
<style>
    .pt-hint { font-size: 0.85em; color: #777; margin: -0.4em 0 1em 0; }
    .pt-msg { padding: 0.6em 1em; border-radius: 4px; margin-bottom: 1em; }
    .pt-msg.ok { background: #e6f4ea; color: #1e5631; }
    .pt-msg.error { background: #fdecea; color: #8a1c1c; }
    .pt-table { width: 100%; border-collapse: collapse; }
    .pt-table th, .pt-table td { text-align: left; padding: 0.35em 0.5em; border-bottom: 1px solid #ddd; }
    .pt-log { max-height: 24em; overflow: auto; background: #222; color: #ddd; padding: 0.8em; font-size: 0.8em; white-space: pre-wrap; }
    .pt-badge { display: inline-block; padding: 0.1em 0.5em; border-radius: 3px; background: #f0ad4e; color: #fff; }
    .pt-health { display: inline-block; padding: 0.1em 0.5em; border-radius: 3px; font-size: 0.85em; color: #fff; }
    .pt-health-ok { background: #3c8d40; }
    .pt-health-error { background: #c0392b; }
    .pt-health-warn { background: #e08e0b; }
    .pt-health-idle { background: #888; }
    .pt-error-text { color: #c0392b; font-size: 0.85em; }
    .pt-guide { margin: 0.5em 0 1.5em 0; }
    .pt-guide .ui-btn { font-size: 1.1em; }
</style>
<?php
foreach ($messages as [$type, $text]) {
    echo '<div class="pt-msg ' . pt_h($type) . '">' . pt_h($text) . '</div>';
}
if ($describe !== null) {
    require __DIR__ . "/inc/page_$page.php";
}
LBWeb::lbfooter();
