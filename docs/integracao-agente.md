# Integração com o Trello e o Kommo pelo agente da casa

Pedido do Edson, 05/11/2026: *"vou usar um desktop na minha casa para manusear o trello e
kommo / o agente claude desse computador fara as integracoes"*.

## Como funciona

```
 Trello  <──>  agente (desktop da casa)  <── VPN ──>  sistema do Studio (servidor da loja)
 Kommo   <──>        com as senhas                      sem senha nenhuma de fora
```

- O **servidor da loja não sai para a internet** em nome do Trello nem do Kommo, e não guarda
  senha de nenhum dos dois. Quem fala com eles é o agente.
- O agente entra no sistema pela VPN com uma **chave própria**, que não é login de pessoa.
- Para fora (**Trello**): o sistema guarda uma fila de eventos. O agente busca, faz a parte
  dele no Trello e devolve "entregue". Se falhar, devolve o erro e o evento continua na fila.
- Para dentro (**Kommo**): o agente lê os leads do Kommo e manda para o sistema. O lead entra
  uma vez só (pelo número dele no Kommo) e as conversas viram contatos "trazidos do Kommo".
  A etapa do funil é do Studio: o agente não muda.

## 1. Criar a chave (uma vez, no servidor)

```powershell
cd C:\studio-sistema\app
..\venv\Scripts\python.exe manage.py criar_chave_integracao agente-da-casa
```

A chave aparece **uma vez**. Guarde no desktop da casa, num arquivo que só o agente lê. Perdeu
ou vazou: crie outra com outro nome e desligue a velha:

```powershell
..\venv\Scripts\python.exe manage.py criar_chave_integracao agente-da-casa --desligar
```

## 2. A API

Endereço base, pela VPN: `https://192.168.3.254:8444/studio/integracao/`. Toda chamada leva o
cabeçalho `Authorization: Bearer <chave>`. Sem chave válida a resposta é `401`.

| Chamada | Para quê |
|---|---|
| `GET eventos/?limite=50` | Os eventos ainda não entregues, do mais antigo para o mais novo. |
| `POST eventos/<id>/` | Dizer como foi: `{"ok": true, "trello_cartao": "<id do cartão>"}` ou `{"ok": false, "erro": "..."}`. |
| `GET projetos/` | Os projetos em andamento e em orçamento (`?todos=1` inclui os entregues), para conferir o quadro inteiro. |
| `POST leads/` | Um lead do Kommo entra ou é atualizado (corpo abaixo). |

Tipos de evento: `projeto.criado`, `projeto.etapa`, `projeto.alterado` (título, cliente,
oficina, prazo ou responsável; valor não), `lead.criado` e `lead.etapa` (lead criado ou mudado
no Studio; o que veio do Kommo não volta como evento).

Os `dados` de um evento de projeto: `codigo`, `titulo`, `cliente`, `etapa`, `etapa_rotulo`,
`oficina`, `prazo_entrega`, `responsavel` e `trello_cartao` (vazio até o agente devolver um).

Corpo de `POST leads/`:

```json
{
  "kommo_id": "123456",
  "nome": "Paula Souza",
  "telefone": "+55 11 98888-0000",
  "email": "",
  "interesse": "Mesa de jantar em ferro, 8 lugares",
  "valor_estimado": "7500.00",
  "mensagens": [
    {"quando": 1793800000, "texto": "Oi, vi a mesa no Instagram", "canal": "whatsapp"}
  ]
}
```

`quando` aceita segundos desde 1970 (como o Kommo manda) ou data ISO. Mensagem igual ou mais
antiga que a última trazida é ignorada, então mandar o histórico inteiro de novo não duplica.
Campo vazio não apaga o que o Studio preencheu.

## 3. O roteiro do agente

A cada 10 minutos, no horário comercial:

1. **Trello**: `GET eventos/`. Para cada evento de projeto:
   - sem `trello_cartao`: criar o cartão `"{codigo} · {titulo} · {cliente}"` na lista da etapa,
     com a data de entrega = `prazo_entrega`, e devolver `{"ok": true, "trello_cartao": id}`;
   - com `trello_cartao`: mover o cartão para a lista da etapa e atualizar nome e data;
   - erro do Trello: devolver `{"ok": false, "erro": "..."}` e seguir para o próximo.
2. **Kommo**: buscar os leads alterados desde a última passada (API v4 do Kommo,
   `GET /api/v4/leads?filter[updated_at][from]=...&with=contacts`, e as mensagens do chat do
   lead) e mandar cada um para `POST leads/`.
3. Eventos de **lead** (`lead.etapa`): mover o lead no funil do Kommo para a etapa
   correspondente (ganho, perdido) e devolver `ok`.
4. Uma vez por dia: `GET projetos/` e conferir que todo projeto tem cartão na lista certa.

### Listas do Trello (uma por etapa)

| Etapa no sistema | Lista no Trello |
|---|---|
| `orcamento` | Orçamento |
| `aprovado` | Aprovado |
| `producao` | Em produção na oficina |
| `pronto` | Pronto para entregar |
| `entregue` | Entregue |
| `cancelado` | arquivar o cartão |

O quadro e o nome exato das listas ficam a combinar com o Edson (perfil do Trello do Studio).

## O que isto não faz

- Não mexe no SET.
- Não manda mensagem de WhatsApp para cliente: quem conversa é a pessoa, pelo Kommo.
- Não recebe webhook: o servidor só é alcançado pela VPN, então quem pergunta é o agente.
