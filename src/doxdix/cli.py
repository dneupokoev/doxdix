"""CLI doxdix: argparse, main(), проверка LLM, диспетчеризация.

Публичный API:
    main() -> int

Коды возврата:
    0 — успех без ошибок (в т.ч. --check/--restore OK)
    1 — были ошибки при обработке файлов
    2 — ошибка конфигурации (нет LLM/модели, неверный путь,
        отсутствие --model + DOXDIX_MODEL, неверный timestamp для --restore)
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from . import backup as backup_mod
from . import llm
from . import orchestrator

dv_file_version = '261028.17'
logger = logging.getLogger(__name__)


DEFAULT_OLLAMA_URL = "http://localhost:11434"
DEFAULT_EXTENSIONS = ".py,.js,.ts,.jsx,.tsx,.go,.rs"
DEFAULT_EXCLUDES = (
    ".git,.doxdix,node_modules,__pycache__,venv,.venv,env,dist,build,"
    "tests,test,.mypy_cache,.pytest_cache,.ruff_cache,target"
)


def _build_parser() -> argparse.ArgumentParser:
    """Собрать argparse со всеми флагами ТЗ п. 5."""
    p = argparse.ArgumentParser(
        prog="doxdix",
        description=(
            "Локальный CLI для генерации и актуализации документации "
            "проекта через LLM (Ollama или OpenAI-совместимый API)."
        ),
    )
    p.add_argument("project_path", metavar="PROJECT_PATH",
                   help="путь к корню целевого проекта")

    g = p.add_argument_group("пути и файлы")
    g.add_argument("--src-dir", metavar="PATH", default=None,
                   help="подпапка с исходным кодом (относительно PROJECT_PATH); "
                        "по умолчанию — весь проект")
    g.add_argument("--docs-dir", metavar="PATH", default="docs/modules",
                   help="куда класть документацию модулей "
                        "(по умолчанию: docs/modules)")
    g.add_argument("--no-monorepo", action="store_true",
                   help="не группировать файлы по подпроектам: плоская "
                        "структура docs/<docs-dir>/<путь>.md (как до "
                        "поддержки монорепозиториев)")
    g.add_argument("--extensions", metavar="LIST", default=DEFAULT_EXTENSIONS,
                   help=f"расширения через запятую (по умолчанию: "
                        f"{DEFAULT_EXTENSIONS})")
    g.add_argument("--exclude", metavar="LIST", default=DEFAULT_EXCLUDES,
                   help="имена папок/паттерны через запятую (добавляются к "
                        "дефолтным исключениям)")

    g = p.add_argument_group("LLM")
    g.add_argument("--model", metavar="NAME", default=None,
                   help="имя модели (по умолчанию: env DOXDIX_MODEL; "
                        "обязательно, если переменная не задана)")
    g.add_argument("--ollama-url", metavar="URL", default=None,
                   help=f"адрес LLM (по умолчанию: env DOXDIX_OLLAMA_URL "
                        f"или {DEFAULT_OLLAMA_URL}). URL с /v1 — "
                        f"OpenAI-совместимый режим")
    g.add_argument("--api-key", metavar="KEY", default=None,
                   help="API-ключ для OpenAI-совместимого режима "
                        "(по умолчанию: env DOXDIX_API_KEY или 'dummy')")
    g.add_argument("--timeout", type=int, metavar="SEC", default=300,
                   help="таймаут одного запроса к LLM (по умолчанию: 300)")
    g.add_argument("--num-ctx", type=int, metavar="N", default=8192,
                   help="размер контекстного окна для Ollama "
                        "(по умолчанию: 8192)")
    g.add_argument("--max-doc-tokens", type=int, metavar="N", default=3000,
                   help="если существующий .md больше — пропустить "
                        "актуализацию (по умолчанию: 3000)")

    g = p.add_argument_group("git")
    g.add_argument("--no-git", action="store_true",
                   help="не использовать git (не читать логи, не коммитить)")
    g.add_argument("--no-commit", action="store_true",
                   help="не делать git-коммиты после изменений")
    g.add_argument("--changelog-limit", type=int, metavar="N", default=100,
                   help="сколько коммитов брать для CHANGELOG "
                        "(по умолчанию: 100)")
    g.add_argument("--changelog-llm", action="store_true",
                   help="обогащать CHANGELOG через LLM")
    g.add_argument("--no-changelog", action="store_true",
                   help="не генерировать CHANGELOG")
    g.add_argument("--no-changelog-append", action="store_true",
                   help="перезаписывать CHANGELOG вместо дополнения "
                        "(по умолчанию — дополнение)")

    g = p.add_argument_group("бэкапы")
    g.add_argument("--backup-dir", metavar="PATH", default=None,
                   help="куда класть бэкапы "
                        "(по умолчанию: <project>/.doxdix/backups)")
    g.add_argument("--backup-keep", type=int, metavar="N", default=10,
                   help="сколько бэкапов хранить (по умолчанию: 10)")
    g.add_argument("--no-backup", action="store_true",
                   help="отключить бэкап")
    g.add_argument("--restore", metavar="TIMESTAMP", default=None,
                   help="восстановить из бэкапа и выйти")

    g = p.add_argument_group("прочее")
    g.add_argument("--init-license", action="store_true",
                   help="создать заготовку LICENSE (MIT), если файла нет")
    g.add_argument("--force", action="store_true",
                   help="игнорировать кэш .doxdix/cache.json и "
                        "перегенерировать все .md (полезно после смены "
                        "модели/промптов)")
    g.add_argument("--check", action="store_true",
                   help="проверить LLM и модель, выйти")
    g.add_argument("--no-readme", action="store_true",
                   help="не обновлять README.md (шаг 2 пропускается)")
    g.add_argument("--log-file", metavar="PATH", default=None,
                   help="файл лога (по умолчанию: <project>/doxdix.log)")
    return p


# --------------------------------------------------------------------------
# Логирование и разрешение параметров
# --------------------------------------------------------------------------

def _setup_logging(log_file: Path) -> None:
    """Настроить logging: stdout + файл (append). Уровень INFO.

    Формат: %(asctime)s [%(levelname)s] %(message)s (см. ТЗ п. 9).
    Если файл не удаётся открыть — warning, работаем только со stdout.
    """
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    # Чистим предыдущие хендлеры, если main() вызвали повторно в тестах
    for h in list(root.handlers):
        root.removeHandler(h)

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    root.addHandler(sh)

    try:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(log_file, mode="a", encoding="utf-8")
        fh.setFormatter(fmt)
        root.addHandler(fh)
    except OSError as exc:
        logger.warning("не удалось открыть лог-файл %s: %s", log_file, exc)


def _resolve_model(arg_value: str | None) -> str | None:
    """--model > env DOXDIX_MODEL. None — если ни того, ни другого."""
    if arg_value:
        return arg_value
    env = os.environ.get("DOXDIX_MODEL", "").strip()
    return env or None


def _resolve_url(arg_value: str | None) -> str:
    """--ollama-url > env DOXDIX_OLLAMA_URL > DEFAULT_OLLAMA_URL."""
    if arg_value:
        return arg_value.rstrip("/")
    env = os.environ.get("DOXDIX_OLLAMA_URL", "").strip()
    if env:
        return env.rstrip("/")
    return DEFAULT_OLLAMA_URL


def _resolve_api_key(arg_value: str | None) -> str:
    """--api-key > env DOXDIX_API_KEY > 'dummy'."""
    if arg_value is not None:
        return arg_value
    env = os.environ.get("DOXDIX_API_KEY", "").strip()
    return env or "dummy"


def _split_list(value: str) -> list[str]:
    """Разбить строку через запятую, обрезать пробелы, отбросить пустые."""
    return [x.strip() for x in value.split(",") if x.strip()]


# --------------------------------------------------------------------------
# --check
# --------------------------------------------------------------------------

def _cmd_check(args: argparse.Namespace) -> int:
    """Проверить LLM и наличие модели. Код 0 — ок, 2 — ошибка."""
    model = _resolve_model(args.model)
    if not model:
        print(
            "doxdix: не задана модель. Используйте --model NAME "
            "или переменную окружения DOXDIX_MODEL.",
            file=sys.stderr,
        )
        return 2
    url = _resolve_url(args.ollama_url)
    key = _resolve_api_key(args.api_key)

    try:
        available = llm.check_model(url, model, timeout=10, api_key=key)
    except llm.LLMError as exc:
        print(f"doxdix: ошибка LLM: {exc.message}", file=sys.stderr)
        if exc.body:
            print(f"  тело: {exc.body[:500]}", file=sys.stderr)
        return 2

    if available and model not in available:
        print(
            f"doxdix: модель {model!r} не найдена в {url}.",
            file=sys.stderr,
        )
        if available:
            print("  доступные модели:", file=sys.stderr)
            for name in available:
                print(f"    - {name}", file=sys.stderr)
        else:
            print("  сервер вернул пустой список моделей.",
                  file=sys.stderr)
        return 2

    print(f"doxdix: OK — LLM доступен, модель {model} найдена.")
    return 0


# --------------------------------------------------------------------------
# --restore
# --------------------------------------------------------------------------

def _cmd_restore(args: argparse.Namespace, project_root: Path) -> int:
    """Восстановить из бэкапа. Код 0 — ок, 2 — бэкап не найден."""
    backup_dir = (Path(args.backup_dir) if args.backup_dir
                  else project_root / ".doxdix" / "backups")
    restored = backup_mod.restore_backup(
        project_root, backup_dir, args.restore,
    )
    if restored is None:
        available = backup_mod.list_backups(backup_dir)
        print(
            f"doxdix: бэкап {args.restore!r} не найден в {backup_dir}.",
            file=sys.stderr,
        )
        if available:
            print("  доступные бэкапы (свежие сверху):", file=sys.stderr)
            for ts in available:
                print(f"    - {ts}", file=sys.stderr)
        else:
            print("  бэкапов нет.", file=sys.stderr)
        return 2
    print(f"doxdix: восстановлено файлов: {restored}")
    return 0


# --------------------------------------------------------------------------
# Сборка RunConfig и запуск конвейера
# --------------------------------------------------------------------------

def _build_run_config(args: argparse.Namespace,
                      project_root: Path) -> orchestrator.RunConfig:
    """Собрать RunConfig из argparse.Namespace + env."""
    model = _resolve_model(args.model)
    assert model is not None  # вызывающая сторона уже проверила
    url = _resolve_url(args.ollama_url)
    key = _resolve_api_key(args.api_key)

    backup_dir = (Path(args.backup_dir) if args.backup_dir
                  else project_root / ".doxdix" / "backups")
    log_file = (Path(args.log_file) if args.log_file
                else project_root / "doxdix.log")

    extensions = _split_list(args.extensions)
    excludes = _split_list(args.exclude)

    return orchestrator.RunConfig(
        project_root=project_root,
        src_dir=args.src_dir,
        docs_dir=args.docs_dir,
        monorepo=not args.no_monorepo,
        model=model,
        ollama_url=url,
        api_key=key,
        extensions=extensions,
        excludes=excludes,
        timeout=args.timeout,
        num_ctx=args.num_ctx,
        max_doc_tokens=args.max_doc_tokens,
        use_git=not args.no_git,
        do_commit=not args.no_commit and not args.no_git,
        changelog_limit=args.changelog_limit,
        changelog_llm=args.changelog_llm,
        do_changelog=not args.no_changelog,
        changelog_append=not args.no_changelog_append,
        backup_dir=backup_dir,
        backup_keep=args.backup_keep,
        do_backup=not args.no_backup,
        init_license=args.init_license,
        do_readme=not args.no_readme,
        force=args.force,
        log_file=log_file,
    )


def _cmd_run(args: argparse.Namespace, project_root: Path) -> int:
    """Основной запуск: настроить лог, проверить LLM, вызвать run()."""
    cfg = _build_run_config(args, project_root)
    # cli — единственное место, где достраивается дефолтный путь лога
    # (RunConfig.log_file по умолчанию None, см. п. 5/9 ТЗ).
    log_file = cfg.log_file or (project_root / "doxdix.log")
    _setup_logging(log_file)

    logger.info("doxdix: project=%s", project_root)
    logger.info("doxdix: model=%s url=%s", cfg.model, cfg.ollama_url)

    # Проверка LLM+модели перед запуском (решение п. 2).
    try:
        available = llm.check_model(
            cfg.ollama_url, cfg.model, timeout=10, api_key=cfg.api_key,
        )
    except llm.LLMError as exc:
        logger.error("ошибка LLM: %s", exc.message)
        if exc.body:
            logger.error("тело: %s", exc.body[:500])
        return 2
    if available and cfg.model not in available:
        logger.error("модель %r не найдена в %s", cfg.model, cfg.ollama_url)
        if available:
            logger.error("доступные модели:")
            for name in available:
                logger.error("  - %s", name)
        return 2

    try:
        stats = orchestrator.run(cfg)
    except orchestrator.ConfigError as exc:
        # Неверный путь/конфигурация — код 2 (ТЗ п. 5, п. 10).
        logger.error("конфигурация: %s", exc)
        return 2
    logger.info(
        "Успешно: %d, ошибок: %d, пропущено: %d. Лог: %s",
        stats.success, stats.errors, stats.skipped, log_file,
    )
    return 0 if stats.errors == 0 else 1


# --------------------------------------------------------------------------
# main()
# --------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    """Точка входа. Диспетчеризация: --restore, --check, основной запуск."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    # PROJECT_PATH обязателен для всех режимов.
    project_root = Path(args.project_path).expanduser()
    if not project_root.is_dir():
        print(
            f"doxdix: PROJECT_PATH не директория: {project_root}",
            file=sys.stderr,
        )
        return 2
    project_root = project_root.resolve()

    # --restore — до проверки LLM, без него вообще (решение п. 3).
    if args.restore:
        # Логирование в файл, чтобы был след, но без проверки LLM.
        log_file = (Path(args.log_file) if args.log_file
                    else project_root / "doxdix.log")
        _setup_logging(log_file)
        return _cmd_restore(args, project_root)

    # --check — проверить LLM и выйти.
    if args.check:
        return _cmd_check(args)

    # Основной запуск.
    return _cmd_run(args, project_root)


if __name__ == "__main__":
    sys.exit(main())
