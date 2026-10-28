# Модуль `changelog`

## Назначение

Модуль парсит коммиты в формате Conventional Commits, группирует их по секциям Keep a Changelog и формирует или обновляет `CHANGELOG.md` с блоком `[Unreleased]`. Также умеет возвращать только тело `[Unreleased]` — например, для последующей переработки через `--changelog-llm`.

## Публичный API

- `ParsedCommit` — frozen dataclass с полями:
  - `section: str` — секция changelog;
  - `text: str` — текст пункта;
  - `sha: str = ""` — SHA коммита; сохраняется для трассируемости, но в итоговый changelog не выводится.

- `parse_commits(commits: list[GitCommit]) -> list[ParsedCommit]`
  - Разбирает список коммитов.
  - Пропускает коммиты, которые не должны попадать в changelog.
  - Логирует количество разобранных и пропущенных коммитов.

- `format_grouped(parsed: list[ParsedCommit]) -> str`
  - Возвращает только тело блока `[Unreleased]`, без `# Changelog` и `## [Unreleased]`.
  - Выводит секции в фиксированном порядке, пустые секции не включает.
  - Используется для `--changelog-llm`.

- `generate(commits: list[GitCommit], existing_content: str, append: bool, unreleased_block: str | None = None) -> str`
  - Формирует полный текст `CHANGELOG.md`.
  - `commits` — список коммитов из `scanner.GitData.commits`.
  - `existing_content` — текущее содержимое `CHANGELOG.md` или пустая строка.
  - `append` — обязательный флаг:
    - `True` — вставить или заменить блок `[Unreleased]` в существующем файле;
    - `False` — полностью перезаписать файл минимальным шаблоном.
  - `unreleased_block` — готовое тело `[Unreleased]`, например после `--changelog-llm`. Если `None` или пусто, используется детерминированная группировка по секциям.

## Правила парсинга

- Поддерживается формат `type(scope): description` и `type: description`.
- Type приводится к нижнему регистру; scope опционален; description обрезается по краям.
- Маппинг type → секция:
  - `feat` → `Added`
  - `fix` → `Fixed`
  - `perf`, `refactor` → `Changed`
  - `docs` → `Documentation`
  - `chore`, `ci`, `build`, `test`, `style` и другие типы, отсутствующие в маппинге, пропускаются.
- `BREAKING CHANGE: ...` или `BREAKING-CHANGE: ...` в теле коммита имеет приоритет над type и попадает в `Breaking Changes`; в текст пункта идёт только описание.
- Флаг `!` в заголовке, например `feat!: ...`, также переводит коммит в `Breaking Changes`; в тексте пункта `!` не сохраняется.
- Нераспознанный заголовок, не подходящий под Conventional Commits, попадает в `Other` с префиксом `[non-conventional]`.
- Пустой `subject` пропускается.
- Порядок секций: `Added`, `Fixed`, `Changed`, `Documentation`, `Breaking Changes`, `Other`.

Важно: по фактической реализации неизвестный conventional type, который совпал с regex, но отсутствует в `TYPE_TO_SECTION`, пропускается. В `Other` попадают именно нераспознанные заголовки, не соответствующие Conventional Commits.

## Внутренние помощники

- `_parse_commit(commit: GitCommit) -> ParsedCommit | None` — разбор одного коммита; `None` означает пропуск.
- `_group_by_section(parsed: list[ParsedCommit]) -> dict[str, list[str]]` — группировка пунктов по секциям.
- `_build_unreleased_block(parsed, body_override=None) -> str` — сборка блока `## [Unreleased]`; при отсутствии изменений добавляет заглушку `### Added` / `- (нет изменений)`.
- `_merge_append(existing: str, unreleased_block: str) -> str` — вставка или замена `[Unreleased]` в существующем changelog:
  - если файл пуст — создаёт `# Changelog`;
  - если заголовка `# Changelog` нет — добавляет его и новый блок перед существующим текстом;
  - если старый `[Unreleased]` есть — заменяет его до следующего `## ` или до конца файла;
  - если старого `[Unreleased]` нет — вставляет новый сразу после `# Changelog`.

## Зависимости

Из импортов:

- стандартная библиотека: `logging`, `re`, `dataclasses.dataclass`;
- `from __future__ import annotations`;
- проектный модуль: `.scanner.GitCommit`.

Модуль ожидает, что `GitCommit` содержит атрибуты `subject`, `body` и `sha`.

## Использование в проекте

В изолированном файле виден только импорт `GitCommit` из `.scanner`. Обратные импорты и конкретные вызывающие модули не видны, поэтому точное место использования определить нельзя. По публичному API модуль, вероятно, вызывается из CLI/генератора changelog:

- `parse_commits` — промежуточный разбор коммитов;
- `format_grouped` — подготовка тела `[Unreleased]` для `--changelog-llm`;
- `generate` — формирование итогового `CHANGELOG.md` с учётом существующего содержимого и режима `append`.

## Поведение `generate`

- При `append=False` возвращает минимальный шаблон `# Changelog` + `## [Unreleased]`, без сохранения старого содержимого.
- При `append=True` и наличии коммитов/LLM-тела выполняет вставку или замену `[Unreleased]`.
- При `append=True`, отсутствии коммитов, отсутствии LLM-тела и непустом существующем файле возвращает существующее содержимое без изменений.
- Если коммитов нет, но `unreleased_block` передан, он всё равно используется для формирования блока.

## Служебное

- `dv_file_version = '261028.05'` — служебный маркер версии файла.
- `logger = logging.getLogger(__name__)` — логирование разбора и случаев, когда файл не изменяется.