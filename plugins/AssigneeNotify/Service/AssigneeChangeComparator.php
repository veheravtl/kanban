<?php

namespace Kanboard\Plugin\AssigneeNotify\Service;

class AssigneeChangeComparator
{
    public function decide(
        $oldKnown,
        $oldAssigneeId,
        $newKnown,
        $newAssigneeId,
        $eventName = null,
        $newFromChanges = false
    )
    {
        if ($this->isAssigneeChangeEvent($eventName) && $newKnown) {
            if ($newAssigneeId === null) {
                return array(
                    'should_send' => false,
                    'record_skipped' => true,
                    'reason' => 'assignee_removed',
                );
            }

            return array(
                'should_send' => true,
                'record_skipped' => false,
                'reason' => 'assignee_change_event',
            );
        }

        if ($newFromChanges && $newKnown) {
            if ($newAssigneeId === null) {
                return array(
                    'should_send' => false,
                    'record_skipped' => true,
                    'reason' => 'assignee_removed',
                );
            }

            return array(
                'should_send' => true,
                'record_skipped' => false,
                'reason' => 'assignee_change_in_update',
            );
        }

        if (!$oldKnown || !$newKnown) {
            return array(
                'should_send' => false,
                'record_skipped' => false,
                'reason' => 'insufficient_payload',
            );
        }

        if ($oldAssigneeId === $newAssigneeId) {
            if ($oldAssigneeId === null) {
                return array(
                    'should_send' => false,
                    'record_skipped' => false,
                    'reason' => 'both_null',
                );
            }

            return array(
                'should_send' => false,
                'record_skipped' => false,
                'reason' => 'unchanged',
            );
        }

        if ($newAssigneeId === null) {
            return array(
                'should_send' => false,
                'record_skipped' => true,
                'reason' => 'assignee_removed',
            );
        }

        if ($oldAssigneeId === null) {
            return array(
                'should_send' => true,
                'record_skipped' => false,
                'reason' => 'assigned',
            );
        }

        return array(
            'should_send' => true,
            'record_skipped' => false,
            'reason' => 'reassigned',
        );
    }

    private function isAssigneeChangeEvent($eventName)
    {
        if (!is_string($eventName) || $eventName === '') {
            return false;
        }

        return strtolower($eventName) === 'task.assignee_change';
    }
}
