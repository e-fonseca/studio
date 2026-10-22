# Evidências de testes

**Execução**: 05/10/2026, ambiente de desenvolvimento na nuvem (Linux), Python 3.11,
Django 5.2.17, openpyxl 3.1.5, PostgreSQL 16.14. Comando: `python manage.py test --settings=config.settings.test -v 2`.

**Resultado**: 152 testes, todos aprovados (atualizado em 06/10/2026 com a revisão do módulo de
importação, o log de cada importação, o versionamento do sistema e o aviso da sincronização diária; antes disso, a importação dos dados do
SET, o painel de compras, o progresso da importação, a explicação dos erros e a ajuda F1).

**Conferido no navegador (Chromium)**: a ajuda F1 abre em 9 passos no painel, destaca o elemento de
cada passo, navega pelo teclado e fecha com Esc sem deixar destaque para trás; a barra de progresso
mostra a etapa ("Lendo as vendas — 60%"); o erro de importação aparece com título em linguagem de
loja, explicação e os passos para resolver.

**Conferência com dados reais** (05/10/2026): a importação leu a cópia do banco enviada pelo Edson
em 13 segundos — 11.274 produtos, dados até 20/09/2026, 356 dias com venda em 12 meses. Os valores
do painel bateram com o diagnóstico entregue em planilha: R$ 231.938,13 parados sem venda,
R$ 321.740,17 de excesso, R$ 155.621,67 comprados acima da necessidade, R$ 189.041,16 comprados
além do que foi vendido (1.688 produtos) e 699 produtos em falta valendo R$ 243.499,55 de venda.

**Conferido no navegador (06/10/2026)**: a tela de Importações mostra o cartão da sincronização
diária com o horário e a pasta do backup, uma coluna de versão por execução, o log de cada
importação dentro de "Ver o log" e o link para baixá-lo em texto (`Content-Type: text/plain`,
anexo); o rodapé de todas as telas mostra "Versão 1.4.0". Com a cópia real do banco, o log registrou
as 16 linhas da execução, do backup escolhido (364,4 MB, gravado em 05/10/2026 08:34) até
"Concluída: 11274 produtos gravados, dados até 20/09/2026".

**Revisão da importação com dados reais (06/10/2026)**: reimportação da cópia do Edson depois das
correções — 11.274 produtos em 10 s, 142 produtos com pedido de compra em aberto, 95 itens de compra
e 14 de venda sem cabeçalho no SET (ignorados, agora contados no log). Efeito das correções nos
indicadores: "comprou mais do que vendeu" R$ 189.041,16 → R$ 187.333,96 (1.688 → 1.651 produtos),
"comprado acima do necessário" R$ 155.621,67 → R$ 155.437,38 e "o que comprar" R$ 77.112,78 →
R$ 76.291,31 (1.208 → 1.163 produtos, porque o que já está pedido não é comprado de novo).

**Visual e backup compactado (06/10/2026)**: importação de um `.zip` com o banco real dentro
(146,6 MB) concluída em 12 s, 11.274 produtos. Telas conferidas no Chromium em 1366px e em 390px
(celular, sem rolagem lateral): painel, lista de produtos, importações, início, entrada e a ajuda
F1. O gráfico de barras de compra e venda confere com os valores da tabela anterior.

**Não testado ainda** (depende do ambiente da Cabana): servidor Windows, proxy HTTPS, VPN,
certificado nos dispositivos, login pela intranet, uso real pela equipe.

## Conferência no navegador (Chromium, sem interface)

Servidor de desenvolvimento em `http://127.0.0.1:8000/sistema/`, usuário de demonstração
do perfil Estoque, 21 processos carregados pelo roteiro.

| Tela | Arquivo |
|---|---|
| Quadro no computador (1366 px) | [desktop-quadro.png](evidencias/desktop-quadro.png) |
| Quadro no celular (390 px) | [celular-quadro.png](evidencias/celular-quadro.png) |
| Processo com a versão 1 salva e pendências para teste | [desktop-detalhe.png](evidencias/desktop-detalhe.png) |
| Recusa de senha no procedimento | [desktop-erro-senha.png](evidencias/desktop-erro-senha.png) |

## Lista de testes

