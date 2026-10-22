"""Leitura dos dados do SET a partir de uma CÓPIA do banco Firebird.

Regra que não muda (docs/leitura-firebird.md): nunca abrir o DADOS-SET.FDB que o
caixa usa, nem falar com o serviço Firebird do SET na porta 3050. Esta leitura
trabalha sempre sobre uma cópia própria, dentro da pasta do sistema novo, e só
executa SELECT.

Tudo é agregado em duas janelas contadas a partir da data de corte (a última
venda que existe na cópia): 12 meses e 90 dias. "Dias abertos" é a quantidade de
dias distintos com venda, que é o divisor honesto da média diária -- domingo
fechado não derruba a média.
"""

import codecs
import shutil
import statistics
import struct
import subprocess
import sys
import zipfile
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

# Empresa 1 é a loja física (docs/mapeamento-set.md).
EMPRESA = 1
JANELA_12M = 365
JANELA_90D = 90
PRAZO_MAXIMO_PLAUSIVEL = 180  # acima disso é erro de digitação na data de entrega, não prazo
# Compra ainda não recebida. Não conta como compra feita (senão infla "comprou mais do que
# vendeu"); entra como mercadoria a caminho, que reduz o que ainda falta comprar.
SITUACAO_PENDENTE = "Pendente"
# Quanto do financeiro do SET entra na foto. Tudo o que está em aberto entra sempre,
# porque é o que ainda mexe no caixa; do que já foi pago ou recebido vale a janela
# abaixo, que é o bastante para comparar mês a mês sem guardar dez anos de histórico.
JANELA_FINANCEIRO_DIAS = 730
# Quantos MESES de venda por produto e por mês entram na foto, e a leitura começa sempre
# no dia 1º do mês mais antigo. Duas coisas moram nesta linha:
#
# 1. Começar no meio de um mês (era "corte menos 730 dias") deixa o mês mais antigo pela
#    METADE, e a comparação de 12 meses usava esse pedaço como se fosse mês inteiro:
#    outubro cheio contra meio outubro acusava um crescimento que não existe.
# 2. Cinco anos, e não dois, porque o Edson pediu em 14/10/2026 "trazer outro comparativo
#    de vendas do mesmo período dos anos anteriores". São 61 meses porque a comparação
#    descarta o mês mais antigo da foto (ver apps/compras/comparacao.py:_limites), e aí
#    sobram 60: cinco janelas de 12 meses, uma por ano.
JANELA_COMPARACAO_MESES = 61
# Arquiteturas de programa do Windows, como vêm gravadas no cabeçalho PE.
ARQUITETURAS_PE = {0x8664: "64 bits", 0xAA64: "ARM de 64 bits", 0x014C: "32 bits"}
# A leitura é feita com charset NONE, ou seja o Firebird entrega os bytes como estão
# gravados, e quem decide a tabela de caracteres é o sistema. O SET grava a maior parte em
# cp1252, mas nem tudo: no servidor da loja o cadastro de clientes veio em UTF-8 e, lido
# como cp1252, "São Paulo" virava "SÃ£o Paulo" na tela (visto em 07/10/2026). Por isso a
# decodificação tenta UTF-8 primeiro e só cai para cp1252 quando os bytes não formam UTF-8
# válido. Texto cp1252 com acento quase nunca é UTF-8 válido por acaso (um acento precisaria
# vir seguido de outro byte entre 0x80 e 0xBF), então a tentativa é segura.
#
# E a cp1252 vai com um ajuste: byte que não existe na tabela (0x81 apareceu em 06/10/2026
# na descrição de um produto) é descartado em vez de derrubar a importação inteira por causa
# de um caractere. A quantidade descartada fica no log, para dar para conferir depois.
CODIFICACAO_SET = "cabana-set"
_descartados = {"bytes": 0}


def _descartar_byte_invalido(erro):
    _descartados["bytes"] += erro.end - erro.start
    return "", erro.end


def _decodificar(dados):
    """UTF-8 quando os bytes formam UTF-8; cp1252 no resto, descartando byte inválido."""
    try:
        return dados.decode("utf-8")
    except UnicodeDecodeError:
        return dados.decode("cp1252", "cabana_descartar")


def _codec_do_set(nome):
    if nome.replace("-", "_").lower() != CODIFICACAO_SET.replace("-", "_"):
        return None
    return codecs.CodecInfo(
        name=CODIFICACAO_SET,
        encode=lambda texto, erros="replace": (texto.encode("cp1252", "replace"), len(texto)),
        decode=lambda dados, erros=None: (_decodificar(bytes(dados)), len(dados)),
    )


codecs.register_error("cabana_descartar", _descartar_byte_invalido)
codecs.register(_codec_do_set)

ERRO_BITS = (
    "O motor Firebird do sistema é de {arquitetura} e o programa que lê o banco é de "
    "{bits} bits; por isso a cópia do backup não abre. Rode a atualização de novo: o "
    "instalador troca o motor por um de 64 bits."
)


class ErroFonte(Exception):
    """Falha ao preparar ou ler a cópia do banco, com explicação para quem opera."""


@dataclass
class Extracao:
    data_corte: date
    dias_abertos_12m: int
    dias_abertos_90d: int
    produtos: list = field(default_factory=list)
    lancamentos: list = field(default_factory=list)
    clientes: list = field(default_factory=list)
    fichas_fornecedor: list = field(default_factory=list)
    compras: list = field(default_factory=list)
    vendas: list = field(default_factory=list)
    caixas: list = field(default_factory=list)
    # (codigo, ano, mes, unidades, receita) de cinco anos: a base da comparação com o
    # mesmo período dos anos anteriores, produto a produto.
    vendas_por_mes: list = field(default_factory=list)
    # O dia 1º do mês mais antigo que `vendas_por_mes` traz. Quem compara períodos precisa
    # saber onde o histórico começa para não usar um mês pela metade como mês inteiro.
    mes_a_mes_desde: date | None = None
    detalhe: dict = field(default_factory=dict)


