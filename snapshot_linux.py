"""
snapshot.py

Project: THERESE - Transparent HR Employee Resource Evaluation System Enhanced
"""

import os
import sys
from datetime import datetime


def create_project_snapshot():
    print("=== THERESE / Project Snapshot Tool ===\n")

    # Project name
    if len(sys.argv) > 1:
        project_name = sys.argv[1]
    else:
        default_name = "therese"
        project_name = input(f"Enter project name (Enter for '{default_name}'): ").strip() or default_name

    root_dir = os.path.abspath(".")
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    output_file = f"{timestamp}-{project_name}.txt"

    relevant_extensions = {'.py', '.html', '.js', '.css', '.txt', '.md', '.json'}

    ignore_dirs = {
        'venv', '.git', '__pycache__', 'migrations', 'media', 'staticfiles',
        'node_modules', '.vscode', '.idea', 'static', 'logs', 'backup',
        'temp', 'cache', 'env', 'ENV', 'dist', 'build', 'certs',
    }

    ignore_files = {
        '.DS_Store', 'db.sqlite3', '.env', 'DEMO_ANLEITUNG.txt',
        '*.pyc', '*.pyo', '*.log', '*.sqlite3',
        'snapshot.py', 'snapshot_linux.py', '*therese.txt',
        'EmployeeForm_*.txt', 'employee_form_init_*.txt',
        '*.png', '*.jpg', '*.jpeg', '*.gif',
        '*.min.js', '*.min.css', '*.woff', '*.woff2', '*.ttf', '*.eot',
        'Thumbs.db', '*.bak', '*.tmp', '*.pem', '*.key',
    }

    def should_ignore_file(file):
        if file in ignore_files:
            return True
        for pattern in ignore_files:
            if '*' not in pattern:
                continue
            prefix, suffix = pattern.split('*', 1)
            if prefix and file.startswith(prefix):
                return True
            if suffix and file.endswith(suffix):
                return True
        return False

    collected_files = []
    file_count = 0

    print(f"Creating snapshot for project: {project_name}")
    print(f"Output file: {output_file}\n")

    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(f"=== PROJECT SNAPSHOT ===\n")
        f.write(f"Project     : {project_name}\n")
        f.write(f"Created on  : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Root path   : {root_dir}\n")
        f.write("=" * 90 + "\n\n")

        f.write("TABLE OF CONTENTS:\n")
        f.write("-" * 40 + "\n")

        for root, dirs, files in os.walk(root_dir):
            dirs[:] = [d for d in dirs if d not in ignore_dirs]

            for file in files:
                if file.startswith('.env') or file.endswith('.env'):
                    continue
                if any(file.endswith(ext) for ext in relevant_extensions):
                    if should_ignore_file(file):
                        continue

                    rel_path = os.path.relpath(os.path.join(root, file), root_dir)
                    collected_files.append(rel_path)

                    f.write(f"{file_count + 1:3d}. {rel_path}\n")
                    file_count += 1

        f.write("-" * 40 + "\n\n")
        f.write(f"Total files: {file_count}\n\n")
        f.write("=" * 90 + "\n\n")

        for i, rel_path in enumerate(collected_files, 1):
            file_path = os.path.join(root_dir, rel_path)
            f.write(f"{i:3d}. FILE: {rel_path}\n")
            f.write("=" * 90 + "\n")

            try:
                with open(file_path, 'r', encoding='utf-8') as source:
                    content = source.read()
            except Exception:
                content = "<<< Could not read file (binary or encoding error) >>>"

            f.write(content)
            f.write("\n\n")

    print(f"\n✅ Snapshot successfully created!")
    print(f"   File      : {output_file}")
    print(f"   Files     : {file_count}")


if __name__ == "__main__":
    create_project_snapshot()
