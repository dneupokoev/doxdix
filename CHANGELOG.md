# Changelog

## [Unreleased]

### Added
- feat: добавить поддержку подпроектов монорепозитория
- feat: добавить флаг --no-monorepo для плоской структуры docs
- feat: собирать SUMMARY по содержимому .md и описать кэш с --force
- feat: добавить кэширование хэшей файлов и флаг --force
- feat: добавить тайминг в лог шага modules
- feat: реализовать --changelog-llm, финальный SUMMARY и правки по SPEC
- feat: doxdix — CLI for automated documentation generation via LLM

### Fixed
- fix: привести пути в промптах и SUMMARY в соответствие с ТЗ
- fix: убрать обертку root из пути документации корневого проекта
- fix: исправить пути подпроектов и логи шага 4
- fix: пропускать пустые и неизменённые файлы, убрать ранний выход

### Documentation
- docs: дополни описание автопоиска подпроектов
- docs(doxdix): finalize SUMMARY.md
- docs(doxdix): src/doxdix/scanner.py
- docs(doxdix): src/doxdix/prompts.py
- docs(doxdix): src/doxdix/orchestrator.py
- docs(doxdix): src/doxdix/llm.py
- docs(doxdix): src/doxdix/cli.py
- docs(doxdix): src/doxdix/changelog_gen.py
- docs(doxdix): src/doxdix/cache.py
- docs(doxdix): src/doxdix/backup.py
- docs(doxdix): src/doxdix/__init__.py
- docs(doxdix): update README.md
- docs(doxdix): update CHANGELOG.md
- docs(doxdix): finalize SUMMARY.md
- docs(doxdix): src/doxdix/scanner.py
- docs(doxdix): src/doxdix/prompts.py
- docs(doxdix): src/doxdix/orchestrator.py
- docs(doxdix): src/doxdix/llm.py
- docs(doxdix): src/doxdix/cli.py
- docs(doxdix): src/doxdix/changelog_gen.py
- docs(doxdix): src/doxdix/cache.py
- docs(doxdix): src/doxdix/backup.py
- docs(doxdix): src/doxdix/__init__.py
- docs(doxdix): update SUMMARY.md
- docs(doxdix): update README.md
- docs(doxdix): update CHANGELOG.md
- docs: описать автоопределение подпроектов и структуру docs/modules
- docs: обновить документацию модулей doxdix по текущему коду
- docs: remove license section from SUMMARY (should be in README only)
- docs(readme): fix install URL (real GitHub user)

### Other
- [non-conventional] ch
- [non-conventional] ch
