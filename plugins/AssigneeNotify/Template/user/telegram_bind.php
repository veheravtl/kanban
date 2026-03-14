<div class="page-header">
    <h2><?= t('Telegram binding') ?></h2>
</div>

<?php if (!empty($error)): ?>
    <p class="alert alert-error"><?= $this->text->e($error) ?></p>
<?php endif ?>

<?php
$isBound = $binding !== null && isset($binding['is_active']) && (int)$binding['is_active'] === 1;
$chatId = $binding !== null && isset($binding['telegram_chat_id']) ? (string)$binding['telegram_chat_id'] : '';
$generatedCode = isset($generated_code) ? (string)$generated_code : '';
$generatedExpiresAt = isset($generated_expires_at) ? (string)$generated_expires_at : '';
?>

<?php if ($isBound): ?>
    <p class="alert alert-success">
        <?= t('Current status: bound') ?>.
        <?= t('Chat id:') ?> <strong><?= $this->text->e($chatId) ?></strong>
    </p>
<?php else: ?>
    <p class="alert"><?= t('Current status: not bound') ?></p>
<?php endif ?>

<div class="panel">
    <p><strong><?= t('How to bind') ?></strong></p>
    <ol>
        <li><?= t('Click "Generate bind code" below.') ?></li>
        <li><?= t('Open your Telegram bot and send: /bind <code>') ?></li>
        <li><?= t('After success, click "Send test message".') ?></li>
    </ol>
</div>

<?php if ($generatedCode !== ''): ?>
    <p class="alert alert-success">
        <?= t('Bind code generated:') ?> <strong><?= $this->text->e($generatedCode) ?></strong><br>
        <?= t('Send to bot:') ?> <code>/bind <?= $this->text->e($generatedCode) ?></code><br>
        <?php if ($generatedExpiresAt !== ''): ?>
            <?= t('Expires at:') ?> <strong><?= $this->text->e($generatedExpiresAt) ?></strong>
        <?php endif ?>
    </p>
<?php endif ?>

<form method="post" action="<?= $this->url->href('TelegramSelfBindController', 'createCode', array('plugin' => 'AssigneeNotify', 'user_id' => (int)$user['id'])) ?>" autocomplete="off" class="form-inline">
    <?= $this->form->csrf() ?>
    <button type="submit" class="btn btn-blue"><?= t('Generate bind code') ?></button>
</form>

<form method="post" action="<?= $this->url->href('TelegramSelfBindController', 'test', array('plugin' => 'AssigneeNotify', 'user_id' => (int)$user['id'])) ?>" autocomplete="off" class="form-inline margin-top">
    <?= $this->form->csrf() ?>
    <button type="submit" class="btn"><?= t('Send test message') ?></button>
</form>

<p class="margin-top">
    <small><?= t('Unbind is performed by administrator only.') ?></small>
</p>
