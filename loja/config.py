"""Configuração lida do ambiente, num lugar só."""

from __future__ import annotations

import os


def caminho_do_banco() -> str:
    return os.environ.get("LOJA_BANCO", "loja.db")


def porta() -> int:
    return int(os.environ.get("LOJA_PORTA", "8000"))


def host() -> str:
    return os.environ.get("LOJA_HOST", "127.0.0.1")
