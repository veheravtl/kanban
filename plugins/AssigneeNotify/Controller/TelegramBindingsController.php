<?php

namespace Kanboard\Plugin\AssigneeNotify\Controller;

use Kanboard\Controller\BaseController;
use Kanboard\Core\Controller\AccessForbiddenException;
use Kanboard\Plugin\AssigneeNotify\Service\BotServiceBindingsClient;
use Kanboard\Plugin\AssigneeNotify\Service\Config;

class TelegramBindingsController extends BaseController
{
    public function index()
    {
        $this->assertAdmin();

        $usersById = $this->getAllUsersById();
        $users = $this->filterActiveUsers($usersById);
        $client = $this->getBindingsClient();
        $result = $client->listBindings();

        $bindingsByUserId = array();
        $staleBindings = array();
        $listError = '';

        if ($result['ok']) {
            $rows = isset($result['data']['bindings']) && is_array($result['data']['bindings'])
                ? $result['data']['bindings']
                : array();

            foreach ($rows as $row) {
                if (isset($row['kanboard_user_id'])) {
                    $kanboardUserId = (int)$row['kanboard_user_id'];
                    $bindingsByUserId[$kanboardUserId] = $row;

                    if (!isset($usersById[$kanboardUserId])) {
                        $staleBindings[] = array(
                            'kanboard_user_id' => $kanboardUserId,
                            'telegram_chat_id' => isset($row['telegram_chat_id']) ? (string)$row['telegram_chat_id'] : '',
                            'is_active' => isset($row['is_active']) && (int)$row['is_active'] === 1,
                            'reason' => 'missing_user',
                            'username' => '',
                            'name' => '',
                        );
                    } elseif (isset($usersById[$kanboardUserId]['is_active']) && (int)$usersById[$kanboardUserId]['is_active'] !== 1) {
                        $user = $usersById[$kanboardUserId];
                        $staleBindings[] = array(
                            'kanboard_user_id' => $kanboardUserId,
                            'telegram_chat_id' => isset($row['telegram_chat_id']) ? (string)$row['telegram_chat_id'] : '',
                            'is_active' => isset($row['is_active']) && (int)$row['is_active'] === 1,
                            'reason' => 'inactive_user',
                            'username' => isset($user['username']) ? (string)$user['username'] : '',
                            'name' => isset($user['name']) ? (string)$user['name'] : '',
                        );
                    }
                }
            }
        } else {
            $listError = $this->formatError($result);
        }

        $this->response->html($this->helper->layout->config('assigneeNotify:config/telegram_bindings', array(
            'title' => t('Settings') . ' &gt; ' . t('Telegram bindings'),
            'users' => $users,
            'bindings_by_user_id' => $bindingsByUserId,
            'stale_bindings' => $staleBindings,
            'list_error' => $listError,
        )));
    }

    public function upsert()
    {
        $this->assertAdmin();
        $this->checkCSRFForm();

        $values = $this->request->getValues();
        $kanboardUserId = $this->readPositiveInt($values, 'kanboard_user_id');
        $telegramChatId = isset($values['telegram_chat_id']) ? trim((string)$values['telegram_chat_id']) : '';

        if ($kanboardUserId <= 0) {
            $this->flash->failure(t('Invalid user id.'));
            $this->redirectToIndex();
            return;
        }

        if ($telegramChatId === '') {
            $this->flash->failure(t('Telegram chat id is required.'));
            $this->redirectToIndex();
            return;
        }

        $client = $this->getBindingsClient();
        $result = $client->upsertBinding($kanboardUserId, $telegramChatId, true);

        if ($result['ok']) {
            $this->flash->success(t('Telegram binding has been saved.'));
        } else {
            $this->flash->failure(t('Unable to save Telegram binding: %s', $this->formatError($result)));
        }

        $this->redirectToIndex();
    }

    public function unbind()
    {
        $this->assertAdmin();
        $this->checkCSRFForm();

        $values = $this->request->getValues();
        $kanboardUserId = $this->readPositiveInt($values, 'kanboard_user_id');
        if ($kanboardUserId <= 0) {
            $this->flash->failure(t('Invalid user id.'));
            $this->redirectToIndex();
            return;
        }

        $client = $this->getBindingsClient();
        $result = $client->unbindBinding($kanboardUserId);

        if ($result['ok']) {
            $this->flash->success(t('Telegram binding has been deactivated.'));
        } else {
            $this->flash->failure(t('Unable to unbind Telegram chat: %s', $this->formatError($result)));
        }

        $this->redirectToIndex();
    }

