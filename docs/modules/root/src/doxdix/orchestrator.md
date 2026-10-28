# Конвейер документации doxdix

Версия файла: `dv_file_version = '261028.22'`.

## Назначение

Модуль реализует основной конвейер шагов 0–5:

0. сканирование файлов проекта;
0.5. создание бэкапа документации;
1. обновление `CHANGELOG.md`;
2. обновление `README.md`;
3. первичное формирование `docs/SUMMARY.md`;
4. обход файлов кода и генерация/обновление `.md`-документации модулей;
5. финальное обновление `docs/SUMMARY.md` по уже созданным/обновлённым `.md`.

Ошибки обработки отдельных файлов не фатальны: они логируются и увеличивают `RunStats.errors`, конвейер продолжается. Конфигурационные ошибки, например неверный `--src-dir`, приводят к `ConfigError`; предполагается, что CLI завершится с кодом 2.

## Публичный API

### `ConfigError`

Исключение для ошибок конфигурации запуска. Не инкрементирует `errors`; используется для сигнала CLI о фатальной ошибке конфигурации.

### `RunConfig`

Dataclass со всеми параметрами запуска, собранными из CLI.

Основные поля:

- `project_root: Path` — корень проекта. В `run()` нормализуется через `resolve()`.
- `src_dir: str | None` — исходный каталог, если задан.
- `docs_dir: str` — каталог документации относительно `project_root`.
- `model: str` — имя LLM-модели.
- `ollama_url: str` — URL Ollama.
- `api_key: str` — API-ключ для LLM.
- `extensions: list[str]` — расширения файлов кода.
- `excludes: list[str]` — пользовательские исключения.
- `timeout: int` — таймаут LLM.
- `num_ctx: int` — размер контекста LLM.
- `max_doc_tokens: int` — лимит токенов существующей документации модуля.
- `use_git: bool` — использовать данные git.
- `do_commit: bool` — делать git-коммиты.
- `changelog_limit: int` — лимит коммитов для CHANGELOG.
- `changelog_llm: bool` — переписывать блок `[Unreleased]` через LLM.
- `do_changelog: bool` — обновлять CHANGELOG.
- `changelog_append: bool` — дополнять CHANGELOG.
- `backup_dir: Path` — каталог бэкапов.
- `backup_keep: int` — сколько бэкапов хранить.
- `do_backup: bool` — создавать бэкап.
- `init_license: bool` — создать MIT-заготовку `LICENSE`, если файла нет.
- `do_readme: bool = True` — обновлять README.
- `monorepo: bool = True` — группировать документацию по подпроектам. При `False` используется плоская структура.
- `force: bool = False` — игнорировать `.doxdix/cache.json` и генерировать `.md` заново.
- `log_file: Path | None = None` — путь к логу; `run()` это поле не использует, значение задаётся в CLI.

### `RunStats`

Счётчики и результаты выполнения:

- `success: int` — успешно созданные/обновлённые `.md`;
- `errors: int` — количество нефатальных ошибок;
- `skipped: int` — пропущенные файлы;
- `backup_created: Path | None` — путь созданного бэкапа;
- `license_created: bool` — была ли создана лицензия.

### `run(cfg: RunConfig) -> RunStats`

Выполняет конвейер шагов 0–5 и возвращает `RunStats`.

Поведение:

- нормализует `project_root` через `resolve()`;
- вызывает `scanner.scan_grouped(...)`;
- при `ValueError` от сканера поднимает `ConfigError`;
- создаёт `LICENSE` при `--init-license`, если файла ещё нет;
- создаёт бэкап при `do_backup`;
- обновляет `CHANGELOG.md`, `README.md`, `docs/SUMMARY.md`;
- обходит файлы кода с учётом кэша;
- сохраняет кэш после шага 4;
- финально обновляет `docs/SUMMARY.md`;
- итоговую сводку не печатает, это делает `cli._cmd_run` по комментариям в коде.

## Основные внутренние функции

