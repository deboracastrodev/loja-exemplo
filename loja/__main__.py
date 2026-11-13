"""`python -m loja`: sobe a API em LOJA_HOST:LOJA_PORTA sobre o banco LOJA_BANCO."""

from __future__ import annotations

import logging
import signal

from loja import config
from loja.api import criar_servidor
from loja.repositorio import Loja


def _parar(_sinal, _quadro) -> None:
    # SIGTERM do `docker compose down` encerra como o Ctrl+C, sem esperar o kill.
    raise KeyboardInterrupt


def main() -> int:
    signal.signal(signal.SIGTERM, _parar)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    servidor = criar_servidor(Loja(config.caminho_do_banco()), config.host(), config.porta())
    logging.getLogger("loja").info("ouvindo em %s:%s", *servidor.server_address[:2])
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        servidor.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
