"""API HTTP da loja: JSON de entrada e de saída, uma rota por operação do repositório.

Erro de regra sai como `{"erro": <codigo>, "mensagem": <texto>}` com o status da
classe do erro (`loja.dominio`). Erro inesperado sai como 500 sem detalhe; o
detalhe vai para o log do servidor.
"""

from __future__ import annotations

import json
import logging
import re
from urllib.parse import unquote
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable, Optional, Tuple

from loja.dominio import EntradaInvalida, ErroDeNegocio, NaoEncontrado
from loja.repositorio import Loja

LIMITE_DO_CORPO_BYTES = 16 * 1024

log = logging.getLogger("loja.api")

Resposta = Tuple[int, object]
Acao = Callable[[Loja, "re.Match[str]", dict], Resposta]


def _id(m: "re.Match[str]") -> int:
    return int(m["id"])


def _sku(corpo: dict) -> str:
    sku = corpo.get("sku")
    if not isinstance(sku, str) or not sku.strip():
        raise EntradaInvalida("sku_invalido", "sku precisa ser um texto não vazio")
    return sku


ROTAS: list = [
    ("GET", r"/saude", lambda loja, m, c: (200, {"status": "ok"})),
    ("GET", r"/produtos", lambda loja, m, c: (200, loja.produtos())),
    ("POST", r"/carrinhos", lambda loja, m, c: (201, loja.criar_carrinho())),
    ("GET", r"/carrinhos/(?P<id>\d+)", lambda loja, m, c: (200, loja.carrinho(_id(m)))),
    ("POST", r"/carrinhos/(?P<id>\d+)/itens",
     lambda loja, m, c: (200, loja.adicionar_item(_id(m), _sku(c), c.get("quantidade")))),
    ("DELETE", r"/carrinhos/(?P<id>\d+)/itens/(?P<sku>[^/]+)",
     lambda loja, m, c: (200, loja.remover_item(_id(m), unquote(m["sku"])))),
    ("POST", r"/carrinhos/(?P<id>\d+)/checkout", lambda loja, m, c: (201, loja.finalizar(_id(m)))),
    ("GET", r"/pedidos/(?P<id>\d+)", lambda loja, m, c: (200, loja.pedido(_id(m)))),
    ("POST", r"/pedidos/(?P<id>\d+)/cancelar", lambda loja, m, c: (200, loja.cancelar(_id(m)))),
    ("POST", r"/pedidos/(?P<id>\d+)/enviar", lambda loja, m, c: (200, loja.enviar(_id(m)))),
]
_COMPILADAS = [(metodo, re.compile(padrao + r"/?"), acao) for metodo, padrao, acao in ROTAS]


def resolver(metodo: str, caminho: str) -> Tuple[Optional[Acao], Optional["re.Match[str]"], bool]:
    """A ação da rota, o match e se o caminho existe com outro método (405)."""
    caminho_existe = False
    for metodo_da_rota, padrao, acao in _COMPILADAS:
        m = padrao.fullmatch(caminho)
        if not m:
            continue
        if metodo_da_rota == metodo:
            return acao, m, True
        caminho_existe = True
    return None, None, caminho_existe


class Manipulador(BaseHTTPRequestHandler):
    server_version = "loja-exemplo"
    loja: Loja  # atribuído por criar_servidor

    def do_GET(self):
        self._atender("GET")

    def do_POST(self):
        self._atender("POST")

    def do_DELETE(self):
        self._atender("DELETE")

    def _atender(self, metodo: str) -> None:
        caminho = self.path.split("?", 1)[0]
        acao, m, caminho_existe = resolver(metodo, caminho)
        try:
            if acao is None:
                if caminho_existe:
                    raise _ErroHttp(HTTPStatus.METHOD_NOT_ALLOWED, "metodo_nao_permitido", "método não permitido")
                raise NaoEncontrado("rota_inexistente", f"{caminho} não existe")
            status, corpo = acao(self.loja, m, self._corpo())
        except ErroDeNegocio as e:
            status, corpo = e.status, {"erro": e.codigo, "mensagem": e.mensagem}
        except Exception:
            log.exception("erro inesperado em %s %s", metodo, caminho)
            status, corpo = 500, {"erro": "erro_interno", "mensagem": "erro interno"}
        self._responder(status, corpo)

    def _corpo(self) -> dict:
        tamanho = int(self.headers.get("Content-Length") or 0)
        if tamanho > LIMITE_DO_CORPO_BYTES:
            raise _ErroHttp(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "corpo_grande", "corpo acima do limite")
        if not tamanho:
            return {}
        try:
            corpo = json.loads(self.rfile.read(tamanho))
        except (ValueError, UnicodeDecodeError):
            raise EntradaInvalida("json_invalido", "corpo não é JSON válido") from None
        if not isinstance(corpo, dict):
            raise EntradaInvalida("json_invalido", "corpo precisa ser um objeto JSON")
        return corpo

    def _responder(self, status: int, corpo: object) -> None:
        dados = json.dumps(corpo, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(dados)))
        self.end_headers()
        self.wfile.write(dados)

    def log_message(self, formato: str, *args) -> None:
        log.info("%s %s", self.address_string(), formato % args)


class _ErroHttp(ErroDeNegocio):
    """Erro de protocolo (405, 413), fora das regras de negócio."""

    def __init__(self, status: int, codigo: str, mensagem: str):
        super().__init__(codigo, mensagem)
        self.status = int(status)


def criar_servidor(loja: Loja, host: str, porta: int) -> ThreadingHTTPServer:
    manipulador = type("ManipuladorDaLoja", (Manipulador,), {"loja": loja})
    return ThreadingHTTPServer((host, porta), manipulador)
