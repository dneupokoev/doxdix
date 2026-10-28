"""Парсер Conventional Commits + генератор CHANGELOG.md.

Публичный API:
    parse_commits(commits) -> list[ParsedCommit]
    format_grouped(parsed) -> str
    generate(commits, existing_content, append) -> str

Правила (см. ТЗ п. 6.3):
- type(scope): description — Conventional Commits.
- Маппинг type -> секция: feat→Added, fix→Fixed, perf/refactor→Changed,
  docs→Documentation, chore/ci/build/test/style→пропустить,
  BREAKING CHANGE→Breaking Changes, остальное→Other с [non-conventional].
- Формат вывода — Keep a Changelog, секция [Unreleased].
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from .scanner import GitCommit

dv_file_version = '261028.05'
logger = logging.getLogger(__name__)


# Порядок секций в выводе (важно для стабильного diff'а).
SECTION_ORDER: tuple[str, ...] = (
    "Added",
    "Fixed",
    "Changed",
    "Documentation",
    "Breaking Changes",
    "Other",
)

# type -> секция. Отсутствие type в словаре = пропустить.
TYPE_TO_SECTION: dict[str, str] = {
    "feat": "Added",
    "fix": "Fixed",
    "perf": "Changed",
    "refactor": "Changed",
    "docs": "Documentation",
    # chore, ci, build, test, style — пропускаем (нет в словаре).
}

# Conventional Commits: type(scope)!: description | type: description
_CC_RE = re.compile(
    r"^(?P<type>[a-zA-Z]+)"
    r"(?:\((?P<scope>[^)]*)\))?"
    r"(?P<breaking>!)?"
    r":\s*(?P<desc>.+)$"
)

_BREAKING_RE = re.compile(r"^BREAKING[ -]CHANGE:\s*(?P<desc>.+)$",
                          re.MULTILINE)


@dataclass(frozen=True)
class ParsedCommit:
    """Один распарсенный коммит, готовый к вставке в секцию."""
    section: str
    text: str
    sha: str = ""


def _parse_commit(commit: GitCommit) -> ParsedCommit | None:
    """Разобрать один коммит. None — если секция не нужна (chore и т.п.)."""
    subject = commit.subject.strip()
    if not subject:
        return None

    # BREAKING CHANGE в теле — приоритетнее type.
    m_break = _BREAKING_RE.search(commit.body or "")
    if m_break:
        desc = m_break.group("desc").strip()
        return ParsedCommit(
            section="Breaking Changes",
            text=desc,
            sha=commit.sha,
        )

    m = _CC_RE.match(subject)
    if not m:
        # Нераспознанный коммит — в Other с пометкой.
        return ParsedCommit(
            section="Other",
            text=f"[non-conventional] {subject}",
            sha=commit.sha,
        )

    ctype = m.group("type").lower()
    scope = m.group("scope")
    desc = m.group("desc").strip()
    breaking = bool(m.group("breaking"))

    if breaking:
        # `feat!:` — тоже Breaking Changes.
        text = f"{ctype}({scope}): {desc}" if scope else f"{ctype}: {desc}"
        return ParsedCommit(section="Breaking Changes", text=text,
                            sha=commit.sha)

    section = TYPE_TO_SECTION.get(ctype)
    if section is None:
        # chore/ci/build/test/style или неизвестный type — пропускаем.
        return None

    # Сохраняем исходную формулировку (вместе с type и scope), чтобы
    # CHANGELOG оставался трассируемым к коммиту.
    text = f"{ctype}({scope}): {desc}" if scope else f"{ctype}: {desc}"
    return ParsedCommit(section=section, text=text, sha=commit.sha)


def parse_commits(commits: list[GitCommit]) -> list[ParsedCommit]:
    """Разобрать список коммитов, отбросив пропускаемые (chore и т.п.)."""
    result: list[ParsedCommit] = []
    skipped = 0
    for c in commits:
        p = _parse_commit(c)
        if p is None:
            skipped += 1
            continue
        result.append(p)
    logger.info("changelog: разобрано %d коммитов, пропущено %d",
                len(result), skipped)
    return result


def _group_by_section(parsed: list[ParsedCommit]) -> dict[str, list[str]]:
    """Сгруппировать по секциям в порядке SECTION_ORDER."""
    groups: dict[str, list[str]] = {s: [] for s in SECTION_ORDER}
    for p in parsed:
        groups.setdefault(p.section, []).append(p.text)
    return groups


def format_grouped(parsed: list[ParsedCommit]) -> str:
    """Вернуть тело `[Unreleased]` (без `# Changelog` и `## [Unreleased]`).

    Используется для --changelog-llm: LLM перепишет этот фрагмент.
    Секции с пустыми списками не выводятся.
    """
    groups = _group_by_section(parsed)
    lines: list[str] = []
    for section in SECTION_ORDER:
        items = groups.get(section) or []
        if not items:
            continue
        lines.append(f"### {section}")
        for text in items:
            lines.append(f"- {text}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _build_unreleased_block(parsed: list[ParsedCommit],
                            body_override: str | None = None) -> str:
    """Собрать `## [Unreleased]` + содержимое. Пустая секция — заглушка.

    body_override — готовый текст тела (например, переписанный LLM
    через --changelog-llm, см. ТЗ п. 6.3/7.4). Если пуст — берём
    детерминированную группировку по секциям.
    """
    body = (body_override or "").strip()
    if not body:
        body = format_grouped(parsed).rstrip()
    if not body:
        body = "### Added\n- (нет изменений)"
    return "## [Unreleased]\n\n" + body + "\n"


def _merge_append(existing: str, unreleased_block: str) -> str:
    """Вставить новый `[Unreleased]` после `# Changelog`, сохранив остальное.

    Если `# Changelog` нет — создать шапку. Если старый `## [Unreleased]`
    уже есть — заменить его на новый (актуальные изменения перетирают
    прошлый Unreleased, что соответствует смыслу «unreleased»).
    """
    header = "# Changelog\n"
    if not existing.strip():
        return header + "\n" + unreleased_block

    lines = existing.splitlines()
    # Найти `# Changelog`
    h_idx = next(
        (i for i, ln in enumerate(lines) if ln.strip() == "# Changelog"),
        -1,
    )
    if h_idx == -1:
        return header + "\n" + unreleased_block + "\n" + existing

    # Найти границы старого `## [Unreleased]` (если есть).
    unrel_start = -1
    for i in range(h_idx + 1, len(lines)):
        if lines[i].strip() == "## [Unreleased]":
            unrel_start = i
            break

    if unrel_start == -1:
        # Старого Unreleased нет — вставляем сразу после `# Changelog`.
        before = lines[:h_idx + 1]
        after = lines[h_idx + 1:]
        out = before + [""] + unreleased_block.rstrip("\n").splitlines()
        if after:
            out += [""] + after
        return "\n".join(out).rstrip() + "\n"

    # Старый Unreleased есть — вырезаем его до следующего `## ` или EOF.
    unrel_end = len(lines)
    for i in range(unrel_start + 1, len(lines)):
        if lines[i].startswith("## "):
            unrel_end = i
            break

    before = lines[:unrel_start]
    after = lines[unrel_end:]
    out = (
        before
        + unreleased_block.rstrip("\n").splitlines()
        + ([""] + after if after else [])
    )
    return "\n".join(out).rstrip() + "\n"


def generate(commits: list[GitCommit], existing_content: str,
             append: bool, unreleased_block: str | None = None) -> str:
    """Сгенерировать полный текст CHANGELOG.md.

    Параметры:
        commits — список коммитов (из scanner.GitData.commits).
        existing_content — текущий CHANGELOG.md или "".
        append — True (по умолчанию): вставка после `# Changelog`,
                 False: полная перезапись.
        unreleased_block — готовое тело `[Unreleased]` (результат
                 --changelog-llm, ТЗ п. 6.3/7.4). None или "" —
                 детерминированная группировка по секциям.

    Возвращает готовый текст файла. Если коммитов, попадающих в секции,
    нет — возвращает существующее содержимое без изменений (append=True)
    или минимальный шаблон (append=False).
    """
    parsed = parse_commits(commits)
    llm_body = (unreleased_block or "").strip()
    unreleased = _build_unreleased_block(parsed, llm_body or None)

    if not append:
        return "# Changelog\n\n" + unreleased

    if not parsed and not llm_body and existing_content.strip():
        # Нечего добавлять — не трогаем существующий файл.
        logger.info("changelog: нечего добавлять, файл не изменён")
        return existing_content

    return _merge_append(existing_content, unreleased)
