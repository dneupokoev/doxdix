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
- fix: исправить пути подпроектов и логи шага 4
- fix: пропускать пустые и неизменённые файлы, убрать ранний выход

### Documentation
- docs: описать автоопределение подпроектов и структуру docs/modules
- docs: обновить документацию модулей doxdix по текущему коду
- docs: remove license section from SUMMARY (should be in README only)
- docs(readme): fix install URL (real GitHub user)

### Other
- [non-conventional] ch
