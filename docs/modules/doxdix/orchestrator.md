# module: pipeline

## Назначение

Модуль реализует главный конвейер документации проекта (шаги 0–5): сканирование исходников, создание бэкапа, генерацию/обновление `CHANGELOG.md`, `README.md`, `docs/SUMMARY.md`, обход файлов кода с генерацией `.md`-описаний и финальную сборку `SUMMARY.md`. Все операции обработки файлов **нефатальны** — ошибка логируется, инкрементирует счётчик `errors` и конвейер продолжается. Конфигурационные ошибки (недоступен Ollama, не найдена модель, некорректные пути) фатальны и перехватываются на уровне `cli.py` до вызова `run()`.

Версия файла: `dv_file_version = '261028.17'`.

## Публичный API

- `ConfigError` — исключение конфигурационной ошибки (неверный путь/`--src-dir`). `run()` пробрасывает его наружу, `cli` завершает работу с кодом 2.
- `RunConfig` — dataclass со всеми параметрами запуска (собираются из CLI).
- `RunStats` — dataclass со счётчиками и результатом.
- `run(cfg: RunConfig) -> RunStats` — выполнить конвейер.

### `RunConfig`

Поля-аргументы:

| Поле | Тип | Описание |
|---|---|---|
| `project_root` | `Path` | корень проекта |
| `src_dir` | `str \| None` | подкаталог с исходниками (для зеркалирования путей) |
| `docs_dir` | `str` | каталог документации относительно `project_root` |
| `model` | `str` | имя LLM-модели в Ollama |
| `ollama_url` | `str` | URL Ollama API |
| `api_key` | `str` | ключ API (если требуется) |
| `extensions` | `list[str]` | расширения обрабатываемых файлов |
| `excludes` | `list[str]` | исключаемые пути/паттерны |
| `timeout` | `int` | таймаут LLM-запроса |
| `num_ctx` | `int` | размер контекста модели |
| `max_doc_tokens` | `int` | лимит токенов существующей доки для пропуска |
| `use_git` | `bool` | использовать данные git |
| `do_commit` | `bool` | коммитить изменения |
| `changelog_limit` | `int` | сколько коммитов брать в CHANGELOG |
| `changelog_llm` | `bool` | генерировать CHANGELOG через LLM |
| `do_changelog` | `bool` | включать шаг CHANGELOG |
| `changelog_append` | `bool` | дополнять CHANGELOG вместо перезаписи |
| `backup_dir` | `Path` | каталог бэкапов |
| `backup_keep` | `int` | сколько бэкапов хранить |
| `do_backup` | `bool` | включать шаг бэкапа |
| `init_license` | `bool` | создать MIT-заготовку LICENSE при отсутствии |
| `do_readme` | `bool = True` | включать шаг README |
| `log_file` | `Path \| None` | путь лог-файла; `None` — дефолт `<project>/doxdix.log` достраивается в `cli`; `run()` это поле не использует |

### `RunStats`

Поля:

- `success: int = 0` — успешно обработанные файлы;
- `errors: int = 0` — количество ошибок;
- `skipped: int = 0` — пропущенные (например, превышен лимит токенов, пустой файл, содержимое не изменилось);
- `backup_created: Path | None = None` — путь созданного бэкапа;
- `license_created: bool = False` — был ли создан LICENSE.

## Основные функции

### Главная точка входа

- **`run(cfg: RunConfig) -> RunStats`** — нормализует `project_root` (`replace(cfg, project_root=cfg.project_root.resolve())`), последовательно выполняет шаги 0 → 5, возвращает `RunStats`. Пустой список файлов не прерывает конвейер: шаги 1–3 и 5 выполняются, шаг 4 просто не находит файлов. Если сканер поднял `ValueError`, `run()` бросает `ConfigError`.

Порядок выполнения: сканирование → `--init-license` → бэкап → CHANGELOG → README (если `do_readme`) → SUMMARY init → обход файлов → SUMMARY final. В конце логирует путь бэкапа, если он создан.

### Шаги конвейера

