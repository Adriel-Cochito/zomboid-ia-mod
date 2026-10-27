# TTS NPC Bridge

Mod de cliente do Project Zomboid (build 42) que coloca um NPC amigável no mundo e o liga ao `daemon-ia`. O núcleo da ponte não conhece o mod de NPC: quem cria, move e lê o companheiro é um adapter. Trocar de mod de NPC é trocar o adapter.

Identificação no jogo: **TTS NPC Bridge** (`id=TTS_NPC_Bridge`). Há um `mod.info` na raiz e outro em `42/`; a build 42 usa o de `42/`.

## Peças

| Arquivo | Papel |
| --- | --- |
| `42/media/lua/client/NPC_Bridge.lua` | Núcleo. Grava eventos, lê comandos, menu de contexto e detecção de pausa. |
| `42/media/lua/client/NPC_AdapterBandits.lua` | Adapter ativo. Cria e comanda um companheiro do Bandits 2 (B42). |
| `42/media/lua/client/NPC_AdapterStub.lua` | Companheiro virtual, só para testar a ponte sem Bandits. `ENABLE_STUB` está `false`. |
| `42/media/lua/client/NPC_BanditsProbe.lua` | Sonda de diagnóstico. Botão direito no chão: “TTS: sonda do Bandits v2”. Só lê dados e grava `NPC_probe2.txt`. |

O adapter Bandits se registra sozinho no fim do arquivo. Com o stub desligado, ele é o único adapter.

## O que o adapter Bandits faz

Depende do mod **Bandits** (APIs `BanditBrain`, `BanditUtils`, `BanditMenu`). Na prática:

- procura um bandit não hostil cujo `master` é o jogador local; se não achar, pede o spawn de um clã amigável no programa `Companion` (`sendClientCommand` → `Spawner` / `Clan`), dois tiles ao lado do jogador;
- cala as falas próprias do Bandits (`SILENCE_BANDITS_SPEECH`), para só a voz do daemon falar;
- traduz os modos da ponte para programas do Bandits:

| Modo da ponte | Programa Bandits | Efeito |
| --- | --- | --- |
| `seguir` | `Companion` | segue o jogador e ataca inimigos próximos |
| `defender` | `Companion` | o mesmo programa; o daemon trata o modo como defesa |
| `ficar` | `CompanionStay` | fica no posto e volta se for empurrado para longe |
| `saquear` | — | o Bandits não looteia no programa Companion; a ponte manda uma busca (`fetch`) |

A busca (`Adapter.fetch`) vasculha contêineres num raio de 25 tiles, por até 90 s, e leva no máximo 8 itens. Palavras-chave vêm do daemon (`petrol`, `cat:Food`, `@util`, e o prefixo `-` para excluir). Se não achar nada, ou se houver perigo ou estourar o tempo, o adapter emite `fetch_fail`.

Veículo: o companheiro não entra no carro de verdade. Perto de um veículo, o adapter guarda o estado dele (`player:getModData().ttsBoard`) e o remove do mundo; ao descer, recria o NPC. Se em 2 minutos ele não embarcar, volta sozinho.

## Contrato do adapter

Toda função recebe o jogador local. O núcleo chama isto:

- `hasNpc(player)` → o companheiro existe (no mundo, embarcado ou sendo recriado);
- `isNpcNearby(player, objs)` → dá para mostrar o menu;
- `npcName(player)` → nome exibido;
- `getState(player)` → tabela com `name`, `mode`, `hp`, `player_hp`, `threats`, `ammo`, `loot_near`;
- `setMode(player, mode)` → `seguir`, `ficar`, `defender` ou `saquear`;
- `say(player, text)` → balão de fala no NPC;
- `fetch(player, keywords, label)` → buscar itens (opcional);
- `pollEvents(player)` → lista `{ evt, payload }` de coisas que aconteceram desde a última leitura (opcional).

