<?php

namespace Kanboard\Plugin\AutoPdf;

use Kanboard\Core\Plugin\Base;
use Kanboard\Model\TaskFileModel;
use PDO;
use Throwable;

class Plugin extends Base
{
    private const SUPPORTED_EXTENSIONS = array('doc', 'docx', 'xls', 'xlsx', 'xlsm');

    private const SCHEMA_SQL = <<<'SQL'
CREATE TABLE IF NOT EXISTS conversion_queue (
    id INTEGER PRIMARY KEY,
    file_id INTEGER NOT NULL UNIQUE,
    task_id INTEGER NOT NULL,
    project_id INTEGER,
    original_name TEXT NOT NULL,
    target_name TEXT NOT NULL,
    status TEXT NOT NULL,
    retry_count INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_conversion_queue_status_id
    ON conversion_queue(status, id);
SQL;

    public function initialize()
    {
        $this->container['dispatcher']->addListener(
            TaskFileModel::EVENT_CREATE,
            array($this, 'onTaskFileCreate')
        );
    }

    public function onTaskFileCreate($event)
    {
        try {
            $payload = $this->extractPayload($event);
            $file = $this->readArrayField($payload, 'file');
            $task = $this->readArrayField($payload, 'task');

            $fileId = (int)($file['id'] ?? 0);
            $taskId = (int)($file['task_id'] ?? $task['id'] ?? 0);
            $projectId = $this->nullableInt($task['project_id'] ?? $file['project_id'] ?? null);
            $originalName = (string)($file['name'] ?? $file['filename'] ?? '');

            if ($fileId <= 0 || $taskId <= 0 || $originalName === '') {
                $this->container['logger']->warning(sprintf(
                    '[AutoPdf] Skip enqueue: invalid payload (file_id=%s, task_id=%s, name=%s)',
                    (string)$fileId,
                    (string)$taskId,
                    $originalName
                ));
                return;
            }

            if (!$this->isSupportedOfficeFile($originalName)) {
                return;
            }

            $targetName = $this->buildTargetName($originalName, $fileId);
            $queuePath = $this->getQueueDatabasePath();
            $pdo = $this->openQueueDatabase($queuePath);

            $now = gmdate('c');
            $stmt = $pdo->prepare(
                'INSERT OR IGNORE INTO conversion_queue
                (file_id, task_id, project_id, original_name, target_name, status, retry_count, created_at, updated_at)
                VALUES (:file_id, :task_id, :project_id, :original_name, :target_name, :status, 0, :created_at, :updated_at)'
            );

            $stmt->bindValue(':file_id', $fileId, PDO::PARAM_INT);
            $stmt->bindValue(':task_id', $taskId, PDO::PARAM_INT);
            if ($projectId === null) {
                $stmt->bindValue(':project_id', null, PDO::PARAM_NULL);
            } else {
                $stmt->bindValue(':project_id', $projectId, PDO::PARAM_INT);
            }
            $stmt->bindValue(':original_name', $originalName, PDO::PARAM_STR);
            $stmt->bindValue(':target_name', $targetName, PDO::PARAM_STR);
            $stmt->bindValue(':status', 'pending', PDO::PARAM_STR);
            $stmt->bindValue(':created_at', $now, PDO::PARAM_STR);
            $stmt->bindValue(':updated_at', $now, PDO::PARAM_STR);
            $stmt->execute();

            if ($stmt->rowCount() > 0) {
                $this->container['logger']->info(sprintf(
                    '[AutoPdf] Enqueued file_id=%d task_id=%d source=%s',
                    $fileId,
                    $taskId,
                    $originalName
                ));
            }
        } catch (Throwable $e) {
            $this->container['logger']->error(sprintf(
                '[AutoPdf] Enqueue error: %s',
                $e->getMessage()
            ));
        }
    }

    public function getPluginName()
    {
        return 'AutoPdf';
    }

    public function getPluginDescription()
    {
        return 'Queues Office task attachments for async PDF conversion by external worker';
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

    private function extractPayload($event)
    {
        if (is_array($event)) {
            return $event;
        }

        if (is_object($event)) {
            if (method_exists($event, 'getAll')) {
                $all = $event->getAll();
                if (is_array($all)) {
                    return $all;
                }
            }

            if (method_exists($event, 'getArguments')) {
                $all = $event->getArguments();
                if (is_array($all)) {
                    return $all;
                }
            }
        }

        return array();
    }

    private function readArrayField(array $payload, $key)
    {
        if (!isset($payload[$key]) || !is_array($payload[$key])) {
            return array();
        }

        return $payload[$key];
    }

    private function nullableInt($value)
    {
        if ($value === null || $value === '') {
            return null;
        }

        return (int)$value;
    }

    private function isSupportedOfficeFile($filename)
    {
        $extension = strtolower(pathinfo($filename, PATHINFO_EXTENSION));
        return in_array($extension, self::SUPPORTED_EXTENSIONS, true);
    }

    private function buildTargetName($originalName, $fileId)
    {
        $baseName = pathinfo($originalName, PATHINFO_FILENAME);
        if ($baseName === '' || $baseName === '.') {
            $baseName = 'file_' . (string)$fileId;
        }

        return $baseName . '.pdf';
    }

    private function getQueueDatabasePath()
    {
        if (defined('AUTOPDF_QUEUE_DB') && AUTOPDF_QUEUE_DB) {
            return AUTOPDF_QUEUE_DB;
        }

        $env = getenv('AUTOPDF_QUEUE_DB');
        if ($env !== false && $env !== '') {
            return $env;
        }

        return DATA_DIR . DIRECTORY_SEPARATOR . 'autopdf_queue.sqlite';
    }

    private function openQueueDatabase($queuePath)
    {
        $directory = dirname($queuePath);
        if (!is_dir($directory)) {
            mkdir($directory, 0775, true);
        }

        $pdo = new PDO('sqlite:' . $queuePath);
        $pdo->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);
        $pdo->setAttribute(PDO::ATTR_DEFAULT_FETCH_MODE, PDO::FETCH_ASSOC);
        $pdo->exec('PRAGMA journal_mode = WAL');
        $pdo->exec('PRAGMA busy_timeout = 5000');
        $pdo->exec(self::SCHEMA_SQL);

        return $pdo;
    }
}
