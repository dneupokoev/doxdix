# Модуль CLI doxdix

## Назначение
Модуль реализует интерфейс командной строки (CLI) для утилиты doxdix, предназначенной для генерации и актуализации документации проекта через LLM (Ollama или OpenAI-совместимый API). Обеспечивает разбор аргументов, проверку доступности LLM и модели, восстановление из бэкапов, диспетчеризацию режимов и запуск основного конвейера обработки.

## Публичный API
- `main(argv: list[str] | None = None) -> int` — точка входа. Выполняет диспетчеризацию: `--restore`, `--check` или основной запуск. Возвращает код возврата (см. ниже).

## Коды возврата
- `0` — успех без ошибок (в т.ч. `--check`/`--restore` OK).
- `1` — были ошибки при обработке файлов.
- `2` — ошибка конфигурации (нет LLM/модели, неверный путь, отсутствие `--model` + `DOXDIX_MODEL`, неверный timestamp для `--restore`).

## Основные функции и аргументы
- `_build_parser() -> argparse.ArgumentParser` — создаёт парсер аргументов командной строки со всеми флагами (пути, LLM, git, бэкапы, прочее).
- `_setup_logging(log_file: Path) -> None` — настраивает логирование в stdout и файл (append). При ошибке открытия файла выводит предупреждение.
- `_resolve_model(arg_value: str | None) -> str | None` — определяет модель: аргумент `--model` > env `DOXDIX_MODEL`.
- `_resolve_url(arg_value: str | None) -> str` — определяет URL LLM: `--ollama-url` > env `DOXDIX_OLLAMA_URL` > `DEFAULT_OLLAMA_URL`.
- `_resolve_api_key(arg_value: str | None) -> str` — определяет API-ключ: `--api-key` > env `DOXDIX_API_KEY` > `"dummy"`.
- `_split_list(value: str) -> list[str]` — разбивает строку через запятую, обрезает пробелы, отбрасывает пустые.
- `_cmd_check(args: argparse.Namespace) -> int` — проверяет доступность LLM и наличие модели. Возвращает 0 или 2.
- `_cmd_restore(args: argparse.Namespace, project_root: Path) -> int` — восстанавливает файлы из бэкапа по timestamp. Возвращает 0 или 2.
- `_build_run_config(args: argparse.Namespace, project_root: Path) -> orchestrator.RunConfig` — собирает конфигурацию запуска из аргументов и переменных окружения.
- `_cmd_run(args: argparse.Namespace, project_root: Path) -> int` — настраивает логирование, проверяет LLM, вызывает `orchestrator.run()`, возвращает 0 при отсутствии ошибок, иначе 1 (или 2 при ошибке LLM).
- `main(argv: list[str] | None = None) -> int` — точка входа, описана выше.

## Зависимости
- Стандартная библиотека: `argparse`, `logging`, `os`, `sys`, `pathlib`.
- Внутренние модули пакета:
  - `backup` (как `backup_mod`) — восстановление и список бэкапов.
  - `llm` — проверка доступности LLM и модели (`llm.check_model`, `llm.LLMError`).
  - `orchestrator` — основной конвейер обработки (`orchestrator.run`, `orchestrator.RunConfig`).

## Константы
- `dv_file_version = '261028.11'`
- `DEFAULT_OLLAMA_URL = "http://localhost:11434"`
- `DEFAULT_EXTENSIONS = ".py,.js,.ts,.jsx,.tsx,.go,.rs"`
- `DEFAULT_EXCLUDES` — список исключаемых папок по умолчанию.

## Использование другими модулями
Модуль является точкой входа CLI. Внутри пакета другие модули не импортируют его напрямую, кроме возможного вызова `main()` из консольного скрипта (entry point) или тестов. Обратные зависимости: сам модуль импортирует `backup`, `llm`, `orchestrator`. При запуске в режиме `--check` или `--restore` основной конвейер не используется. В основном режиме вызывается `orchestrator.run(cfg)`, который выполняет обработку файлов.

## Примечания
- `PROJECT_PATH` обязателен для всех режимов.
- `--restore` выполняется до проверки LLM.
- `--check` проверяет LLM и модель, затем выходит.
- При повторном вызове `main()` в тестах логирование перенастраивается (удаляются старые хендлеры).