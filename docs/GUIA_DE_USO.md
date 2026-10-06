# Guia completo de utilização

## 1. Instalar e abrir

### Windows

1. Extraia o ZIP em uma pasta com permissão de gravação.
2. Instale Python 3.9 ou superior. Python 3.11 ou 3.12 é recomendado.
3. Execute setup_windows.bat. Na primeira vez, o computador precisa acessar o índice de pacotes Python para baixar as dependências.
4. Ao terminar, execute run_windows.bat.
5. O aplicativo abre no navegador por um endereço localhost. Se a janela não abrir sozinha, use o endereço local exibido no terminal.
6. Para encerrar, feche a janela do terminal que iniciou o Streamlit.

### macOS e Linux

Abra um terminal na pasta extraída e rode:

    sh setup_unix.sh
    sh run_unix.sh

O servidor fica vinculado a 127.0.0.1. Não altere esse endereço para expor informações da carteira à rede.

## 2. Primeiro uso e manutenção da carteira

1. Abra Cadastro e importação.
2. Cadastre cada compra ou aporte. Informe ticker, classe, data, quantidade, preço e custos.
3. Para uma carteira existente, baixe o modelo CSV, preencha as transações e importe o arquivo. É possível importar operações compatíveis de OFX.
4. Revise as linhas encontradas e confirme a importação.
5. Abra Estado atual. O sistema tenta obter histórico de mercado quando a carteira é consultada pela primeira vez e usa cache de 15 minutos.
6. Se um ativo não for localizado, registre seu preço em Cadastro e importação > Cotação manual.
7. Registre dividendos, JCP ou rendimentos na guia Provento manual. O yfinance também fornece dividendos e desdobramentos quando o histórico existe.
8. Cadastre vendas e retiradas como novas operações. Não apague compras antigas: o livro de operações é a origem da posição e do preço médio.

### Operações e saldo

- Compra e Aporte adicionam unidades à posição.
- Venda e Retirada reduzem unidades, usando o método de custo médio.
- Vendas acima da posição disponível são recusadas e uma importação em lote inteira é revertida. Confira o histórico e corrija as operações antes de tentar novamente.
- Taxas de compra integram o custo; taxas de venda reduzem o recebimento. A tela separa resultados realizados, não realizados e proventos.

## 3. Importar CSV

Obrigatórios: ticker, tipo_operacao, data_transacao, quantidade e preco_unitario. Colunas opcionais: nome_ativo, classe_ativo, categoria_fundo_setor, taxas_custos, codigo_api, moeda_ativo, moeda_cotacao, moeda_transacao e taxa_cambio.

Preço e custos estão na moeda_transacao. A moeda_ativo descreve a denominação/listagem; moeda_cotacao descreve a série do provedor. Em arquivos, a coluna antiga moeda identifica a moeda do ativo, enquanto moeda_transacao ausente assume BRL. Declare a moeda da operação corretamente e informe taxa de câmbio em BRL por unidade; USD, USDT e outras moedas exigem taxas próprias.

Use classes Ação, FII, ETF, Cripto, Renda Fixa ou Outro. Operações: Compra/Venda/Aporte/Retirada. Datas ISO ou DD/MM/AAAA e decimal com vírgula são aceitos. Duplicatas no arquivo são marcadas; arquivo todo é gravado atomicamente.

## 4. Importar OFX

O importador aceita blocos de compra e venda de investimento que contenham identificador da segurança como ticker, data da operação, unidades e preço unitário. Alguns bancos fornecem um identificador interno em vez do ticker ou usam outra variante do OFX; esses arquivos precisam ser convertidos para o CSV do modelo. Revise sempre os dados detectados antes de confirmar.

## 5. Consultar cotações e analisar

Na tela Estado atual, use Atualizar cotações para forçar uma nova consulta. Fontes e comportamento:

- yfinance: ações, FIIs e ETFs. Tickers brasileiros são enviados com sufixo .SA automaticamente. Para símbolos estrangeiros, informe USD como moeda de cotação e o símbolo Yahoo (por exemplo, AAPL); o histórico USD/BRL é usado para exibir valores em reais. Tickers internacionais listados em bolsa brasileira podem usar BRL e o sufixo .SA.
- CoinGecko: BTC, ETH, SOL, ADA, XRP e DOGE têm IDs padrão. Para outra moeda, informe o ID CoinGecko (por exemplo, bitcoin, ethereum). Os preços recebidos são convertidos para BRL pelo serviço.
- Cotações ficam salvas no SQLite com data, origem, moeda original e taxa aplicada quando disponíveis. Se a API falhar, o sistema mantém a última cotação e permite digitação manual com taxa explícita ou cache.
- A série retornada pelo yfinance usa preço ajustado quando disponível; a métrica de retorno incorpora proventos ajustados na série de preço. Os valores de dividendos e splits são registrados separadamente quando o provedor os informa.
- As chamadas dependem da disponibilidade e dos termos dos provedores. Não são preços garantidos em tempo real.

## 6. Ver métricas de risco

