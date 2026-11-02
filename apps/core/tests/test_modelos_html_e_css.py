"""Conferências de modelo e de estilo que já falharam uma vez.

Nenhuma delas abre navegador: são leituras dos arquivos, baratas e rodam no servidor.
"""

import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase


def _modelos():
    return sorted(Path(settings.BASE_DIR, "templates").rglob("*.html"))


class ComentariosDeModelo(SimpleTestCase):
    def test_nenhum_comentario_fica_aberto_na_linha(self):
        """{# #} do Django só vale em UMA linha.

        Aberto em uma linha e fechado na seguinte, o Django não remove nada e o comentário
        aparece escrito na tela do usuário. Já aconteceu no topo do sistema.
        """
        abertos = [
            f"{caminho.relative_to(settings.BASE_DIR)}:{numero}"
            for caminho in _modelos()
            for numero, linha in enumerate(caminho.read_text(encoding="utf-8").splitlines(), 1)
            if linha.count("{#") != linha.count("#}")
        ]
        self.assertEqual(abertos, [], "comentário {# #} aberto numa linha e fechado em outra")

    def test_nenhuma_tag_do_django_fica_partida_em_duas_linhas(self):
        """`{% %}` e `{{ }}` também só valem em UMA linha, e falham em silêncio.

        O Django acha tag com uma expressão que NÃO atravessa fim de linha. Quebrar um
        `{% if %}` comprido em duas linhas para caber na régua de 100 colunas não dá erro
        nenhum: o Django não reconhece a tag, e o usuário lê o código-fonte escrito na
        tela. Aconteceu na lista de compra em 14/10/2026, com um `{% if %}{% elif %}` da
        linha de movimento do estoque — a tela mostrou "o estoque caiu 12{% elif ... %}".

        Contar abre e fecha por linha acha os dois casos. Tag comprida se encurta com
        variável no `with` ou com a conta feita no Python, nunca com quebra de linha.
        """
        partidas = [
            f"{caminho.relative_to(settings.BASE_DIR)}:{numero}"
            for caminho in _modelos()
            for numero, linha in enumerate(caminho.read_text(encoding="utf-8").splitlines(), 1)
            for abre, fecha in (("{%", "%}"), ("{{", "}}"))
            if linha.count(abre) != linha.count(fecha)
        ]
        self.assertEqual(partidas, [], "tag do Django aberta numa linha e fechada em outra")


class CaixasQueEscondem(SimpleTestCase):
    """Quem declara display precisa devolver o hidden, senão a caixa nunca fecha."""

    def test_caixas_com_display_proprio_tratam_o_hidden(self):
        css = Path(settings.BASE_DIR, "static", "css", "sistema.css").read_text(encoding="utf-8")
        modelos = "\n".join(caminho.read_text(encoding="utf-8") for caminho in _modelos())
        for classe in ("lembretes", "ajuda-caixa"):
            if f'class="{classe}"' not in modelos and f'class="{classe} ' not in modelos:
                continue
            bloco = css.split(f".{classe} {{", 1)
            if len(bloco) == 1 or "display:" not in bloco[1].split("}", 1)[0]:
                continue
            self.assertIn(
                f".{classe}[hidden]",
                css,
                f".{classe} declara display, então precisa de .{classe}[hidden] "
                "para o atributo hidden voltar a esconder a caixa",
            )


