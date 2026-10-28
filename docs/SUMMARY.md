# Обзор проекта doxdix

`doxdix` — локальный CLI-инструмент для автоматической генерации и актуализации документации проекта с помощью LLM: Ollama или OpenAI-совместимого endpoint.

Инструмент пофайлово обходит исходный код, чтобы не переполнять контекстное окно LLM, и поддерживает существующую документацию: читает её, сверяет с кодом, актуализирует, сохраняя вручную написанные разделы. Перед изменениями создаёт бэкап.

## Ключевые возможности

- пофайловый обход исходного кода и изолированная документация каждого файла;
- актуализация существующих `.md` с сохранением ручных разделов;
- бэкап перед изменениями в `.doxdix/backups/<timestamp>/` с `manifest.json`;
- генерация CHANGELOG из git по Conventional Commits в формате Keep a Changelog;
- поддержка Ollama и OpenAI-совместимых endpoint;
- опциональные git-коммиты после изменений;
- зеркалирование структуры исходников в `docs/modules/...`;
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

## Основные модули

| Модуль | Назначение |
|---|---|
| [__init__](modules/doxdix/__init__.md) | Инициализация пакета. |
| [backup](modules/doxdix/backup.md) | Резервное копирование перед изменением документации. |
| [cache](modules/doxdix/cache.md) | Кэш хэшей (`.doxdix/cache.json`) и проверка содержимого для пропуска пустых и неизменённых файлов; `--force` игнорирует кэш. |
| [changelog_gen](modules/doxdix/changelog_gen.md) | Разбор conventional commits и генерация changelog. |
| [cli](modules/doxdix/cli.md) | CLI-интерфейс: разбор аргументов, точка входа и диспетчеризация режимов. |
| [llm](modules/doxdix/llm.md) | Клиент для работы с LLM через Ollama и OpenAI-совместимые эндпоинты. |
| [orchestrator](modules/doxdix/orchestrator.md) | Оркестрация pipeline: сканирование, подготовка промптов, вызов LLM и обновление документации. |
| [prompts](modules/doxdix/prompts.md) | Шаблоны промптов. |
| [scanner](modules/doxdix/scanner.md) | Сканирование файлов проекта. |

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

## Структура пакета

- `__init__.py` — инициализация пакета.
- `backup.py` — резервное копирование перед изменением документации.
- `cache.py` — кэш хэшей и проверка содержимого для пропуска пустых и неизменённых файлов.
- `changelog_gen.py` — разбор conventional commits и генерация changelog.
- `cli.py` — CLI-интерфейс: разбор аргументов, точка входа и диспетчеризация режимов.
- `llm.py` — клиент для работы с LLM через Ollama и OpenAI-совместимые эндпоинты.
- `orchestrator.py` — оркестрация pipeline: сканирование, подготовка промптов, вызов LLM и обновление документации.
- `prompts.py` — шаблоны промптов.
- `scanner.py` — сканирование файлов проекта.
