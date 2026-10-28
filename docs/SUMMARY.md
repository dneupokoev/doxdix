# Обзор проекта doxdix

`doxdix` — локальный CLI-инструмент для автоматической генерации и актуализации документации проекта с помощью LLM: Ollama или OpenAI-совместимого endpoint.

Инструмент пофайлово обходит исходный код, чтобы не переполнять контекстное окно LLM, и поддерживает существующую документацию: читает её, сверяет с кодом, актуализирует, сохраняя вручную написанные разделы. Перед изменениями создаёт бэкап.

## Ключевые возможности

- пофайловый обход исходного кода и изолированная документация каждого файла;
- актуализация существующих `.md` с сохранением ручных разделов;
- бэкап перед изменениями в `.doxdix/backups/<timestamp>/` с `manifest.json`;
- генерация CHANGELOG из git по Conventional Commits;
- поддержка Ollama и OpenAI-совместимых endpoint;
- опциональные git-коммиты после изменений;
- зеркалирование структуры исходников в `docs/modules/...`;
- пропуск пустых и неизменённых файлов;
- автопоиск подпроектов (монорепозиторий) и раскладка документации по ним.

## Установка

Для установки используется `pipx`:

`pipx install git+https://github.com/dneupokoev/doxdix.git`

## Основной сценарий работы

- сканирование проекта и автопоиск подпроектов;
- создание резервной копии документации перед изменениями;
- генерация или обновление `CHANGELOG.md`, `README.md`, `SUMMARY.md`;
- пофайловый обход исходного кода и генерация/актуализация `.md` модулей;
- финальное дополнение `SUMMARY.md` ссылками на созданные и обновлённые файлы документации;
- сверка документации с кодом и сохранение вручную написанных разделов.

Конкретные режимы и параметры запуска определяются CLI-интерфейсом проекта.

## Основные модули

| Модуль | Назначение |
|---|---|
| [__init__](modules/src/doxdix/__init__.md) | Инициализация пакета; версии `__version__` и `dv_file_version`. |
| [backup](modules/src/doxdix/backup.md) | Создание, восстановление и ротация резервных копий документации с `manifest.json`. |
| [cache](modules/src/doxdix/cache.md) | Кэш SHA-256 (`.doxdix/cache.json`) и проверка содержимого для пропуска пустых и неизменённых файлов; `--force` игнорирует кэш. |
| [changelog_gen](modules/src/doxdix/changelog_gen.md) | Разбор Conventional Commits и генерация `CHANGELOG.md` в формате Keep a Changelog. |
| [cli](modules/src/doxdix/cli.md) | CLI-интерфейс: разбор аргументов, коды возврата, `--restore`/`--check`, запуск конвейера. |
| [llm](modules/src/doxdix/llm.md) | HTTP-клиент для Ollama и OpenAI-совместимых API: `chat`, `check_model`, `LLMError`. |
| [orchestrator](modules/src/doxdix/orchestrator.md) | Конвейер шагов 0–5: сканирование, бэкап, CHANGELOG, README/SUMMARY, пофайловая документация и финальный SUMMARY; `RunConfig`, нефатальные ошибки файлов. |
| [prompts](modules/src/doxdix/prompts.md) | Русскоязычные шаблоны промптов для SUMMARY, README, модулей и CHANGELOG; функция `render`; требование возвращать полный `.md`. |
| [scanner](modules/src/doxdix/scanner.md) | Сканирование файлов проекта, сбор git-данных и автопоиск подпроектов. |

## Документация модулей в альтернативном наборе путей

- [__init__](modules/doxdix/__init__.md)
- [backup](modules/doxdix/backup.md)
- [cache](modules/doxdix/cache.md)
- [changelog_gen](modules/doxdix/changelog_gen.md)
- [cli](modules/doxdix/cli.md)
- [llm](modules/doxdix/llm.md)
- [orchestrator](modules/doxdix/orchestrator.md)
- [prompts](modules/doxdix/prompts.md)
- [scanner](modules/doxdix/scanner.md)

## Созданные/обновлённые файлы документации

- [orchestrator](modules/src/doxdix/orchestrator.md) — конвейер шагов 0–5, `RunConfig`, нефатальная обработка ошибок отдельных файлов.
- [prompts](modules/src/doxdix/prompts.md) — шаблоны промптов и функция `render`.

## Структура пакета

- `__init__.py` — инициализация пакета.
- `backup.py` — резервное копирование перед изменением документации.
- `cache.py` — кэширование хэшей для пропуска неизменённых файлов.
- `changelog_gen.py` — разбор conventional commits и генерация changelog.
- `cli.py` — CLI-интерфейс: разбор аргументов, точка входа и диспетчеризация режимов.
- `llm.py` — клиент для работы с LLM через Ollama и OpenAI-совместимые эндпоинты.
- `orchestrator.py` — конвейер шагов 0–5: сканирование, бэкап, CHANGELOG/README/SUMMARY, пофайловая документация и финальный SUMMARY.
- `prompts.py` — русскоязычные шаблоны промптов для SUMMARY, README, модулей и CHANGELOG.
- `scanner.py` — сканирование файлов проекта и поиск подпроектов.