Um adapter novo segue esse contrato e termina com `NPC_Bridge.registerAdapter(Adapter)`. O modelo comentado está em `daemon-ia/docs/NPC_AdapterTemplate.lua.txt`. Mantenha `ENABLE_STUB = false` quando houver um adapter real: os dois não devem se registrar juntos.

O stub virtual não move ninguém. A vida do “NPC” fica em 100, as ameaças são zumbis mirando no jogador a até 10 tiles, `kill` sobe com os seus abates e `hurt` com a sua perda de vida. Serve para validar menu, texto e voz.

## Arquivos trocados com o daemon

Os dois ficam em `%USERPROFILE%\Zomboid\Lua\`, ao lado de `TTS_events.txt` do `MeuTTSMod`.

**Lua → daemon** (`NPC_events.txt`), uma linha `evento|payload`:

| Evento | Quando | Payload |
| --- | --- | --- |
| `joined` | o companheiro passou a existir | `name=...` |
| `left` | deixou de existir | vazio |
| `state` | a cada ~5 s, enquanto existe | `name;mode;hp;player_hp;threats;ammo;loot_near` |
| `kill`, `hurt`, `loot`, `no_ammo` | o adapter reporta em `pollEvents` | chave=valor |
| `fetch_fail` | a busca não deu certo | `reason=none`, `danger` ou `timeout` |
| `cmd` | item do menu (Seguir, Ficar, Defender, Buscar) | `seguir`, `ficar`, `defender` ou `saquear` |
| `say` | o jogador escreveu no menu “Falar...” | texto livre |
| `paused` / `resumed` | a velocidade do jogo foi a 0 ou voltou | vazio |

`|`, `;`, `=` e quebras de linha nos valores são removidos antes de gravar.

**Daemon → Lua** (`NPC_commands.txt`), uma linha `seq|tipo|arg|extra`:

| Tipo | Efeito |
| --- | --- |
| `mode` | `setMode` com `seguir`, `ficar`, `defender` ou `saquear` |
| `say` | balão com o texto no instante em que o áudio começa |
| `fetch` | busca; `arg` são as palavras-chave, `extra` é o rótulo falado |

A ponte lê os comandos cerca de 1 vez por segundo. Na primeira leitura ignora o que sobrou de uma sessão anterior e só aplica sequências novas. Se o número de sequência voltar para trás, entende que o daemon reiniciou.

## Menu no jogo

Com o companheiro presente e por perto, o botão direito no mundo abre **Companheiro: &lt;nome&gt;** com:

- Seguir
- Ficar aqui
- Defender
- Buscar itens uteis
- Falar... (caixa de texto; o texto vai como evento `say`)

Esses cliques não mudam o NPC na hora. Eles avisam o daemon, que decide e devolve `mode`, `say` ou `fetch`.

## Pausa

O daemon continua rodando com o jogo pausado. A ponte usa `Events.OnTickEvenPaused` (ou `OnPlayerUpdate`, se esse evento não existir) e emite `paused` / `resumed` quando `getGameSpeed()` vai a 0 ou sai de 0. O daemon segura falas novas do NPC enquanto recebe `paused`.

## Loop

Em `OnPlayerUpdate`, só o jogador local:

- a cada ~1 s, lê `NPC_commands.txt`;
- a cada ~0,5 s, pede `pollEvents` ao adapter;
- a cada ~5 s, emite `joined` / `left` / `state`.

Uma função que lançar erro é desligada e o erro vai ao console com o prefixo `[TTS NPC]`. O carregamento bem-sucedido imprime `[TTS NPC] Ponte do NPC carregada`.

## Instalação

1. Ative o mod Bandits e o **TTS NPC Bridge** num jogo da build 42.
2. Deixe `ENABLE_STUB` em `false` (já é o padrão).
3. Rode o `daemon-ia` (`python tts_daemon.py`) antes ou durante a partida.
4. Entre no mundo. O adapter cria o companheiro se ainda não houver um bandit seu por perto.

No console, o spawn aparece com o prefixo `[NPC BANDITS]`. A voz e as decisões saem no terminal do daemon, com o prefixo `[NPC]`.
