"""HTTP-клиент LLM: Ollama (/api/*) и OpenAI-совместимый (/v1/*).

Публичный API:
    LLMError
    chat(base_url, model, prompt, num_ctx, timeout, api_key="dummy") -> str
    check_model(base_url, model, timeout=10, api_key="dummy") -> list[str]

Режим определяется по URL:
- URL оканчивается на "/v1" или содержит "/v1/" -> OpenAI-совместимый:
    POST {base}/chat/completions
    GET  {base}/models
    заголовок Authorization: Bearer <api_key>
- иначе -> Ollama:
    POST {base}/api/chat
    GET  {base}/api/tags
    без auth

Правила (см. ТЗ п. 8):
- HTTP != 200 / нет content / пустой content -> LLMError.
- Возвращает content.strip().
- В Ollama-режиме num_ctx передаётся в options.num_ctx; если
  len(prompt)//4 > num_ctx — предупреждение (не блокируем).
- В OpenAI-режиме num_ctx игнорируется (сервер сам решает).
"""
from __future__ import annotations

import logging

import requests

dv_file_version = '261028.11'
logger = logging.getLogger(__name__)


class LLMError(Exception):
    """Ошибка LLM-клиента: HTTP-код, тело ответа, сообщение."""

    def __init__(self, message: str, status: int | None = None,
                 body: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.status = status
        self.body = body


def _is_openai_mode(base_url: str) -> bool:
    """True, если URL похож на OpenAI-совместимый (/v1/...)."""
    u = base_url.rstrip("/")
    return u.endswith("/v1") or "/v1/" in (u + "/")


def _ollama_chat_url(base_url: str) -> str:
    return base_url.rstrip("/") + "/api/chat"


def _ollama_tags_url(base_url: str) -> str:
    return base_url.rstrip("/") + "/api/tags"


def _openai_chat_url(base_url: str) -> str:
    return base_url.rstrip("/") + "/chat/completions"


def _openai_models_url(base_url: str) -> str:
    return base_url.rstrip("/") + "/models"


def _auth_headers(api_key: str) -> dict[str, str]:
    """Заголовки для OpenAI-режима. Пустой ключ -> без Authorization."""
    if not api_key:
        return {}
    return {"Authorization": f"Bearer {api_key}"}


# --------------------------------------------------------------------------
# Ollama-режим
# --------------------------------------------------------------------------

def _chat_ollama(base_url: str, model: str, prompt: str,
                 num_ctx: int, timeout: int) -> str:
    url = _ollama_chat_url(base_url)
    approx_tokens = len(prompt) // 4
    if approx_tokens > num_ctx:
        logger.warning(
            "промпт ~%d токенов > num_ctx=%d, возможна обрезка контекста",
            approx_tokens, num_ctx,
        )
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {"num_ctx": num_ctx},
    }
    try:
        resp = requests.post(url, json=payload, timeout=timeout)
    except requests.Timeout as exc:
        raise LLMError(f"таймаут запроса к Ollama ({timeout}s): {exc}") from exc
    except requests.RequestException as exc:
        raise LLMError(f"ошибка запроса к Ollama: {exc}") from exc

    if resp.status_code != 200:
        raise LLMError(
            f"Ollama вернул HTTP {resp.status_code}",
            status=resp.status_code,
            body=(resp.text or "")[:1000],
        )
    try:
        data = resp.json()
    except ValueError as exc:
        raise LLMError(f"Ollama вернул не-JSON: {exc}",
                       body=(resp.text or "")[:1000]) from exc

    message = data.get("message") or {}
    content = message.get("content")
    if not isinstance(content, str):
        raise LLMError("в ответе Ollama нет message.content",
                       body=str(data)[:1000])
    if not content.strip():
        raise LLMError("Ollama вернул пустой content",
                       body=str(data)[:1000])
    return content.strip()


def _check_ollama(base_url: str, timeout: int) -> list[str]:
    url = _ollama_tags_url(base_url)
    try:
        resp = requests.get(url, timeout=timeout)
    except requests.Timeout as exc:
        raise LLMError(
            f"Ollama не отвечает по {url} (таймаут {timeout}s): {exc}"
        ) from exc
    except requests.RequestException as exc:
        raise LLMError(f"Ollama недоступен по {url}: {exc}") from exc

    if resp.status_code != 200:
        raise LLMError(
            f"Ollama /api/tags вернул HTTP {resp.status_code}",
            status=resp.status_code,
            body=(resp.text or "")[:1000],
        )
    try:
        data = resp.json()
    except ValueError as exc:
        raise LLMError(f"Ollama /api/tags вернул не-JSON: {exc}",
                       body=(resp.text or "")[:1000]) from exc

    names: list[str] = []
    for m in data.get("models") or []:
        if isinstance(m, dict):
            name = m.get("name")
            if isinstance(name, str) and name:
                names.append(name)
    return names


