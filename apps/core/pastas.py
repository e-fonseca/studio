r"""Onde a atualização do Studio acontece no servidor da loja (2.2.0).

Pedido do Edson em 06/11/2026: *"manter atualização do sistema studio industrial em um
subdiretório dentro da intranet, fazer a melhor escolha e boa pratica sempre."*

O PROGRAMA continua na pasta dele, ``C:\studio-sistema``, como o da Cabana na dele: é outro
sistema, com banco, serviço e permissões próprios, e misturar com a intranet faria um
backup ou uma permissão de um encostar no outro. O que mudou foi a ATUALIZAÇÃO: o zip do
Studio chega numa subpasta dos pacotes da intranet, ``C:\intranet\pacotes\studio``, e os
comandos de atualizar e de higienizar rodam dela. É o mesmo lugar onde o Edson já põe o zip
da intranet, e a subpasta separa os dois:

- o ``atualizar.ps1`` da intranet só olha ``intranet-v*.zip`` na pasta de cima e nunca mexe
  numa subpasta que não conhece, então um zip do Studio nunca entra como intranet;
- até a 2.1.0 o texto daqui dizia ``C:\instalacao\pacote``, que é a pasta da CABANA (veio
  na cópia do sistema dela). Um zip do Studio salvo ali seria instalado por cima do
  sistema da Cabana pelo instalador dela.

Logs, downloads (o motor Firebird, quando não há internet) e o histórico de pacotes ficam
em subpastas desta, para a atualização inteira morar num lugar só.

Este é o único lugar que escreve esses caminhos: as telas e os avisos de erro leem daqui.
"""

ATUALIZACAO = r"C:\intranet\pacotes\studio"
ATUALIZAR = ATUALIZACAO + r"\atualizar.ps1"
HIGIENIZAR = ATUALIZACAO + r"\higienizar.ps1"
LOGS = ATUALIZACAO + r"\logs"
DOWNLOADS = ATUALIZACAO + r"\downloads"
HISTORICO = ATUALIZACAO + r"\historico"

# A pasta da Cabana, que o Studio nunca usa. Fica escrita para a suíte conferir que nenhum
# texto daqui volte a mandar o zip para lá.
DA_CABANA = r"C:\instalacao"
