# Архитектура doxdix

Документ для тех, кто хочет **понять, как устроен doxdix**, и **вносить
изменения**: разработчиков, ИИ-ассистентов, ревьюеров.

Если вы просто хотите **использовать** doxdix — читайте [README.md](README.md).
Здесь — внутреннее устройство.

## Назначение и границы

**doxdix** — локальный CLI, который генерирует и актуализирует документацию
проекта с помощью LLM.

**Что делает:**
- пофайлово обходит исходный код;
- генерирует/обновляет `README.md`, `CHANGELOG.md`, `docs/SUMMARY.md`,
  `docs/modules/**/*.md`;
- сохраняет вручную написанные разделы существующей документации;
- делает бэкап перед изменениями;
- коммитит каждый шаг в git (опционально).

**Чего не делает:**
- не запускает код проекта, не тестирует его;
- не строит граф зависимостей между модулями (только читает импорты);
- не работает с бинарниками, изображениями, ассетами;
- не является надстройкой над Aider — работает напрямую с LLM HTTP API.

**Внешние зависимости:** только `requests>=2.31`. Всё остальное — stdlib.

## Раскладка модулей

```
src/doxdix/
├── __init__.py          # версия пакета
├── cli.py               # argparse, main(), --check, --restore, диспетчеризация
├── scanner.py           # обход файлов, исключения, git-данные
├── backup.py            # создание/восстановление/ротация бэкапов
├── changelog_gen.py     # парсер Conventional Commits + генератор Markdown
├── llm.py               # HTTP-клиент: Ollama (/api/*) и OpenAI (/v1/*)
├── prompts.py           # 4 шаблона промптов + render()
└── orchestrator.py      # конвейер шагов 0–5, логирование, коммиты
```

**Принцип:** каждый модуль можно тестировать **без LLM** (кроме `llm.py`,
которому нужен HTTP). `orchestrator.py` — единственный, кто знает про
**все** остальные модули; остальные друг о друге не знают.

## Поток данных (шаги 0–5)

```
                    ┌─────────────────┐
   PROJECT_PATH ──▶ │  scanner.scan() │ ──▶ files: list[Path]
                    │                 │ ──▶ git_data: GitData
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │ backup.create() │ ──▶ .doxdix/backups/<ts>/
                    └────────┬────────┘
                             │
                             ▼
   ┌─────────────────────────────────────────────────────────┐
   │  Шаг 1: CHANGELOG.md                                    │
   │  changelog_gen.generate(git_data.commits, existing)     │
   └────────────────────────┬────────────────────────────────┘
                            │
                            ▼
   ┌─────────────────────────────────────────────────────────┐
   │  Шаг 2: README.md                                       │
   │  prompts.README_PROMPT + llm.chat()                     │
   │  + _inject_license_link() (детерминированно)            │
   └────────────────────────┬────────────────────────────────┘
                            │
                            ▼
   ┌─────────────────────────────────────────────────────────┐
   │  Шаг 3: docs/SUMMARY.md (init)                          │
   │  prompts.SUMMARY_PROMPT + llm.chat()                    │
   └────────────────────────┬────────────────────────────────┘
                            │
                            ▼
   ┌─────────────────────────────────────────────────────────┐
   │  Шаг 4: обход файлов                                    │
   │  для каждого code_path:                                 │
   │    md_path = зеркало(code_path)                         │
   │    prompts.MODULE_PROMPT + llm.chat()                   │
   │    _strip_code_fence() перед записью                    │
   └────────────────────────┬────────────────────────────────┘
                            │
                            ▼
   ┌─────────────────────────────────────────────────────────┐
   │  Шаг 5: docs/SUMMARY.md (final)                         │
   │  prompts.SUMMARY_PROMPT со списком созданных .md        │
   └────────────────────────┬────────────────────────────────┘
                            │
                            ▼
                    RunStats (success/errors/skipped)
                    ──▶ код возврата 0/1/2
```

**Правило зеркалирования** (`_md_path_for`):

