"""Leitura da planilha de diagnóstico (CSV ou XLSX) e escrita do relatório.

Formato de entrada: uma linha por produto, montada a partir dos relatórios
exportados do SET (ver docs/diagnostico-de-compras.md). O arquivo é dado, nunca
instrução: fórmulas e macros não são executadas (openpyxl lê só valores) e o
relatório de saída neutraliza textos que começariam uma fórmula.
"""

import csv
import io
import unicodedata
from decimal import Decimal, InvalidOperation
from pathlib import Path

from .calculos import ZERO, Item

LIMITE_LINHAS = 50_000
LIMITE_BYTES = 20 * 1024 * 1024

# Nome canônico -> nomes aceitos no cabeçalho (comparados sem acento, minúsculos).
COLUNAS = {
    "sku": ["sku", "codigo", "cod", "codigo produto", "referencia"],
    "descricao": ["descricao", "produto", "nome"],
    "estoque_atual": ["estoque atual", "estoque", "saldo", "quantidade em estoque"],
    "custo_unitario": ["custo unitario", "custo", "preco de custo"],
    "vendas_qtd": ["vendas qtd", "quantidade vendida", "vendas", "qtd vendida"],
    "devolucoes_qtd": ["devolucoes qtd", "devolucoes", "qtd devolvida"],
    "comprado_qtd": ["comprado qtd", "quantidade comprada", "compras", "qtd comprada"],
    "prazo_reposicao_dias": ["prazo reposicao dias", "prazo de reposicao", "prazo", "prazo entrega"],
    "lote_minimo": ["lote minimo"],
    "multiplo": ["multiplo", "multiplo de compra"],
    "dias_sem_estoque": ["dias sem estoque", "dias em ruptura"],
    "pedidos_pendentes": ["pedidos pendentes", "a receber"],
}
OBRIGATORIAS = ["sku", "descricao", "estoque_atual", "vendas_qtd"]


class ErroPlanilha(Exception):
    pass


def _normalizar(texto):
    texto = unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode()
    return " ".join(texto.lower().replace("_", " ").replace("(", " ").replace(")", " ").split())


def numero(valor, *, inteiro=False):
    """Converte número em formato brasileiro ("1.234,56") ou já numérico. Vazio vira None."""
    if valor is None:
        return None
    if isinstance(valor, (int, float, Decimal)) and not isinstance(valor, bool):
        resultado = Decimal(str(valor))
    else:
        texto = str(valor).strip().replace("R$", "").replace(" ", "")
        if not texto or texto == "-":
            return None
        if "," in texto:
            texto = texto.replace(".", "").replace(",", ".")
        try:
            resultado = Decimal(texto)
        except InvalidOperation as erro:
            raise ValueError(f"“{valor}” não é um número") from erro
    if not resultado.is_finite():
        raise ValueError(f"“{valor}” não é um número")
    if inteiro:
        if resultado != resultado.to_integral_value():
            raise ValueError(f"“{valor}” precisa ser um número inteiro")
        return int(resultado)
    return resultado


def _linhas_csv(conteudo: bytes):
    for codificacao in ("utf-8-sig", "cp1252"):
        try:
            texto = conteudo.decode(codificacao)
            break
        except UnicodeDecodeError:
            continue
    amostra = texto[:4096]
    delimitador = ";" if amostra.count(";") >= amostra.count(",") else ","
    return list(csv.reader(io.StringIO(texto), delimiter=delimitador))


def _linhas_xlsx(conteudo: bytes):
    from openpyxl import load_workbook

    livro = load_workbook(io.BytesIO(conteudo), read_only=True, data_only=True)
    try:
        planilha = livro.worksheets[0]
        return [list(linha) for linha in planilha.iter_rows(values_only=True)]
    finally:
        livro.close()


