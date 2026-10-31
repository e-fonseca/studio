"""Recuperar a senha com um código mandado ao e-mail cadastrado (1.43.0).

Pedido do Edson em 31/10/2026: *"adotar recurso de recuperar senha por e-mail cadastrado
via confirmação de código, senão tiver cadastro informe que não é possível, procure o
administrador do sistema."*

O caminho, em duas telas
------------------------
1. Na tela de entrada, "Esqueci a minha senha". A pessoa digita o usuário (ou o e-mail
   cadastrado). Se a conta tem e-mail, está liberada e já tem senha, o sistema manda um
   código de seis números para esse e-mail e diz para onde mandou, com o meio escondido
   (ed•••@gmail.com). Se não tem, a tela diz que não é possível por aqui e manda procurar
   o administrador do sistema, como ele pediu.
2. Na tela seguinte a pessoa digita o código e a senha nova duas vezes. Deu certo: a senha
   muda, as sessões abertas dela em outros aparelhos caem, o bloqueio por senha errada
   (django-axes) sai, chega um e-mail avisando da troca, e ela volta para a tela de entrada
   para entrar com a senha nova.

As travas
---------
* O código vale **15 minutos** e serve **uma vez**. Pedir outro anula o anterior.
* **Cinco erros** no código e ele deixa de valer: seis números são um milhão de
  combinações, e cinco tentativas por código, com no máximo cinco códigos por hora, dão
  25 chutes por hora contra um milhão.
* Entre dois códigos para a mesma pessoa, **um minuto**: quem clica de novo achando que o
  primeiro não chegou recebe a tela do código, e não um segundo e-mail que anula o
  primeiro enquanto ele ainda está chegando.
* Do mesmo endereço (IP), no máximo **dez pedidos por hora**, contando os que não deram
  em nada: é o que impede alguém de ficar testando nomes de usuário.
* O código não fica guardado: fica uma assinatura dele feita com a chave secreta do
  sistema (`salted_hmac`), que confere o que foi digitado sem permitir lê-lo de volta.
* Tudo vai para a auditoria (pedido, código enviado, código errado, senha criada), menos
  o código e a senha. E-mail digitado no lugar do usuário entra com o meio escondido.

Conta sem senha (recém-criada) não recupera por aqui: a primeira senha continua sendo
definida pela gerência, na tela de usuários, como desde a 1.4.0.
"""

import logging
import secrets
from dataclasses import dataclass
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.crypto import constant_time_compare, salted_hmac

from apps.auditoria.contexto import ip_atual
from apps.auditoria.models import EventoAuditoria
from apps.auditoria.servicos import registrar

from . import servicos
from .models import CodigoDeRecuperacao

logger = logging.getLogger(__name__)

VALIDADE = timedelta(minutes=15)
TENTATIVAS = 5
INTERVALO = timedelta(minutes=1)
CODIGOS_POR_HORA = 5
PEDIDOS_POR_HORA_POR_ENDERECO = 10
SERVICO = "recuperação de senha"

NAO_E_POSSIVEL = (
    "Não é possível recuperar a senha por aqui: esse usuário não tem e-mail cadastrado ou "
    "não está com o acesso liberado. Procure o administrador do sistema."
)
EMAIL_EM_DOIS = ("Esse e-mail está cadastrado em mais de um usuário. Digite o seu usuário de "
                 "acesso no lugar do e-mail.")
SEM_ENVIO = ("Não é possível mandar o código agora: o envio de e-mail do sistema ainda não "
             "está configurado. Procure o administrador do sistema.")
NAO_SAIU = ("O e-mail com o código não saiu. Tente de novo em alguns minutos ou procure o "
            "administrador do sistema.")
MUITOS = ("Foram muitos pedidos de código em pouco tempo. Espere uma hora ou procure o "
          "administrador do sistema.")


def mascarar(email):
    """O e-mail com o meio escondido: "ed•••@gmail.com".

    O bastante para a pessoa reconhecer o próprio e-mail e saber onde procurar o código,
    e pouco para quem digitou o nome de outra pessoa descobrir o e-mail dela.
    """
    nome, _, dominio = (email or "").strip().partition("@")
    if not nome or not dominio:
        return "•••"
    return f"{nome[:2] if len(nome) > 3 else nome[:1]}•••@{dominio}"


