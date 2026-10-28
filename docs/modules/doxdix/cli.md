# Модуль CLI doxdix

## Назначение
Модуль реализует интерфейс командной строки утилиты doxdix для генерации и актуализации документации проекта через LLM (Ollama или OpenAI-совместимый API). Отвечает за разбор аргументов, настройку логирования, проверку доступности LLM и модели, восстановление из бэкапов, диспетчеризацию режимов и запуск основного конвейера `orchestrator.run()`.

## Публичный API
- `main(argv: list[str] | None = None) -> int` — точка входа. Разбирает аргументы, проверяет `PROJECT_PATH`, выполняет диспетчеризацию: `--restore`, `--check` или основной запуск. Возвращает код возврата.

## Коды возврата
- `0` — успех без ошибок, в том числе успешные `--check` и `--restore`.
- `1` — были ошибки при обработке файлов (`stats.errors > 0`).
- `2` — ошибка конфигурации/LLM/пути/бэкапа: неверный `PROJECT_PATH`, неверный timestamp для `--restore`, отсутствие модели в `--check`, `llm.LLMError`, `orchestrator.ConfigError`. В основном режиме отсутствие `--model` и `DOXDIX_MODEL` текущей реализацией может приводить к `AssertionError` (см. «Примечания»).

## Аргументы CLI
- `PROJECT_PATH` — обязательный путь к корню целевого проекта.
- Пути и файлы:
  - `--src-dir PATH` — подпапка с исходным кодом; по умолчанию весь проект.
  - `--docs-dir PATH` — куда класть документацию модулей; по умолчанию `docs/modules`.
  - `--extensions LIST` — расширения через запятую; по умолчанию `DEFAULT_EXTENSIONS`.
  - `--exclude LIST` — исключения через запятую; по умолчанию `DEFAULT_EXCLUDES`.
- LLM:
  - `--model NAME` — имя модели; иначе env `DOXDIX_MODEL`.
  - `--ollama-url URL` — адрес LLM; иначе env `DOXDIX_OLLAMA_URL` или `DEFAULT_OLLAMA_URL`. URL с `/v1` включает OpenAI-совместимый режим.
  - `--api-key KEY` — API-ключ; иначе env `DOXDIX_API_KEY` или `"dummy"`.
  - `--timeout SEC` — таймаут запроса к LLM; по умолчанию `300`.
  - `--num-ctx N` — размер контекстного окна Ollama; по умолчанию `8192`.
  - `--max-doc-tokens N` — порог размера существующего `.md`; по умолчанию `3000`.
- Git:
  - `--no-git` — не использовать git.
  - `--no-commit` — не делать коммиты.
  - `--changelog-limit N` — число коммитов для CHANGELOG; по умолчанию `100`.
  - `--changelog-llm` — обогащать CHANGELOG через LLM.
  - `--no-changelog` — не генерировать CHANGELOG.
  - `--no-changelog-append` — перезаписывать CHANGELOG вместо дополнения.
- Бэкапы:
  - `--backup-dir PATH` — каталог бэкапов; по умолчанию `<project>/.doxdix/backups`.
  - `--backup-keep N` — сколько бэкапов хранить; по умолчанию `10`.
  - `--no-backup` — отключить бэкап.
  - `--restore TIMESTAMP` — восстановить из бэкапа и выйти.
- Прочее:
  - `--init-license` — создать заготовку LICENSE (MIT), если файла нет.
  - `--force` — игнорировать кэш `.doxdix/cache.json` и перегенерировать все `.md`.
  - `--check` — проверить LLM и модель, выйти.
  - `--no-readme` — не обновлять `README.md`.
  - `--log-file PATH` — файл лога; по умолчанию `<project>/doxdix.log`.

