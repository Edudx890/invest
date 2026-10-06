# Changelog

## 1.2.0  Primeira homologação

- BRL definido como moeda-base, com moeda do ativo, da transação e da cotação separadas; USD e USDT usam taxas distintas.
- Conversão cambial manual/cacheada explícita, valores originais e convertidos preservados e cotações armazenadas em BRL com origem/data.
- Ledger com Decimal, custo médio ponderado, taxas, proventos, posição e resultados realizados/não realizados separados; venda excedente bloqueada sem apagar operações.
- Quantidade fracionária, preço de cotação e valores monetários mantêm representação decimal canônica; migração aditiva para schema 3 preserva a base existente e marca operações estrangeiras antigas sem taxa como pendentes de regularização manual.
- Cadastro manual de renda fixa, importação atômica, backup snapshot e restauração com validação.
- Série histórica da carteira identificada como estimativa baseada nos pesos atuais; dados manuais, em cache ou externos têm origem identificada quando disponível.
- Suíte automatizada para cálculos, transações, importação, banco, migração, backup/restauração, provedores simulados e interface.
- Limitações: câmbio pode exigir entrada manual; renda fixa não tem cotações automáticas; TWR/XIRR e tributação não estão implementados.
