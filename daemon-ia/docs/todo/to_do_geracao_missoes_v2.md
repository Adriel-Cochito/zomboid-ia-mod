Aqui está o planejamento de engenharia e arquitetura para a refatoração e implementação do novo motor de decisões e missões. O objetivo principal é desacoplar os componentes utilizando princípios **SOLID**, garantindo que alterações no algoritmo de IA ou na estrutura de missões fiquem isoladas e não afetem o daemon de áudio ou o monitoramento de eventos.

---

## 1. Reorganização Estrutural (Modularização por Responsabilidade)

Para evitar que o projeto se torne um monólito acoplado, vamos reorganizar a pasta `src/` em módulos independentes baseados no **Princípio da Responsabilidade Única (SRP)**:

* **`src/core/`** -> Orquestrador principal (`tts_daemon.py`), controle de concorrência (`threading.Lock`) e ciclo de vida do daemon.
* **`src/services/`** -> Serviços externos e de infraestrutura:
* `ollama_service.py`: Comunicação bruta com a API do Ollama (gerenciamento de prompts e chamadas).
* `tts_service.py`: Gerenciamento do modelo XTTS-v2 e reprodução de áudio.


* **`src/engine/`** -> O cérebro cognitivo dividido em agentes especializados (Pipeline Multi-Pass):
* `log_analyst.py`: Responsável por minerar e correlacionar os logs do `StateManager`.
* `knowledge_filter.py`: Responsável pelo *Query-Driven Filtering* do `game_knowledge.json`.


* `strategy_engine.py`: Cruza o estado do personagem (skills/status capturados no descanso) com as necessidades táticas.
* `narrative_generator.py`: Aplica a persona e gera os textos finais no tom sugestivo.


* **`src/storage/`** -> Persistência de dados limpa (separando a leitura/escrita do `missions.json` e dos estados temporários).



---

## 2. Fases do Planejamento de Implantação

### Fase 1: Isolamento e Contratos (Preparação SOLID)

* Criar interfaces ou classes base bem definidas para os serviços de LLM e armazenamento.
* Garantir que o `StateManager` exponha métodos limpos de consulta para que o motor de análise de logs consiga buscar eventos específicos (ex: filtrar apenas `stealth_broken` ou `hurt` do dia atual) sem expor a estrutura interna de dados.

### Fase 2: Módulo de Contexto Dinâmico (Filtros e Skills)

* **Captura no Descanso:** Ajustar o gatilho de descanso (`rest`) para recolher um snapshot do estado/perícias do personagem enviado pelo jogo.
* **Filtro Inteligente de Conhecimento:** Desenvolver o `knowledge_filter.py` para ler o `game_knowledge.json` de forma seletiva, injetando no prompt *apenas* as categorias e itens reais pertinentes aos eventos detectados no dia, poupando tokens.



### Fase 3: Pipeline Multi-Pass da IA (O Algoritmo de Decisão)

Substituir a chamada única de reflexão por uma cadeia sequencial de raciocínio isolada no diretório `src/engine/`:

1. **Passo 1 (Analista):** A LLM resume os subtextos e falhas operacionais com base nos logs minerados.
2. **Passo 2 (Estrategista):** O sistema cruza os problemas com as skills atuais do personagem e as ações válidas do conhecimento técnico.
3. **Passo 3 (Escritor):** A LLM transforma o diagnóstico em diário de bordo e objetivos estruturados, mantendo rigorosamente o tom sugestivo.

### Fase 4: Persistência e Enriquecimento das Missões

* Atualizar o `MissionStore` para salvar no `missions.json` não apenas títulos genéricos, mas dados ricos (categoria técnica, itens recomendados e justificativa baseada nos erros do dia).



---

## 3. Benefícios Arquiteturais

* **Extensibilidade (OCP):** Se quisermos adicionar um novo passo no pipeline de IA (por exemplo, um validador de realismo de inventário), criamos um novo ficheiro em `src/engine/` sem precisar alterar o código do orquestrador principal.
* **Manutenibilidade:** Erros na geração de texto da LLM ou falhas ao ler o ficheiro de conhecimento ficam confinados nos respetivos serviços, facilitando *debugging* e testes unitários.

---

Qual destas fases gostaria de detalhar ou começar a estruturar primeiro no código?