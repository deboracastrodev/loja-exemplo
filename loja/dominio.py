"""Regras de negócio da loja, puras: nada aqui toca banco nem HTTP.

Dinheiro é sempre inteiro em centavos. Quem precisa de uma regra importa daqui;
o repositório e a API não repetem limite nem transição.
"""

from __future__ import annotations

from typing import Iterable, Mapping

FRETE_CENTAVOS = 1500
FRETE_GRATIS_A_PARTIR_DE_CENTAVOS = 20000
MAX_UNIDADES_POR_ITEM = 10

CONFIRMADO = "confirmado"
ENVIADO = "enviado"
CANCELADO = "cancelado"

TRANSICOES = {
    CONFIRMADO: frozenset({ENVIADO, CANCELADO}),
    ENVIADO: frozenset(),
    CANCELADO: frozenset(),
}


class ErroDeNegocio(Exception):
    """Pedido válido na forma que a regra recusa. Vira 409 na API."""

    status = 409

    def __init__(self, codigo: str, mensagem: str):
        super().__init__(mensagem)
        self.codigo = codigo
        self.mensagem = mensagem


class EntradaInvalida(ErroDeNegocio):
    """Entrada fora da forma (tipo, faixa). Vira 422 na API."""

    status = 422


class NaoEncontrado(ErroDeNegocio):
    """O recurso pedido não existe. Vira 404 na API."""

    status = 404


def frete(subtotal_centavos: int) -> int:
    """Frete fixo; grátis a partir do limite; carrinho vazio não paga frete."""
    if subtotal_centavos <= 0 or subtotal_centavos >= FRETE_GRATIS_A_PARTIR_DE_CENTAVOS:
        return 0
    return FRETE_CENTAVOS


def totais(itens: Iterable[Mapping[str, int]]) -> dict:
    """Subtotal, frete e total de itens com `preco_centavos` e `quantidade`."""
    subtotal = sum(i["preco_centavos"] * i["quantidade"] for i in itens)
    valor_frete = frete(subtotal)
    return {
        "subtotal_centavos": subtotal,
        "frete_centavos": valor_frete,
        "total_centavos": subtotal + valor_frete,
    }


def validar_quantidade(quantidade: object) -> int:
    """Quantidade pedida: inteiro de 1 ao máximo por item."""
    if isinstance(quantidade, bool) or not isinstance(quantidade, int):
        raise EntradaInvalida("quantidade_invalida", "quantidade precisa ser um inteiro")
    if not 1 <= quantidade <= MAX_UNIDADES_POR_ITEM:
        raise EntradaInvalida(
            "quantidade_invalida",
            f"quantidade precisa estar entre 1 e {MAX_UNIDADES_POR_ITEM}",
        )
    return quantidade


def conferir_inclusao(ja_no_carrinho: int, pedida: int, estoque: int) -> int:
    """Quantidade final do item no carrinho, ou o motivo da recusa."""
    final = ja_no_carrinho + pedida
    if final > MAX_UNIDADES_POR_ITEM:
        raise ErroDeNegocio(
            "limite_por_item",
            f"no máximo {MAX_UNIDADES_POR_ITEM} unidades do mesmo produto por carrinho",
        )
    if final > estoque:
        raise ErroDeNegocio("estoque_insuficiente", f"há {estoque} unidades em estoque")
    return final


def transicionar(atual: str, novo: str) -> str:
    """Novo estado do pedido, se a transição é permitida."""
    if novo not in TRANSICOES.get(atual, frozenset()):
        raise ErroDeNegocio("transicao_invalida", f"pedido {atual} não pode ir para {novo}")
    return novo
