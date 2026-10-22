"""Certificado próprio do servidor da loja, assinado por uma autoridade da própria loja.

Por que isso existe: o navegador do celular só libera a câmera em página segura
(HTTPS) ou em localhost. Sem HTTPS, a contagem de inventário pela câmera não
funciona, por mais certo que esteja o código da tela. A loja não tem domínio nem
certificado pago, e o endereço é um IP da rede interna, então o caminho é um
certificado feito pelo próprio servidor.

O que mudou na 1.18.0 (pedido do Edson: "resolver a questão do certificado SSL").
Até a 1.17.0 o certificado era assinado por ele mesmo, e aí não existe nada que o
aparelho possa confiar: o aviso do navegador voltava a cada aparelho novo e a cada
renovação, para sempre. Agora são dois certificados:

- a **autoridade da loja** (`cabana-autoridade.crt`), que vale dez anos e é
  instalada uma vez em cada aparelho, pela tela /sistema/certificado/;
- o **certificado do servidor** (`cabana.crt`), assinado por essa autoridade e
  refeito sozinho quando está perto de vencer. Aparelho que já confia na
  autoridade aceita o certificado novo sem perguntar nada.

Duas regras de fora mandam nos prazos, e é de propósito que estão aqui:

- a Apple não confia em certificado de servidor com validade acima de 825 dias,
  mesmo com a autoridade instalada, e os navegadores recusam acima de 398. Por
  isso o do servidor vale 395 dias e se renova sozinho.
- a autoridade pode valer muito mais, porque quem a instala é uma pessoa, uma vez.

Nada aqui fala com a internet: a chave e os certificados nascem no próprio servidor.
"""

import datetime as dt
import ipaddress
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

# Validade do certificado do servidor. 395 dias fica abaixo do limite de 398 dos
# navegadores e do de 825 da Apple, com folga para a renovação acontecer.
VALIDADE_DIAS = 395
# Abaixo disso o certificado do servidor é refeito na próxima vez que o sistema sobe.
RENOVAR_COM_DIAS = 30
# A autoridade é instalada à mão em cada aparelho, então vale muito mais.
VALIDADE_AUTORIDADE_DIAS = 10 * 365
RENOVAR_AUTORIDADE_COM_DIAS = 180

NOME_CERTIFICADO = "cabana.crt"
NOME_CHAVE = "cabana.key"
NOME_AUTORIDADE = "cabana-autoridade.crt"
NOME_CHAVE_AUTORIDADE = "cabana-autoridade.key"

ORGANIZACAO = "Cabana do Jacaranda"
NOME_DA_AUTORIDADE = "Cabana do Jacaranda - autoridade da loja"


def _da_para_gravar(pasta):
    """A conta que roda o sistema consegue criar arquivo nesta pasta?"""
    try:
        pasta.mkdir(parents=True, exist_ok=True)
        teste = pasta / ".teste-de-escrita"
        teste.write_bytes(b"ok")
        teste.unlink()
        return True
    except OSError:
        return False


def _candidatas():
    """A pasta configurada e, se ela não aceitar escrita, para onde cair.

    Por que existe alternativa: no servidor da loja a pasta configurada era
    C:\cabana-sistema\config\certificado, e a conta que roda o sistema só tem leitura
    em config. O certificado nunca chegou a ser criado, a porta segura nunca subiu e o
    download da autoridade dava "Página não encontrada" — tudo calado, porque quem tenta
    criar é o servir.py e ele engole a falha para não derrubar o HTTP (visto em
    08/10/2026). A pasta dados é onde a conta do serviço escreve, então é para lá que o
    sistema cai sozinho enquanto o instalador não corrige a configuração.
    """
    configurada = os.environ.get("CABANA_CERTIFICADO_PASTA")
    programa = Path(__file__).resolve().parents[2]
    primeira = Path(configurada) if configurada else programa / "var" / "certificado"
    return [primeira, programa.parent / "dados" / "certificado", programa / "var" / "certificado"]


def pasta_padrao():
    """Onde ficam os certificados. O servir.py e a tela têm que olhar o mesmo lugar.

    Por isso a escolha é só uma conta sobre o que está no disco, sem estado guardado:
    rodando no mesmo servidor, as duas chegam sempre à mesma pasta.
    """
    candidatas = _candidatas()
    for pasta in candidatas:
        # Numa passada só e nesta ordem: a configurada ganha quando já tem o certificado
        # (ler basta) ou quando aceita escrita. Duas passadas fariam uma alternativa com
        # certificado velho ganhar da pasta certa.
        if (pasta / NOME_AUTORIDADE).is_file() or _da_para_gravar(pasta):
            return pasta
    return candidatas[0]


