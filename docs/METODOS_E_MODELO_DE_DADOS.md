# Métodos financeiros e modelo de dados

## 1. Convenções

- Os retornos diários usam preços ajustados do provedor quando disponíveis; para entradas manuais, usam o preço cadastrado.
- Ativos e cotações têm um campo de origem e uma marca de entrada manual.
- A taxa livre de risco é configurada como taxa anual em porcentagem e usada como decimal nos cálculos.
- Um dia útil de bolsa é aproximado por 1/252 do ano.
- Projeções e indicadores são estimativas. O app não executa ordens.
- Preços Yahoo em USD podem ser convertidos com a série USD/BRL. Os valores em moeda estrangeira precisam de símbolo e moeda corretos.

## 2. Retorno acumulado

Para uma série diária de retornos:

    R_acumulado = produto(1 + r_t) - 1

O histórico do yfinance usa preço ajustado quando disponível; isso aproxima retorno total com ajustes de eventos e proventos. Em dados digitados manualmente, o preço não tem ajuste retroativo automático.

## 3. Volatilidade EWMA

    variancia_t = lambda * variancia_(t-1) + (1 - lambda) * retorno_(t-1)^2
    lambda = 0,94
    volatilidade_anual = raiz(variancia_diaria) * raiz(252)

A variância inicial é estimada pela variância amostral dos retornos disponíveis. Com menos de dois retornos, o valor é exibido como indisponível.

## 4. Sharpe

    Sharpe = (retorno_anualizado - taxa_livre_de_risco_anual) / volatilidade_anual

O retorno é anualizado a partir do produto de retornos observados. A taxa Selic/CDI é informada manualmente pelo usuário. O app não busca a taxa corrente nem recompõe automaticamente a taxa diária do período.

## 5. CAPM e beta

    beta_i = cov(retorno_i, retorno_mercado) / variancia(retorno_mercado)
    retorno_esperado_i = Rf + beta_i * (Rm - Rf)

Na simulação, o app usa Ibovespa (^BVSP) como referência padrão para ativos brasileiros, S&P 500 (^GSPC) quando é informado um símbolo Yahoo estrangeiro e Bitcoin (BTC-USD) para cripto. Se um benchmark falhar ou houver menos de 20 retornos pareados, beta e CAPM ficam indisponíveis.

## 6. Preço médio e posição

Compra e Aporte adicionam unidades e custos. Venda e Retirada removem unidades ao custo médio móvel; taxas de compras entram no custo. A posição visível é:

    valor_mercado = quantidade_atual * cotacao_mais_recente
    resultado_nao_realizado = valor_mercado - custo_residual

O sistema limita uma venda ao saldo positivo disponível e não cria uma posição vendida. O resultado realizado em cada venda não é mostrado como métrica de lucro/prejuízo fiscal.

## 7. Eventos corporativos e proventos

- O yfinance fornece dividendos e desdobramentos junto ao histórico quando disponível.
- Em um desdobramento com fator F, a quantidade histórica é multiplicada por F; o custo total permanece igual e o custo por unidade muda proporcionalmente.
- Proventos encontrados no histórico são gravados com a quantidade conhecida na data. Proventos manuais podem ser informados na interface.
- Dividend yield ponderado usa valores de proventos registrados nos últimos 12 meses e o valor atual da posição; não é previsão de distribuição futura.

## 8. Carteira e séries históricas

Os indicadores da carteira usam pesos derivados do valor atual. A série total é uma aproximação de pesos constantes baseada na composição atual; ela não reconstrói compras, vendas, aportes e saldos de caixa em cada data. Cotações sem datas sobrepostas podem reduzir a amostra. Esta escolha deixa explícita a limitação de séries que não têm histórico completo das posições.

## 9. Previsão

O cenário determinístico aplica capitalização mensal, taxa informada e aportes na periodicidade escolhida. A faixa de incerteza usa 800 trajetórias simuladas com choques normais e volatilidade mensal derivada de EWMA anual ou da premissa manual. Ela é uma distribuição matemática sob premissas, não uma previsão probabilística validada de mercado.

## 10. Simulação de ativo

O aporte hipotético modifica os pesos pelo valor atual da carteira e do aporte. Retorno, EWMA e Sharpe comparam séries disponíveis. Se a API falhar e forem usadas premissas manuais, a série do ativo é sintética e reprodutível; os resultados devem ser interpretados como exemplo de cenário.

## 11. Banco SQLite

O banco data/investimentos.db usa tabelas normalizadas:

### Ativos

- id_ativo: chave primária.
- ticker: código único.
- nome_ativo, classe_ativo, categoria_fundo_setor.
- is_manual_entry: identifica o cadastro manual.
- codigo_api: ticker específico do provedor ou ID do CoinGecko.
- moeda: moeda-base da série Yahoo (BRL ou USD); preços em USD são convertidos para BRL.
- data_cadastro.

### Transacoes

- id_transacao: chave primária.
- id_ativo: chave estrangeira para Ativos.
- tipo_operacao, data_transacao, quantidade, preco_unitario, taxas_custos.
- is_manual_entry: identifica origem manual/importada.

### Cotacoes_Historico

- id_cotacao: chave primária.
- id_ativo: chave estrangeira para Ativos.
- data_cotacao, preco_fechamento, fonte_dados, is_manual_entry.
- Restrição única por id_ativo e data_cotacao para atualização idempotente da cotação diária.

### Proventos

- id_provento: chave primária.
- id_ativo: chave estrangeira para Ativos.
- tipo_provento (Dividendo, JCP, Rendimento ou Split).
- data_com, data_pagamento, valor_por_acao, valor_total, is_manual_entry.

### Configuracoes

- chave: chave primária.
- valor, atualizado_em.

Índices são criados nas chaves estrangeiras e datas usadas nas consultas. Na inicialização, o app cria um backup e conserva as 14 versões mais recentes.

## 12. Dados e fontes

- yfinance: https://ranaroussi.github.io/yfinance/reference/api/yfinance.Ticker.history.html
- CoinGecko: https://docs.coingecko.com/reference/coins-id-market-chart
- Banco Central do Brasil, descrição da série Selic efetiva: https://dadosabertos.bcb.gov.br/pt_BR/dataset/11-taxa-de-juros---selic

