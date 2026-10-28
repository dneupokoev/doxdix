# Модуль `cli` (doxdix)

## Назначение

Модуль реализует CLI-интерфейс `doxdix`: разбор аргументов через `argparse`, настройку логирования, проверку доступности LLM и модели, восстановление из бэкапа, сборку `orchestrator.RunConfig` и запуск основного конвейера обработки проекта.

Публичный API:

- `main(argv: list[str] | None = None) -> int`

Модуль является точкой входа CLI. При запуске как скрипт вызывает `sys.exit(main())`.

## Коды возврата

| Код | Значение |
|---:|---|
| `0` | Успех, в том числе успешные `--check` и `--restore` |
| `1` | Были ошибки при обработке файлов |
| `2` | Ошибка конфигурации: нет LLM/модели, неверный `PROJECT_PATH`, отсутствует `--model` и `DOXDIX_MODEL`, неверный timestamp для `--restore` и т.п. |

## Основные функции

### `main(argv=None) -> int`

Точка входа и диспетчеризация режимов.

Аргументы:

- `argv` — необязательный список аргументов командной строки; если `None`, используется `sys.argv`.

Поведение:

1. Собирает parser.
2. Проверяет, что `PROJECT_PATH` существует и является директорией.
3. Разрешает путь через `expanduser()` и `resolve()`.
4. Если указан `--restore`, настраивает логирование и вызывает `_cmd_restore()` без проверки LLM.
5. Если указан `--check`, вызывает `_cmd_check()`.
6. Иначе запускает основной конвейер через `_cmd_run()`.

### `_build_parser() -> argparse.ArgumentParser`

Создаёт CLI-parser `doxdix` со всеми аргументами. Позиционный аргумент — `PROJECT_PATH`.

Группы аргументов:

- пути и файлы: `--src-dir`, `--docs-dir`, `--no-monorepo`, `--extensions`, `--exclude`;
- LLM: `--model`, `--ollama-url`, `--api-key`, `--timeout`, `--num-ctx`, `--max-doc-tokens`;
- git: `--no-git`, `--no-commit`, `--changelog-limit`, `--changelog-llm`, `--no-changelog`, `--no-changelog-append`;
- бэкапы: `--backup-dir`, `--backup-keep`, `--no-backup`, `--restore`;
- прочее: `--init-license`, `--force`, `--check`, `--no-readme`, `--log-file`.

Значения по умолчанию:

- `DEFAULT_OLLAMA_URL = "http://localhost:11434"`;
- `DEFAULT_EXTENSIONS = ".py,.js,.ts,.jsx,.tsx,.go,.rs"`;
- `DEFAULT_EXCLUDES` включает `.git`, `.doxdix`, `node_modules`, `__pycache__`, `venv`, `.venv`, `env`, `dist`, `build`, `tests`, `test`, `.mypy_cache`, `.pytest_cache`, `.ruff_cache`, `target`;
- `--docs-dir` — `docs/modules`;
- `--timeout` — `300`;
- `--num-ctx` — `8192`;
- `--max-doc-tokens` — `3000`;
- `--changelog-limit` — `100`;
- `--backup-keep` — `10`.

Особенность: при явной передаче `--exclude` значение флага заменяет `DEFAULT_EXCLUDES`, а не дополняет его, так как `_split_list(args.exclude)` разбирает только переданную строку.

### `_setup_logging(log_file: Path) -> None`

Настраивает корневой logger.

Аргументы:

- `log_file` — путь к файлу лога.

Поведение:

- устанавливает уровень `INFO`;
- удаляет предыдущие root-handlers, чтобы `main()` можно было повторно вызывать в тестах;
- добавляет вывод в `sys.stdout`;
- добавляет файловый handler в режиме append с кодировкой UTF-8;
- формат: `%(asctime)s [%(levelname)s] %(message)s`;
- при `OSError` при открытии файла пишет warning и продолжает работу только со stdout.

### `_resolve_model(arg_value: str | None) -> str | None`

Определяет имя модели.

Приоритет:

1. `--model`;
2. переменная окружения `DOXDIX_MODEL`;
3. `None`, если модель не задана.

### `_resolve_url(arg_value: str | None) -> str`

Определяет URL LLM.

Приоритет:

1. `--ollama-url`;
2. `DOXDIX_OLLAMA_URL`;
3. `DEFAULT_OLLAMA_URL`.

У результата удаляется завершающий `/`.

### `_resolve_api_key(arg_value: str | None) -> str`

Определяет API-ключ.

Приоритет:

1. `--api-key`;
2. `DOXDIX_API_KEY`;
3. `"dummy"`.

Если `arg_value` передан и не равен `None`, возвращается он, даже если это пустая строка.

### `_split_list(value: str) -> list[str]`

Разбивает строку по запятым, обрезает пробелы и отбрасывает пустые элементы.

### `_cmd_check(args: argparse.Namespace) -> int`

