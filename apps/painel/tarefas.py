"""O que fazer agora: a lista de tarefas que o sistema monta sozinho.

Pedido do Edson (07/10/2026): "a minha ideia é que o sistema me diga o que eu
tenho que fazer". O sistema já sabia várias coisas — que tem produto faltando,
que tem conta vencida, que tem mercadoria parada, que tem sugestão da equipe sem
resposta —, mas cada uma morava numa tela diferente e quem abria o sistema tinha
que ir atrás. Aqui elas viram uma lista só, em ordem de urgência, com o número
que prova a tarefa e o link que a resolve.

Três regras que fazem esta tela valer alguma coisa:

1. **Só entra tarefa que tem ação.** Nada de "a loja vendeu R$ 1,5 milhão"; isso
   é informação e mora no painel. Tarefa é o que alguém faz hoje.
2. **Cada tarefa traz o número que a justifica**, e o número sai do dado, nunca de
   um palpite. Se a conta der zero, a tarefa não aparece.
3. **A ordem é de urgência, não de assunto.** Dinheiro que já venceu vem antes de
   mercadoria parada, que vem antes de cadastro incompleto.

Nada aqui decide nada sozinho: toda tarefa termina num link para a tela onde uma
pessoa decide.
"""

from dataclasses import dataclass, field
from decimal import Decimal

from django.db.models import Count, DecimalField, ExpressionWrapper, F, Q, Sum
from django.urls import reverse

ZERO = Decimal("0")
QUANTAS_NA_ABERTURA = 5

# Níveis, do mais urgente para o menos. São os mesmos nomes de cor do resto do sistema.
URGENTE = "ruim"
ATENCAO = "atencao"
NORMAL = "neutro"
PESO = {URGENTE: 0, ATENCAO: 1, NORMAL: 2}


@dataclass
class Tarefa:
    chave: str
    titulo: str          # o que fazer, começando com um verbo
    detalhe: str         # a frase com o número que prova a tarefa
    rota: str            # nome da rota que resolve
    nivel: str = NORMAL
    rotulo_do_link: str = "Abrir"
    parametros: str = ""  # query string, quando a tela precisa de filtro
    permissao: str = None

    @property
    def endereco(self):
        return reverse(self.rota) + (self.parametros or "")

    @property
    def gravidade(self):
        """A palavra do nível, para o quadro de problemas do Dashboard."""
        return NOME_DO_NIVEL.get(self.nivel, "")


@dataclass
class Agenda:
    tarefas: list = field(default_factory=list)
    data_corte: object = None

    @property
    def tem_tarefas(self):
        return bool(self.tarefas)

    @property
    def urgentes(self):
        return [t for t in self.tarefas if t.nivel == URGENTE]

    @property
    def primeiras(self):
        return self.tarefas[:QUANTAS_NA_ABERTURA]

    @property
    def restantes(self):
        return max(len(self.tarefas) - QUANTAS_NA_ABERTURA, 0)


def _reais(valor):
    texto = f"{(valor or ZERO):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {texto}"


def _dados_velhos(estado, agenda):
    """Dado velho invalida todas as outras tarefas, então esta vem antes de tudo."""
    if estado is None or estado.nivel in ("bom", "ok"):
        return
    if estado.nivel == "sem_dados":
        agenda.tarefas.append(Tarefa(
            chave="importar", titulo="Importar os dados do SET",
            detalhe="Nenhuma importação concluída ainda: sem isso nenhuma tela tem número.",
            rota="importacao:historico", nivel=URGENTE, rotulo_do_link="Ver importações",
            permissao="importacao.ver_painel"))
        return
    agenda.tarefas.append(Tarefa(
        chave="importar", titulo="Conferir a importação",
        detalhe=f"{estado.titulo}. Decidir compra por número velho é decidir no escuro.",
        rota="importacao:historico",
        nivel=URGENTE if estado.nivel == "vencido" else ATENCAO,
        rotulo_do_link="Ver importações", permissao="importacao.ver_painel"))


