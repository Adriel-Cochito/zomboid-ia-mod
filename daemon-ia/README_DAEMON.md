# daemon-ia

Aplicação Python externa que dá voz e raciocínio ao Project Zomboid. Ela não entra no jogo: lê arquivos de texto gravados pelos mods Lua e responde com áudio no Windows (e, no caso do NPC, com comandos de volta para o jogo).

Há duas vozes no mesmo processo:

- a do **sobrevivente**, disparada pelos eventos de `MeuTTSMod`;
- a do **companheiro** (Marcos, por padrão), disparada pelos eventos de `TTS_NPC_Bridge`.

As duas compartilham um único modelo de voz (Coqui XTTS-v2) e um único modelo de linguagem no Ollama. A fala do personagem tem prioridade: o NPC só toca quando o daemon não está ocupado com a voz do jogador.

## Como as peças se ligam

```
MeuTTSMod          TTS_events.txt     daemon-ia          alto-falante
(jogador local)  ------------------>  voz + reflexão  ---------------->  Windows

TTS_NPC_Bridge     NPC_events.txt     daemon-ia          NPC_commands.txt
(adapter Bandits) ------------------>  cérebro do NPC  ---------------->  Lua
```

Os três arquivos ficam em `%USERPROFILE%\Zomboid\Lua\`:

| Arquivo | Direção | Formato |
| --- | --- | --- |
| `TTS_events.txt` | Lua → daemon | `evento\|detalhe` |
| `NPC_events.txt` | Lua → daemon | `evento\|payload` |
| `NPC_commands.txt` | daemon → Lua | `seq\|tipo\|arg\|extra` |

O daemon começa a ler `TTS_events.txt` pelo fim, então o que já estava no arquivo de sessões anteriores é ignorado.

## Requisitos

- Windows. A reprodução usa `winsound`.
- Python com [Coqui TTS](https://github.com/coqui-ai/TTS) (`TTS`) e PyTorch. Se houver GPU CUDA, o XTTS sobe nela; senão, usa CPU.
- [Ollama](https://ollama.com/) em `http://localhost:11434`, com o modelo definido em `src/config.py` (`OLLAMA_MODEL`, hoje `gemma2:2b`).
- Um WAV de referência em `modelos_voz/`. O nome esperado está em `VOZ_MODELO` (`src/config.py`).
- Para o companheiro ter voz própria, coloque `modelos_voz/npc_voice.wav`. Sem esse arquivo, o NPC usa a voz embutida `Damien Black` do XTTS, separada da voz do jogador.
- No jogo (build 42): `MeuTTSMod` ativo para a voz do jogador, e `TTS_NPC_Bridge` mais o mod Bandits para o companheiro.

## Como rodar

Na pasta `daemon-ia`, com o Ollama já no ar:

```powershell
python tts_daemon.py
```

A janela de configuração (voz do personagem, voz do NPC, quantidade de falas e ligar o daemon) abre fora do jogo:

```powershell
python configurar.py
```

Na subida o processo:

1. aquece o modelo do Ollama;
2. carrega o XTTS-v2;
3. pré-gera o cache das frases estáticas em `audios_gerados/`;
4. sobe o módulo do NPC;
5. passa a observar `TTS_events.txt`.

Deixe o daemon aberto enquanto joga. Ao descansar ou dormir no jogo, o mod emite `rest` e o daemon entra no ciclo de reflexão do dia.

Quem vai jogar usa o `iniciar.bat` na raiz do repositório. Ele instala em `runtime/` só o que ainda falta, abre a tela de configuração e cria o atalho da área de trabalho.

## Voz do jogador

Cada linha nova de `TTS_events.txt` entra no histórico do dia (`StateManager`). Eventos de fala passam por cooldown próprio (`EVENT_COOLDOWN_S` em `src/config.py`). Se o daemon já estiver falando, o evento é descartado para a voz e continua só no histórico.

A frase sai assim:

1. em cerca de 40% dos casos, uma frase estática de `PHRASES` / `FALLBACK_TEMPLATES`;
2. nos demais, o Ollama escreve uma fala curta (3 a 9 palavras) com exemplos de estilo;
3. a fala da LLM é recusada se tiver tamanho errado, palavra proibida ou, no loot, se não citar o item ou falar como se o personagem tivesse consumido o que só pegou;
4. se a LLM falhar, volta a frase estática.

O tom do áudio muda com o evento: pânico (`zombie_back`, `hurt`, `panic`…), loot, fala normal, e reflexão lenta no descanso. O WAV é cacheado por texto, parâmetros e voz. Texto igual não é sintetizado de novo.

`player_status` só atualiza profissão, dias, horas e perks. `wake_up` entra no histórico e não tem fala própria.

### Reflexão ao descansar

O evento `rest` (personagem deitou ou dormiu) dispara um pipeline em quatro passos. Os dois primeiros são determinísticos; a LLM só dá a voz no fim.

1. **Perfil do dia** (`src/engine/log_analyst.py`). Conta loot por categoria, incidentes e necessidades que ficaram sem resolução (sangramento, fome, sede). A etapa de vida sai dos dias sobrevividos: início (&lt; 7), meio (&lt; 30) ou avançado.
2. **Estratégia** (`src/engine/strategy_engine.py`). Cruza esse perfil com `src/game_knowledge/game_knowledge.json` (saúde, suprimentos, fortificação, veículos/energia, combate) e escolhe até três direções para o dia seguinte.
3. **Narrativa** (`src/engine/narrative_generator.py`). O Ollama devolve JSON: resumo do dia no passado, uma fala em tom de dúvida e uma missão por direção. Campo inválido cai num texto determinístico.
4. **Fala do objetivo**. Segunda fala, também lenta, sobre o que talvez valha fazer amanhã.