# --------------------------------------------------------------------------
# OpenAI-совместимый режим
# --------------------------------------------------------------------------

def _chat_openai(base_url: str, model: str, prompt: str,
                 timeout: int, api_key: str) -> str:
    url = _openai_chat_url(base_url)
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
    }
    headers = {"Content-Type": "application/json", **_auth_headers(api_key)}
    try:
        resp = requests.post(url, json=payload, headers=headers,
                             timeout=timeout)
    except requests.Timeout as exc:
        raise LLMError(
            f"таймаут запроса к {url} ({timeout}s): {exc}"
        ) from exc
    except requests.RequestException as exc:
        raise LLMError(f"ошибка запроса к {url}: {exc}") from exc

    if resp.status_code != 200:
        raise LLMError(
            f"{url} вернул HTTP {resp.status_code}",
            status=resp.status_code,
            body=(resp.text or "")[:1000],
        )
    try:
        data = resp.json()
    except ValueError as exc:
        raise LLMError(f"{url} вернул не-JSON: {exc}",
                       body=(resp.text or "")[:1000]) from exc

    choices = data.get("choices") or []
    if not choices or not isinstance(choices[0], dict):
        raise LLMError("в ответе нет choices[0]", body=str(data)[:1000])
    message = choices[0].get("message") or {}
    content = message.get("content")
    if not isinstance(content, str):
        raise LLMError("в ответе нет choices[0].message.content",
                       body=str(data)[:1000])
    if not content.strip():
        raise LLMError("LLM вернул пустой content",
                       body=str(data)[:1000])
    return content.strip()


def _check_openai(base_url: str, timeout: int, api_key: str) -> list[str]:
    url = _openai_models_url(base_url)
    headers = _auth_headers(api_key)
    try:
        resp = requests.get(url, headers=headers, timeout=timeout)
    except requests.Timeout as exc:
        raise LLMError(
            f"{url} не отвечает (таймаут {timeout}s): {exc}"
        ) from exc
    except requests.RequestException as exc:
        raise LLMError(f"{url} недоступен: {exc}") from exc

    if resp.status_code == 404:
        # Некоторые OpenAI-совместимые прокси не реализуют /v1/models.
        # Это не фатально: chat может работать.
        logger.warning(
            "%s вернул 404 (нет /v1/models); проверка имени модели "
            "пропущена, chat может работать", url,
        )
        return []
    if resp.status_code != 200:
        raise LLMError(
            f"{url} вернул HTTP {resp.status_code}",
            status=resp.status_code,
            body=(resp.text or "")[:1000],
        )
    try:
        data = resp.json()
    except ValueError as exc:
        raise LLMError(f"{url} вернул не-JSON: {exc}",
                       body=(resp.text or "")[:1000]) from exc

    names: list[str] = []
    for m in data.get("data") or []:
        if isinstance(m, dict):
            mid = m.get("id")
            if isinstance(mid, str) and mid:
                names.append(mid)
    return names


# --------------------------------------------------------------------------
# Публичный API
# --------------------------------------------------------------------------

def chat(base_url: str, model: str, prompt: str,
         num_ctx: int, timeout: int, api_key: str = "dummy") -> str:
    """Отправить промпт в LLM и вернуть content.strip().

    Режим (Ollama vs OpenAI-совместимый) определяется по base_url.
    Бросает LLMError при любой ошибке.
    """
    if _is_openai_mode(base_url):
        return _chat_openai(base_url, model, prompt, timeout, api_key)
    return _chat_ollama(base_url, model, prompt, num_ctx, timeout)


def check_model(base_url: str, model: str, timeout: int = 10,
                api_key: str = "dummy") -> list[str]:
    """Проверить доступность LLM и вернуть список имён моделей.

    Наличие `model` проверяет вызывающая сторона (cli.py), чтобы
    показать список. Бросает LLMError, если сервер недоступен.
    """
    if _is_openai_mode(base_url):
        return _check_openai(base_url, timeout, api_key)
    return _check_ollama(base_url, timeout)
