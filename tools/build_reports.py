#!/usr/bin/env python3
"""Compile the two editable LuaLaTeX documents. No Python packages required."""
import argparse
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
DOCUMENTS = ("nabari_research_report", "nabari_student_guide")


def main():
    parser = argparse.ArgumentParser(description="LuaLaTeXで報告書と高校生向け解説書をPDF化")
    parser.add_argument("--out", type=Path, default=ROOT / "build/latex")
    args = parser.parse_args()
    args.out = args.out.resolve()
    args.out.mkdir(parents=True, exist_ok=True)
    if not shutil.which("lualatex"):
        parser.error("lualatexがありません。docs/BUILD_LATEX.mdの準備を確認してください。")
    for name in DOCUMENTS:
        command = ["lualatex", "-interaction=nonstopmode", "-halt-on-error", "-file-line-error",
                   "-no-shell-escape", f"-output-directory={args.out}", name + ".tex"]
        for _ in range(2):
            subprocess.run(command, cwd=ROOT / "docs", check=True)
        print(args.out / (name + ".pdf"))


if __name__ == "__main__":
    main()
