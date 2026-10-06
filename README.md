# Carteira Clara

Plataforma local de análise pessoal de investimentos criada a partir dos requisitos do Guia Mestre. A aplicação separa a carteira real, as projeções e a simulação de ativos externos. Os dados da carteira ficam em um banco SQLite no computador do usuário.

## Começar no Windows

1. Extraia todo o ZIP para uma pasta local.
2. Instale Python 3.9 ou superior. Python 3.11 ou 3.12 é recomendado para instalar versões atuais das bibliotecas.
3. Abra a pasta extraída e execute setup_windows.bat uma vez. O instalador cria um ambiente isolado e instala as dependências.
4. Execute run_windows.bat. O navegador abrirá a plataforma em localhost.
5. Cadastre a carteira ou importe um extrato na área Cadastro e importação.

Também é possível instalar e executar em macOS ou Linux com setup_unix.sh e run_unix.sh. Os comandos detalhados estão em docs/GUIA_DE_USO.md.

## O que está incluído

- Estado atual: posições, preço médio, valor estimado, resultado não realizado, alocação, proventos e indicadores de risco.
- Previsão: cenários determinísticos e faixa de incerteza simulada em até 600 meses.
- Simulação: análise histórica e de impacto hipotético de um ativo externo.
- Dados: SQLite, importação CSV e OFX compatível, entrada manual, cotações de mercado e cópias locais de segurança.
- Documentação de uso, fórmulas, modelo de dados, arquitetura, decisões e rastreabilidade dos requisitos.

## Arquivos de dados

O primeiro início cria data/investimentos.db. Cópias automáticas são guardadas em data/backups. Essas pastas contêm informações financeiras privadas: não as compartilhe e inclua-as em seus backups pessoais.

## Escopo de integração

O Guia Mestre não fornece contrato, credenciais ou fluxo de autorização para uma API de custódia Banco Inter/B3. Por isso, a entrega importa transações compatíveis via CSV/OFX e permite cadastro manual; ela não tenta acessar contas do investidor. Cotações de mercado são complementares e podem estar atrasadas ou indisponíveis.

Consulte:

- docs/GUIA_DE_USO.md
- docs/MAPA_DE_DESENVOLVIMENTO.md
- docs/METODOS_E_MODELO_DE_DADOS.md
- docs/DECISOES_E_LIMITACOES.md

## Tecnologias

Python, Streamlit, Pandas, NumPy, Plotly e SQLite. yfinance fornece séries de mercado de ações, ETFs e FIIs; CoinGecko fornece histórico de criptoativos em BRL. As fontes externas são opcionais para iniciar o sistema; cadastro manual e dados locais continuam disponíveis.

Ativos Yahoo podem usar BRL ou USD. Séries em USD são convertidas para BRL pelo histórico USD/BRL do Yahoo Finance. Criptoativos via CoinGecko já chegam em BRL.

## Aviso

Esta aplicação é uma ferramenta de registro e análise, não executa ordens, não substitui uma corretora, não fornece recomendação financeira e não garante resultados. Rentabilidade passada não representa garantia de rendimentos futuros.
