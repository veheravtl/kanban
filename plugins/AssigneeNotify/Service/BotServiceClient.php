<?php

namespace Kanboard\Plugin\AssigneeNotify\Service;

class BotServiceClient
{
    private $url;
    private $sharedSecret;
    private $timeoutSec;
    private $snippetLimit;

    public function __construct($url, $sharedSecret, $timeoutSec = 5, $snippetLimit = 400)
    {
        $this->url = (string)$url;
        $this->sharedSecret = (string)$sharedSecret;
        $this->timeoutSec = (int)$timeoutSec > 0 ? (int)$timeoutSec : 5;
        $this->snippetLimit = (int)$snippetLimit > 0 ? (int)$snippetLimit : 400;
    }

    public function send(array $payload)
    {
        if ($this->url === '') {
            return array(
                'ok' => false,
                'status' => null,
                'http_status' => null,
                'error' => 'bot_service_url_is_empty',
                'raw_response_snippet' => '',
            );
        }

        if ($this->sharedSecret === '') {
            return array(
                'ok' => false,
                'status' => null,
                'http_status' => null,
                'error' => 'shared_secret_is_empty',
                'raw_response_snippet' => '',
            );
        }

        $body = json_encode($payload);
        if ($body === false) {
            return array(
                'ok' => false,
                'status' => null,
                'http_status' => null,
                'error' => 'json_encode_failed',
                'raw_response_snippet' => '',
            );
        }

        if (function_exists('curl_init')) {
            return $this->sendWithCurl($body);
        }

        return $this->sendWithStreams($body);
    }

    private function sendWithCurl($body)
    {
        $ch = curl_init($this->url);
        if ($ch === false) {
            return array(
                'ok' => false,
                'status' => null,
                'http_status' => null,
                'error' => 'curl_init_failed',
                'raw_response_snippet' => '',
            );
        }

        curl_setopt($ch, CURLOPT_POST, true);
        curl_setopt($ch, CURLOPT_POSTFIELDS, $body);
        curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
        curl_setopt($ch, CURLOPT_CONNECTTIMEOUT, $this->timeoutSec);
        curl_setopt($ch, CURLOPT_TIMEOUT, $this->timeoutSec);
        curl_setopt($ch, CURLOPT_HTTPHEADER, array(
            'Content-Type: application/json',
            'Accept: application/json',
            'X-Webhook-Token: ' . $this->sharedSecret,
        ));

        $response = curl_exec($ch);
        if ($response === false) {
            $error = curl_error($ch);
            curl_close($ch);

            return array(
                'ok' => false,
                'status' => null,
                'http_status' => null,
                'error' => 'http_error: ' . $error,
                'raw_response_snippet' => '',
            );
        }

        $httpStatus = (int)curl_getinfo($ch, CURLINFO_HTTP_CODE);
        curl_close($ch);

        return $this->buildResponse($httpStatus, $response);
    }

    private function sendWithStreams($body)
    {
        $context = stream_context_create(array(
            'http' => array(
                'method' => 'POST',
                'header' => implode("\r\n", array(
                    'Content-Type: application/json',
                    'Accept: application/json',
                    'X-Webhook-Token: ' . $this->sharedSecret,
                )),
                'content' => $body,
                'timeout' => $this->timeoutSec,
                'ignore_errors' => true,
            ),
        ));

        $response = @file_get_contents($this->url, false, $context);
        $httpStatus = null;

        if (isset($http_response_header) && is_array($http_response_header) && isset($http_response_header[0])) {
            if (preg_match('/\s(\d{3})\s/', $http_response_header[0], $matches) === 1) {
                $httpStatus = (int)$matches[1];
            }
        }

        if ($response === false) {
            return array(
                'ok' => false,
                'status' => null,
                'http_status' => $httpStatus,
                'error' => 'http_error: stream_request_failed',
                'raw_response_snippet' => '',
            );
        }

        return $this->buildResponse($httpStatus, $response);
    }

    private function buildResponse($httpStatus, $rawBody)
    {
        $snippet = $this->truncate((string)$rawBody);
        $decoded = json_decode((string)$rawBody, true);

        if (!is_array($decoded)) {
            return array(
                'ok' => false,
                'status' => null,
                'http_status' => $httpStatus,
                'error' => 'invalid_json_response',
                'raw_response_snippet' => $snippet,
            );
        }

        $status = isset($decoded['status']) && is_string($decoded['status'])
            ? $decoded['status']
            : null;

        $ok = isset($decoded['ok']) && $decoded['ok'] === true;

        $error = null;
        if (!$ok) {
            if (isset($decoded['error']) && is_string($decoded['error'])) {
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
