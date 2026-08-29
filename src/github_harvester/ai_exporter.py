import os
from pathlib import Path
from typing import Sequence

# Common binary or ignored extensions
BINARY_EXTENSIONS = {
    ".exe", ".dll", ".so", ".dylib", ".bin", ".dat", ".db", ".sqlite", ".sqlite3",
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".svg", ".webp", ".tiff",
    ".mp3", ".mp4", ".avi", ".mkv", ".mov", ".flv", ".wav", ".ogg",
    ".zip", ".tar", ".gz", ".rar", ".7z", ".bz2", ".xz",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".pyc", ".pyo", ".pyd", ".class", ".o", ".obj", ".a", ".lib",
    ".eot", ".ttf", ".woff", ".woff2",
}

IGNORED_DIRECTORIES = {
    ".git", ".svn", ".hg", "node_modules", "venv", ".venv", "env", ".env",
    "__pycache__", ".idea", ".vscode", "build", "dist"
}

def is_binary_string(bytes_val: bytes) -> bool:
    """Heuristic to determine if a byte string is binary."""
    textchars = bytearray({7,8,9,10,12,13,27} | set(range(0x20, 0x100)) - {0x7f})
    return bool(bytes_val.translate(None, textchars))

def is_binary_file(filepath: Path) -> bool:
    if filepath.suffix.lower() in BINARY_EXTENSIONS:
        return True
    try:
        with open(filepath, "rb") as f:
            chunk = f.read(1024)
            if b"\0" in chunk:
                return True
            if is_binary_string(chunk):
                return True
    except Exception:
        return True
    return False

def generate_repo_map(repo_path: Path) -> str:
    """Generate a text-based tree representation of the repository."""
    lines = []
    
    def walk_dir(current_path: Path, prefix: str = ""):
        try:
            entries = sorted(list(current_path.iterdir()), key=lambda x: (x.is_file(), x.name.lower()))
        except PermissionError:
            return
            
        entries = [e for e in entries if e.name not in IGNORED_DIRECTORIES]
        
        for i, entry in enumerate(entries):
            is_last = (i == len(entries) - 1)
            pointer = "└── " if is_last else "├── "
            lines.append(prefix + pointer + entry.name)
            
            if entry.is_dir():
                extension = "    " if is_last else "│   "
                walk_dir(entry, prefix + extension)

    lines.append(repo_path.name + "/")
    walk_dir(repo_path)
    return "\n".join(lines)

def export_repo_for_ai(repo_name: str, repo_path: Path, output_root: Path) -> Path:
    """
    Generate an AI-ready XML dump (Repomix format) for a downloaded repository.
    Saves the result to output_root/ai_exports/repo_name.xml.
    """
    safe_name = repo_name.replace("/", "_")
    ai_export_dir = output_root / "ai_exports"
    ai_export_dir.mkdir(parents=True, exist_ok=True)
    
    export_file = ai_export_dir / f"{safe_name}.xml"
    
    repo_map = generate_repo_map(repo_path)
    
    with open(export_file, "w", encoding="utf-8", errors="replace") as out_f:
        out_f.write(f'<?xml version="1.0" encoding="UTF-8"?>\n')
        out_f.write(f'<repository name="{repo_name}">\n')
        
        out_f.write('  <repo_map>\n')
        out_f.write('    <![CDATA[\n')
        out_f.write(repo_map + "\n")
        out_f.write('    ]]>\n')
        out_f.write('  </repo_map>\n\n')
        
        out_f.write('  <files>\n')
        
        for root, dirs, files in os.walk(repo_path):
            dirs[:] = [d for d in dirs if d not in IGNORED_DIRECTORIES]
            for file in files:
                if file in IGNORED_DIRECTORIES:
                    continue
                filepath = Path(root) / file
                if not filepath.is_file():
                    continue
                if is_binary_file(filepath):
                    continue
                
                try:
                    rel_path = filepath.relative_to(repo_path)
                    content = filepath.read_text(encoding="utf-8", errors="replace")
                    content = content.replace("]]>", "]]]]><![CDATA[>")
                    out_f.write(f'    <file path="{rel_path}">\n')
                    out_f.write(f'      <![CDATA[\n{content}\n      ]]>\n')
                    out_f.write(f'    </file>\n')
                except Exception as e:
                    print(f"Skipping file {filepath}: {e}")
                    
        out_f.write('  </files>\n')
        out_f.write('</repository>\n')
        
    return export_file
