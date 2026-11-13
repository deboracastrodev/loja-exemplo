"""A API de ponta a ponta: servidor de verdade em porta livre, banco sqlite temporário."""

import json
import sqlite3
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from loja.api import criar_servidor
from loja.migrar import migrar, semear
from loja.repositorio import Loja


class ApiDaLoja(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.banco = str(Path(self._tmp.name) / "loja.db")
        migrar(self.banco)
        semear(self.banco)
        self.servidor = criar_servidor(Loja(self.banco), "127.0.0.1", 0)
        self.base = "http://127.0.0.1:%d" % self.servidor.server_address[1]
        self._thread = threading.Thread(target=self.servidor.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
        self._thread.start()

    def tearDown(self):
        self.servidor.shutdown()
        self.servidor.server_close()
        self._tmp.cleanup()

    def chamar(self, metodo, caminho, corpo=None, cru=None):
        dados = cru if cru is not None else (json.dumps(corpo).encode() if corpo is not None else None)
        req = urllib.request.Request(self.base + caminho, data=dados, method=metodo)
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def estoque(self, sku):
        con = sqlite3.connect(self.banco)
        try:
            return con.execute("SELECT estoque FROM produtos WHERE sku = ?", (sku,)).fetchone()[0]
        finally:
            con.close()

    def carrinho_com(self, *itens):
        _, carrinho = self.chamar("POST", "/carrinhos")
        for sku, quantidade in itens:
            status, _ = self.chamar("POST", f"/carrinhos/{carrinho['id']}/itens",
                                    {"sku": sku, "quantidade": quantidade})
            self.assertEqual(status, 200)
        return carrinho["id"]

    # ── catálogo e saúde ──────────────────────────────────────────────────

    def test_saude(self):
        self.assertEqual(self.chamar("GET", "/saude"), (200, {"status": "ok"}))

    def test_catalogo_lista_produto_sem_estoque_como_indisponivel(self):
        status, produtos = self.chamar("GET", "/produtos")
        self.assertEqual(status, 200)
        garrafa = next(p for p in produtos if p["sku"] == "GAR-001")
        self.assertFalse(garrafa["disponivel"])

    def test_produto_inativo_some_do_catalogo_e_nao_entra_no_carrinho(self):
        con = sqlite3.connect(self.banco)
        with con:
            con.execute("UPDATE produtos SET ativo = 0 WHERE sku = 'CAN-001'")
        con.close()
        _, produtos = self.chamar("GET", "/produtos")
        self.assertNotIn("CAN-001", [p["sku"] for p in produtos])
        _, carrinho = self.chamar("POST", "/carrinhos")
        status, erro = self.chamar("POST", f"/carrinhos/{carrinho['id']}/itens", {"sku": "CAN-001", "quantidade": 1})
        self.assertEqual((status, erro["erro"]), (404, "produto_inexistente"))

    # ── carrinho ──────────────────────────────────────────────────────────

    def test_carrinho_soma_itens_e_cobra_frete_abaixo_do_limite(self):
        cid = self.carrinho_com(("CAN-001", 2), ("CAM-001", 1))
        _, carrinho = self.chamar("GET", f"/carrinhos/{cid}")
        self.assertEqual(
            (carrinho["subtotal_centavos"], carrinho["frete_centavos"], carrinho["total_centavos"]),
            (17170, 1500, 18670),
        )

    def test_frete_gratis_a_partir_do_limite(self):
        cid = self.carrinho_com(("MOC-001", 1), ("CAN-001", 1))
        _, carrinho = self.chamar("GET", f"/carrinhos/{cid}")
        self.assertEqual(carrinho["frete_centavos"], 0)

    def test_adicionar_o_mesmo_sku_acumula_ate_o_limite(self):
        cid = self.carrinho_com(("CAN-001", 6), ("CAN-001", 4))
        _, carrinho = self.chamar("GET", f"/carrinhos/{cid}")
        self.assertEqual(carrinho["itens"][0]["quantidade"], 10)
        status, erro = self.chamar("POST", f"/carrinhos/{cid}/itens", {"sku": "CAN-001", "quantidade": 1})
        self.assertEqual((status, erro["erro"]), (409, "limite_por_item"))

    def test_nao_adiciona_acima_do_estoque(self):
        _, carrinho = self.chamar("POST", "/carrinhos")
        status, erro = self.chamar("POST", f"/carrinhos/{carrinho['id']}/itens", {"sku": "MOC-001", "quantidade": 6})
        self.assertEqual((status, erro["erro"]), (409, "estoque_insuficiente"))

    def test_entrada_invalida_vira_422(self):
        _, carrinho = self.chamar("POST", "/carrinhos")
        caminho = f"/carrinhos/{carrinho['id']}/itens"
        self.assertEqual(self.chamar("POST", caminho, {"sku": "CAN-001", "quantidade": 0})[0], 422)
        self.assertEqual(self.chamar("POST", caminho, {"quantidade": 1})[0], 422)
        self.assertEqual(self.chamar("POST", caminho, cru=b"{nao e json")[0], 422)

    def test_remover_item(self):
        cid = self.carrinho_com(("CAN-001", 1), ("CAM-001", 1))
        status, carrinho = self.chamar("DELETE", f"/carrinhos/{cid}/itens/CAN-001")
        self.assertEqual((status, [i["sku"] for i in carrinho["itens"]]), (200, ["CAM-001"]))
        self.assertEqual(self.chamar("DELETE", f"/carrinhos/{cid}/itens/CAN-001")[0], 404)

    # ── checkout e pedido ─────────────────────────────────────────────────

    def test_checkout_baixa_estoque_e_fecha_o_carrinho(self):
        cid = self.carrinho_com(("CAN-001", 3))
        status, pedido = self.chamar("POST", f"/carrinhos/{cid}/checkout")
        self.assertEqual((status, pedido["estado"]), (201, "confirmado"))
        self.assertEqual(self.estoque("CAN-001"), 27)
        status, erro = self.chamar("POST", f"/carrinhos/{cid}/itens", {"sku": "CAM-001", "quantidade": 1})
        self.assertEqual((status, erro["erro"]), (409, "carrinho_fechado"))
        self.assertEqual(self.chamar("POST", f"/carrinhos/{cid}/checkout")[1]["erro"], "carrinho_fechado")

    def test_checkout_de_carrinho_vazio_e_recusado(self):
        _, carrinho = self.chamar("POST", "/carrinhos")
        status, erro = self.chamar("POST", f"/carrinhos/{carrinho['id']}/checkout")
        self.assertEqual((status, erro["erro"]), (409, "carrinho_vazio"))

    def test_checkout_sem_estoque_nao_baixa_nada(self):
        cid = self.carrinho_com(("CAN-001", 2), ("MOC-001", 5))
        con = sqlite3.connect(self.banco)
        with con:
            con.execute("UPDATE produtos SET estoque = 4 WHERE sku = 'MOC-001'")
        con.close()
        status, erro = self.chamar("POST", f"/carrinhos/{cid}/checkout")
        self.assertEqual((status, erro["erro"]), (409, "estoque_insuficiente"))
        self.assertEqual((self.estoque("CAN-001"), self.estoque("MOC-001")), (30, 4))
        self.assertFalse(self.chamar("GET", f"/carrinhos/{cid}")[1]["fechado"])

    def test_preco_do_pedido_e_o_do_checkout(self):
        cid = self.carrinho_com(("CAN-001", 1))
        _, pedido = self.chamar("POST", f"/carrinhos/{cid}/checkout")
        con = sqlite3.connect(self.banco)
        with con:
            con.execute("UPDATE produtos SET preco_centavos = 9999 WHERE sku = 'CAN-001'")
        con.close()
        _, depois = self.chamar("GET", f"/pedidos/{pedido['id']}")
        self.assertEqual(depois["itens"][0]["preco_centavos"], 4590)

    def test_ultima_unidade_disputada_vende_uma_vez(self):
        con = sqlite3.connect(self.banco)
        with con:
            con.execute("UPDATE produtos SET estoque = 1 WHERE sku = 'MOC-001'")
        con.close()
        carrinhos = [self.carrinho_com(("MOC-001", 1)) for _ in range(5)]
        resultados = []
        threads = [threading.Thread(target=lambda c=c: resultados.append(
            self.chamar("POST", f"/carrinhos/{c}/checkout")[0])) for c in carrinhos]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(sorted(resultados), [201, 409, 409, 409, 409])
        self.assertEqual(self.estoque("MOC-001"), 0)

    def test_cancelar_devolve_estoque_e_enviado_nao_cancela(self):
        cid = self.carrinho_com(("CAN-001", 3))
        _, pedido = self.chamar("POST", f"/carrinhos/{cid}/checkout")
        status, cancelado = self.chamar("POST", f"/pedidos/{pedido['id']}/cancelar")
        self.assertEqual((status, cancelado["estado"]), (200, "cancelado"))
        self.assertEqual(self.estoque("CAN-001"), 30)

        cid = self.carrinho_com(("CAN-001", 1))
        _, pedido = self.chamar("POST", f"/carrinhos/{cid}/checkout")
        self.assertEqual(self.chamar("POST", f"/pedidos/{pedido['id']}/enviar")[1]["estado"], "enviado")
        status, erro = self.chamar("POST", f"/pedidos/{pedido['id']}/cancelar")
        self.assertEqual((status, erro["erro"]), (409, "transicao_invalida"))
        self.assertEqual(self.estoque("CAN-001"), 29)

    # ── protocolo ─────────────────────────────────────────────────────────

    def test_rota_inexistente_e_metodo_errado(self):
        self.assertEqual(self.chamar("GET", "/nada")[0], 404)
        self.assertEqual(self.chamar("DELETE", "/produtos")[0], 405)
        self.assertEqual(self.chamar("GET", "/pedidos/999")[1]["erro"], "pedido_inexistente")


class Migracao(unittest.TestCase):
    def test_migrar_e_semear_de_novo_nao_muda_nada(self):
        with tempfile.TemporaryDirectory() as tmp:
            banco = str(Path(tmp) / "loja.db")
            self.assertEqual(migrar(banco), 1)
            self.assertEqual(semear(banco), 4)
            self.assertEqual(migrar(banco), 1)
            self.assertEqual(semear(banco), 0)


if __name__ == "__main__":
    unittest.main()
