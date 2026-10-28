# module: pipeline

## Назначение

Модуль реализует главный конвейер документации проекта (шаги 0–5): сканирование исходников, создание бэкапа, генерацию/обновление `CHANGELOG.md`, `README.md`, `docs/SUMMARY.md`, обход файлов кода с генерацией `.md`-описаний и финальную сборку `SUMMARY.md`. Все операции обработки файлов **нефатальны** — ошибка логируется, инкрементирует счётчик `errors` и конвейер продолжается. Конфигурационные ошибки (недоступен Ollama, не найдена модель, некорректные пути) фатальны и перехватываются на уровне `cli.py` до вызова `run()`.

Версия файла: `dv_file_version = '261028.10'`.

## Публичный API

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
| `log_file` | `Path` | путь лог-файла |

### `RunStats`

Поля:

- `success: int = 0` — успешно обработанные файлы;
- `errors: int = 0` — количество ошибок;
- `skipped: int = 0` — пропущенные (например, превышен лимит токенов);
- `backup_created: Path | None = None` — путь созданного бэкапа;
- `license_created: bool = False` — был ли создан LICENSE.

## Основные функции

### Главная точка входа

- **`run(cfg: RunConfig) -> RunStats`** — последовательно выполняет шаги 0 → 5, возвращает `RunStats`. Конвейер прерывается досрочно, только если не найдено ни одного файла кода или если сканер поднял `ValueError`.

### Шаги конвейера

- **`_step_changelog(cfg, git_data, stats)`** — шаг 1: генерация/дополнение `CHANGELOG.md` через `changelog_gen.generate`. Пропускается при `--no-changelog` или отсутствии git.
- **`_step_readme(cfg, files, git_data, stats)`** — шаг 2: обновление `README.md` через LLM (промпт `prompts.README_PROMPT`), затем детерминированная вставка ссылки на LICENSE.
- **`_step_summary(cfg, files, md_files, stats, final=False)`** — шаги 3 (init, по списку кода) и 5 (final, по списку сгенерированных `.md`). Всегда пишет в `docs/SUMMARY.md` независимо от `docs_dir`.
- **`_step_modules(cfg, files, stats) -> list[Path]`** — шаг 4: обход файлов кода, генерация/обновление `.md` для каждого через `prompts.MODULE_PROMPT`. Пропускает файлы, чья существующая дока превышает `max_doc_tokens` (инкрементирует `skipped`). Возвращает список созданных/обновлённых `.md`.

### Утилиты

- **`_read_text(path) -> str`** — чтение UTF-8; при ошибке возвращает `""` и пишет warning.
- **`_write_text(path, content) -> bool`** — запись UTF-8 с автосозданием родительских каталогов; `False` при `OSError`.
- **`_estimate_tokens(text) -> int`** — грубая оценка: `len(text) // 4`.
- **`_md_path_for(code_file, project_root, src_dir, docs_dir) -> Path`** — правило зеркалирования: относительный путь от `src_dir` (или `project_root`), префикс `docs_dir`, расширение → `.md`.
- **`_git_commit(project_root, paths, message, do_commit)`** — `git add` + `git commit`; ошибки логируются как warning.
- **`_file_list_for_prompt(files, project_root) -> str`** — относительные пути через `\n` для промптов.
- **`_recent_commits_for_prompt(commits, limit=10) -> str`** — последние N коммитов одной строкой.
- **`_strip_code_fence(text) -> str`** — срезает обрамляющие ` ```markdown ... ``` ` из ответа LLM.
- **`_project_context(project_root, limit=2000) -> str`** — первые 2000 символов `README.md` как контекст для промптов.

### Работа с лицензией

- **`_init_license_if_requested(cfg, stats)`** — при `init_license=True` создаёт MIT-заготовку, если `LICENSE` отсутствует (до бэкапа, чтобы файл попал в архив).
- **`_detect_license_type(license_path) -> str | None`** — тип лицензии по первым 20 строкам: `MIT`, `Apache 2.0`, `GPL`, `BSD`; иначе `None`.
- **`_inject_license_link(project_root, readme) -> str`** — добавляет раздел «Лицензия» в конец README, если ссылки на `LICENSE` ещё нет и сам файл существует.
- **`_current_year() -> int`** — текущий год для MIT-шаблона.

### Константы

- `_LICENSE_LINK_RE` — регэксп для детекта уже присутствующей ссылки на `LICENSE` в README.
- `_LICENSE_DETECT_LINES = 20` — число строк LICENSE для определения типа.

## Обработка ошибок

- Ошибки чтения/записи файлов, LLM-ошибки (`llm.LLMError`), ошибки git-коммитов — **нефатальны**: логируются, инкрементируют `stats.errors` (кроме git), конвейер продолжается.
- Ошибка сканера (`ValueError`) — прерывает `run()`, возвращается `RunStats` с `errors >= 1`.
- Конфигурационные проблемы (Ollama, модель, пути) должны перехватываться в `cli.py` **до** вызова `run()`.

## Зависимости

Импорты:

- `from . import backup as backup_mod` — создание/ротация бэкапов (`backup_mod.create_backup(project_root, backup_dir, backup_keep)`).
- `from . import changelog_gen` — генерация CHANGELOG (`changelog_gen.generate(commits, existing, append=...)`).
- `from . import llm` — обращение к LLM (`llm.chat(...)`, исключение `llm.LLMError`).
- `from . import prompts` — шаблоны промптов (`prompts.render`, `prompts.README_PROMPT`, `prompts.SUMMARY_PROMPT`, `prompts.MODULE_PROMPT`).
- `from . import scanner` — сканирование проекта (`scanner.scan(...)`, типы `scanner.GitData`, `scanner.GitCommit`).
- Стандартная библиотека: `logging`, `re`, `subprocess`, `dataclasses`, `pathlib`, локально `datetime`.

## Использование в проекте

Модуль является **оркестратором** конвейера. Его вызывает `cli.py`:

1. парсит аргументы и формирует `RunConfig`;
2. валидирует конфигурацию (Ollama, модель, пути) — при ошибке завершает работу до вызова `run()`;
3. вызывает `run(cfg)`, получает `RunStats` и использует счётчики для итогового лога и кода возврата.

Сам модуль напрямую зависит от `scanner`, `backup`, `changelog_gen`, `llm`, `prompts` — каждый отвечает за свой этап, тогда как `pipeline` связывает их в единый сценарий.