from re import sub
import subprocess
import sys

NO_CHANGES_STRING = "No changes detected"
CREATE_MIGRATIONS_COMMAND = "python ../web/manage.py makemigrations"

def check_for_migrations():
    process = subprocess.Popen(CREATE_MIGRATIONS_COMMAND, shell=True, stdout=subprocess.PIPE)
    subprocess_return_string = process.stdout.read().decode("utf-8")
    if subprocess_return_string is not NO_CHANGES_STRING:
        return True
    return False


def main() -> None:
    if check_for_migrations():
        sys.exit(1)
    sys.exit(0)

if __name__ == '__main__':
    main()