def enderecos_configurados():
    """Os endereços que o certificado cobre, como o cabana.env diz."""
    bruto = os.environ.get("CABANA_CERTIFICADO_NOMES", "192.168.3.254,localhost")
    return [valor.strip() for valor in bruto.split(",") if valor.strip()]


def _nomes(enderecos):
    """Separa o que é IP do que é nome de máquina, como o certificado exige."""
    from cryptography import x509

    alternativos = []
    for valor in enderecos:
        valor = (valor or "").strip()
        if not valor:
            continue
        try:
            alternativos.append(x509.IPAddress(ipaddress.ip_address(valor)))
        except ValueError:
            alternativos.append(x509.DNSName(valor))
    return alternativos


def _ler(caminho):
    from cryptography import x509

    try:
        return x509.load_pem_x509_certificate(caminho.read_bytes())
    except Exception:  # noqa: BLE001 - arquivo truncado, vazio ou de outro formato
        return None


def _vence_em(caminho):
    certificado = _ler(caminho)
    return None if certificado is None else certificado.not_valid_after_utc


def _vale_por(caminho, dias):
    """Verdadeiro quando o arquivo é um certificado que ainda dura mais que `dias`."""
    vencimento = _vence_em(caminho)
    if vencimento is None:
        return False
    return vencimento - dt.datetime.now(dt.timezone.utc) > dt.timedelta(days=dias)


def _chave_nova():
    from cryptography.hazmat.primitives.asymmetric import rsa

    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _guardar_chave(caminho, privada):
    from cryptography.hazmat.primitives import serialization

    caminho.write_bytes(privada.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ))
    try:
        caminho.chmod(0o600)  # no Windows não faz efeito; no Linux dos testes faz.
    except OSError:
        pass


def _ler_chave(caminho):
    from cryptography.hazmat.primitives import serialization

    try:
        return serialization.load_pem_private_key(caminho.read_bytes(), password=None)
    except Exception:  # noqa: BLE001 - chave truncada ou protegida por senha
        return None


def garantir_autoridade(pasta, refazer=False):
    """Devolve (certificado, chave) da autoridade da loja, criando se precisar.

    Refazer a autoridade obriga a reinstalar em todo aparelho, então só acontece
    quando o arquivo não existe, está ilegível ou está perto de vencer.
    """
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.x509.oid import NameOID

    pasta.mkdir(parents=True, exist_ok=True)
    certificado = pasta / NOME_AUTORIDADE
    chave = pasta / NOME_CHAVE_AUTORIDADE
    if (not refazer and chave.is_file() and _ler_chave(chave) is not None
            and _vale_por(certificado, RENOVAR_AUTORIDADE_COM_DIAS)):
        return certificado, chave

    agora = dt.datetime.now(dt.timezone.utc)
    privada = _chave_nova()
    identificacao = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, NOME_DA_AUTORIDADE),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, ORGANIZACAO),
    ])
    assinado = (
        x509.CertificateBuilder()
        .subject_name(identificacao)
        .issuer_name(identificacao)
        .public_key(privada.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(agora - dt.timedelta(days=1))
        .not_valid_after(agora + dt.timedelta(days=VALIDADE_AUTORIDADE_DIAS))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(x509.KeyUsage(
            digital_signature=False, content_commitment=False, key_encipherment=False,
            data_encipherment=False, key_agreement=False, key_cert_sign=True,
            crl_sign=True, encipher_only=False, decipher_only=False), critical=True)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(privada.public_key()),
                       critical=False)
        .sign(privada, hashes.SHA256())
    )
    _guardar_chave(chave, privada)
    certificado.write_bytes(assinado.public_bytes(serialization.Encoding.PEM))
    logger.info("Autoridade da loja gerada em %s", certificado)
    return certificado, chave


def _assinada_pela_autoridade(certificado, autoridade):
    """Verdadeiro quando o certificado do servidor foi assinado por esta autoridade."""
    atual = _ler(certificado)
    raiz = _ler(autoridade)
    if atual is None or raiz is None or atual.issuer != raiz.subject:
        return False
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding

    try:
        raiz.public_key().verify(
            atual.signature, atual.tbs_certificate_bytes,
            padding.PKCS1v15(), hashes.SHA256())
    except (InvalidSignature, TypeError, ValueError):
        return False
    return True


