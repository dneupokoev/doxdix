# Обзор проекта doxdix

`doxdix` — локальный CLI-инструмент для автоматической генерации и актуализации документации проекта с помощью LLM: Ollama или OpenAI-совместимого endpoint.

Инструмент пофайлово обходит исходный код, чтобы не переполнять контекстное окно LLM, и поддерживает существующую документацию: читает её, сверяет с кодом, актуализирует, сохраняя瑀 вручную написанные разделы. Перед изменениями создаёт бэкап.

## Ключевые возможности

- пофайловый обход исходного кода и изолированная документация каждого файла;
- актуализация существующих `.md` с сохранением ручных разделов;
- бэкап перед изменениями в `.doxdix/backups/<timestamp>/` с `manifest.json`; восстановление через `--restore`;
- генерация CHANGELOG из git по Conventional Commits в формате Keep a Changelog;
- поддержка Ollama и OpenAI-совместимых endpoint;
- опциональные git-коммиты после изменений (`--no-commit` отключает коммиты);
- зеркалирование структуры исходников в `docs/modules/...`;
- автоматическое определение подпроектов монорепозитория по маркерам `pyproject.toml`, `package.json`, `Cargo.toml`, `go.mod`; группировка документации по `docs/modules/<подпроект>/...` (отключается `--no-monorepo`);
- пропуск пустых и неизменённых файлов по кэшу хэшей
  (`.doxdix/cache.json`; сброс — `--force`);
- тайминг шага генерации модулей в логе.

## Установка

Для установки используется `pipx`:

`pipx install git+https://github.com/dneupokoev/doxdix.git`

## Основной сценарий работы

- пофайловый обход исходного кода проекта;
- подготовка промптов и обращение к LLM;
- генерация новой или актуализация существующей документации;
- сверка документации с кодом;
- сохранение вручную написанных разделов;
- создание резервной копии перед изменениями.

Конкретные режимы и параметры запуска определяются CLI-интерфейсом проекта.

## Конвейер обработки

В общем виде конвейер выполняет:

- сканирование исходников и сбор git-данных;
- создание бэкапа документации;
- генерацию или обновление `CHANGELOG.md`, `README.md` и `docs/SUMMARY.md`;
- пофайловый обход кода с генерацией `.md`-описаний;
- финальное дополнение `SUMMARY.md` ссылками на созданные файлы документации.

Ошибки обработки отдельных файлов нефатальны: они логируются и учитываются в счётчике ошибок. Конфигурационные ошибки, например недоступность LLM или некорректные пути, завершают работу с соответствующим кодом возврата.

## Основные модули

| Модуль | Назначение |
|---|---|
| [__init__](modules/doxdix/__init__.md) | Инициализация пакета; версии `__version__` и `dv_file_version`, без CLI-логики. |
| [backup](modules/doxdix/backup.md) | Создание, восстановление и ротация резервных копий документации с `manifest.json`. |
| [cache](modules/doxdix/cache.md) | Кэш SHA-256 (`.doxdix/cache.json`) и проверка содержимого для пропуска пустых и неизменённых файлов; `--force` игнорирует кэш. |
| [changelog_gen](modules/doxdix/changelog_gen.md) | Разбор Conventional Commits и генерация `CHANGELOG.md` в формате Keep a Changelog. |
| [cli](modules/doxdix/cli.md) | CLI-интерфейс: разбор аргументов, коды возврата, `--restore`/`--check`, запуск конвейера. |
| [llm](modules/doxdix/llm.md) | HTTP-клиент для Ollama и OpenAI-совместимых API: `chat`, `check_model`, `LLMError`. |
| [orchestrator](modules/doxdix/orchestrator.md) | Оркестрация конвейера: сканирование, бэкап, CHANGELOG, README/SUMMARY, документация файлов. |
| [prompts](modules/doxdix/prompts.md) | Русскоязычные шаблоны промптов и функция `render`. |
| [scanner](modules/doxdix/scanner.md) | Сканирование файлов проекта и сбор git-данных: коммиты и отслеживаемые файлы. |

### Документация модулей

- [__init__](modules/doxdix/__init__.md)
- [backup](modules/doxdix/backup.md)
- [cache](modules/doxdix/cache.md)
- [changelog_gen](modules/doxdix/changelog_gen.md)
- [cli](modules/doxdix/cli.md)
- [llm](modules/doxdix/llm.md)
- [orchestrator](modules/doxdix/orchestrator.md)
- [prompts](modules/doxdix/prompts.md)
- [scanner](modules/doxdix/scanner.md)

### Документация модулей: актуальные пути

