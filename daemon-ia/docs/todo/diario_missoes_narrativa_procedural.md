Aqui está o documento Markdown completo e atualizado com a **nova estrutura de pastas e módulos**, pronto para você salvar em `docs/todo/diario_missoes_narrativa_procedural.md` (ou no arquivo de sua preferência).

---

```markdown
# 📋 To-Do List: Sistema de Reflexão Cognitiva, Áudios Modulares e Missões

## 🏗️ Estrutura de Pastas e Arquitetura do Projeto

A organização do projeto na pasta principal `IA Gaming local/` adota a separação de responsabilidades em módulos dentro do pacote `src/`:

```text
IA Gaming local/
│
├── src/                          📂 Código-fonte modular
│   ├── __init__.py
│   ├── config.py                 # Parâmetros de áudio, cooldowns, caminhos e frases estáticas
│   ├── event_monitor.py          # Leitura e tail do TTS_events.txt
│   ├── state_manager.py          # Timeline de eventos e controle do timestamp da reflexão
│   ├── cognition_engine.py       # Prompts modulares (Físico, Tático, Resumo/Missões) e Ollama
│   ├── audio_pipeline.py         # Limpeza de texto (clean_text_for_tts), cache, XTTS-v2 e pipelining
│   └── mission_store.py          # Gestão e gravação do missions.json
│
├── modelos_voz/                  📂 Modelos de referência de voz (.mp3 / .wav)
├── audios_gerados/               📂 Cache de áudios renderizados (.wav)
├── Audios bons/                  📂 Seleção e amostras de destaques
├── scripts_testes/               📂 Protótipos e testes avulsos
│
├── docs/                         📂 Documentação e rascunhos do projeto
│   ├── ideias.md
│   └── todo/
│       └── diario_missoes_narrativa_procedural.md
│
├── venv/                         📂 Ambiente virtual Python
│
├── api_tts.py                    # Script utilitário / API
└── tts_daemon.py                 # 🚀 Ponto de entrada principal (Orquestrador que importa 'src/')

```

---

## 📋 Detalhamento das Etapas de Implementação

### FASE 1: Mapeamento no LUA (`TTS_Event_Tracker.lua`)

* [ ] **Gatilho do Evento de Descanso (`rest`):**
* [ ] Confirmar o envio do evento `rest` com detalhes de estado do jogador ao ser acionado no jogo.
* [ ] Ajustar o cooldown no Lua para evitar chamadas duplas acidentais ao clicar em descansar.



---

### FASE 2: Configurações Globais e Estado (`src/config.py` & `src/state_manager.py`)

* [ ] **Módulo `src/config.py`:**
* [ ] Centralizar caminhos absolutos (`EVENTS_FILE`, `CACHE_DIR`, `SPEAKER_WAV`, `MISSIONS_FILE`).
* [ ] Configurar dicionários de parâmetros do TTS (`TTS_PARAMS_NORMAL`, `TTS_PARAMS_SLOW`, `TTS_PARAMS_LOOT`).
* [ ] Definir a tabela de cooldowns de eventos.


* [ ] **Módulo `src/state_manager.py`:**
* [ ] Implementar a estrutura de lista/buffer para registrar eventos contínuos do jogo.
* [ ] Criar a variável de controle `last_reflection_timestamp`.
* [ ] Criar a função para extrair e isolar apenas os eventos ocorridos após `last_reflection_timestamp` e atualizar o ponteiro após a reflexão.



---

### FASE 3: Monitoria do Arquivo de Eventos (`src/event_monitor.py`)

* [ ] **Módulo `src/event_monitor.py`:**
* [ ] Isolar a lógica de leitura dinâmica (*tail*) do arquivo `TTS_events.txt`.
* [ ] Processar linhas no formato `evento|detalhe` e repassá-las diretamente para o `state_manager`.



---

### FASE 4: Motor Cognitivo e Prompts Modulares (`src/cognition_engine.py`)

* [ ] **Módulo `src/cognition_engine.py`:**
* [ ] Configurar a integração HTTP assíncrona/síncrona com a API do Ollama (`qwen2.5:3b`).
* [ ] **Bloco 1 (Análise Física):** Prompt para avaliar exaustão, ferimentos, fome e sede.
* [ ] **Bloco 2 (Análise Tática):** Prompt para sintetizar os combates, sustos, hordas e furtividade quebrada.
* [ ] **Bloco 3 (Resumo e Missões):** Prompt instruindo a LLM a retornar uma fala de fechamento acompanhada de uma estrutura JSON limpa contendo 1 ou 2 missões/objetivos para o dia seguinte.



---

### FASE 5: Processamento de Áudio e Cache (`src/audio_pipeline.py`)

* [ ] **Módulo `src/audio_pipeline.py`:**
* [ ] Manter a função sanitizadora `clean_text_for_tts` (removendo o ponto final do encerramento da frase `text.rstrip('.')` para evitar o erro de narração "ponto").
* [ ] Gerenciar a chave de hashing do cache `.wav`.
* [ ] Inicializar e gerenciar a execução do Coqui XTTS-v2 em GPU.
* [ ] Implementar a quebra por chunks e o encadeamento de áudios modulares sem travamentos.



---

### FASE 6: Persistência de Missões (`src/mission_store.py`)

* [ ] **Módulo `src/mission_store.py`:**
* [ ] Criar a função de extração/parse do bloco JSON de missões emitido no Bloco 3 pela LLM.
* [ ] Implementar a gravação e atualização atômica do arquivo `missions.json` na raiz ou pasta informada.



---

### FASE 7: Orquestração Central (`tts_daemon.py`)

* [ ] **Atualização do `tts_daemon.py`:**
* [ ] Refatorar o daemon principal para importar e conectar os módulos da pasta `src/`.
* [ ] Mapear a chegada do evento `rest` para pausar a fila padrão e disparar a sequência cognitiva dos 3 blocos em cadeia.
* [ ] Garantir o fluxo ponta a ponta: *Gatilho `rest` no Lua ➔ Coleta de Eventos (state_manager) ➔ Geração dos Blocos (cognition_engine) ➔ Pipelining de Áudio (audio_pipeline) ➔ Gravação de Objetivos (mission_store)*.



```

---

Qual arquivo da estrutura (`src/config.py`, `src/state_manager.py`, etc.) você quer criar/montar primeiro?

```