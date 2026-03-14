<?php

namespace Kanboard\Plugin\AssigneeNotify;

require_once __DIR__ . '/Service/Config.php';
require_once __DIR__ . '/Service/EventPayloadExtractor.php';
require_once __DIR__ . '/Service/AssigneeChangeComparator.php';
require_once __DIR__ . '/Service/BotServiceClient.php';
require_once __DIR__ . '/Service/BotServiceBindingsClient.php';
require_once __DIR__ . '/Service/AssigneeChangeHandler.php';
require_once __DIR__ . '/Service/SubtaskAssigneeChangeHook.php';
require_once __DIR__ . '/Model/NotificationEventStore.php';

use Kanboard\Core\Plugin\Base;
use Kanboard\Plugin\AssigneeNotify\Model\NotificationEventStore;
use Kanboard\Plugin\AssigneeNotify\Service\AssigneeChangeComparator;
use Kanboard\Plugin\AssigneeNotify\Service\AssigneeChangeHandler;
use Kanboard\Plugin\AssigneeNotify\Service\BotServiceClient;
use Kanboard\Plugin\AssigneeNotify\Service\Config;
use Kanboard\Plugin\AssigneeNotify\Service\EventPayloadExtractor;
use Kanboard\Plugin\AssigneeNotify\Service\SubtaskAssigneeChangeHook;
use Throwable;

class Plugin extends Base
{
    public function initialize()
    {
        try {
            $config = new Config(__DIR__);
            $store = new NotificationEventStore(
                $config->getEventsDbPath(),
                __DIR__ . '/Schema/notification_events.sql'
            );
            $store->initSchema();

            $handler = new AssigneeChangeHandler(
                new EventPayloadExtractor(),
                new AssigneeChangeComparator(),
                $store,
                new BotServiceClient(
                    $config->getBotServiceUrl(),
                    $config->getSharedSecret(),
                    $config->getHttpTimeoutSec(),
                    $config->getResponseSnippetLimit()
                ),
                $this->container['logger']
            );

            $subtaskHook = new SubtaskAssigneeChangeHook(
                new AssigneeChangeComparator(),
                $store,
                new BotServiceClient(
                    $config->getBotServiceUrl(),
                    $config->getSharedSecret(),
                    $config->getHttpTimeoutSec(),
                    $config->getResponseSnippetLimit()
                ),
                $this->container['subtaskModel'],
                $this->container['logger']
            );

            $events = $this->resolveUpdateEvents();
            foreach ($events as $eventName) {
                $this->container['dispatcher']->addListener($eventName, array($handler, 'handle'));
            }

            $this->hook->on('model:subtask:modification:prepare', array($subtaskHook, 'handle'));
            $this->template->hook->attach('template:config:sidebar', 'assigneeNotify:config/sidebar');
            $this->template->hook->attach('template:user:sidebar:actions', 'assigneeNotify:user/sidebar');

            $this->container['logger']->info(sprintf(
                '[AssigneeNotify] Initialized. Listening on events: %s; hooks: model:subtask:modification:prepare, template:config:sidebar, template:user:sidebar:actions',
                implode(', ', $events)
            ));
        } catch (Throwable $e) {
            $this->container['logger']->error(sprintf(
                '[AssigneeNotify] Initialization failed: %s',
                $e->getMessage()
            ));
        }
    }

    public function getPluginName()
    {
        return 'AssigneeNotify';
    }

    public function getPluginDescription()
    {
        return 'Tracks task assignee changes and forwards anonymized notifications to external bot-service';
    }

    public function getPluginAuthor()
    {
        return 'Local Integration';
    }

    public function getPluginVersion()
    {
        return '0.1.0';
    }

    public function getCompatibleVersion()
    {
        return '>=1.2.37';
    }

    private function resolveUpdateEvents()
    {
        $events = array(
            'task.update',
            'task.assignee_change',
        );

        $constantCandidates = array(
            'Kanboard\\Model\\TaskModel::EVENT_UPDATE',
            'Kanboard\\Model\\TaskModel::EVENT_ASSIGNEE_CHANGE',
            'Kanboard\\Model\\TaskModificationModel::EVENT_UPDATE',
        );

        foreach ($constantCandidates as $constantName) {
            if (defined($constantName)) {
                $value = constant($constantName);
                if (is_string($value) && $value !== '') {
                    $events[] = $value;
                }
            }
        }

        return array_values(array_unique($events));
    }
}
