from datetime import timedelta
from decimal import Decimal

from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.auditoria.models import EventoAuditoria
from apps.contas.perfis import ADMINISTRACAO, ADMINISTRATIVO
from apps.core import versao
from apps.core.fabricas import SENHA_TESTE, usuario
from apps.importacao import servicos
from apps.importacao.fontes.firebird import ErroFonte, preparar_copia
from apps.importacao.models import Importacao, ProdutoImportado


def importacao_concluida(dias_atras=0, **extra):
    hoje = timezone.localdate()
    agora = timezone.now()
    dados = {
        "origem": Importacao.Origem.BANCO,
        "situacao": Importacao.Situacao.CONCLUIDA,
        "iniciada_em": agora - timedelta(days=dias_atras),
        "concluida_em": agora - timedelta(days=dias_atras),
        "data_corte": hoje - timedelta(days=dias_atras),
        "produtos": 2,
        "dias_abertos_12m": 300,
        "arquivo": "C:\\backup\\DADOS-SET.FDB",
    }
    dados.update(extra)
    return Importacao.objects.create(**dados)


class EstadoDosDadosTest(TestCase):
    def test_sem_nenhuma_importacao_avisa_que_falta_importar(self):
        estado = servicos.estado_dos_dados()
        self.assertEqual(estado.nivel, "sem_dados")
        self.assertTrue(estado.avisar)

    def test_dados_de_ontem_ficam_em_dia(self):
        importacao_concluida(dias_atras=1)
        estado = servicos.estado_dos_dados()
        self.assertEqual(estado.nivel, "ok")
        self.assertFalse(estado.avisar)
        self.assertIn("DADOS-SET.FDB", estado.detalhe)

    def test_dados_de_tres_dias_pedem_atencao(self):
        importacao_concluida(dias_atras=3)
        self.assertEqual(servicos.estado_dos_dados().nivel, "atencao")

    def test_dados_de_dez_dias_ficam_vencidos(self):
        importacao_concluida(dias_atras=10)
        estado = servicos.estado_dos_dados()
        self.assertEqual(estado.nivel, "vencido")
        self.assertIn("10 dias atrás", estado.titulo)

    def test_falha_depois_de_uma_importacao_boa_aparece_no_aviso(self):
        importacao_concluida(dias_atras=1)
        Importacao.objects.create(
            origem=Importacao.Origem.BANCO,
            situacao=Importacao.Situacao.FALHOU,
            mensagem="Não encontrei o arquivo de origem",
            concluida_em=timezone.now(),
        )
        estado = servicos.estado_dos_dados()
        self.assertEqual(estado.nivel, "atencao")
        self.assertIn("Não encontrei o arquivo", estado.detalhe)
        self.assertIsNotNone(estado.falha_posterior)

    def test_idade_dos_dados_conta_em_dias(self):
        importacao = importacao_concluida(dias_atras=5)
        self.assertEqual(importacao.idade_dos_dados(), 5)


class LocalizarBackupTest(TestCase):
    def test_sem_configuracao_nao_adivinha_arquivo(self):
        with override_settings(IMPORTACAO_BACKUP_ORIGEM=""):
            self.assertIsNone(servicos.localizar_backup())

    def test_em_uma_pasta_pega_o_backup_mais_recente(self):
        import os
        import tempfile

        with tempfile.TemporaryDirectory() as pasta:
            antigo = f"{pasta}/DADOS-SET-01.FDB"
            novo = f"{pasta}/DADOS-SET-02.FDB"
            open(antigo, "wb").write(b"a")
            open(novo, "wb").write(b"b")
            os.utime(antigo, (1, 1))
            open(f"{pasta}/leia.txt", "w").write("nao e backup")
            with override_settings(IMPORTACAO_BACKUP_ORIGEM=pasta):
                self.assertEqual(str(servicos.localizar_backup()), novo)

    def test_procura_tambem_nas_subpastas_por_data(self):
        import os
        import tempfile
        from pathlib import Path as Caminho

        with tempfile.TemporaryDirectory() as pasta:
            antiga = Caminho(pasta) / "2026-10-03"
            nova = Caminho(pasta) / "2026-10-04"
            antiga.mkdir()
            nova.mkdir()
            (antiga / "DADOS-SET.FDB").write_bytes(b"antigo")
            alvo = nova / "DADOS-SET.FDB"
            alvo.write_bytes(b"novo")
            os.utime(antiga / "DADOS-SET.FDB", (1, 1))
            with override_settings(IMPORTACAO_BACKUP_ORIGEM=pasta):
                self.assertEqual(servicos.localizar_backup(), alvo)

    def test_arquivo_vazio_e_ignorado(self):
        import tempfile
        from pathlib import Path as Caminho

        with tempfile.TemporaryDirectory() as pasta:
            cheio = Caminho(pasta) / "DADOS-SET-01.FDB"
            cheio.write_bytes(b"conteudo")
            vazio = Caminho(pasta) / "DADOS-SET-02.FDB"
            vazio.write_bytes(b"")
            with override_settings(IMPORTACAO_BACKUP_ORIGEM=pasta):
                self.assertEqual(servicos.localizar_backup(), cheio)

    def test_arquivo_informado_vale_mais_que_a_configuracao(self):
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".fdb") as arquivo:
            self.assertEqual(str(servicos.localizar_backup(arquivo.name)), arquivo.name)


