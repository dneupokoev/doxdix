"""Кэш SHA-256 хэшей исходного кода: `<project>/.doxdix/cache.json`.

Формат файла: {"относительный/путь.py": "<sha256 в hex>"}.

Назначение — не отправлять в LLM файлы, код которых не менялся с
прошлого запуска (экономия токенов и времени). При `RunConfig.force`
кэш игнорируется (см. cli.py, флаг --force).

Публичный API:
    CACHE_DIR, CACHE_FILENAME
    cache_file_path(project_root), file_sha256(path)
    Cache (load/save/get/set/is_unchanged)
"""
from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

dv_file_version = '261028.18'
logger = logging.getLogger(__name__)

CACHE_DIR = ".doxdix"
CACHE_FILENAME = "cache.json"
# Читаем файл порциями: не грузим содержимое целиком в память.
_READ_CHUNK = 1024 * 1024


def cache_file_path(project_root: Path) -> Path:
    """Путь к файлу кэша: <project>/.doxdix/cache.json."""
    return project_root / CACHE_DIR / CACHE_FILENAME


def file_sha256(code_path: Path) -> str | None:
    """SHA-256 содержимого файла в hex; None при ошибке чтения."""
    digest = hashlib.sha256()
    try:
        with code_path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(_READ_CHUNK), b""):
                digest.update(chunk)
    except OSError as exc:
        logger.warning("кэш: не удалось прочитать %s: %s", code_path, exc)
        return None
    return digest.hexdigest()


class Cache:
    """Хэши содержимого файлов, прочитанные из .doxdix/cache.json.

    Отсутствующий или битый файл кэша не фатален: кэш считается
    пустым. save() пишет файл только если данные менялись.
    """

    def __init__(self, project_root: Path,
                 data: dict[str, str] | None = None) -> None:
        self._path = cache_file_path(project_root)
        self._data: dict[str, str] = dict(data or {})
        self._dirty = False

    @classmethod
    def load(cls, project_root: Path) -> "Cache":
        """Прочитать кэш; при любой проблеме вернуть пустой."""
        path = cache_file_path(project_root)
        if not path.is_file():
            logger.debug("кэш: %s отсутствует, начинаем с пустого", path)
            return cls(project_root)
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            logger.warning(
                "кэш: не удалось прочитать %s (%s); начинаем с пустого",
                path, exc,
            )
            return cls(project_root)
        if not isinstance(raw, dict):
            logger.warning(
                "кэш: %s: ожидался объект JSON; начинаем с пустого", path,
            )
            return cls(project_root)
        data = {str(k): str(v) for k, v in raw.items()}
        logger.debug("кэш: загружено записей: %d", len(data))
        return cls(project_root, data)

    def get(self, rel_key: str) -> str | None:
        """Хэш из кэша по относительному пути (posix) или None."""
        return self._data.get(rel_key)

    def set(self, rel_key: str, sha: str) -> None:
        """Запомнить хэш файла (запись произойдёт в save())."""
        if self._data.get(rel_key) != sha:
            self._data[rel_key] = sha
            self._dirty = True

    def is_unchanged(self, rel_key: str, sha: str,
                     md_path: Path) -> bool:
        """True, если хэш совпал с кэшем и итоговый .md уже существует."""
        return md_path.is_file() and self._data.get(rel_key) == sha

    def save(self) -> bool:
        """Записать кэш, если были изменения. True при успехе."""
        if not self._dirty:
            return True
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(
                json.dumps(self._data, ensure_ascii=False,
                           indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        except OSError as exc:
            logger.warning("кэш: не удалось записать %s: %s",
                           self._path, exc)
            return False
        self._dirty = False
        logger.debug("кэш: сохранено записей: %d", len(self._data))
        return True
