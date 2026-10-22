# O desenho que o dono da loja já lê

Ele devolveu o layout inteiro duas vezes e a Curva ABC duas vezes. A lição que vale para
toda tela nova: **desenho novo pede explicação, desenho que já está na tela não.** Antes
de inventar um gráfico, procurar o padrão que ele já lê sem reclamar.

## Os blocos que existem

| Padrão | Classe | Para que |
|---|---|---|
| Cabeçalho da página | `.cabecalho-pagina` | título + uma linha do que a tela responde |
| Quatro números grandes | `.cartoes-numero` > `.cartao-numero` | o resumo que se lê de longe |
| Cartão de aviso | `.cartao.cartao-atencao` | o que precisa de atenção, com o número na frase |
| Cartão de destaque | `.cartao.cartao-destaque` | instrução de configuração |
| Filtros | `form.filtros` | `GET`, sempre com um botão de limpar |
| Tabela | `.tabela-rolavel` > `table` | lista; `.numerico` nas colunas de número |
| Lista de barras | `._barras.html` | comparação entre poucos itens, com o nome em palavras |
| Etiqueta | `.etiqueta`, `.etiqueta-atencao` | estado curto dentro de célula |

Cor de nível: `.nivel-bom`, `.nivel-atencao`, `.nivel-ruim` no cartão de número.

## Regras de tela

1. **Todo número tem uma frase embaixo** dizendo o que ele significa e o que fazer com
   ele. Número sozinho vira palpite.
2. **A tela diz de quando são os dados.** Amarelo com 2-3 dias, vermelho com 4+, com o
   botão "Importar agora".
3. **Erro em linguagem de loja**, nunca a exceção crua. Progresso em barra, não em log.
4. **F1 abre o tour** (`{% block ajuda %}` com `#passos-ajuda`): três a quatro passos,
   cada um apontando um seletor da própria tela.
5. **Texto dentro de barra não funciona**: CSS não mede texto. O rótulo fica fora.
6. **Conferir em 1600 e em 390 px** antes de entregar, medindo
   `document.documentElement.scrollWidth > window.innerWidth`. Palavra sem espaço
   (e-mail, código) vaza sem mudar a largura do elemento: só `scrollWidth > clientWidth`
   acha, e o conserto é `overflow-wrap: anywhere`.
7. **Medir com o valor real do servidor**: `127.0.0.1:8099` cabe onde
   `192.168.3.254:8443` quebra.
8. O menu tem DOIS níveis e `apps/core/menu.py` é a única lista; ele também move as setas
   de anterior/próxima.
9. A versão no menu de cima é como o dono confere se a atualização entrou. A tela de
   entrada mostra versão, servidor e IP.

## Palavras

Português do Brasil, frase curta, nada de jargão: "sobrou no dia" em vez de "lucro
bruto", "o que fazer agora" em vez de "ações sugeridas", "sem custo gravado no SET" em
vez de "custo nulo". Nomes de função, variável, teste e commit também em português.