```
src/auth/login.py      ──▶ docs/modules/auth/login.md
src/api/v1/users.ts    ──▶ docs/modules/api/v1/users.md
main.go (src_dir=None) ──▶ docs/modules/main.md
```

Относительный путь от `--src-dir` (или от `PROJECT_PATH`, если не задан) +
префикс `--docs-dir` (по умолчанию `docs/modules`) + расширение `.md`.

**`SUMMARY.md` — всегда `docs/SUMMARY.md`**, независимо от `--docs-dir`.
Причина: это оглавление проекта, а не модульная дока.

## Ключевые решения

### 1. Два режима LLM: Ollama + OpenAI-совместимый

`llm.py` определяет режим по URL:
- URL оканчивается на `/v1` или содержит `/v1/` → **OpenAI-режим**
  (`/chat/completions`, `/models`, `Authorization: Bearer <key>`);
- иначе → **Ollama-режим** (`/api/chat`, `/api/tags`, без auth).

**Почему:** ТЗ требует Ollama, но на практике популярны vLLM, LM Studio,
OpenRouter, opencode, DeepSeek. Один клиент — два протокола.

**`num_ctx`** передаётся только в Ollama-режиме (OpenAI-серверы его не
понимают). В OpenAI-режиме — игнорируется.

**404 на `/v1/models`** — не фатален (некоторые прокси его не реализуют).
`check_model` возвращает `[]`, `cli.py` пропускает проверку имени модели.

### 2. Фильтрация по `git ls-files`

Если git доступен и не передан `--no-git` — обрабатываются **только
отслеживаемые файлы**. Неотслеживаемые (черновики, `egg-info`, `__pycache__`,
локальные заметки) — **пропускаются**.

**Почему:** не хотим генерировать доку по мусору, который пользователь ещё
не закоммитил. Если git нет — обход файловой системы с теми же фильтрами.

### 3. `_strip_code_fence` — срезание обёртки

Модели часто возвращают markdown, обёрнутый в ` ```markdown … ``` `, даже
если просили «только текст». `_strip_code_fence` в `orchestrator.py`
срезает первую и последнюю строки, если они начинаются/кончаются на ` ``` `.

**Применяется** в `_step_readme`, `_step_summary`, `_step_modules` — перед
записью файла.

### 4. `project_context` в промптах README/SUMMARY

Первые ~2000 символов `README.md` передаются в `SUMMARY_PROMPT` и
`README_PROMPT`. Без этого модель **выдумывает** назначение проекта
(реальный случай: «doxdix — диалоги врачей и пациентов»).

**Почему:** модель должна опираться на факты из README, а не на название
проекта.

### 5. Детерминированная вставка ссылки на LICENSE

LLM **не просят** добавлять раздел про лицензию. После ответа модели
`_inject_license_link` вставляет раздел в конец README:
- если `LICENSE` нет — ничего;
- если ссылка на `LICENSE` уже есть — не трогает;
- иначе — определяет тип лицензии по первым 20 строкам и вставляет
  `[MIT](LICENSE)` / `[Apache 2.0](LICENSE)` / `[GPL](LICENSE)` /
  `[BSD](LICENSE)` или общий `[LICENSE](LICENSE)`.

**Почему:** ссылка на лицензию — детерминированная, не должна зависеть
от фантазии модели.

### 6. SUMMARY без раздела «Лицензия»

В `SUMMARY_PROMPT` — явный запрет: «НЕ добавляй раздел про лицензию».
`docs/SUMMARY.md` — это **оглавление**, а не README. Лицензия — в README.

### 7. `--no-readme`

Флаг `--no-readme` пропускает шаг 2. Используется, когда README пишется
**вручную** (например, для самого doxdix) и LLM не должна его трогать.

## Как расширять

### Добавить новый шаг в конвейер

1. Написать `_step_xxx(cfg, ..., stats)` в `orchestrator.py`.
2. Вызвать его из `run()` в нужном порядке.
3. Добавить промпт в `prompts.py` (если нужен LLM).
4. Добавить флаг в `cli.py` + поле в `RunConfig` (если шаг опционален).
5. Обновить `README.md` (раздел «Как это работает») и этот файл.

### Добавить новый протокол LLM

1. В `llm.py` — функция `_chat_xxx(base_url, ...) -> str` и
   `_check_xxx(base_url, ...) -> list[str]`.
2. В `_is_xxx_mode(base_url)` — детектор по URL.
3. В `chat()` и `check_model()` — ветка `if _is_xxx_mode(...)`.

### Добавить новый язык в `--extensions`

Ничего менять не надо — список расширений уже параметризован. Просто
добавьте через `--extensions .py,.js,.ts,.rs,.go,.rb` при запуске.

### Изменить формат CHANGELOG

`changelog_gen.py`: `TYPE_TO_SECTION` (маппинг type → секция),
`SECTION_ORDER` (порядок секций), `_build_unreleased_block` (шапка).

### Изменить зеркалирование

`orchestrator._md_path_for(code_file, project_root, src_dir, docs_dir)` —
единственное место.

## Тестирование

Каждый модуль можно проверить **без LLM**:

```bash
# scanner: обход файлов + git-данные
python -c "import sys; sys.path.insert(0,'src'); \
  from doxdix.scanner import scan; \
  files, git = scan(__import__('pathlib').Path('.'), 'src', ['.py'], [], True, 100); \
  print(len(files), git.has_git)"

