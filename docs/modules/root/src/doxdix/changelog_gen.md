# Модуль `changelog`

## Назначение

Модуль предназначен для:

- парсинга сообщений коммитов по правилам Conventional Commits;
- группировки изменений по секциям Keep a Changelog;
- генерации или обновления `CHANGELOG.md`, в частности блока `## [Unreleased]`;
- подготовки тела `[Unreleased]` для сценария `--changelog-llm`, когда текст переписывается LLM.

Версия модуля: `dv_file_version = '261028.05'`.

## Публичный API

- `parse_commits(commits: list[GitCommit]) -> list[ParsedCommit]`
  - принимает список коммитов из `scanner`;
  - разбирает каждый коммит, отбрасывает пустые и пропускаемые типы;
  - логирует количество разобранных и пропущенных коммитов.

- `format_grouped(parsed: list[ParsedCommit]) -> str`
  - возвращает тело будущего блока `[Unreleased]` без заголовков `# Changelog` и `## [Unreleased]`;
  - выводит только непустые секции в порядке `SECTION_ORDER`;
  - формат элементов: `- <текст>`.

- `generate(commits: list[GitCommit], existing_content: str, append: bool, unreleased_block: str | None = None) -> str`
  - основной генератор полного текста `CHANGELOG.md`;
  - `commits` — список коммитов, обычно `GitData.commits`;
  - `existing_content` — текущее содержимое файла или `""`;
  - `append` — режим работы: `True` — вставка/замена `[Unreleased]` с сохранением остального файла, `False` — полная перезапись;
  - `unreleased_block` — готовое тело `[Unreleased]`, например после `--changelog-llm`; если пусто, используется детерминированная группировка;
  - возвращает готовый текст файла.

## Классы и константы

- `ParsedCommit` — frozen dataclass с полями:
  - `section: str` — секция CHANGELOG;
  - `text: str` — строка изменения;
  - `sha: str = ""` — SHA коммита, сохраняется, но в текущем выводе не используется.

- `SECTION_ORDER` — фиксированный порядок секций:
  `Added`, `Fixed`, `Changed`, `Documentation`, `Breaking Changes`, `Other`.

- `TYPE_TO_SECTION` — маппинг Conventional Commits type в секцию:
  - `feat` → `Added`
  - `fix` → `Fixed`
  - `perf`, `refactor` → `Changed`
  - `docs` → `Documentation`
  - `chore`, `ci`, `build`, `test`, `style` и другие отсутствующие типы пропускаются.

## Правила парсинга

- Пустой `subject` пропускается.
- `BREAKING CHANGE:` или `BREAKING-CHANGE:` в теле коммита имеет приоритет над типом и отправляет изменение в `Breaking Changes`.
- Conventional Commits распознаются регулярным выражением вида:
  - `type(scope): description`
  - `type: description`
  - `type(scope)!: description`
  - `type!: description`
- Для обычных типов текст сохраняет исходную формулировку с `type` и `scope`, например `feat(ui): add button`.
- Для breaking-коммитов с `!` текст также сохраняет `type(scope): description`, но попадает в `Breaking Changes`.
- Нераспознанный `subject` попадает в `Other` с префиксом `[non-conventional]`.
- Важная особенность текущей реализации: если `subject` похож на Conventional Commit, но его тип неизвестен и отсутствует в `TYPE_TO_SECTION`, коммит пропускается, а не попадает в `Other`. В `Other` попадают только сообщения, не соответствующие regex Conventional Commits.

## Внутренние функции

- `_parse_commit(commit: GitCommit) -> ParsedCommit | None`
  - разбирает один коммит;
  - возвращает `None`, если коммит нужно пропустить.

- `_group_by_section(parsed: list[ParsedCommit]) -> dict[str, list[str]]`
  - группирует тексты по секциям;
  - инициализирует все секции из `SECTION_ORDER`.

- `_build_unreleased_block(parsed: list[ParsedCommit], body_override: str | None = None) -> str`
  - собирает блок `## [Unreleased]`;
  - если передан `body_override`, использует его вместо детерминированной группировки;
  - если тело пустое, подставляет заглушку `### Added` и `- (нет изменений)`.

- `_merge_append(existing: str, unreleased_block: str) -> str`
  - вставляет новый `[Unreleased]` после `# Changelog`;
  - если `# Changelog` отсутствует, создаёт шапку и добавляет существующее содержимое после нового блока;
  - если старый `## [Unreleased]` найден, заменяет его до следующего заголовка `## ` или до конца файла;
  - сохраняет остальные разделы CHANGELOG.

## Поведение `generate`

- При `append=False` возвращается полный новый файл:
  - `# Changelog`
  - пустая строка
  - блок `## [Unreleased]`.

- При `append=True`:
  - если коммитов для добавления нет, LLM-тело пустое и существующий файл не пуст, файл возвращается без изменений;
  - иначе новый `[Unreleased]` вставляется после `# Changelog` или заменяет старый `[Unreleased]`.

## Зависимости

Внешние зависимости отсутствуют.

Импорты:

- `from __future__ import annotations` — отложенная оценка аннотаций;
- `logging` — логирование процесса разбора и генерации;
- `re` — регулярные выражения для Conventional Commits и `BREAKING CHANGE`;
- `dataclasses.dataclass` — описание `ParsedCommit`;
- `from .scanner import GitCommit` — тип входных коммитов.

Ожидаемые атрибуты `GitCommit`, используемые модулем:

- `subject`;
- `body`;
- `sha`.

## Использование в проекте

В самом файле не видно модулей, которые импортируют `changelog`, поэтому конкретные вызывающие модули по этому коду не определить.

По публичному API и docstring модуль предназначен для вызова из CLI/оркестратора генерации CHANGELOG:

- `generate(...)` — основная точка входа для получения полного текста `CHANGELOG.md`;
- `parse_commits(...)` и `format_grouped(...)` — вспомогательные точки входа, в том числе для сценария `--changelog-llm`, где LLM переписывает только тело `[Unreleased]`;
- модуль не выполняет файловый ввод-вывод: запись результата в `CHANGELOG.md` выполняет вызывающий код.

## Ограничения и особенности

- SHA коммита сохраняется в `ParsedCommit`, но не выводится в CHANGELOG.
- Старый `[Unreleased]` при обновлении заменяется новым, что соответствует смыслу «unreleased».
- Порядок секций стабилен и задаётся `SECTION_ORDER`.
- Секции с пустыми списками в `format_grouped` не выводятся.
- Если после фильтрации не осталось изменений и не передан LLM-текст, при `append=True` существующий файл не изменяется.
- Существующая документация в задании пуста; разделы для сохранения отсутствуют.