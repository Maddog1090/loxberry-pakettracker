<?php
/** Statusseite: Zusammenfassung, Slots, manueller Lauf, Log. */

$state = pt_read_json(pt_path('state'));
$summary = $state['summary'] ?? [];
?>
<h2><?= pt_h($L['STATUS.HEADING']) ?></h2>

<?php if (!empty($describe['values']['general']['mock_mode'])): ?>
    <p><span class="pt-badge"><?= pt_h($L['STATUS.MOCK_ACTIVE']) ?></span></p>
<?php endif; ?>

<p><?= pt_h($L['STATUS.LAST_UPDATE']) ?>:
    <strong><?= pt_h(isset($state['updated']) ? date('d.m.Y H:i:s', strtotime($state['updated'])) : $L['STATUS.NEVER']) ?></strong>
    <?php if (!empty($state['errors'])): ?>
        – <span class="pt-error-text"><?= pt_h(sprintf($L['STATUS.RUN_ERRORS'], (int)$state['errors'])) ?></span>
    <?php endif; ?>
    <br><?= pt_h($L['STATUS.LAST_FULL_SUCCESS']) ?>: <strong><?= pt_h(pt_fmt_time($state['last_full_success'] ?? '')) ?></strong>
</p>

<form method="post" action="index.php?page=status" data-ajax="false">
    <?= pt_csrf_field() ?>
    <input type="hidden" name="action" value="run">
    <button type="submit" class="ui-btn ui-btn-inline ui-icon-refresh ui-btn-icon-left"><?= pt_h($L['STATUS.RUN_NOW']) ?></button>
</form>

<?php if ($run_output !== null): ?>
    <h3><?= pt_h($L['STATUS.RUN_OUTPUT']) ?></h3>
    <div class="pt-log"><?= pt_h($run_output) ?></div>
<?php endif; ?>

<h3><?= pt_h($L['STATUS.SUMMARY']) ?></h3>
<table class="pt-table">
    <?php foreach ($summary as $key => $value): ?>
        <tr>
            <th><?= pt_h($L['SUMMARY.' . strtoupper($key)] ?? $key) ?></th>
            <td><?= pt_h($value) ?></td>
        </tr>
    <?php endforeach; ?>
</table>

<h3><?= pt_h($L['STATUS.PROVIDER_HEALTH']) ?></h3>
<table class="pt-table">
    <tr><th><?= pt_h($L['SHIPMENTS.PROVIDER']) ?></th><th><?= pt_h($L['PROVIDERS.HEALTH']) ?></th>
        <th><?= pt_h($L['PROVIDERS.SHIPMENTS']) ?></th><th><?= pt_h($L['PROVIDERS.LAST_SUCCESS']) ?></th>
        <th><?= pt_h($L['PROVIDERS.LAST_ERROR']) ?></th></tr>
    <?php $titles = array_map(function ($s) { return $s['title']; }, pt_providers($describe)); ?>
    <?php foreach ($state['providers'] ?? [] as $id => $p): ?>
        <tr>
            <td><?= pt_h($titles[$id] ?? $id) ?></td>
            <td><?= pt_health_badge((string)($p['health'] ?? 'idle'), $L) ?></td>
            <td><?= (int)($p['active'] ?? 0) ?> / <?= (int)($p['shipment_count'] ?? 0) ?></td>
            <td><?= pt_h(pt_fmt_time($p['last_success'] ?? '')) ?></td>
            <td class="pt-error-text"><?= pt_h($p['error'] ?? '') ?></td>
        </tr>
    <?php endforeach; ?>
    <?php if (!empty($state['email']['enabled'])): ?>
        <tr>
            <td><?= pt_h($L['PROVIDERS.EMAIL_HEADING']) ?></td>
            <td><?= pt_health_badge(!empty($state['email']['error']) ? 'error' : (!empty($state['email']['last_success']) ? 'ok' : 'idle'), $L) ?></td>
            <td></td>
            <td><?= pt_h(pt_fmt_time($state['email']['last_success'] ?? '')) ?></td>
            <td class="pt-error-text"><?= pt_h($state['email']['error'] ?? '') ?></td>
        </tr>
    <?php endif; ?>
</table>
<p class="pt-hint"><?= pt_h($L['PROVIDERS.COUNT_HINT']) ?></p>

<h3><?= pt_h($L['STATUS.SLOTS']) ?></h3>
<table class="pt-table">
    <tr><th>#</th><th><?= pt_h($L['SHIPMENTS.PROVIDER']) ?></th><th><?= pt_h($L['SHIPMENTS.DESCRIPTION']) ?></th>
        <th><?= pt_h($L['SHIPMENTS.STATUS']) ?></th><th><?= pt_h($L['SHIPMENTS.ETA']) ?></th></tr>
    <?php foreach ($state['slots'] ?? [] as $slot): ?>
        <tr>
            <td><?= (int)$slot['slot'] ?></td>
            <td><?= pt_h($slot['provider']) ?></td>
            <td><?= pt_h($slot['description'] ?: $slot['tracking_number']) ?></td>
            <td><?= pt_h($slot['status_label']) ?> <?= $slot['used'] ? '(' . (int)$slot['status_code'] . ')' : '' ?></td>
            <td><?= pt_h(pt_fmt_eta($slot)) ?></td>
        </tr>
    <?php endforeach; ?>
</table>

<h3><?= pt_h($L['STATUS.LOG']) ?></h3>
<?php $log = pt_tail(pt_path('log')); ?>
<div class="pt-log"><?= $log !== '' ? pt_h($log) : pt_h($L['STATUS.NO_LOG']) ?></div>
