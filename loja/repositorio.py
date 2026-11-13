"""Persistência da loja em sqlite. As regras vêm de `loja.dominio`; aqui só se aplicam.

Cada operação abre a própria conexão: o servidor atende em threads e conexão
sqlite não se compartilha entre elas. Escrita roda em `BEGIN IMMEDIATE`, que
trava o banco para escrita desde o início e serializa dois checkouts disputando
a mesma unidade.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Iterator, Optional

from loja import dominio
from loja.dominio import ErroDeNegocio, NaoEncontrado


class Loja:
    def __init__(self, caminho: str):
        self.caminho = caminho

    @contextmanager
    def _conexao(self, escrita: bool = False) -> Iterator[sqlite3.Connection]:
        con = sqlite3.connect(self.caminho, timeout=5, isolation_level=None)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys = ON")
        try:
            if escrita:
                con.execute("BEGIN IMMEDIATE")
            yield con
            if escrita:
                con.execute("COMMIT")
        except BaseException:
            if con.in_transaction:
                con.execute("ROLLBACK")
            raise
        finally:
            con.close()

    # ── catálogo ──────────────────────────────────────────────────────────

    def produtos(self) -> list:
        with self._conexao() as con:
            linhas = con.execute(
                "SELECT sku, nome, preco_centavos, estoque FROM produtos WHERE ativo = 1 ORDER BY sku"
            ).fetchall()
        return [_produto(linha) for linha in linhas]

    # ── carrinho ──────────────────────────────────────────────────────────

    def criar_carrinho(self) -> dict:
        with self._conexao(escrita=True) as con:
            carrinho_id = con.execute("INSERT INTO carrinhos DEFAULT VALUES").lastrowid
            return _carrinho(con, carrinho_id)

    def carrinho(self, carrinho_id: int) -> dict:
        with self._conexao() as con:
            return _carrinho(con, carrinho_id)

    def adicionar_item(self, carrinho_id: int, sku: str, quantidade: object) -> dict:
        pedida = dominio.validar_quantidade(quantidade)
        with self._conexao(escrita=True) as con:
            _carrinho_aberto(con, carrinho_id)
            produto = _produto_ativo(con, sku)
            linha = con.execute(
                "SELECT quantidade FROM itens_carrinho WHERE carrinho_id = ? AND sku = ?",
                (carrinho_id, sku),
            ).fetchone()
            final = dominio.conferir_inclusao(linha[0] if linha else 0, pedida, produto["estoque"])
            con.execute(
                "INSERT INTO itens_carrinho (carrinho_id, sku, quantidade) VALUES (?, ?, ?) "
                "ON CONFLICT (carrinho_id, sku) DO UPDATE SET quantidade = excluded.quantidade",
                (carrinho_id, sku, final),
            )
            return _carrinho(con, carrinho_id)

    def remover_item(self, carrinho_id: int, sku: str) -> dict:
        with self._conexao(escrita=True) as con:
            _carrinho_aberto(con, carrinho_id)
            removidos = con.execute(
                "DELETE FROM itens_carrinho WHERE carrinho_id = ? AND sku = ?", (carrinho_id, sku)
            ).rowcount
            if not removidos:
                raise NaoEncontrado("item_inexistente", f"o carrinho não tem {sku}")
            return _carrinho(con, carrinho_id)

    # ── pedido ────────────────────────────────────────────────────────────

    def finalizar(self, carrinho_id: int) -> dict:
        """Checkout: baixa o estoque de todos os itens ou de nenhum, e fecha o carrinho."""
        with self._conexao(escrita=True) as con:
            _carrinho_aberto(con, carrinho_id)
            itens = _itens_do_carrinho(con, carrinho_id)
            if not itens:
                raise ErroDeNegocio("carrinho_vazio", "carrinho sem itens não vira pedido")
            for item in itens:
                if not item["ativo"]:
                    raise ErroDeNegocio("produto_indisponivel", f"{item['sku']} saiu do catálogo")
                baixou = con.execute(
                    "UPDATE produtos SET estoque = estoque - ? WHERE sku = ? AND estoque >= ?",
                    (item["quantidade"], item["sku"], item["quantidade"]),
                ).rowcount
                if not baixou:
                    raise ErroDeNegocio(
                        "estoque_insuficiente", f"{item['sku']} não tem {item['quantidade']} em estoque"
                    )
            valores = dominio.totais(itens)
            pedido_id = con.execute(
                "INSERT INTO pedidos (carrinho_id, estado, subtotal_centavos, frete_centavos, total_centavos) "
                "VALUES (?, ?, ?, ?, ?)",
                (carrinho_id, dominio.CONFIRMADO, valores["subtotal_centavos"],
                 valores["frete_centavos"], valores["total_centavos"]),
            ).lastrowid
            con.executemany(
                "INSERT INTO itens_pedido (pedido_id, sku, nome, preco_centavos, quantidade) VALUES (?, ?, ?, ?, ?)",
                [(pedido_id, i["sku"], i["nome"], i["preco_centavos"], i["quantidade"]) for i in itens],
            )
            con.execute("UPDATE carrinhos SET fechado = 1 WHERE id = ?", (carrinho_id,))
            return _pedido(con, pedido_id)

    def pedido(self, pedido_id: int) -> dict:
        with self._conexao() as con:
            return _pedido(con, pedido_id)

    def cancelar(self, pedido_id: int) -> dict:
        """Cancela e devolve ao estoque o que o pedido tinha baixado."""
        with self._conexao(escrita=True) as con:
            atual = _pedido(con, pedido_id)
            novo = dominio.transicionar(atual["estado"], dominio.CANCELADO)
            con.executemany(
                "UPDATE produtos SET estoque = estoque + ? WHERE sku = ?",
                [(i["quantidade"], i["sku"]) for i in atual["itens"]],
            )
            con.execute("UPDATE pedidos SET estado = ? WHERE id = ?", (novo, pedido_id))
            return _pedido(con, pedido_id)

    def enviar(self, pedido_id: int) -> dict:
        with self._conexao(escrita=True) as con:
            atual = _pedido(con, pedido_id)
            novo = dominio.transicionar(atual["estado"], dominio.ENVIADO)
            con.execute("UPDATE pedidos SET estado = ? WHERE id = ?", (novo, pedido_id))
            return _pedido(con, pedido_id)


# ── leitura, dentro da conexão de quem chama ──────────────────────────────

def _produto(linha: sqlite3.Row) -> dict:
    return {
        "sku": linha["sku"],
        "nome": linha["nome"],
        "preco_centavos": linha["preco_centavos"],
        "estoque": linha["estoque"],
        "disponivel": linha["estoque"] > 0,
    }


def _produto_ativo(con: sqlite3.Connection, sku: object) -> sqlite3.Row:
    linha = con.execute(
        "SELECT sku, estoque FROM produtos WHERE sku = ? AND ativo = 1", (sku,)
    ).fetchone()
    if linha is None:
        raise NaoEncontrado("produto_inexistente", f"produto {sku} não está no catálogo")
    return linha


def _linha_do_carrinho(con: sqlite3.Connection, carrinho_id: int) -> sqlite3.Row:
    linha = con.execute("SELECT id, fechado FROM carrinhos WHERE id = ?", (carrinho_id,)).fetchone()
    if linha is None:
        raise NaoEncontrado("carrinho_inexistente", f"carrinho {carrinho_id} não existe")
    return linha


def _carrinho_aberto(con: sqlite3.Connection, carrinho_id: int) -> None:
    if _linha_do_carrinho(con, carrinho_id)["fechado"]:
        raise ErroDeNegocio("carrinho_fechado", "carrinho já virou pedido")


def _itens_do_carrinho(con: sqlite3.Connection, carrinho_id: int) -> list:
    linhas = con.execute(
        "SELECT p.sku, p.nome, p.preco_centavos, p.ativo, i.quantidade "
        "FROM itens_carrinho i JOIN produtos p ON p.sku = i.sku "
        "WHERE i.carrinho_id = ? ORDER BY p.sku",
        (carrinho_id,),
    ).fetchall()
    return [dict(linha) for linha in linhas]


def _carrinho(con: sqlite3.Connection, carrinho_id: int) -> dict:
    linha = _linha_do_carrinho(con, carrinho_id)
    itens = _itens_do_carrinho(con, carrinho_id)
    return {
        "id": linha["id"],
        "fechado": bool(linha["fechado"]),
        "itens": [_item(i) for i in itens],
        **dominio.totais(itens),
    }


def _pedido(con: sqlite3.Connection, pedido_id: int) -> dict:
    linha: Optional[sqlite3.Row] = con.execute(
        "SELECT id, carrinho_id, estado, subtotal_centavos, frete_centavos, total_centavos "
        "FROM pedidos WHERE id = ?",
        (pedido_id,),
    ).fetchone()
    if linha is None:
        raise NaoEncontrado("pedido_inexistente", f"pedido {pedido_id} não existe")
    itens = con.execute(
        "SELECT sku, nome, preco_centavos, quantidade FROM itens_pedido WHERE pedido_id = ? ORDER BY sku",
        (pedido_id,),
    ).fetchall()
    return {**dict(linha), "itens": [_item(dict(i)) for i in itens]}


def _item(i: dict) -> dict:
    return {
        "sku": i["sku"],
        "nome": i["nome"],
        "preco_centavos": i["preco_centavos"],
        "quantidade": i["quantidade"],
        "total_centavos": i["preco_centavos"] * i["quantidade"],
    }
