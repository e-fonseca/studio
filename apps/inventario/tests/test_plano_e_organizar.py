"""O padrão de inventário do varejo: contagem cíclica, classificação e os relatórios.

Entraram na 1.39.0, a pedido dele em 22/10/2026. Os testes aqui cobram as decisões que
quebram calado quando alguém mexer:

* a classe do produto é a MESMA do painel (foi defeito entre o Painel e a Visão geral);
* "parado" é só mercadoria de revenda (foi defeito uma vez, com o consumo próprio);
* a conferência do SET distingue "não entrou" de "mexeu", porque a loja vendeu no meio;
* quem conta não decide descarte;
* a tabela que decide na última coluna vira cartão no celular.
"""

from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.auditoria.models import EventoAuditoria
from apps.contas.perfis import ADMINISTRACAO, ADMINISTRATIVO, VENDEDOR
from apps.core import curva_abc
from apps.core.fabricas import SENHA_TESTE, usuario
from apps.importacao.models import Importacao, ProdutoImportado
from apps.inventario import conferencia, organizar, plano, servicos
from apps.inventario.models import Contagem, ItemContado
from apps.painel import dashboard


def _importacao(corte=date(2026, 9, 20)):
    return Importacao.objects.create(
        origem=Importacao.Origem.BANCO,
        situacao=Importacao.Situacao.CONCLUIDA,
        concluida_em=timezone.now(),
        data_corte=corte,
        dias_abertos_12m=300,
    )


def _produto(importacao, codigo, **campos):
    campos.setdefault("descricao", f"PRODUTO {codigo}")
    campos.setdefault("custo", Decimal("10"))
    campos.setdefault("estoque", Decimal("4"))
    campos.setdefault("receita_12m", Decimal("0"))
    return ProdutoImportado.objects.create(importacao=importacao, codigo=codigo, **campos)