# backup: создать/восстановить/ротировать
python -c "import sys; sys.path.insert(0,'src'); \
  from doxdix.backup import create_backup, restore_backup, list_backups; \
  from pathlib import Path; \
  print(create_backup(Path('.'), Path('.doxdix/backups'), 3))"

# changelog_gen: парсер + генератор
python -c "import sys; sys.path.insert(0,'src'); \
  from doxdix.changelog_gen import generate; \
  from doxdix.scanner import GitCommit; \
  print(generate([GitCommit('a'*40, 'feat: x', '')], '', True))"

# prompts: render
python -c "import sys; sys.path.insert(0,'src'); \
  from doxdix.prompts import render, MODULE_PROMPT; \
  print(render(MODULE_PROMPT, code_content='x=1', existing_content=''))"

# orchestrator: утилиты
python -c "import sys; sys.path.insert(0,'src'); \
  from doxdix.orchestrator import _strip_code_fence, _md_path_for; \
  print(_strip_code_fence('```md\n# x\n```'))"
```

Для `llm.py` нужен реальный HTTP-эндпоинт — `--check` в `cli.py` это и делает.

## Известные ограничения

- **Пофайловый обход** — LLM видит только один файл (+ `project_context`).
  Межфайловые связи — из импортов, угадываются.
- **`--max-doc-tokens`** — если существующий `.md` больше лимита, файл
  пропускается (защита от переполнения контекста).
- **`num_ctx`** — только для Ollama. В OpenAI-режиме игнорируется.
- **`_strip_code_fence`** — простая эвристика: только первая/последняя
  строка с ` ``` `. Вложенные ` ``` ` внутри кода не обрабатываются
  специально, но markdown-парсеры их и так понимают.
- **`_detect_license_type`** — по первым 20 строкам. Экзотические лицензии
  не распознаются → общая ссылка `[LICENSE](LICENSE)`.
- **Git-коммиты** — после каждого файла. На большом проекте — много
  коммитов. Используйте `--no-commit`, если не нужно.

## Связанные документы

- [README.md](README.md) — как использовать.
- [CHANGELOG.md](CHANGELOG.md) — история изменений.
- [docs/SUMMARY.md](docs/SUMMARY.md) — оглавление модульной документации.
- [docs/modules/](docs/modules/) — документация по каждому модулю.
- [AGENTS.md](AGENTS.md) — правила для ИИ-ассистентов в этом репозитории.
- [LICENSE](LICENSE) — MIT.
