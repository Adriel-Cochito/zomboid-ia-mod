Antes do plano, um bloqueio: **o Superb Survivors é um mod de Build 41 e, segundo o [PZ Fans](https://pzfans.com/zomboid_lonely_best_npc_mods_for_friends_and_foes_in_build_4142/), "quebra no 42"**. Também não achei nenhum port oficial para B42. Por isso a Fase 0 abaixo decide a base do NPC antes de qualquer código.

# Planejamento: NPC companheiro com IA de voz

**Princípio:** o mod base manda no corpo do NPC (andar, atacar, saquear). A IA cuida da voz, da personalidade e, no máximo, de escolher o modo entre os que o mod já oferece.

## Fase 0 – Spike de viabilidade (antes de tudo)

Objetivo: descobrir qual mod serve de base no B42 e o que dá para controlar por Lua.

| Opção | Situação no B42 | Risco |
|---|---|---|
| Superb Survivors | B41 apenas | Alto: provável porte ou downgrade para B41 |
| Bandits v2 | B41 e B42, mas hostil por padrão e com [relatos de bugs de IA e desempenho](https://pzfans.com/zomboid_npc_mods_in_b42_surviving_the_apocalypse_with_friends/) | Médio: preciso verificar se existe modo aliado/companheiro |
| Knox Event Expanded | B42 alpha, instalação manual | Alto: instável |

O que verificar em 1 a 2 horas, com o mod instalado:
1. Existe um estado "companheiro" ou "seguir o jogador"?
2. Quais funções Lua mudam o comportamento (seguir, ficar, guardar, saquear)?
3. Dá para ler o estado do NPC (vida, alvo, inventário)?

**Decisão pendente sua:** se nenhum mod B42 servir, jogar B41 com Superb Survivors é o caminho mais seguro. Ele tem as ordens que você descreveu (convidar para o grupo, "ficar aqui", patrulha e guarda), mas é só singleplayer.

## Fase 1 – Contrato de comunicação (arquivos de texto)

Reaproveita o padrão que você já tem. São 3 arquivos, cada um com um único escritor:

- `TTS_events.txt` (Lua → daemon), que já existe. Ganha eventos do NPC: `npc_state|modo=seguir;vida=80;alvo=zumbi`, `npc_hurt`, `npc_loot|item`, `npc_kill`.
- `NPC_commands.txt` (daemon → Lua). Cada linha é `modo|seguir`, `modo|defender`, `modo|saquear` ou `modo|ficar`, mais um `id` de linha para confirmação.
- `NPC_chat.txt` (jogador → daemon). Contém o comando do menu ou o texto livre.

Regras do protocolo: o Lua faz polling a cada ~1 s, guarda o offset lido, e as linhas são idempotentes (com `id`).

## Fase 2 – Mod ponte em Lua (adapter)

Um mod pequeno, separado do mod base, com uma interface fixa:

```
NpcAdapter.getState(npc)  →  vida, modo, alvo, inventário resumido
NpcAdapter.setMode(npc, mode)  →  chama a função NATIVA do mod base
```

Só esse arquivo conhece o mod base. Se você trocar de mod, troca só o adapter (mesmo princípio SOLID do seu TODO). Ele não reimplementa combate nem loot.

## Fase 3 – Daemon: módulo `src/npc/`

- `npc_state.py`: estado atual do NPC, igual ao `StateManager`.
- `npc_persona.py`: nome, histórico, humor e relação com o jogador (confiança sobe quando você o protege).
- `npc_speaker.py`: fila de falas com prioridade (perigo > ordem > comentário), com cooldown por evento. Só uma voz fala por vez, e a sua tem prioridade sobre a do NPC.
- Voz própria: **o mesmo modelo XTTS com outro `speaker_wav`**. Não carrega um segundo modelo, então não gasta VRAM extra. O cache já inclui o nome da voz no hash, então os áudios do NPC ficam separados.

## Fase 4 – Decisão de modo (IA só sugere)

Em camadas, da mais barata para a mais cara:

1. **Regras determinísticas** (Python, sem LLM): vida abaixo de 30% → `defender`/`seguir`; sem munição → `seguir`; área limpa e item por perto → `saquear`.
2. **LLM só em empate ou contexto ambíguo**, devolvendo JSON limitado a `{"modo": <enum>, "motivo": "..."}`. A saída é validada contra a lista de modos, e se vier inválida a decisão cai no padrão do mod.
3. **Histerese**: troca de modo no máximo a cada ~20 s, para o NPC não ficar oscilando.
4. **Sua ordem manual sempre vence**, e a IA só volta a sugerir depois de um tempo.

O motivo da decisão vira fala ("Tô sem munição, fico perto de você").

## Fase 5 – Interação (menu + conversa livre)

Em duas etapas, para controlar custo e risco:

- **5a, menu de comandos.** Clique direito no NPC → Seguir / Ficar / Defender / Saquear. O Lua escreve em `NPC_chat.txt`, o daemon responde por voz.
- **5b, conversa livre.** O LLM recebe o texto e devolve `{fala, modo_opcional}`. Se o jogador diz "fica aí", o modo vira `ficar`. Começar por **texto digitado**. Voz com STT (faster-whisper pequeno, em CPU, com push-to-talk) fica para depois, porque come CPU e latência.

## Fase 6 – Orçamento de hardware (seu "apertado")

Você já tem evictions de VRAM no log do jogo, então:
- 1 NPC, 1 modelo XTTS, 1 modelo Ollama (qwen2.5:3b). Nada de modelo maior por enquanto.
- Falas do NPC majoritariamente de **templates em cache** (60 a 70%), com LLM só para variar, como você já faz.
- A LLM nunca roda durante combate. Em combate, só frases estáticas pré-geradas.
- Medir antes: FPS e VRAM com o jogo aberto + daemon, e só depois liberar a conversa livre.

## Ordem de entrega

1. Fase 0, o spike. Define tudo o resto.
2. Fases 1 e 2 com o NPC só **emitindo eventos** (sem comandos) e o daemon só falando.
3. Fase 4, decisão por regras. Depois o LLM como desempate.
4. Fase 5a (menu), depois 5b (texto), e voz por último.

## Riscos principais

- **Mod base sem API** de controle. Mitigação: o spike da Fase 0.
- **Desempenho** do jogo com NPCs mais o daemon. Mitigação: 1 NPC e fila de falas.
- **Atualizações do mod** quebrando o adapter. Mitigação: isolar tudo no `NpcAdapter`.

**Para eu detalhar a Fase 0:** qual caminho você prefere, ficar no B42 (testar o Bandits como base) ou voltar ao B41 (Superb Survivors)? Se você tiver o mod instalado, mande a lista de arquivos `.lua` dele que eu aponto onde ficam as funções de modo.

Se quiser, transformo este plano em um documento (`.md` como o seu TODO anterior) para você acompanhar as fases.

Sources:
- [Zomboid Lonely? Best NPC Mods for Friends (and Foes) in Build 41/42, PZ Fans](https://pzfans.com/zomboid_lonely_best_npc_mods_for_friends_and_foes_in_build_4142/)
- [Zomboid NPC Mods in B42: Surviving the Apocalypse With Friends(?), PZ Fans](https://pzfans.com/zomboid_npc_mods_in_b42_surviving_the_apocalypse_with_friends/)