def _primeiro_dia_de_meses_atras(corte, meses):
    """O dia 1º do mês que fica `meses` meses antes do mês do corte.

    A leitura mês a mês precisa começar numa virada de mês. Começar em "corte menos N
    dias" deixa o mês mais antigo pela metade, e quem compara um período com o mesmo
    período do ano anterior usa esse meio mês como mês inteiro.
    """
    total = corte.year * 12 + (corte.month - 1) - int(meses)
    return date(total // 12, total % 12 + 1, 1)


def _decimal(valor):
    if valor is None:
        return None
    return valor if isinstance(valor, Decimal) else Decimal(str(valor))


def _centavos(valor):
    """Arredonda para centavo como o banco faria, e não como o Python faria sozinho."""
    return valor.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _nada(etapa, progresso):
    """Relator de progresso padrão: não faz nada."""


def _extrair_do_zip(origem, pasta_trabalho, progresso):
    """Tira do .zip o banco que está lá dentro e devolve o caminho dele.

    O backup da Cabana é gerado compactado (Set-Cabana-FULL.zip). Dentro vem o
    .FDB ou o .FBK; quando há mais de um, vale o maior, que é o banco da loja.
    Só o nome do arquivo é usado para gravar, nunca o caminho de dentro do zip.
    """
    progresso("Abrindo o backup compactado", 8)
    try:
        with zipfile.ZipFile(origem) as pacote:
            candidatos = [
                item for item in pacote.infolist()
                if not item.is_dir() and Path(item.filename).suffix.lower() in (".fdb", ".fbk")
            ]
            if not candidatos:
                dentro = ", ".join(sorted({Path(i.filename).suffix.lower() or "sem extensão"
                                           for i in pacote.infolist()})) or "nada"
                raise ErroFonte(
                    f"O backup {origem.name} está compactado, mas não tem nenhum arquivo .FDB ou .FBK "
                    f"dentro (encontrei: {dentro}). Confira se é o backup do banco do SET."
                )
            escolhido = max(candidatos, key=lambda item: item.file_size)
            destino = pasta_trabalho / Path(escolhido.filename).name
            progresso(f"Descompactando {destino.name}", 12)
            with pacote.open(escolhido) as dentro_do_zip, open(destino, "wb") as saida:
                shutil.copyfileobj(dentro_do_zip, saida)
    except zipfile.BadZipFile as erro:
        raise ErroFonte(
            f"Não consegui abrir o backup compactado {origem.name}; o arquivo pode estar "
            f"incompleto ou ter sido gravado pela metade ({erro})."
        ) from erro
    return destino


def preparar_copia(origem, pasta_trabalho, cliente_gbak=None, progresso=_nada):
    """Deixa pronta, em pasta_trabalho, uma cópia .FDB que pode ser lida à vontade.

    Aceita o backup em .FDB (copia o arquivo), em .FBK (restaura com gbak) ou em
    .ZIP com um dos dois dentro. Devolve o caminho da cópia, nunca o da origem.
    """
    origem = Path(origem)
    if not origem.is_file():
        raise ErroFonte(f"Não encontrei o arquivo de origem: {origem}")
    pasta_trabalho = Path(pasta_trabalho)
    pasta_trabalho.mkdir(parents=True, exist_ok=True)
    copia = pasta_trabalho / "set.fdb"
    if copia.exists():
        copia.unlink()

    if origem.suffix.lower() == ".zip":
        extraido = _extrair_do_zip(origem, pasta_trabalho, progresso)
        if extraido.suffix.lower() == ".fdb" and extraido != copia:
            extraido.replace(copia)
            progresso("Cópia pronta", 40)
            return copia
        origem = extraido  # .FBK: segue para a restauração com o gbak

    if origem.suffix.lower() == ".fbk":
        progresso("Restaurando o backup", 15)
        if not cliente_gbak:
            raise ErroFonte(
                "O backup está em .FBK e precisa ser restaurado pelo gbak. "
                "Defina CABANA_FIREBIRD_GBAK com o caminho do gbak."
            )
        comando = [str(cliente_gbak), "-replace_database", "-user", "SYSDBA", "-password", "masterkey",
                   str(origem), str(copia)]
        resultado = subprocess.run(comando, capture_output=True, text=True)  # noqa: S603
        if resultado.returncode != 0 or not copia.exists():
            raise ErroFonte(f"gbak não conseguiu restaurar o backup: {resultado.stderr.strip()[:500]}")
        progresso("Cópia pronta", 40)
        return copia

    progresso("Copiando o backup", 15)
    shutil.copy2(origem, copia)
    progresso("Cópia pronta", 40)
    return copia


def _arquitetura_do_pe(caminho):
    """Diz se um .dll do Windows é de 64 ou de 32 bits, lendo o cabeçalho PE.

    Devolve None quando não dá para saber (outro sistema operacional, arquivo
    inacessível ou formato diferente), e aí a conferência simplesmente não acontece.
    """
    try:
        with open(caminho, "rb") as arquivo:
            arquivo.seek(0x3C)
            (inicio,) = struct.unpack("<I", arquivo.read(4))
            arquivo.seek(inicio + 4)
            (maquina,) = struct.unpack("<H", arquivo.read(2))
    except (OSError, struct.error):
        return None
    return ARQUITETURAS_PE.get(maquina)


def _conferir_arquitetura(biblioteca_cliente):
    """Barra, com explicação, o motor Firebird de bits diferentes do Python.

    O Firebird que acompanha o SET costuma ser de 32 bits e o Python deste sistema é de
    64; carregar um no outro dá "[WinError 193] %1 não é um aplicativo Win32 válido",
    mensagem que não diz nada para quem está na gerência.
    """
    arquitetura = _arquitetura_do_pe(biblioteca_cliente)
    bits = 64 if sys.maxsize > 2**32 else 32
    if arquitetura and arquitetura != f"{bits} bits":
        raise ErroFonte(ERRO_BITS.format(arquitetura=arquitetura, bits=bits))


def _conectar(copia, biblioteca_cliente):
    try:
        from firebird.driver import connect, driver_config
    except ImportError as erro:  # pragma: no cover - depende do pacote instalado
        raise ErroFonte(
            "A biblioteca firebird-driver não está instalada neste servidor; "
            "sem ela a leitura da cópia do banco não funciona."
        ) from erro
    if biblioteca_cliente:
        _conferir_arquitetura(biblioteca_cliente)
        driver_config.fb_client_library.value = str(biblioteca_cliente)
    try:
        conexao = connect(str(copia), user="SYSDBA", password="masterkey", charset="NONE")
    except Exception as erro:  # noqa: BLE001 - o driver lança tipos variados
        if getattr(erro, "winerror", None) == 193 or "WinError 193" in str(erro):
            # O Windows recusou carregar a DLL: é motor de bits diferentes do Python.
            arquitetura = _arquitetura_do_pe(biblioteca_cliente) or "32 bits"
            bits = 64 if sys.maxsize > 2**32 else 32
            raise ErroFonte(ERRO_BITS.format(arquitetura=arquitetura, bits=bits)) from erro
        raise ErroFonte(f"Não consegui abrir a cópia do banco: {erro}") from erro
    # NONE entrega os bytes como estão gravados; quem escolhe a tabela é CODIFICACAO_SET,
    # que tenta UTF-8 e cai para cp1252, sem parar por byte inválido.
    conexao._encoding = CODIFICACAO_SET
    att = getattr(conexao, "_att", None)
    if att is not None:
        att.encoding = CODIFICACAO_SET
    return conexao


def _texto(valor, limite=200):
    return (valor or "").strip()[:limite]


def _ler_financeiro(linhas, corte):
    """Contas a pagar e a receber do SET, uma linha por parcela.

    Entra tudo o que ainda está em aberto, porque é o que ainda mexe no caixa, mais o que
    foi pago ou recebido dentro da janela. O SET guarda a conta já classificada no plano de
    contas dele (GRUPO traz "1.01.05 - Aluguel"), então a classificação vem pronta: o
    sistema não inventa categoria nenhuma.
    """
    desde = corte - timedelta(days=JANELA_FINANCEIRO_DIAS)
    lancamentos = []
    for tipo, tabela, chave, coluna_parte, coluna_origem in (
        ("pagar", "contaspag", "idcontapag", "fornecedor", "idcompra"),
        ("receber", "contasrec", "idcontarec", "cliente", "idvenda"),
    ):
        for (id_set, nome, documento, parcela, situacao, cadastro, vencimento, pagamento,
             valor, valor_pago, grupo, forma, parte, origem, plano) in linhas(f"""
            select c.{chave}, c.nomeconta, c.ndoc, c.parcela, c.situacao, c.datacad,
                   c.datavencto, c.datapag, c.valor, c.valorpag, c.grupo, c.formapagto,
                   c.{coluna_parte}, c.{coluna_origem}, p.tipo
            from {tabela} c
            left join planodeconta p on p.idplanoconta = c.idplanoconta
            where c.empresa = ? and (c.datapag is null or c.datapag > ?)
        """, (EMPRESA, desde)):
            lancamentos.append({
                "tipo": tipo,
                "id_set": int(id_set or 0),
                "descricao": _texto(nome),
                "documento": _texto(documento, 60),
                "parcela": _texto(parcela, 20),
                "situacao_set": _texto(situacao, 40),
                "grupo": _texto(grupo, 120) or "SEM CLASSIFICAÇÃO",
                "tipo_plano": _texto(plano, 40),
                "contraparte": _texto(parte),
                "forma_pagamento": _texto(forma, 40),
                "cadastrado_em": cadastro,
                "vencimento": vencimento,
                "pagamento": pagamento,
                "valor": _decimal(valor) or Decimal("0"),
                "valor_pago": _decimal(valor_pago) or Decimal("0"),
                "origem_set": int(origem or 0),
            })
    return lancamentos


def _ler_compras(linhas):
    """As compras do SET, cabeçalho e itens, para a tela de compras por fornecedor.

    São poucas (338 na cópia de 20/09/2026, com 7.398 linhas de item), então entram
    inteiras: é o que responde "quando foi a última compra deste fornecedor e o que veio
    nela". Compra com situação Pendente é mercadoria a caminho e fica marcada como tal,
    pela mesma razão de sempre: não é compra feita.
    """
    compras = {}
    for (id_set, numero, fornecedor, comprador, situacao, pedido, nota, entrega,
         valor_produtos, valor_total, nota_fiscal) in linhas("""
        select c.idcompra, c.ncompra, c.fornecedor, c.comprador, c.situacao, c.datapedido,
               c.nfdata, c.dataentrega, c.vlprod, c.vltotal, c.nfentrada
        from compras c where c.empresa = ?
    """, (EMPRESA,)):
        chave = _texto(numero, 40)
        compras[chave] = {
            "id_set": int(id_set or 0),
            "numero": chave,
            "fornecedor": _texto(fornecedor),
            "comprador": _texto(comprador),
            "situacao": _texto(situacao, 40),
            "pendente": _texto(situacao, 40) == SITUACAO_PENDENTE,
            "data_pedido": pedido,
            "data_nota": nota,
            "data_entrega": entrega,
            "valor_produtos": _decimal(valor_produtos) or Decimal("0"),
            "valor_total": _decimal(valor_total) or Decimal("0"),
            "nota_fiscal": _texto(nota_fiscal, 40),
            "linhas": [],
        }

    for numero, codigo, descricao, quantidade, custo_unitario, custo_total in linhas("""
        select i.ncompra, i.nprod, i.descricao, i.qtde, i.custoun, i.custototal
        from icompra i where i.empresa = ?
    """, (EMPRESA,)):
        compra = compras.get(_texto(numero, 40))
        if compra is None:
            continue  # item sem cabeçalho: já contado no log como órfão
        compra["linhas"].append({
            "codigo": _texto(codigo, 60),
            "descricao": _texto(descricao),
            "quantidade": _decimal(quantidade) or Decimal("0"),
            "custo_unitario": _decimal(custo_unitario) or Decimal("0"),
            "custo_total": _decimal(custo_total) or Decimal("0"),
        })
    for compra in compras.values():
        compra["itens"] = len(compra["linhas"])
    return sorted(compras.values(), key=lambda c: c["id_set"])


def _ler_itens_de_venda(linhas, inicio, produtos):
    """O que saiu em cada venda: produto, quantidade, valor e o custo daquele dia.

    São 32 mil linhas em 12 meses na cópia de 20/09/2026, e é a única forma de responder
    "o que a loja vendeu hoje e quanto sobrou disso". O produto importado não responde:
    ele guarda a soma de 12 meses, não o dia.

    O custo lido é o IVENDAS.PRECOCUSTO, o que o produto custava no dia da venda, e não o
    custo de hoje — é com ele que o lucro do dia é o lucro que a loja realizou.

    Em 1.608 dos 32.034 itens ele está vazio, e não espalhado: até 24/08/2026 falta em
    0,5% dos itens, de 25/08/2026 em diante falta em 70% a 100% deles, todo dia. Alguma
    coisa mudou no SET nesse dia. Como é justamente o período que a loja abre na tela,
    cada item leva também o custo do CADASTRO no momento da importação, que cobre 90%
    desses casos e entra como estimativa marcada. Produto que saiu do cadastro fica sem
    custo nenhum e fora da conta do lucro.

    LGPD: aqui não há nada de cliente. Produto, quantidade, valor e custo.
    """
    por_venda = {}
    for id_venda, codigo, quantidade, valor, custo in linhas("""
        select v.idvenda, i.nprod, i.qtde, i.valortotal, i.precocusto
        from ivendas i
        join vendas v on v.nvenda = i.nvenda and v.empresa = i.empresa
        where v.empresa = ? and v.status <> 'Estornado' and v.datavenda > ?
    """, (EMPRESA, inicio)):
        quantidade = _decimal(quantidade) or Decimal("0")
        custo_unitario = _decimal(custo)
        if not custo_unitario or custo_unitario <= 0:
            custo_unitario = None
        ficha = produtos.get(codigo) or {}
        do_cadastro = ficha.get("custo")
        if not do_cadastro or do_cadastro <= 0:
            do_cadastro = None
        por_venda.setdefault(int(id_venda or 0), []).append({
            "codigo": codigo,
            "descricao": ficha.get("descricao", ""),
            "grupo": ficha.get("grupo", ""),
            "quantidade": quantidade,
            "valor_total": _decimal(valor) or Decimal("0"),
            "custo_unitario": custo_unitario,
            "custo_total": _centavos(quantidade * custo_unitario) if custo_unitario else None,
            "custo_cadastro_unitario": do_cadastro,
            "custo_estimado_total": _centavos(quantidade * do_cadastro) if do_cadastro else None,
        })
    return por_venda


def _ler_vendas(linhas, inicio):
    """As vendas dos últimos 12 meses, uma a uma, para o ticket médio.

    São 16 mil linhas na cópia de 20/09/2026, leves porque só vêm seis colunas. Venda a
    venda, e não a soma do mês, é o que permite filtrar por forma de pagamento, vendedor
    e dia da semana depois, sem reimportar nada.

    LGPD: a tabela tem NOMECLI, COMPRADOR e COMPRADOR_CPF, e nenhum deles é lido aqui.
    O vendedor é gente da loja, não cliente, e é o que a gerência pede para comparar.

    Venda estornada fica de fora, como em todo o resto do sistema: ela foi desfeita e
    contá-la puxaria o ticket médio para baixo sem motivo.
    """
    vendas = []
    for id_set, numero, data, hora, valor, desconto, forma, vendedor in linhas("""
        select v.idvenda, v.nvenda, v.datavenda, v.horavenda, v.totalvenda, v.totaldesc,
               v.formapagto, v.vendedor
        from vendas v
        where v.empresa = ? and v.status <> 'Estornado' and v.datavenda > ?
    """, (EMPRESA, inicio)):
        if data is None:
            continue
        vendas.append({
            "id_set": int(id_set or 0),
            "numero": _texto(numero, 40),
            "data": data,
            "hora": _texto(hora, 8),
            # 0 é domingo, igual ao extract(weekday) do Firebird; em Python a semana
            # começa na segunda, daí a conta.
            "dia_da_semana": (data.weekday() + 1) % 7,
            "valor": _decimal(valor) or Decimal("0"),
            "desconto": _decimal(desconto) or Decimal("0"),
            "forma_pagamento": _texto(forma, 60),
            "vendedor": _texto(vendedor),
        })
    return vendas


# Códigos de TIPO em ICAIXA, lidos da cópia de 20/09/2026: I é o saldo inicial do turno,
# R recebimento de venda, S sangria, P pagamento e E entrada de dinheiro. "Estornado" é o
# movimento desfeito, que não entra em soma nenhuma.
TIPOS_DO_MOVIMENTO = {"E": "entrada", "S": "sangria", "P": "pagamento"}


def _ler_caixas(linhas):
    """Os turnos de caixa do SET, com os movimentos de cada um já somados.

    O que vem linha a linha são só os movimentos que não são venda (sangria, pagamento e
    entrada): são 3.975 contra 43.945 recebimentos, e são os que alguém confere quando o
    caixa não fecha. O recebimento entra somado, e por forma de pagamento, porque a venda
    em si o sistema já guarda em VendaImportada.

    Conferido na cópia de 20/09/2026: saldo inicial + recebimentos + entradas - sangrias
    - pagamentos dá exatamente o SALDOFINAL que o SET gravou (turno 970: 379,40 + 8.067,50
    - 266,25 = 8.180,65). É essa conta que a tela usa para dizer se o caixa fecha.
    """
    caixas = {}
    for (id_set, operador, abertura, fechamento, inicial, final,
         observacao, status, tipo, quem_fechou) in linhas("""
        select c.idcaixa, c.usuario, c.dataabertura, c.datafechamento, c.saldoinicial,
               c.saldofinal, c.observacao, c.status, c.tipo, c.usuariofechamento
        from caixa c where c.empresa = ?
    """, (EMPRESA,)):
        if abertura is None:
            continue
        numero = int(id_set or 0)
        aberto = (status or "").strip().lower().startswith("abert")
        caixas[numero] = {
            "id_set": numero,
            "operador": _texto(operador),
            "operador_fechamento": _texto(quem_fechou),
            "dia": abertura.date(),
            "aberto_em": abertura,
            "fechado_em": fechamento,
            "saldo_inicial": _dinheiro(inicial),
            # Caixa aberto não tem saldo final, e zero aqui mentiria: fica vazio.
            "saldo_final": None if aberto else _dinheiro(final),
            "situacao": "aberto" if aberto else "fechado",
            "tipo": _texto(tipo, 50),
            "observacao": _texto(observacao, 255),
            "recebido": Decimal("0"), "entradas": Decimal("0"), "sangrias": Decimal("0"),
            "pagamentos": Decimal("0"), "estornado": Decimal("0"), "movimentos": 0,
            "por_forma": {},
            "lancamentos": [],
        }

    for (id_movimento, id_caixa, quando, descricao, grupo, valor,
         operador, forma, tipo) in linhas("""
        select i.idicaixa, i.idcaixa, i.data, i.descricao, i.grupo, i.valor,
               i.usuario, i.formapagto, i.tipo
        from icaixa i where i.empresa = ?
    """, (EMPRESA,)):
        caixa = caixas.get(int(id_caixa or 0))
        if caixa is None or quando is None:
            continue
        quanto = _dinheiro(valor)
        marca = (tipo or "").strip()
        if marca == "Estornado":
            caixa["estornado"] += quanto
            continue
        if marca == "I":
            continue  # é o saldo inicial, que já veio do cabeçalho do turno
        caixa["movimentos"] += 1
        if marca == "R":
            caixa["recebido"] += quanto
            nome = _texto(forma, 50) or "sem forma"
            caixa["por_forma"][nome] = str(Decimal(caixa["por_forma"].get(nome, "0")) + quanto)
            continue
        nosso = TIPOS_DO_MOVIMENTO.get(marca)
        if nosso is None:
            continue
        caixa[{"entrada": "entradas", "sangria": "sangrias",
               "pagamento": "pagamentos"}[nosso]] += quanto
        caixa["lancamentos"].append({
            "id_set": int(id_movimento or 0),
            "quando": quando,
            "tipo": nosso,
            "descricao": _texto(descricao, 150),
            "grupo": _texto(grupo, 100),
            "valor": quanto,
            "operador": _texto(operador, 50),
            "forma_pagamento": _texto(forma, 50),
        })
    return sorted(caixas.values(), key=lambda c: c["aberto_em"], reverse=True)


def _dinheiro(valor):
    """Valor do SET em reais, com duas casas. O SET guarda em ponto flutuante."""
    return (_decimal(valor) or Decimal("0")).quantize(Decimal("0.01"))


def _ler_fichas_de_fornecedor(linhas):
    """Ficha cadastral do fornecedor, como o SET guarda.

    Aqui o CNPJ e a inscrição estadual entram, ao contrário do cadastro de clientes: são
    o que se confere na nota da compra. Dado de pessoa física do cadastro (RG, data de
    nascimento, dados bancários) fica de fora, que não é assunto da loja.

    O que liga esta ficha ao resto do sistema é a razão social, porque é o nome que o SET
    grava na compra e, por tabela, no produto.
    """
    fichas = []
    for (id_set, codigo, razao, fantasia, tipo, cnpj, ie, fone1, fone2, email, site,
         contato, contato_fone, endereco, numero, bairro, cidade, uf, cep, status,
         observacoes) in linhas("""
        select idfornecedor, cod, razao, fantasia, tipo, cnpjcpf, ie, fone1, fone2,
               email1, site, cont1nome, cont1fone, endereco, numero, bairro, cidade,
               uf, cep, status, observacoes
        from fornecedores
    """):
        fichas.append({
            "id_set": int(id_set or 0),
            "codigo": _texto(codigo, 20),
            "razao": _texto(razao),
            "fantasia": _texto(fantasia),
            "pessoa_juridica": _texto(tipo, 1).upper() != "F",
            "cnpj_cpf": _texto(cnpj, 25),
            "inscricao_estadual": _texto(ie, 30),
            "telefone": _texto(fone1, 60),
            "telefone_2": _texto(fone2, 60),
            "email": _texto(email, 150),
            "site": _texto(site, 150),
            "contato": _texto(contato, 120),
            "contato_telefone": _texto(contato_fone, 60),
            "endereco": _texto(endereco),
            "numero": _texto(numero, 20),
            "bairro": _texto(bairro, 100),
            "cidade": _texto(cidade, 80),
            "uf": _texto(uf, 2).upper(),
            "cep": _texto(cep, 15),
            "situacao": _texto(status, 30),
            "observacoes": _texto(observacoes, 2000),
        })
    return fichas


def _ler_clientes(linhas, corte):
    """Cadastro de clientes com o que cada um comprou. Só o que a loja precisa ver.

    A tabela CLIENTES do SET tem CPF, RG, nome dos pais, renda do cônjuge e mais de cem
    colunas. Nada disso entra aqui: o sistema guarda nome, cidade, estado, data de cadastro
    e o que a pessoa comprou. É o bastante para a loja saber quem compra e é o mínimo que a
    LGPD pede (docs/leitura-firebird.md).

    O código do cliente na venda é o COD do cadastro, não o IDCLIENTE, e o balcão lança
    quase tudo no cliente genérico CONSUMIDOR FINAL, que fica marcado para não parecer o
    maior cliente da loja.
    """
    inicio_12m = corte - timedelta(days=JANELA_12M)
    compras = {}
    for codigo, quantidade, valor, ultima, valor_12m in linhas("""
        select trim(v.idcliente), count(*), sum(v.totalvenda), max(v.datavenda),
               sum(case when v.datavenda > ? then v.totalvenda else 0 end)
        from vendas v
        where v.empresa = ? and v.status <> 'Estornado' and trim(coalesce(v.idcliente, '')) <> ''
        group by 1
    """, (inicio_12m, EMPRESA)):
        compras[codigo] = (int(quantidade or 0), _decimal(valor) or Decimal("0"), ultima,
                           _decimal(valor_12m) or Decimal("0"))

    clientes = []
    for id_set, codigo, razao, fantasia, tipo, cidade, uf, cadastro, bloqueado in linhas("""
        select idcliente, cod, razao, fantasia, tipo, cidade, uf, datacad, bloqueado
        from clientes
    """):
        codigo = _texto(codigo, 20)
        quantidade, valor, ultima, valor_12m = compras.get(codigo, (0, Decimal("0"), None, Decimal("0")))
        nome = _texto(razao) or _texto(fantasia)
        clientes.append({
            "id_set": int(id_set or 0),
            "codigo": codigo,
            "nome": nome,
            "pessoa_juridica": _texto(tipo, 1).upper() == "J",
            "cidade": _texto(cidade, 80),
            "uf": _texto(uf, 2).upper(),
            "cadastrado_em": cadastro,
            "bloqueado": _texto(bloqueado, 10).upper().startswith("S"),
            "generico": nome.upper().startswith("CONSUMIDOR"),
            "compras": quantidade,
            "valor_comprado": valor,
            "valor_comprado_12m": valor_12m,
            "ultima_compra": ultima,
        })
    return clientes


def extrair(copia, biblioteca_cliente=None, progresso=_nada) -> Extracao:
    """Lê a cópia e devolve os números por produto. Só SELECT."""
    progresso("Abrindo a cópia", 45)
    _descartados["bytes"] = 0
    conexao = _conectar(copia, biblioteca_cliente)
    try:
        cursor = conexao.cursor()

        def linhas(sql, parametros=()):
            cursor.execute(sql, list(parametros))
            return cursor.fetchall()

        ultima_venda = linhas(
            "select max(datavenda) from vendas where empresa = ? and status <> 'Estornado'", (EMPRESA,)
        )[0][0]
        if ultima_venda is None:
            raise ErroFonte("A cópia não tem nenhuma venda registrada; confira se o backup é o do SET da loja.")
        corte = ultima_venda if isinstance(ultima_venda, date) else ultima_venda.date()
        inicio_12m = corte - timedelta(days=JANELA_12M)
        inicio_90d = corte - timedelta(days=JANELA_90D)

        progresso("Lendo os produtos", 50)
        produtos = {}
        for (codigo, descricao, grupo, custo, compra, venda, qtdemin, situacao,
             estoque, reservado, codigo_barras, plucro) in linhas("""
            select p.nprod, p.descricao, p.grupo, p.precocusto, p.precocompra, p.precovenda,
                   p.qtdemin, p.situacao, pe.qtde, pe.qtde_reservado, p.codbarras, p.plucro
            from produtos p
            left join produtos_estoque pe on pe.idproduto = p.idproduto and pe.empresa = ?
        """, (EMPRESA,)):
            custo_valido = _decimal(custo) if custo and custo > 0 else (_decimal(compra) if compra and compra > 0 else None)
            produtos[codigo] = {
                "codigo": codigo,
                "descricao": (descricao or "").strip()[:200],
                "grupo": (grupo or "SEM GRUPO").strip().upper()[:100],
                "situacao_set": (situacao or "").strip()[:40],
                "codigo_barras": (codigo_barras or "").strip()[:40],
                "custo": custo_valido,
                "preco_venda": _decimal(venda),
                # PLUCRO é o "% de lucro" do cadastro do SET. Apesar do nome, é markup
                # sobre o custo e não margem sobre a venda: confere com
                # (precovenda / precocusto - 1) x 100 em 10.759 dos 10.764 produtos que
                # têm os três campos. Vem para o sistema poder mostrar lado a lado o que
                # está escrito no SET e o que o preço de hoje realmente dá.
                "markup_set": _decimal(plucro) if plucro and plucro > 0 else None,
                "estoque_minimo_set": _decimal(qtdemin),
                "estoque": _decimal(estoque) or Decimal("0"),
                "reservado": _decimal(reservado) or Decimal("0"),
                "vendas_12m": Decimal("0"),
                "vendas_90d": Decimal("0"),
                "receita_12m": Decimal("0"),
                "custo_vendido_12m": Decimal("0"),
                "receita_com_custo_12m": Decimal("0"),
                "compras_12m": Decimal("0"),
                "valor_compras_12m": Decimal("0"),
                "pedido_em_aberto": Decimal("0"),
                "ultima_venda": None,
                "ultima_compra": None,
                "fornecedor": "",
                "prazo_reposicao_dias": None,
                "prazo_estimado": False,
            }

        progresso("Lendo as vendas", 60)
        # O item da venda guarda o custo que o produto tinha no dia (IVENDAS.PRECOCUSTO):
        # é com ele que se calcula a margem que a loja REALIZOU, e não a que o cadastro de
        # hoje promete. Em 1.608 dos 32.034 itens de 12 meses esse custo está vazio, então
        # a receita dos itens que têm custo vem separada: a margem realizada é calculada
        # sobre o pedaço comparável, em vez de sair otimista.
        for codigo, q12, q90, receita, custo_vendido, receita_com_custo, ultima in linhas("""
            select i.nprod,
                   sum(case when v.datavenda > ? then i.qtde else 0 end),
                   sum(case when v.datavenda > ? then i.qtde else 0 end),
                   sum(case when v.datavenda > ? then i.valortotal else 0 end),
                   sum(case when v.datavenda > ? then i.qtde * coalesce(i.precocusto, 0) else 0 end),
                   sum(case when v.datavenda > ? and coalesce(i.precocusto, 0) > 0
                            then i.valortotal else 0 end),
                   max(v.datavenda)
            from ivendas i
            join vendas v on v.nvenda = i.nvenda and v.empresa = i.empresa
            where v.empresa = ? and v.status <> 'Estornado'
            group by i.nprod
        """, (inicio_12m, inicio_90d, inicio_12m, inicio_12m, inicio_12m, EMPRESA)):
            item = produtos.get(codigo)
            if item:
                item.update(
                    vendas_12m=_decimal(q12) or Decimal("0"),
                    vendas_90d=_decimal(q90) or Decimal("0"),
                    receita_12m=_decimal(receita) or Decimal("0"),
                    custo_vendido_12m=_decimal(custo_vendido) or Decimal("0"),
                    receita_com_custo_12m=_decimal(receita_com_custo) or Decimal("0"),
                    ultima_venda=ultima,
                )

        progresso("Lendo as compras", 70)
        for codigo, quantidade, valor, ultima in linhas("""
            select i.nprod,
                   sum(case when coalesce(c.nfdata, c.datapedido) > ? then i.qtde else 0 end),
                   sum(case when coalesce(c.nfdata, c.datapedido) > ? then i.custototal else 0 end),
                   max(coalesce(c.nfdata, c.datapedido))
            from icompra i
            join compras c on c.ncompra = i.ncompra and c.empresa = i.empresa
            where c.empresa = ? and c.situacao <> ?
            group by i.nprod
        """, (inicio_12m, inicio_12m, EMPRESA, SITUACAO_PENDENTE)):
            item = produtos.get(codigo)
            if item:
                item.update(
                    compras_12m=_decimal(quantidade) or Decimal("0"),
                    valor_compras_12m=_decimal(valor) or Decimal("0"),
                    ultima_compra=ultima,
                )

        # Pedido de compra ainda não recebido: mercadoria a caminho. Entra no cálculo do que
        # falta comprar para a loja não comprar duas vezes a mesma coisa.
        progresso("Lendo os pedidos em aberto", 74)
        pendentes = 0
        for codigo, quantidade in linhas("""
            select i.nprod, sum(i.qtde)
            from icompra i
            join compras c on c.ncompra = i.ncompra and c.empresa = i.empresa
            where c.empresa = ? and c.situacao = ?
            group by i.nprod
        """, (EMPRESA, SITUACAO_PENDENTE)):
            item = produtos.get(codigo)
            if item:
                item["pedido_em_aberto"] = _decimal(quantidade) or Decimal("0")
                pendentes += 1

        # Prazo de reposição: mediana de (entrega - pedido) por fornecedor. Fornecedor com
        # uma única compra não forma mediana; nesse caso vale a mediana geral da loja, e o
        # produto fica marcado como prazo estimado para o painel avisar.
        progresso("Calculando prazos de entrega", 78)
        prazos = {}
        for fornecedor, pedido, entrega in linhas("""
            select fornecedor, datapedido, dataentrega from compras
            where empresa = ? and situacao <> ? and datapedido is not null and dataentrega is not null
        """, (EMPRESA, SITUACAO_PENDENTE)):
            dias = (entrega - pedido).days
            if 0 <= dias <= PRAZO_MAXIMO_PLAUSIVEL:
                prazos.setdefault((fornecedor or "").strip(), []).append(dias)
        prazo_por_fornecedor = {f: int(statistics.median(d)) for f, d in prazos.items() if len(d) >= 2}
        todos_os_prazos = [dias for lista in prazos.values() for dias in lista]
        prazo_geral = int(statistics.median(todos_os_prazos)) if todos_os_prazos else None

        # Fornecedor da última compra de cada produto (a consulta vem em ordem de compra).
        for codigo, fornecedor in linhas("""
            select i.nprod, c.fornecedor from icompra i
            join compras c on c.ncompra = i.ncompra and c.empresa = i.empresa
            where c.empresa = ? order by c.idcompra
        """, (EMPRESA,)):
            item = produtos.get(codigo)
            if item:
                nome = (fornecedor or "").strip()
                item["fornecedor"] = nome[:200]
                prazo = prazo_por_fornecedor.get(nome)
                item["prazo_reposicao_dias"] = prazo if prazo is not None else prazo_geral
                item["prazo_estimado"] = prazo is None and prazo_geral is not None

        dias_12m = linhas("""
            select count(distinct datavenda) from vendas
            where empresa = ? and status <> 'Estornado' and datavenda > ?
        """, (EMPRESA, inicio_12m))[0][0]
        dias_90d = linhas("""
            select count(distinct datavenda) from vendas
            where empresa = ? and status <> 'Estornado' and datavenda > ?
        """, (EMPRESA, inicio_90d))[0][0]

        # Linhas de item sem o cabeçalho correspondente existem no SET e ficam de fora das
        # somas (o join as descarta). Ficam contadas no log para a diferença não assustar.
        orfaos_compra = linhas("""
            select count(*) from icompra i
            where not exists (select 1 from compras c where c.ncompra = i.ncompra and c.empresa = i.empresa)
        """)[0][0]
        orfaos_venda = linhas("""
            select count(*) from ivendas i
            where not exists (select 1 from vendas v where v.nvenda = i.nvenda and v.empresa = i.empresa)
        """)[0][0]

        progresso("Lendo contas a pagar e a receber", 80)
        lancamentos = _ler_financeiro(linhas, corte)
        progresso("Lendo as fichas dos fornecedores", 80)
        fichas_fornecedor = _ler_fichas_de_fornecedor(linhas)
        progresso("Lendo as compras uma a uma", 81)
        compras_do_set = _ler_compras(linhas)
        progresso("Lendo as vendas uma a uma", 82)
        vendas_do_set = _ler_vendas(linhas, inicio_12m)
        # O item vem junto da venda, e não solto, porque ele só faz sentido com a data e a
        # hora dela: é o cabeçalho que diz de que dia é o lucro.
        itens_por_venda = _ler_itens_de_venda(linhas, inicio_12m, produtos)
        for venda in vendas_do_set:
            venda["linhas"] = itens_por_venda.get(venda["id_set"], [])

        progresso("Lendo os clientes", 82)
        clientes = _ler_clientes(linhas, corte)

        progresso("Lendo os caixas", 83)
        caixas = _ler_caixas(linhas)

        progresso("Somando a venda de cada produto por mês", 83)
        # Produto a produto e mês a mês, cinco anos. É a mesma junção da soma de 12 meses
        # lá em cima, só que separada por mês, e é o único jeito de comparar um período
        # com o mesmo dos anos anteriores sem reimportar nada. São dezenas de milhares de
        # linhas, não milhões: a loja vende 16 mil vezes por ano.
        comeco_da_comparacao = _primeiro_dia_de_meses_atras(corte, JANELA_COMPARACAO_MESES)
        vendas_por_mes = [
            {
                "codigo": _texto(codigo, 60),
                "ano": int(ano),
                "mes": int(mes),
                "unidades": _decimal(unidades) or Decimal("0"),
                "receita": _decimal(receita) or Decimal("0"),
            }
            for codigo, ano, mes, unidades, receita in linhas("""
                select i.nprod, extract(year from v.datavenda), extract(month from v.datavenda),
                       sum(i.qtde), sum(i.valortotal)
                from ivendas i
                join vendas v on v.nvenda = i.nvenda and v.empresa = i.empresa
                where v.empresa = ? and v.status <> 'Estornado' and v.datavenda >= ?
                group by 1, 2, 3
            """, (EMPRESA, comeco_da_comparacao))
            if codigo
        ]

        progresso("Somando compra e venda por mês", 84)
        desde = corte - timedelta(days=730)
        vendas_mes = [
            (int(ano), int(mes), float(valor or 0), int(n))
            for ano, mes, valor, n in linhas("""
                select extract(year from datavenda), extract(month from datavenda),
                       sum(totalvenda), count(*)
                from vendas where empresa = ? and status <> 'Estornado' and datavenda > ?
                group by 1, 2 order by 1, 2
            """, (EMPRESA, desde))
        ]
        compras_mes = [
            (int(ano), int(mes), float(valor or 0), int(n))
            for ano, mes, valor, n in linhas("""
                select extract(year from coalesce(nfdata, datapedido)),
                       extract(month from coalesce(nfdata, datapedido)), sum(vltotal), count(*)
                from compras where empresa = ? and coalesce(nfdata, datapedido) > ?
                group by 1, 2 order by 1, 2
            """, (EMPRESA, desde))
        ]
        # O mês do corte quase nunca está fechado: no dia 7, o gráfico comparava sete
        # dias deste mês com o mês inteiro do ano passado e acusava uma queda de 84% que
        # não existe. Então vem também o mesmo PEDAÇO do ano passado, do dia 1 ao mesmo
        # dia, que é a comparação que se pode fazer.
        ate_o_dia = linhas("""
            select sum(totalvenda) from vendas
            where empresa = ? and status <> 'Estornado'
              and extract(year from datavenda) = ? and extract(month from datavenda) = ?
              and extract(day from datavenda) <= ?
        """, (EMPRESA, corte.year - 1, corte.month, corte.day))[0][0]
        mes_parcial = [corte.year, corte.month, corte.day, float(ate_o_dia or 0)]

        return Extracao(
            data_corte=corte,
            mes_a_mes_desde=comeco_da_comparacao,
            dias_abertos_12m=int(dias_12m or 0),
            dias_abertos_90d=int(dias_90d or 0),
            produtos=list(produtos.values()),
            lancamentos=lancamentos,
            clientes=clientes,
            fichas_fornecedor=fichas_fornecedor,
            compras=compras_do_set,
            vendas=vendas_do_set,
            caixas=caixas,
            vendas_por_mes=vendas_por_mes,
            detalhe={
                "fornecedores_com_prazo": len(prazo_por_fornecedor),
                "prazo_geral_dias": prazo_geral,
                "produtos_com_pedido_em_aberto": pendentes,
                "compras_com_prazo_medido": len(todos_os_prazos),
                "compras_com_entrega_no_mesmo_dia": sum(1 for dias in todos_os_prazos if dias == 0),
                "itens_de_compra_sem_cabecalho": int(orfaos_compra or 0),
                "itens_de_venda_sem_cabecalho": int(orfaos_venda or 0),
                "bytes_fora_da_tabela_de_caracteres": _descartados["bytes"],
                "contas_a_pagar_em_aberto": sum(1 for l in lancamentos if l["tipo"] == "pagar" and not l["pagamento"]),
                "contas_a_receber_em_aberto": sum(1 for l in lancamentos if l["tipo"] == "receber" and not l["pagamento"]),
                "lancamentos_financeiros": len(lancamentos),
                "caixas_importados": len(caixas),
                "caixas_abertos": sum(1 for c in caixas if c["situacao"] == "aberto"),
                "fichas_de_fornecedor": len(fichas_fornecedor),
                "compras_importadas": len(compras_do_set),
                "vendas_importadas": len(vendas_do_set),
                "itens_de_venda_importados": sum(len(v["linhas"]) for v in vendas_do_set),
                "itens_de_venda_sem_custo": sum(
                    1 for v in vendas_do_set for linha in v["linhas"]
                    if linha["custo_unitario"] is None
                ),
                "itens_de_venda_com_custo_estimado": sum(
                    1 for v in vendas_do_set for linha in v["linhas"]
                    if linha["custo_unitario"] is None and linha["custo_estimado_total"] is not None
                ),
                "vendas_com_vendedor": sum(1 for v in vendas_do_set if v["vendedor"]),
                "produtos_com_codigo_de_barras": sum(1 for p in produtos.values() if p["codigo_barras"]),
                "clientes_cadastrados": sum(1 for c in clientes if not c["generico"]),
                "clientes_com_compra_12m": sum(1 for c in clientes if not c["generico"] and c["valor_comprado_12m"]),
                "vendas_por_mes_do_produto": len(vendas_por_mes),
                "vendas_mes": vendas_mes,
                "compras_mes": compras_mes,
                "mes_parcial": mes_parcial,
            },
        )
    finally:
        conexao.close()
