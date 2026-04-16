import os
import sys
from datetime import datetime

def create_project_snapshot():
    print("=== THERESE / Projekt Snapshot Tool ===\n")

    # Projektname: entweder als Argument oder per Eingabe
    if len(sys.argv) > 1:
        project_name = sys.argv[1]
        print(f"Projektname aus Argument: {project_name}")
    else:
        default_name = "therese"
        project_name = input(f"Projektname eingeben (Enter für '{default_name}'): ").strip()
        if not project_name:
            project_name = default_name

    root_dir = os.path.abspath(".")
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    output_file = f"{timestamp}-{project_name}.txt"

    # Relevante Dateitypen
    relevant_extensions = {'.py', '.html', '.txt', '.md', '.env', '.json', '.yaml', '.yml', '.css', '.js'}

    # Ignorierte Verzeichnisse und Dateien
    ignore_dirs = {'venv', '.git', '__pycache__', 'migrations', 'media', 'staticfiles', 
                   'node_modules', '.vscode', '.idea', 'static', 'staticfiles'}
    ignore_files = {'.DS_Store', 'db.sqlite3', '*.pyc', '*.pyo', '*.log'}

    collected_files = []

    print(f"Erstelle Snapshot für Projekt: {project_name}")
    print(f"Ausgabedatei: {output_file}\n")

    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(f"=== PROJECT SNAPSHOT ===\n")
        f.write(f"Projekt     : {project_name}\n")
        f.write(f"Erstellt am : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Root-Pfad   : {root_dir}\n")
        f.write("=" * 90 + "\n\n")

        # Inhaltsverzeichnis sammeln
        f.write("INHALTSVERZEICHNIS:\n")
        f.write("-" * 40 + "\n")

        file_count = 0

        for root, dirs, files in os.walk(root_dir):
            dirs[:] = [d for d in dirs if d not in ignore_dirs]

            for file in files:
                if any(file.endswith(ext) for ext in relevant_extensions):
                    if file in ignore_files or any(file.startswith(p.replace('*','')) for p in ignore_files if '*' in p):
                        continue

                    file_path = os.path.join(root, file)
                    rel_path = os.path.relpath(file_path, root_dir)
                    collected_files.append(rel_path)

                    f.write(f"{file_count+1:3d}. {rel_path}\n")
                    file_count += 1

        f.write("-" * 40 + "\n\n")
        f.write(f"Gesamtanzahl Dateien: {file_count}\n\n")
        f.write("=" * 90 + "\n\n")

        # Inhalte der Dateien schreiben
        for i, rel_path in enumerate(collected_files, 1):
            file_path = os.path.join(root_dir, rel_path)
            
            f.write(f"{i:3d}. DATEI: {rel_path}\n")
            f.write("=" * 90 + "\n")

            try:
                with open(file_path, 'r', encoding='utf-8') as source:
                    content = source.read()
            except Exception:
                content = "<<< Konnte Datei nicht lesen (binär oder Encoding-Fehler) >>>"

            f.write(content)
            f.write("\n\n")

    print(f"\n✅ Snapshot erfolgreich erstellt!")
    print(f"   Datei     : {output_file}")
    print(f"   Dateien   : {file_count}")
    print(f"   Größe     : {os.path.getsize(output_file) / 1024:.1f} KB")


if __name__ == "__main__":
    create_project_snapshot()