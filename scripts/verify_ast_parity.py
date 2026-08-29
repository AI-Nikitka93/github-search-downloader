#!/usr/bin/env python3
"""
AST Parity Validator for Multi-lingual Documentation (EN & RU)
Ensures 100% heading depth parity and code block alignment between README.md and README.ru.md.
"""

import sys
import re
from pathlib import Path

def extract_headings(file_path: Path):
    headings = []
    lines = file_path.read_text(encoding="utf-8").splitlines()
    in_code_block = False
    for idx, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code_block = not in_code_block
            continue
        if not in_code_block and stripped.startswith("#"):
            match = re.match(r"^(#+)\s+(.*)$", stripped)
            if match:
                level = len(match.group(1))
                title = match.group(2).strip()
                headings.append((idx, level, title))
    return headings

def main():
    root = Path(__file__).resolve().parent.parent
    en_file = root / "README.md"
    ru_file = root / "README.ru.md"

    if not en_file.exists():
        print(f"Error: {en_file} not found.", file=sys.stderr)
        sys.exit(1)
    if not ru_file.exists():
        print(f"Error: {ru_file} not found.", file=sys.stderr)
        sys.exit(1)

    en_headings = extract_headings(en_file)
    ru_headings = extract_headings(ru_file)

    en_depths = [h[1] for h in en_headings]
    ru_depths = [h[1] for h in ru_headings]

    print(f"[AST Validator] Parsed {len(en_headings)} headings from README.md")
    print(f"[AST Validator] Parsed {len(ru_headings)} headings from README.ru.md")

    if en_depths != ru_depths:
        print("[AST Validator FAILED] Heading depth mismatch detected!", file=sys.stderr)
        print(f"EN Depths ({len(en_depths)}): {en_depths}", file=sys.stderr)
        print(f"RU Depths ({len(ru_depths)}): {ru_depths}", file=sys.stderr)
        for i, ((en_l, en_d, en_t), (ru_l, ru_d, ru_t)) in enumerate(zip(en_headings, ru_headings)):
            if en_d != ru_d:
                print(f"Mismatch at index {i}: EN (L{en_l}, H{en_d}) '{en_t}' != RU (L{ru_l}, H{ru_d}) '{ru_t}'", file=sys.stderr)
        sys.exit(1)

    print("[AST Validator SUCCESS] 100% Heading Depth Parity Confirmed.")
    sys.exit(0)

if __name__ == "__main__":
    main()