    public function test()
    {
        $this->assertAdmin();
        $this->checkCSRFForm();

        $values = $this->request->getValues();
        $kanboardUserId = $this->readPositiveInt($values, 'kanboard_user_id');
        if ($kanboardUserId <= 0) {
            $this->flash->failure(t('Invalid user id.'));
            $this->redirectToIndex();
            return;
        }

        $client = $this->getBindingsClient();
        $result = $client->testBinding($kanboardUserId);

        if ($result['ok']) {
            $this->flash->success(t('Test message delivered.'));
        } else {
            $this->flash->failure(t('Test message failed: %s', $this->formatError($result)));
        }

        $this->redirectToIndex();
    }

    public function cleanupStale()
    {
        $this->assertAdmin();
        $this->checkCSRFForm();

        $usersById = $this->getAllUsersById();
        $client = $this->getBindingsClient();
        $result = $client->listBindings();

        if (!$result['ok']) {
            $this->flash->failure(t('Unable to load bindings: %s', $this->formatError($result)));
            $this->redirectToIndex();
            return;
        }

        $rows = isset($result['data']['bindings']) && is_array($result['data']['bindings'])
            ? $result['data']['bindings']
            : array();

        $successCount = 0;
        $failedUserIds = array();

        foreach ($rows as $row) {
            if (!isset($row['kanboard_user_id'])) {
                continue;
            }

            $kanboardUserId = (int)$row['kanboard_user_id'];
            if ($kanboardUserId <= 0) {
                continue;
            }

            $isStale = !isset($usersById[$kanboardUserId]) || (isset($usersById[$kanboardUserId]['is_active']) && (int)$usersById[$kanboardUserId]['is_active'] !== 1);
            if (!$isStale) {
                continue;
            }

            $unbind = $client->unbindBinding($kanboardUserId);
            if ($unbind['ok']) {
                $successCount++;
            } else {
                $failedUserIds[] = $kanboardUserId;
            }
        }

        if (!empty($failedUserIds)) {
            $this->flash->failure(t(
                'Stale cleanup partially failed. Deactivated: %d. Failed user ids: %s',
                $successCount,
                implode(', ', $failedUserIds)
            ));
        } else {
            $this->flash->success(t('Stale bindings deactivated: %d', $successCount));
        }

        $this->redirectToIndex();
    }

    private function assertAdmin()
    {
        if (! $this->userSession->isAdmin()) {
            throw new AccessForbiddenException();
        }
    }

    private function getAllUsersById()
    {
        $rows = $this->userModel->getAll();
        $usersById = array();

        foreach ($rows as $row) {
            if (! isset($row['id'])) {
                continue;
            }

            $usersById[(int)$row['id']] = $row;
        }

        return $usersById;
    }

    private function filterActiveUsers(array $usersById)
    {
        $result = array();

        foreach ($usersById as $row) {
            if (isset($row['is_active']) && (int)$row['is_active'] !== 1) {
                continue;
            }

            $result[] = $row;
        }

        return $result;
    }

    private function getBindingsClient()
    {
        $config = new Config(dirname(__DIR__));

        return new BotServiceBindingsClient(
            $config->getBotServiceUrl(),
            $config->getSharedSecret(),
            $config->getHttpTimeoutSec(),
            $config->getResponseSnippetLimit()
        );
    }

    private function redirectToIndex()
    {
        $this->response->redirect($this->helper->url->to(
            'TelegramBindingsController',
            'index',
            array('plugin' => 'AssigneeNotify')
        ));
    }

    private function formatError(array $result)
    {
        $parts = array();

        if (isset($result['error']) && is_string($result['error']) && $result['error'] !== '') {
            $parts[] = $result['error'];
        }

        if (isset($result['status']) && is_string($result['status']) && $result['status'] !== '') {
            $parts[] = 'status=' . $result['status'];
        }

        if (isset($result['http_status']) && $result['http_status'] !== null) {
            $parts[] = 'http=' . (int)$result['http_status'];
        }

        if (isset($result['raw_response_snippet']) && is_string($result['raw_response_snippet']) && $result['raw_response_snippet'] !== '') {
            $parts[] = $result['raw_response_snippet'];
        }

        if (empty($parts)) {
            return 'unknown_error';
        }

        return implode('; ', $parts);
    }

    private function readPositiveInt(array $values, $key)
    {
        if (!isset($values[$key])) {
            return 0;
        }

        $value = (string)$values[$key];
        if (!ctype_digit($value)) {
            return 0;
        }

        $parsed = (int)$value;
        return $parsed > 0 ? $parsed : 0;
    }
}
