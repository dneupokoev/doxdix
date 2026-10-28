"""Конвейер шагов 0–5: сканирование, бэкап, CHANGELOG, README,
SUMMARY, обход файлов, финальный SUMMARY.

Публичный API:
    RunConfig, RunStats
    run(cfg) -> RunStats

Все ошибки обработки файлов не фатальны: инкрементируют errors,
логируются, конвейер продолжается. Конфигурационные ошибки (нет
Ollama/модели/путей) — фатальны, ловятся в cli.py до вызова run().
"""
from __future__ import annotations

import logging
import re
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import backup as backup_mod
from . import changelog_gen
from . import llm
from . import prompts
from . import scanner

dv_file_version = '261028.15'
logger = logging.getLogger(__name__)


class ConfigError(Exception):
    """Ошибка конфигурации запуска (неверный путь и т.п.).

    В отличие от ошибок обработки файлов не инкрементирует errors:
    CLI завершается с кодом 2 (см. ТЗ п. 5, 10).
    """


# Регексп для проверки, есть ли уже ссылка на LICENSE в README
# (см. решение п. 3: не дублировать, если уже есть).
_LICENSE_LINK_RE = re.compile(r"\[.*?\]\(\.?/?LICENSE[^)]*\)",
                              re.IGNORECASE)

# Первые 20 строк LICENSE — для детекта типа лицензии.
_LICENSE_DETECT_LINES = 20


@dataclass
class RunConfig:
    """Все параметры запуска, собранные из CLI."""
    project_root: Path
    src_dir: str | None
    docs_dir: str                       # относительно project_root
    model: str
    ollama_url: str
    api_key: str
    extensions: list[str]
    excludes: list[str]
    timeout: int
    num_ctx: int
    max_doc_tokens: int
    use_git: bool
    do_commit: bool
    changelog_limit: int
    changelog_llm: bool
    do_changelog: bool
    changelog_append: bool
    backup_dir: Path
    backup_keep: int
    do_backup: bool
    init_license: bool
    do_readme: bool = True
    log_file: Path = Path("doxdix.log")


@dataclass
class RunStats:
    """Счётчики для итоговой сводки и кода возврата."""
    success: int = 0
    errors: int = 0
    skipped: int = 0
    backup_created: Path | None = None
    license_created: bool = False


# --------------------------------------------------------------------------
# Утилиты
# --------------------------------------------------------------------------

def _read_text(path: Path) -> str:
    """Прочитать файл как UTF-8; при ошибке — пустая строка + warning."""
    if not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        logger.warning("не удалось прочитать %s: %s", path, exc)
        return ""


def _write_text(path: Path, content: str) -> bool:
    """Записать файл как UTF-8, создав родительские папки.

    True при успехе, False при ошибке (лог error, не бросаем).
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return True
    except OSError as exc:
        logger.error("не удалось записать %s: %s", path, exc)
        return False


def _estimate_tokens(text: str) -> int:
    """Грубая оценка токенов: len(text) // 4 (см. ТЗ п. 6.6)."""
    return len(text) // 4


def _md_path_for(code_file: Path, project_root: Path,
                 src_dir: str | None, docs_dir: str) -> Path:
    """Правило зеркалирования: код -> docs_dir/<rel>.md.

    Решение п. 5: относительный путь от src_dir (если задан) или от
    project_root; префикс docs_dir; расширение меняется на .md.
    """
    if src_dir:
        rel = code_file.relative_to((project_root / src_dir).resolve())
    else:
        rel = code_file.relative_to(project_root)
    return (project_root / docs_dir / rel).with_suffix(".md")


