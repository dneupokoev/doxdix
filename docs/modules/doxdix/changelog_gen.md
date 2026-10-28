# changelog_gen.py — парсер Conventional Commits и генератор CHANGELOG.md

## Назначение
Модуль изолированно разбирает коммиты Git в формате Conventional Commits, группирует их по секциям Keep a Changelog и формирует/обновляет текст `CHANGELOG.md` с секцией `[Unreleased]`. Используется для автоматической генерации changelog, включая подготовку тела `[Unreleased]` для режима `--changelog-llm`. Сам модуль не читает и не пишет файлы — только возвращает готовый текст.

## Публичный API
- `parse_commits(commits: list[GitCommit]) -> list[ParsedCommit]` — разбирает список коммитов, отбрасывает пропускаемые типы, логирует количество разобранных и пропущенных коммитов.
- `format_grouped(parsed: list[ParsedCommit]) -> str` — возвращает тело `[Unreleased]` без заголовков `# Changelog` и `## [Unreleased]`. Секции выводятся в фиксированном порядке `SECTION_ORDER`, пустые секции не выводятся. Используется для `--changelog-llm`.
- `generate(commits: list[GitCommit], existing_content: str, append: bool, unreleased_block: str | None = None) -> str` — генерирует полный текст `CHANGELOG.md`.
  - `commits` — список коммитов из `scanner.GitData.commits`.
  - `existing_content` — текущее содержимое `CHANGELOG.md` или пустая строка.
  - `append` — режим работы: `False` — полная перезапись, `True` — вставка/замена блока `[Unreleased]` в существующем содержимом. Значения по умолчанию в сигнатуре нет.
  - `unreleased_block` — готовое тело `[Unreleased]` (например, результат `--changelog-llm`). Если `None` или пусто — используется детерминированная группировка по секциям.
  - При `append=False` возвращает `# Changelog` + `[Unreleased]`.
  - При `append=True` и отсутствии подходящих коммитов, отсутствии LLM-тела и непустом `existing_content` возвращает существующее содержимое без изменений.

## Классы и внутренние функции
- `ParsedCommit(section: str, text: str, sha: str = "")` — frozen dataclass одного разобранного коммита: целевая секция, текст пункта, SHA.
- `_parse_commit(commit: GitCommit) -> ParsedCommit | None` — разбор одного коммита:
  - пустой `subject` → пропуск;
  - `BREAKING CHANGE:` / `BREAKING-CHANGE:` в теле → секция `Breaking Changes` (приоритетнее type);
  - `type(scope)!: description` или `type: description` → маппинг по типу; `!` → `Breaking Changes`;
  - нераспознанный `subject`, не подходящий под Conventional Commits → `Other` с префиксом `[non-conventional]`;
  - type, подходящий под шаблон, но отсутствующий в `TYPE_TO_SECTION` (`chore`, `ci`, `build`, `test`, `style` и неизвестные type) → пропуск.
- `_group_by_section(parsed)` — группировка пунктов по секциям в порядке `SECTION_ORDER`.
- `_build_unreleased_block(parsed, body_override=None)` — собирает блок `## [Unreleased]`. Если `body_override` задан, использует его как тело вместо детерминированной группировки. Если изменений нет, добавляет заглушку `### Added` / `- (нет изменений)`.
- `_merge_append(existing, unreleased_block)` — вставка/замена `[Unreleased]` после `# Changelog`. При отсутствии шапки создаёт её. Старый `[Unreleased]` заменяется новым; вырезание старого блока идёт до следующего заголовка `## ` или до конца файла.

## Правила маппинга
- `feat` → `Added`
- `fix` → `Fixed`
- `perf`, `refactor` → `Changed`
- `docs` → `Documentation`
- `BREAKING CHANGE` или `!` → `Breaking Changes`
- `chore`, `ci`, `build`, `test`, `style` → пропуск
- неизвестный type, распознанный как Conventional Commit → пропуск
- нераспознанный `subject` → `Other` с `[non-conventional]`

Порядок секций: `Added`, `Fixed`, `Changed`, `Documentation`, `Breaking Changes`, `Other`. Порядок важен для стабильного diff.

## Зависимости
- Стандартная библиотека: `logging`, `re`, `dataclasses.dataclass`.
- `from .scanner import GitCommit` — модуль ожидает объект коммита с атрибутами `subject`, `body`, `sha`.
- Константа `dv_file_version = '261028.05'`.
- Других внутренних импортов в изолированном файле нет.

## Использование в проекте
В предоставленном изолированном фрагменте обратные импорты и вызовы этого модуля не показаны. Публичный API (`parse_commits`, `format_grouped`, `generate`) предназначен для вызова из CLI/оркестратора генерации `CHANGELOG.md`. Судя по docstring, `format_grouped` используется для режима `--changelog-llm`, где LLM переписывает только тело `[Unreleased]`, а `generate` собирает итоговый текст файла; запись выполняет вызывающий код.

## Ограничения и заметки
- Модуль не читает и не пишет файлы сам — возвращает готовый текст; запись выполняет вызывающий код.
- `_BREAKING_RE` ищет `BREAKING CHANGE` / `BREAKING-CHANGE` в начале строки тела коммита с помощью `MULTILINE` и `search`; срабатывает первое найденное вхождение.
- При наличии `BREAKING CHANGE` в теле обычный type игнорируется для выбора секции.
- Текст пункта сохраняет `type`/`scope` в нормализованном виде: `type` приводится к нижнему регистру, `scope` сохраняется, пустой `scope` опускается. Для `!` в `subject` секция — `Breaking Changes`, но сам `!` в текст пункта не попадает.
- При `append=True` и отсутствии подходящих коммитов существующий непустой файл не изменяется.
- При `append=False` возвращается минимальный шаблон `# Changelog` + `[Unreleased]` даже если коммитов нет (с заглушкой).
- При `append=True` и пустом/пробельном `existing_content` создаётся новый файл с шапкой и блоком `[Unreleased]`.
- Если в существующем файле нет `# Changelog`, шапка создаётся, а новый `[Unreleased]` размещается перед старым содержимым.
- В сигнатуре `generate` у параметра `append` нет значения по умолчанию, несмотря на комментарий в docstring; режим должен передавать вызывающий код.