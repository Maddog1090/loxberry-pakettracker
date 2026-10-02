<?php
/** Einstellungen: Allgemein, MQTT, REST, E-Mail-Eingang (mit Test) und alle Anbieter (mit Test). */

$api = pt_api_base();
$base = $describe['values']['mqtt']['base_topic'] ?? 'pakettracker';
$providers = pt_providers($describe);
?>
<h2><?= pt_h($L['SETTINGS.HEADING']) ?></h2>
<p class="pt-hint"><?= pt_h($L['SETTINGS.SECRETS_HINT']) ?></p>

<form method="post" action="index.php?page=settings" data-ajax="false" autocomplete="off">
    <?= pt_csrf_field() ?>
    <?php foreach ($describe['sections'] as $section) {
        if (isset($section['provider_id'])) {
            continue;
        }
        echo pt_render_section($section, $describe, $L);
        if ($section['id'] === 'email') {
            echo '<button type="submit" name="action" value="test:imap" class="ui-btn ui-btn-inline ui-mini ui-icon-mail ui-btn-icon-left">'
                . pt_h($L['SETTINGS.TEST_IMAP']) . '</button>';
        }
    } ?>

    <h3><?= pt_h($L['SETTINGS.PROVIDERS']) ?></h3>
    <p class="pt-hint"><?= pt_h($L['PROVIDERS.HINT']) ?></p>
    <?php foreach ($providers as $id => $section):
        $cred = pt_credentials_status($section, $describe);
        $enabled = !empty($describe['values'][$section['id']]['enabled']); ?>
        <div data-role="collapsible" data-collapsed="true">
            <h4><?= pt_h($section['title']) ?> –
                <?= pt_h($enabled ? pt_label($L, 'SOURCE.' . strtoupper(str_replace('+', '_', $section['data_source']))) : $L['HEALTH.DISABLED']) ?>
                <?= $cred === 'missing' && $enabled ? ' – ' . pt_h($L['CRED.MISSING']) : '' ?></h4>
            <?= pt_render_section($section, $describe, $L, false) ?>
            <p class="pt-hint"><?= pt_h($section['live_tracking'] ? $L['PROVIDERS.LIVE'] : $L['PROVIDERS.EMAIL_ONLY']) ?></p>
            <?php if ($section['supports_test']): ?>
                <button type="submit" name="action" value="test:<?= pt_h($id) ?>"
                        class="ui-btn ui-btn-inline ui-mini ui-icon-check ui-btn-icon-left"><?= pt_h($L['SETTINGS.TEST_PROVIDER']) ?></button>
                <?php if ($id === 'dhl'): ?><span class="pt-hint"><?= pt_h($L['SETTINGS.TEST_DHL_QUOTA']) ?></span><?php endif; ?>
            <?php endif; ?>
        </div>
    <?php endforeach; ?>

    <button type="submit" name="action" value="save" class="ui-btn ui-btn-inline ui-icon-check ui-btn-icon-left"><?= pt_h($L['COMMON.SAVE']) ?></button>
</form>

<h3><?= pt_h($L['SETTINGS.MQTT_TOPICS']) ?></h3>
<table class="pt-table">
    <tr><td><code><?= pt_h($base) ?>/summary/active</code></td><td><?= pt_h($L['SUMMARY.ACTIVE']) ?></td></tr>
    <tr><td><code><?= pt_h($base) ?>/summary/out_for_delivery</code></td><td><?= pt_h($L['SUMMARY.OUT_FOR_DELIVERY']) ?></td></tr>
    <tr><td><code><?= pt_h($base) ?>/summary/delivered_today</code></td><td><?= pt_h($L['SUMMARY.DELIVERED_TODAY']) ?></td></tr>
    <tr><td><code><?= pt_h($base) ?>/provider/&lt;id&gt;/active</code></td><td><?= pt_h($L['SETTINGS.TOPIC_PROVIDER']) ?></td></tr>
    <tr><td><code><?= pt_h($base) ?>/provider/&lt;id&gt;/shipment_count</code></td><td><?= pt_h($L['SETTINGS.TOPIC_PROVIDER_COUNT']) ?></td></tr>
    <tr><td><code><?= pt_h($base) ?>/provider/&lt;id&gt;/error</code></td><td><?= pt_h($L['SETTINGS.TOPIC_PROVIDER_ERROR']) ?></td></tr>
    <tr><td><code><?= pt_h($base) ?>/provider/&lt;id&gt;/last_success</code></td><td><?= pt_h($L['SETTINGS.TOPIC_PROVIDER_SUCCESS']) ?></td></tr>
    <tr><td><code><?= pt_h($base) ?>/slot/&lt;n&gt;/status_code</code></td><td><?= pt_h($L['SETTINGS.TOPIC_SLOT']) ?></td></tr>
</table>

<h3><?= pt_h($L['SETTINGS.REST_EXAMPLES']) ?></h3>
<ul>
    <?php foreach (['q=summary&format=text', 'q=slot&n=1&format=text', 'q=summary&field=active&format=text',
                    'q=slot&n=1&field=description&format=text', 'q=all'] as $q): ?>
        <?php $url = pt_rest_url($api, $q, $describe['values']['rest'] ?? []); ?>
        <li><a href="<?= pt_h($url) ?>" target="_blank" rel="noopener"><code><?= pt_h($url) ?></code></a></li>
    <?php endforeach; ?>
</ul>
