<?php

namespace Kanboard\Plugin\AssigneeNotify\Model;

use PDO;

class NotificationEventStore
{
    private $dbPath;
    private $schemaPath;

    public function __construct($dbPath, $schemaPath)
    {
        $this->dbPath = (string)$dbPath;
        $this->schemaPath = (string)$schemaPath;
    }

    public function initSchema()
    {
        $schemaSql = file_get_contents($this->schemaPath);
        if ($schemaSql === false) {
            throw new \RuntimeException('Unable to read schema file: ' . $this->schemaPath);
        }

        $pdo = $this->openConnection();
        $pdo->exec($schemaSql);
    }

    public function createEvent($eventUuid, $eventType, $taskId, $oldAssignee, $newAssignee, $deliveryStatus, $createdAt)
    {
        $pdo = $this->openConnection();
        $stmt = $pdo->prepare(
            'INSERT INTO notification_events
            (event_uuid, event_type, task_id, old_assignee_user_id, new_assignee_user_id, created_at, delivery_status)
            VALUES (:event_uuid, :event_type, :task_id, :old_assignee, :new_assignee, :created_at, :delivery_status)'
        );

        $stmt->bindValue(':event_uuid', (string)$eventUuid, PDO::PARAM_STR);
        $stmt->bindValue(':event_type', (string)$eventType, PDO::PARAM_STR);
        $stmt->bindValue(':task_id', (int)$taskId, PDO::PARAM_INT);

        if ($oldAssignee === null) {
            $stmt->bindValue(':old_assignee', null, PDO::PARAM_NULL);
        } else {
            $stmt->bindValue(':old_assignee', (int)$oldAssignee, PDO::PARAM_INT);
        }

        if ($newAssignee === null) {
            $stmt->bindValue(':new_assignee', null, PDO::PARAM_NULL);
        } else {
            $stmt->bindValue(':new_assignee', (int)$newAssignee, PDO::PARAM_INT);
        }

        $stmt->bindValue(':created_at', (string)$createdAt, PDO::PARAM_STR);
        $stmt->bindValue(':delivery_status', (string)$deliveryStatus, PDO::PARAM_STR);
        $stmt->execute();

        return (int)$pdo->lastInsertId();
    }

    public function markDeliveryResult($eventId, $deliveryStatus, $httpStatus, $errorMessage, $rawSnippet)
    {
        $pdo = $this->openConnection();
        $stmt = $pdo->prepare(
            'UPDATE notification_events
             SET delivery_status = :delivery_status,
                 delivery_attempted_at = :attempted_at,
                 delivery_http_status = :http_status,
                 delivery_error_message = :error_message,
                 raw_response_snippet = :raw_snippet
             WHERE id = :id'
        );

        $stmt->bindValue(':delivery_status', (string)$deliveryStatus, PDO::PARAM_STR);
        $stmt->bindValue(':attempted_at', gmdate('c'), PDO::PARAM_STR);

        if ($httpStatus === null) {
            $stmt->bindValue(':http_status', null, PDO::PARAM_NULL);
        } else {
            $stmt->bindValue(':http_status', (int)$httpStatus, PDO::PARAM_INT);
        }

        $error = $this->truncate($errorMessage, 1000);
        if ($error === null || $error === '') {
            $stmt->bindValue(':error_message', null, PDO::PARAM_NULL);
        } else {
            $stmt->bindValue(':error_message', $error, PDO::PARAM_STR);
        }

        $snippet = $this->truncate($rawSnippet, 1000);
        if ($snippet === null || $snippet === '') {
            $stmt->bindValue(':raw_snippet', null, PDO::PARAM_NULL);
        } else {
            $stmt->bindValue(':raw_snippet', $snippet, PDO::PARAM_STR);
        }

        $stmt->bindValue(':id', (int)$eventId, PDO::PARAM_INT);
        $stmt->execute();
    }

    private function openConnection()
    {
        $dir = dirname($this->dbPath);
        if (!is_dir($dir)) {
            mkdir($dir, 0775, true);
        }

        $pdo = new PDO('sqlite:' . $this->dbPath);
        $pdo->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);
        $pdo->setAttribute(PDO::ATTR_DEFAULT_FETCH_MODE, PDO::FETCH_ASSOC);
        $pdo->exec('PRAGMA journal_mode = WAL');
        $pdo->exec('PRAGMA busy_timeout = 5000');

        return $pdo;
    }

    private function truncate($value, $limit)
    {
        if ($value === null) {
            return null;
        }

        $stringValue = (string)$value;
        if (strlen($stringValue) <= $limit) {
            return $stringValue;
        }

        return substr($stringValue, 0, $limit - 3) . '...';
    }
}
