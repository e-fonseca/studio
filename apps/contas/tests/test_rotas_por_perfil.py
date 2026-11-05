"""Varredura automática de TODAS as rotas do sistema contra os perfis.

Por que este teste existe
-------------------------
Até a 1.24.0 esta conferência era feita à mão, uma vez, e está escrita em
`docs/verificacao-geral.md` como "59 rotas × 3 perfis". O problema de uma
conferência à mão é que ela envelhece: toda versão acrescenta tela, e ninguém
refaz a varredura inteira. A 1.24.0 sozinha acrescentou seis rotas.

Então a lista de rotas não se digita aqui: ela é lida do próprio Django, com
`get_resolver()`. Tela nova entra na varredura no dia em que nasce, sem ninguém
lembrar de nada. Se alguém criar uma tela de dinheiro e esquecer o
`permission_required`, este teste falha antes de o pacote sair.

O que ele garante
-----------------
1. O `Operador vendedor` só abre a tela de consulta de balcão. Qualquer outra
   rota tem que recusar: 403, redirecionar para o login ou 404. Nunca 200.
2. Nenhuma rota responde 500 para nenhum perfil. Erro de programação numa tela
   pouco visitada aparece aqui, não na mão do Edson.
3. Quem não entrou não abre nada além das rotas públicas.

O que ele NÃO cobre, de propósito
---------------------------------
- O `/studio/admin/` é o admin do próprio Django e exige `is_staff`, que
  nenhuma tela do sistema concede: só um superusuário criado na mão no
  servidor entra lá. Fica fora da varredura para o teste não virar um teste do
  Django.
- Rota com argumento é chamada com um número que não existe. O que se confere
  nela é a recusa, não o conteúdo: 404 para o vendedor é resposta correta,
  porque não vazou nada. O conteúdo de cada tela é conferido no teste da
  própria tela.
"""

from django.test import TestCase
from django.urls import get_resolver

from apps.contas.perfis import (ADMIN_ACESSOS, ADMINISTRACAO, ADMINISTRATIVO, COMPRAS, CONSULTA,
                                ESTOQUE, LIDER, VENDEDOR)
from apps.core.fabricas import SENHA_TESTE, confirmar_senha, usuario

# A única tela do vendedor, decidida pelo Edson em 07/10/2026: consulta de balcão,
# sem custo, sem margem e sem valor. As irmãs dela são o autocompletar da mesma tela.
DO_VENDEDOR = {
    "/studio/importacao/consulta/",
    "/studio/importacao/consulta/sugestoes/",
}

# Rotas que qualquer pessoa logada abre, em qualquer perfil, porque não mostram
# número nenhum da loja: a tela de entrada, a saída, o manifesto do aplicativo e o
# certificado (todo mundo precisa instalar para a câmera funcionar no celular).
#
# `/studio/versoes/` NÃO está nesta lista, e isso foi descoberto aqui: até a
# 1.24.0 ela pedia só login, e o histórico de mudanças cita os números que cada
# versão consertou — faturamento, lucro bruto, margem, o que está parado na
# prateleira. O vendedor abria tudo isso digitando o endereço. Agora ela pede
# `importacao.ver_painel`, como toda tela de dinheiro.
DE_TODOS = {
    "/",
    "/studio/",
    "/studio/entrar/",
    "/studio/sair/",
    "/studio/saude/",
    "/studio/manifesto.webmanifest",
    "/studio/operario.js",
    "/studio/certificado/",
    "/studio/certificado/autoridade.crt",
    # Trocar a própria senha (1.42.0): só o formulário, sem número da loja.
    "/studio/senha/",
    # Esqueci a minha senha (1.43.0): é para quem ainda NÃO entrou, então abre sem login.
    # Não mostra número da loja e não diz se a conta existe (apps/contas/recuperacao.py).
    "/studio/senha/esqueci/",
    "/studio/senha/esqueci/codigo/",
}

FORA_DA_VARREDURA = "/studio/admin/"

# A área de acessos (1.44.0): o que o Administrador de acessos abre. Nenhuma dessas telas
# mostra número da loja; é o "acesso financeiro concedido separadamente" do prompt de
# controle de acesso (02/11/2026).
DA_AREA_DE_ACESSOS = "/studio/usuarios/"


def _rotas():
    """Toda rota registrada no sistema, lida do próprio Django."""

    def andar(resolver, prefixo=""):
        for padrao in resolver.url_patterns:
            if hasattr(padrao, "url_patterns"):
                yield from andar(padrao, prefixo + str(padrao.pattern))
            else:
                yield prefixo + str(padrao.pattern)

    for caminho in andar(get_resolver()):
        endereco = "/" + caminho
        if endereco.startswith(FORA_DA_VARREDURA):
            continue
        # Argumento vira um número que não existe: o que se confere é a recusa.
        endereco = (
            endereco.replace("<int:pk>", "99999")
            .replace("<int:item_pk>", "99999")
            .replace("<int:anexo_id>", "99999")
            .replace("<int:id_set>", "99999")
            .replace("<int:numero>", "99999")
            .replace("<str:rotina>", "contas")
        )
        if "<" in endereco or "(?P" in endereco:
            continue
        yield endereco


