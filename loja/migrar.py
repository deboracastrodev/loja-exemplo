"""Schema do banco, versionado por `PRAGMA user_version`, e o catálogo inicial.

Cada migração entra no fim de MIGRACOES e nunca se edita depois de publicada.
Rodar de novo é seguro: só aplica as que faltam, e o catálogo inicial só entra
em banco sem produto.

  python -m loja.migrar            aplica as migrações e semeia o catálogo
  python -m loja.migrar --sem-semear
"""

from __future__ import annotations

import argparse
import sqlite3

from loja.config import caminho_do_banco

MIGRACOES = [
    """
    CREATE TABLE produtos (
        sku            TEXT PRIMARY KEY,
        nome           TEXT NOT NULL,
        preco_centavos INTEGER NOT NULL CHECK (preco_centavos > 0),
        estoque        INTEGER NOT NULL CHECK (estoque >= 0),
        ativo          INTEGER NOT NULL DEFAULT 1 CHECK (ativo IN (0, 1))
    );
    CREATE TABLE carrinhos (
        id      INTEGER PRIMARY KEY AUTOINCREMENT,
        fechado INTEGER NOT NULL DEFAULT 0 CHECK (fechado IN (0, 1))
    );
    CREATE TABLE itens_carrinho (
        carrinho_id INTEGER NOT NULL REFERENCES carrinhos (id),
        sku         TEXT NOT NULL REFERENCES produtos (sku),
        quantidade  INTEGER NOT NULL CHECK (quantidade > 0),
        PRIMARY KEY (carrinho_id, sku)
    );
    CREATE TABLE pedidos (
        id                INTEGER PRIMARY KEY AUTOINCREMENT,
        carrinho_id       INTEGER NOT NULL UNIQUE REFERENCES carrinhos (id),
        estado            TEXT NOT NULL,
        subtotal_centavos INTEGER NOT NULL,
        frete_centavos    INTEGER NOT NULL,
        total_centavos    INTEGER NOT NULL
    );
    CREATE TABLE itens_pedido (
        pedido_id      INTEGER NOT NULL REFERENCES pedidos (id),
        sku            TEXT NOT NULL REFERENCES produtos (sku),
        nome           TEXT NOT NULL,
        preco_centavos INTEGER NOT NULL,
        quantidade     INTEGER NOT NULL CHECK (quantidade > 0),
        PRIMARY KEY (pedido_id, sku)
    );
    """,
]

CATALOGO_INICIAL = [
    ("CAN-001", "Caneca de cerâmica", 4590, 30),
    ("CAM-001", "Camiseta básica", 7990, 20),
    ("MOC-001", "Mochila de lona", 18990, 5),
    ("GAR-001", "Garrafa térmica", 12900, 0),
]


def migrar(caminho: str) -> int:
    """Aplica as migrações que faltam; devolve a versão final do schema."""
    con = sqlite3.connect(caminho, isolation_level=None)
    try:
        versao = con.execute("PRAGMA user_version").fetchone()[0]
        for numero, script in enumerate(MIGRACOES[versao:], start=versao + 1):
            # executescript faz COMMIT antes de rodar; a transação vai dentro do script,
            # junto com a versão, para migração e versão nunca divergirem.
            con.executescript(f"BEGIN;\n{script}\nPRAGMA user_version = {numero};\nCOMMIT;")
        return con.execute("PRAGMA user_version").fetchone()[0]
    finally:
        con.close()


def semear(caminho: str) -> int:
    """Catálogo inicial em banco sem produto; devolve quantos entraram."""
    con = sqlite3.connect(caminho)
    try:
        with con:
            if con.execute("SELECT 1 FROM produtos LIMIT 1").fetchone():
                return 0
            con.executemany(
                "INSERT INTO produtos (sku, nome, preco_centavos, estoque) VALUES (?, ?, ?, ?)",
                CATALOGO_INICIAL,
            )
        return len(CATALOGO_INICIAL)
    finally:
        con.close()


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--banco", default=None, help="caminho do sqlite; padrão: LOJA_BANCO")
    p.add_argument("--sem-semear", action="store_true", help="não insere o catálogo inicial")
    a = p.parse_args(argv)
    caminho = a.banco or caminho_do_banco()
    versao = migrar(caminho)
    semeados = 0 if a.sem_semear else semear(caminho)
    print(f"schema na versão {versao}; {semeados} produto(s) semeado(s) em {caminho}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
