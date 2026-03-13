<?php

namespace Kanboard\Plugin\AssigneeNotify\Service;

class EventPayloadExtractor
{
    public function extract($event)
    {
        $payload = $this->extractPayload($event);

        list($taskIdFound, $taskIdRaw) = $this->findFirst($payload, array(
            array('task_id'),
            array('task', 'id'),
            array('values', 'id'),
            array('new', 'id'),
            array('id'),
        ));

        $taskId = $taskIdFound ? $this->toPositiveIntOrNull($taskIdRaw) : null;

        list($oldFound, $oldRaw) = $this->findFirst($payload, array(
            array('old_assignee_user_id'),
            array('old_owner_id'),
            array('previous_assignee_user_id'),
            array('previous_owner_id'),
            array('old', 'assignee_user_id'),
            array('old', 'owner_id'),
            array('before', 'assignee_user_id'),
            array('before', 'owner_id'),
            array('task_old', 'owner_id'),
            array('old_values', 'owner_id'),
            array('changes', 'owner_id', 'old'),
            array('changes', 'assignee_user_id', 'old'),
        ));

        list($newFound, $newRaw) = $this->findFirst($payload, array(
            array('new_assignee_user_id'),
            array('new_owner_id'),
            array('changes', 'owner_id', 'new'),
            array('changes', 'assignee_user_id', 'new'),
            array('changes', 'owner_id'),
            array('changes', 'assignee_user_id'),
            array('owner_id'),
            array('assignee_user_id'),
            array('new', 'owner_id'),
            array('new', 'assignee_user_id'),
            array('values', 'owner_id'),
            array('values', 'assignee_user_id'),
            array('task', 'owner_id'),
            array('task', 'assignee_user_id'),
        ));

        list($newFromChanges, $_newFromChangesRaw) = $this->findFirst($payload, array(
            array('changes', 'owner_id', 'new'),
            array('changes', 'assignee_user_id', 'new'),
            array('changes', 'owner_id'),
            array('changes', 'assignee_user_id'),
        ));

        $oldParsed = $this->parseNullableInt($oldRaw);
        $newParsed = $this->parseNullableInt($newRaw);

        return array(
            'task_id' => $taskId,
            'old_known' => $oldFound && $oldParsed['valid'],
            'new_known' => $newFound && $newParsed['valid'],
            'old_assignee_user_id' => $oldParsed['value'],
            'new_assignee_user_id' => $newParsed['value'],
            'new_from_changes' => $newFromChanges,
            'occurred_at' => gmdate('c'),
            'raw_payload' => $payload,
        );
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

    private function findFirst(array $payload, array $paths)
    {
        foreach ($paths as $path) {
            $result = $this->readPath($payload, $path);
            if ($result['found']) {
                return array(true, $result['value']);
            }
        }

        return array(false, null);
    }

    private function readPath(array $payload, array $path)
    {
        $cursor = $payload;

        foreach ($path as $segment) {
            if (!is_array($cursor) || !array_key_exists($segment, $cursor)) {
                return array('found' => false, 'value' => null);
            }
            $cursor = $cursor[$segment];
        }

        return array('found' => true, 'value' => $cursor);
    }

    private function parseNullableInt($value)
    {
        if ($value === null || $value === '') {
            return array('valid' => true, 'value' => null);
        }

        if (is_int($value)) {
            return array('valid' => true, 'value' => $value);
        }

        if (is_string($value) && preg_match('/^-?\d+$/', $value) === 1) {
            return array('valid' => true, 'value' => (int)$value);
        }

        return array('valid' => false, 'value' => null);
    }

    private function toPositiveIntOrNull($value)
    {
        if (is_int($value)) {
            return $value > 0 ? $value : null;
        }

        if (is_string($value) && preg_match('/^\d+$/', $value) === 1) {
            $parsed = (int)$value;
            return $parsed > 0 ? $parsed : null;
        }

        return null;
    }
}