def ler(caminho):
    """Lê o arquivo e devolve (itens válidos, erros por linha). Não grava nada."""
    caminho = Path(caminho)
    conteudo = caminho.read_bytes()
    if len(conteudo) > LIMITE_BYTES:
        raise ErroPlanilha("Arquivo maior que 20 MB.")
    extensao = caminho.suffix.lower()
    if extensao == ".xlsx":
        if not conteudo.startswith(b"PK\x03\x04"):
            raise ErroPlanilha("O arquivo não é um XLSX válido.")
        linhas = _linhas_xlsx(conteudo)
    elif extensao in (".csv", ".txt"):
        linhas = _linhas_csv(conteudo)
    else:
        raise ErroPlanilha("Envie a planilha em CSV ou XLSX.")
    linhas = [linha for linha in linhas if any(c not in (None, "") for c in linha)]
    if not linhas:
        raise ErroPlanilha("A planilha está vazia.")
    if len(linhas) - 1 > LIMITE_LINHAS:
        raise ErroPlanilha(f"A planilha passa de {LIMITE_LINHAS} linhas.")

    cabecalho = [_normalizar(c) for c in linhas[0]]
    indice = {}
    for nome, apelidos in COLUNAS.items():
        for posicao, titulo in enumerate(cabecalho):
            if titulo in apelidos:
                indice[nome] = posicao
                break
    faltando = [c for c in OBRIGATORIAS if c not in indice]
    if faltando:
        raise ErroPlanilha("Colunas obrigatórias não encontradas: " + ", ".join(faltando) + ".")

    itens, erros, vistos = [], [], {}
    for numero_linha, linha in enumerate(linhas[1:], start=2):
        def campo(nome):
            pos = indice.get(nome)
            return linha[pos] if pos is not None and pos < len(linha) else None

        try:
            sku = str(campo("sku") or "").strip()
            if not sku:
                raise ValueError("SKU vazio")
            if sku in vistos:
                raise ValueError(f"SKU repetido (já aparece na linha {vistos[sku]})")
            estoque = numero(campo("estoque_atual"))
            vendas = numero(campo("vendas_qtd"))
            if estoque is None or vendas is None:
                raise ValueError("estoque atual e vendas são obrigatórios")
            if vendas < 0:
                raise ValueError("vendas negativas")
            devolucoes = numero(campo("devolucoes_qtd")) or ZERO
            custo = numero(campo("custo_unitario"))
            if custo is not None and custo < 0:
                raise ValueError("custo negativo")
            prazo = numero(campo("prazo_reposicao_dias"), inteiro=True)
            if prazo is not None and not 0 <= prazo <= 365:
                raise ValueError("prazo de reposição fora de 0 a 365 dias")
            multiplo = numero(campo("multiplo")) or Decimal("1")
            if multiplo <= 0:
                raise ValueError("múltiplo de compra precisa ser maior que zero")
            item = Item(
                sku=sku,
                descricao=str(campo("descricao") or "").strip()[:200],
                estoque_utilizavel=max(estoque, ZERO),
                vendas_liquidas=max(vendas - devolucoes, ZERO),
                dias_janela=1,  # substituído pelo período informado no comando
                prazo_reposicao_dias=prazo,
                custo_unitario=custo,
                recebimentos_pendentes=numero(campo("pedidos_pendentes")) or ZERO,
                lote_minimo=numero(campo("lote_minimo")) or ZERO,
                multiplo=multiplo,
                dias_em_ruptura=numero(campo("dias_sem_estoque"), inteiro=True) or 0,
                comprado_na_janela=numero(campo("comprado_qtd")) or ZERO,
            )
        except ValueError as erro:
            erros.append((numero_linha, str(erro)))
            continue
        vistos[sku] = numero_linha
        if estoque < 0:
            erros.append((numero_linha, f"aviso: estoque negativo ({estoque}) no SET; tratado como zero"))
        itens.append(item)
    return itens, erros


def _seguro(valor):
    """Evita que um texto vire fórmula ao abrir o relatório no Excel."""
    texto = "" if valor is None else str(valor)
    return "'" + texto if texto[:1] in ("=", "+", "-", "@", "\t", "\r") else texto


def _br(valor):
    if valor is None:
        return "não informado"
    return f"{valor:.2f}".replace(".", ",")


CABECALHO_SAIDA = [
    "SKU", "Descrição", "Situação", "Venda por dia", "Cobertura", "Estoque", "Ponto de reposição",
    "Estoque alvo", "Compra sugerida", "Custo da compra (R$)", "Valor em estoque (R$)",
    "Unidades em excesso", "Valor em excesso (R$)", "Comprado acima do necessário (un.)",
    "Valor comprado acima (R$)", "Confiança", "Motivo", "Avisos",
]


def escrever_relatorio(resultados, destino):
    with open(destino, "w", newline="", encoding="utf-8-sig") as arquivo:
        escritor = csv.writer(arquivo, delimiter=";")
        escritor.writerow(CABECALHO_SAIDA)
        for r in resultados:
            escritor.writerow([
                _seguro(r.sku), _seguro(r.descricao), r.situacao, _br(r.demanda_diaria), r.cobertura_texto,
                _br(r.posicao_estoque), _br(r.ponto_reposicao) if r.ponto_reposicao is not None else "",
                _br(r.estoque_alvo) if r.estoque_alvo is not None else "", _br(r.compra_sugerida),
                _br(r.custo_compra), _br(r.valor_estoque), _br(r.excesso_unidades), _br(r.valor_excesso),
                _br(r.comprado_acima_do_necessario), _br(r.valor_comprado_acima), r.confianca,
                _seguro(r.motivo), _seguro(" | ".join(r.avisos)),
            ])
