# Конвейер (pipeline) — doxdix

## Назначение

Модуль реализует главный конвейер шагов 0–5 инструмента **doxdix**: сканирование проекта, резервное копирование, генерацию/обновление `CHANGELOG.md`, `README.md`, `SUMMARY.md`, пофайловый обход кода с генерацией `.md` модулей и финальный `SUMMARY.md`.

Все ошибки обработки отдельных файлов **не фатальны**: инкрементируют `RunStats.errors`, логируются, конвейер продолжается. Конфигурационные ошибки: в этом модуле `ConfigError` бросается, если `scanner.scan_grouped` выбросил `ValueError` (например, неверный `src_dir`). Остальные конфигурационные проверки (Ollama/модель/пути) выполняются в `cli.py` до вызова `run()`; при `ConfigError` CLI завершается с кодом 2 (ТЗ п. 5, 10). `ConfigError` не инкрементирует `errors`.

Версия файла: `dv_file_version = '261028.22'`.

## Публичный API

### `RunConfig` (dataclass)

Все параметры запуска, собираются из CLI (в `cli._build_run_config`).

| Поле | Тип | Назначение |
|---|---|---|
| `project_root` | `Path` | Корень проекта (нормализуется до абсолютного в `run()`). |
| `src_dir` | `str \| None` | Подкаталог исходников или `None`. |
| `docs_dir` | `str` | Каталог документации относительно корня. |
| `model`, `ollama_url`, `api_key` | `str` | Параметры Ollama. |
| `extensions`, `excludes` | `list[str]` | Фильтры сканирования. |
| `timeout`, `num_ctx`, `max_doc_tokens` | `int` | Лимиты LLM и размера доки. |
| `use_git`, `do_commit` | `bool` | Использовать git / делать коммиты. |
| `changelog_limit` | `int` | Сколько коммитов брать для CHANGELOG. |
| `changelog_llm`, `do_changelog`, `changelog_append` | `bool` | Опции CHANGELOG. |
| `backup_dir`, `backup_keep`, `do_backup` | `Path`, `int`, `bool` | Опции бэкапа. |
| `init_license` | `bool` | Создать MIT-LICENSE при отсутствии. |
| `do_readme` | `bool = True` | Обновлять README. |
| `monorepo` | `bool = True` | `False` — плоская структура `docs_dir/<rel>.md`. |
| `force` | `bool = False` | Игнорировать `.doxdix/cache.json`. |
| `log_file` | `Path \| None = None` | Не используется в `run()`, заполняется в CLI. |

### `RunStats` (dataclass)

Счётчики и артефакты прогона: `success`, `errors`, `skipped`, `backup_created: Path | None`, `license_created: bool`.

### `run(cfg: RunConfig) -> RunStats`

Выполняет конвейер шагов 0–5. Нормализует `project_root` через `.resolve()`, чтобы все шаги видели абсолютный путь. Возвращает `RunStats`. Бросает `ConfigError`, если `scanner.scan_grouped` выбрасывает `ValueError` из-за неверного пути (ловушка в CLI → код 2).

### `ConfigError(Exception)`

Ошибка конфигурации. В отличие от ошибок обработки файлов, **не** инкрементирует `errors`.

## Внутренние функции

### Утилиты

- `_read_text(path: Path) -> str` — чтение UTF-8, при ошибке `""` + warning.
- `_write_text(path: Path, content: str) -> bool` — запись UTF-8 с созданием родительских папок; `False` при `OSError`.
- `_estimate_tokens(text: str) -> int` — `len(text) // 4`.
- `_strip_implicit_src_root(rel: Path) -> Path` — срезает первый компонент, если это `src` (см. `_IMPLICIT_SRC_ROOTS`).
- `_md_path_for(code_file, subproject, project_root, src_dir, docs_dir) -> Path` — правило зеркалирования код → `.md`. В монорежиме: `docs_dir/<subproject>/<rel>.md` (для корневого проекта обёртка `root` не добавляется). В плоском режиме: путь считается от `src_dir` или от корня с отрезанием implicit-src. При файле вне корня подпроекта логирует warning и считает путь от `project_root`.
- `_git_commit(project_root, paths, message, do_commit, has_git=True)` — `git add` + `git commit`; ошибки — warning, не фатальны. Коммит только при `do_commit and has_git`.
- `_file_list_for_prompt(files, project_root) -> str` — относительные пути через `\n`.
- `_recent_commits_for_prompt(commits, limit=10) -> str` — последние N коммитов для промпта README; при отсутствии — `(нет данных git)`.
- `_strip_code_fence(text) -> str` — убирает обрамляющие ` ```markdown … ``` ` из ответа LLM.
- `_project_context(project_root, limit=2000) -> str` — первые `limit` символов `README.md`; если README нет — пустая строка.