```
test_correlacao_volta_no_cabecalho_e_fica_no_evento [auditoria · AcessoAuditadoTest]
test_entrada_e_falha_registradas_sem_senha [auditoria · AcessoAuditadoTest]
test_consulta_ve_auditoria [auditoria · ConsultaAuditoriaTest]
test_banco_recusa_update_e_delete [auditoria · TrilhaSomenteInclusaoTest]
test_campos_sensiveis_sao_omitidos [auditoria · TrilhaSomenteInclusaoTest]
test_orm_nao_altera_nem_apaga [auditoria · TrilhaSomenteInclusaoTest]
test_gera_relatorio_e_resumo [compras · ComandoTest]
test_recusa_parcial_sem_autorizacao [compras · ComandoTest]
test_coluna_obrigatoria_faltando [compras · LeituraTest]
test_estoque_negativo_vira_zero_com_aviso [compras · LeituraTest]
test_le_cp1252 (apps.compras.tests.test_planilha.LeituraTest.test_le_cp1252)
test_le_csv_com_cabecalho_flexivel [compras · LeituraTest]
test_linhas_invalidas_vao_para_erros [compras · LeituraTest]
test_numeros_brasileiros [compras · LeituraTest]
test_recusa_extensao_e_conteudo_falso [compras · LeituraTest]
test_xlsx_le_valores_e_nao_formulas [compras · LeituraTest]
test_desligado_perde_sessao_e_nao_entra_mais [contas · DesligamentoTest]
test_desligamento_exige_motivo [contas · DesligamentoTest]
test_configurar_perfis_e_idempotente [contas · PerfisTest]
test_mudanca_de_perfil_e_auditada [contas · PerfisTest]
test_so_gerencia_valida_processo [contas · PerfisTest]
test_estaticos_e_cookies_sob_sistema [core · PrefixoSistemaTest]
test_login_completo_e_cookie_no_caminho [core · PrefixoSistemaTest]
test_raiz_redireciona_para_sistema [core · PrefixoSistemaTest]
test_rotas_ficam_sob_sistema [core · PrefixoSistemaTest]
test_sem_login_vai_para_entrar_sob_sistema [core · PrefixoSistemaTest]
test_tela_de_entrada_mostra_aviso [core · PrefixoSistemaTest]
test_saude_responde_sem_login [core · SaudeTest]
test_declaracao_por_quem_documenta [processos · AfirmacoesTest]
test_regra_so_pela_gerencia [processos · AfirmacoesTest]
test_aceita_pdf_valido [processos · AnexosTest]
test_duplicado_recusado [processos · AnexosTest]
test_imagem_de_pessoa_exige_autorizacao [processos · AnexosTest]
test_recusa_extensao_falsa [processos · AnexosTest]
test_recusa_tamanho [processos · AnexosTest]
test_recusa_tipo_nao_aceito [processos · AnexosTest]
test_autor_e_titular_nao_testam [processos · FluxoCompletoTest]
test_caminho_feliz_ate_validado [processos · FluxoCompletoTest]
test_devolver_validado_exige_gerencia_e_motivo [processos · FluxoCompletoTest]
test_exige_titular_e_substituto_diferentes [processos · FluxoCompletoTest]
test_nao_vai_para_teste_incompleto [processos · FluxoCompletoTest]
test_nova_versao_depois_de_validado_volta_para_documentacao [processos · FluxoCompletoTest]
test_so_gerencia_valida [processos · FluxoCompletoTest]
test_teste_com_ajuda_nao_conta_para_validar [processos · FluxoCompletoTest]
test_teste_sem_sucesso_devolve_para_documentacao [processos · FluxoCompletoTest]
test_validar_exige_teste_aprovado_da_versao_atual [processos · FluxoCompletoTest]
test_carregar_roteiro_e_idempotente [processos · RoteiroTest]
test_telas_abrem_com_processos_sem_responsavel [processos · RoteiroTest]
test_anexo_so_com_permissao_e_auditado [processos · TelasEPermissoesTest]
test_consulta_nao_registra_teste [processos · TelasEPermissoesTest]
test_fluxo_pelas_telas [processos · TelasEPermissoesTest]
test_operador_nao_envia_para_teste_pela_url [processos · TelasEPermissoesTest]
test_procedimento_com_senha_mostra_erro_sem_salvar [processos · TelasEPermissoesTest]
test_quadro_mostra_colunas_e_busca [processos · TelasEPermissoesTest]
test_aceita_texto_comum_sobre_senha [processos · TextoSeguroTest]
test_recusa_cpf [processos · TextoSeguroTest]
test_recusa_senha [processos · TextoSeguroTest]
test_edicao_concorrente_e_recusada [processos · VersoesTest]
test_sem_mudanca_nao_cria_versao [processos · VersoesTest]
test_versao_e_imutavel [processos · VersoesTest]
test_classes [compras · CurvaABCTest]
test_acima_do_ponto_nao_compra [compras · FormulasTest]
test_dados_vencidos_reduzem_confianca [compras · FormulasTest]
test_demanda_zero_sem_divisao [compras · FormulasTest]
test_excesso_e_compra_acima_do_necessario [compras · FormulasTest]
test_formulas_do_briefing [compras · FormulasTest]
test_lote_minimo_e_multiplo [compras · FormulasTest]
test_minimo_manual_prevalece [compras · FormulasTest]
test_parametros [compras · FormulasTest]
test_posicao_soma_pedidos_e_tira_reservas_uma_vez [compras · FormulasTest]
test_reproduzivel [compras · FormulasTest]
test_ruptura [compras · FormulasTest]
test_sem_custo [compras · FormulasTest]
test_sem_prazo_nao_sugere_compra [compras · FormulasTest]
test_totais [compras · ResumoTest]
```
