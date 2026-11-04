"""Os .ps1 do servidor não podem chegar à loja com bloco aberto ou aspas sem par.

Desta máquina não se roda o PowerShell (baixar o pwsh foi barrado em 04/11/2026), e um erro
de digitação num .ps1 só aparece na loja, na hora de atualizar: o atualizar.ps1 é o que
traz a versão seguinte, então um atualizador quebrado prende o servidor na versão em que
está. A conferência daqui é grosseira de propósito: chaves, parênteses, colchetes, aspas e
subexpressões $( ), sabendo o que é comentário e o que é texto no PowerShell. Não substitui
o parser; pega o erro mais comum de uma edição. Todas as versões que já rodaram na loja
passam nela.

E todo .ps1 começa com a marca de UTF-8 (BOM): sem ela, o PowerShell 5.1 do Windows lê o
arquivo como ANSI, e cada "não", "versão" e "você" das mensagens sai torto na tela.
"""

from pathlib import Path

from django.test import SimpleTestCase

PASTA = Path(__file__).resolve().parents[3] / "implantacao"
PARES = {"(": ")", "{": "}", "[": "]"}


def problemas(texto):
    """O que estiver aberto sem fechar, ou fechado sem abrir, com a linha onde começou."""
    achados = []
    n = len(texto)

    def dupla(i, linha):
        comeco = linha
        while i < n:
            c = texto[i]
            if c == "\n":
                linha += 1
            if c == "`":  # escape dentro de aspas duplas
                i += 2
                continue
            if c == '"':
                if texto.startswith('""', i):
                    i += 2
                    continue
                return i + 1, linha
            if texto.startswith("$(", i):
                i, linha = codigo(i + 2, linha, fecha=")")
                continue
            i += 1
        achados.append(f"aspas duplas abertas na linha {comeco}")
        return i, linha

    def simples(i, linha):
        comeco = linha
        while i < n:
            c = texto[i]
            if c == "\n":
                linha += 1
            if c == "'":
                if texto.startswith("''", i):
                    i += 2
                    continue
                return i + 1, linha
            i += 1
        achados.append(f"aspas simples abertas na linha {comeco}")
        return i, linha

    def codigo(i, linha, fecha=None):
        abertos = []
        while i < n:
            c = texto[i]
            if c == "\n":
                linha += 1
                i += 1
            elif texto.startswith("<#", i):
                fim = texto.find("#>", i + 2)
                if fim < 0:
                    achados.append(f"comentário <# aberto na linha {linha}")
                    return n, linha
                linha += texto.count("\n", i, fim)
                i = fim + 2
            elif c == "#" and (i == 0 or texto[i - 1] in " \t\n;({|"):
                fim = texto.find("\n", i)
                i = n if fim < 0 else fim
            elif c == "`":  # continuação de linha ou caractere escapado
                if texto.startswith("`\n", i):
                    linha += 1
                i += 2
            elif c == '"':
                i, linha = dupla(i + 1, linha)
            elif c == "'":
                i, linha = simples(i + 1, linha)
            elif c in PARES:
                abertos.append((c, linha))
                i += 1
            elif c in ")}]":
                if abertos:
                    aberto, onde = abertos.pop()
                    if PARES[aberto] != c:
                        achados.append(f"'{aberto}' da linha {onde} fechado com '{c}' na linha {linha}")
                elif fecha == c:
                    return i + 1, linha
                else:
                    achados.append(f"'{c}' sobrando na linha {linha}")
                i += 1
            else:
                i += 1
        achados.extend(f"'{aberto}' aberto na linha {onde} sem fechar" for aberto, onde in abertos)
        if fecha:
            achados.append(f"subexpressão $( sem o '{fecha}'")
        return i, linha

    codigo(0, 1)
    return achados


class OsScriptsDoServidorTest(SimpleTestCase):
    def setUp(self):
        self.scripts = sorted(PASTA.glob("*.ps1"))
        if not self.scripts:  # o pacote instalado no servidor não leva implantacao/
            self.skipTest("os .ps1 só existem no repositório")

    def test_nenhum_script_tem_bloco_ou_aspas_sem_par(self):
        for script in self.scripts:
            with self.subTest(script=script.name):
                texto = script.read_text(encoding="utf-8-sig").replace("\r\n", "\n")
                self.assertEqual(problemas(texto), [])

    def test_todo_script_comeca_com_a_marca_de_utf8(self):
        for script in self.scripts:
            with self.subTest(script=script.name):
                self.assertTrue(script.read_bytes().startswith(b"\xef\xbb\xbf"))

    def test_os_que_vao_no_pacote_estao_todos_aqui(self):
        """O montar-pacote.sh copia uma lista fixa; script novo fora dela não chega à loja."""
        lista = (PASTA / "montar-pacote.sh").read_text(encoding="utf-8")
        for script in self.scripts:
            with self.subTest(script=script.name):
                self.assertIn(f"/implantacao/{script.name}", lista)


class AConferenciaPegaOErroTest(SimpleTestCase):
    """A conferência só vale se pegar o erro: cada caso aqui é uma edição que quebraria."""

    def test_bloco_sem_fechar(self):
        self.assertTrue(problemas("if ($a) {\n    Write-Host 'oi'\n"))

    def test_aspas_sem_par(self):
        self.assertTrue(problemas('Write-Host "PAREI: sem fechar\nexit 1\n'))

    def test_subexpressao_cortada(self):
        self.assertTrue(problemas('Write-Host "Pacote: $($novo.Name (versão)"\n'))

    def test_fechou_com_o_par_errado(self):
        self.assertTrue(problemas("foreach ($z in $zips) { Move-Item $z ) }\n"))

    def test_o_que_e_texto_e_comentario_nao_conta(self):
        texto = (
            "<# bloco { aberto ( no comentário #>\n"
            "# linha { de comentário\n"
            "Write-Host 'chave { dentro de aspas simples, e uma aspa '' escapada'\n"
            'Write-Host "e dentro de duplas: { ( `" $($a.Nome) ${b}"\n'
            "$x = @{ Chave = 'valor' }; $y = @(1, 2)[0]\n"
        )
        self.assertEqual(problemas(texto), [])
