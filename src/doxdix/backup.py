"""Бэкап документации: создание, восстановление, ротация.

Публичный API:
    create_backup(project_root, backup_dir, keep) -> Path | None
    restore_backup(project_root, backup_dir, timestamp) -> int | None
    list_backups(backup_dir) -> list[str]

Правила (см. ТЗ п. 6.2 и решения по неоднозначностям):
- Бэкап кладётся в <backup_dir>/<ISO-timestamp>/.
- Копируются README.md, CHANGELOG.md и всё содержимое docs/.
- manifest.json: {"timestamp": ..., "files": [{"path": ..., "sha256": ...}]}.
- Ротация: оставить `keep` последних (сортировка по имени папки).
- При коллизии timestamp — суффикс -1, -2, ...
- Восстановление: копирование обратно, отсутствующие в бэкапе файлы
  не удаляются.
"""
from __future__ import annotations

import hashlib
import json
import logging
import shutil
from datetime import datetime
from pathlib import Path

dv_file_version = '261028.03'
logger = logging.getLogger(__name__)


def _iso_timestamp() -> str:
    """Текущий timestamp в формате 2026-10-28T14-30-00 (двоеточия → дефисы)."""
    return datetime.now().strftime("%Y-%m-%dT%H-%M-%S")


def _sha256(path: Path) -> str:
    """SHA-256 файла, hex-строка."""
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _unique_backup_dir(backup_dir: Path) -> tuple[str, Path]:
    """Подобрать свободный timestamp и вернуть (timestamp, path).

    При коллизии добавляем суффикс -1, -2, ... — см. решение п. 9.
    """
    base_ts = _iso_timestamp()
    candidate = backup_dir / base_ts
    if not candidate.exists():
        return base_ts, candidate
    i = 1
    while True:
        ts = f"{base_ts}-{i}"
        candidate = backup_dir / ts
        if not candidate.exists():
            return ts, candidate
        i += 1


def list_backups(backup_dir: Path) -> list[str]:
    """Список timestamp'ов существующих бэкапов, свежие сверху."""
    if not backup_dir.is_dir():
        return []
    names = [
        p.name for p in backup_dir.iterdir()
        if p.is_dir() and not p.name.startswith(".")
    ]
    names.sort(reverse=True)
    return names


def _rotate(backup_dir: Path, keep: int) -> None:
    """Удалить старые бэкапы, оставив `keep` последних.

    Сортировка по имени папки лексикографически корректна для формата
    YYYY-MM-DDTHH-MM-SS и суффиксов -1, -2 (см. решение п. 9).
    Если бэкапов меньше или равно keep — ничего не удаляем.
    """
    if keep <= 0:
        return
    backups = list_backups(backup_dir)  # свежие сверху
    if len(backups) <= keep:
        return
    to_remove = backups[keep:]
    for name in to_remove:
        path = backup_dir / name
        try:
            shutil.rmtree(path)
            logger.info("ротация бэкапов: удалён %s", name)
        except OSError as exc:
            logger.warning("ротация бэкапов: не удалось удалить %s: %s",
                           name, exc)


def _collect_backup_targets(project_root: Path) -> list[Path]:
    """Собрать файлы для бэкапа (относительные пути от project_root).

    README.md, CHANGELOG.md (если есть) + всё содержимое docs/ (если есть).
    """
    targets: list[Path] = []
    for name in ("README.md", "CHANGELOG.md"):
        p = project_root / name
        if p.is_file():
            targets.append(Path(name))
    docs = project_root / "docs"
    if docs.is_dir():
        for p in docs.rglob("*"):
            if p.is_file():
                try:
                    targets.append(p.relative_to(project_root))
                except ValueError:
                    continue
    return targets


def create_backup(project_root: Path, backup_dir: Path,
                  keep: int) -> Path | None:
    """Создать бэкап документации. Вернуть Path бэкапа или None.

    Ошибки не фатальны для конвейера: логируем error, возвращаем None.
    """
    project_root = project_root.resolve()
    backup_dir = backup_dir.resolve()

    targets = _collect_backup_targets(project_root)
    if not targets:
        logger.info("бэкап: нечего копировать (нет README/CHANGELOG/docs)")
        return None

    try:
        backup_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        logger.error("бэкап: не удалось создать %s: %s", backup_dir, exc)
        return None

    ts, dest = _unique_backup_dir(backup_dir)
    try:
        dest.mkdir(parents=True, exist_ok=False)
    except OSError as exc:
        logger.error("бэкап: не удалось создать %s: %s", dest, exc)
        return None

    manifest_files: list[dict[str, str]] = []
    copied = 0
    for rel in targets:
        src = project_root / rel
        dst = dest / rel
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            manifest_files.append({
                "path": rel.as_posix(),
                "sha256": _sha256(dst),
            })
            copied += 1
        except OSError as exc:
            logger.error("бэкап: ошибка копирования %s: %s", rel, exc)

    manifest = {
        "timestamp": ts,
        "files": manifest_files,
    }
    try:
        (dest / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError as exc:
        logger.error("бэкап: не удалось записать manifest.json: %s", exc)
        return None

    logger.info("бэкап: %s (%d файлов)", dest, copied)
    _rotate(backup_dir, keep)
    return dest


def restore_backup(project_root: Path, backup_dir: Path,
                   timestamp: str) -> int | None:
    """Восстановить файлы из бэкапа. Вернуть число файлов или None.

    None — если бэкап не найден или manifest.json отсутствует.
    Отсутствующие в бэкапе файлы проекта не удаляются.
    """
    project_root = project_root.resolve()
    backup_dir = backup_dir.resolve()
    src = backup_dir / timestamp
    manifest_path = src / "manifest.json"
    if not src.is_dir() or not manifest_path.is_file():
        logger.error("восстановление: бэкап не найден: %s", src)
        return None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.error("восстановление: битый manifest.json: %s", exc)
        return None

    restored = 0
    for entry in manifest.get("files", []):
        rel_str = entry.get("path")
        if not rel_str:
            continue
        rel = Path(rel_str)
        src_file = src / rel
        dst_file = project_root / rel
        if not src_file.is_file():
            logger.warning("восстановление: файл отсутствует в бэкапе: %s",
                           rel_str)
            continue
        try:
            dst_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_file, dst_file)
            restored += 1
        except OSError as exc:
            logger.error("восстановление: ошибка копирования %s: %s",
                         rel_str, exc)
    logger.info("восстановление: %d файлов из %s", restored, timestamp)
    return restored