- EWMA usa lambda 0,94 e dados diários disponíveis.
- Sharpe usa a taxa anual que você preencher em Configurações e backup.
- O beta e o CAPM são exibidos na simulação de um ativo se o histórico do benchmark estiver disponível.
- Ativos sem histórico suficiente podem mostrar “—”.
- Uma posição sem cotação usa o preço médio como valor provisório; confira a origem da cotação na tabela.
- O gráfico histórico é uma estimativa que reaplica pesos atuais às séries disponíveis; não é rentabilidade histórica reconstruída.

## 7. Criar projeções

1. Abra Previsão.
2. Defina prazo e unidade (meses, semestres ou anos).
3. Informe o valor do aporte e sua frequência.
4. Informe a taxa mensal do cenário escolhido.
5. Se a carteira não tiver histórico suficiente, ajuste a volatilidade anual de fallback.
6. Clique em Calcular projeção.

O gráfico compara a taxa escolhida com as duas metas configuradas e apresenta percentis 10–90 calculados por simulação. A simulação não prevê o mercado nem garante faixa de retorno.

## 8. Simular outro ativo

1. Abra Simular ativo.
2. Informe ticker, classe e, para cripto fora da lista padrão, ID CoinGecko.
3. Informe o valor hipotético.
4. Clique em Simular adição de ativo.
5. Se não houver histórico no provedor, marque a opção de premissas manuais e informe retorno e volatilidade.

A página compara indicadores da carteira atual e da composição hipotética. Os dados manuais são premissas inseridas pelo usuário, não cotações reais. O tipo de fundo/setor deve ser cadastrado para que os alertas de concentração tenham utilidade.

## 9. Configurar referências

Em Configurações e backup, personalize:

- Metas mensais usadas nos cenários comparativos.
- Selic/CDI anual para calcular Sharpe e CAPM. Informe a taxa acumulada/anual adequada ao horizonte de análise em porcentagem, por exemplo, 10,5 para 10,5%.
- Percentual de referência de renda fixa, exibido como contexto.
- Limite percentual de alertas de concentração.

A taxa livre de risco não é atualizada automaticamente. Use uma fonte oficial ou o dado fornecido por sua instituição e atualize o parâmetro quando necessário.

## 10. Backup e restauração

- O sistema cria uma cópia do banco antes da inicialização e conserva as 14 cópias mais recentes em data/backups.
- Baixe também uma cópia pelo botão Baixar backup SQLite e guarde-a em local seguro, separado do computador.
- Para restaurar, selecione um arquivo de backup e use Validar e restaurar. O sistema verifica integridade SQLite, tabelas, versão do schema e chaves estrangeiras antes da substituição.
- Não edite investimentos.db enquanto a plataforma estiver aberta. Encerre o aplicativo antes de copiar arquivos diretamente.

## 11. Onde os dados ficam

- data/investimentos.db: ativos, operações, cotações, eventos e preferências.
- data/backups/: cópias automáticas.

Esses arquivos permanecem na pasta do projeto. Ao mover a plataforma, copie os arquivos de dados com o aplicativo fechado.

## 12. Problemas comuns

- “yfinance não está instalado”: execute novamente setup_windows.bat ou sh setup_unix.sh.
- Cotação não encontrada: confirme o ticker, use um código do provedor ou registre preço manual.
- Erro CoinGecko/rate limit: aguarde, tente mais tarde, configure a variável opcional COINGECKO_DEMO_API_KEY ou use cotação manual.
- Gráfico vazio: confira se há pelo menos duas observações de preço para calcular variação.
- Após migrar uma base antiga, resultados estão bloqueados: abra Cadastro e importação / Câmbio legado. Informe uma taxa histórica confiável para cada operação estrangeira pendente. A operação é preservada em moeda original e não entra nos resultados até a regularização.
- O portfólio parece divergente: revise vendas, desdobramentos, ticker, moeda da transação/cotação e quantidade por ativo.
- Porta ocupada: encerre outra instância local do Streamlit antes de abrir de novo.

## 13. Encerrar e proteger os dados

Feche o terminal que iniciou o app. Guarde backups fora da pasta quando desejar proteção contra falha ou perda do computador. Não exponha o aplicativo na rede e não armazene tokens de acesso bancário neste projeto.

## 14. Referências técnicas

- Streamlit, cache de dados com TTL: https://docs.streamlit.io/develop/api-reference/caching-and-state/st.cache_data
- yfinance, histórico de preços: https://ranaroussi.github.io/yfinance/reference/api/yfinance.Ticker.history.html
- CoinGecko, gráfico histórico por ID: https://docs.coingecko.com/reference/coins-id-market-chart
- Banco Central do Brasil, série diária da taxa Selic efetiva (SGS 11): https://dadosabertos.bcb.gov.br/pt_BR/dataset/11-taxa-de-juros---selic


Operações estrangeiras exigem moeda e câmbio para BRL; pode-se usar cache de até sete dias ou entrada manual. USD e USDT não são equivalentes. Renda fixa e valor atualizado são manuais. Migração existente cria backup sem apagar banco.
