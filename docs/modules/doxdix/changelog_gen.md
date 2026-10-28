# changelog.py — парсер Conventional Commits и генератор CHANGELOG.md

## Назначение
Модуль разбирает коммиты Git в формате Conventional Commits, группирует их по секциям Keep a Changelog и формирует/обновляет `CHANGELOG.md` с секцией `[Unreleased]`. Используется для автоматической генерации changelog, включая подготовку фрагмента для LLM (`--changelog-llm`).

## Публичный API
- `parse_commits(commits: list[GitCommit]) -> list[ParsedCommit]` — разбирает список коммитов, отбрасывает пропускаемые типы (`chore`, `ci`, `build`, `test`, `style` и неизвестные типы без секции), логирует количество разобранных и пропущенных коммитов.
- `format_grouped(parsed: list[ParsedCommit]) -> str` — возвращает тело `[Unreleased]` без заголовков `# Changelog` и `## [Unreleased]`. Секции выводятся в фиксированном порядке, пустые секции не выводятся. Используется для `--changelog-llm`.
- `generate(commits: list[GitCommit], existing_content: str, append: bool) -> str` — генерирует полный текст `CHANGELOG.md`.
  - `append=False` — полная перезапись: `# Changelog` + `[Unreleased]`.
  - `append=True` — вставка/замена блока `[Unreleased]` в существующем содержимом; если подходящих коммитов нет и файл не пуст, возвращает существующее содержимое без изменений.

## Классы и внутренние функции
- `ParsedCommit(section: str, text: str, sha: str = "")` — frozen dataclass одного разобранного коммита: целевая секция, текст пункта, SHA.
- `_parse_commit(commit: GitCommit) -> ParsedCommit | None` — разбор одного коммита:
  - пустой `subject` → пропуск;
  - `BREAKING CHANGE:` / `BREAKING-CHANGE:` в теле → секция `Breaking Changes` (приоритетнее type);
  - `type(scope)!: description` или `type: description` → маппинг по типу; `!` → `Breaking Changes`;
  - нераспознанный `subject` → `Other` с префиксом `[non-conventional]`;
  - `chore` / `ci` / `build` / `test` / `style` и неизвестные типы → пропуск.
- `_group_by_section(parsed)` — группировка пунктов по секциям в порядке `SECTION_ORDER`.
- `_build_unreleased_block(parsed)` — собирает блок `## [Unreleased]`; если изменений нет, добавляет заглушку `### Added` / `- (нет изменений)`.
- `_merge_append(existing, unreleased_block)` — вставка/замена `[Unreleased]` после `# Changelog`; при отсутствии шапки создаёт её; старый `[Unreleased]` заменяется новым.

## Правила маппинга
- `feat` → `Added`
- `fix` → `Fixed`
- `perf`, `refactor` → `Changed`
- `docs` → `Documentation`
- `BREAKING CHANGE` или `!` → `Breaking Changes`
- `chore`, `ci`, `build`, `test`, `style` → пропуск
- нераспознанное → `Other` с `[non-conventional]`

Порядок секций: `Added`, `Fixed`, `Changed`, `Documentation`, `Breaking Changes`, `Other`.

## Зависимости
- Стандартная библиотека: `logging`, `re`, `dataclasses.dataclass`.
- `from .scanner import GitCommit` — модуль ожидает объект коммита с полями/атрибутами `subject`, `body`, `sha`.
- Константа `dv_file_version = '261028.04'`.

## Использование в проекте
В предоставленном фрагменте обратные импорты этого модуля не показаны. Публичный API (`parse_commits`, `format_grouped`, `generate`) предназначен для вызова из CLI/оркестратора генерации `CHANGELOG.md`. Судя по docstring, `format_grouped` также используется для режима `--changelog-llm`, где LLM переписывает только тело `[Unreleased]`.

## Ограничения и заметки
- Модуль не читает и не пишет файлы сам — возвращает готовый текст; запись выполняет вызывающий код.
- `_BREAKING_RE` ищет `BREAKING CHANGE` / `BREAKING-CHANGE` в начале строки тела коммита с помощью `MULTILINE` и `search`; срабатывает первое найденное вхождение.
- При наличии `BREAKING CHANGE` в теле обычный type игнорируется для выбора секции.
- Текст пункта сохраняет `type`/`scope` в нормализованном виде: `type` приводится к нижнему регистру.
- При `append=True` и отсутствии подходящих коммитов существующий непустой файл не изменяется.
- При `append=False` возвращается минимальный шаблон `# Changelog` + `[Unreleased]` даже если коммитов нет (с заглушкой).