from pathlib import Path
import importlib
import os
from typing import Optional

# Delay importing config until tests reload it to pick up .env changes
import bot.config as config


def _project_root() -> Path:
    # bot package is located in <project_root>/bot
    return Path(__file__).resolve().parent.parent


def _write_env_file(content: str) -> Path:
    p = _project_root() / ".env"
    p.write_text(content)
    return p


def _backup_and_remove_env() -> Optional[bytes]:
    p = _project_root() / ".env"
    if p.exists():
        data = p.read_bytes()
        p.unlink()
        return data
    return None


def test_env_file_loaded_when_env_not_set(monkeypatch):
    # Ensure BOT_TOKEN is not in environment
    original = os.environ.pop('BOT_TOKEN', None)

    # Backup any existing .env and remove it
    backup = _backup_and_remove_env()

    env_path = None
    try:
        # Create a temporary .env in project root
        env_path = _write_env_file('BOT_TOKEN=from_env_file\n')

        # Reload config so it picks up the .env file
        importlib.reload(config)

        assert config.bot_token == 'from_env_file'
    finally:
        # Clean up: remove the created .env
        try:
            if env_path is not None and env_path.exists():
                env_path.unlink()
        except Exception:
            pass
        # Restore previous .env if present
        if backup is not None:
            (_project_root() / '.env').write_bytes(backup)
        # Restore original environment variable
        if original is not None:
            os.environ['BOT_TOKEN'] = original
        else:
            os.environ.pop('BOT_TOKEN', None)
        # Reload config to restore original state
        importlib.reload(config)


def test_env_file_does_not_override_existing_env(monkeypatch):
    # Backup any existing .env and remove it
    backup = _backup_and_remove_env()

    # Ensure BOT_TOKEN is set in OS environment
    original = os.environ.get('BOT_TOKEN')
    os.environ['BOT_TOKEN'] = 'from_os_env'

    try:
        # Create a .env with a different value
        env_path = _write_env_file('BOT_TOKEN=from_env_file\n')

        # Reload config so it picks up .env but should not override real env
        importlib.reload(config)

        assert config.bot_token == 'from_os_env'
    finally:
        # Clean up
        try:
            if (_project_root() / '.env').exists():
                (_project_root() / '.env').unlink()
        except Exception:
            pass
        if backup is not None:
            (_project_root() / '.env').write_bytes(backup)
        # Restore original BOT_TOKEN
        if original is None:
            os.environ.pop('BOT_TOKEN', None)
        else:
            os.environ['BOT_TOKEN'] = original
        importlib.reload(config)