- **`_changelog_body_llm(cfg, git_data) -> str | None`** — при `--changelog-llm` переписывает сгруппированные коммиты через LLM (`prompts.CHANGELOG_LLM_PROMPT`). Использует `changelog_gen.parse_commits` и `changelog_gen.format_grouped`. При ошибке LLM, пустом ответе или отсутствии изменений возвращает `None` (используется детерминированная группировка).
- **`_step_changelog(cfg, git_data, stats)`** — шаг 1: генерация/дополнение `CHANGELOG.md` через `changelog_gen.generate`; при `--changelog-llm` тело `[Unreleased]` передаётся как `unreleased_block`. Пропускается при `--no-changelog` или отсутствии git. При ошибке генерации инкрементирует `stats.errors`. Пишет файл только при изменении, затем при необходимости делает git-коммит.
- **`_step_readme(cfg, files, git_data, stats)`** — шаг 2: обновление `README.md` через LLM (промпт `prompts.README_PROMPT`), затем детерминированная вставка ссылки на LICENSE. Вызывается из `run()` только при `cfg.do_readme`. При ошибке LLM инкрементирует `stats.errors`. Пишет файл только при изменении, затем при необходимости делает git-коммит.
- **`_step_summary(cfg, files, md_files, stats, final=False, has_git=True)`** — шаги 3 (init, промпт `SUMMARY_PROMPT`, по списку кода) и 5 (final, промпт `SUMMARY_FINAL_PROMPT`, по списку сгенерированных `.md`). В режиме `final` пути передаются относительно `docs/` (без префикса). Всегда пишет в `docs/SUMMARY.md` независимо от `docs_dir`. При ошибке LLM инкрементирует `stats.errors`.
- **`_step_modules(cfg, files, stats, has_git=True) -> list[Path]`** — шаг 4: обход файлов кода, генерация/обновление `.md` для каждого через `prompts.MODULE_PROMPT`. Пропускает пустые файлы, файлы с существующей докой больше `max_doc_tokens` и файлы, чьё содержимое не изменилось (инкрементирует `skipped`). Ошибки чтения кода, LLM и записи инкрементируют `errors`. Возвращает список созданных/обновлённых `.md`.

### Утилиты

- **`_read_text(path) -> str`** — чтение UTF-8; если путь не файл или произошла `OSError`/`UnicodeDecodeError`, возвращает `""` и пишет warning.
- **`_write_text(path, content) -> bool`** — запись UTF-8 с автосозданием родительских каталогов; `False` при `OSError`.
- **`_estimate_tokens(text) -> int`** — грубая оценка: `len(text) // 4`.
- **`_strip_implicit_src_root(rel: Path) -> Path`** — отрезает первый компонент пути, если это implicit src-корень из `_IMPLICIT_SRC_ROOTS` (сейчас `src`).
- **`_md_path_for(code_file, project_root, src_dir, docs_dir) -> Path`** — правило зеркалирования: относительный путь от `src_dir` (если задан) или от `project_root`; префикс `docs_dir`; расширение → `.md`. Без `--src-dir` первый компонент из `_IMPLICIT_SRC_ROOTS` отрезается.
- **`_summary_path(cfg) -> Path`** — всегда `project_root / "docs" / "SUMMARY.md"`.
- **`_docs_relative(path, project_root) -> str`** — путь относительно `docs/` в POSIX-виде для ссылок в финальном SUMMARY; при `ValueError` возвращает имя файла.
- **`_git_commit(project_root, paths, message, do_commit, has_git=True)`** — `git add` + `git commit` только при `do_commit` и `has_git`; таймаут 30 с; ошибки (`FileNotFoundError`, `TimeoutExpired`, `OSError`, ненулевой код) логируются как warning и не инкрементируют `errors`.
- **`_file_list_for_prompt(files, project_root) -> str`** — относительные пути через `\n` для промптов.
- **`_recent_commits_for_prompt(commits, limit=10) -> str`** — последние N коммитов строками `sha[:8] subject`; при отсутствии коммитов возвращает `(нет данных git)`.
- **`_strip_code_fence(text) -> str`** — срезает обрамляющие ` ```markdown ... ``` ` из ответа LLM, если ответ начинается с code fence.
- **`_project_context(project_root, limit=2000) -> str`** — первые `limit` символов `README.md` как контекст для промптов; если README нет — пустая строка.

