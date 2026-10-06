# Testes

No Windows, na pasta do projeto, execute:

    .venv\Scripts\python.exe -m pytest

O pacote inclui 31 testes automatizados, incluindo uma verificação de renderização das rotas Streamlit. A suíte cobre:

- Custo médio, posição, custo residual, patrimônio, resultados realizado/não realizado, proventos, taxas e rentabilidade.
- Conversão BRL, USD e USDT, taxa manual/cache, projeções e renda fixa.
- Compra, novas compras a preços diferentes, venda parcial/total, lucro, prejuízo, split e cenário completo compra  nova compra  valorização  venda parcial  provento.
- CSV/OFX válido e inválido, campos obrigatórios, datas, valores, moedas e duplicidade.
- Criação/migração/inserção/leitura/atualização SQLite, atomicidade, câmbio cacheado, quantidades/preços decimais, legado estrangeiro pendente e regularização manual de câmbio, renda fixa manual, backup e restauração.
- Renderização das principais rotas da interface sem exceções e execução de simulação manual com provedores indisponíveis.

Os cenários financeiros usam dados fictícios e verificam valores esperados. Os testes de provedores de mercado usam respostas controladas; não comprovam disponibilidade externa, custódia, conciliação fiscal ou funcionamento em todas as versões de Windows/navegadores. A execução deve ser repetida no ambiente de homologação com cópia de dados reais.
