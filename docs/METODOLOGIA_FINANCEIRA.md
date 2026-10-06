# Metodologia financeira

## 1. Precisão e moeda-base

BRL é a moeda-base da carteira. Cálculos de ledger, câmbio, custo e resultado usam Decimal; valores canônicos são persistidos como texto decimal no SQLite. Campos REAL permanecem para compatibilidade e gráficos. Quantidades e preços de cotação também têm campos decimais canônicos no schema 3. Dados legados que já chegaram como REAL só podem ser migrados com a precisão que ainda existe no banco antigo.

## 2. Compras

Uma compra guarda ativo e moeda do ativo, moeda da transação, preço e total originais, taxa aplicada, valor unitário e total convertidos para BRL, taxas e origem do câmbio. O total original é quantidade  preço unitário. O custo de aquisição em BRL soma o valor da compra convertido e os custos/taxas convertidos.

## 3. Preço médio

A metodologia inicial é custo médio ponderado móvel em BRL. Cada compra acrescenta seu valor total e taxas ao custo residual. O preço médio é custo residual dividido pela posição. Um desdobramento altera quantidade e preço médio, mantendo o custo total.

## 4. Vendas e posição

Venda reduz a quantidade e remove do custo residual a parcela proporcional ao custo médio imediatamente anterior à venda. A transação permanece no histórico. O banco rejeita vendas acima da posição disponível na data, inclusive em lotes importados. Retirada reduz posição sem assumir que houve receita.

## 5. Resultado realizado

Na venda, resultado realizado = valor de venda convertido para BRL  taxas da venda convertidas  custo médio removido. Custos de compra já compõem o custo de aquisição. Lucros e prejuízos realizados são acumulados separadamente.

## 6. Patrimônio e resultado não realizado

Patrimônio atual = quantidade em carteira  última cotação disponível convertida para BRL. Custo residual é o custo das unidades ainda mantidas. Resultado não realizado = patrimônio atual  custo residual. Se faltar cotação, a tela identifica o uso de custo médio como estimativa de marcação; esse valor não é uma cotação de mercado.

## 7. Proventos e taxas

Dividendos, JCP e rendimentos são somados separadamente dos resultados de venda e de marcação a mercado. A entrada manual atual registra proventos em BRL. Taxas conhecidas são guardadas à parte e entram no custo das compras ou reduzem o valor líquido de venda. Impostos não são calculados.

## 8. Câmbio e USDT

A taxa registrada é BRL por unidade da moeda original. BRL usa taxa 1. USD, USDT e outras moedas são códigos distintos e exigem taxas próprias. A operação usa taxa informada manualmente ou observação cacheada na data/até sete dias antes; não usa taxa futura. Sem taxa adequada, a operação estrangeira é bloqueada até entrada manual ou atualização do cache. Na migração de operações antigas, a moeda do ativo identifica a moeda original; se não houver câmbio histórico no banco, a operação fica pendente e nenhuma métrica é apresentada até o usuário informar uma taxa confiável. O sistema não presume que USDT equivale a USD ou BRL. A cotação de mercado também guarda moeda original, conversão e taxa usada.

## 9. Renda fixa

CDB, LCI/LCA, Tesouro e outros investimentos de renda fixa podem ser cadastrados manualmente em BRL com valor investido e atualizado, taxa, indexador, vencimento, liquidez, emissor/instituição e observações. A valorização é a diferença entre os dois valores informados. Não há cotação ou atualização automática; o usuário deve revisar o valor atualizado e sua data.

## 10. Projeções

Cenários capitalizam o saldo mensalmente pela taxa escolhida e acrescentam aportes na periodicidade informada. A simulação aplica choques normais com volatilidade informada e apresenta percentis 10, 50 e 90. São cenários matemáticos hipotéticos, sem garantia, inflação ou tributação; não constituem previsão de mercado nem recomendação.

## 11. Dados de mercado

Yahoo Finance fornece cotações/séries para ativos cobertos; fechamento para patrimônio e série ajustada separada para indicadores. O câmbio histórico é buscado por data, sem preencher lacunas com taxas futuras. CoinGecko fornece histórico cripto em BRL. A origem e data da cotação ficam registradas quando disponíveis. Falha externa preserva última cotação local e deve ser comunicada; nenhum preço de ativo é inventado. Cobertura, atraso e disponibilidade dos provedores variam.

## 12. Histórico e estimativas

A série histórica da carteira disponível na interface aplica os pesos atuais aos retornos passados dos ativos. É uma reconstrução estimada e não representa rentabilidade histórica real da carteira. O ledger preserva transações datadas para uma futura reconstrução data, transações, posições, fluxo de caixa e patrimônio. TWR e XIRR não estão implementados. Rentabilidade exibida no estado atual é o resultado acumulado (realizado + não realizado + proventos) dividido pela base investida registrada; não é uma métrica fiscal ou TWR/XIRR.

## 13. Limitações

Câmbio histórico pode faltar ou estar desatualizado; confirme taxas manuais e suas fontes. Cotações podem atrasar ou falhar. Proventos dependem de cadastro manual ou da fonte e podem estar incompletos. Retirada sem valor recebido não gera resultado realizado. Renda fixa é manual. A importação exige conciliação com o extrato/custódia. Não há cálculo tributário, execução de ordens, integração com corretoras, multiusuário, TWR ou XIRR.
