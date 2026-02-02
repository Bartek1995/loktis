#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys
from pathlib import Path

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    local_env = Path(__file__).resolve().parent / '.env'
    root_env = Path(__file__).resolve().parent.parent / '.env'
    if local_env.exists():
        load_dotenv(local_env)
    elif root_env.exists():
        load_dotenv(root_env)
except ImportError:
    # Fallback: Manual parsing if python-dotenv is missing or failing
    def load_env_manual(path):
        if not path.exists(): return
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line: continue
                k, v = line.split('=', 1)
                os.environ.setdefault(k.strip(), v.strip().strip("'").strip('"'))

    local_env = Path(__file__).resolve().parent / '.env'
    root_env = Path(__file__).resolve().parent.parent / '.env'
    
    if local_env.exists():
        load_env_manual(local_env)
    elif root_env.exists():
        load_env_manual(root_env)


def main():
    """Run administrative tasks."""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'project_config.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
