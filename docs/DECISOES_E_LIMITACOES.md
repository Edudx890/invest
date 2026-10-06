# Decisões, premissas e limitações

## Decisões de implementação

1. A plataforma é um aplicativo local Streamlit conectado ao SQLite, de acordo com a restrição tecnológica do Guia Mestre.
2. As três visões do produto são rotas separadas: Estado atual, Previsão e Simular ativo.
3. Transações manuais e arquivos de extrato são a entrada de posição. A camada de dados de mercado é independente da carteira.
4. yfinance e CoinGecko são adaptadores de consulta opcional; a falha não impede uso dos dados locais.
5. O cache em memória tem TTL de 15 minutos. Cotações diárias consultadas são gravadas no SQLite.
6. O banco mantém uma origem por cotação/entrada e guarda preferências de análise localmente.
7. Backups locais são feitos antes da inicialização. Restauração valida o arquivo SQLite antes de substituí-lo.
8. O servidor inicia vinculado a 127.0.0.1. A aplicação não abre portas para acesso público.

## Integrações externas

### Banco Inter/B3

O material de requisitos cita uma API de custódia, porém não especifica uma API concreta, endpoint, formato, documentação, consentimento ou credencial. O código não autentica no Banco Inter, não lê credenciais bancárias e não automatiza acesso à conta. Como contingência operacional, há importação de CSV, suporte limitado a OFX padrão e cadastro manual.

Para implementar uma integração bancária real será necessário selecionar uma API documentada e autorizada, fornecer o modelo de autenticação e definir o mapeamento de posições e operações. O ponto de extensão é a camada importers/adapters; os dados devem chegar ao mesmo modelo de transações, sem acoplar a interface ao provedor.

### yfinance e CoinGecko

São serviços de terceiros e podem impor limites, mudar formato ou retornar dados atrasados. yfinance não é uma API oficial de custódia da corretora. Tickers B3 recebem sufixo .SA por padrão; símbolos de outros mercados devem usar moeda USD e seu símbolo Yahoo completo. O histórico USD/BRL converte os preços para reais. Para criptoativos, BTC, ETH, SOL, ADA, XRP e DOGE têm IDs pré-configurados. Outras moedas usam o ID CoinGecko; essa fonte retorna valores em BRL.

Se o CoinGecko pedir uma chave Demo, defina a variável de ambiente COINGECKO_DEMO_API_KEY antes de iniciar o aplicativo. A chave não é gravada no banco.

## Limites analíticos

- O preço e o valor total de mercado são estimativas baseadas na cotação mais recente disponível.
- A série histórica do portfólio aplica pesos atuais ao histórico de ativos; não reconstrói o caminho real da carteira.
- Não há preço médio tributário, apuração fiscal, cálculo de imposto, ordens, custódia ou recomendação automatizada.
- A volatilidade EWMA segue o lambda do documento, porém a qualidade depende da quantidade e qualidade das observações.
- Sharpe e CAPM dependem do período, benchmark, taxa livre de risco e dados. A taxa Selic/CDI é digitada pelo usuário; o sistema não consulta a série automaticamente.
- O CAPM usa benchmarks aproximados de Yahoo Finance. Moedas, ativos internacionais e períodos sem dados pareados podem invalidar comparação.
- O dividend yield é calculado a partir dos proventos registrados. Proventos não fornecidos pelo provedor devem ser lançados manualmente.
- A previsão usa juros compostos e choques normais para ilustrar cenários. Não é uma previsão de retorno nem uma banda de confiança calibrada.
- A simulação manual usa retornos sintéticos quando não há histórico do ativo.
- Exportação e importação de OFX cobrem blocos simples de compra/venda com identificador de segurança reconhecido como ticker. Outros dialetos precisam ser convertidos para CSV.
- A versão local é de usuário único e sem senha de aplicação. A proteção depende da conta e criptografia do dispositivo. A Fase 2 em nuvem, TLS, autenticação e 2FA foi deixada fora da entrega.

## Premissas originais preservadas

- Metas de 1,5% e 2,0% ao mês são valores de referência editáveis, nunca promessa de retorno.
- A referência de 40% de renda fixa é contextual e não restringe a carteira.
- O alerta de concentração começa em 25% e pode ser alterado.
- A aplicação é passiva e analítica.

## Segurança e operação

- O app escuta em localhost por padrão.
- Não insira credenciais de corretora no app nem compartilhe o arquivo SQLite sem criptografia.
- A chave CoinGecko opcional vem de variável de ambiente.
- O banco não é criptografado por esta aplicação.
- Faça uma cópia externa para proteger contra perda do computador; backups na mesma pasta não protegem contra falha do disco.
- Não abra o banco em outro programa enquanto o app estiver em execução.

## Referências técnicas

- Streamlit cache: https://docs.streamlit.io/develop/api-reference/caching-and-state/st.cache_data
- Histórico yfinance: https://ranaroussi.github.io/yfinance/reference/api/yfinance.Ticker.history.html
- CoinGecko market chart: https://docs.coingecko.com/reference/coins-id-market-chart
- Banco Central, série diária da Selic: https://dadosabertos.bcb.gov.br/pt_BR/dataset/11-taxa-de-juros---selic