- `_read_text(path) -> str` — читает UTF-8, при ошибке возвращает пустую строку и пишет warning.
- `_write_text(path, content) -> bool` — создаёт родительские каталоги и пишет UTF-8; ошибка логируется, возвращается `False`.
- `_estimate_tokens(text) -> int` — грубая оценка токенов: `len(text) // 4`.
- `_strip_implicit_src_root(rel) -> Path` — отрезает первый компонент `src` для плоской раскладки без `--src-dir`.
- `_md_path_for(code_file, subproject, project_root, src_dir, docs_dir) -> Path` — вычисляет путь `.md` по правилам монорепо или плоской структуры.
- `_git_commit(project_root, paths, message, do_commit, has_git=True)` — выполняет `git add` и `git commit`; ошибки логируются как warning.
- `_file_list_for_prompt(files, project_root) -> str` — формирует список относительных путей для промптов.
- `_recent_commits_for_prompt(commits, limit=10) -> str` — последние коммиты для README-промпта.
- `_strip_code_fence(text) -> str` — удаляет обрамляющие markdown code fence из ответа LLM.
- `_project_context(project_root, limit=2000) -> str` — первые `limit` символов `README.md`.
- `_changelog_body_llm(cfg, git_data) -> str | None` — LLM-переписывание тела `[Unreleased]`; при ошибке возвращает `None`.
- `_step_changelog(cfg, git_data, stats)` — шаг CHANGELOG.
- `_step_readme(cfg, files, git_data, stats)` — шаг README.
- `_detect_license_type(license_path) -> str | None` — определяет MIT, Apache 2.0, GPL или BSD по первым 20 строкам.
- `_inject_license_link(project_root, readme) -> str` — добавляет раздел «Лицензия», если есть `LICENSE` и в README ещё нет ссылки на него.
- `_summary_path(cfg) -> Path` — всегда `docs/SUMMARY.md`.
- `_module_doc_files(cfg) -> list[Path]` — все `.md` из `docs_dir`, кроме `SUMMARY.md`, отсортированные по пути.
- `_collect_modules_content(paths, project_root) -> str` — собирает содержимое `.md` для SUMMARY с лимитами: до 2000 символов на файл и до 40000 символов суммарно; не влезшие файлы перечисляются путями.
- `_step_summary(cfg, files, md_files, stats, final=False, has_git=True)` — создаёт/обновляет `docs/SUMMARY.md`.
- `_step_modules(cfg, files_by_subproject, stats, cache, has_git=True) -> list[Path]` — обходит файлы кода и возвращает созданные/обновлённые `.md`.
- `_init_license_if_requested(cfg, stats)` — создаёт MIT-заготовку `LICENSE` при необходимости.
- `_current_year() -> int` — текущий год для MIT-заготовки.

## Шаги конвейера

### Шаг 0. Сканирование

Вызывается `scanner.scan_grouped(...)` с параметрами:

- `project_root`;
- `src_dir`;
- `extensions`;
- `user_excludes`;
- `use_git`;
- `changelog_limit`.

Результат: `files_by_subproject` и `git_data`. Если файлов не найдено, конвейер не останавливается: CHANGELOG, README и SUMMARY всё равно могут обновляться, а шаг 4 будет пустым.

### Создание LICENSE

При `init_license=True` создаётся MIT-заготовка, если `LICENSE` отсутствует. Если файл уже есть, шаг пропускается. Это выполняется до README, чтобы ссылка на лицензию ставилась на существующий файл.

### Шаг 0.5. Бэкап

При `do_backup=True` вызывается `backup_mod.create_backup(project_root, backup_dir, backup_keep)`. Неожиданная ошибка логируется и увеличивает `errors`, но конвейер продолжается.

### Шаг 1. CHANGELOG

Выполняется, если `do_changelog=True` и есть git.

- При `changelog_llm=True` тело `[Unreleased]` может быть переписано через LLM.
- При ошибке LLM используется детерминированная группировка.
- Вызывается `changelog_gen.generate(...)` с учётом `changelog_append`.
- Если содержимое не изменилось, запись и коммит не выполняются.
- При успехе возможен git-коммит `docs(doxdix): update CHANGELOG.md`.

### Шаг 2. README

Выполняется при `do_readme=True`.

- Формируется промпт из списка файлов, последних коммитов, текущего README и контекста проекта.
- Вызывается LLM.
- Ответ очищается от code fence.
- В README добавляется ссылка на `LICENSE`, если файл лицензии есть и ссылки ещё нет.
- При ошибке LLM увеличивается `errors`.
- При успешном изменении возможен git-коммит `docs(doxdix): update README.md`.

### Шаг 3. SUMMARY (init)

Создаёт или обновляет `docs/SUMMARY.md`.

- Собирает содержимое существующих `.md` из `docs_dir`.
- Если документации модулей ещё нет, передаёт LLM список файлов кода как fallback.
- Использует `SUMMARY_PROMPT`.
- При ошибке LLM увеличивается `errors`.
- При успешном изменении возможен git-коммит `docs(doxdix): update SUMMARY.md`.

### Шаг 4. Обход файлов кода

Для каждого файла:

