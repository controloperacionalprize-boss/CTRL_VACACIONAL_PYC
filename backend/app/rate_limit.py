"""Límite de tasa compartido para endpoints sensibles (login, device-code flow).

En memoria por proceso: suficiente para un solo worker de Uvicorn. Si en el
futuro se corre con varios workers/instancias, cambiar a un backend
compartido (Redis) vía `storage_uri`.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
