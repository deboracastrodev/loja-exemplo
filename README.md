# loja-exemplo

API HTTP de uma loja pequena: catálogo, carrinho e pedido, em Python só com biblioteca padrão e sqlite.

> **Repo de exemplo.** Existe para servir de repo de entrega a um hub de especificação: ter código, testes, lei do repo e receita de ambiente de verdade, num tamanho que se lê inteiro. A loja, o catálogo e as regras são fictícios.

## Rodar

```bash
LOJA_BANCO=loja.db python3 -m loja.migrar
LOJA_BANCO=loja.db python3 -m loja
```

Ou em container:

```bash
docker compose up -d --build
docker compose exec api python -m loja.migrar
```

| Variável | Padrão | O quê |
| --- | --- | --- |
| `LOJA_BANCO` | `loja.db` | caminho do sqlite |
| `LOJA_HOST` | `127.0.0.1` (`0.0.0.0` no container) | interface onde a API ouve |
| `LOJA_PORTA` | `8000` | porta da API |

## Testes

```bash
python3 -m unittest discover -s tests
```

## API

JSON de entrada e de saída. Valores em centavos, inteiros. Erro sai como `{"erro": "<codigo>", "mensagem": "<texto>"}`.

| Método e rota | O quê | Sucesso |
| --- | --- | --- |
| `GET /saude` | prontidão | 200 |
| `GET /produtos` | catálogo ativo, com `disponivel` | 200 |
| `POST /carrinhos` | carrinho novo e vazio | 201 |
| `GET /carrinhos/{id}` | itens, subtotal, frete e total | 200 |
| `POST /carrinhos/{id}/itens` | `{"sku", "quantidade"}`; o mesmo SKU acumula | 200 |
| `DELETE /carrinhos/{id}/itens/{sku}` | tira o item | 200 |
| `POST /carrinhos/{id}/checkout` | vira pedido `confirmado` e baixa o estoque | 201 |
| `GET /pedidos/{id}` | pedido com os preços do checkout | 200 |
| `POST /pedidos/{id}/enviar` | `confirmado` → `enviado` | 200 |
| `POST /pedidos/{id}/cancelar` | `confirmado` → `cancelado`, devolve o estoque | 200 |

| Status | Quando |
| --- | --- |
| 404 | carrinho, pedido, produto, item ou rota que não existe |
| 405 | rota existe com outro método |
| 409 | a regra recusa: estoque, limite por item, carrinho fechado ou vazio, transição |
| 413 | corpo acima de 16 KiB |
| 422 | entrada fora da forma: JSON inválido, `sku` vazio, `quantidade` fora de 1 a 10 |

## Licença

MIT.