class ExecutarImportacaoTest(TestCase):
    def test_arquivo_inexistente_registra_falha_com_motivo(self):
        importacao = servicos.executar(arquivo="/nao/existe/DADOS-SET.FDB")
        self.assertEqual(importacao.situacao, Importacao.Situacao.FALHOU)
        self.assertIn("Não encontrei o arquivo", importacao.mensagem)
        self.assertTrue(
            EventoAuditoria.objects.filter(acao="importacao.falhou", resultado="falha").exists()
        )

    def test_sem_origem_configurada_explica_o_que_falta(self):
        with override_settings(IMPORTACAO_BACKUP_ORIGEM=""):
            importacao = servicos.executar()
        self.assertEqual(importacao.situacao, Importacao.Situacao.FALHOU)
        self.assertIn("STUDIO_SET_BACKUP", importacao.mensagem)

    def test_comando_falha_com_mensagem_clara(self):
        with self.assertRaisesMessage(CommandError, "Importação falhou"):
            call_command("importar_set", "--arquivo", "/nao/existe/DADOS-SET.FDB")

    def test_importacao_relatorio_ainda_nao_implementada(self):
        with self.assertRaises(ErroFonte):
            servicos.executar(origem=Importacao.Origem.RELATORIO)

    def test_copia_nunca_le_o_arquivo_de_origem(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as pasta:
            origem = Path(pasta) / "DADOS-SET.FDB"
            origem.write_bytes(b"conteudo")
            copia = preparar_copia(origem, Path(pasta) / "trabalho")
            self.assertNotEqual(copia, origem)
            self.assertEqual(copia.read_bytes(), b"conteudo")
            self.assertEqual(copia.name, "set.fdb")

    def test_fbk_sem_gbak_avisa_o_que_configurar(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as pasta:
            origem = Path(pasta) / "SET.FBK"
            origem.write_bytes(b"backup")
            with self.assertRaisesMessage(ErroFonte, "STUDIO_FIREBIRD_GBAK"):
                preparar_copia(origem, Path(pasta) / "trabalho")


class BackupSemNovidadeTest(TestCase):
    def test_mesmo_backup_nao_e_importado_de_novo(self):
        import tempfile
        from pathlib import Path as Caminho

        with tempfile.TemporaryDirectory() as pasta:
            arquivo = Caminho(pasta) / "DADOS-SET.FDB"
            arquivo.write_bytes(b"conteudo")
            anterior = importacao_concluida(dias_atras=1)
            anterior.arquivo = str(arquivo)
            anterior.arquivo_bytes = arquivo.stat().st_size
            anterior.arquivo_modificado_em = servicos.momento_do_arquivo(arquivo)
            # Mesma versão do sistema: backup igual e programa igual é que não dão o que fazer.
            anterior.versao_sistema = versao.atual().curta[:40]
            anterior.save()

            nova = servicos.executar(arquivo=str(arquivo))

        self.assertEqual(nova.situacao, Importacao.Situacao.SEM_NOVIDADE)
        self.assertIn("não mudou", nova.mensagem)
        self.assertEqual(servicos.ultima_concluida(), anterior, "os dados anteriores continuam valendo")
        self.assertEqual(servicos.estado_dos_dados().nivel, "ok", "sem backup novo não é falha")


class LimparAntigasTest(TestCase):
    def test_guarda_apenas_as_ultimas_fotos(self):
        for dias in range(5):
            importacao = importacao_concluida(dias_atras=dias)
            ProdutoImportado.objects.create(importacao=importacao, codigo=f"P{dias}", estoque=Decimal("1"))
        servicos.limpar_antigas(manter=2)
        self.assertEqual(ProdutoImportado.objects.count(), 2)
        self.assertEqual(Importacao.objects.count(), 5, "o registro das execuções não se apaga")


class TelasTest(TestCase):
    def setUp(self):
        self.importacao = importacao_concluida(dias_atras=1)
        ProdutoImportado.objects.create(
            importacao=self.importacao, codigo="100", descricao="CARVÃO 10KG",
            estoque=Decimal("5"), vendas_12m=Decimal("50"), compras_12m=Decimal("80"),
            custo=Decimal("20"), receita_12m=Decimal("2000"), prazo_reposicao_dias=7,
        )

    def test_historico_exige_permissao(self):
        usuario("operador")
        self.client.login(username="operador", password=SENHA_TESTE)
        self.assertEqual(self.client.get(reverse("importacao:historico")).status_code, 403)

    def test_quem_consulta_ve_o_historico(self):
        usuario("fiscal", ADMINISTRATIVO)
        self.client.login(username="fiscal", password=SENHA_TESTE)
        pagina = self.client.get(reverse("importacao:historico"))
        self.assertContains(pagina, "Concluída")
        self.assertContains(pagina, "Importações")

    def test_consulta_nao_importa(self):
        usuario("fiscal", ADMINISTRATIVO)
        self.client.login(username="fiscal", password=SENHA_TESTE)
        self.assertEqual(self.client.post(reverse("importacao:importar")).status_code, 403)

    def test_gerencia_dispara_a_importacao(self):
        usuario("edson", ADMINISTRACAO)
        self.client.login(username="edson", password=SENHA_TESTE)
        chamadas = []
        original = servicos.executar_em_segundo_plano
        servicos.executar_em_segundo_plano = lambda **kwargs: chamadas.append(kwargs)
        try:
            resposta = self.client.post(reverse("importacao:importar"), follow=True)
        finally:
            servicos.executar_em_segundo_plano = original
        self.assertEqual(len(chamadas), 1)
        self.assertContains(resposta, "Importação iniciada")

    def test_nao_dispara_duas_importacoes_juntas(self):
        Importacao.objects.create(origem=Importacao.Origem.BANCO, situacao=Importacao.Situacao.EM_ANDAMENTO)
        usuario("edson", ADMINISTRACAO)
        self.client.login(username="edson", password=SENHA_TESTE)
        resposta = self.client.post(reverse("importacao:importar"), follow=True)
        self.assertContains(resposta, "Já existe uma importação em andamento")

    def test_aviso_de_dados_velhos_aparece_no_topo_das_paginas(self):
        Importacao.objects.all().delete()
        importacao_concluida(dias_atras=9)
        usuario("edson", ADMINISTRACAO)
        self.client.login(username="edson", password=SENHA_TESTE)
        # A Visão geral mostra a data dos dados no próprio cabeçalho e esconde a faixa;
        # o painel é onde a faixa aparece.
        pagina = self.client.get(reverse("painel:painel"))
        self.assertContains(pagina, "9 dias atrás")
        self.assertContains(pagina, "Abrir o painel")

    def test_dados_em_dia_nao_poluem_a_tela(self):
        usuario("edson", ADMINISTRACAO)
        self.client.login(username="edson", password=SENHA_TESTE)
        self.assertNotContains(self.client.get(reverse("painel:painel")), "faixa-dados")


class ExplicacaoDoErroTest(TestCase):
    def test_erro_conhecido_vira_instrucao(self):
        from apps.importacao import diagnostico

        explicacao = diagnostico.explicar("Não sei onde está o backup do SET. Informe a pasta...")
        self.assertTrue(explicacao.conhecido)
        self.assertIn("não sabe onde fica o backup", explicacao.titulo)
        self.assertTrue(any("atualizar.ps1" in passo for passo in explicacao.como_resolver))

    def test_erro_de_permissao_fala_de_servico_de_rede(self):
        from apps.importacao import diagnostico

        explicacao = diagnostico.explicar("[WinError 5] Acesso negado: 'D:\\\\backup'")
        self.assertIn("permissão", explicacao.titulo)
        self.assertTrue(any("SERVIÇO DE REDE" in passo for passo in explicacao.como_resolver))

    def test_erro_desconhecido_cai_na_explicacao_geral(self):
        from apps.importacao import diagnostico

        explicacao = diagnostico.explicar("algo muito estranho aconteceu")
        self.assertFalse(explicacao.conhecido)
        self.assertTrue(any("importacao.log" in passo for passo in explicacao.como_resolver))

    def test_sem_mensagem_nao_inventa_explicacao(self):
        from apps.importacao import diagnostico

        self.assertIsNone(diagnostico.explicar(""))


class AvisoDeConclusaoTest(TestCase):
    def test_falha_recente_aparece_com_o_que_fazer(self):
        servicos.executar(arquivo="/nao/existe/DADOS-SET.FDB")
        usuario("edson", ADMINISTRACAO)
        self.client.login(username="edson", password=SENHA_TESTE)
        pagina = self.client.get(reverse("painel:painel"))
        self.assertContains(pagina, "falhou")
        self.assertContains(pagina, "não tem backup para ler")
        self.assertContains(pagina, "O que fazer")

    def test_conclusao_antiga_nao_fica_na_tela_para_sempre(self):
        antiga = importacao_concluida(dias_atras=0)
        antiga.concluida_em = timezone.now() - timedelta(hours=3)
        antiga.save()
        self.assertFalse(servicos.ultima_com_explicacao()["recente"])

    def test_progresso_comeca_registrado(self):
        importacao = servicos.executar(arquivo="/nao/existe/DADOS-SET.FDB")
        self.assertEqual(importacao.etapa, "Parou com erro")
        self.assertEqual(
            Importacao.objects.get(pk=importacao.pk).situacao, Importacao.Situacao.FALHOU
        )

    def test_barra_aparece_enquanto_importa(self):
        Importacao.objects.create(
            origem=Importacao.Origem.BANCO, situacao=Importacao.Situacao.EM_ANDAMENTO,
            etapa="Lendo as vendas", progresso=60,
        )
        usuario("edson", ADMINISTRACAO)
        self.client.login(username="edson", password=SENHA_TESTE)
        pagina = self.client.get(reverse("painel:painel"))
        self.assertContains(pagina, "<progress")
        self.assertContains(pagina, "Lendo as vendas")
        self.assertContains(pagina, "60%")


class AjudaTest(TestCase):
    def test_todas_as_telas_tem_o_botao_de_ajuda(self):
        usuario("edson", ADMINISTRACAO)
        self.client.login(username="edson", password=SENHA_TESTE)
        for nome in ["painel:geral", "painel:painel", "importacao:historico"]:
            pagina = self.client.get(reverse(nome))
            self.assertContains(pagina, 'id="abrir-ajuda"', msg_prefix=nome)
            self.assertContains(pagina, "js/ajuda.js", msg_prefix=nome)

    def test_painel_tem_passos_proprios_e_validos(self):
        import json

        usuario("edson", ADMINISTRACAO)
        self.client.login(username="edson", password=SENHA_TESTE)
        corpo = self.client.get(reverse("painel:painel")).content.decode()
        bruto = corpo.split('id="passos-ajuda">')[1].split("</script>")[0]
        passos = json.loads(bruto)
        self.assertGreaterEqual(len(passos), 5)
        for passo in passos:
            self.assertTrue(passo["titulo"])
            self.assertTrue(passo["texto"])


class LogDaImportacaoTest(TestCase):
    """O log é o que explica depois o que a importação fez, ou onde parou."""

    def test_falha_deixa_no_log_o_passo_e_o_erro(self):
        importacao = servicos.executar(arquivo="/nao/existe/DADOS-SET.FDB")
        linhas = importacao.linhas_do_log
        self.assertTrue(linhas, "a importação precisa gravar log mesmo falhando")
        self.assertIn("Importação iniciada", linhas[0])
        self.assertTrue(any("ERRO" in linha and "Não encontrei o arquivo" in linha for linha in linhas))
        self.assertTrue(any("importação anterior continuam valendo" in linha for linha in linhas))

    def test_cada_linha_do_log_tem_hora(self):
        importacao = servicos.executar(arquivo="/nao/existe/DADOS-SET.FDB")
        for linha in importacao.linhas_do_log:
            self.assertRegex(linha, r"^\[\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2}\] ")

    def test_log_registra_o_backup_escolhido_com_data_e_tamanho(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as pasta:
            origem = Path(pasta) / "DADOS-SET.FDB"
            origem.write_bytes(b"x" * 2048)
            importacao = servicos.executar(arquivo=str(origem))
        self.assertTrue(any("Backup escolhido" in linha and "MB" in linha
                            for linha in importacao.linhas_do_log))

    def test_sem_backup_novo_tambem_fica_registrado(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as pasta:
            origem = Path(pasta) / "DADOS-SET.FDB"
            origem.write_bytes(b"x" * 10)
            caminho = str(origem)
            momento = timezone.now()
            importacao_concluida(
                arquivo=caminho,
                arquivo_modificado_em=momento,
                arquivo_bytes=10,
                # Mesma versão do sistema: é isso que torna o backup igual "nada a fazer".
                versao_sistema=versao.atual().curta[:40],
            )
            Importacao.objects.filter(arquivo=caminho).update(
                arquivo_modificado_em=servicos.momento_do_arquivo(origem)
            )
            nova = servicos.executar(arquivo=caminho)
        self.assertEqual(nova.situacao, Importacao.Situacao.SEM_NOVIDADE)
        self.assertTrue(any("não mudou" in linha for linha in nova.linhas_do_log))

    def test_versao_nova_le_o_mesmo_backup_de_novo(self):
        """Senão a tela que a versão nova trouxe fica vazia até o SET gerar outro backup.

        Foi o que aconteceu em 08/10/2026: a 1.19.0 entrou no servidor, a importação
        logo depois viu o mesmo backup da noite anterior, pulou, e o menu Caixa abriu
        sem nenhum turno — a foto ainda era a que a 1.18.0 tinha tirado, e ela não tem
        caixa nenhum.
        """
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as pasta:
            origem = Path(pasta) / "DADOS-SET.FDB"
            origem.write_bytes(b"x" * 10)
            caminho = str(origem)
            importacao_concluida(
                arquivo=caminho,
                arquivo_modificado_em=timezone.now(),
                arquivo_bytes=10,
                versao_sistema="1.18.0",
            )
            Importacao.objects.filter(arquivo=caminho).update(
                arquivo_modificado_em=servicos.momento_do_arquivo(origem)
            )
            nova = servicos.executar(arquivo=caminho)
        # Não pulou: foi ler. (Para aqui porque o arquivo é falso, e tudo bem — o que o
        # teste trava é a decisão de reler, não a leitura.)
        self.assertNotEqual(nova.situacao, Importacao.Situacao.SEM_NOVIDADE)
        self.assertTrue(any("o sistema mudou da versão" in linha for linha in nova.linhas_do_log))

    def test_a_importacao_guarda_a_versao_que_a_gerou(self):
        importacao = servicos.executar(arquivo="/nao/existe/DADOS-SET.FDB")
        self.assertTrue(importacao.versao_sistema)

    def test_log_aparece_na_tela_de_importacoes(self):
        importacao = importacao_concluida()
        importacao.anotar("Lendo as vendas (60%)")
        importacao.save()
        usuario("fiscal", ADMINISTRATIVO)
        self.client.login(username="fiscal", password=SENHA_TESTE)
        pagina = self.client.get(reverse("importacao:historico"))
        self.assertContains(pagina, "Ver o log")
        self.assertContains(pagina, "Lendo as vendas")

    def test_log_pode_ser_baixado_em_texto(self):
        importacao = importacao_concluida()
        importacao.anotar("Lendo as compras (70%)")
        importacao.save()
        usuario("fiscal", ADMINISTRATIVO)
        self.client.login(username="fiscal", password=SENHA_TESTE)
        resposta = self.client.get(reverse("importacao:log", args=[importacao.pk]))
        self.assertEqual(resposta.status_code, 200)
        self.assertTrue(resposta["Content-Type"].startswith("text/plain"))
        self.assertIn("attachment", resposta["Content-Disposition"])
        corpo = resposta.content.decode("utf-8")
        self.assertIn("Lendo as compras", corpo)
        self.assertIn("Resultado: Concluída", corpo)

    def test_baixar_log_exige_permissao(self):
        importacao = importacao_concluida()
        usuario("operador")
        self.client.login(username="operador", password=SENHA_TESTE)
        self.assertEqual(
            self.client.get(reverse("importacao:log", args=[importacao.pk])).status_code, 403
        )

    def test_comando_automatico_repete_o_log_na_saida(self):
        import tempfile
        from io import StringIO
        from pathlib import Path

        with tempfile.TemporaryDirectory() as pasta:
            origem = Path(pasta) / "DADOS-SET.FDB"
            origem.write_bytes(b"x" * 10)
            saida = StringIO()
            with self.assertRaises(CommandError):
                call_command("importar_set", "--arquivo", str(origem), stdout=saida)
        self.assertIn("Importação iniciada", saida.getvalue())


class SincronizacaoDiariaTest(TestCase):
    """A sincronização automática passou a rodar três vezes por dia na 1.25.0.

    Pedido do Edson em 13/10/2026: 8:30, 12:30 e 19:30, ao lado do botão de importar na
    hora. A tela tem que dizer os horários que estão valendo de verdade, porque é por ela
    que alguém descobre por que os números são os de ontem.
    """

    def test_tela_diz_os_horarios_e_a_pasta_do_backup(self):
        importacao_concluida()
        usuario("fiscal", ADMINISTRATIVO)
        self.client.login(username="fiscal", password=SENHA_TESTE)
        with override_settings(
            IMPORTACAO_HORARIOS=["08:30", "12:30", "19:30"],
            IMPORTACAO_BACKUP_ORIGEM="C:\\backup-Set\\Studio\\Set-Studio",
        ):
            pagina = self.client.get(reverse("importacao:historico"))
        for hora in ("08:30", "12:30", "19:30"):
            self.assertContains(pagina, hora)
        self.assertContains(pagina, "Set-Studio")
        self.assertContains(pagina, "Sincronização automática")
        # Três sincronizações só adiantam se o SET gerar backup mais de uma vez por dia.
        self.assertContains(pagina, "o backup do SET precisa rodar mais de uma vez")

    def test_com_um_horario_so_a_tela_nao_fala_no_plural(self):
        importacao_concluida()
        usuario("fiscal_um", ADMINISTRATIVO)
        self.client.login(username="fiscal_um", password=SENHA_TESTE)
        with override_settings(IMPORTACAO_HORARIOS=["00:20"]):
            pagina = self.client.get(reverse("importacao:historico"))
        self.assertContains(pagina, "00:20")
        self.assertNotContains(pagina, "o backup do SET precisa rodar mais de uma vez")


class BackupCompactadoTest(TestCase):
    """O backup da Cabana é gerado em .zip, com o banco do SET dentro."""

    def zip_com(self, pasta, nomes):
        import zipfile

        from pathlib import Path as Caminho

        arquivo = Caminho(pasta) / "Set-Cabana-FULL.zip"
        with zipfile.ZipFile(arquivo, "w") as pacote:
            for nome, conteudo in nomes.items():
                pacote.writestr(nome, conteudo)
        return arquivo

    def test_le_o_banco_de_dentro_do_zip(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as pasta:
            origem = self.zip_com(pasta, {"backup/DADOS-SET.FDB": b"conteudo do banco",
                                          "leia-me.txt": b"x"})
            copia = preparar_copia(origem, Path(pasta) / "trabalho")
            self.assertEqual(copia.name, "set.fdb")
            self.assertEqual(copia.read_bytes(), b"conteudo do banco")

    def test_zip_sem_banco_dentro_explica_o_que_houve(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as pasta:
            origem = self.zip_com(pasta, {"relatorio.txt": b"nada aqui"})
            with self.assertRaisesMessage(ErroFonte, "não tem nenhum arquivo .FDB ou .FBK"):
                preparar_copia(origem, Path(pasta) / "trabalho")

    def test_zip_quebrado_avisa_que_pode_estar_incompleto(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as pasta:
            origem = Path(pasta) / "Set-Cabana-FULL.zip"
            origem.write_bytes(b"isto nao e um zip")
            with self.assertRaisesMessage(ErroFonte, "Não consegui abrir o backup compactado"):
                preparar_copia(origem, Path(pasta) / "trabalho")

    def test_pasta_com_zip_e_reconhecida_como_backup(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as pasta:
            origem = self.zip_com(pasta, {"DADOS-SET.FDB": b"banco"})
            self.assertEqual(servicos.localizar_backup(pasta), Path(origem))

    def test_importar_apontando_para_a_pasta(self):
        """A configuração e o --arquivo aceitam a pasta; vale o arquivo mais novo."""
        import tempfile

        with tempfile.TemporaryDirectory() as pasta:
            self.zip_com(pasta, {"relatorio.txt": b"sem banco"})
            importacao = servicos.executar(arquivo=pasta)
        self.assertEqual(importacao.situacao, Importacao.Situacao.FALHOU)
        self.assertIn("não tem nenhum arquivo", importacao.mensagem)

    def test_pasta_vazia_diz_que_nao_achou_backup(self):
        import tempfile

        with tempfile.TemporaryDirectory() as pasta:
            importacao = servicos.executar(arquivo=pasta)
        self.assertIn("Não encontrei nenhum backup", importacao.mensagem)


class MotorFirebirdTest(TestCase):
    """O motor Firebird tem que ter os mesmos bits do programa que lê o banco.

    O Firebird que acompanha o SET costuma ser de 32 bits. Carregado dentro do Python de
    64 bits do sistema, o Windows recusa com "[WinError 193] %1 não é um aplicativo Win32
    válido" e a importação não começa. Era o erro que aparecia no painel em 06/10/2026.
    """

    def dll_falsa(self, pasta, maquina):
        """Escreve um arquivo com só o cabeçalho PE, que é o que a conferência lê."""
        import struct
        from pathlib import Path

        caminho = Path(pasta) / "fbclient.dll"
        cabecalho = bytearray(b"\0" * 0x100)
        cabecalho[0:2] = b"MZ"
        struct.pack_into("<I", cabecalho, 0x3C, 0x80)
        cabecalho[0x80:0x84] = b"PE\0\0"
        struct.pack_into("<H", cabecalho, 0x84, maquina)
        caminho.write_bytes(bytes(cabecalho))
        return caminho

    def test_reconhece_64_e_32_bits(self):
        import tempfile

        from apps.importacao.fontes import firebird

        with tempfile.TemporaryDirectory() as pasta:
            self.assertEqual(firebird._arquitetura_do_pe(self.dll_falsa(pasta, 0x8664)), "64 bits")
            self.assertEqual(firebird._arquitetura_do_pe(self.dll_falsa(pasta, 0x014C)), "32 bits")

    def test_arquivo_que_nao_e_programa_nao_atrapalha(self):
        """Sem conseguir ler a arquitetura, a conferência não barra nada."""
        import tempfile

        from apps.importacao.fontes import firebird

        from pathlib import Path

        with tempfile.TemporaryDirectory() as pasta:
            qualquer = Path(pasta) / "fbclient.dll"
            qualquer.write_bytes(b"nao sou um programa")
            self.assertIsNone(firebird._arquitetura_do_pe(qualquer))
            firebird._conferir_arquitetura(qualquer)

    def test_motor_de_32_bits_explica_em_vez_de_dar_winerror(self):
        import tempfile

        from apps.importacao.fontes import firebird

        with tempfile.TemporaryDirectory() as pasta:
            with self.assertRaises(ErroFonte) as erro:
                firebird._conferir_arquitetura(self.dll_falsa(pasta, 0x014C))
        self.assertIn("32 bits", str(erro.exception))
        self.assertIn("atualização", str(erro.exception))

    def test_motor_certo_passa(self):
        import sys
        import tempfile

        from apps.importacao.fontes import firebird

        maquina = 0x8664 if sys.maxsize > 2**32 else 0x014C
        with tempfile.TemporaryDirectory() as pasta:
            firebird._conferir_arquitetura(self.dll_falsa(pasta, maquina))

    def test_painel_explica_o_winerror_193(self):
        from apps.importacao import diagnostico

        explicacao = diagnostico.explicar(
            "Não consegui abrir a cópia do banco: [WinError 193] %1 não é um aplicativo Win32 válido"
        )
        self.assertTrue(explicacao.conhecido)
        self.assertIn("32 bits", explicacao.o_que_aconteceu)
        self.assertIn("atualizar.ps1", " ".join(explicacao.como_resolver))


class CodificacaoDoSetTest(TestCase):
    """Um caractere estranho num produto não pode derrubar a importação inteira.

    Em 06/10/2026 a leitura parou com "'charmap' codec can't decode byte 0x81": o SET
    grava em cp1252 e havia um byte que não existe nessa tabela.
    """

    def decodificar(self, dados):
        from apps.importacao.fontes import firebird

        firebird._descartados["bytes"] = 0
        return dados.decode(firebird.CODIFICACAO_SET), firebird._descartados["bytes"]

    def test_acentos_continuam_certos(self):
        texto, descartados = self.decodificar("TAÇA MÉDIA".encode("cp1252"))
        self.assertEqual(texto, "TAÇA MÉDIA")
        self.assertEqual(descartados, 0)

    def test_byte_fora_da_tabela_e_descartado_e_contado(self):
        texto, descartados = self.decodificar(b"CADEIRA A\x81\xc7\xc3O")
        self.assertEqual(texto, "CADEIRA AÇÃO")
        self.assertEqual(descartados, 1)

    def test_aspas_do_windows_continuam_legiveis(self):
        texto, _ = self.decodificar("peça “especial”".encode("cp1252"))
        self.assertEqual(texto, "peça “especial”")

    def test_escrever_parametro_de_consulta_funciona(self):
        from apps.importacao.fontes import firebird

        self.assertEqual("Pendente".encode(firebird.CODIFICACAO_SET), b"Pendente")

    def test_texto_gravado_em_utf8_tambem_vem_certo(self):
        """No servidor da loja o cadastro de clientes veio em UTF-8 e virava "SÃ£o Paulo"."""
        texto, descartados = self.decodificar("São Paulo".encode("utf-8"))
        self.assertEqual(texto, "São Paulo")
        self.assertEqual(descartados, 0)

    def test_utf8_e_cp1252_convivem_na_mesma_leitura(self):
        self.assertEqual(self.decodificar("Belém".encode("utf-8"))[0], "Belém")
        self.assertEqual(self.decodificar("Belém".encode("cp1252"))[0], "Belém")
        self.assertEqual(self.decodificar("CONGREGAÇÃO".encode("cp1252"))[0], "CONGREGAÇÃO")


class TestVendaImportadaNaoGuardaDadoPessoal(TestCase):
    """Venda a venda entrou para o ticket médio, e só com o que o ticket precisa.

    A tabela VENDAS do SET tem NOMECLI, COMPRADOR e COMPRADOR_CPF. Nada disso é
    lido: a mesma regra dos clientes vale aqui. Este teste falha se alguém
    acrescentar um desses campos ao modelo.
    """

    def test_o_modelo_nao_tem_campo_de_cliente_nem_de_documento(self):
        from apps.importacao.models import VendaImportada

        campos = {campo.name for campo in VendaImportada._meta.get_fields()}
        for proibido in ("cliente", "nome_cliente", "comprador", "cpf", "cnpj",
                         "documento", "endereco", "telefone"):
            self.assertNotIn(proibido, campos)

    def test_a_consulta_do_set_nao_pede_coluna_de_cliente(self):
        """Olha o SELECT, e não o comentário: o comentário cita as colunas justamente
        para dizer que elas não são lidas."""
        import inspect
        import re

        from apps.importacao.fontes import firebird

        codigo = inspect.getsource(firebird._ler_vendas)
        selects = " ".join(re.findall(r"select\b.*?from\b.*?(?=\"\"\")", codigo,
                                      re.IGNORECASE | re.DOTALL)).upper()
        self.assertIn("V.TOTALVENDA", selects)  # o teste está olhando a consulta certa
        # CLIFORNE (ICAIXA) e OBSERVACAO (FATVENDAS), lidas desde a 1.46.0 pelas tabelas
        # vizinhas, também podem ter nome de cliente.
        for proibida in ("NOMECLI", "COMPRADOR", "IDCLIENTE", "CLIFORNE", "OBSERVACAO"):
            self.assertNotIn(proibida, selects)


class VendaMesAMesTest(TestCase):
    """A foto diz desde quando guarda venda mês a mês, e começa numa virada de mês.

    Até a 1.29.0 a leitura começava em "corte menos 730 dias", que cai no meio de um mês:
    o mês mais antigo da foto era um pedaço, e comparar doze meses com os doze anteriores
    usava esse pedaço como mês inteiro. Desde a 1.30.0 começa no dia 1º, são cinco anos, e
    a foto guarda a data para quem lê não precisar adivinhar.
    """

    def test_a_leitura_comeca_no_dia_primeiro(self):
        from datetime import date

        from apps.importacao.fontes.firebird import _primeiro_dia_de_meses_atras
        self.assertEqual(_primeiro_dia_de_meses_atras(date(2026, 10, 14), 61),
                         date(2021, 9, 1))
        self.assertEqual(_primeiro_dia_de_meses_atras(date(2026, 1, 31), 1),
                         date(2025, 12, 1))
        self.assertEqual(_primeiro_dia_de_meses_atras(date(2026, 3, 1), 12),
                         date(2025, 3, 1))

    def test_sao_cinco_anos_de_historico(self):
        """61 meses: a comparação despreza o mais antigo, e sobram 60 — cinco anos."""
        from apps.importacao.fontes.firebird import JANELA_COMPARACAO_MESES
        self.assertEqual(JANELA_COMPARACAO_MESES, 61)


class DepoisDaFotoGravadaNadaPodeApagarEla(TestCase):
    """Importação boa não pode virar loja sem dados por causa de um passo de arrumação.

    Achado na revisão geral de 15/10/2026. Depois do commit da foto, a execução seguia
    DENTRO do mesmo `try` para escrever a auditoria e podar as fotos antigas — e o
    `except` desse `try` apaga a foto e marca FALHOU. Um tempo esgotado na poda, que é um
    DELETE em massa sobre oito tabelas, apagava a foto que acabara de ser gravada; e,
    como a poda já havia tirado as anteriores, a loja ficava sem dado nenhum.
    """

    def _extracao(self):
        from apps.importacao.fontes.firebird import Extracao

        hoje = timezone.localdate()
        return Extracao(
            data_corte=hoje - timedelta(days=1),
            dias_abertos_12m=300,
            dias_abertos_90d=78,
            produtos=[{"codigo": "1", "descricao": "CARVAO 10KG", "custo": Decimal("10"),
                       "estoque": Decimal("60"), "vendas_12m": Decimal("40"),
                       "compras_12m": Decimal("100"), "receita_12m": Decimal("1200")}],
            detalhe={"vendas_mes": [[hoje.year, hoje.month, 90000.0, 380]], "compras_mes": []},
        )

    def _importar(self, **quebrar):
        """Roda uma importação boa, podendo quebrar de propósito um passo do fim.

        O Firebird é trocado por um dublê: o que estes testes travam é o fim da
        importação, não a leitura do banco, que tem testes próprios.
        """
        import tempfile
        from contextlib import ExitStack
        from pathlib import Path
        from unittest import mock

        with tempfile.TemporaryDirectory() as pasta, ExitStack() as pilha:
            caminho = Path(pasta) / "DADOS-SET.FDB"
            caminho.write_bytes(b"x" * 4096)
            pilha.enter_context(mock.patch("apps.importacao.fontes.firebird.preparar_copia",
                                           return_value=caminho))
            pilha.enter_context(mock.patch("apps.importacao.fontes.firebird.extrair",
                                           return_value=self._extracao()))
            for alvo, erro in quebrar.items():
                pilha.enter_context(mock.patch(f"apps.importacao.servicos.{alvo}",
                                               side_effect=erro))
            return servicos.executar(arquivo=str(caminho))

    def test_falha_na_poda_das_fotos_antigas_nao_derruba_a_importacao(self):
        with self.assertLogs("apps.importacao.servicos", level="ERROR"):
            importacao = self._importar(limpar_antigas=RuntimeError("tempo esgotado no DELETE"))
        self.assertEqual(importacao.situacao, Importacao.Situacao.CONCLUIDA)
        self.assertEqual(ProdutoImportado.objects.filter(importacao=importacao).count(), 1,
                         "a foto gravada e commitada não pode ser apagada depois")
        self.assertEqual(servicos.ultima_concluida(), importacao)

    def test_falha_ao_escrever_a_auditoria_nao_derruba_a_importacao(self):
        with self.assertLogs("apps.importacao.servicos", level="ERROR"):
            importacao = self._importar(registrar=RuntimeError("auditoria fora do ar"))
        self.assertEqual(importacao.situacao, Importacao.Situacao.CONCLUIDA)
        self.assertEqual(ProdutoImportado.objects.filter(importacao=importacao).count(), 1)

    def test_quando_tudo_vai_bem_a_auditoria_e_a_poda_acontecem(self):
        """A régua: as duas coisas continuam sendo feitas, só não derrubam mais nada."""
        antiga = importacao_concluida(dias_atras=30)
        ProdutoImportado.objects.create(importacao=antiga, codigo="velho", estoque=Decimal("1"))
        with override_settings(IMPORTACAO_MANTER=1):
            importacao = self._importar()
        self.assertEqual(importacao.situacao, Importacao.Situacao.CONCLUIDA)
        self.assertTrue(EventoAuditoria.objects.filter(acao="importacao.concluida").exists())
        self.assertFalse(ProdutoImportado.objects.filter(importacao=antiga).exists(),
                         "a poda das fotos antigas continua rodando")

    def test_o_desfazer_da_falha_nao_deixa_sobra_de_outras_tabelas(self):
        """O `except` apagava produtos, contas, clientes e caixas, e esquecia o resto.

        Compras, vendas, fichas de fornecedor e a venda mês a mês ficavam penduradas numa
        importação marcada como FALHOU, esperando a próxima poda.
        """
        from apps.importacao.models import CompraImportada, VendaImportada

        falhada = importacao_concluida(situacao=Importacao.Situacao.EM_ANDAMENTO)
        ProdutoImportado.objects.create(importacao=falhada, codigo="1", estoque=Decimal("1"))
        CompraImportada.objects.create(
            importacao=falhada, id_set=1, numero="1", data_nota=timezone.localdate(),
            fornecedor="GERMAN", valor_total=Decimal("10"))
        VendaImportada.objects.create(
            importacao=falhada, id_set=1, numero="1", data=timezone.localdate(),
            dia_da_semana=1, valor=Decimal("10"))

        servicos._apagar_a_foto(falhada)

        self.assertFalse(ProdutoImportado.objects.filter(importacao=falhada).exists())
        self.assertFalse(CompraImportada.objects.filter(importacao=falhada).exists())
        self.assertFalse(VendaImportada.objects.filter(importacao=falhada).exists())
