<?php

namespace Kanboard\Plugin\AssigneeNotify\Service;

class BotServiceBindingsClient
{
    private $webhookUrl;
    private $sharedSecret;
    private $timeoutSec;
    private $snippetLimit;

    public function __construct($webhookUrl, $sharedSecret, $timeoutSec = 5, $snippetLimit = 400)
    {
        $this->webhookUrl = rtrim((string)$webhookUrl, '/');
        $this->sharedSecret = (string)$sharedSecret;
        $this->timeoutSec = (int)$timeoutSec > 0 ? (int)$timeoutSec : 5;
        $this->snippetLimit = (int)$snippetLimit > 0 ? (int)$snippetLimit : 400;
    }

    public function listBindings($kanboardUserId = null)
    {
        $path = '/api/v1/bindings';
        if ((int)$kanboardUserId > 0) {
            $path .= '?kanboard_user_id=' . (int)$kanboardUserId;
        }

        return $this->request('GET', $path);
    }

    public function upsertBinding($kanboardUserId, $telegramChatId, $isActive = true)
    {
        return $this->request('POST', '/api/v1/bindings/upsert', array(
            'kanboard_user_id' => (int)$kanboardUserId,
            'telegram_chat_id' => (string)$telegramChatId,
            'is_active' => (bool)$isActive,
        ));
    }

    public function unbindBinding($kanboardUserId)
    {
        return $this->request('POST', '/api/v1/bindings/unbind', array(
            'kanboard_user_id' => (int)$kanboardUserId,
        ));
    }

    public function testBinding($kanboardUserId)
    {
        return $this->request('POST', '/api/v1/bindings/test', array(
            'kanboard_user_id' => (int)$kanboardUserId,
        ));
    }

    public function createBindingToken($kanboardUserId)
    {
        return $this->request('POST', '/api/v1/bindings/token/create', array(
            'kanboard_user_id' => (int)$kanboardUserId,
        ));
    }

    private function request($method, $path, array $payload = null)
    {
        if ($this->sharedSecret === '') {
            return $this->errorResponse('shared_secret_is_empty');
        }

        $baseUrl = $this->getApiBaseUrl();
        if ($baseUrl === '') {
            return $this->errorResponse('bot_service_url_is_empty');
        }

        if (strpos($path, '/') !== 0) {
            $path = '/' . $path;
        }

        $url = $baseUrl . $path;
        $body = null;

        if ($payload !== null) {
            $body = json_encode($payload);
            if ($body === false) {
                return $this->errorResponse('json_encode_failed');
            }
        }

        if (function_exists('curl_init')) {
            return $this->requestWithCurl($method, $url, $body);
        }

        return $this->requestWithStreams($method, $url, $body);
    }

    private function requestWithCurl($method, $url, $body)
    {
        $ch = curl_init($url);
        if ($ch === false) {
            return $this->errorResponse('curl_init_failed');
        }

        $headers = array(
            'Accept: application/json',
            'X-Webhook-Token: ' . $this->sharedSecret,
        );

        if ($body !== null) {
            $headers[] = 'Content-Type: application/json';
        }

        curl_setopt($ch, CURLOPT_CUSTOMREQUEST, (string)$method);
        curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
        curl_setopt($ch, CURLOPT_CONNECTTIMEOUT, $this->timeoutSec);
        curl_setopt($ch, CURLOPT_TIMEOUT, $this->timeoutSec);
        curl_setopt($ch, CURLOPT_HTTPHEADER, $headers);

        if ($body !== null) {
            curl_setopt($ch, CURLOPT_POSTFIELDS, $body);
        }

        $response = curl_exec($ch);
        if ($response === false) {
            $error = curl_error($ch);
            curl_close($ch);
            return $this->errorResponse('http_error: ' . $error);
        }

        $httpStatus = (int)curl_getinfo($ch, CURLINFO_HTTP_CODE);
        curl_close($ch);

        return $this->buildResponse($httpStatus, $response);
    }

    private function requestWithStreams($method, $url, $body)
    {
        $headers = array(
            'Accept: application/json',
            'X-Webhook-Token: ' . $this->sharedSecret,
        );

        if ($body !== null) {
            $headers[] = 'Content-Type: application/json';
        }

        $context = stream_context_create(array(
            'http' => array(
                'method' => (string)$method,
                'header' => implode("\r\n", $headers),
                'content' => $body === null ? '' : $body,
                'timeout' => $this->timeoutSec,
                'ignore_errors' => true,
            ),
        ));

        $response = @file_get_contents($url, false, $context);
        $httpStatus = null;

        if (isset($http_response_header) && is_array($http_response_header) && isset($http_response_header[0])) {
            if (preg_match('/\s(\d{3})\s/', $http_response_header[0], $matches) === 1) {
                $httpStatus = (int)$matches[1];
            }
        }

        if ($response === false) {
            return $this->errorResponse('http_error: stream_request_failed', $httpStatus);
        }

        return $this->buildResponse($httpStatus, $response);
    }

    private function buildResponse($httpStatus, $rawBody)
    {
        $snippet = $this->truncate((string)$rawBody);
        $decoded = json_decode((string)$rawBody, true);

        if (!is_array($decoded)) {
            return $this->errorResponse('invalid_json_response', $httpStatus, $snippet);
        }

        $ok = isset($decoded['ok']) && $decoded['ok'] === true;
        $status = isset($decoded['status']) && is_string($decoded['status'])
            ? $decoded['status']
            : null;
        $data = isset($decoded['data']) && is_array($decoded['data'])
            ? $decoded['data']
            : array();

        $error = null;
        if (!$ok) {
            if (isset($decoded['error']) && is_string($decoded['error']) && $decoded['error'] !== '') {
                $error = $decoded['error'];
            } elseif ($status !== null) {
                $error = $status;
            } else {
                $error = 'bot_service_rejected';
            }
        }

        return array(
            'ok' => $ok,
            'status' => $status,
            'http_status' => $httpStatus,
            'error' => $error,
            'data' => $data,
            'raw_response_snippet' => $snippet,
        );
    }

    private function getApiBaseUrl()
    {
        if ($this->webhookUrl === '') {
            return '';
        }

        $suffix = '/events/assignee-changed';
        if (substr($this->webhookUrl, -strlen($suffix)) === $suffix) {
            return substr($this->webhookUrl, 0, -strlen($suffix));
        }

        return $this->webhookUrl;
    }

    private function errorResponse($error, $httpStatus = null, $snippet = '')
    {
        return array(
            'ok' => false,
            'status' => null,
            'http_status' => $httpStatus,
            'error' => $error,
            'data' => array(),
            'raw_response_snippet' => $snippet,
        );
    }

    private function truncate($value)
    {
        if (strlen($value) <= $this->snippetLimit) {
            return $value;
        }

        return substr($value, 0, $this->snippetLimit - 3) . '...';
    }
}