def _o_que_foi_digitado(texto):
    """Para a auditoria: usuário digitado vai como está; e-mail vai com o meio escondido."""
    texto = (texto or "").strip()[:150]
    return mascarar(texto) if "@" in texto else texto


def _assinatura(usuario, codigo):
    return salted_hmac("apps.contas.recuperacao", f"{usuario.pk}:{codigo}",
                       algorithm="sha256").hexdigest()


def encontrar(texto):
    """A conta pelo usuário ou pelo e-mail cadastrado. Devolve (usuário, frase do problema).

    Usuário que não existe, sem e-mail, desligado ou ainda sem senha recebem todos a MESMA
    frase: diferenciar diria a quem está testando nomes quais contas existem.
    """
    texto = (texto or "").strip()
    if not texto:
        return None, "Digite o seu usuário ou o e-mail cadastrado."
    Usuario = get_user_model()
    if "@" in texto:
        achados = list(Usuario.objects.filter(email__iexact=texto, is_active=True)[:2])
        if len(achados) > 1:
            return None, EMAIL_EM_DOIS
        conta = achados[0] if achados else None
    else:
        conta = Usuario.objects.filter(username__iexact=texto).first()
    if (conta is None or not conta.is_active or not (conta.email or "").strip()
            or not conta.has_usable_password()):
        return None, NAO_E_POSSIVEL
    return conta, ""


@dataclass
class Pedido:
    """O que a tela precisa saber depois do pedido de código."""

    usuario: object = None
    erro: str = ""
    # O e-mail com o meio escondido, para a tela dizer para onde o código foi.
    para: str = ""
    # O código mandado há menos de um minuto ainda vale, e nenhum e-mail novo saiu.
    reaproveitado: bool = False

    @property
    def deu_certo(self):
        return self.usuario is not None and not self.erro


def _anotar_pedido(texto, conta=None, *, deu_certo, motivo="", depois=None):
    """Todo pedido vai para a auditoria, com e sem sucesso. É por ele que se conta o limite
    por endereço: a trilha já guarda o IP de cada evento."""
    registrar(
        "acesso.codigo_pedido",
        servico=SERVICO,
        recurso=conta,
        recurso_rotulo=conta.get_username() if conta else "",
        resultado=(EventoAuditoria.Resultado.SUCESSO if deu_certo
                   else EventoAuditoria.Resultado.FALHA),
        depois={"usuario_tentado": _o_que_foi_digitado(texto), **(depois or {})},
        motivo=motivo,
    )


def _pedidos_do_endereco(ip, agora):
    return EventoAuditoria.objects.filter(
        acao="acesso.codigo_pedido", ip=ip, momento__gte=agora - timedelta(hours=1)).count()


