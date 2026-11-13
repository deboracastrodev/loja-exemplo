# AGENTS.md

> Lei deste repo para quem escreve código nele, pessoa ou agente.

## O que é

API HTTP de uma loja: catálogo, carrinho e pedido. Python 3.9 ou mais novo, só biblioteca padrão, banco sqlite.

## Regras

1. **Sem dependência de terceiros.** Nada de `pip install`. Se a biblioteca padrão não resolve, a mudança para e a decisão sobe.
2. **Dinheiro é inteiro em centavos**, com sufixo `_centavos` no nome. Nunca `float`, nem na resposta da API.
3. **Regra de negócio mora em `loja/dominio.py`**, pura: sem banco e sem HTTP. Limite, transição de estado e cálculo não se repetem em `repositorio.py` nem em `api.py`; importam de lá.
4. **Escrita no banco roda em `Loja._conexao(escrita=True)`**, uma transação por operação. Operação que mexe em estoque baixa com `UPDATE ... WHERE estoque >= ?` e confere o `rowcount`; ler e depois gravar perde a corrida.
5. **Schema muda só por migração nova** no fim de `MIGRACOES` em `loja/migrar.py`. Migração publicada nunca se edita.
6. **Erro de regra é exceção de `loja.dominio`** (`ErroDeNegocio` 409, `EntradaInvalida` 422, `NaoEncontrado` 404) com um `codigo` estável em snake_case. O `codigo` é contrato com quem chama a API: renomear é quebra.
7. **Todo comportamento novo nasce com teste**: regra pura em `tests/test_dominio.py`, rota em `tests/test_api.py` contra o servidor de verdade.

## Comandos

```bash
python3 -m unittest discover -s tests          # testes
python3 -m compileall -q loja tests            # sintaxe
LOJA_BANCO=loja.db python3 -m loja.migrar      # schema e catálogo inicial
LOJA_BANCO=loja.db python3 -m loja             # API em 127.0.0.1:8000
docker compose up -d --build && docker compose exec api python -m loja.migrar
```

## Commits e PR

Mensagem no imperativo, em português, com prefixo (`feat:`, `fix:`, `test:`, `docs:`, `refactor:`). Um PR por mudança de comportamento; a descrição diz qual regra mudou.
