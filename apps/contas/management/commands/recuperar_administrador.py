"""Devolve o acesso de administração a uma pessoa, no próprio servidor (1.44.0).

Para quando ninguém mais consegue administrar os acessos pela tela: a única pessoa que
administrava esqueceu a senha e não tem e-mail cadastrado, foi bloqueada por engano, ou a
data marcada para o acesso acabar passou. O sistema não deixa a tela tirar o último
administrador, mas a vida acha outros caminhos.

Quem roda isto está no servidor da loja, como administrador do Windows: já pode tudo. Por
isso não há regra de autoridade aqui, só o registro na auditoria, com o motivo.

    ..\\python\\python.exe manage.py recuperar_administrador edson --motivo "esqueceu a senha" --senha

A senha nova é pedida na tela, duas vezes, e nunca vai na linha de comando (ficaria no
histórico do PowerShell).
"""

import getpass

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.auditoria.servicos import registrar
from apps.contas.models import VinculoIdentidade
from apps.contas.perfis import ADMINISTRACAO
from apps.contas.servicos import configurar_perfis, mudando_pela_tela


class Command(BaseCommand):
    help = ("Devolve o acesso de administração a uma pessoa: reativa a conta, tira bloqueio e "
            "data para acabar, dá o perfil Administrador gerência e libera as tentativas de "
            "senha. Com --senha, pede uma senha nova.")

    def add_arguments(self, parser):
        parser.add_argument("usuario", help="o usuário de acesso, como edson")
        parser.add_argument("--motivo", required=True, help="por que, em poucas palavras")
        parser.add_argument("--senha", action="store_true",
                            help="pedir uma senha nova (digitada aqui, duas vezes)")

    def handle(self, *args, usuario, motivo, senha, **opcoes):
        motivo = (motivo or "").strip()
        if not motivo:
            raise CommandError("Diga o motivo: ele fica na auditoria.")
        Usuario = get_user_model()
        alvo = Usuario.objects.filter(username__iexact=usuario.strip()).first()
        if alvo is None:
            raise CommandError(f"Usuário {usuario} não encontrado. Confira em Usuários, ou crie "
                               "a conta técnica com: python manage.py createsuperuser")
        nova = self._pedir_senha(alvo) if senha else None
        if not Group.objects.filter(name=ADMINISTRACAO, permissions__isnull=False).exists():
            configurar_perfis()
        grupo = Group.objects.get(name=ADMINISTRACAO)
        with transaction.atomic():
            antes = {"ativo": alvo.is_active,
                     "perfis": sorted(alvo.groups.values_list("name", flat=True))}
            alvo.is_active = True
            campos = ["is_active"]
            if nova is not None:
                alvo.set_password(nova)
                campos.append("password")
            alvo.save(update_fields=campos)
            vinculo, _ = VinculoIdentidade.objects.get_or_create(usuario=alvo)
            vinculo.desligado_em = None
            vinculo.bloqueado_em = None
            vinculo.bloqueio_motivo = ""
            vinculo.acesso_ate = None
            vinculo.save(update_fields=["desligado_em", "bloqueado_em", "bloqueio_motivo", "acesso_ate"])
            token = mudando_pela_tela.set(True)
            try:
                alvo.groups.add(grupo)
            finally:
                mudando_pela_tela.reset(token)
            registrar("acesso.administrador_recuperado", servico="linha de comando", recurso=alvo,
                      recurso_rotulo=alvo.get_username(), antes=antes,
                      depois={"ativo": True,
                              "perfis": sorted(alvo.groups.values_list("name", flat=True)),
                              "senha_nova": nova is not None},
                      motivo=motivo)
        liberadas = self._liberar_tentativas(alvo)
        self.stdout.write(self.style.SUCCESS(
            f"{alvo.get_username()} está ativo e com o perfil {ADMINISTRACAO}."))
        if liberadas:
            self.stdout.write(f"{liberadas} tentativa(s) de senha errada apagada(s): já pode tentar entrar.")
        if nova is None and not alvo.has_usable_password():
            self.stdout.write(self.style.WARNING(
                "A conta ainda não tem senha. Rode de novo com --senha para definir uma."))

    def _pedir_senha(self, alvo):
        for _ in range(3):
            primeira = getpass.getpass("Senha nova: ")
            segunda = getpass.getpass("A mesma senha de novo: ")
            if primeira != segunda:
                self.stderr.write("As duas não são iguais. Tente de novo.")
                continue
            try:
                validate_password(primeira, alvo)
            except ValidationError as erro:
                self.stderr.write(" ".join(erro.messages))
                continue
            return primeira
        raise CommandError("Senha não definida. Nada foi mudado.")

    def _liberar_tentativas(self, alvo):
        try:
            from axes.utils import reset  # noqa: PLC0415 - só existe com o axes instalado
        except ImportError:
            return 0
        return reset(username=alvo.get_username()) or 0
