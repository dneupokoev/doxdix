"""Сканирование проекта: обход файлов, исключения, git-данные.

Публичный API:
    scan(project_root, src_dir, extensions, user_excludes, use_git,
         changelog_limit) -> tuple[list[Path], GitData]

Правила (см. ТЗ п. 6.1 и решения по неоднозначностям):
- Если git доступен — обрабатываются только отслеживаемые файлы
  (git ls-files), отфильтрованные по расширениям и исключениям.
- Если git недоступен — рекурсивный обход файловой системы с теми же
  фильтрами.
- Ошибки git логируются как warning; сканирование продолжается без
  git-данных.
"""
from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

dv_file_version = '261028.02'
logger = logging.getLogger(__name__)


# Дефолтные исключения (папки) — см. ТЗ п. 6.1.
DEFAULT_EXCLUDE_DIRS: frozenset[str] = frozenset({
    ".git", ".doxdix", "node_modules", "__pycache__",
    "venv", ".venv", "env", "dist", "build",
    "tests", "test", ".mypy_cache", ".pytest_cache",
    ".ruff_cache", "target",
})

# Дефолтные исключения (файлы/паттерны) — см. ТЗ п. 6.1.
DEFAULT_EXCLUDE_FILE_PATTERNS: tuple[str, ...] = (
    "test_*", "*_test.*", "*.min.*", "*.spec.*", "conftest.py",
)


@dataclass(frozen=True)
class GitCommit:
    """Один коммит из git log."""
    sha: str
    subject: str
    body: str


@dataclass
class GitData:
    """Результат сбора git-данных."""
    has_git: bool = False
    commits: list[GitCommit] = field(default_factory=list)
    tracked_files: set[str] = field(default_factory=set)


def _matches_glob(name: str, pattern: str) -> bool:
    """Сопоставить имя файла glob-паттерну (через fnmatch).

    Используем fnmatch, чтобы поддержать `*` в паттернах вроде `test_*`
    и `*.min.*`. fnmatch регистрозависим на POSIX — это ожидаемо.
    """
    from fnmatch import fnmatch
    return fnmatch(name, pattern)


def _is_excluded(rel_path: Path, user_excludes: list[str]) -> bool:
    """Проверить, исключён ли файл по пути относительно project_root.

    Исключаем, если:
    - любая часть пути (папка) входит в DEFAULT_EXCLUDE_DIRS или
      user_excludes;
    - имя файла матчится любому паттерну из
      DEFAULT_EXCLUDE_FILE_PATTERNS или user_excludes.
    """
    parts = rel_path.parts
    # Проверяем папки (все, кроме последнего компонента — имени файла).
    for part in parts[:-1]:
        if part in DEFAULT_EXCLUDE_DIRS:
            return True
        if part in user_excludes:
            return True
    # Проверяем имя файла.
    name = parts[-1] if parts else ""
    for pattern in DEFAULT_EXCLUDE_FILE_PATTERNS:
        if _matches_glob(name, pattern):
            return True
    for pattern in user_excludes:
        if _matches_glob(name, pattern):
            return True
    return False


def _normalize_extensions(extensions: list[str]) -> tuple[str, ...]:
    """Привести расширения к единому виду: с точкой, в нижнем регистре."""
    result: list[str] = []
    for ext in extensions:
        ext = ext.strip().lower()
        if not ext:
            continue
        if not ext.startswith("."):
            ext = "." + ext
        result.append(ext)
    return tuple(result)


def _run_git(project_root: Path, args: list[str], timeout: int = 30) -> str | None:
    """Запустить git-команду и вернуть stdout, либо None при ошибке.

    Все git-вызовы идут через subprocess.run с capture_output=True,
    text=True, timeout=30 (см. ТЗ п. 6.1). Ошибки логируются как warning.
    """
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError:
        logger.warning("git не найден в PATH; git-данные недоступны")
        return None
    except subprocess.TimeoutExpired:
        logger.warning("git %s: таймаут %ss", " ".join(args), timeout)
        return None
    except OSError as exc:
        logger.warning("git %s: ошибка ОС: %s", " ".join(args), exc)
        return None

    if proc.returncode != 0:
        logger.warning(
            "git %s: код %s, stderr: %s",
            " ".join(args), proc.returncode, proc.stderr.strip()[:500],
        )
        return None
    return proc.stdout


def _get_git_commits(project_root: Path, limit: int) -> list[GitCommit]:
    """Получить последние `limit` коммитов (без merge).

    Формат: `%H|%s|%b` — по одному коммиту на запись, поля через `|`.
    Тело коммита (%b) может содержать переводы строк — поэтому парсим
    по первому и второму `|`, остаток — body (возможно, многострочный).
    """
    if limit <= 0:
        return []
    out = _run_git(
        project_root,
        ["log", "--no-merges", f"-{limit}", "--pretty=format:%H|%s|%b"],
    )
    if out is None or not out.strip():
        return []

    commits: list[GitCommit] = []
    # Записи разделены переводами строк, но body может содержать их же.
    # Надёжный парсер: каждая запись начинается с 40-символьного SHA + '|'.
    import re
    pattern = re.compile(r"^([0-9a-f]{40})\|(.*)$", re.MULTILINE)
    matches = list(pattern.finditer(out))
    for i, m in enumerate(matches):
        sha = m.group(1)
        rest = m.group(2)
        # rest = "<subject>|<body с возможными \n>"
        if "|" in rest:
            subject, body = rest.split("|", 1)
        else:
            subject, body = rest, ""
        # Обрезаем body до следующего коммита (если он был в этом же rest).
        if i + 1 < len(matches):
            next_start = matches[i + 1].start()
            # body тянется до конца текущей записи; уже ограничено split'ом
            # по matches, но на всякий случай оставим как есть.
            _ = next_start
        commits.append(
            GitCommit(sha=sha, subject=subject.strip(), body=body.strip())
        )
    return commits


