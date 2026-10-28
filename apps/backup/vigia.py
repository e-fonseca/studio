"""O vigia do backup: ele avisa quando a cópia de fora do servidor parou de acontecer.

Pedido do Edson em 14/10/2026: *"Acessar de forma automática o github, sem ação humana,
método automatizado"*, dentro do foco que ele deu ao projeto, *"tentar automatizar tudo
para que possamos escalonar a produtividade da empresa"*.

O que é automático, e o que não dá para ser
-------------------------------------------
O envio já é: ele acontece no fim de cada atualização, sem ninguém clicar. O que não dá
para automatizar é a AUTORIZAÇÃO — o GitHub exige uma permissão dada por uma pessoa em
qualquer caminho (token, aplicativo, chave de implantação), e isso é proposital: é o que
impede um programa de escrever na conta de alguém sozinho. Prometer o contrário seria
mentira; o que este arquivo faz é tirar da pessoa tudo o que sobra depois disso.

As duas coisas que ele faz
--------------------------
**Reenvia sozinho.** Se a última cópia que chegou ao GitHub tem mais de uma semana, o
sistema tenta de novo por conta própria, na tarefa que já acorda de hora em hora. Isso
cobre o caso em que a atualização falhou no meio, em que a loja ficou sem internet
naquele minuto, e o caso mais comum de todos: o mês em que não houve atualização
nenhuma. Quando nada mudou, o envio compara os resumos e não manda arquivo nenhum, então
reenviar é barato.

**Fala antes de quebrar.** Automação que falha calada é pior que botão, porque o botão
pelo menos não dá a impressão de estar funcionando. O vigia olha três coisas: a cópia
está velha? o GitHub recusou o token? o token vence em menos de dez dias? Qualquer uma
delas vira recado na tela Cópia do programa e, uma vez por dia, alerta por e-mail e Telegram.
Nenhuma delas dá notícia quando está tudo bem — relatório que chega todo dia dizendo
"está tudo certo" é relatório que ninguém abre.
"""

from dataclasses import dataclass
from datetime import timedelta

from django.urls import reverse
from django.utils import timezone

from . import envio
from .github import NaoDeuCerto, validade_do_token
from .models import ConfiguracaoDeBackup

# A cópia no GitHub pode ter até uma semana. O código só muda em atualização, e a loja
# passa semanas sem nenhuma: cobrar todo dia seria cobrar o que não aconteceu.
DIAS_ATE_FICAR_VELHO = 7
# Quantos dias antes do vencimento o sistema começa a pedir token novo. Dez dias cobrem
# uma viagem e um fim de semana sem a loja ficar descoberta.
DIAS_DE_AVISO_DE_VALIDADE = 10
# De quanto em quanto tempo vale a pena perguntar ao GitHub até quando o token vale.
HORAS_ENTRE_LEITURAS_DE_VALIDADE = 24


class Gravidade:
    OK = "ok"
    ATENCAO = "atencao"
    ERRO = "erro"


@dataclass(frozen=True)
class Situacao:
    """O estado do backup numa frase, do jeito que a tela e o alerta precisam.

    `precisa_de_voce` é o campo que decide se isto vira alerta: problema que o sistema
    resolve sozinho na próxima tentativa não acorda ninguém.
    """

    gravidade: str
    titulo: str
    frase: str
    precisa_de_voce: bool = False

    @property
    def ok(self):
        return self.gravidade == Gravidade.OK

    @property
    def tem_noticia(self):
        return self.gravidade != Gravidade.OK

    @property
    def caminho(self):
        return reverse("backup:painel")


def _dias_desde(quando, agora):
    return (agora - quando).days if quando else None


