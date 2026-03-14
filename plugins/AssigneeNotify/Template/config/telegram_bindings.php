<div class="page-header">
    <h2><?= t('Telegram bindings') ?></h2>
</div>

<p><?= t('Map Kanboard users to Telegram chat ids and run delivery tests.') ?></p>

<?php if (!empty($list_error)): ?>
    <p class="alert alert-error"><?= $this->text->e($list_error) ?></p>
<?php endif ?>

<?php if (empty($users)): ?>
    <p class="alert"><?= t('There is no active user.') ?></p>
<?php else: ?>
    <table class="table-striped table-scrolling">
        <tr>
            <th class="column-10"><?= t('ID') ?></th>
            <th class="column-25"><?= t('User') ?></th>
            <th class="column-30"><?= t('Telegram chat id') ?></th>
            <th class="column-15"><?= t('Status') ?></th>
            <th class="column-20"><?= t('Action') ?></th>
        </tr>
        <?php foreach ($users as $user): ?>
            <?php
            $userId = (int)$user['id'];
            $binding = isset($bindings_by_user_id[$userId]) ? $bindings_by_user_id[$userId] : null;
            $chatId = $binding && isset($binding['telegram_chat_id']) ? (string)$binding['telegram_chat_id'] : '';
            $isActive = $binding && isset($binding['is_active']) && (int)$binding['is_active'] === 1;
            $status = $binding === null ? t('Not bound') : ($isActive ? t('Active') : t('Inactive'));
            ?>
            <tr>
                <td><?= $userId ?></td>
                <td>
                    <strong><?= $this->text->e($user['username']) ?></strong>
                    <?php if (!empty($user['name'])): ?>
                        <br><small><?= $this->text->e($user['name']) ?></small>
                    <?php endif ?>
                </td>
                <td>
                    <form method="post" action="<?= $this->url->href('TelegramBindingsController', 'upsert', array('plugin' => 'AssigneeNotify')) ?>" autocomplete="off" class="form-inline">
                        <?= $this->form->csrf() ?>
                        <input type="hidden" name="kanboard_user_id" value="<?= $userId ?>">
                        <input type="text" name="telegram_chat_id" value="<?= $this->text->e($chatId) ?>" placeholder="506566433">
                        <button type="submit" class="btn btn-blue"><?= t('Save') ?></button>
                    </form>
                </td>
                <td><?= $status ?></td>
                <td>
                    <form method="post" action="<?= $this->url->href('TelegramBindingsController', 'test', array('plugin' => 'AssigneeNotify')) ?>" autocomplete="off" class="form-inline">
                        <?= $this->form->csrf() ?>
                        <input type="hidden" name="kanboard_user_id" value="<?= $userId ?>">
                        <button type="submit" class="btn"><?= t('Test') ?></button>
                    </form>
                    <form method="post" action="<?= $this->url->href('TelegramBindingsController', 'unbind', array('plugin' => 'AssigneeNotify')) ?>" autocomplete="off" class="form-inline">
                        <?= $this->form->csrf() ?>
                        <input type="hidden" name="kanboard_user_id" value="<?= $userId ?>">
                        <button type="submit" class="btn btn-red"><?= t('Unbind') ?></button>
                    </form>
                </td>
            </tr>
        <?php endforeach ?>
    </table>
<?php endif ?>

<div class="page-header margin-top">
    <h2><?= t('Stale bindings') ?></h2>
</div>

<p><?= t('Bindings linked to inactive or removed users.') ?></p>

<?php if (empty($stale_bindings)): ?>
    <p class="alert alert-success"><?= t('No stale bindings detected.') ?></p>
<?php else: ?>
    <form method="post" action="<?= $this->url->href('TelegramBindingsController', 'cleanupStale', array('plugin' => 'AssigneeNotify')) ?>" autocomplete="off">
        <?= $this->form->csrf() ?>
        <button type="submit" class="btn btn-red"><?= t('Deactivate all stale bindings') ?></button>
    </form>

    <table class="table-striped table-scrolling margin-top">
        <tr>
            <th class="column-10"><?= t('ID') ?></th>
            <th class="column-25"><?= t('User') ?></th>
            <th class="column-25"><?= t('Telegram chat id') ?></th>
            <th class="column-20"><?= t('Reason') ?></th>
            <th class="column-20"><?= t('Action') ?></th>
        </tr>
        <?php foreach ($stale_bindings as $binding): ?>
            <?php
            $userId = (int)$binding['kanboard_user_id'];
            $reason = $binding['reason'] === 'inactive_user'
                ? t('User is inactive')
                : t('User does not exist');
            ?>
            <tr>
                <td><?= $userId ?></td>
                <td>
                    <?php if (!empty($binding['username'])): ?>
                        <strong><?= $this->text->e($binding['username']) ?></strong>
                        <?php if (!empty($binding['name'])): ?>
                            <br><small><?= $this->text->e($binding['name']) ?></small>
                        <?php endif ?>
                    <?php else: ?>
                        <em><?= t('Deleted user') ?></em>
                    <?php endif ?>
                </td>
                <td><?= $this->text->e($binding['telegram_chat_id']) ?></td>
                <td><?= $reason ?></td>
                <td>
                    <form method="post" action="<?= $this->url->href('TelegramBindingsController', 'unbind', array('plugin' => 'AssigneeNotify')) ?>" autocomplete="off" class="form-inline">
                        <?= $this->form->csrf() ?>
                        <input type="hidden" name="kanboard_user_id" value="<?= $userId ?>">
                        <button type="submit" class="btn btn-red"><?= t('Unbind') ?></button>
                    </form>
                </td>
            </tr>
        <?php endforeach ?>
    </table>
<?php endif ?>