### CHANGELOG (шаг 1)

- `_changelog_body_llm(cfg, git_data) -> str | None` — тело `[Unreleased]` через LLM (`--changelog-llm`). Сначала парсит и группирует коммиты через `changelog_gen.parse_commits` / `format_grouped`. На ошибке LLM, пустом ответе или пустой группировке — `None`, используется детерминированный вариант.
- `_step_changelog(cfg, git_data, stats)` — генерирует/дополняет `CHANGELOG.md` через `changelog_gen.generate`. Пропускается, если `--no-changelog` или нет git. При ошибке генерации/записи — `errors += 1`. При изменении делает git-коммит `docs(doxdix): update CHANGELOG.md`.

### README (шаг 2)

- `_step_readme(cfg, files, git_data, stats)` — обновляет `README.md` через LLM, снимает code fence, вставляет ссылку на LICENSE. При ошибке LLM — `errors += 1` и выход из шага. При изменении делает git-коммит `docs(doxdix): update README.md`.
- `_detect_license_type(license_path) -> str | None` — тип лицензии по первым 20 строкам (MIT, Apache 2.0, GPL, BSD), иначе `None`.
- `_inject_license_link(project_root, readme) -> str` — добавляет секцию «Лицензия» в конец README, если в README ещё нет ссылки на `LICENSE` (по `_LICENSE_LINK_RE`) и файл существует. Тип лицензии определяется `_detect_license_type`, иначе выводится просто ссылка на файл.

### SUMMARY (шаги 3 и 5)

- `_summary_path(cfg) -> Path` — всегда `<project_root>/docs/SUMMARY.md` независимо от `docs_dir`.
- `_module_doc_files(cfg) -> list[Path]` — все `.md` из `docs_dir` (кроме файлов с именем `SUMMARY.md`), отсортированы по `as_posix()`.
- `_collect_modules_content(paths, project_root) -> str` — собирает содержимое `.md` с лимитами `_SUMMARY_DOC_MAX_CHARS_PER_FILE = 2000` на файл и `_SUMMARY_DOCS_TOTAL_CHARS = 40000` суммарно; не влезшие файлы перечисляются путями. Формат блока: `### <путь относительно docs/>` + текст. Для путей вне `docs/` используется путь от `project_root`, затем имя файла. Пустые/нечитаемые файлы пропускаются; если данных нет — `""`.
- `_step_summary(cfg, files, md_files, stats, final=False, has_git=True)`:
  - `final=False` — шаг 3, передаёт содержимое существующих `.md`; при отсутствии — фолбэк на список файлов кода;
  - `final=True` — шаг 5, передаёт содержимое созданных/обновлённых `.md`; если их нет или содержимое пусто — шаг пропускается.
  - При ошибке LLM/записи — `errors += 1`. При изменении делает git-коммит `docs(doxdix): update SUMMARY.md` или `docs(doxdix): finalize SUMMARY.md`.

### Обход файлов (шаг 4)

`_step_modules(cfg, files_by_subproject, stats, cache, has_git=True) -> list[Path]`

Обходит файлы кода и генерирует/обновляет `.md` для каждого. Строит плоский план `(subproject | None, code_path, sub_root)`; в монорежиме логирует число файлов по подпроектам. Для каждого файла:

1. Вычисляет `sha = cache_mod.file_sha256(code_path)` **до** чтения текста.
2. Если хэш совпадает с кэшем, `.md` существует и `not cfg.force` — пропуск без обращения к LLM (`skipped++`).
3. Ошибка чтения UTF-8 → `errors++`, продолжение.
4. Пустой/пробельный файл → `skipped++`.
5. Существующий `.md` с оценкой токенов выше `max_doc_tokens` → `skipped++`.
6. LLM-вызов; при ошибке `errors++`.
7. Совпадение с `existing` → `skipped++` и обновление хэша в кэше (если `sha` получен).
8. Иначе запись, `created.append`, `success++`, `cache.set` (если `sha` получен), git-commit.

Ключ кэша: в монорежиме `<subproject>/<rel_in_sub>`, в плоском — путь от корня проекта. Возвращает список созданных/обновлённых путей `.md`. В логах шага используется этот же ключ как метка файла.

### Служебные

