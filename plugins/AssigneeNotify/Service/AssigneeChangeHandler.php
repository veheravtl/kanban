<?php

namespace Kanboard\Plugin\AssigneeNotify\Service;

use Kanboard\Plugin\AssigneeNotify\Model\NotificationEventStore;
use Throwable;

class AssigneeChangeHandler
{
    private const EVENT_TYPE = 'assignee_changed';

    private $extractor;
    private $comparator;
    private $store;
    private $botClient;
    private $logger;

    public function __construct(
        EventPayloadExtractor $extractor,
        AssigneeChangeComparator $comparator,
        NotificationEventStore $store,
        BotServiceClient $botClient,
        $logger
    ) {
        $this->extractor = $extractor;
        $this->comparator = $comparator;
        $this->store = $store;
        $this->botClient = $botClient;
        $this->logger = $logger;
    }

    public function handle($event, $eventName = null)
    {
        try {
            $parsed = $this->extractor->extract($event);

            $taskId = $parsed['task_id'];
            if ($taskId === null || $taskId <= 0) {
                $this->logger->warning('[AssigneeNotify] Skip event: task_id is missing');
                return;
            }

            $decision = $this->comparator->decide(
                $parsed['old_known'],
                $parsed['old_assignee_user_id'],
                $parsed['new_known'],
                $parsed['new_assignee_user_id'],
                $eventName,
                $parsed['new_from_changes']
            );

            if (!$decision['should_send']) {
                if ($decision['record_skipped']) {
                    $eventUuid = $this->generateUuidV4();
                    $this->store->createEvent(
                        $eventUuid,
                        self::EVENT_TYPE,
                        $taskId,
                        $parsed['old_assignee_user_id'],
                        $parsed['new_assignee_user_id'],
                        'skipped',
                        $parsed['occurred_at']
                    );
                    $this->logger->info(sprintf(
                        '[AssigneeNotify] Skipped event recorded task_id=%d reason=%s',
                        $taskId,
                        $decision['reason']
                    ));
                }

                if (!$decision['record_skipped']) {
                    $this->logger->info(sprintf(
                        '[AssigneeNotify] Skip delivery task_id=%d reason=%s event=%s',
                        $taskId,
                        $decision['reason'],
                        (string)$eventName
                    ));
                }

                return;
            }

            $eventUuid = $this->generateUuidV4();
            $eventId = $this->store->createEvent(
                $eventUuid,
                self::EVENT_TYPE,
                $taskId,
                $parsed['old_assignee_user_id'],
                $parsed['new_assignee_user_id'],
                'pending',
                $parsed['occurred_at']
            );

            $payload = array(
                'event_id' => $eventUuid,
                'event_type' => self::EVENT_TYPE,
                'task_id' => $taskId,
                'kanboard_user_id' => $parsed['new_assignee_user_id'],
                'occurred_at' => $parsed['occurred_at'],
                'old_assignee_user_id' => $parsed['old_assignee_user_id'],
                'new_assignee_user_id' => $parsed['new_assignee_user_id'],
            );

            $this->logger->info(sprintf(
                '[AssigneeNotify] Event created id=%d uuid=%s task_id=%d new_assignee=%s event=%s',
                $eventId,
                $eventUuid,
                $taskId,
                (string)$parsed['new_assignee_user_id'],
                (string)$eventName
            ));

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
                    '[AssigneeNotify] Delivery sent event_id=%d task_id=%d http_status=%s',
                    $eventId,
                    $taskId,
                    (string)$httpStatus
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
                '[AssigneeNotify] Delivery failed event_id=%d task_id=%d status=%s http_status=%s',
                $eventId,
                $taskId,
                $status,
                (string)$httpStatus
            ));
        } catch (Throwable $e) {
            $this->logger->error(sprintf(
                '[AssigneeNotify] Handle error: %s',
                $e->getMessage()
            ));
        }
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
            return uniqid('assignee_notify_', true);
        }
    }
}