def _nomes_conferem(certificado, enderecos):
    """Verdadeiro quando o certificado já cobre todos os endereços pedidos.

    Sem isso, acrescentar um endereço no `cabana.env` não teria efeito nenhum: o
    certificado antigo continuaria valendo e o navegador recusaria o endereço novo.
    """
    from cryptography import x509

    atual = _ler(certificado)
    if atual is None:
        return False
    try:
        tem = set(atual.extensions.get_extension_for_class(
            x509.SubjectAlternativeName).value.get_values_for_type(x509.DNSName))
        tem |= {str(ip) for ip in atual.extensions.get_extension_for_class(
            x509.SubjectAlternativeName).value.get_values_for_type(x509.IPAddress)}
    except x509.ExtensionNotFound:
        return False
    pedidos = {(valor or "").strip() for valor in enderecos if (valor or "").strip()}
    return pedidos.issubset(tem)


def garantir(pasta, enderecos, refazer=False):
    """Devolve (certificado, chave) do servidor, criando ou renovando se precisar.

    Garante a autoridade da loja antes e assina o certificado do servidor com ela.
    Um certificado antigo, assinado por ele mesmo, é trocado na primeira subida
    depois da atualização: o aviso do navegador aparece uma última vez em cada
    aparelho e para de aparecer quando a autoridade é instalada.
    """
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

    arquivo_autoridade, chave_autoridade = garantir_autoridade(pasta, refazer=refazer)
    certificado = pasta / NOME_CERTIFICADO
    chave = pasta / NOME_CHAVE
    if (not refazer and certificado.is_file() and chave.is_file()
            and _vale_por(certificado, RENOVAR_COM_DIAS)
            and _assinada_pela_autoridade(certificado, arquivo_autoridade)
            and _nomes_conferem(certificado, enderecos)):
        return certificado, chave

    raiz = _ler(arquivo_autoridade)
    privada_da_autoridade = _ler_chave(chave_autoridade)
    agora = dt.datetime.now(dt.timezone.utc)
    privada = _chave_nova()
    identificacao = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, (enderecos[0] if enderecos else "cabana")),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, ORGANIZACAO),
    ])
    construtor = (
        x509.CertificateBuilder()
        .subject_name(identificacao)
        .issuer_name(raiz.subject)
        .public_key(privada.public_key())
        .serial_number(x509.random_serial_number())
        # Um dia para trás: relógio de celular adiantado em minutos não invalida.
        .not_valid_before(agora - dt.timedelta(days=1))
        .not_valid_after(agora + dt.timedelta(days=VALIDADE_DIAS))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.KeyUsage(
            digital_signature=True, content_commitment=False, key_encipherment=True,
            data_encipherment=False, key_agreement=False, key_cert_sign=False,
            crl_sign=False, encipher_only=False, decipher_only=False), critical=True)
        # A Apple exige o uso "servidor TLS" declarado; sem isso o iPhone recusa
        # mesmo com a autoridade instalada e confiada.
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(privada.public_key()),
                       critical=False)
        .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(raiz.public_key()),
                       critical=False)
    )
    alternativos = _nomes(enderecos)
    if alternativos:
        construtor = construtor.add_extension(x509.SubjectAlternativeName(alternativos), critical=False)
    assinado = construtor.sign(privada_da_autoridade, hashes.SHA256())

    _guardar_chave(chave, privada)
    certificado.write_bytes(assinado.public_bytes(serialization.Encoding.PEM))
    logger.info("Certificado do servidor gerado em %s para %s", certificado, ", ".join(enderecos))
    return certificado, chave


def descrever(pasta):
    """O que mostrar na tela do certificado: validade e impressão digital de cada um.

    Devolve um dicionário simples para a view não precisar saber de x509.
    """
    from cryptography.hazmat.primitives import hashes

    def ficha(caminho):
        atual = _ler(caminho)
        if atual is None:
            return None
        digital = atual.fingerprint(hashes.SHA256()).hex().upper()
        return {
            "arquivo": caminho.name,
            "vence_em": atual.not_valid_after_utc.date(),
            "dias": (atual.not_valid_after_utc - dt.datetime.now(dt.timezone.utc)).days,
            # Em pares, como o navegador e o Windows mostram.
            "impressao": " ".join(digital[i:i + 2] for i in range(0, len(digital), 2)),
        }

    return {
        "autoridade": ficha(pasta / NOME_AUTORIDADE),
        "servidor": ficha(pasta / NOME_CERTIFICADO),
        "pasta": str(pasta),
    }