def _financeiro(resumo, agenda):
    if resumo is None:
        return
    if resumo.vencidas.quantidade:
        agenda.tarefas.append(Tarefa(
            chave="vencidas", titulo="Resolver as contas vencidas",
            detalhe=(f"{resumo.vencidas.quantidade} contas venceram e continuam em aberto no SET, "
                     f"somando {_reais(resumo.vencidas.valor)}. Pode ser pagamento feito e não "
                     "baixado, mas alguém precisa olhar."),
            rota="financeiro:contas_a_pagar", parametros="?filtro=atrasados",
            nivel=URGENTE, rotulo_do_link="Ver contas",
            permissao="financeiro.ver_financeiro"))
    prestes = next((f for f in resumo.por_faixa if f["dias"] == 7), None)
    if prestes and prestes["valor"] > ZERO:
        agenda.tarefas.append(Tarefa(
            chave="prestes", titulo="Separar o caixa da semana",
            detalhe=f"{_reais(prestes['valor'])} vencem nos próximos 7 dias.",
            rota="financeiro:contas_a_pagar", parametros="?filtro=prestes",
            nivel=ATENCAO, rotulo_do_link="Ver contas",
            permissao="financeiro.ver_financeiro"))


def _compras(lista, agenda):
    """As tarefas que saem da lista de compra, que já fez a conta pesada."""
    if lista is None or not lista.tem_itens:
        return
    if lista.faltando:
        quantos = len(lista.primeiro)
        agenda.tarefas.append(Tarefa(
            chave="faltando", titulo="Fechar o pedido do que está faltando",
            detalhe=(f"{lista.faltando} produtos estão zerados e continuam vendendo. "
                     + (f"Começando pelos {quantos} fornecedores do topo da lista, "
                        f"são {_reais(lista.valor_primeiro)}." if quantos else "")),
            rota="compras:lista", nivel=URGENTE, rotulo_do_link="Ver a lista",
            permissao="importacao.ver_painel"))
    if lista.abaixo_do_minimo:
        agenda.tarefas.append(Tarefa(
            chave="minimo", titulo="Repor o que está abaixo do mínimo",
            detalhe=(f"{lista.abaixo_do_minimo} produtos estão abaixo do mínimo que a própria "
                     "loja cadastrou no SET."),
            rota="compras:lista", parametros="?situacao=abaixo_do_minimo",
            nivel=ATENCAO, rotulo_do_link="Ver a lista", permissao="importacao.ver_painel"))
    if lista.sem_prazo_informado:
        agenda.tarefas.append(Tarefa(
            chave="prazos", titulo="Informar o prazo dos fornecedores",
            detalhe=(f"{lista.sem_prazo_informado} linhas da lista de compra usam um prazo "
                     "assumido pelo sistema, porque o SET grava a data da nota e não o prazo. "
                     "Com o prazo certo, a data de comprar fica certa."),
            rota="fornecedores:lista", nivel=NORMAL, rotulo_do_link="Ver fornecedores",
            permissao="fornecedores.view_fornecedor"))


def _parado(importacao, agenda):
    if importacao is None:
        return
    from apps.compras.sugestoes import so_mercadoria

    parado = ExpressionWrapper(F("estoque") * F("custo"),
                               output_field=DecimalField(max_digits=16, decimal_places=2))
    consulta = so_mercadoria(
        importacao.itens.filter(estoque__gt=0, vendas_12m__lte=0, custo__gt=0))
    resumo = consulta.annotate(v=parado).aggregate(total=Sum("v"), quantos=Count("id"))
    if not resumo["quantos"]:
        return
    agenda.tarefas.append(Tarefa(
        chave="parado", titulo="Pôr para girar o que está parado",
        detalhe=(f"{resumo['quantos']} produtos têm saldo na prateleira e não venderam "
                 f"nenhuma unidade em 12 meses, segurando {_reais(resumo['total'])} ao custo."),
        rota="compras:sugestoes", nivel=ATENCAO, rotulo_do_link="Ver sugestões",
        permissao="importacao.ver_painel"))


def _sugestoes_da_equipe(agenda):
    from apps.compras.models import SugestaoDeCompra

    abertas = SugestaoDeCompra.objects.filter(situacao=SugestaoDeCompra.Situacao.ABERTA).count()
    if not abertas:
        return
    agenda.tarefas.append(Tarefa(
        chave="equipe", titulo="Responder a equipe",
        detalhe=(f"{abertas} sugestão{'' if abertas == 1 else 'ões'} de compra escrita"
                 f"{'' if abertas == 1 else 's'} por quem está na loja esperando resposta."),
        rota="compras:sugestoes_da_equipe", nivel=ATENCAO, rotulo_do_link="Ver sugestões",
        permissao="compras.responder_sugestao"))


