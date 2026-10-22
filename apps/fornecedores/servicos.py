"""Resumo dos fornecedores a partir da última importação e o prazo informado."""

import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from decimal import Decimal

from apps.core.texto import sem_acento

from .models import REPUTACAO_MAXIMA, Fornecedor, FornecedorImportado

ZERO = Decimal("0")
SEM_NOME = "(sem fornecedor na última compra)"

# Quantos nomes o autopreenchimento oferece. O mesmo número das caixas de busca de
# produto (apps/core/procura.QUANTAS): mais do que isso não cabe na tela do celular.
QUANTAS_SUGESTOES = 8

# Começo de palavra sem depender de \b: "FLOR" casa em "QUITERIA FLOR MILHO" e em
# "QUITERIA-FLOR", porque o fornecedor vem do SET com hífen, ponto e barra no nome.
_PALAVRAS = re.compile(r"[^0-9A-Z]+")


@dataclass
class ResumoFornecedor:
    nome: str
    produtos: int
    valor_comprado_12m: Decimal
    prazo_medido: int | None
    prazo_informado: int | None
    observacao: str = ""
    reputacao: int | None = None
    relacao: str = ""
    relacao_rotulo: str = ""
    documento_fiscal: str = ""
    documento_rotulo: str = ""

    @property
    def estrelas(self):
        """Cinco posições, cheias ou vazias, para a tela desenhar as estrelinhas."""
        nota = self.reputacao or 0
        return [posicao <= nota for posicao in range(1, REPUTACAO_MAXIMA + 1)]

    @property
    def precisa_de_reputacao(self):
        return self.reputacao is None

    @property
    def prazo_em_uso(self):
        """O que o cálculo usa: o informado quando existe, senão o medido no SET."""
        return self.prazo_informado if self.prazo_informado is not None else self.prazo_medido

    @property
    def precisa_de_prazo(self):
        """Sem prazo informado e com o medido zerado, a sugestão de compra sai cedo demais."""
        return self.prazo_informado is None and not self.prazo_medido


def prazos_informados():
    """{nome do fornecedor: dias}. Só os que a gerência preencheu."""
    return dict(Fornecedor.objects.exclude(prazo_dias=None).values_list("nome", "prazo_dias"))


def cadastrados():
    """{nome do fornecedor: ficha}. Para quem precisa da reputação junto de outro cálculo."""
    return {f.nome: f for f in Fornecedor.objects.all()}


def versao_dos_prazos():
    """Muda quando alguém mexe num prazo; entra na chave do cache do painel."""
    ultima = Fornecedor.objects.order_by("-atualizado_em").values_list("atualizado_em", flat=True).first()
    return ultima.isoformat() if ultima else "vazio"


def resumir(importacao):
    """Agrupa os produtos da importação por fornecedor, do que mais custou para o que menos."""
    if importacao is None:
        return []
    produtos = defaultdict(lambda: {"produtos": 0, "valor": ZERO, "prazos": Counter()})
    campos = ("fornecedor", "valor_compras_12m", "prazo_reposicao_dias", "prazo_estimado")
    for nome, valor, prazo, estimado in importacao.itens.values_list(*campos):
        dados = produtos[(nome or "").strip() or SEM_NOME]
        dados["produtos"] += 1
        dados["valor"] += valor or ZERO
        if prazo is not None and not estimado:
            dados["prazos"][prazo] += 1

    fichas = cadastrados()
    resumos = []
    for nome, dados in produtos.items():
        cadastrado = fichas.get(nome)
        mais_comum = dados["prazos"].most_common(1)
        resumos.append(ResumoFornecedor(
            nome=nome,
            produtos=dados["produtos"],
            valor_comprado_12m=dados["valor"],
            prazo_medido=mais_comum[0][0] if mais_comum else None,
            prazo_informado=cadastrado.prazo_dias if cadastrado else None,
            observacao=cadastrado.observacao if cadastrado else "",
            reputacao=cadastrado.reputacao if cadastrado else None,
            relacao=cadastrado.relacao if cadastrado else "",
            relacao_rotulo=cadastrado.get_relacao_display() if cadastrado and cadastrado.relacao else "",
            documento_fiscal=cadastrado.documento_fiscal if cadastrado else "",
            documento_rotulo=(cadastrado.get_documento_fiscal_display()
                              if cadastrado and cadastrado.documento_fiscal else ""),
        ))
    resumos.sort(key=lambda r: (-r.valor_comprado_12m, r.nome))
    return resumos


def procurar(resumos, termo):
    """Os fornecedores que casam com o que foi digitado, do mais provável ao menos.

    Pedido do Edson em 14/10/2026: "FORNECEDORES = campo de pesquisas com recurso de
    auto complete". A tela listava os 2.628 de uma vez, em ordem de quanto pesaram na
    compra, e achar um pelo nome era rolar a página.

    A ordem segue a mesma regra de apps/core/procura.py, que vale para as caixas de
    busca do sistema: quem COMEÇA com o digitado vem antes de quem tem o termo no meio
    de uma palavra, e o empate vai para quem a loja mais comprou no ano. A diferença é
    que aqui a lista já está na memória — ela nasce de um agrupamento em Python, não de
    uma tabela — então a comparação é feita com `texto.sem_acento` em vez de `iregex`.
    """
    procurado = sem_acento(termo).strip()
    if not procurado:
        return list(resumos)
    achados = []
    for resumo in resumos:
        nome = sem_acento(resumo.nome)
        if nome.startswith(procurado):
            perto = 0
        elif any(palavra.startswith(procurado) for palavra in _PALAVRAS.split(nome)):
            perto = 1
        elif procurado in nome:
            perto = 2
        else:
            continue
        achados.append((perto, -resumo.valor_comprado_12m, resumo.nome, resumo))
    achados.sort(key=lambda achado: achado[:3])
    return [achado[3] for achado in achados]


def ficha(importacao, nome):
    """A ficha cadastral do SET para este fornecedor, se o SET tiver uma.

    A ligação é pela razão social, que é o nome que o SET grava na compra e, por tabela,
    no produto. Fornecedor que só aparece em compra antiga pode não ter ficha, e aí a tela
    mostra o que o sistema sabe e diz que o cadastro não foi encontrado.
    """
    if importacao is None or not nome:
        return None
    return (FornecedorImportado.objects.filter(importacao=importacao, razao__iexact=nome).first()
            or FornecedorImportado.objects.filter(importacao=importacao, fantasia__iexact=nome).first())


def resumo_de(importacao, nome):
    """O resumo de um fornecedor só, com os mesmos números da lista."""
    for resumo in resumir(importacao):
        if resumo.nome == nome:
            return resumo
    return None


def produtos_do_fornecedor(importacao, nome, quantos=20):
    """O que a loja compra deste fornecedor, do que mais custou em 12 meses para o que menos."""
    if importacao is None or not nome:
        return []
    return list(
        importacao.itens.filter(fornecedor=nome)
        .order_by("-valor_compras_12m", "codigo")[:quantos]
    )