def situacao(configuracao=None, agora=None):
    """O que está acontecendo com o backup, na ordem do que é mais grave."""
    configuracao = configuracao or ConfiguracaoDeBackup.atual()
    agora = agora or timezone.now()

    faltando = configuracao.falta_preencher
    if faltando:
        return Situacao(
            Gravidade.ERRO, "A cópia do programa no GitHub ainda não está ligada",
            "Falta " + " e ".join(faltando) + ". Enquanto isso, ESTE servidor não manda "
            "o código para o GitHub — o que já estiver lá, mandado de outro lugar, "
            "continua lá, mas nada do que mudar aqui chega sozinho.", precisa_de_voce=True)

    if not configuracao.ativo:
        return Situacao(
            Gravidade.ATENCAO, "A cópia do programa está configurada mas desligada",
            "O token e o repositório estão preenchidos, mas o envio automático está "
            'desmarcado. Marque "mandar a cada atualização" para a cópia voltar a sair '
            "sozinha.", precisa_de_voce=True)

    validade = configuracao.token_validade
    if validade is not None:
        faltam = (validade - agora.date()).days
        if faltam < 0:
            return Situacao(
                Gravidade.ERRO, "O token do GitHub venceu",
                f"Ele valia até {validade:%d/%m/%Y}. Enquanto não entrar um token novo, "
                "nenhuma cópia nova sai do servidor.", precisa_de_voce=True)
        if faltam <= DIAS_DE_AVISO_DE_VALIDADE:
            quando = "hoje" if faltam == 0 else f"em {faltam} dia{'s' if faltam > 1 else ''}"
            return Situacao(
                Gravidade.ATENCAO, f"O token do GitHub vence {quando}",
                f"Ele vale até {validade:%d/%m/%Y}. Gerando um token novo e colando na "
                "tela antes disso, a cópia não para.", precisa_de_voce=True)

    dias = _dias_desde(configuracao.ultimo_sucesso_em, agora)
    if dias is None:
        if configuracao.ultimo_envio_em and not configuracao.ultimo_deu_certo:
            # Primeira tentativa, e ela falhou. Dizer "nenhuma cópia subiu ainda" aqui
            # esconderia o motivo, que é justamente o que a pessoa tem como consertar.
            return Situacao(
                Gravidade.ERRO, "A primeira cópia não conseguiu subir",
                configuracao.ultimo_resultado, precisa_de_voce=True)
        return Situacao(
            Gravidade.ATENCAO, "Nenhuma cópia subiu ainda",
            "Está tudo preenchido, mas o código nunca chegou ao GitHub. O sistema tenta "
            'sozinho; para não esperar, use o botão "Enviar agora".')

    if dias > DIAS_ATE_FICAR_VELHO:
        recado = configuracao.ultimo_resultado if not configuracao.ultimo_deu_certo else ""
        return Situacao(
            Gravidade.ERRO, f"A última cópia no GitHub tem {dias} dias",
            f"O código do servidor não chega ao GitHub desde "
            f"{timezone.localtime(configuracao.ultimo_sucesso_em):%d/%m/%Y}."
            + (f" O último envio não deu certo: {recado}" if recado else
               " O sistema continua tentando sozinho."),
            precisa_de_voce=bool(recado))

    if not configuracao.ultimo_deu_certo:
        return Situacao(
            Gravidade.ATENCAO, "O último envio não deu certo",
            f"{configuracao.ultimo_resultado} A cópia de "
            f"{timezone.localtime(configuracao.ultimo_sucesso_em):%d/%m/%Y} continua lá, e "
            "o sistema tenta de novo sozinho.")

    from apps.core import versao as versao_do_sistema  # noqa: PLC0415

    quando = timezone.localtime(configuracao.ultimo_sucesso_em)
    return Situacao(
        Gravidade.OK, "A cópia do programa está em dia",
        # Pedido dele em 27/10/2026: "a nomenclatura deixa a entender outra coisa". A
        # data parada em 22/10 parecia backup atrasado; é a data da última VERSÃO.
        f"O GitHub tem a versão {versao_do_sistema.atual().numero}, copiada em "
        f"{quando:%d/%m/%Y às %H:%M} ({configuracao.ultimos_arquivos} arquivos). Esta "
        "data só muda quando há alteração ou implementação no sistema.")


def anotar_validade_do_token(configuracao=None, agora=None, consultar=None):
    """Pergunta ao GitHub até quando o token vale e guarda a resposta.

    Uma vez por dia, no máximo: é uma chamada de rede dentro de uma tarefa que acorda de
    hora em hora, e a validade de um token não muda sozinha.
    """
    configuracao = configuracao or ConfiguracaoDeBackup.atual()
    agora = agora or timezone.now()
    if not configuracao.configurado:
        return None
    lida = configuracao.token_validade_lida_em
    if lida and (agora - lida) < timedelta(hours=HORAS_ENTRE_LEITURAS_DE_VALIDADE):
        return configuracao.token_validade

    dono, repositorio = configuracao.dono_e_repositorio
    respondeu, validade = (consultar or validade_do_token)(
        dono, repositorio, configuracao.token)
    if not respondeu:
        # Sem internet naquele minuto. Guardar None aqui apagaria um aviso de vencimento
        # que já estava de pé, e ninguém saberia que ele existiu.
        return configuracao.token_validade
    configuracao.token_validade = validade
    configuracao.token_validade_lida_em = agora
    configuracao.save(update_fields=["token_validade", "token_validade_lida_em"])
    return validade


def reenviar_se_atrasado(configuracao=None, agora=None, enviar=None):
    """Manda o código quando a última cópia ficou velha. Devolve o que aconteceu, ou None.

    Chamado pela tarefa de hora em hora. Nunca levanta erro: ela está no meio do caminho
    dos alertas, e derrubá-la por causa do GitHub deixaria a loja sem os relatórios.
    """
    configuracao = configuracao or ConfiguracaoDeBackup.atual()
    agora = agora or timezone.now()
    if not configuracao.ativo or not configuracao.configurado:
        return None

    # A última TENTATIVA, e não o último sucesso: sem isto, token vencido viraria uma
    # tentativa por hora, e o GitHub trata insistência como abuso.
    tentou = configuracao.ultimo_envio_em
    if tentou and (agora - tentou) < timedelta(days=1):
        return None
    sucesso = configuracao.ultimo_sucesso_em
    if sucesso and (agora - sucesso) <= timedelta(days=DIAS_ATE_FICAR_VELHO):
        return None

    try:
        return (enviar or envio.enviar)(configuracao=configuracao)
    except NaoDeuCerto:
        # O motivo já está gravado na configuração pelo próprio envio, e é dele que a
        # tela e o alerta falam. Aqui não há ninguém para avisar.
        return None
