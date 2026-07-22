"""
ASGI config for the IndusMind AI project.

Exposes the ASGI callable as a module-level variable named ``application``.
Provided for forward compatibility with future async features (e.g.
streaming AI responses over WebSockets).
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

application = get_asgi_application()
