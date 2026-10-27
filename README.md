# Zomboid IA Mod — Voz e Raciocínio em Tempo Real

Este projeto traz um ecossistema autônomo de inteligência artificial local para o **Project Zomboid** (Build 42). Ele dá voz, autonomia e raciocínio em tempo real tanto ao seu **sobrevivente** quanto a um **companheiro NPC**.

---

## 🛠️ Como Instalar e Rodar

Você não precisa saber programar. O instalador **`iniciar.bat`** cuida de todas as dependências e pastas.

### 1. Se você baixou os mods pela Oficina da Steam

Assine na Oficina:

* **TTS Dynamic Voice Mod**


* **TTS NPC Bridge**


* **Bandits** *(obrigatório apenas se for usar o companheiro NPC)*

Em seguida:

1. Baixe o ZIP deste repositório GitHub.


2. Mantenha em qualquer pasta a pasta `daemon-ia` e o arquivo `iniciar.bat`.


3. Dê dois cliques em **`iniciar.bat`**.



---

### 2. Se você baixou direto pelo GitHub

1. Clique no botão verde **Code** > **Download ZIP** no topo desta página.


2. Extraia o arquivo.


3. Mova a pasta inteira contendo `iniciar.bat`, `daemon-ia`, `MeuTTSMod` e `TTS_NPC_Bridge` para:


```text
C:\Users\SeuNome\Zomboid\mods

```


(Troque `SeuNome` pelo seu usuário do Windows. Não é a pasta da Steam e nem a pasta onde o jogo está instalado).


4. Abra o Project Zomboid, entre em **Mods** e ative:


* **TTS Dynamic Voice Mod**


* **TTS NPC Bridge**


* **Bandits** *(se for jogar com o companheiro)*


5. Reinicie o jogo conforme solicitado.



---

## 🖥️ Usando o Aplicativo

1. Execute o arquivo **`iniciar.bat`** (ou o atalho criado na Área de Trabalho **Iniciar Daemon Zomboid**).


2. Na primeira vez, a janela preta baixará as dependências e modelos de voz (pode demorar alguns minutos).


* *Se aparecer um aviso com `y/n`, digite `y` e aperte `Enter*`.




3. A janela de configuração abrirá automaticamente:


* Selecione a voz do personagem e a do NPC.


* Clique em **Iniciar**.




4. Deixe a aplicação aberta e bom jogo!



---

## 🚀 O que este mod faz (Arquitetura e Detalhes Técnicos)

### ⚡ Arquitetura e Comunicação em Tempo Real

* **Comunicação Desacoplada (Zero Lag):** Mods em Lua capturam eventos do jogo e escrevem em arquivos de log em disco (`tail` assíncrono), isolando completamente o processamento pesado do motor gráfico para garantir estabilidade e manter o jogo rodando liso sem quedas de FPS.


* **Processamento Externo (`daemon-ia`):** Um daemon em Python gerencia de forma integrada o modelo de linguagem Ollama (`gemma2:2b`) e o motor de clonagem de voz (Coqui XTTS-v2) rodando de forma local na máquina.


* **Smart Audio Cache:** O sistema armazena em cache os arquivos `.wav` gerados com base em hashes que combinam texto, parâmetros de voz e emoção, garantindo que frases recorrentes nunca sejam sintetizadas duas vezes e poupando ciclos de CPU/GPU.



---

### 🎙️ Eventos Capturados do Sobrevivente (`MeuTTSMod`)

O daemon monitora de forma contínua o arquivo de troca `TTS_events.txt` para traduzir o gameplay em reações faladas imediatas:

* **Combate, Danos e Pânico:**
* `panic` e `zombie_back`: Disparam reações verbais instantâneas de susto, alerta ou pânico quando o personagem se depara com zumbis à espreita ou é cercado.
* `hurt`: Captura eventos de dano físico e ferimentos, gerando expressões curtas de dor e sofrimento.


* **Sobrevivência, Loot e Coleta:**
* `loot`: Monitora a interação com o inventário e recipientes, fazendo o personagem narrar dinamicamente o nome dos itens coletados no chão ou em baús.


* **Status e Progressão:**
* `player_status`: Atualiza periodicamente estatísticas vitais do personagem, como tempo de sobrevivência (dias vivos), profissão escolhida e evolução de perks/habilidades.


* **Ciclo de Sono e Descanso:**
* `rest`: Disparado quando o sobrevivente deita para dormir, servindo como gatilho principal para iniciar o complexo pipeline de reflexão diária.
* `wake_up`: Registra o fim do ciclo de descanso no histórico interno do personagem sem gerar falas repetitivas ou poluição sonora desnecessária.



---

### 🤖 Eventos e Cérebro do Companheiro NPC (`TTS_NPC_Bridge`)

Totalmente integrado ao ecossistema do mod *Bandits*, o cérebro dedicado do NPC (`NpcBrain`) recebe pacotes de dados contínuos através de `NPC_events.txt` para tomar decisões autônomas:

* **Telemetria de Estado (~5s):**
* Coleta ciclos regulares de dados contendo o HP atual do NPC, a saúde do jogador, contagem exata de ameaças e zumbis nas proximidades, nível de munição e itens de loot disponíveis no raio de ação.


* **Hierarquia de Decisão e Modos Reativos:**
* **Perigo Extremo:** Avalia situações críticas de combate para acionar automaticamente o modo de defesa (`defender`) ou ordenar recuo tático se a vida estiver baixa.
* **Comandos Manuais:** Garante que ordens diretas dadas pelo jogador tenham prioridade absoluta, travando a autonomia temporariamente para obedecer comandos como `seguir`, `ficar` ou `saquear`.
* **Modo Ocioso (Idle):** Gerencia conversas casuais e espontâneas em momentos de calmaria, emitindo falas de ambientação após períodos de ociosidade.


* **Chat Interativo Integrado:**
* Interpreta comandos textuais inseridos pelo jogador diretamente no menu de chat do jogo (como pedidos para "pegar combustível", "ajudar a procurar comida" ou "defender a posição") convertendo-os em ações práticas do NPC e respostas faladas.





---

### 🧠 Algoritmo de Reflexão Pós-Sono (Pipeline em 4 Etapas)

Assim que o evento de descanso (`rest`) é concluído no jogo, o daemon executa um pipeline analítico sofisticado antes de devolver o controle total ao jogador:

1. **Perfil Diário (Stage 1):** Realiza uma contagem estatística e determinística de tudo o que aconteceu no dia, incluindo itens coletados por categoria, ferimentos sofridos e necessidades de sobrevivência que ficaram pendentes (como fome, sede ou sangramentos).


2. **Mapeamento Tático (Stage 2):** Cruza o perfil gerado do dia com um arquivo estruturado de matriz de conhecimento do jogo (`game_knowledge.json`), avaliando prioridades de saúde, suprimentos, fortificação e gestão de recursos.


3. **Geração de Missões (Stage 3):** O modelo de linguagem (Ollama) processa o resumo analítico e redige um JSON contendo um balanço narrativo do dia passado e define metas acionáveis e objetivos táticos para o dia seguinte.


4. **Síntese de Voz Lenta (Stage 4):** O sistema renderiza uma fala calma e reflexiva em tom de ponderação sobre os objetivos futuros, tocando a reflexão e as missões geradas logo após o personagem acordar.