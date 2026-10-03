<?php
/** Sendungen: manuell erfasste Nummern verwalten, aktuellen Stand anzeigen. */

$tracked = pt_read_json(pt_path('tracked'));
$state = pt_read_json(pt_path('state'));
$providers = [];
foreach ($describe['sections'] as $section) {
    if (isset($section['provider_id'])) {
        $providers[$section['provider_id']] = $section;
    }
}

function pt_tracking_link(array $providers, string $provider, string $number): string
{
    $template = $providers[$provider]['tracking_url_template'] ?? '';
    if ($template === '') {
        return pt_h($number);
    }
    $url = str_replace('{number}', rawurlencode($number), $template);
    return '<a href="' . pt_h($url) . '" target="_blank" rel="noopener noreferrer">' . pt_h($number) . '</a>';
}
?>
<h2><?= pt_h($L['SHIPMENTS.HEADING']) ?></h2>

<h3><?= pt_h($L['SHIPMENTS.ADD']) ?></h3>
<form method="post" action="index.php?page=shipments" data-ajax="false">
    <?= pt_csrf_field() ?>
    <input type="hidden" name="action" value="add_tracking">
    <div class="ui-field-contain">
        <label for="provider"><?= pt_h($L['SHIPMENTS.PROVIDER']) ?></label>
        <select id="provider" name="provider">
            <option value="auto"><?= pt_h($L['SHIPMENTS.AUTO']) ?></option>
            <?php foreach ($providers as $id => $section): ?>
                <option value="<?= pt_h($id) ?>"><?= pt_h($section['title']) ?><?=
                    empty($describe['values'][$section['id']]['enabled']) ? ' ' . pt_h($L['SHIPMENTS.DISABLED']) : '' ?></option>
            <?php endforeach; ?>
        </select>
    </div>
    <div class="ui-field-contain">
        <label for="tracking_number"><?= pt_h($L['SHIPMENTS.NUMBER']) ?></label>
        <input type="text" id="tracking_number" name="tracking_number" maxlength="40" required>
    </div>
    <div class="ui-field-contain">
        <label for="description"><?= pt_h($L['SHIPMENTS.DESCRIPTION']) ?></label>
        <input type="text" id="description" name="description" maxlength="100">
    </div>
    <button type="submit" class="ui-btn ui-btn-inline ui-icon-plus ui-btn-icon-left"><?= pt_h($L['SHIPMENTS.ADD']) ?></button>
    <p class="pt-hint"><?= pt_h($L['SHIPMENTS.HINT_RUN']) ?> <?= pt_h($L['SHIPMENTS.HINT_MANUAL']) ?></p>
</form>

<h3><?= pt_h($L['SHIPMENTS.TRACKED']) ?></h3>
<?php if (!$tracked): ?>
    <p><?= pt_h($L['SHIPMENTS.NONE_TRACKED']) ?></p>
<?php else: ?>
    <table class="pt-table">
        <?php foreach ($tracked as $entry): ?>
            <tr>
                <td><?= pt_h($entry['provider'] === 'auto' ? $L['SHIPMENTS.AUTO'] : ($providers[$entry['provider']]['title'] ?? $entry['provider'])) ?></td>
                <td><?= pt_h($entry['tracking_number']) ?></td>
                <td><?= pt_h($entry['description'] ?? '') ?></td>
                <td>
                    <form method="post" action="index.php?page=shipments" data-ajax="false">
                        <?= pt_csrf_field() ?>
                        <input type="hidden" name="action" value="remove_tracking">
                        <input type="hidden" name="tracking_number" value="<?= pt_h($entry['tracking_number']) ?>">
                        <button type="submit" class="ui-btn ui-mini ui-btn-inline ui-icon-delete ui-btn-icon-notext"
                                title="<?= pt_h($L['SHIPMENTS.REMOVE']) ?>"><?= pt_h($L['SHIPMENTS.REMOVE']) ?></button>
                    </form>
                </td>
            </tr>
        <?php endforeach; ?>
    </table>
<?php endif; ?>

<?php
/** Tabelle des aktuellen Stands; $rows aus state.json. */
function pt_shipment_table(array $rows, array $providers, array $L): void
{ ?>
    <table class="pt-table">
        <tr><th><?= pt_h($L['SHIPMENTS.PROVIDER']) ?></th><th><?= pt_h($L['SHIPMENTS.NUMBER']) ?></th>
            <th><?= pt_h($L['SHIPMENTS.DESCRIPTION']) ?></th><th><?= pt_h($L['SHIPMENTS.STATUS']) ?></th>
            <th><?= pt_h($L['SHIPMENTS.ETA']) ?></th><th><?= pt_h($L['SHIPMENTS.ORIGIN']) ?></th></tr>
        <?php foreach ($rows as $s): ?>
            <tr>
                <td><?= pt_h($providers[$s['provider']]['title'] ?? $s['provider']) ?></td>
                <td><?= pt_tracking_link($providers, $s['provider'], $s['tracking_number']) ?></td>
                <td><?= pt_h($s['description']) ?></td>
                <td>
                    <?= pt_h($s['status_label']) ?>
                    <?php if (($s['status_text'] ?? '') !== ''): ?>
                        <div class="pt-small"><?= pt_h($s['status_text']) ?></div>
                    <?php endif; ?>
                    <?php if (!empty($s['events'])): ?>
                        <details class="pt-small"><summary><?= pt_h(sprintf($L['SHIPMENTS.EVENTS'], count($s['events']))) ?></summary>
                            <ul class="pt-events">
                                <?php foreach ($s['events'] as $e): ?>
                                    <li><?= pt_h(pt_fmt_time($e['timestamp'] ?? '')) ?> – <?= pt_h($e['description'] ?? '') ?><?= ($e['location'] ?? '') !== '' ? ' (' . pt_h($e['location']) . ')' : '' ?></li>
                                <?php endforeach; ?>
                            </ul>
                        </details>
                    <?php endif; ?>
                </td>
                <td><?= pt_h(pt_fmt_eta($s)) ?>
                    <?php if (($s['eta_text'] ?? '') !== ''): ?><div class="pt-small"><?= pt_h($s['eta_text']) ?></div><?php endif; ?>
                </td>
                <td><?= pt_h(implode(', ', $s['origins'])) ?><?= !empty($s['live_checked']) ? pt_h(' · ' . $L['SHIPMENTS.LIVE']) : '' ?></td>
            </tr>
        <?php endforeach; ?>
    </table>
<?php }

$current = array_values(array_filter($state['shipments'] ?? [], function ($s) { return empty($s['stale']); }));
$stale = array_values(array_filter($state['shipments'] ?? [], function ($s) { return !empty($s['stale']); }));
?>
<h3><?= pt_h($L['SHIPMENTS.CURRENT']) ?></h3>
<?php if (!$current): ?>
    <p><?= pt_h($L['SHIPMENTS.NONE']) ?></p>
<?php else: ?>
    <?php pt_shipment_table($current, $providers, $L); ?>
<?php endif; ?>

<?php if ($stale): ?>
    <h3><?= pt_h($L['SHIPMENTS.STALE_HEADING']) ?></h3>
    <p class="pt-hint"><?= pt_h($L['SHIPMENTS.STALE_HINT']) ?></p>
    <?php pt_shipment_table($stale, $providers, $L); ?>
<?php endif; ?>
