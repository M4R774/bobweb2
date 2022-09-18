#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys


def main():
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'bobweb.web.web.settings')
    # Add bobweb2 project to path from bobweb2/bobweb/web/manage.py
    sys.path.append(os.path.dirname(os.path.abspath(__file__)) + '/../..')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    try:
        execute_from_command_line(sys.argv)
    except RuntimeError as e:
        print(e)


if __name__ == '__main__':
    main()
