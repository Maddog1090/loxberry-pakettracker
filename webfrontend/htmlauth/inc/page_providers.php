<?php
/** Anbieter-Übersicht: Aktivierung, Datenquelle, Zugangsdaten, letzter Abruf/Fehler, Sendungen. */

$state = pt_read_json(pt_path('state'));
$info = $state['providers'] ?? [];
$email = $state['email'] ?? [];
?>
<h2><?= pt_h($L['PROVIDERS.HEADING']) ?></h2>
<p class="pt-hint"><?= pt_h($L['PROVIDERS.OVERVIEW_HINT']) ?></p>

<table class="pt-table">
    <tr>
        <th><?= pt_h($L['SHIPMENTS.PROVIDER']) ?></th>
        <th><?= pt_h($L['PROVIDERS.ENABLED']) ?></th>
        <th><?= pt_h($L['PROVIDERS.SOURCE']) ?></th>
        <th><?= pt_h($L['PROVIDERS.CREDENTIALS']) ?></th>
        <th><?= pt_h($L['PROVIDERS.HEALTH']) ?></th>
        <th><?= pt_h($L['PROVIDERS.LAST_SUCCESS']) ?></th>
        <th><?= pt_h($L['PROVIDERS.LAST_ERROR']) ?></th>
        <th><?= pt_h($L['PROVIDERS.SHIPMENTS']) ?></th>
        <th></th>
    </tr>
    <?php foreach (pt_providers($describe) as $id => $section):
        $enabled = !empty($describe['values'][$section['id']]['enabled']);
        $p = $info[$id] ?? [];
        $cred = pt_credentials_status($section, $describe); ?>
        <tr>
            <td><strong><?= pt_h($section['title']) ?></strong></td>
            <td><?= pt_h($enabled ? $L['COMMON.YES'] : $L['COMMON.NO']) ?></td>
            <td><?= pt_h(pt_label($L, 'SOURCE.' . strtoupper(str_replace('+', '_', $section['data_source'])))) ?></td>
            <td><?= pt_h(pt_label($L, 'CRED.' . strtoupper($cred))) ?></td>
            <td><?= $enabled ? pt_health_badge((string)($p['health'] ?? 'idle'), $L) : pt_health_badge('disabled', $L) ?></td>
            <td><?= pt_h(pt_fmt_time($p['last_success'] ?? '')) ?></td>
            <td class="pt-error-text"><?= pt_h($p['error'] ?? '') ?></td>
            <td><?= (int)($p['active'] ?? 0) ?> / <?= (int)($p['shipment_count'] ?? 0) ?></td>
            <td>
                <?php if ($section['supports_test'] && $enabled): ?>
                    <form method="post" action="index.php?page=providers" data-ajax="false">
                        <?= pt_csrf_field() ?>
                        <button type="submit" name="action" value="test:<?= pt_h($id) ?>"
                                class="ui-btn ui-mini ui-btn-inline"><?= pt_h($L['PROVIDERS.TEST']) ?></button>
                    </form>
                <?php endif; ?>
            </td>
        </tr>
    <?php endforeach; ?>
</table>
<p class="pt-hint"><?= pt_h($L['PROVIDERS.COUNT_HINT']) ?></p>

<h3><?= pt_h($L['PROVIDERS.EMAIL_HEADING']) ?></h3>
<?php if (empty($describe['values']['email']['enabled'])): ?>
    <p><?= pt_h($L['PROVIDERS.EMAIL_OFF']) ?></p>
<?php else: ?>
    <p><?= pt_h($L['PROVIDERS.LAST_SUCCESS']) ?>: <strong><?= pt_h(pt_fmt_time($email['last_success'] ?? '')) ?></strong>
        <?php if (!empty($email['error'])): ?><br><span class="pt-error-text"><?= pt_h($email['error']) ?></span><?php endif; ?></p>
<?php endif; ?>
<p><a href="index.php?page=settings" class="ui-btn ui-btn-inline ui-mini"><?= pt_h($L['PROVIDERS.TO_SETTINGS']) ?></a></p>
