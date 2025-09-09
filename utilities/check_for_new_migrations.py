from re import sub
import subprocess
import sys

NO_CHANGES_STRING = "No changes detected"
CREATE_MIGRATIONS_COMMAND = "python3.10 web/manage.py makemigrations --no-input"


def uncreated_migrations_exist():
    with subprocess.Popen(CREATE_MIGRATIONS_COMMAND, shell=True, stdout=subprocess.PIPE) as process:
        process.wait()
        subprocess_return_string = process.stdout.read().decode("utf-8")
    if NO_CHANGES_STRING not in subprocess_return_string:
        return True
    return False


def main() -> None:
    if uncreated_migrations_exist():
        sys.exit(1)


if __name__ == '__main__':
    main()
