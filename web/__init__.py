import os
import django

os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    "web.settings"
)
os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"
django.setup()