class TestCurvaAbcNumLugarSo(TestCase):
    """A classe do produto não pode ser uma no painel e outra no inventário."""

    def test_a_classe_sai_do_acumulado_antes_do_produto(self):
        """Quem CRUZA os 80% entra em A: senão o maior produto deixaria A vazia."""
        self.assertEqual(curva_abc.letras([Decimal("100")]), ["A"])

    def test_sem_faturamento_nenhum_nao_existe_curva(self):
        """Total zero devolve vazio, e não um monte de produtos classe A."""
        self.assertEqual(curva_abc.letras([Decimal("0"), Decimal("0")]), [])
        self.assertEqual(curva_abc.letras([]), [])

    def test_produto_sem_venda_fica_com_a_letra_vazia(self):
        """São 6.483 produtos nesta loja: jogá-los em C esconderia o grupo."""
        classes = curva_abc.por_produto([("a", Decimal("100")), ("b", Decimal("0"))])
        self.assertEqual(classes["a"], "A")
        self.assertEqual(classes["b"], "")

    def test_a_ordem_de_entrada_nao_muda_a_classe(self):
        pares = [("c", Decimal("1")), ("a", Decimal("900")), ("b", Decimal("99"))]
        self.assertEqual(curva_abc.por_produto(pares),
                         curva_abc.por_produto(list(reversed(pares))))

    def test_o_painel_e_o_plano_classificam_igual(self):
        """O teste que importa: as duas telas leem a MESMA regra."""
        importacao = _importacao()
        for n in range(1, 21):
            _produto(importacao, str(n), receita_12m=Decimal(str(1000 // n)),
                     estoque=Decimal("3"))
        do_painel = dashboard._abc(importacao.itens.all())
        do_plano = plano.montar(importacao)
        por_letra = {c.letra: c.produtos for c in do_painel}
        for classe in do_plano.classes:
            if classe.letra:
                self.assertEqual(classe.produtos, por_letra[classe.letra],
                                 f"classe {classe.letra} difere entre painel e plano")


class TestPlanoDeContagem(TestCase):
    def setUp(self):
        self.importacao = _importacao()
        self.caro = _produto(self.importacao, "1", receita_12m=Decimal("1000"),
                             estoque=Decimal("10"), custo=Decimal("50"))
        self.barato = _produto(self.importacao, "2", receita_12m=Decimal("1"),
                               estoque=Decimal("2"), custo=Decimal("1"))
        self.zerado = _produto(self.importacao, "3", receita_12m=Decimal("500"),
                               estoque=Decimal("0"))
        self.operador = usuario("contador", ADMINISTRATIVO)

    def test_produto_zerado_nao_entra_no_plano(self):
        """Contar o que está zerado não acha divergência e afogaria a lista."""
        montado = plano.montar(self.importacao)
        self.assertEqual(montado.produtos, 2)
        self.assertNotIn("3", [item.codigo for item in montado.sugeridos])

    def test_a_curva_sai_de_todos_os_produtos_e_nao_so_dos_com_estoque(self):
        """O zerado conta para a curva, senão a classe mudaria entre as telas."""
        montado = plano.montar(self.importacao)
        classes = {c.letra: c.produtos for c in montado.classes}
        # Com 1000, 500 e 1 de faturamento, o de 1000 é A e o de 1 é C. Se o zerado
        # (500) ficasse de fora da curva, o de 1 subiria de classe.
        self.assertEqual(classes.get("A"), 1)
        self.assertEqual(classes.get("C"), 1)

    def test_nunca_contado_conta_como_esperando(self):
        montado = plano.montar(self.importacao)
        self.assertEqual(montado.nunca_contados, 2)
        self.assertEqual(montado.a_contar, 2)
        self.assertTrue(montado.geral_vencida)

    def test_contagem_aberta_nao_conta_como_contado(self):
        """Contagem no meio não é resultado: a pessoa ainda está contando."""
        contagem = servicos.abrir("Prateleira", self.operador)
        contagem.importacao = self.importacao
        contagem.save()
        servicos.registrar_contagem(contagem, "1", Decimal("10"), self.operador)
        self.assertEqual(plano.montar(self.importacao).nunca_contados, 2)
        servicos.fechar(contagem, self.operador)
        self.assertEqual(plano.montar(self.importacao).nunca_contados, 1)

    def test_o_prazo_de_cada_classe_e_o_do_varejo(self):
        self.assertEqual(plano.CADENCIA["A"], 30)
        self.assertEqual(plano.CADENCIA["B"], 90)
        self.assertEqual(plano.CADENCIA["C"], 180)
        self.assertEqual(plano.CADENCIA[""], 180)
        self.assertEqual(plano.CADENCIA_GERAL, 365)

    def test_classe_a_vence_em_trinta_dias_e_classe_c_nao(self):
        contagem = servicos.abrir("Prateleira", self.operador)
        contagem.importacao = self.importacao
        contagem.save()
        for codigo in ("1", "2"):
            servicos.registrar_contagem(contagem, codigo, Decimal("1"), self.operador)
        servicos.fechar(contagem, self.operador)
        ItemContado.objects.update(contado_em=timezone.now() - timedelta(days=45))

        montado = plano.montar(self.importacao)
        por_letra = {c.letra: c for c in montado.classes}
        self.assertEqual(por_letra["A"].vencidos, 1, "classe A vence com 45 dias")
        self.assertEqual(por_letra["C"].em_dia, 1, "classe C ainda está em dia")

    def test_a_classe_mais_urgente_vem_na_frente_e_dentro_dela_o_maior_dinheiro(self):
        caro_de_c = _produto(self.importacao, "4", receita_12m=Decimal("2"),
                             estoque=Decimal("100"), custo=Decimal("90"))
        sugeridos = plano.montar(self.importacao).sugeridos
        self.assertEqual(sugeridos[0].codigo, "1", "classe A vem antes de classe C cara")
        self.assertEqual(sugeridos[1].codigo, caro_de_c.codigo)

    def test_o_nome_sugerido_leva_a_classe_e_a_data(self):
        nome = plano.nome_sugerido(plano.montar(self.importacao))
        self.assertIn("classe A", nome)

    def test_sem_importacao_o_plano_e_vazio_e_nao_estoura(self):
        montado = plano.montar(None)
        self.assertEqual(montado.produtos, 0)
        self.assertEqual(montado.classes, [])


class TestOQueSeAchaNaPrateleira(TestCase):
    def setUp(self):
        self.importacao = _importacao()
        _produto(self.importacao, "1", descricao="VASO", custo=Decimal("30"))
        self.operador = usuario("contador", ADMINISTRATIVO)
        self.contagem = servicos.abrir("Prateleira", self.operador)
        self.contagem.importacao = self.importacao
        self.contagem.save()
        self.item = servicos.registrar_contagem(
            self.contagem, "1", Decimal("4"), self.operador)

    def test_a_peca_nasce_perfeita(self):
        self.assertTrue(self.item.perfeito)
        self.assertEqual(organizar.contar_por_estado()["danificado"], 0)

    def test_marcar_registra_quem_e_quando_na_auditoria(self):
        organizar.marcar(self.item, ItemContado.Estado.DANIFICADO, self.operador)
        self.item.refresh_from_db()
        self.assertEqual(self.item.estado, ItemContado.Estado.DANIFICADO)
        self.assertIsNotNone(self.item.estado_em)
        self.assertEqual(self.item.estado_por, self.operador)
        evento = EventoAuditoria.objects.filter(acao="inventario.estado_marcado").first()
        self.assertIsNotNone(evento)
        self.assertEqual(evento.depois["estado"], "danificado")

    def test_marcar_duas_vezes_o_mesmo_estado_nao_enche_a_trilha(self):
        organizar.marcar(self.item, ItemContado.Estado.DANIFICADO, self.operador)
        organizar.marcar(self.item, ItemContado.Estado.DANIFICADO, self.operador)
        self.assertEqual(
            EventoAuditoria.objects.filter(acao="inventario.estado_marcado").count(), 1)

    def test_o_valor_da_peca_e_o_que_se_perde_e_nao_a_diferenca(self):
        """Jogar a peça fora perde a peça inteira, não o quanto ela divergia do SET."""
        self.assertEqual(self.item.valor_no_custo, Decimal("120.00"))
        self.assertEqual(self.item.valor_da_diferenca, Decimal("0.00"))

    def test_resolver_tira_da_fila_e_reabrir_devolve(self):
        organizar.marcar(self.item, ItemContado.Estado.SEM_ETIQUETA, self.operador)
        self.assertEqual(len(organizar.esperando()), 1)
        organizar.resolver(self.item, self.operador)
        self.assertEqual(len(organizar.esperando()), 0)
        organizar.reabrir(self.item, self.operador)
        self.assertEqual(len(organizar.esperando()), 1)

    def test_peca_perfeita_nao_tem_o_que_resolver(self):
        with self.assertRaises(organizar.ErroDeOrganizacao):
            organizar.resolver(self.item, self.operador)

    def test_a_classificacao_e_em_dois_tempos(self):
        """Quem conta marca danificado; quem decide manda para conserto ou descarte."""
        organizar.marcar(self.item, ItemContado.Estado.DANIFICADO, self.operador)
        grupos = {g.chave: g for g in organizar.grupos(self.importacao)}
        self.assertEqual(grupos["danificado"].quantos, 1)
        organizar.marcar(self.item, ItemContado.Estado.CONSERTO, self.operador)
        grupos = {g.chave: g for g in organizar.grupos(self.importacao)}
        self.assertEqual(grupos["danificado"].quantos, 0)
        self.assertEqual(grupos["conserto"].quantos, 1)

    def test_so_peca_com_codigo_de_barras_tem_etiqueta_para_refazer(self):
        organizar.marcar(self.item, ItemContado.Estado.SEM_ETIQUETA, self.operador)
        self.assertEqual(organizar.itens_para_etiqueta(), [])
        self.item.codigo_barras = "0000000000024"
        self.item.save(update_fields=["codigo_barras"])
        self.assertEqual(len(organizar.itens_para_etiqueta()), 1)


class TestProdutosParados(TestCase):
    def setUp(self):
        self.importacao = _importacao()
        self.hoje = date(2026, 10, 22)

    def test_entra_quem_tem_peca_e_nao_vende_ha_meses(self):
        _produto(self.importacao, "1", ultima_venda=self.hoje - timedelta(days=400))
        _produto(self.importacao, "2", ultima_venda=self.hoje - timedelta(days=10))
        parados = organizar.parados(self.importacao, hoje=self.hoje)
        self.assertEqual([p.codigo for p in parados], ["1"])

    def test_sem_estoque_nao_e_parado(self):
        """Sem peça na prateleira não há dinheiro parado: há produto que não se repôs."""
        _produto(self.importacao, "1", estoque=Decimal("0"),
                 ultima_venda=self.hoje - timedelta(days=400))
        self.assertEqual(organizar.parados(self.importacao, hoje=self.hoje), [])

    def test_consumo_proprio_da_loja_fica_de_fora(self):
        """Já foi defeito uma vez: nunca vendeu porque nunca foi para vender."""
        _produto(self.importacao, "1", descricao="CONSUMO PROPRIO - CESTO/PAPEL ETC",
                 grupo="SEM GRUPO")
        _produto(self.importacao, "2", descricao="VASO DE CERAMICA")
        parados = organizar.parados(self.importacao, hoje=self.hoje)
        self.assertEqual([p.codigo for p in parados], ["2"])

    def test_nunca_vendido_e_encalhado(self):
        _produto(self.importacao, "1")
        parado = organizar.parados(self.importacao, hoje=self.hoje)[0]
        self.assertTrue(parado.nunca_vendeu)
        self.assertTrue(parado.encalhado)

    def test_o_mais_caro_vem_na_frente(self):
        _produto(self.importacao, "1", custo=Decimal("1"), estoque=Decimal("1"))
        _produto(self.importacao, "2", custo=Decimal("100"), estoque=Decimal("10"))
        parados = organizar.parados(self.importacao, hoje=self.hoje)
        self.assertEqual([p.codigo for p in parados], ["2", "1"])


class TestOAjusteEntrouNoSet(TestCase):
    def setUp(self):
        self.velha = _importacao(corte=date(2026, 9, 20))
        _produto(self.velha, "1", descricao="VASO", estoque=Decimal("8"),
                 custo=Decimal("30"))
        self.operador = usuario("contador", ADMINISTRATIVO)
        self.contagem = servicos.abrir("Prateleira", self.operador)
        self.contagem.importacao = self.velha
        self.contagem.save()
        servicos.registrar_contagem(self.contagem, "1", Decimal("6"), self.operador)
        servicos.fechar(self.contagem, self.operador)

    def _foto_nova(self, estoque):
        nova = _importacao(corte=date(2026, 9, 27))
        _produto(nova, "1", descricao="VASO", estoque=Decimal(estoque),
                 custo=Decimal("30"))
        return nova

    def test_sem_foto_nova_a_conferencia_nao_responde(self):
        """Comparar com a mesma foto repetiria a divergência e não diria nada."""
        conferida = conferencia.conferir(self.contagem)
        self.assertFalse(conferida.disponivel)

    def test_saldo_igual_ao_contado_quer_dizer_que_entrou(self):
        self._foto_nova("6")
        conferida = conferencia.conferir(self.contagem)
        self.assertTrue(conferida.disponivel)
        self.assertEqual(conferida.entraram, 1)
        self.assertTrue(conferida.tudo_entrou)

    def test_saldo_igual_ao_de_antes_quer_dizer_que_nao_entrou(self):
        self._foto_nova("8")
        conferida = conferencia.conferir(self.contagem)
        self.assertEqual(conferida.nao_entraram, 1)
        self.assertFalse(conferida.tudo_entrou)

    def test_saldo_diferente_dos_dois_nao_e_afirmado_como_pendente(self):
        """A loja vendeu entre a contagem e a foto: o sistema não finge saber."""
        self._foto_nova("5")
        conferida = conferencia.conferir(self.contagem)
        self.assertEqual(conferida.mexeram, 1)
        self.assertEqual(conferida.nao_entraram, 0)
        self.assertEqual(conferida.linhas[0].recado, "Mudou, mas não para o contado")

    def test_produto_que_saiu_do_set_sai_da_conta(self):
        _importacao(corte=date(2026, 9, 27))
        conferida = conferencia.conferir(self.contagem)
        self.assertEqual(conferida.sumiram, 1)
        self.assertEqual(conferida.linhas, [])


class TestTelas(TestCase):
    def setUp(self):
        self.importacao = _importacao()
        _produto(self.importacao, "1", descricao="VASO", custo=Decimal("30"),
                 receita_12m=Decimal("900"), codigo_barras="0000000000024")
        self.gerente = usuario("gerente", ADMINISTRACAO)
        self.operador = usuario("operador", ADMINISTRATIVO)
        self.vendedor = usuario("vendedor", VENDEDOR)
        self.contagem = servicos.abrir("Prateleira", self.operador)
        self.contagem.importacao = self.importacao
        self.contagem.save()
        self.item = servicos.registrar_contagem(
            self.contagem, "1", Decimal("2"), self.operador)

    def _entrar(self, quem):
        self.client.login(username=quem.get_username(), password=SENHA_TESTE)

    def test_o_vendedor_nao_chega_na_tela_organizar(self):
        """Ela mostra custo e valor da peça, e o vendedor não vê dinheiro."""
        self._entrar(self.vendedor)
        self.assertEqual(self.client.get(reverse("inventario:organizar")).status_code, 403)

    def test_o_vendedor_nao_baixa_o_relatorio_de_descarte(self):
        self._entrar(self.vendedor)
        self.assertEqual(self.client.get(reverse("inventario:descarte")).status_code, 403)

    def test_a_tela_do_inventario_abre_com_o_plano(self):
        self._entrar(self.operador)
        pagina = self.client.get(reverse("inventario:lista"))
        self.assertContains(pagina, "Plano de contagem")
        self.assertContains(pagina, "Classe A")

    def test_abrir_a_contagem_sugerida_da_nome_a_ela(self):
        self._entrar(self.operador)
        antes = Contagem.objects.count()
        resposta = self.client.post(reverse("inventario:abrir_sugerida"), follow=True)
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(Contagem.objects.count(), antes + 1)
        self.assertIn("Contagem cíclica", Contagem.objects.first().nome)

    def test_quem_conta_marca_danificada_mas_nao_descarta(self):
        """Na prateleira, com a peça numa mão, sairia o que for mais rápido."""
        self._entrar(self.operador)
        endereco = reverse("inventario:estado", args=[self.contagem.pk, self.item.pk])
        self.client.post(endereco, {"estado": "danificado", "da_tela": "1"})
        self.item.refresh_from_db()
        self.assertEqual(self.item.estado, ItemContado.Estado.DANIFICADO)

        self.client.post(endereco, {"estado": "descarte", "da_tela": "1"})
        self.item.refresh_from_db()
        self.assertEqual(self.item.estado, ItemContado.Estado.DANIFICADO,
                         "descarte não se decide na contagem")

    def test_a_camera_recebe_json_e_a_tela_recebe_redirecionamento(self):
        """Recarregar desligaria a câmera; a tela do computador espera o de sempre."""
        self._entrar(self.operador)
        endereco = reverse("inventario:estado", args=[self.contagem.pk, self.item.pk])
        da_camera = self.client.post(endereco, {"estado": "sem_etiqueta"})
        self.assertEqual(da_camera.status_code, 200)
        self.assertTrue(da_camera.json()["ok"])
        da_tela = self.client.post(endereco, {"estado": "danificado", "da_tela": "1"})
        self.assertEqual(da_tela.status_code, 302)

    def test_endereco_do_formulario_nao_vira_redirecionamento(self):
        """Redirecionamento aberto: bastaria um link forjado para mandar alguém fora."""
        self._entrar(self.operador)
        resposta = self.client.post(
            reverse("inventario:estado", args=[self.contagem.pk, self.item.pk]),
            {"estado": "danificado", "da_tela": "1", "voltar": "https://exemplo.invalido/"},
        )
        self.assertNotIn("exemplo.invalido", resposta["Location"])

    def test_classificar_leva_a_peca_para_conserto(self):
        self._entrar(self.gerente)
        organizar.marcar(self.item, ItemContado.Estado.DANIFICADO, self.operador)
        self.client.post(reverse("inventario:classificar", args=[self.item.pk]),
                         {"estado": "conserto"})
        self.item.refresh_from_db()
        self.assertEqual(self.item.estado, ItemContado.Estado.CONSERTO)

    def test_resolver_e_desfazer_pela_tela(self):
        self._entrar(self.gerente)
        organizar.marcar(self.item, ItemContado.Estado.SEM_ETIQUETA, self.operador)
        self.client.post(reverse("inventario:resolver", args=[self.item.pk]))
        self.item.refresh_from_db()
        self.assertTrue(self.item.resolvido)
        self.client.post(reverse("inventario:resolver", args=[self.item.pk]),
                         {"desfazer": "1"})
        self.item.refresh_from_db()
        self.assertFalse(self.item.resolvido)

    def test_a_folha_de_etiquetas_desenha_o_codigo_de_barras(self):
        self._entrar(self.gerente)
        organizar.marcar(self.item, ItemContado.Estado.SEM_ETIQUETA, self.operador)
        pagina = self.client.get(reverse("inventario:etiquetas"))
        self.assertContains(pagina, "<svg")
        self.assertContains(pagina, "0000000000024")


class TestRelatorios(TestCase):
    def setUp(self):
        self.importacao = _importacao()
        _produto(self.importacao, "1", descricao="VASO", custo=Decimal("30"),
                 receita_12m=Decimal("900"))
        self.gerente = usuario("gerente", ADMINISTRACAO)
        self.client.login(username="gerente", password=SENHA_TESTE)
        self.contagem = servicos.abrir("Prateleira", self.gerente)
        self.contagem.importacao = self.importacao
        self.contagem.save()
        self.item = servicos.registrar_contagem(
            self.contagem, "1", Decimal("2"), self.gerente)

    def _baixar(self, rota, **argumentos):
        papel = self.client.get(reverse(rota, **argumentos))
        folha = self.client.get(reverse(rota, **argumentos) + "?formato=planilha")
        return papel, folha

    def test_os_quatro_relatorios_saem_em_papel_e_em_planilha(self):
        organizar.marcar(self.item, ItemContado.Estado.DESCARTE, self.gerente)
        rotas = [
            ("inventario:folha_de_contagem", {}),
            ("inventario:descarte", {}),
            ("inventario:conserto", {}),
            ("inventario:parados", {}),
            ("inventario:divergencia", {"args": [self.contagem.pk]}),
        ]
        for rota, argumentos in rotas:
            papel, folha = self._baixar(rota, **argumentos)
            self.assertEqual(papel.status_code, 200, rota)
            self.assertEqual(papel["Content-Type"], "application/pdf", rota)
            self.assertEqual(folha.status_code, 200, rota)
            self.assertIn("spreadsheet", folha["Content-Type"], rota)

    def test_o_papel_e_a_planilha_do_descarte_contam_a_mesma_peca(self):
        """Montados pela MESMA função: dois montadores divergem na primeira correção."""
        organizar.marcar(self.item, ItemContado.Estado.DESCARTE, self.gerente)
        papel, folha = self._baixar("inventario:descarte")
        self.assertGreater(len(papel.content), 800)
        self.assertGreater(len(folha.content), 800)

    def test_o_relatorio_de_divergencia_diz_que_o_sistema_nao_escreve_no_set(self):
        papel = self.client.get(reverse("inventario:divergencia", args=[self.contagem.pk]))
        # O PDF é binário, mas o texto vai dentro em parênteses, sem compressão.
        self.assertIn(b"nunca escreve", papel.content)


class TestTabelaQueDecideViraCartao(TestCase):
    """Quadro que rola de lado no celular esconde a coluna que decide.

    Medir `scrollWidth` da PÁGINA não acha isso: quem rola é o quadro. O que se pode
    cobrar aqui é o contrato: toda tabela com `data-rotulo` tem de estar dentro de um
    quadro `tabela-em-cartao`, senão os rótulos ficam escritos e a tabela rola igual.
    """

    def test_toda_tabela_com_data_rotulo_esta_num_quadro_em_cartao(self):
        import re
        from pathlib import Path

        from django.conf import settings

        faltando = []
        for caminho in Path(settings.BASE_DIR, "templates").rglob("*.html"):
            texto = caminho.read_text(encoding="utf-8")
            if "data-rotulo" not in texto:
                continue
            for bloco in re.findall(r'<div class="[^"]*tabela[^"]*">.*?</table>',
                                    texto, flags=re.S):
                if "data-rotulo" in bloco and "tabela-em-cartao" not in bloco:
                    faltando.append(caminho.name)
        self.assertEqual(faltando, [], "tabelas com data-rotulo fora de tabela-em-cartao")
