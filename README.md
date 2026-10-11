# Robô de Cobrança de Propostas

Automação em Python (RPA) que acompanha propostas comerciais paradas na etapa
**"AGUARDANDO ACEITE"** de um CRM web e cobra cada consultor(a) pelo WhatsApp.

## Problema

Em uma equipe de vendas, muitas propostas ficam travadas na última etapa: o
cliente já concordou, mas falta o aceite final. Acompanhar isso manualmente,
consultor por consultor, toma tempo e deixa negócios esfriarem.

O robô faz essa varredura sozinho, avisa cada consultor(a) sobre as próprias
pendências e envia um resumo consolidado para a diretoria e para o grupo da equipe.

## Como funciona

1. É executado manualmente ou por agendamento (cron) em um servidor.
2. Abre um navegador Chromium em modo headless com Playwright e faz login no CRM.
3. Acessa a tela de pedidos e lê a lista de consultores do filtro.
4. Para cada consultor(a): limpa os filtros, seleciona o nome e o status
   "AGUARDANDO ACEITE".
5. Lê a quantidade informada pelo sistema e rola a página até carregar todos os cards.
6. Extrai ID, empresa e data de criação de cada card com expressões regulares,
   descartando cards de outro status, de outro consultor ou duplicados em cache.
7. Envia uma mensagem individual pelo WhatsApp (Evolution API) com a lista de
   clientes pendentes. Se o consultor não tiver número cadastrado, alerta o supervisor.
8. No final, envia para a diretoria e para o grupo o total de pendências e o
   período (data mais antiga e mais recente).

## Stack

- Python 3.10+
- [Playwright](https://playwright.dev/python/) para automação do navegador
- [Evolution API](https://doc.evolution-api.com/) para envio de mensagens no WhatsApp
- requests, python-dotenv
- pytest para os testes da lógica de extração e montagem das mensagens

## Estrutura

```
main.py               # robô (configuração, lógica pura e automação)
tests/test_parsing.py # testes que rodam sem navegador
.env.example          # modelo das variáveis de ambiente
equipe.example.json   # modelo do cadastro da equipe
```

## Como executar

1. Crie o ambiente e instale as dependências:

   ```bash
   python -m venv venv
   source venv/bin/activate        # Windows: venv\Scripts\activate
   pip install -r requirements.txt
   playwright install chromium     # no Linux, se faltar biblioteca: playwright install --with-deps chromium
   ```

2. Configure as variáveis de ambiente:

   ```bash
   cp .env.example .env
   ```

   | Variável | Descrição |
   | :--- | :--- |
   | `CRM_URL` | Página de login do CRM |
   | `CRM_PEDIDOS_URL` | Página de pedidos do CRM |
   | `CRM_EMAIL` / `CRM_SENHA` | Credenciais de acesso ao CRM |
   | `EVOLUTION_API_URL` | Endereço da Evolution API |
   | `EVOLUTION_INSTANCE` | Nome da instância do WhatsApp |
   | `EVOLUTION_API_KEY` | Chave da Evolution API |
   | `WHATSAPP_DIRETORIA` | Número que recebe o resumo final |
   | `WHATSAPP_GRUPO` | (opcional) ID do grupo que também recebe o resumo |
   | `WHATSAPP_SUPERVISOR` | (opcional) número alertado quando falta o telefone de um consultor |
   | `EQUIPE_ARQUIVO` | (opcional) caminho do cadastro da equipe, padrão `equipe.json` |

   Se alguma variável obrigatória estiver faltando, o robô para com uma mensagem
   dizendo quais são.

3. Cadastre a equipe (nome exatamente como aparece no CRM e número com DDI e DDD):

   ```bash
   cp equipe.example.json equipe.json
   ```

4. Execute:

   ```bash
   python main.py
   ```

### Agendamento com cron

Exemplo para rodar de segunda a sexta às 9h:

```cron
0 9 * * 1-5 cd /caminho/robo-cobranca-propostas && ./venv/bin/python main.py >> robo.log 2>&1
```

## Testes

```bash
pip install pytest
pytest
```

Os testes cobrem a leitura dos cards, o cálculo do período e a montagem das
mensagens, sem abrir navegador nem chamar a API.

## Segurança

- Credenciais, chaves e números ficam fora do código, no `.env` e no `equipe.json`,
  ambos ignorados pelo Git.
- Os logs mostram apenas nomes de consultores, IDs de pedidos e destinos das mensagens.

## Observação

Todos os nomes, números de telefone, empresas e endereços presentes neste
repositório (exemplos e testes) são fictícios.

## Licença

[MIT](LICENSE)
