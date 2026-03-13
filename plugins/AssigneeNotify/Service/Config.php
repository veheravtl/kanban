<?php

namespace Kanboard\Plugin\AssigneeNotify\Service;

class Config
{
    private $pluginDir;
    private $defaults;

    public function __construct($pluginDir)
    {
        $this->pluginDir = rtrim((string)$pluginDir, DIRECTORY_SEPARATOR);
        $defaultsPath = $this->pluginDir . '/config/defaults.php';
        $this->defaults = file_exists($defaultsPath) ? require $defaultsPath : array();
    }

    public function getBotServiceUrl()
    {
        $value = $this->readString(
            'ASSIGNEE_NOTIFY_BOT_SERVICE_URL',
            'bot_service_url',
            ''
        );

        return rtrim($value, '/');
    }

    public function getSharedSecret()
    {
        return $this->readString(
            'ASSIGNEE_NOTIFY_SHARED_SECRET',
            'shared_secret',
            ''
        );
    }

    public function getEventsDbPath()
    {
        $value = $this->readString(
            'ASSIGNEE_NOTIFY_EVENTS_DB_PATH',
            'events_db_path',
            ''
        );

        if ($value !== '') {
            return $value;
        }

        if (defined('DATA_DIR') && DATA_DIR) {
            return DATA_DIR . DIRECTORY_SEPARATOR . 'assignee_notify.sqlite';
        }

        return $this->pluginDir . DIRECTORY_SEPARATOR . 'assignee_notify.sqlite';
    }

    public function getHttpTimeoutSec()
    {
        return $this->readInt(
            'ASSIGNEE_NOTIFY_HTTP_TIMEOUT_SEC',
            'http_timeout_sec',
            5
        );
    }

    public function getResponseSnippetLimit()
    {
        return $this->readInt(
            'ASSIGNEE_NOTIFY_RESPONSE_SNIPPET_LIMIT',
            'response_snippet_limit',
            400
        );
    }

    private function readString($envKey, $defaultKey, $fallback)
    {
        if (defined($envKey) && constant($envKey) !== '') {
            return (string)constant($envKey);
        }

        $envValue = getenv($envKey);
        if ($envValue !== false && trim((string)$envValue) !== '') {
            return trim((string)$envValue);
        }

        if (array_key_exists($defaultKey, $this->defaults)) {
            return trim((string)$this->defaults[$defaultKey]);
        }

        return $fallback;
    }

    private function readInt($envKey, $defaultKey, $fallback)
    {
        $raw = $this->readString($envKey, $defaultKey, (string)$fallback);
        if ($raw === '') {
            return $fallback;
        }

        $value = (int)$raw;
        if ($value <= 0) {
            return $fallback;
        }

        return $value;
    }
}
