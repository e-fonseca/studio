"""A API que o agente da casa do Edson usa, pela VPN, com a chave dele.

Tudo em JSON. A chave vai no cabeçalho `Authorization: Bearer <chave>`. Sem chave válida, a
resposta é 401 e nada mais: não diz se a chave existe, nem de quem é. Ver
docs/integracao-agente.md para o passo a passo do agente.
"""

import json
from datetime import datetime
from decimal import Decimal, InvalidOperation
from functools import wraps

from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from apps.auditoria.servicos import registrar
from apps.leads.models import Contato, Lead
from apps.projetos.models import Projeto

from .models import ChaveDeIntegracao, Evento
from .sinais import dados_do_projeto

LIMITE_PADRAO = 50
LIMITE_MAXIMO = 200


def com_chave(view):
    @csrf_exempt  # quem chama é um programa com chave, não um navegador com cookie
    @wraps(view)
    def _view(request, *args, **kwargs):
        cabecalho = request.headers.get("Authorization", "")
        chave = cabecalho[7:].strip() if cabecalho.startswith("Bearer ") else ""
        registro = ChaveDeIntegracao.conferir(chave)
        if registro is None:
            return JsonResponse({"erro": "chave inválida"}, status=401)
        ChaveDeIntegracao.objects.filter(pk=registro.pk).update(usada_em=timezone.now())
        request.chave = registro
        return view(request, *args, **kwargs)
    return _view


def _json(request):
    try:
        return json.loads(request.body or b"{}")
    except (ValueError, UnicodeDecodeError):
        return None


def _servico(request):
    return f"agente:{request.chave.nome}"


@com_chave
@require_http_methods(["GET"])
def eventos(request):
    """Os eventos ainda não entregues, do mais antigo para o mais novo."""
    try:
        limite = min(LIMITE_MAXIMO, max(1, int(request.GET.get("limite", LIMITE_PADRAO))))
    except ValueError:
        limite = LIMITE_PADRAO
    pendentes = Evento.objects.filter(entregue_em__isnull=True)[:limite]
    return JsonResponse({"eventos": [
        {"id": e.pk, "tipo": e.tipo, "recurso_tipo": e.recurso_tipo, "recurso_id": e.recurso_id,
         "dados": e.dados, "criado_em": e.criado_em.isoformat(), "tentativas": e.tentativas}
        for e in pendentes
    ]})


@com_chave
@require_http_methods(["POST"])
def entregar(request, pk):
    """O agente diz como foi: {"ok": true, "trello_cartao": "..."} ou {"ok": false, "erro": "..."}."""
    corpo = _json(request)
    if corpo is None:
        return JsonResponse({"erro": "corpo não é JSON"}, status=400)
    evento = Evento.objects.filter(pk=pk).first()
    if evento is None:
        return JsonResponse({"erro": "evento não existe"}, status=404)
    if corpo.get("ok"):
        evento.entregue_em = timezone.now()
        evento.ultimo_erro = ""
        cartao = str(corpo.get("trello_cartao") or "")[:64]
        if cartao and evento.recurso_tipo == "projeto":
            projeto = Projeto.objects.filter(pk=evento.recurso_id).first()
            if projeto is not None and projeto.trello_cartao != cartao:
                projeto.trello_cartao = cartao
                projeto.save(update_fields=["trello_cartao"])
    else:
        evento.tentativas += 1
        evento.ultimo_erro = str(corpo.get("erro") or "sem detalhe")[:2000]
    evento.save()
    return JsonResponse({"id": evento.pk, "entregue": evento.entregue_em is not None})


@com_chave
@require_http_methods(["GET"])
def projetos(request):
    """Os projetos que não estão encerrados, para o agente conferir o quadro do Trello inteiro."""
    abertos = Projeto.objects.exclude(etapa__in=[Projeto.Etapa.CANCELADO]).select_related(
        "oficina", "responsavel")
    if request.GET.get("todos") != "1":
        abertos = abertos.exclude(etapa=Projeto.Etapa.ENTREGUE)
    return JsonResponse({"projetos": [{"id": p.pk, **dados_do_projeto(p)} for p in abertos]})


def _valor(bruto):
    if bruto in (None, ""):
        return None
    try:
        valor = Decimal(str(bruto)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None
    return valor if valor >= 0 else None


def _quando(bruto):
    if isinstance(bruto, (int, float)):  # o Kommo manda data em segundos desde 1970
        return datetime.fromtimestamp(bruto, tz=timezone.get_current_timezone())
    data = parse_datetime(str(bruto or ""))
    if data and timezone.is_naive(data):
        data = timezone.make_aware(data)
    return data


@com_chave
@require_http_methods(["POST"])
def receber_lead(request):
    """Um lead do Kommo entra ou é atualizado, com as conversas novas.

    Corpo: {"kommo_id", "nome", "telefone", "email", "interesse", "valor_estimado",
    "mensagens": [{"quando", "texto", "canal"}]}. O lead é achado pelo kommo_id; os dados
    que alguém do Studio já preencheu aqui não são apagados por um campo vazio do Kommo, e a
    etapa daqui não muda: quem trabalha o funil é o Studio.
    """
    corpo = _json(request)
    if corpo is None:
        return JsonResponse({"erro": "corpo não é JSON"}, status=400)
    kommo_id = str(corpo.get("kommo_id") or "").strip()[:40]
    nome = str(corpo.get("nome") or "").strip()[:160]
    if not kommo_id or not nome:
        return JsonResponse({"erro": "kommo_id e nome são obrigatórios"}, status=400)

    with transaction.atomic():
        lead = Lead.objects.select_for_update().filter(kommo_id=kommo_id).first()
        criado = lead is None
        if criado:
            lead = Lead(kommo_id=kommo_id, origem=Lead.Origem.WHATSAPP,
                        proximo_contato=timezone.localdate())
        lead.nome = nome
        for campo, limite in (("telefone", 40), ("email", 254), ("interesse", 4000)):
            valor = str(corpo.get(campo) or "").strip()[:limite]
            if valor:
                setattr(lead, campo, valor)
        valor = _valor(corpo.get("valor_estimado"))
        if valor is not None:
            lead.valor_estimado = valor
        lead._veio_do_kommo = True
        lead.save()

        ultimo = lead.contatos.filter(automatico=True).order_by("-quando").values_list(
            "quando", flat=True).first()
        novos = 0
        for mensagem in corpo.get("mensagens") or []:
            quando = _quando(mensagem.get("quando"))
            texto = str(mensagem.get("texto") or "").strip()[:4000]
            if not quando or not texto or (ultimo and quando <= ultimo):
                continue  # já trazida numa passada anterior
            canal = mensagem.get("canal") if mensagem.get("canal") in Contato.Canal.values else "whatsapp"
            Contato.objects.create(lead=lead, quando=quando, canal=canal, resumo=texto,
                                   automatico=True)
            novos += 1

    registrar("integracao.lead_recebido", servico=_servico(request), recurso=lead,
              depois={"kommo_id": kommo_id, "criado": criado, "mensagens_novas": novos})
    return JsonResponse({"id": lead.pk, "criado": criado, "mensagens_novas": novos},
                        status=201 if criado else 200)
