"""
reset_db.py

Project: THERESE - Transparent HR Employee Resource Evaluation System Enhanced
Complete database reset with new app structure.
"""

import os
import shutil
import subprocess
from pathlib import Path

def reset_database():
    print("=== THERESE Database Reset (New Structure) ===\n")

    base_dir = Path(__file__).resolve().parent
    venv_python = base_dir / "venv" / "Scripts" / "python.exe"

    # 1. Delete SQLite database
    print("1. Deleting SQLite database...")
    db_path = base_dir / "db.sqlite3"
    if db_path.exists():
        db_path.unlink()
        print("   â†’ db.sqlite3 deleted")
    else:
        print("   â†’ db.sqlite3 did not exist")

    # 2. Delete old migrations
    print("2. Deleting old migrations...")
    apps = ["core", "accounts", "hr", "finances", "tasks"]

    for app in apps:
        migrations_dir = base_dir / "apps" / app / "migrations"
        if migrations_dir.exists():
            shutil.rmtree(migrations_dir)
            print(f"   â†’ {app}/migrations deleted")
            
            migrations_dir.mkdir(parents=True, exist_ok=True)
            (migrations_dir / "__init__.py").touch()
            print(f"   â†’ {app}/migrations recreated")

    # 3. Create new migrations
    print("3. Creating new migrations...")
    subprocess.run([str(venv_python), "manage.py", "makemigrations"], check=True, cwd=base_dir)

    # 4. Apply migrations
    print("4. Applying migrations...")
    subprocess.run([str(venv_python), "manage.py", "migrate"], check=True, cwd=base_dir)


    # 5. Create superuser
    print("5. Creating superuser...")
    try:
        subprocess.run([str(venv_python), "manage.py", "createsuperuser"], check=True, cwd=base_dir)
    except subprocess.CalledProcessError:
        print("   â†’ Superuser creation skipped or already exists")

    # 5. Create superuser non-interactively (reliable for fresh installs)
    print("5. Creating superuser (admin / admin123)...")
    env = os.environ.copy()
    env["DJANGO_SUPERUSER_USERNAME"] = "admin"
    env["DJANGO_SUPERUSER_EMAIL"] = "admin@example.com"
    env["DJANGO_SUPERUSER_PASSWORD"] = "admin123"

    result = subprocess.run(
        [str(venv_python), "manage.py", "createsuperuser", "--noinput"],
        env=env,
        cwd=base_dir,
    )
    if result.returncode == 0:
        print("   â†’ Superuser 'admin' / 'admin123' created (is_staff + is_superuser)")
    else:
        print("   â†’ Superuser creation skipped (may already exist)")


    # 6. Load TV-L data
    print("6. Loading TV-L salary data...")
    subprocess.run([str(venv_python), "load_tv_l.py"], check=True, cwd=base_dir)

    print("\n=== Database reset completed successfully! ===")
    print("Start the server with: python manage.py runserver")


if __name__ == "__main__":
    reset_database()

