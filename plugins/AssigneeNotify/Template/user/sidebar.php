<?php if ($this->user->isCurrentUser((int)$user['id'])): ?>
    <li <?= $this->app->checkMenuSelection('TelegramSelfBindController', 'index', 'AssigneeNotify') ?>>
        <?= $this->url->link(
            t('Telegram binding'),
            'TelegramSelfBindController',
            'index',
            array(
                'plugin' => 'AssigneeNotify',
                'user_id' => (int)$user['id'],
            )
        ) ?>
    </li>
<?php endif ?>