class RotasPorPerfil(TestCase):
    """A varredura de rotas × perfis, refeita a cada execução dos testes."""

    @classmethod
    def setUpTestData(cls):
        cls.gerencia = usuario("gerencia_varredura", ADMINISTRACAO)
        cls.administrativo = usuario("administrativo_varredura", ADMINISTRATIVO)
        cls.lider = usuario("lider_varredura", LIDER)
        cls.vendedor = usuario("vendedor_varredura", VENDEDOR)
        # Os quatro perfis que vieram com o prompt de controle de acesso (1.44.0), e a conta
        # sem perfil nenhum, que entra e não pode abrir nada.
        cls.acessos = usuario("acessos_varredura", ADMIN_ACESSOS)
        cls.compras = usuario("compras_varredura", COMPRAS)
        cls.estoque = usuario("estoque_varredura", ESTOQUE)
        cls.consulta = usuario("consulta_varredura", CONSULTA)
        cls.sem_perfil = usuario("sem_perfil_varredura")
        cls.rotas = sorted(set(_rotas()))

    def _entrar(self, nome):
        """Entra e já confirma a senha: sem isso a área de acessos só redirecionaria para a
        tela da senha, e a varredura não chegaria às telas de verdade."""
        self.client.login(username=nome, password=SENHA_TESTE)
        confirmar_senha(self.client)

    def test_a_varredura_enxerga_as_telas_do_sistema(self):
        """Se este número cair muito, a varredura parou de achar as rotas."""
        self.assertGreater(len(self.rotas), 50, "a varredura deixou de enxergar as rotas")
        self.assertIn("/studio/painel/vendas-do-dia/", self.rotas)
        self.assertIn("/studio/alertas/", self.rotas)

    def test_o_vendedor_so_abre_a_tela_de_consulta(self):
        """Nenhuma outra rota pode responder 200 para o Operador vendedor."""
        self.client.login(username="vendedor_varredura", password=SENHA_TESTE)
        vazaram = []
        for rota in self.rotas:
            if rota in DO_VENDEDOR or rota in DE_TODOS:
                continue
            resposta = self.client.get(rota)
            if resposta.status_code == 200:
                vazaram.append(rota)
        self.assertEqual(
            vazaram, [],
            "estas telas abriram para o Operador vendedor, que só pode ver a consulta "
            "de balcão. Falta permission_required nelas: " + ", ".join(vazaram),
        )

    def test_a_tela_de_consulta_abre_para_o_vendedor(self):
        """O outro lado da moeda: a tela dele não pode ter fechado sem querer."""
        self.client.login(username="vendedor_varredura", password=SENHA_TESTE)
        for rota in sorted(DO_VENDEDOR):
            with self.subTest(rota=rota):
                self.assertEqual(
                    self.client.get(rota).status_code, 200,
                    f"a única tela do vendedor parou de abrir: {rota}",
                )

    def test_sem_perfil_nao_abre_nada(self):
        """Conta sem perfil entra (a senha confere) e não abre tela nenhuma da loja."""
        self._entrar("sem_perfil_varredura")
        abriram = [rota for rota in self.rotas
                   if rota not in DE_TODOS and self.client.get(rota).status_code == 200]
        self.assertEqual(abriram, [], "abriram para quem não tem perfil: " + ", ".join(abriram))

    def test_o_administrador_de_acessos_nao_ve_numero_da_loja(self):
        """Cuida de contas e senhas; dinheiro, só se a gerência der à parte."""
        self._entrar("acessos_varredura")
        abriram = [rota for rota in self.rotas
                   if rota not in DE_TODOS and not rota.startswith(DA_AREA_DE_ACESSOS)
                   and self.client.get(rota).status_code == 200]
        self.assertEqual(abriram, [], "abriram para o Administrador de acessos: " + ", ".join(abriram))
        self.assertEqual(self.client.get(DA_AREA_DE_ACESSOS).status_code, 200)

    def test_nenhuma_rota_quebra_para_nenhum_perfil(self):
        """Erro de programação em tela pouco visitada aparece aqui, não na loja."""
        for nome in ("gerencia_varredura", "lider_varredura", "administrativo_varredura",
                     "vendedor_varredura", "acessos_varredura", "compras_varredura",
                     "estoque_varredura", "consulta_varredura", "sem_perfil_varredura"):
            self._entrar(nome)
            quebraram = []
            for rota in self.rotas:
                resposta = self.client.get(rota)
                if resposta.status_code >= 500:
                    quebraram.append(f"{rota} ({resposta.status_code})")
            self.assertEqual(
                quebraram, [],
                f"estas rotas quebraram para {nome}: " + ", ".join(quebraram),
            )
            self.client.logout()

    def test_o_historico_de_versoes_e_tela_de_dinheiro(self):
        """O caso que esta varredura encontrou no dia em que nasceu.

        O histórico de mudanças explica cada conserto citando o número que estava
        errado, e esses números são o faturamento, o lucro bruto e a margem da loja.
        A tela pedia só login até a 1.24.0: o vendedor abria o ano inteiro de
        faturamento digitando o endereço.
        """
        self.client.login(username="vendedor_varredura", password=SENHA_TESTE)
        self.assertEqual(
            self.client.get("/studio/versoes/").status_code, 403,
            "a tela de versões voltou a abrir para o Operador vendedor",
        )

        self.client.logout()
        self.client.login(username="gerencia_varredura", password=SENHA_TESTE)
        pagina = self.client.get("/studio/versoes/")
        self.assertEqual(pagina.status_code, 200, "a gerência precisa ver o histórico")
        self.assertIn(
            "R$", pagina.content.decode(),
            "o histórico deixou de citar os números dos consertos. Se isso for de "
            "propósito, esta tela pode voltar a ser de todo mundo.",
        )

    def test_quem_nao_entrou_nao_abre_tela_nenhuma(self):
        """Sem login, só as rotas públicas respondem."""
        abriram = []
        for rota in self.rotas:
            if rota in DE_TODOS:
                continue
            resposta = self.client.get(rota)
            if resposta.status_code == 200:
                abriram.append(rota)
        self.assertEqual(
            abriram, [],
            "estas telas abriram sem login: " + ", ".join(abriram),
        )
