# doxdix

Локальный CLI-инструмент для автоматической генерации и актуализации
документации проекта с помощью LLM.

Пофайлово обходит исходный код, чтобы не переполнять контекстное окно LLM,
и поддерживает существующую документацию: читает её, сверяет с кодом,
актуализирует, сохраняя вручную написанные разделы. Перед изменениями
создаёт бэкап.

## Возможности

- **Пофайловый обход** — каждый файл кода документируется изолированно,
  контекст LLM не переполняется.
- **Сохранение ручной документации** — LLM обновляет существующие `.md`,
  не удаляя разделы, написанные человеком.
- **Бэкап перед изменениями** — `.doxdix/backups/<timestamp>/` с
  `manifest.json` (sha256 каждого файла). Восстановление: `--restore`.
- **CHANGELOG из git** — парсинг Conventional Commits
  (`feat`, `fix`, `perf`, `refactor`, `docs`, `BREAKING CHANGE`),
  формат Keep a Changelog.
- **Два режима LLM** — Ollama (`/api/*`) и любой OpenAI-совместимый
  endpoint (`/v1/*`: vLLM, LM Studio, OpenRouter, opencode, DeepSeek и т.п.).
- **Git-коммиты** — после каждого изменения файла (опционально,
  `--no-commit`).
- **Зеркалирование структуры** — `src/auth/login.py` →
  `docs/modules/auth/login.md`.

## Требования

- Python >= 3.10
- `pipx` (рекомендуется) или `pip`
- Доступ к LLM:
  - **Ollama** на `http://localhost:11434` (по умолчанию), либо
  - **OpenAI-совместимый endpoint** (URL с `/v1`, ключ через `--api-key`).
- Хотя бы одна загруженная модель.
- Единственная Python-зависимость: `requests>=2.31`.

## Установка

```bash
pipx install git+https://github.com/<user>/doxdix.git
```

Обновление:

```bash
pipx install --force git+https://github.com/<user>/doxdix.git
```

Удаление:

```bash
pipx uninstall doxdix
```

## Быстрый старт

### С Ollama

```bash
# 1. Убедиться, что Ollama запущен и модель загружена
ollama list

# 2. Проверить связь
doxdix /path/to/project --check --model qwen2.5-coder:7b

# 3. Сгенерировать документацию (без коммитов, посмотреть результат)
doxdix /path/to/project --src-dir src --model qwen2.5-coder:7b --no-commit

# 4. Если результат устраивает — запустить с коммитами
doxdix /path/to/project --src-dir src --model qwen2.5-coder:7b
```

### С OpenAI-совместимым API

```bash
doxdix /path/to/project \
    --src-dir src \
    --ollama-url https://api.example.com/v1 \
    --model gpt-4o-mini \
    --api-key <your_api_key> \
    --num-ctx 16384
```

## Переменные окружения

Все параметры можно задать через окружение — удобно для `~/.bashrc`.
CLI-флаги **перекрывают** переменные.

| Переменная | Соответствует флагу | По умолчанию |
|---|---|---|
| `DOXDIX_MODEL` | `--model` | — (обязательно) |
| `DOXDIX_OLLAMA_URL` | `--ollama-url` | `http://localhost:11434` |
| `DOXDIX_API_KEY` | `--api-key` | `dummy` |

Пример `~/.bashrc`:

```bash
export DOXDIX_OLLAMA_URL="http://192.168.1.50:11434"
export DOXDIX_MODEL="qwen2.5-coder:14b"
# export DOXDIX_API_KEY="dummy"   # для OpenAI-совместимых
```

> **Не коммитьте эти переменные в git.** Они живут в окружении, а не в файлах
> проекта.

## Режимы работы

| Команда | Что делает | Код возврата |
|---|---|---|
| `doxdix PROJECT --check` | Проверить LLM и наличие модели, выйти | `0` / `2` |
| `doxdix PROJECT --restore TIMESTAMP` | Восстановить из бэкапа, выйти | `0` / `2` |
| `doxdix PROJECT [опции]` | Полный конвейер (шаги 0–5) | `0` / `1` / `2` |

Коды возврата:
- `0` — успех без ошибок;
- `1` — были ошибки при обработке файлов (см. лог);
- `2` — ошибка конфигурации (нет LLM/модели, неверный путь,
  неверный `TIMESTAMP`).

## Как это работает

1. **Сканирование** — обход файлов с расширениями из `--extensions`.
   Если git доступен — только `git ls-files` (мусор не трогаем).
2. **Бэкап** — `README.md`, `CHANGELOG.md`, `docs/**` →
   `.doxdix/backups/<ts>/`. Ротация: `--backup-keep` последних.
3. **CHANGELOG** — парсинг коммитов, генерация Markdown,
   `[Unreleased]` вставляется после `# Changelog`.
4. **README** — LLM обновляет существующий, сохраняет ручные разделы.
   Ссылка на `LICENSE` вставляется детерминированно, отдельным шагом.
5. **SUMMARY** — `docs/SUMMARY.md` со ссылками на модули.
6. **Модули** — `docs/modules/**/*.md` по правилу зеркалирования.
7. **Финальный SUMMARY** — дополняется ссылками на созданные `.md`.
8. **Итог** — `Успешно: N, ошибок: M, пропущено: K.`

## Флаги

Полный список — `doxdix --help`. Кратко:

- **Пути:** `--src-dir`, `--docs-dir`, `--extensions`, `--exclude`.
- **LLM:** `--model`, `--ollama-url`, `--api-key`, `--timeout`, `--num-ctx`,
  `--max-doc-tokens`.
- **Git:** `--no-git`, `--no-commit`, `--changelog-limit`, `--changelog-llm`,
  `--no-changelog`, `--no-changelog-append`.
- **Бэкапы:** `--backup-dir`, `--backup-keep`, `--no-backup`, `--restore`.
- **Прочее:** `--init-license`, `--check`, `--no-readme`, `--log-file`.

## Безопасность и приватность

- **Никаких конфиг-файлов.** Все параметры — CLI + окружение.
- **Секреты не в git.** `DOXDIX_API_KEY` — только в `~/.bashrc` / окружении.
- **Бэкапы перед изменениями.** Откат: `doxdix PROJECT --restore <ts>`.
- **`doxdix.log`** — в корне целевого проекта. **Добавьте `*.log` в
  `.gitignore` целевого проекта**, чтобы лог не попал в коммиты.
- **LLM видит код.** Для проприетарного кода используйте локальную модель
  (Ollama) или проверенный OpenAI-совместимый endpoint.

## Ограничения

- **Пофайловый обход** — LLM не видит проект целиком, только один файл
  за раз (+ `project_context` из README). Межфайловые связи угадываются
  по импортам.
- **`--max-doc-tokens`** — если существующий `.md` больше лимита,
  актуализация пропускается (чтобы не переполнять контекст).
- **`num_ctx` в OpenAI-режиме** игнорируется (сервер решает сам).
- **CHANGELOG** — работает только при наличии git и Conventional Commits.

## Лицензия

Проект распространяется под лицензией [MIT](LICENSE).
См. файл [LICENSE](LICENSE).