## Основные функции и аргументы
- `_build_parser() -> argparse.ArgumentParser` — собирает argparse-парсер со всеми флагами и группами аргументов.
- `_setup_logging(log_file: Path) -> None` — настраивает root logger на уровень `INFO`, добавляет stdout-хендлер и файловый хендлер в режиме append. Перед этим удаляет старые хендлеры. При `OSError` пишет warning и продолжает без файла.
- `_resolve_model(arg_value: str | None) -> str | None` — выбирает модель: `--model` > env `DOXDIX_MODEL`; возвращает `None`, если не задано.
- `_resolve_url(arg_value: str | None) -> str` — выбирает URL: `--ollama-url` > env `DOXDIX_OLLAMA_URL` > `DEFAULT_OLLAMA_URL`; убирает завершающий `/`.
- `_resolve_api_key(arg_value: str | None) -> str` — выбирает API-ключ: `--api-key` > env `DOXDIX_API_KEY` > `"dummy"`.
- `_split_list(value: str) -> list[str]` — разбивает строку через запятую, обрезает пробелы, отбрасывает пустые элементы.
- `_cmd_check(args: argparse.Namespace) -> int` — проверяет наличие модели и доступность LLM через `llm.check_model(..., timeout=10, api_key=...)`. При отсутствии модели или `llm.LLMError` возвращает `2`; при успехе печатает OK и возвращает `0`.
- `_cmd_restore(args: argparse.Namespace, project_root: Path) -> int` — определяет `backup_dir`, вызывает `backup_mod.restore_backup()`. Если бэкап не найден, выводит список доступных бэкапов и возвращает `2`; иначе печатает число восстановленных файлов и возвращает `0`.
- `_build_run_config(args: argparse.Namespace, project_root: Path) -> orchestrator.RunConfig` — собирает `RunConfig` из аргументов и env. Определяет модель, URL, API-ключ, каталог бэкапов, лог-файл, списки расширений/исключений, флаги git/CHANGELOG/бэкапов/README/LICENSE и `force`.
- `_cmd_run(args: argparse.Namespace, project_root: Path) -> int` — собирает `RunConfig`, настраивает логирование, проверяет LLM и модель, вызывает `orchestrator.run(cfg)`. При `llm.LLMError` или `orchestrator.ConfigError` возвращает `2`. Итоговый код: `0`, если `stats.errors == 0`, иначе `1`.
- `main(argv: list[str] | None = None) -> int` — разбирает аргументы, проверяет, что `PROJECT_PATH` является директорией, разрешает путь. Для `--restore` сначала настраивает логирование, затем вызывает `_cmd_restore()` без проверки LLM. Для `--check` вызывает `_cmd_check()`. Иначе вызывает `_cmd_run()`.

## Зависимости
- Стандартная библиотека: `argparse`, `logging`, `os`, `sys`, `pathlib.Path`, `__future__.annotations`.
- Внутренние модули пакета:
  - `backup as backup_mod` — `restore_backup()`, `list_backups()`.
  - `llm` — `check_model()`, `LLMError`.
  - `orchestrator` — `RunConfig`, `run()`, `ConfigError`.

## Константы
- `dv_file_version = '261028.16'`
- `DEFAULT_OLLAMA_URL = "http://localhost:11434"`
- `DEFAULT_EXTENSIONS = ".py,.js,.ts,.jsx,.tsx,.go,.rs"`
- `DEFAULT_EXCLUDES` — строка исключений через запятую: `.git,.doxdix,node_modules,__pycache__,venv,.venv,env,dist,build,tests,test,.mypy_cache,.pytest_cache,.ruff_cache,target`.

## Использование другими модулями
Модуль является точкой входа CLI. Внутри пакета он импортирует `backup`, `llm`, `orchestrator`; обратные импорты по данному файлу не видны. Обычно используется консольным entry point, запуском `python -m ...` или тестами через вызов `main()`. В режимах `--check` и `--restore` основной конвейер не запускается. В основном режиме вызывается `orchestrator.run(cfg)`.

## Примечания
- `PROJECT_PATH` обязателен для всех режимов.
- `--restore` выполняется до проверки LLM. При одновременном указании `--restore` и `--check` срабатывает `--restore`.
- `--check` проверяет LLM и модель, затем выходит; файловое логирование для `--check` не настраивается.
- При вызове `_setup_logging()` в основном режиме или `--restore` логирование перенастраивается: старые root-хендлеры удаляются.
- `orchestrator.ConfigError` перехватывается в `_cmd_run()` и даёт код `2` без инкремента `stats.errors`.
- `RunConfig.log_file` может быть `None`; `_cmd_run()` достраивает дефолтный путь `<project>/doxdix.log`.
- В `_build_run_config()` есть `assert model is not None`: в основном режиме при отсутствии `--model` и `DOXDIX_MODEL` текущая реализация может завершиться `AssertionError`, а не кодом `2`.
- Проверка «модель не найдена» срабатывает только при непустом списке `available` (`if available and model not in available`). Пустой список доступных моделей не приводит к ошибке в `_cmd_check()` и `_cmd_run()`.