- `_init_license_if_requested(cfg, stats)` — создаёт MIT-заготовку `LICENSE`, если `--init-license` и файла ещё нет. `license_created=True`; при ошибке записи — `errors += 1`.
- `_current_year() -> int` — текущий год (для текста MIT).

## Главный конвейер `run(cfg)`

1. **Шаг 0** — `scanner.scan_grouped(...)`; `ValueError` → `ConfigError`. Формирует плоский список `files` для промптов README/SUMMARY. Пустой результат — warning, конвейер продолжается.
2. **`--init-license`** — до README, чтобы ссылка ставилась на существующий файл (в бэкап LICENSE не входит).
3. **Шаг 0.5** — `backup_mod.create_backup(...)` при `do_backup`; ошибки — `errors++`.
4. **Шаг 1** — `_step_changelog`.
5. **Шаг 2** — `_step_readme` (или пропуск при `--no-readme`).
6. **Шаг 3** — `_step_summary(final=False)`.
7. **Шаг 4** — `_step_modules` с предварительной загрузкой `cache_mod.Cache.load(project_root)` и `cache.save()` после.
8. **Шаг 5** — `_step_summary(final=True)` по `created_md`.
9. Итоговая сводка — в `cli._cmd_run` (не дублируется).

## Постоянные модуля

- `_LICENSE_LINK_RE` — регэксп поиска ссылки `[…](LICENSE)` в README.
- `_LICENSE_DETECT_LINES = 20` — сколько строк LICENSE читать для детекта типа.
- `_SUMMARY_DOCS_TOTAL_CHARS = 40000`, `_SUMMARY_DOC_MAX_CHARS_PER_FILE = 2000` — лимиты контекста SUMMARY.
- `_IMPLICIT_SRC_ROOTS = frozenset({"src"})` — корни, отрезаемые от путей в плоском режиме.

## Зависимости

Внутренние модули пакета (по импортам):

- `.backup` (`create_backup`) — резервное копирование документации;
- `.cache` (`Cache`, `file_sha256`) — кэш хэшей `.doxdix/cache.json`;
- `.changelog_gen` (`generate`, `parse_commits`, `format_grouped`) — детерминированная генерация CHANGELOG;
- `.llm` (`chat`, `LLMError`) — вызов Ollama;
- `.prompts` (`README_PROMPT`, `MODULE_PROMPT`, `SUMMARY_PROMPT`, `SUMMARY_FINAL_PROMPT`, `CHANGELOG_LLM_PROMPT`, `render`);
- `.scanner` (`scan_grouped`, `subproject_root`, `GitData`, `GitCommit`).

Стандартная библиотека: `logging`, `re`, `subprocess`, `time`, `dataclasses.dataclass/replace`, `pathlib.Path`, `datetime.datetime` (внутри `_current_year`).

## Использование другими модулями

- **`cli.py`** — основной внешний потребитель публичного API: собирает `RunConfig`, вызывает `run(cfg)`, ловит `ConfigError` (возврат кода 2) и выводит итоговую сводку в `_cmd_run`. См. комментарии в `RunConfig.log_file` (`cli._build_run_config`).
- Модуль сам является оркестратором для `scanner`, `backup`, `changelog_gen`, `prompts`, `llm`, `cache` — они не зависят от pipeline и вызываются из него.

## Ограничения и заметки

- **Не фатальные ошибки файлов:** любая ошибка чтения/LLM/записи отдельного файла → `errors++`, файл пропускается, конвейер идёт дальше. Фатален только некорректный путь при сканировании (`ConfigError`).
- **Коммиты:** только при `do_commit == True` **и** наличии git (`has_git`); отсутствие git — warning, не ошибка.
- **README без изменений:** сравнение с `existing`, при равенстве запись и коммит не выполняются.
- **SUMMARY финальный** не перегенерируется, если на шаге 4 не было создано/изменено ни одного `.md`, а также если собранное содержимое пусто.
- **Кэш:** при совпадении хэша и наличии `.md` файл не читается как UTF-8 и не уходит в LLM. При совпадении результата LLM с `existing` хэш фиксируется, чтобы не вызывать LLM повторно.
- **`RunStats` не содержит** полного пути лога — итоговая строка выводится в CLI.
- Все обращения к LLM выполняются с параметрами `cfg.ollama_url`, `cfg.model`, `cfg.num_ctx`, `cfg.timeout`, `cfg.api_key`.
- Пути кода предполагаются внутри `project_root` и корня подпроекта: `_step_modules` вычисляет `code_rel`/`rel_in_sub` через `relative_to` без fallback (fallback есть только в `_md_path_for`). При рассинхроне группировки возможен `ValueError`.