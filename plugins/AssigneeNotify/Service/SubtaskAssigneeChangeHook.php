<?php

namespace Kanboard\Plugin\AssigneeNotify\Service;

use Kanboard\Plugin\AssigneeNotify\Model\NotificationEventStore;
use Throwable;

class SubtaskAssigneeChangeHook
{
    private const STORAGE_EVENT_TYPE = 'subtask_assignee_changed';
    private const PAYLOAD_EVENT_TYPE = 'assignee_changed';

    private $comparator;
    private $store;
    private $botClient;
    private $subtaskModel;
    private $logger;

    public function __construct(
        AssigneeChangeComparator $comparator,
        NotificationEventStore $store,
        BotServiceClient $botClient,
        $subtaskModel,
        $logger
    ) {
        $this->comparator = $comparator;
        $this->store = $store;
        $this->botClient = $botClient;
        $this->subtaskModel = $subtaskModel;
        $this->logger = $logger;
    }

    public function handle(&$values)
    {
        try {
            if (!is_array($values)) {
                return;
            }

            if (!array_key_exists('id', $values) || !array_key_exists('user_id', $values)) {
                return;
            }

            $subtaskId = $this->toPositiveIntOrNull($values['id']);
            if ($subtaskId === null) {
                return;
            }

            $existingSubtask = $this->subtaskModel->getById($subtaskId);
            if (!is_array($existingSubtask) || empty($existingSubtask)) {
                $this->logger->warning(sprintf(
                    '[AssigneeNotify] Skip subtask hook: subtask not found (subtask_id=%s)',
                    (string)$subtaskId
                ));
                return;
            }

            $taskId = $this->toPositiveIntOrNull($existingSubtask['task_id'] ?? null);
            if ($taskId === null) {
                $this->logger->warning(sprintf(
                    '[AssigneeNotify] Skip subtask hook: invalid task_id (subtask_id=%s)',
                    (string)$subtaskId
                ));
                return;
            }

            $oldAssigneeId = $this->normalizeUserId($existingSubtask['user_id'] ?? null);
            $newAssigneeId = $this->normalizeUserId($values['user_id']);

            $decision = $this->comparator->decide(
                true,
                $oldAssigneeId,
                true,
                $newAssigneeId
            );

            if (!$decision['should_send']) {
                if ($decision['record_skipped']) {
                    $eventUuid = $this->generateUuidV4();
                    $this->store->createEvent(
                        $eventUuid,
                        self::STORAGE_EVENT_TYPE,
                        $taskId,
                        $oldAssigneeId,
                        $newAssigneeId,
                        'skipped',
                        gmdate('c')
                    );
                }

                return;
            }

            $eventUuid = $this->generateUuidV4();
            $eventId = $this->store->createEvent(
                $eventUuid,
                self::STORAGE_EVENT_TYPE,
                $taskId,
                $oldAssigneeId,
                $newAssigneeId,
                'pending',
                gmdate('c')
            );

            $payload = array(
                'event_id' => $eventUuid,
                'event_type' => self::PAYLOAD_EVENT_TYPE,
                'task_id' => $taskId,
                'kanboard_user_id' => $newAssigneeId,
                'occurred_at' => gmdate('c'),
                'old_assignee_user_id' => $oldAssigneeId,
                'new_assignee_user_id' => $newAssigneeId,
                'subtask_id' => $subtaskId,
                'source' => 'subtask',
            );

            $response = $this->botClient->send($payload);
            $status = (string)($response['status'] ?? '');
            $httpStatus = $response['http_status'];

            if (($response['ok'] ?? false) === true && $status === 'delivered') {
                $this->store->markDeliveryResult(
                    $eventId,
                    'sent',
                    $httpStatus,
                    null,
                    $response['raw_response_snippet']
                );
                $this->logger->info(sprintf(
                    '[AssigneeNotify] Subtask delivery sent event_id=%d task_id=%d subtask_id=%d',
                    $eventId,
                    $taskId,
                    $subtaskId
                ));
                return;
            }

            $error = (string)($response['error'] ?? $status ?: 'delivery_failed');
            $this->store->markDeliveryResult(
                $eventId,
                'failed',
                $httpStatus,
                $error,
                $response['raw_response_snippet']
            );
            $this->logger->warning(sprintf(
                '[AssigneeNotify] Subtask delivery failed event_id=%d task_id=%d subtask_id=%d status=%s',
                $eventId,
                $taskId,
                $subtaskId,
                $status
            ));
        } catch (Throwable $e) {
            $this->logger->error(sprintf(
                '[AssigneeNotify] Subtask hook error: %s',
                $e->getMessage()
            ));
        }
    }

    private function normalizeUserId($value)
    {
        if ($value === null || $value === '') {
            return null;
        }

        if (is_string($value) && preg_match('/^-?\d+$/', $value) !== 1) {
            return null;
        }

        $parsed = (int)$value;
        return $parsed > 0 ? $parsed : null;
    }

    private function toPositiveIntOrNull($value)
    {
        if ($value === null || $value === '') {
            return null;
        }

        if (is_string($value) && preg_match('/^\d+$/', $value) !== 1) {
            return null;
        }

        $parsed = (int)$value;
        return $parsed > 0 ? $parsed : null;
    }

    private function generateUuidV4()
    {
        try {
            $bytes = random_bytes(16);
            $bytes[6] = chr((ord($bytes[6]) & 0x0f) | 0x40);
            $bytes[8] = chr((ord($bytes[8]) & 0x3f) | 0x80);
            $hex = bin2hex($bytes);

            return sprintf(
                '%s-%s-%s-%s-%s',
                substr($hex, 0, 8),
                substr($hex, 8, 4),
                substr($hex, 12, 4),
                substr($hex, 16, 4),
                substr($hex, 20, 12)
            );
        } catch (Throwable $e) {
            return uniqid('assignee_notify_subtask_', true);
        }
    }
}
