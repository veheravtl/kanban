<li <?= $this->app->checkMenuSelection('TelegramBindingsController', 'index', 'AssigneeNotify') ?>>
    <?= $this->url->link(t('Telegram bindings'), 'TelegramBindingsController', 'index', array('plugin' => 'AssigneeNotify')) ?>
</li>