| Документ | Назначение |
|---|---|
| [__init__](modules/root/src/doxdix/__init__.md) | Метаинформация пакета: `__version__ = "0.1.0"` и `dv_file_version`; реализации CLI, генерации документации или интеграции с Ollama в файле нет. |
| [backup](modules/root/src/doxdix/backup.md) | Бэкап `README.md`, `CHANGELOG.md` и `docs/` в каталог с timestamp и `manifest.json`; восстановление и ротация по `keep`. |
| [cache](modules/root/src/doxdix/cache.md) | Кэш SHA-256 исходников в `<project>/.doxdix/cache.json`; ключи учитывают подпроект, поддерживаются `--force` и пропуск неизменённых файлов. |
| [changelog_gen](modules/root/src/doxdix/changelog_gen.md) | Парсинг Conventional Commits, группировка по секциям Keep a Changelog и генерация/обновление блока `## [Unreleased]`. |
| [cli](modules/root/src/doxdix/cli.md) | Точка входа `main`, `argparse`-параметры, логирование, проверка LLM, `--restore`, `--check`, сборка `RunConfig` и коды возврата. |
| [llm](modules/root/src/doxdix/llm.md) | HTTP-клиент для Ollama (`/api/chat`, `/api/tags`) и OpenAI-совместимых API (`/v1/chat/completions`, `/v1/models`), `chat`, `check_model`, `LLMError`. |
| [orchestrator](modules/root/src/doxdix/orchestrator.md) | Конвейер шагов 0–5: сканирование, бэкап, CHANGELOG, README, SUMMARY, документация модулей; `RunConfig`, `RunStats`, `ConfigError`. |
| [prompts](modules/root/src/doxdix/prompts.md) | Централизованные русскоязычные промпты для SUMMARY, README, документации модулей и CHANGELOG; функция `render`. |
| [scanner](modules/root/src/doxdix/scanner.md) | Обход файлов, фильтрация по расширениям и исключениям, git-коммиты и tracked files, поддержка монорепозиториев и группировка по подпроектам. |

### Документация модулей: созданные/обновлённые файлы

| Документ | Назначение |
|---|---|
| [__init__](modules/src/doxdix/__init__.md) | Метаданные пакета `doxdix`: `__version__ = "0.1.0"` и `dv_file_version`; CLI, генерация документации и интеграция с Ollama в файле отсутствуют. |
| [backup](modules/src/doxdix/backup.md) | Бэкап `README.md`, `CHANGELOG.md` и `docs/` в каталог с ISO-timestamp, `manifest.json` с SHA-256; восстановление и ротация с `keep`. |
| [cache](modules/src/doxdix/cache.md) | Кэш SHA-256 в `<project>/.doxdix/cache.json`; ключи с учётом подпроекта, пропуск неизменённых файлов, `--force` игнорирует кэш. |
| [changelog_gen](modules/src/doxdix/changelog_gen.md) | Разбор Conventional Commits, группировка по секциям Keep a Changelog, формирование/обновление блока `[Unreleased]` и `CHANGELOG.md`. |
| [cli](modules/src/doxdix/cli.md) | Точка входа `main`: `argparse`, логирование, проверка LLM/модели, `--restore`, `--check`, сборка `RunConfig`, коды возврата. |
| [llm](modules/src/doxdix/llm.md) | HTTP-клиент LLM: Ollama (`/api/chat`, `/api/tags`) и OpenAI-совместимый API (`/chat/completions`, `/models`); `chat`, `check_model`, `LLMError`. |
| [orchestrator](modules/src/doxdix/orchestrator.md) | Конвейер шагов 0–5: сканирование, бэкап, CHANGELOG, README, SUMMARY, пофайловая документация; `RunConfig`, `RunStats`, `ConfigError`. |
| [prompts](modules/src/doxdix/prompts.md) | Русскоязычные шаблоны промптов для SUMMARY, README, модулей и CHANGELOG; функция `render`. |
| [scanner](modules/src/doxdix/scanner.md) | Сканирование файлов проекта, git-данные, фильтрация по расширениям/исключениям, определение подпроектов и группировка. |

## Структура пакета

- `__init__.py` — инициализация пакета; версии `__version__` и `dv_file_version`.
- `backup.py` — резервное копирование, восстановление и ротация бэкапов документации.
- `cache.py` — кэш хэшей и проверка содержимого для пропуска пустых и неизменённых файлов.
- `changelog_gen.py` — разбор conventional commits и генерация changelog.
- `cli.py` — CLI-интерфейс: разбор аргументов, точка входа и диспетчеризация режимов.
- `llm.py` — клиент для работы с LLM через Ollama и OpenAI-совместимые эндпоинты.
- `orchestrator.py` — оркестрация pipeline: сканирование, подготовка промптов, вызов LLM и обновление документации.
- `prompts.py` — шаблоны промптов.
- `scanner.py` — сканирование файлов проекта и сбор git-данных.