def _inventario(importacao, agenda):
    from apps.inventario.models import Contagem

    aberta = Contagem.objects.filter(situacao=Contagem.Situacao.ABERTA).first()
    if aberta is not None:
        agenda.tarefas.append(Tarefa(
            chave="contagem", titulo="Terminar a contagem em andamento",
            detalhe=f'A contagem "{aberta.nome}" está aberta desde {aberta.aberta_em:%d/%m/%Y}.',
            rota="inventario:lista", nivel=NORMAL, rotulo_do_link="Ver inventário",
            permissao="inventario.contar_estoque"))
        return
    if importacao is None:
        return
    negativos = importacao.itens.filter(estoque__lt=0).count()
    if negativos:
        agenda.tarefas.append(Tarefa(
            chave="negativos", titulo="Contar o que está negativo no SET",
            detalhe=(f"{negativos} produtos estão com saldo negativo, o que só acontece quando "
                     "a entrada não foi lançada. Enquanto não houver contagem, o saldo de "
                     "estoque é estimativa."),
            rota="inventario:lista", nivel=NORMAL, rotulo_do_link="Abrir contagem",
            permissao="inventario.contar_estoque"))


def montar(estado, importacao=None, resumo_financeiro=None, lista=None, usuario=None) -> Agenda:
    """A agenda do dia. Recebe pronto o que já foi calculado para a tela, para não repetir conta."""
    agenda = Agenda(data_corte=getattr(importacao, "data_corte", None))
    _dados_velhos(estado, agenda)
    _financeiro(resumo_financeiro, agenda)
    _compras(lista, agenda)
    _parado(importacao, agenda)
    _sugestoes_da_equipe(agenda)
    _inventario(importacao, agenda)

    agenda.tarefas.sort(key=lambda t: PESO.get(t.nivel, 3))
    return para(agenda, usuario)


# O nome de cada nível no quadro de problemas do Dashboard, que é a lista desta mesma
# agenda com a gravidade escrita ao lado, como o "Problemas recentes" do Grafana.
NOME_DO_NIVEL = {URGENTE: "Urgente", ATENCAO: "Atenção", NORMAL: "Para fazer"}


@dataclass
class Situacao:
    """O quadro "Situação da loja" do Dashboard: a agenda resumida numa palavra.

    A palavra é a do item mais grave da lista que ESTA pessoa vê, e a frase embaixo
    conta quantos há de cada nível. Não é um juízo novo sobre a loja: é a mesma agenda
    da Visão geral, com as mesmas regras e as mesmas permissões.
    """

    nivel: str = "bom"
    palavra: str = "Tudo em dia"
    urgentes: int = 0
    atencao: int = 0
    para_fazer: int = 0

    @property
    def frase(self):
        partes = []
        if self.urgentes:
            partes.append(f"{self.urgentes} urgente{'' if self.urgentes == 1 else 's'}")
        if self.atencao:
            partes.append(f"{self.atencao} de atenção")
        if self.para_fazer:
            partes.append(f"{self.para_fazer} para fazer")
        return " · ".join(partes) if partes else "Nada pedindo ação agora."

    @property
    def letras(self):
        """Para o quadro escolher o tamanho da palavra, como nos números (o símbolo do
        lado conta como duas letras)."""
        return len(self.palavra) + 2


def situacao(agenda):
    urgentes = sum(1 for t in agenda.tarefas if t.nivel == URGENTE)
    atencao = sum(1 for t in agenda.tarefas if t.nivel == ATENCAO)
    para_fazer = sum(1 for t in agenda.tarefas if t.nivel == NORMAL)
    if urgentes:
        nivel, palavra = "ruim", "Urgente"
    elif atencao:
        nivel, palavra = "atencao", "Atenção"
    else:
        # Só tarefa sem pressa (prazo de fornecedor, contagem aberta) não é problema: a
        # loja está em dia, e a frase embaixo diz o que há para fazer quando der.
        nivel, palavra = "bom", "Tudo em dia"
    return Situacao(nivel=nivel, palavra=palavra, urgentes=urgentes, atencao=atencao,
                    para_fazer=para_fazer)


def para(agenda, usuario):
    """A mesma agenda, com só as tarefas que esta pessoa pode abrir.

    O vendedor não tem tela nenhuma dessas, e mostrar a ele uma tarefa que termina em
    "acesso negado" seria pior do que não mostrar nada.
    """
    if usuario is None:
        return agenda
    return Agenda(
        data_corte=agenda.data_corte,
        tarefas=[t for t in agenda.tarefas
                 if t.permissao is None or usuario.has_perm(t.permissao)],
    )