Режим `--check`: проверяет LLM и наличие модели.

Аргументы:

- `args` — разобранные аргументы CLI.

Поведение:

- разрешает модель, URL и API-ключ;
- если модель не задана — код `2`;
- вызывает `llm.check_model(url, model, timeout=10, api_key=key)`;
- при `llm.LLMError` печатает ошибку и тело ответа, возвращает `2`;
- если сервер вернул непустой список моделей и нужной модели нет — печатает доступные модели и возвращает `2`;
- если список моделей пустой, ошибка отсутствия модели не возникает;
- при успехе печатает OK и возвращает `0`.

### `_cmd_restore(args: argparse.Namespace, project_root: Path) -> int`

Режим `--restore`: восстанавливает файлы из бэкапа.

Аргументы:

- `args` — аргументы CLI;
- `project_root` — разрешённый корень проекта.

Поведение:

- определяет `backup_dir`: `--backup-dir` или `<project_root>/.doxdix/backups`;
- вызывает `backup_mod.restore_backup(project_root, backup_dir, args.restore)`;
- если бэкап не найден, выводит доступные бэкапы через `backup_mod.list_backups(backup_dir)` и возвращает `2`;
- при успехе печатает количество восстановленных файлов и возвращает `0`.

### `_build_run_config(args: argparse.Namespace, project_root: Path) -> orchestrator.RunConfig`

Собирает `orchestrator.RunConfig` из аргументов CLI и переменных окружения.

Аргументы:

- `args` — аргументы CLI;
- `project_root` — корень проекта.

Поведение:

- разрешает модель, URL, API-ключ;
- вычисляет `backup_dir` по умолчанию: `<project_root>/.doxdix/backups`;
- вычисляет `log_file` по умолчанию: `<project_root>/doxdix.log`;
- разбирает `extensions` и `excludes` через `_split_list`;
- переносит флаги CLI в поля `RunConfig`;
- `do_commit` включается только если не указаны `--no-commit` и `--no-git`;
- `do_readme` равен `not args.no_readme`;
- ожидает, что модель уже проверена вызывающей стороной; использует `assert model is not None`.

### `_cmd_run(args: argparse.Namespace, project_root: Path) -> int`

Основной режим запуска.

Аргументы:

- `args` — аргументы CLI;
- `project_root` — корень проекта.

Поведение:

1. Собирает `RunConfig`.
2. Настраивает логирование.
3. Логирует проект, модель и URL.
4. Выполняет предварительную проверку LLM и модели через `llm.check_model(..., timeout=10, ...)`.
5. При `llm.LLMError` логирует ошибку и возвращает `2`.
6. Если сервер вернул непустой список моделей и нужной модели нет — логирует ошибку и возвращает `2`.
7. Вызывает `orchestrator.run(cfg)`.
8. При `orchestrator.ConfigError` логирует ошибку конфигурации и возвращает `2`.
9. Возвращает `0`, если `stats.errors == 0`, иначе `1`.

## Зависимости

Стандартная библиотека:

- `argparse`;
- `logging`;
- `os`;
- `sys`;
- `pathlib.Path`.

Внутренние модули пакета:

- `.backup as backup_mod` — функции `restore_backup`, `list_backups`;
- `.llm` — функция `check_model`, исключение `LLMError`;
- `.orchestrator` — класс `RunConfig`, функция `run`, исключение `ConfigError`.

Константы модуля:

- `dv_file_version = '261028.17'`;
- `DEFAULT_OLLAMA_URL`;
- `DEFAULT_EXTENSIONS`;
- `DEFAULT_EXCLUDES`.

## Использование другими модулями проекта

В предоставленном коде другие модули не импортируют `cli`. Модуль предназначен для использования как точка входа CLI: через `main()` или через запуск модуля как скрипта.

`main()` возвращает целочисленный код вместо прямого вызова `sys.exit`, что удобно для тестирования и программного вызова. Внутри модуль выступает координатором:

- `llm` используется для проверки доступности LLM и модели;
- `backup_mod` используется для восстановления из бэкапа и просмотра списка бэкапов;
- `orchestrator` используется для сборки `RunConfig` и запуска основного конвейера обработки проекта.

## Особенности поведения

- `--restore` обрабатывается до проверки LLM: для восстановления доступность LLM не требуется.
- `--check` не настраивает файловое логирование, а выводит результат в stdout/stderr.
- Для `--restore` и основного запуска логирование настраивается в файл.
- `_setup_logging()` очищает существующие root-handlers, что важно при повторных вызовах `main()` в тестах.
- Проверка модели считается успешной, если сервер вернул пустой список моделей: ошибка возникает только когда список непустой и нужной модели в нём нет.
- `--no-git` отключает не только чтение git-логов, но и коммиты.
- `--no-changelog` отключает генерацию CHANGELOG.
- `--no-changelog-append` переключает CHANGELOG с дополнения на перезапись.