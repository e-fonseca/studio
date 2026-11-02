"""Quem tem acesso a quê, para conferir antes e depois de uma atualização (1.44.0).

É o mesmo quadro "O que pede atenção" da tela Perfis e permissões, em texto, para rodar no
servidor sem precisar entrar no sistema:

    ..\\python\\python.exe manage.py relatorio_de_acessos
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from apps.contas import autorizacao, catalogo, fichas, servicos


class Command(BaseCommand):
    help = "Mostra quem tem acesso a quê: perfis de cada pessoa, quem vê dinheiro, quem administra."

    def handle(self, *args, **opcoes):
        escrever = self.stdout.write
        Usuario = get_user_model()
        dinheiro = {p.codigo for p in catalogo.CATALOGO if p.dinheiro}
        administracao = {p.codigo for p in catalogo.CATALOGO if p.administracao}

        escrever("PESSOAS")
        for pessoa in Usuario.objects.order_by("-is_active", "username").prefetch_related("groups"):
            estado = servicos.SITUACOES[servicos.situacao(pessoa)]
            perfis = ", ".join(servicos.perfis_do_usuario(pessoa)) or "nenhum perfil"
            if pessoa.is_superuser:
                perfis = "CONTA TÉCNICA (superusuário): pode tudo"
            codigos = autorizacao.permissoes_de(pessoa)
            marcas = []
            if codigos & dinheiro:
                marcas.append("vê dinheiro")
            if codigos & administracao:
                marcas.append("administra")
            extra = f" [{', '.join(marcas)}]" if marcas else ""
            escrever(f"  {pessoa.get_username():<14} {estado:<22} {perfis}{extra}")

        escrever("")
        escrever("PERFIS")
        colunas, _ = fichas.matriz()
        for coluna in colunas:
            escrever(f"  {coluna['grupo'].name:<26} {coluna['permissoes']:>2} permissões, "
                     f"{coluna['pessoas']} pessoa(s) ativa(s)")

        impacto = fichas.impacto()
        escrever("")
        escrever("O QUE PEDE ATENÇÃO")
        admins = impacto["administradores_completos"]
        escrever(f"  Administram pessoas e perfis: {len(admins)} "
                 f"({', '.join(p.get_username() for p in admins) or 'ninguém'})")
        if len(admins) < 2:
            escrever("    Bom ter pelo menos duas pessoas, para uma cobrir a outra.")
        if impacto["sem_perfil"]:
            escrever("  Ativos sem perfil (entram e não abrem nada): "
                     + ", ".join(p.get_username() for p in impacto["sem_perfil"]))
        if impacto["individuais"]:
            escrever("  Com permissão individual, fora de perfil: "
                     + ", ".join(p.get_username() for p in impacto["individuais"]))
        if impacto["superusuarios"]:
            escrever("  Contas técnicas (superusuário): "
                     + ", ".join(p.get_username() for p in impacto["superusuarios"]))
        if impacto["perfis_vazios"]:
            escrever("  Perfis sem ninguém: " + ", ".join(impacto["perfis_vazios"]))