O resultado vai para `src/data/missions.json` (missão atual, resumo e as últimas 7 reflexões). Em seguida o daemon toca a reflexão e, depois de uma pausa curta, a fala do objetivo.

## Companheiro (NPC)

`NpcCompanion` (`src/npc/npc_brain.py`) observa `NPC_events.txt` e devolve ordens em `NPC_commands.txt`. Quem move o corpo no jogo é o adapter Lua; o Python decide modo, fala e memória.

Estado que chega no evento `state` (a cada ~5 s, enquanto o NPC existe): nome, modo, vida do NPC, vida do jogador, ameaças próximas, munição e loot perto.

Decisão de modo (`src/npc/npc_decision.py`), nesta ordem:

- ordem manual do jogador trava a IA por 120 s (`MANUAL_OVERRIDE_S`);
- regras fixas: vida baixa recua para `seguir`, jogador ferido ou muitos zumbis passam a `defender`, área calma com loot pode ir a `saquear`;
- a LLM só desempata um caso ambíguo (calmo, loot perto, NPC meio ferido) e a resposta tem de ser um modo da lista.

Modos canônicos: `seguir`, `ficar`, `defender`, `saquear`. No Bandits, `saquear` vira um pedido de busca (`fetch`), porque o programa Companion daquele mod não looteia.

Falas do NPC:

- frases estáticas em `src/npc/npc_config.py` (`NPC_PHRASES`), pré-geradas no arranque;
- LLM fora de combate, com a mesma regra do loot (não inventar consumo);
- fila com prioridade (`danger` &gt; ordem/conversa &gt; evento &gt; conversa ociosa), TTL e cooldown por tipo;
- conversa ociosa entre 90 e 180 s quando está calmo.

A memória (`src/data/npc_memory.json`) guarda fatos recentes, vínculo e contagens (abates, buscas, ordens, conversas). O nome padrão é Marcos (`NPC_NAME`).

Chat do jogador (`say` no menu do jogo, ou pelo simulador):

- “procura combustível”, “pega comida”, “lotear” e equivalentes viram `fetch` com palavras-chave (`src/npc/npc_chat.py`);
- “fica”, “segue”, “defende” e equivalentes viram ordem de modo;
- o resto é conversa livre, respondida pelo Ollama.

Pausa: `TTS_NPC_Bridge` emite `paused` / `resumed`. Enquanto o jogo está pausado, o ticker do NPC não gera fala nova.

Para desligar só o NPC, ponha `NPC_ENABLED = False` em `src/npc/npc_config.py`. A voz do jogador continua.

## Estrutura

```
tts_daemon.py                 entrada: voz do jogador + reflexão + NPC
src/config.py                 Ollama, voz, cooldowns, frases do sobrevivente
src/core/event_monitor.py     tail de TTS_events.txt
src/core/state_manager.py     histórico do dia e status do personagem
src/services/ollama_service.py   /api/chat, histórico anti-repetição, modo JSON
src/services/phrase_service.py   falas curtas de evento, com validação
src/services/tts_service.py      XTTS-v2, limpeza de texto e cache WAV
src/engine/                   perfil do dia, estratégia, narrativa, conhecimento
src/storage/mission_store.py  missions.json
src/game_knowledge/           itens e ações válidas do Zomboid, por categoria
src/npc/                      protocolo, estado, decisão, falas, voz e memória
src/data/                     missions.json e npc_memory.json
modelos_voz/                  WAVs de referência (jogador e, se houver, NPC)
audios_gerados/               cache de WAV (não versionado)
tools/npc_simulator.py        escreve NPC_events.txt sem abrir o jogo
tests/test_npc_smoke.py       fumaça do NPC, sem XTTS e sem Ollama
```

`src/cognition_engine.py` e os scripts em `scripts_testes/` são experimentos antigos. O caminho usado pelo `tts_daemon.py` é o de `src/engine/` e `src/services/`.

## Testar sem o jogo

Fumaça do cérebro do NPC (não carrega modelo):

```powershell
python tests/test_npc_smoke.py
```

Com o daemon já rodando, em outro terminal, a partir de `daemon-ia`:

```powershell
python tools/npc_simulator.py state "hp=80;player_hp=90;threats=0;loot_near=0"
python tools/npc_simulator.py loot "item=Lata de Feijão"
python tools/npc_simulator.py say "procura combustível"
python tools/npc_simulator.py watch
```

`watch` mostra as linhas novas de `NPC_commands.txt`.

## Onde ajustar

| Quero mudar | Arquivo |
| --- | --- |
| Modelo do Ollama, temperatura, cooldowns e frases do jogador | `src/config.py` |
| Nome, voz, modos e frases do NPC | `src/npc/npc_config.py` |
| Itens e ações que a reflexão pode sugerir | `src/game_knowledge/game_knowledge.json` |
| Voz do jogador, voz do NPC, quantidade de falas, NPC ligado | `python configurar.py` (`config_usuario.json`) |
| Voz clonada do jogador, se a janela não escolher outra | `modelos_voz/` + `VOZ_MODELO` |
| Voz clonada do NPC, se a janela não escolher outra | `modelos_voz/npc_voice.wav` |