### Работа с лицензией

- **`_init_license_if_requested(cfg, stats)`** — при `init_license=True` создаёт MIT-заготовку, если `LICENSE` отсутствует (до README, чтобы ссылка ставилась на существующий файл; в бэкап LICENSE не входит — ТЗ п. 6.2). При успехе выставляет `stats.license_created = True`.
- **`_detect_license_type(license_path) -> str | None`** — тип лицензии по первым 20 строкам: `MIT`, `Apache 2.0`, `GPL`, `BSD`; иначе `None`.
- **`_inject_license_link(project_root, readme) -> str`** — добавляет раздел «Лицензия» в конец README, если ссылки на `LICENSE` ещё нет и сам файл существует.
- **`_current_year() -> int`** — текущий год для MIT-шаблона (локальный импорт `datetime`).

### Константы

- `_LICENSE_LINK_RE` — регэксп для детекта уже присутствующей ссылки на `LICENSE` в README.
- `_LICENSE_DETECT_LINES = 20` — число строк LICENSE для определения типа.
- `_IMPLICIT_SRC_ROOTS` — `frozenset({"src"})`, каталоги-обёртки, отрезаемые при зеркалировании без `--src-dir`.

## Обработка ошибок

- Ошибки чтения/записи файлов кода, LLM-ошибки (`llm.LLMError`), ошибки генерации CHANGELOG, ошибки бэкапа и записи LICENSE — **нефатальны**: логируются, инкрементируют `stats.errors`, конвейер продолжается.
- Ошибки git-коммитов — только warning, `stats.errors` не инкрементируется.
- Пустой или состоящий из пробелов файл кода — не ошибка: `skipped += 1`, конвейер продолжается.
- Существующая дока больше `max_doc_tokens` или неизменившееся содержимое — `skipped += 1`.
- Ошибка сканера (`ValueError`) — `run()` бросает `ConfigError`, `cli` завершает работу с кодом 2.
- Конфигурационные проблемы (Ollama, модель, пути) перехватываются в `cli.py` **до** вызова `run()`.

## Зависимости

Импорты:

- `from . import backup as backup_mod` — создание/ротация бэкапов (`backup_mod.create_backup(project_root, backup_dir, backup_keep)`).
- `from . import changelog_gen` — генерация CHANGELOG (`changelog_gen.generate(...)`, `parse_commits`, `format_grouped`).
- `from . import llm` — обращение к LLM (`llm.chat(...)`, исключение `llm.LLMError`).
- `from . import prompts` — шаблоны промптов (`prompts.render`, `prompts.CHANGELOG_LLM_PROMPT`, `prompts.README_PROMPT`, `prompts.SUMMARY_PROMPT`, `prompts.SUMMARY_FINAL_PROMPT`, `prompts.MODULE_PROMPT`).
- `from . import scanner` — сканирование проекта (`scanner.scan(...)`, типы `scanner.GitData`, `scanner.GitCommit`).
- Стандартная библиотека: `logging`, `re`, `subprocess`, `time`, `dataclasses` (`dataclass`, `field`, `replace`), `pathlib`, локально `datetime`.

## Использование в проекте

Модуль является **оркестратором** конвейера. В самом файле не видно импортов `pipeline` другими модулями; по существующей архитектуре его вызывает `cli.py`:

1. парсит аргументы и формирует `RunConfig`;
2. валидирует конфигурацию (Ollama, модель, пути) — при ошибке завершает работу до вызова `run()`;
3. вызывает `run(cfg)`, получает `RunStats` и использует счётчики для итогового лога и кода возврата.

Сам модуль напрямую зависит от `scanner`, `backup`, `changelog_gen`, `llm`, `prompts` — каждый отвечает за свой этап, тогда как `pipeline` связывает их в единый сценарий.