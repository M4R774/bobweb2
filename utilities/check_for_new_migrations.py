import shutil
import subprocess
import sys

NO_CHANGES_STRING = "No changes detected"
PYTHON_EXECUTABLES = ["venv\Scripts\python.exe", "python3.10", "python3", "python"]


def get_available_python_executable() -> str:
    for exe in PYTHON_EXECUTABLES:
        if shutil.which(exe):
            return exe
    raise RuntimeError("No valid Python executable found in PYTHON_EXECUTABLES.")


def uncreated_migrations_exist() -> bool:
    python_exe = get_available_python_executable()
    create_migrations_command = f"{python_exe} web/manage.py makemigrations --no-input --dry-run"

    with subprocess.Popen(create_migrations_command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE) as process:
        process.wait()
        stdout = process.stdout.read().decode("utf-8")
        stderr = process.stderr.read().decode("utf-8")
        if process.returncode != 0:
            raise RuntimeError(f"Migration command failed: {stderr.strip() or stdout.strip()}")
    return NO_CHANGES_STRING not in stdout


def main() -> None:
    if uncreated_migrations_exist():
        sys.exit(1)


if __name__ == '__main__':
    main()
