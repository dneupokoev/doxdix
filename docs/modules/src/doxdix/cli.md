# `doxdix.cli` — точка входа CLI

## Назначение

Модуль реализует командный интерфейс `doxdix`: разбор аргументов, логирование, проверку доступности LLM/модели, восстановление из бэкапа (`--restore`) и запуск основного конвейера через `orchestrator.run()`. Является точкой входа пакета (вызывается из `__main__` и как conscript `doxdix`).

Версия файла: `dv_file_version = '261028.17'`.

## Публичный API

- `main(argv: list[str] | None = None) -> int` — точка входа. Осуществляет диспетчеризацию режимов и возвращает код выхода.

### Коды возврата `main()`

| Код | Значение |
|-----|----------|
| `0` | Успех без ошибок (в т.ч. `--check` / `--restore` OK) |
| `1` | Были ошибки при обработке файлов |
| `2` | Ошибка конфигурации: нет LLM/модели, неверный путь, отсутствие `--model` + `DOXDIX_MODEL`, неверный timestamp для `--restore` |

## Константы

- `DEFAULT_OLLAMA_URL = "http://localhost:11434"` — адрес Ollama по умолчанию.
- `DEFAULT_EXTENSIONS = ".py,.js,.ts,.jsx,.tsx,.go,.rs"` — расширения файлов для документирования.
- `DEFAULT_EXCLUDES` — строка исключаемых папок: `.git, .doxdix, node_modules, __pycache__, venv, .venv, env, dist, build, tests, test, .mypy_cache, .pytest_cache, .ruff_cache, target`.
- `logger` — логгер модуля.

## Основные функции

### `_build_parser() -> argparse.ArgumentParser`
Собирает `argparse.ArgumentParser` со всеми флагами ТЗ (п. 5). Позиционный аргумент `PROJECT_PATH` — путь к корню проекта. Группы флагов:
- **пути и файлы**: `--src-dir`, `--docs-dir` (по умолчанию `docs/modules`), `--no-monorepo`, `--extensions`, `--exclude`;
- **LLM**: `--model`, `--ollama-url`, `--api-key`, `--timeout` (300), `--num-ctx` (8192), `--max-doc-tokens` (3000);
- **git**: `--no-git`, `--no-commit`, `--changelog-limit` (100), `--changelog-llm`, `--no-changelog`, `--no-changelog-append`;
- **бэкапы**: `--backup-dir`, `--backup-keep` (10), `--no-backup`, `--restore TIMESTAMP`;
- **прочее**: `--init-license`, `--force`, `--check`, `--no-readme`, `--log-file`.

### `_setup_logging(log_file: Path) -> None`
Настраивает корневой логгер: уровень `INFO`, формат `%(asctime)s [%(levelname)s] %(message)s`, вывод в `stdout` и в файл (append). Очищает прежние хендлеры (для повторных вызовов в тестах). При невозможности открыть файл — `warning`, работа только со stdout.

### Разрешение параметров (arg > env > default)
- `_resolve_model(arg_value) -> str | None`: `--model` > `DOXDIX_MODEL`; `None`, если не задано.
- `_resolve_url(arg_value) -> str`: `--ollama-url` > `DOXDIX_OLLAMA_URL` > `DEFAULT_OLLAMA_URL`; обрезает завершающий `/`.
- `_resolve_api_key(arg_value) -> str`: `--api-key` > `DOXDIX_API_KEY` > `"dummy"`.
- `_split_list(value) -> list[str]`: разбиение по запятой с обрезкой пробелов и отбрасыванием пустых.

### Режимы
- `_cmd_check(args) -> int` — проверяет LLM и наличие модели через `llm.check_model()` (timeout 10 с). Возвращает `0` при успехе, `2` при ошибке/отсутствии модели. При ошибке печатает доступные модели.
- `_cmd_restore(args, project_root) -> int` — восстанавливает из бэкапа через `backup_mod.restore_backup()`. При отсутствии — печатает список доступных бэкапов (`backup_mod.list_backups()`), возвращает `2`.
- `_build_run_config(args, project_root) -> orchestrator.RunConfig` — собирает конфиг запуска из `argparse.Namespace` + env: разрешает модель/URL/ключ, пути `backup_dir` (по умолчанию `<project>/.doxdix/backups`) и `log_file` (по умолчанию `<project>/doxdix.log`), парсит `extensions`/`excludes`, транслирует флаги в поля `RunConfig` (инверсия `--no-*` в булевы поля).
- `_cmd_run(args, project_root) -> int` — настраивает логирование, проверяет LLM+модель, вызывает `orchestrator.run(cfg)`. Ловит `orchestrator.ConfigError` → `2`, ошибки `llm.LLMError` → `2`. Возвращает `0` при `stats.errors == 0`, иначе `1`.

### `main(argv=None) -> int`
1. Парсит аргументы.
2. Проверяет, что `PROJECT_PATH` — существующая директория (иначе `2`), резолвит путь.
3. `--restore` → настраивает лог и вызывает `_cmd_restore` (без проверки LLM).
4. `--check` → вызывает `_cmd_check`.
5. Иначе → `_cmd_run`.

## Зависимости

Стандартная библиотека: `argparse`, `logging`, `os`, `sys`, `pathlib.Path`, `__future__.annotations`.

Внутри пакета:
- `. import backup as backup_mod` — восстановление и перечисление бэкапов (`restore_backup`, `list_backups`).
- `. import llm` — клиент LLM (`check_model`, исключение `LLMError` с полями `message`, `body`).
- `. import orchestrator` — конвейер обработки (`RunConfig`, `run`, `ConfigError`).

## Использование другими модулями проекта

Модуль — верхнеуровневая точка входа: сам импортирует `backup`, `llm`, `orchestrator`, но не предназначен для импорта из других модулей пакета (прикладной поток идёт через `orchestrator.run(RunConfig)`). Запускается как консольная команда `doxdix` (conscript) или через `python -m doxdix.cli` (блок `if __name__ == "__main__": sys.exit(main())`). Возвращаемый `main()` код используется оболочкой/CI как статус процесса.