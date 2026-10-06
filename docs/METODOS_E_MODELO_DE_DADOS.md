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

## 6. Custo médio, posição e resultados

O custo médio ponderado móvel é calculado em BRL. Compra/Aporte soma unidades, total convertido e taxas ao custo. Venda remove o custo médio das unidades vendidas; o resultado realizado é receita líquida em BRL menos a base removida. Taxas de compra somam à base; taxas de venda reduzem receita. Venda acima da posição é recusada. Retirada reduz unidades sem inventar receita.

Patrimônio atual é quantidade aberta vezes cotação atual em BRL. Resultado não realizado = patrimônio menos custo residual. Realizado, não realizado, proventos e taxas são valores separados. Sem cotação, o custo médio é uma referência provisória identificada.

Resultado total soma realizado + não realizado + proventos. Percentual sobre aquisições acumuladas é indicativo; não é TWR/XIRR nem cálculo tributário.

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

## 11. Banco SQLite  schema 3

A moeda-base de carteira é BRL.

### Ativos
- moeda_ativo: denominação/listagem informada para o ativo.
- moeda: moeda de cotação do provedor, mantida para compatibilidade.
- moeda_base: BRL.
- ticker, classe, categoria, origem e código do provedor.

### Transacoes
- moeda_transacao, preco_unitario_original, valor_total_original e taxas_custos_original.
- taxa_cambio: BRL por unidade da moeda da transação; fonte_cambio identifica manual/cache/identidade/legado.
- moeda_base, preco_unitario_brl, valor_total_brl e taxas_custos_brl.
- Quantidade original canônica, preço original, data, operação, origem e fingerprint de importação; valores decimais ficam como texto canônico.
- Os campos REAL antigos permanecem para leitura por versões legadas. O cálculo usa campos decimais textuais.

### Cotacoes_Historico
- preco_fechamento sempre convertido para BRL, com moeda_base.
- preco_original, moeda_original e taxa_cambio preservam a observação de origem.
- preco_ajustado fica separado do fechamento para indicadores de retorno.
- fonte_dados/is_manual_entry preservam proveniência e a chave única por ativo/data torna atualização idempotente.

### Proventos e câmbio
- Proventos preserva total em BRL, moeda, taxa e fonte.
- Taxas_Cambio guarda moeda, data, taxa_para_brl e fonte, chave única por moeda/data. Cache usa data exata ou taxa anterior até sete dias.

### Renda fixa e versão
- Renda_Fixa guarda cadastro manual em BRL: investido, atualizado, taxa, indexador, vencimento, liquidez, emissor/instituição e observações.
- Schema_Meta e PRAGMA user_version registram a versão 3.
- A inicialização aplica migração aditiva e faz backup da base existente antes de alterar o schema. Operações/importações são transacionais.
- Backups usam a API SQLite consistente; restauração verifica integridade, tabelas, versão e chaves estrangeiras antes da substituição.

Na migração, a moeda antiga do ativo é usada para identificar a moeda original da transação. Se houver taxa histórica no cache, os valores são convertidos; se faltar, o original estrangeiro é preservado e a operação fica pendente, fora dos resultados até regularização manual. O banco existente é preservado por migração aditiva e recebe backup antes da inicialização.

## 12. Dados e fontes

- yfinance: https://ranaroussi.github.io/yfinance/reference/api/yfinance.Ticker.history.html
- CoinGecko: https://docs.coingecko.com/reference/coins-id-market-chart
- Banco Central do Brasil, descrição da série Selic efetiva: https://dadosabertos.bcb.gov.br/pt_BR/dataset/11-taxa-de-juros---selic



A descrição de schema e cálculos acima substitui os campos legados descritos nas versões anteriores deste documento.