- вычисляется путь `.md` по правилам `_md_path_for`;
- вычисляется ключ кэша:
  - в монорежиме: `<subproject>/<путь внутри подпроекта>`;
  - в плоском режиме: путь от корня проекта;
- вычисляется SHA-256 через `cache_mod.file_sha256`;
- если файл не менялся, `.md` существует и `force=False`, файл пропускается без чтения кода и LLM;
- если файл не читается как UTF-8, увеличивается `errors`;
- пустой файл пропускается и увеличивает `skipped`;
- если существующий `.md` превышает `max_doc_tokens`, файл пропускается;
- вызывается LLM с `MODULE_PROMPT`;
- ответ очищается от code fence;
- если содержимое не изменилось, файл считается пропущенным, хэш фиксируется в кэше;
- при успешной записи файл добавляется в список созданных/обновлённых, увеличивается `success`, обновляется кэш;
- возможен git-коммит `docs(doxdix): <путь к файлу кода>`.

При `force=True` кэш игнорируется, но успешные результаты всё равно записываются в кэш. После шага 4 вызывается `cache.save()`.

### Шаг 5. SUMMARY (final)

Финальное обновление `docs/SUMMARY.md`.

- Если на шаге 4 не было созданных/обновлённых `.md`, шаг пропускается.
- Содержимое собирается только по созданным/обновлённым `.md`.
- Используется `SUMMARY_FINAL_PROMPT`.
- Если содержимое пустое, шаг пропускается.
- При успешном изменении возможен git-коммит `docs(doxdix): finalize SUMMARY.md`.

## Правила раскладки документации

В режиме `monorepo=True`:

- документация размещается как `docs_dir/<subproject>/<путь от корня подпроекта>.md`;
- для корневого проекта в комментариях упоминается `subproject="root"`, например `src/doxdix/backup.py` может соответствовать `docs/modules/root/src/doxdix/backup.md`;
- если файл не находится под корнем подпроекта, путь считается от корня проекта, пишется warning.

В режиме `monorepo=False`:

- используется плоская структура `docs_dir/<rel>.md`;
- `rel` считается от `src_dir`, если он задан;
- иначе `rel` считается от `project_root`, а первый компонент `src` отрезается через `_strip_implicit_src_root`.

`docs/SUMMARY.md` всегда находится в `docs/SUMMARY.md`, независимо от `docs_dir`.

## Зависимости

Стандартная библиотека:

- `logging` — логирование;
- `re` — проверка ссылки на `LICENSE`;
- `subprocess` — git-команды;
- `time` — замер времени шага;
- `dataclasses.dataclass`, `dataclasses.replace` — конфиг и статистика;
- `pathlib.Path` — работа с путями.

Локальные модули:

- `backup` — создание бэкапов;
- `cache` — кэш SHA-256, `Cache`, `file_sha256`;
- `changelog_gen` — парсинг и генерация CHANGELOG;
- `llm` — вызов LLM, `LLMError`;
- `prompts` — шаблоны промптов;
- `scanner` — сканирование проекта, `GitData`, `GitCommit`, `subproject_root`.

## Использование другими модулями

Из самого файла не видно обратных импортов, но по docstring и комментариям модуль вызывается из `cli.py`:

- CLI собирает `RunConfig`;
- CLI вызывает `run(cfg)`;
- CLI обрабатывает `ConfigError` как конфигурационную ошибку с кодом возврата 2;
- CLI печатает итоговую сводку «Успешно: N, ошибок: M, пропущено: K. Лог: <path>»;
- `log_file` задаётся в `cli._build_run_config`, но `run()` его не использует.

## Ограничения и заметки

- Ошибки обработки файлов не фатальны и увеличивают `RunStats.errors`.
- Ошибки LLM в README, SUMMARY и модулях увеличивают `errors`; в CHANGELOG LLM-ошибка приводит к fallback на детерминированный вариант без увеличения `errors`.
- Git-коммиты выполняются только при `do_commit=True` и наличии git.
- В монорежиме ключ кэша включает подпроект, чтобы одинаковые относительные пути в разных подпроектах не конфликтовали.
- `--force` игнорирует кэш при проверке, но успешные генерации всё равно обновляют кэш.
- Пустые файлы кода не считаются ошибкой.
- Существующая документация модуля, превышающая `max_doc_tokens`, пропускается без вызова LLM.
- Ответы LLM очищаются от обрамляющих markdown code fence.
- Лимиты контекста SUMMARY: до 2000 символов на файл и до 40000 символов суммарно; не влезшие файлы перечисляются путями.