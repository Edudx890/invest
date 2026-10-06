# Mapa de desenvolvimento e rastreabilidade

## 1. Resultado de produto

Carteira Clara implementa a Fase 1 local para um investidor: registra posições por transações, mantém cotações e proventos, analisa risco e retorno, projeta cenários e simula ativos externos. A solução não executa ordens.

## 2. Arquitetura

    Navegador local
        ↓
    app.py (navegação, formulários, gráficos Plotly)
        ↓
    portfolio_app (cálculos, importadores e adaptadores de mercado)
        ↓
    db.py (serviços SQLite)
        ↓
    data/investimentos.db + data/backups/

    yfinance / CoinGecko ──→ market_data.py ──→ histórico local
    CSV / OFX / entrada manual ──→ importers.py + formulários ──→ transações SQLite

O app é executado no próprio computador e vinculado a 127.0.0.1. SQLite é a fonte persistente para a carteira; os serviços externos fornecem dados de mercado opcionais.

## 3. Mapa dos arquivos

| Arquivo | Responsabilidade |
|---|---|
| app.py | Interface Streamlit, navegação, captura de dados e visualizações. |
| src/portfolio_app/db.py | Schema SQLite, consultas, gravação, backups e restauração. |
| src/portfolio_app/calculations.py | Posições, custo médio, retornos, EWMA, Sharpe, beta, CAPM, concentração e projeção. |
| src/portfolio_app/market_data.py | Consulta yfinance e CoinGecko, normalização de símbolos e preços. |
| src/portfolio_app/importers.py | Leitura e validação de CSV e operações OFX simples. |
| requirements.txt | Dependências Python da aplicação. |
| setup_windows.bat / setup_unix.sh | Criação do ambiente local e instalação de pacotes. |
| run_windows.bat / run_unix.sh | Inicialização local em 127.0.0.1. |
| examples/exemplo_transacoes.csv | Modelo de importação. |
| docs/GUIA_DE_USO.md | Instalação, uso, importação e resolução de problemas. |
| docs/METODOS_E_MODELO_DE_DADOS.md | Equações, convenções e esquema do banco. |
| docs/DECISOES_E_LIMITACOES.md | Premissas, fronteiras das integrações, segurança e limitações. |

## 4. Fluxos de dados

### Carteira atual

    Transações/importação → Ativos + Transacoes
    Histórico de mercado/manual → Cotacoes_Historico
    Dividendos e splits → Proventos
    Consulta SQLite → custo médio + cotação recente → métricas e gráficos

### Previsão

    Valor atual + aportes + horizonte + taxa mensal + EWMA
        → curvas determinísticas e simulação de 800 trajetórias
        → gráficos de cenários e tabela mensal

### Simulação de ativo

    Ticker/ID ou premissas manuais + aporte hipotético
        → histórico/retorno do ativo + benchmark
        → pesos atuais recalculados
        → retorno, EWMA, Sharpe, beta, CAPM e alocação hipotética

## 5. Matriz de rastreabilidade

| Objetivo/requisito do Guia Mestre | Implementação | Estado |
|---|---|---|
| OBJ-01 / RF-001: estado atual | Posições calculadas de transações, preços Yahoo/CoinGecko, cotações manuais, gráficos e indicadores | Implementado para dados inseridos/importáveis e cotações disponíveis |
| RF-001: API Inter/B3 | Não há contrato ou credenciais no documento; adaptador de custódia não é conectado | Substituído por contingência CSV/OFX/manual; integração real aguarda especificação |
| OBJ-02 / RF-002: previsão | Taxa escolhida, metas configuráveis, prazo meses/semestres/anos, aporte e banda 10–90 | Implementado |
| OBJ-03 / RF-003: novo ativo | Consulta de histórico, fallback de premissas manuais, impacto por aporte, métricas e alocação | Implementado para fontes disponíveis |
| RLN-001: retorno, EWMA, Sharpe | Funções em calculations.py e exibição no Estado atual/simulação | Implementado; rf manual |
| RLN-001: CAPM e beta | Beta e retorno CAPM na simulação, usando benchmarks indicados no código | Implementado quando há histórico pareado |
| RLN-001: splits e proventos | Histórico Yahoo registra dividendos/splits; eventos manuais e eventos obtidos mantêm origem | Implementado quando o provedor informa |
| RLN-003: metas e renda fixa | Preferências ajustáveis sem bloquear alocação | Implementado |
| RLN-004: fallback | Entrada manual, CSV/OFX e cotação local | Implementado |
| RLN-005: concentração | Alertas de classe e categoria acima do limite configurável | Implementado |
| RNF-001: consulta até 2 s / 10 mil transações | Índices e cache de 15 min reduzem carga; desempenho depende do hardware e do número de cotações externas | Não homologado; não há benchmark nesta entrega |
| RNF-002: operação local e fallback | Banco SQLite e modo manual independente dos provedores | Implementado |
| RNF-003: segurança local | Dados no arquivo local e bind em 127.0.0.1 | Implementado na Fase 1; sem criptografia de arquivo |
| RNF-004: navegação em até 2 cliques | Navegação por uma lista lateral | Implementado |
| RNF-005: Windows/macOS/Linux | Scripts de setup e execução separados | Preparado; não homologado em todos os sistemas |
| RNF-006: SQLite indexado | DDL e índices criados na inicialização | Implementado |

## 6. Etapas de desenvolvimento aplicadas

1. Interpretação do guia: identificação de objetivos, requisitos, regras, fronteiras e dependências.
2. Baseline de escopo: foco na Fase 1 local e separação das três áreas analíticas.
3. Modelo de dados: ativos, transações, cotações, proventos, configurações e índices.
4. Serviços de domínio: saldo e custo médio, retornos, risco, CAPM, dividendos e projeção.
5. Integrações: adaptadores de mercado com cache, persistência e fallback; importação de arquivo.
6. Interface: navegação, tabelas, formulários, cartões e gráficos interativos.
7. Operação local: scripts de instalação/execução, backup automático e restauração validada.
8. Documentação: guia do usuário, modelos matemáticos, decisões, riscos, limites e rastreabilidade.

## 7. Evoluções indicadas

1. Selecionar e documentar uma API oficial/autorizada de custódia, com credenciais e mapeamento de extrato antes de conectar Inter/B3.
2. Criar importadores específicos para os layouts efetivamente fornecidos pelas instituições.
3. Integrar uma série de taxa Selic/CDI e armazenar taxa por data em vez de entrada anual manual.
4. Reconstituir a carteira histórica por transação para substituir a série aproximada com pesos atuais.
5. Adicionar histórico de vendas e apuração de resultado realizado sem alegar apuração fiscal.
6. Homologar Windows, macOS e Linux, incluindo benchmark com 10 mil transações.
7. Implementar a Fase 2 em ambiente separado com requisitos próprios de autenticação, TLS, 2FA, controle de acesso e revisão de segurança.

## 8. Critérios operacionais para evoluir

Antes de conectar serviço de custódia, validar credenciais, consentimento, limites, formatos e mecanismo de revogação. Antes de usar métricas para decisão, conferir cotação, moeda, quantidade, origem, período e taxa livre de risco. Cada mudança de escopo deve atualizar a matriz, o schema e este mapa.
