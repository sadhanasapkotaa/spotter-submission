#!/usr/bin/env python
import os
import sys


def main():
    # Default to local; every deployed environment sets DJANGO_SETTINGS_MODULE explicitly.
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")
    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