def _get_tracked_files(project_root: Path) -> set[str]:
    """Получить множество относительных путей отслеживаемых файлов."""
    out = _run_git(project_root, ["ls-files"])
    if out is None:
        return set()
    return {line.strip() for line in out.splitlines() if line.strip()}


def _collect_git_data(project_root: Path, use_git: bool,
                      changelog_limit: int) -> GitData:
    """Собрать git-данные, если разрешено и репозиторий существует."""
    if not use_git:
        logger.info("git отключён (--no-git)")
        return GitData(has_git=False)
    if not (project_root / ".git").exists():
        logger.info("git-репозиторий не найден; работаем без git-данных")
        return GitData(has_git=False)

    commits = _get_git_commits(project_root, changelog_limit)
    tracked = _get_tracked_files(project_root)
    if not tracked:
        logger.warning("git ls-files пуст; работаем без git-фильтрации")
        return GitData(has_git=False)

    logger.info(
        "git: %d коммитов, %d отслеживаемых файлов",
        len(commits), len(tracked),
    )
    return GitData(has_git=True, commits=commits, tracked_files=tracked)


def _iter_filesystem(scan_root: Path, project_root: Path,
                     extensions: tuple[str, ...],
                     user_excludes: list[str]) -> list[Path]:
    """Рекурсивный обход файловой системы от scan_root."""
    result: list[Path] = []
    for path in scan_root.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in extensions:
            continue
        try:
            rel = path.relative_to(project_root)
        except ValueError:
            # Файл вне project_root — не наш случай, но на всякий случай.
            continue
        if _is_excluded(rel, user_excludes):
            continue
        result.append(path)
    return result


def _iter_tracked(git_data: GitData, project_root: Path,
                  scan_prefix: str | None,
                  extensions: tuple[str, ...],
                  user_excludes: list[str]) -> list[Path]:
    """Пройтись по отслеживаемым файлам и вернуть подходящие.

    scan_prefix — относительный префикс (src_dir), либо None, если
    обходим весь проект. Относительные пути из git ls-files — от корня
    проекта (POSIX-разделители, но на Linux = '/').
    """
    result: list[Path] = []
    prefix = scan_prefix.rstrip("/") + "/" if scan_prefix else ""
    for rel_str in sorted(git_data.tracked_files):
        if prefix and not rel_str.startswith(prefix):
            continue
        rel = Path(rel_str)
        if rel.suffix.lower() not in extensions:
            continue
        if _is_excluded(rel, user_excludes):
            continue
        abs_path = project_root / rel
        if not abs_path.is_file():
            # Файл в индексе, но отсутствует на диске — пропускаем.
            logger.debug("отслеживаемый файл отсутствует: %s", rel_str)
            continue
        result.append(abs_path)
    return result


def scan(project_root: Path,
         src_dir: str | None,
         extensions: list[str],
         user_excludes: list[str],
         use_git: bool,
         changelog_limit: int) -> tuple[list[Path], GitData]:
    """Сканировать проект и вернуть (файлы, git-данные).

    Параметры:
        project_root — корень целевого проекта (Path).
        src_dir — относительный путь подпапки с кодом, либо None.
        extensions — список расширений (например, ['.py', '.ts']).
        user_excludes — список имён папок/паттернов из --exclude.
        use_git — False, если передан --no-git.
        changelog_limit — сколько коммитов брать для CHANGELOG.

    Возвращает список абсолютных Path, отсортированный по строковому
    пути, и GitData. При пустом результате — ([], GitData(...)).
    """
    project_root = project_root.resolve()
    if not project_root.is_dir():
        raise ValueError(f"project_root не директория: {project_root}")

    if src_dir:
        scan_root = (project_root / src_dir).resolve()
        if not scan_root.is_dir():
            raise ValueError(
                f"--src-dir не найден или не директория: {scan_root}"
            )
        scan_prefix: str | None = src_dir.strip("/")
    else:
        scan_root = project_root
        scan_prefix = None

    exts = _normalize_extensions(extensions)
    if not exts:
        logger.warning("список расширений пуст; файлов не найдено")
        return [], GitData(has_git=False)

    git_data = _collect_git_data(project_root, use_git, changelog_limit)

    if git_data.has_git:
        files = _iter_tracked(
            git_data, project_root, scan_prefix, exts, user_excludes,
        )
        skipped_untracked = _count_untracked(
            scan_root, project_root, exts, user_excludes, git_data,
        )
        if skipped_untracked:
            logger.info(
                "git: %d файлов на диске не отслеживаются и пропущены",
                skipped_untracked,
            )
    else:
        files = _iter_filesystem(
            scan_root, project_root, exts, user_excludes,
        )

    files.sort(key=lambda p: str(p))
    logger.info(
        "сканирование: %d файлов (src_dir=%s, extensions=%s)",
        len(files), src_dir or "<весь проект>", ",".join(exts),
    )
    return files, git_data


def _count_untracked(scan_root: Path, project_root: Path,
                     extensions: tuple[str, ...],
                     user_excludes: list[str],
                     git_data: GitData) -> int:
    """Посчитать файлы на диске, которые не отслеживаются git.

    Только для информационного лога. Ошибки не критичны.
    """
    count = 0
    try:
        for path in scan_root.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix.lower() not in extensions:
                continue
            try:
                rel = path.relative_to(project_root).as_posix()
            except ValueError:
                continue
            if _is_excluded(Path(rel), user_excludes):
                continue
            if rel not in git_data.tracked_files:
                count += 1
    except OSError as exc:
        logger.warning("ошибка при подсчёте неотслеживаемых файлов: %s", exc)
    return count