def _git_commit(project_root: Path, paths: list[str], message: str,
                do_commit: bool, has_git: bool = True) -> None:
    """Сделать git-коммит. Ошибки — warning, не фатальны.

    Коммит выполняется, только если do_commit и has_git
    (ТЗ п. 6.4–6.6: без git коммиты не делаются).
    """
    if not do_commit or not has_git:
        return
    try:
        subprocess.run(
            ["git", "add", *paths],
            cwd=str(project_root), capture_output=True, text=True, timeout=30,
        )
        proc = subprocess.run(
            ["git", "commit", "-m", message],
            cwd=str(project_root), capture_output=True, text=True, timeout=30,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as exc:
        logger.warning("git commit не выполнен (%s): %s", message, exc)
        return
    if proc.returncode != 0:
        logger.warning(
            "git commit не выполнен (%s): %s",
            message, proc.stderr.strip()[:300],
        )


def _file_list_for_prompt(files: list[Path], project_root: Path) -> str:
    """Список относительных путей для промптов README/SUMMARY."""
    return "\n".join(
        str(f.relative_to(project_root)) for f in files
    )


def _recent_commits_for_prompt(commits: list[scanner.GitCommit],
                               limit: int = 10) -> str:
    """Последние N коммитов одной строкой для промпта README."""
    if not commits:
        return "(нет данных git)"
    lines = [
        f"{c.sha[:8]} {c.subject}" for c in commits[:limit]
    ]
    return "\n".join(lines)



def _strip_code_fence(text: str) -> str:
    """Убрать обрамляющие ```markdown ... ``` из ответа LLM.

    Модели часто заворачивают markdown в code fence, даже если просили
    вернуть «только текст .md». Срезаем первую строку (``` или ```lang)
    и последнюю (```), если они есть.
    """
    s = text.strip()
    if not s.startswith("```"):
        return text
    first_nl = s.find("\n")
    if first_nl == -1:
        return text
    body = s[first_nl + 1:]
    stripped = body.rstrip()
    if stripped.endswith("```"):
        body = stripped[:-3]
    return body.strip() + "\n"


def _project_context(project_root: Path, limit: int = 2000) -> str:
    """Первые `limit` символов README.md для контекста промптов.

    Если README нет — пустая строка. Решение: LLM не должна выдумывать
    назначение проекта, если его можно прочитать в README.
    """
    readme = project_root / "README.md"
    if not readme.is_file():
        return ""
    text = _read_text(readme)
    return text[:limit]


# --------------------------------------------------------------------------
# Шаг 1: CHANGELOG.md
# --------------------------------------------------------------------------

def _changelog_body_llm(cfg: RunConfig,
                        git_data: scanner.GitData) -> str | None:
    """Тело `[Unreleased]` через LLM (--changelog-llm), либо None.

    При ошибке LLM возвращает None — вызывающая сторона использует
    детерминированную группировку (ТЗ п. 6.3, п. 7.4).
    """
    if not cfg.changelog_llm:
        return None
    parsed = changelog_gen.parse_commits(git_data.commits)
    grouped = changelog_gen.format_grouped(parsed).strip()
    if not grouped:
        logger.info("CHANGELOG-LLM: нет изменений для переписывания")
        return None

    prompt = prompts.render(
        prompts.CHANGELOG_LLM_PROMPT, grouped_commits=grouped,
    )
    try:
        body = llm.chat(
            cfg.ollama_url, cfg.model, prompt,
            num_ctx=cfg.num_ctx, timeout=cfg.timeout, api_key=cfg.api_key,
        )
    except llm.LLMError as exc:
        logger.warning(
            "CHANGELOG-LLM: LLM-ошибка, оставляем детерминированный "
            "вариант: %s", exc.message,
        )
        return None

    body = _strip_code_fence(body).strip()
    if not body:
        logger.warning(
            "CHANGELOG-LLM: пустой ответ LLM, оставляем "
            "детерминированный вариант",
        )
        return None
    return body


def _step_changelog(cfg: RunConfig, git_data: scanner.GitData,
                    stats: RunStats) -> None:
    """Сгенерировать/дополнить CHANGELOG.md (если git есть и не отключён)."""
    if not cfg.do_changelog:
        logger.info("CHANGELOG: пропущен (--no-changelog)")
        return
    if not git_data.has_git:
        logger.info("CHANGELOG: пропущен (нет git)")
        return

    path = cfg.project_root / "CHANGELOG.md"
    existing = _read_text(path)

    # --changelog-llm: переписать блок [Unreleased] через LLM.
    unreleased_block = _changelog_body_llm(cfg, git_data)

    try:
        new_content = changelog_gen.generate(
            git_data.commits, existing, append=cfg.changelog_append,
            unreleased_block=unreleased_block,
        )
    except Exception as exc:  # noqa: BLE001 — защита от неожиданного
        logger.error("CHANGELOG: ошибка генерации: %s", exc)
        stats.errors += 1
        return

    if new_content == existing:
        logger.info("CHANGELOG: без изменений")
        return
    if not _write_text(path, new_content):
        stats.errors += 1
        return
    logger.info("CHANGELOG.md: обновлён")
    _git_commit(cfg.project_root, ["CHANGELOG.md"],
                "docs(doxdix): update CHANGELOG.md", cfg.do_commit,
                git_data.has_git)


# --------------------------------------------------------------------------
# Шаг 2: README.md
# --------------------------------------------------------------------------

def _step_readme(cfg: RunConfig, files: list[Path],
                 git_data: scanner.GitData, stats: RunStats) -> None:
    """Обновить README.md через LLM + вставить ссылку на LICENSE."""
    path = cfg.project_root / "README.md"
    existing = _read_text(path)
    file_list = _file_list_for_prompt(files, cfg.project_root)
    recent = _recent_commits_for_prompt(git_data.commits)

    prompt = prompts.render(
        prompts.README_PROMPT,
        file_list=file_list,
        recent_commits=recent,
        existing_content=existing,
        project_context=_project_context(cfg.project_root),
    )
    try:
        new_content = llm.chat(
            cfg.ollama_url, cfg.model, prompt,
            num_ctx=cfg.num_ctx, timeout=cfg.timeout, api_key=cfg.api_key,
        )
    except llm.LLMError as exc:
        logger.error("README: LLM-ошибка: %s", exc.message)
        stats.errors += 1
        return

    # Срезать возможный ```markdown ... ``` из ответа LLM.
    new_content = _strip_code_fence(new_content)
    # Детерминированная вставка ссылки на LICENSE (решение п. 3).
    new_content = _inject_license_link(cfg.project_root, new_content)

    if new_content == existing:
        logger.info("README.md: без изменений")
        return
    if not _write_text(path, new_content):
        stats.errors += 1
        return
    logger.info("README.md: обновлён")
    _git_commit(cfg.project_root, ["README.md"],
                "docs(doxdix): update README.md", cfg.do_commit,
                git_data.has_git)


def _detect_license_type(license_path: Path) -> str | None:
    """Определить тип лицензии по первым 20 строкам.

    Матчинг: MIT, Apache, GNU GPL, BSD. Иначе None (решение п. 3).
    """
    try:
        with license_path.open("r", encoding="utf-8") as fh:
            head = "".join(next(fh, "") for _ in range(_LICENSE_DETECT_LINES))
    except OSError:
        return None
    low = head.lower()
    if "mit license" in low:
        return "MIT"
    if "apache license" in low:
        return "Apache 2.0"
    if "gnu general public license" in low:
        return "GPL"
    if "bsd" in low:
        return "BSD"
    return None


def _inject_license_link(project_root: Path, readme: str) -> str:
    """Добавить раздел «Лицензия» в конец README, если его ещё нет.

    Не трогаем, если в README уже есть ссылка на LICENSE.
    Не трогаем, если LICENSE-файла нет.
    """
    license_path = project_root / "LICENSE"
    if not license_path.is_file():
        return readme
    if _LICENSE_LINK_RE.search(readme):
        return readme

    ltype = _detect_license_type(license_path)
    if ltype:
        section = (
            "\n---\n\n## Лицензия\n\n"
            f"Проект распространяется под лицензией "
            f"[{ltype}](LICENSE). См. файл [LICENSE](LICENSE).\n"
        )
    else:
        section = (
            "\n---\n\n## Лицензия\n\n"
            f"См. файл [LICENSE](LICENSE).\n"
        )
    return readme.rstrip() + "\n" + section


# --------------------------------------------------------------------------
# Шаг 3 и 5: SUMMARY.md
# --------------------------------------------------------------------------

def _summary_path(cfg: RunConfig) -> Path:
    """SUMMARY.md всегда в docs/ (решение п. 5), независимо от docs_dir."""
    return cfg.project_root / "docs" / "SUMMARY.md"


def _docs_relative(path: Path, project_root: Path) -> str:
    """Путь относительно docs/ — для ссылок вида modules/... в SUMMARY.

    Если файл вне docs/ (не должно случаться), отдаём имя файла, чтобы
    не сломать промпт.
    """
    try:
        return path.relative_to(project_root / "docs").as_posix()
    except ValueError:
        return path.name


def _step_summary(cfg: RunConfig, files: list[Path],
                  md_files: list[Path], stats: RunStats,
                  final: bool = False, has_git: bool = True) -> None:
    """Создать/обновить docs/SUMMARY.md.

    final=False — шаг 3 (по списку файлов кода).
    final=True  — шаг 5 (ТЗ п. 6.7: отдельный промпт «дополни ссылками
                  на созданные .md», пути — относительно docs/).
    """
    path = _summary_path(cfg)
    existing = _read_text(path)
    if final:
        # Пути относительно docs/: в SUMMARY ссылки имеют вид
        # modules/<подпуть>.md (ТЗ п. 7.1), без префикса docs/.
        listing = "\n".join(
            _docs_relative(m, cfg.project_root) for m in md_files
        )
        prompt = prompts.render(
            prompts.SUMMARY_FINAL_PROMPT,
            file_list=listing,
            existing_content=existing,
        )
    else:
        listing = _file_list_for_prompt(files, cfg.project_root)
        prompt = prompts.render(
            prompts.SUMMARY_PROMPT,
            file_list=listing,
            existing_content=existing,
            project_context=_project_context(cfg.project_root),
        )
    try:
        new_content = llm.chat(
            cfg.ollama_url, cfg.model, prompt,
            num_ctx=cfg.num_ctx, timeout=cfg.timeout, api_key=cfg.api_key,
        )
    except llm.LLMError as exc:
        logger.error("SUMMARY (%s): LLM-ошибка: %s",
                     "final" if final else "init", exc.message)
        stats.errors += 1
        return

    new_content = _strip_code_fence(new_content)
    if new_content == existing:
        logger.info("SUMMARY.md (%s): без изменений",
                    "final" if final else "init")
        return
    if not _write_text(path, new_content):
        stats.errors += 1
        return
    logger.info("SUMMARY.md (%s): обновлён", "final" if final else "init")
    _git_commit(cfg.project_root, ["docs/SUMMARY.md"],
                "docs(doxdix): finalize SUMMARY.md" if final
                else "docs(doxdix): update SUMMARY.md",
                cfg.do_commit, has_git)


# --------------------------------------------------------------------------
# Шаг 4: обход файлов
# --------------------------------------------------------------------------

def _step_modules(cfg: RunConfig, files: list[Path],
                  stats: RunStats, has_git: bool = True) -> list[Path]:
    """Обойти файлы кода, сгенерировать/обновить .md для каждого.

    Возвращает список созданных/обновлённых .md путей.
    """
    created: list[Path] = []
    total = len(files)
    for idx, code_path in enumerate(files, start=1):
        started = time.monotonic()
        rel = code_path.relative_to(cfg.project_root)
        md_path = _md_path_for(code_path, cfg.project_root,
                               cfg.src_dir, cfg.docs_dir)
        md_rel = md_path.relative_to(cfg.project_root)

        code_content = _read_text(code_path)
        if not code_content:
            logger.error("[%d/%d] %s: пустой или нечитаемый файл",
                         idx, total, rel)
            stats.errors += 1
            continue

        existing = _read_text(md_path) if md_path.exists() else ""
        if existing and _estimate_tokens(existing) > cfg.max_doc_tokens:
            logger.warning(
                "[%d/%d] %s: существующая дока ~%d токенов > лимит %d, "
                "пропущено",
                idx, total, rel, _estimate_tokens(existing),
                cfg.max_doc_tokens,
            )
            stats.skipped += 1
            continue

        prompt = prompts.render(
            prompts.MODULE_PROMPT,
            code_content=code_content,
            existing_content=existing,
        )
        try:
            new_content = llm.chat(
                cfg.ollama_url, cfg.model, prompt,
                num_ctx=cfg.num_ctx, timeout=cfg.timeout, api_key=cfg.api_key,
            )
        except llm.LLMError as exc:
            logger.error("[%d/%d] %s: LLM-ошибка: %s",
                         idx, total, rel, exc.message)
            stats.errors += 1
            continue

        new_content = _strip_code_fence(new_content)
        if not _write_text(md_path, new_content):
            stats.errors += 1
            continue
        created.append(md_path)
        stats.success += 1
        elapsed = time.monotonic() - started
        logger.info("[%d/%d] %s -> %s ... OK (%.1fs)",
                    idx, total, rel, md_rel, elapsed)
        _git_commit(cfg.project_root, [str(md_rel)],
                    f"docs(doxdix): {rel}", cfg.do_commit, has_git)
    return created


# --------------------------------------------------------------------------
# Главный конвейер
# --------------------------------------------------------------------------

def _init_license_if_requested(cfg: RunConfig, stats: RunStats) -> None:
    """--init-license: создать MIT-заготовку, если LICENSE нет."""
    if not cfg.init_license:
        return
    path = cfg.project_root / "LICENSE"
    if path.is_file():
        logger.info("LICENSE: уже существует, пропущено (--init-license)")
        return
    year = _current_year()
    text = (
        "MIT License\n\n"
        f"Copyright (c) {year} <author>\n\n"
        "Permission is hereby granted, free of charge, to any person "
        "obtaining a copy\nof this software and associated documentation "
        "files (the \"Software\"), to deal\nin the Software without "
        "restriction, including without limitation the rights\n"
        "to use, copy, modify, merge, publish, distribute, sublicense, "
        "and/or sell\ncopies of the Software, and to permit persons to "
        "whom the Software is\nfurnished to do so, subject to the "
        "following conditions:\n\n"
        "The above copyright notice and this permission notice shall be "
        "included in all\ncopies or substantial portions of the Software.\n\n"
        "THE SOFTWARE IS PROVIDED \"AS IS\", WITHOUT WARRANTY OF ANY KIND, "
        "EXPRESS OR\nIMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES "
        "OF MERCHANTABILITY,\nFITNESS FOR A PARTICULAR PURPOSE AND "
        "NONINFRINGEMENT. IN NO EVENT SHALL THE\nAUTHORS OR COPYRIGHT "
        "HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER\nLIABILITY, "
        "WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING "
        "FROM,\nOUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR "
        "OTHER DEALINGS IN THE\nSOFTWARE.\n"
    )
    if _write_text(path, text):
        logger.info("LICENSE: создана MIT-заготовка")
        stats.license_created = True
    else:
        stats.errors += 1


def _current_year() -> int:
    from datetime import datetime
    return datetime.now().year


def run(cfg: RunConfig) -> RunStats:
    """Выполнить конвейер шагов 0–5. Вернуть RunStats."""
    stats = RunStats()
    project_root = cfg.project_root.resolve()

    # --- Шаг 0: сканирование ---
    logger.info("шаг 0: сканирование %s", project_root)
    try:
        files, git_data = scanner.scan(
            project_root=project_root,
            src_dir=cfg.src_dir,
            extensions=cfg.extensions,
            user_excludes=cfg.excludes,
            use_git=cfg.use_git,
            changelog_limit=cfg.changelog_limit,
        )
    except ValueError as exc:
        # Неверный --src-dir/путь — ошибка конфигурации, CLI вернёт 2
        # (ТЗ п. 5, п. 10), а не 1.
        logger.error("сканирование: %s", exc)
        raise ConfigError(str(exc)) from exc

    if not files:
        logger.warning("файлов кода не найдено; завершаем")
        return stats

    logger.info("найдено файлов: %d", len(files))

    # --- --init-license (до бэкапа, чтобы LICENSE попал в бэкап) ---
    _init_license_if_requested(cfg, stats)

    # --- Шаг 0.5: бэкап ---
    if cfg.do_backup:
        logger.info("шаг 0.5: бэкап документации")
        try:
            bdir = backup_mod.create_backup(
                project_root, cfg.backup_dir, cfg.backup_keep,
            )
            stats.backup_created = bdir
        except Exception as exc:  # noqa: BLE001
            logger.error("бэкап: неожиданная ошибка: %s", exc)
            stats.errors += 1
    else:
        logger.warning("бэкап отключён (--no-backup)")

    # --- Шаг 1: CHANGELOG ---
    logger.info("шаг 1: CHANGELOG.md")
    _step_changelog(cfg, git_data, stats)

    # --- Шаг 2: README ---
    if cfg.do_readme:
        logger.info("шаг 2: README.md")
        _step_readme(cfg, files, git_data, stats)
    else:
        logger.info("шаг 2: README.md — пропущен (--no-readme)")

    # --- Шаг 3: SUMMARY (init) ---
    logger.info("шаг 3: SUMMARY.md (init)")
    _step_summary(cfg, files, [], stats, final=False,
                  has_git=git_data.has_git)

    # --- Шаг 4: обход файлов ---
    logger.info("шаг 4: обход %d файлов", len(files))
    created_md = _step_modules(cfg, files, stats,
                               has_git=git_data.has_git)

    # --- Шаг 5: SUMMARY (final) ---
    logger.info("шаг 5: SUMMARY.md (final)")
    _step_summary(cfg, files, created_md, stats, final=True,
                  has_git=git_data.has_git)

    # --- Итог ---
    logger.info(
        "итог: успешно: %d, ошибок: %d, пропущено: %d",
        stats.success, stats.errors, stats.skipped,
    )
    if stats.backup_created:
        logger.info("бэкап: %s", stats.backup_created)
    return stats
