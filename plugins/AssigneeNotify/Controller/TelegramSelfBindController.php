<?php

namespace Kanboard\Plugin\AssigneeNotify\Controller;

use Kanboard\Controller\BaseController;
use Kanboard\Core\Controller\AccessForbiddenException;
use Kanboard\Plugin\AssigneeNotify\Service\BotServiceBindingsClient;
use Kanboard\Plugin\AssigneeNotify\Service\Config;

class TelegramSelfBindController extends BaseController
{
    public function index()
    {
        $user = $this->getUser();
        $this->assertCurrentUser($user);

        $this->renderIndex($user);
    }

    public function createCode()
    {
        $user = $this->getUser();
        $this->assertCurrentUser($user);
        $this->checkCSRFForm();

        $client = $this->getBindingsClient();
        $result = $client->createBindingToken((int)$user['id']);

        if ($result['ok']) {
            $data = isset($result['data']) && is_array($result['data']) ? $result['data'] : array();
            $code = isset($data['code']) ? (string)$data['code'] : '';
            $expiresAt = isset($data['expires_at']) ? (string)$data['expires_at'] : '';
            if ($code === '') {
                $this->flash->failure(t('Bind code was not returned by bot-service.'));
                $this->renderIndex($user);
                return;
            }

            $this->renderIndex($user, $code, $expiresAt);
            return;
        } else {
            $this->flash->failure(t('Unable to generate bind code: %s', $this->formatError($result)));
        }

        $this->redirectToIndex((int)$user['id']);
    }

    public function test()
    {
        $user = $this->getUser();
        $this->assertCurrentUser($user);
        $this->checkCSRFForm();

        $client = $this->getBindingsClient();
        $result = $client->testBinding((int)$user['id']);

        if ($result['ok']) {
            $this->flash->success(t('Test message delivered.'));
        } else {
            $this->flash->failure(t('Test message failed: %s', $this->formatError($result)));
        }

        $this->redirectToIndex((int)$user['id']);
    }

    private function assertCurrentUser(array $user)
    {
        if ($this->userSession->getId() !== (int)$user['id']) {
            throw new AccessForbiddenException();
        }
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

    private function redirectToIndex($userId)
    {
        $this->response->redirect($this->helper->url->to(
            'TelegramSelfBindController',
            'index',
            array(
                'plugin' => 'AssigneeNotify',
                'user_id' => (int)$userId,
            )
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

        if (empty($parts)) {
            return 'unknown_error';
        }

        return implode('; ', $parts);
    }

    private function renderIndex(array $user, $generatedCode = '', $generatedExpiresAt = '')
    {
        $client = $this->getBindingsClient();
        $result = $client->listBindings((int)$user['id']);

        $binding = null;
        $error = '';

        if ($result['ok']) {
            $rows = isset($result['data']['bindings']) && is_array($result['data']['bindings'])
                ? $result['data']['bindings']
                : array();
            if (!empty($rows)) {
                $binding = $rows[0];
            }
        } else {
            $error = $this->formatError($result);
        }

        $this->response->html($this->helper->layout->user('assigneeNotify:user/telegram_bind', array(
            'user' => $user,
            'binding' => $binding,
            'error' => $error,
            'generated_code' => (string)$generatedCode,
            'generated_expires_at' => (string)$generatedExpiresAt,
        )));
    }
}
