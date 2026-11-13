import unittest

from loja import dominio
from loja.dominio import EntradaInvalida, ErroDeNegocio


class Frete(unittest.TestCase):
    def test_carrinho_vazio_nao_paga_frete(self):
        self.assertEqual(dominio.frete(0), 0)

    def test_abaixo_do_limite_paga_frete_fixo(self):
        self.assertEqual(dominio.frete(19999), dominio.FRETE_CENTAVOS)

    def test_no_limite_o_frete_e_gratis(self):
        self.assertEqual(dominio.frete(dominio.FRETE_GRATIS_A_PARTIR_DE_CENTAVOS), 0)

    def test_totais_somam_itens_e_frete(self):
        itens = [{"preco_centavos": 4590, "quantidade": 2}, {"preco_centavos": 7990, "quantidade": 1}]
        self.assertEqual(
            dominio.totais(itens),
            {"subtotal_centavos": 17170, "frete_centavos": 1500, "total_centavos": 18670},
        )


class Quantidade(unittest.TestCase):
    def test_aceita_de_um_ao_maximo(self):
        self.assertEqual(dominio.validar_quantidade(1), 1)
        self.assertEqual(dominio.validar_quantidade(dominio.MAX_UNIDADES_POR_ITEM), 10)

    def test_recusa_fora_da_faixa_e_tipo_errado(self):
        for valor in (0, -1, 11, 1.5, "2", None, True):
            with self.subTest(valor=valor), self.assertRaises(EntradaInvalida):
                dominio.validar_quantidade(valor)

    def test_inclusao_acumula_e_respeita_limite_por_item(self):
        self.assertEqual(dominio.conferir_inclusao(4, 6, 30), 10)
        with self.assertRaises(ErroDeNegocio) as ctx:
            dominio.conferir_inclusao(5, 6, 30)
        self.assertEqual(ctx.exception.codigo, "limite_por_item")

    def test_inclusao_respeita_estoque(self):
        with self.assertRaises(ErroDeNegocio) as ctx:
            dominio.conferir_inclusao(0, 6, 5)
        self.assertEqual(ctx.exception.codigo, "estoque_insuficiente")


class Transicoes(unittest.TestCase):
    def test_confirmado_vai_para_enviado_ou_cancelado(self):
        self.assertEqual(dominio.transicionar("confirmado", "enviado"), "enviado")
        self.assertEqual(dominio.transicionar("confirmado", "cancelado"), "cancelado")

    def test_estados_finais_nao_saem(self):
        for atual in ("enviado", "cancelado"):
            for novo in ("confirmado", "enviado", "cancelado"):
                with self.subTest(atual=atual, novo=novo), self.assertRaises(ErroDeNegocio):
                    dominio.transicionar(atual, novo)


if __name__ == "__main__":
    unittest.main()
