"""Empacota todo o código-fonte do projeto em um único arquivo Markdown."""

from __future__ import annotations

import argparse
import os
from datetime import datetime
from pathlib import Path

IGNORE_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "node_modules",
    "dist",
    "build",
    ".eggs",
    ".tox",
    ".idea",
    ".vscode",
}

IGNORE_FILES = {
    "uv.lock",
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "poetry.lock",
    "PLANO_MESTRE_JULES.md",
    "README.md",
    "tests/test_buddy.py",
    "tests/test_hook_bridge.py",
    "tests/test_ipc.py",
    "tests/test_pet.py",
    "tests/test_sprites.py",
    "tests/test_swarm.py",
}

BINARY_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".bmp", ".svg",
    ".mp3", ".wav", ".ogg", ".flac", ".mp4", ".avi", ".mov", ".webm",
    ".pdf", ".zip", ".tar", ".gz", ".7z", ".rar",
    ".exe", ".dll", ".so", ".dylib", ".pyd", ".pyc", ".pyo",
    ".db", ".sqlite", ".sqlite3", ".bin", ".dat",
    ".woff", ".woff2", ".ttf", ".otf", ".eot",
}

EXT_TO_LANG = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".jsx": "jsx",
    ".tsx": "tsx",
    ".json": "json",
    ".toml": "toml",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".md": "markdown",
    ".html": "html",
    ".css": "css",
    ".scss": "scss",
    ".sql": "sql",
    ".sh": "bash",
    ".bat": "bat",
    ".ps1": "powershell",
    ".ini": "ini",
    ".cfg": "ini",
    ".env": "dotenv",
    ".xml": "xml",
    ".txt": "text",
}


def is_binary_file(path: Path) -> bool:
    if path.suffix.lower() in BINARY_EXTENSIONS:
        return True
    try:
        with path.open("rb") as f:
            chunk = f.read(4096)
        return b"\x00" in chunk
    except OSError:
        return True


def collect_files(root: Path, output_path: Path, include_self: bool) -> list[Path]:
    self_path = Path(__file__).resolve()
    out_resolved = output_path.resolve()
    files: list[Path] = []

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(
            d for d in dirnames
            if d not in IGNORE_DIRS and not d.endswith(".egg-info")
        )
        for name in sorted(filenames):
            if name in IGNORE_FILES:
                continue
            file_path = Path(dirpath) / name
            resolved = file_path.resolve()
            if resolved == out_resolved:
                continue
            if not include_self and resolved == self_path:
                continue
            if is_binary_file(file_path):
                continue
            files.append(file_path)

    return files


def fence_for_content(content: str) -> str:
    fence = "```"
    while fence in content:
        fence += "`"
    return fence


def pack_project(root: Path, output_path: Path, include_self: bool = False) -> tuple[int, Path]:
    files = collect_files(root, output_path, include_self=include_self)
    lines: list[str] = [
        f"# Projeto: {root.name}",
        "",
        f"Gerado em: `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`  ",
        f"Total de arquivos: **{len(files)}**",
        "",
        "## Estrutura de Arquivos",
        "",
    ]

    rel_paths = [f.relative_to(root).as_posix() for f in files]
    for rel in rel_paths:
        lines.append(f"- `{rel}`")

    lines.extend(["", "---", ""])

    for file_path, rel in zip(files, rel_paths):
        try:
            content = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            content = file_path.read_text(encoding="latin-1")

        lang = EXT_TO_LANG.get(file_path.suffix.lower(), "")
        fence = fence_for_content(content)
        lines.append(f"## `{rel}`")
        lines.append("")
        lines.append(f"{fence}{lang}")
        lines.append(content.rstrip("\r\n"))
        lines.append(fence)
        lines.append("")

    output_path.write_text("\n".join(lines), encoding="utf-8")
    return len(files), output_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Empacota os arquivos do projeto em um único arquivo Markdown."
    )
    parser.add_argument(
        "-r", "--root",
        type=Path,
        default=Path.cwd(),
        help="Pasta raiz do projeto (padrão: diretório atual).",
    )
    parser.add_argument(
        "-o", "--output",
        type=Path,
        default=Path("projeto_empacotado.md"),
        help="Arquivo Markdown de saída (padrão: projeto_empacotado.md).",
    )
    parser.add_argument(
        "--include-self",
        action="store_true",
        help="Inclui este próprio script no arquivo gerado.",
    )
    args = parser.parse_args()

    root = args.root.resolve()
    output = args.output if args.output.is_absolute() else (root / args.output)

    count, out_file = pack_project(root, output, include_self=args.include_self)
    print(f"Empacotados {count} arquivos em: {out_file}")


if __name__ == "__main__":
    main()