def _mensagem_do_codigo(conta, codigo, vale_ate):
    contexto = {
        "nome": conta.first_name or conta.get_username(),
        "usuario": conta.get_username(),
        "codigo": codigo,
        "vale_ate": timezone.localtime(vale_ate),
        "minutos": int(VALIDADE.total_seconds() // 60),
    }
    return (render_to_string("contas/email/codigo.txt", contexto),
            render_to_string("contas/email/codigo.html", contexto))


def pedir_codigo(texto):
    """Manda o código ao e-mail cadastrado de quem foi digitado. Nunca levanta erro de e-mail."""
    # Aqui dentro, e não no topo: o envio carrega os relatórios, que carregam meio sistema,
    # e a tela de entrada não precisa disso tudo para abrir.
    from apps.alertas import envio  # noqa: PLC0415
    from apps.alertas.models import ConfiguracaoDeEmail  # noqa: PLC0415

    agora = timezone.now()
    ip = ip_atual()
    if ip and _pedidos_do_endereco(ip, agora) >= PEDIDOS_POR_HORA_POR_ENDERECO:
        _anotar_pedido(texto, deu_certo=False, motivo="muitos pedidos do mesmo endereço em uma hora")
        return Pedido(erro=MUITOS)

    conta, problema = encontrar(texto)
    if conta is None:
        _anotar_pedido(texto, deu_certo=False, motivo=problema)
        return Pedido(erro=problema)

    para = mascarar(conta.email)
    da_ultima_hora = CodigoDeRecuperacao.objects.filter(
        usuario=conta, criado_em__gte=agora - timedelta(hours=1))
    ultimo = da_ultima_hora.first()
    if ultimo is not None and ultimo.aberto and agora - ultimo.criado_em < INTERVALO:
        _anotar_pedido(texto, conta, deu_certo=True,
                       motivo="o código mandado há menos de um minuto ainda vale; nenhum e-mail novo")
        return Pedido(usuario=conta, para=para, reaproveitado=True)
    if da_ultima_hora.count() >= CODIGOS_POR_HORA:
        _anotar_pedido(texto, conta, deu_certo=False, motivo="cinco códigos na última hora")
        return Pedido(erro=MUITOS)

    configuracao = ConfiguracaoDeEmail.atual()
    if not configuracao.pode_enviar:
        _anotar_pedido(texto, conta, deu_certo=False,
                       motivo="o envio de e-mail não está configurado na tela Alertas")
        return Pedido(erro=SEM_ENVIO)

    codigo = f"{secrets.randbelow(1_000_000):06d}"
    # Um código aberto por pessoa: o novo anula os anteriores.
    CodigoDeRecuperacao.objects.filter(
        usuario=conta, usado_em__isnull=True, anulado_em__isnull=True).update(anulado_em=agora)
    novo = CodigoDeRecuperacao.objects.create(
        usuario=conta, resumo=_assinatura(conta, codigo), criado_em=agora,
        vale_ate=agora + VALIDADE, ip=ip)
    texto_do_email, html_do_email = _mensagem_do_codigo(conta, codigo, novo.vale_ate)
    erro = envio.enviar_avulso(
        assunto="[Cabana] Código para criar a senha nova", texto=texto_do_email,
        html=html_do_email, para=conta.email.strip(), configuracao=configuracao)
    if erro:
        novo.anulado_em = timezone.now()
        novo.save(update_fields=["anulado_em"])
        _anotar_pedido(texto, conta, deu_certo=False, motivo=f"o e-mail não saiu: {erro}"[:1000])
        return Pedido(erro=NAO_SAIU)
    _anotar_pedido(texto, conta, deu_certo=True, depois={"para": para})
    return Pedido(usuario=conta, para=para)


def codigo_aberto(conta):
    """O código que ainda vale para esta pessoa, ou None."""
    codigo = (CodigoDeRecuperacao.objects
              .filter(usuario=conta, usado_em__isnull=True, anulado_em__isnull=True)
              .first())
    return codigo if codigo is not None and codigo.aberto else None


def conferir_codigo(conta, digitado):
    """Confere o código digitado. Devolve (código, frase do problema).

    Cada erro conta uma tentativa; na quinta o código é anulado e é preciso pedir outro.
    Quem chama deve estar dentro de uma transação (a linha é travada para duas abas não
    gastarem a mesma tentativa).
    """
    numeros = "".join(caractere for caractere in (digitado or "") if caractere.isdigit())
    codigo = (CodigoDeRecuperacao.objects.select_for_update()
              .filter(usuario=conta, usado_em__isnull=True, anulado_em__isnull=True)
              .first())
    if codigo is None or not codigo.aberto:
        return None, "Esse código não vale mais. Peça outro código abaixo."
    if len(numeros) == 6 and constant_time_compare(codigo.resumo, _assinatura(conta, numeros)):
        return codigo, ""
    codigo.tentativas += 1
    campos = ["tentativas"]
    if codigo.tentativas >= TENTATIVAS:
        codigo.anulado_em = timezone.now()
        campos.append("anulado_em")
    codigo.save(update_fields=campos)
    registrar("acesso.codigo_errado", servico=SERVICO, recurso=conta,
              recurso_rotulo=conta.get_username(), resultado=EventoAuditoria.Resultado.FALHA,
              depois={"tentativas": codigo.tentativas})
    if codigo.anulado_em is not None:
        return None, (f"O código foi digitado errado {TENTATIVAS} vezes e deixou de valer. "
                      "Peça outro código abaixo.")
    restam = TENTATIVAS - codigo.tentativas
    return None, (f"O código não confere. Confira os seis números no e-mail. "
                  f"{'Resta' if restam == 1 else 'Restam'} {restam} "
                  f"{'tentativa' if restam == 1 else 'tentativas'}.")


def criar_senha_nova(conta, codigo, senha):
    """Grava a senha nova (já validada pelo formulário) e gasta o código.

    As sessões abertas em outros aparelhos caem, porque a senha velha pode ser justamente
    o que vazou; e o bloqueio por senha errada sai, porque quem errou cinco vezes costuma
    ser quem esqueceu. A pessoa entra em seguida, na tela de entrada, com a senha nova.
    """
    from axes.utils import reset as tirar_bloqueio  # noqa: PLC0415 - carrega a config do axes

    agora = timezone.now()
    conta.set_password(senha)
    conta.save(update_fields=["password"])
    codigo.usado_em = agora
    codigo.save(update_fields=["usado_em"])
    sessoes = servicos.encerrar_sessoes(conta)
    try:
        bloqueios = tirar_bloqueio(username=conta.get_username())
    except Exception:  # noqa: BLE001 - a senha nova vale mesmo se o axes falhar
        logger.exception("Não deu para tirar o bloqueio de %s", conta.get_username())
        bloqueios = 0
    # A própria pessoa: ela provou quem é com o código que só o e-mail dela recebeu.
    registrar("acesso.senha_recuperada", usuario=conta, recurso=conta,
              recurso_rotulo=conta.get_username(),
              depois={"sessoes_encerradas": sessoes, "bloqueios_retirados": bloqueios})
    _avisar_da_troca(conta, agora)


def _avisar_da_troca(conta, quando):
    """O e-mail de "sua senha foi trocada": se não foi a pessoa, ela fica sabendo na hora.

    Falhar aqui não desfaz nada: a senha nova já vale, e a auditoria já tem o registro.
    """
    from apps.alertas import envio  # noqa: PLC0415 - ver pedir_codigo

    contexto = {"nome": conta.first_name or conta.get_username(),
                "usuario": conta.get_username(), "quando": timezone.localtime(quando)}
    erro = envio.enviar_avulso(
        assunto="[Cabana] A sua senha foi trocada",
        texto=render_to_string("contas/email/senha_trocada.txt", contexto),
        html=render_to_string("contas/email/senha_trocada.html", contexto),
        para=conta.email.strip())
    if erro:
        logger.warning("O aviso de senha trocada de %s não saiu: %s", conta.get_username(), erro)


def definir_email(conta, email, *, responsavel):
    """Grava o e-mail de recuperação da conta. Em branco tira o e-mail. Devolve se mudou.

    Pela gerência, na tela de usuários, ou pela própria pessoa, na tela de trocar a senha
    (com a senha atual conferida pela tela). O e-mail entra na auditoria com o meio
    escondido: a trilha diz que mudou e de quem para quem, sem guardar o endereço inteiro.
    """
    from django.core.exceptions import ValidationError  # noqa: PLC0415
    from django.core.validators import validate_email  # noqa: PLC0415

    email = (email or "").strip()
    if email:
        try:
            validate_email(email)
        except ValidationError:
            raise ValueError("Esse e-mail não parece certo. Confira se tem o @ e o domínio, "
                             "como nome@gmail.com.") from None
    antes = (conta.email or "").strip()
    if antes == email:
        return False
    conta.email = email
    conta.save(update_fields=["email"])
    registrar("acesso.email_definido", usuario=responsavel, recurso=conta,
              recurso_rotulo=conta.get_username(),
              antes={"email": mascarar(antes) if antes else ""},
              depois={"email": mascarar(email) if email else ""})
    return True