class CartaoNoCelular(SimpleTestCase):
    """A tabela que vira cartão no visor estreito, e as duas formas de ela continuar errada.

    O cartão existe para a coluna que DECIDE não ficar fora do visor atrás de uma rolagem
    lateral que ninguém descobre. Já falhou duas vezes por motivos diferentes, e os dois
    só aparecem quando o conteúdo cresce — por isso viraram teste.
    """

    def _css(self):
        return Path(settings.BASE_DIR, "static", "css", "sistema.css").read_text(encoding="utf-8")

    def test_o_cartao_desliga_a_rolagem_nos_dois_eixos(self):
        """`overflow-x: visible` sozinho volta a computar como `auto`.

        Estes quadros também são `.tabela-dez`, que tem `overflow-y: auto`, e pelo CSS
        "visível de um lado e recortado do outro" não existe. Com o eixo X sozinho a
        rolagem lateral continuava lá, escondida enquanto o conteúdo coubesse.
        """
        css = self._css()
        inicio = css.index(".tabela-em-cartao {")
        # Sem os comentários: o porquê da regra cita o defeito pelo nome.
        bloco = re.sub(r"/\*.*?\*/", "", css[inicio:css.index("}", inicio)], flags=re.S)
        self.assertIn("overflow: visible", bloco)
        self.assertNotIn("overflow-x:", bloco)

    def test_a_frase_dentro_de_celula_de_numero_quebra_linha(self):
        """`td.numerico` é `nowrap` por causa dos números; a linha de detalhe é frase.

        A explicação da estação ("de 36 para 35: no ano passado...") mora na célula da
        quantidade e herdava o `nowrap`: saía numa linha só, esticava a tabela para 557 px
        num visor de 390 e era cortada.
        """
        css = self._css()
        regra = next(linha for linha in css.splitlines()
                     if linha.startswith(".tabela-compra .linha-detalhe {"))
        self.assertIn("white-space: normal", regra)


def _regras_soltas(css):
    """Cada classe definida sozinha (`.nome {`) fora de @media, com as linhas onde aparece.

    Os comentários viram linhas em branco, e não somem, para o número da linha continuar o
    do arquivo: é ele que o teste mostra quando falha.
    """
    sem_comentario = re.sub(r"/\*.*?\*/", lambda achado: "\n" * achado.group().count("\n"),
                            css, flags=re.S)
    onde = {}
    profundidade, inicio = 0, 0
    for posicao, letra in enumerate(sem_comentario):
        if letra == "{":
            seletor = sem_comentario[inicio:posicao].strip()
            if profundidade == 0 and not seletor.startswith("@"):
                linha = sem_comentario.count("\n", 0, posicao) + 1
                for parte in seletor.split(","):
                    parte = parte.strip()
                    if re.fullmatch(r"\.[\w-]+", parte):
                        onde.setdefault(parte, []).append(linha)
            profundidade += 1
            inicio = posicao + 1
        elif letra == "}":
            profundidade = max(profundidade - 1, 0)
            inicio = posicao + 1
        elif letra == ";":
            inicio = posicao + 1
    return onde


class MesmaClasseEmDoisCantos(SimpleTestCase):
    """A mesma classe definida duas vezes, longe uma da outra, é outra tela sendo mudada.

    Na 1.44.0 a etiqueta "dinheiro" da área de acessos ganhou a classe `.marca` — o nome
    que o bloco do logotipo, no topo de TODAS as telas, já usava. A regra de baixo venceu
    a de cima, e o logotipo apareceu com borda branca, em caixa alta e empilhado; o Edson
    viu no dia da instalação (02/11/2026). Na mesma versão, `.formulario-em-linha` ganhou
    uma segunda definição para o botão "Trazer de volta" e mexeu no botão de gerar o
    pedido da Lista de compra. Nenhum teste viu, porque cada tela, sozinha, estava certa.

    Repetir a classe perto da primeira é legítimo (um grupo de regras e um ajuste logo
    abaixo). O defeito é o outro canto do arquivo, onde quem escreve não vê a primeira.
    """

    DISTANCIA = 40

    def test_classe_solta_nao_e_definida_de_novo_longe_da_primeira(self):
        css = Path(settings.BASE_DIR, "static", "css", "sistema.css").read_text(encoding="utf-8")
        repetidas = [
            f"{classe} nas linhas {', '.join(map(str, linhas))}"
            for classe, linhas in sorted(_regras_soltas(css).items())
            if max(linhas) - min(linhas) > self.DISTANCIA
        ]
        self.assertEqual(repetidas, [], "a mesma classe definida em dois cantos do sistema.css: "
                                        "dê um nome novo, ou ponha o recipiente antes dela")

    def test_a_conferencia_acha_o_caso_da_1_44_0(self):
        """O próprio defeito, recolocado num texto de mentira, tem que ser achado."""
        css = (".marca { display: flex; }\n" + "\n" * 60
               + "@media (max-width: 40rem) { .marca { gap: 0; } }\n"
               + "/* comentário\ncom .marca { dentro } */\n"
               + ".marca { border: 1px solid; }\n")
        linhas = _regras_soltas(css)[".marca"]
        self.assertEqual(linhas, [1, 65])
