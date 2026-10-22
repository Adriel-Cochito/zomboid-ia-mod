# MeuTTSMod

Mod de cliente do Project Zomboid (build 42) que observa o jogador local e grava o que acontece num arquivo de texto. A voz, o Ollama e o áudio ficam na aplicação externa `daemon-ia`, que lê esse arquivo.

Identificação no jogo: **TTS Dynamic Voice Mod** (`id=TTSDynamicVoiceMod`).

## O que ele observa

O script `42/media/lua/client/TTS_Event_Tracker.lua` entra em `Events.OnPlayerUpdate`. Só o jogador local é considerado. A checagem roda a cada 10 ticks. Cada verificação está dentro de um `pcall`: se uma API da build falhar, aquela checagem é desligada e o resto continua. A mensagem aparece no console do jogo com o prefixo `[TTS MOD]`.

Cada evento é uma linha acrescentada em `TTS_events.txt`, na pasta Lua do Zomboid (`%USERPROFILE%\Zomboid\Lua\`), no formato:

```
evento|detalhe
```

`|` e quebras de linha no detalhe são trocados por espaço, para a linha continuar legível pelo daemon.

## Eventos

Tempos abaixo são do próprio mod (relógio real, em milissegundos). O daemon aplica um segundo cooldown antes de falar.

| Evento | Quando dispara | Detalhe |
| --- | --- | --- |
| `zombie_back` | Zumbi mirando no jogador, a até 4 tiles, atrás dele, ao ar livre. Mínimo 5 s. | `rua` |
| `zombie_indoor` | O mesmo, dentro de construção. | `casa` |
| `hurt` | Novo arranhão/mordida, ou queda de vida geral de pelo menos 3. Mínimo 3 s. | motivo e quantidade |
| `bleeding` | Alguma parte do corpo sangrando. Mínimo 35 s. | `sangrando` |
| `bleeding_resolved` | O sangramento parou. Mínimo 30 s desde o último aviso. | `estancou` |
| `rain` | A chuva começa com intensidade acima de 0,4. Uma vez por período de chuva. | intensidade |
| `rest` | O personagem começa a descansar ou a dormir. | status do personagem (abaixo) |
| `wake_up` | O personagem levanta do descanso ou acorda. | `acordou` |
| `panic` | Moodle de pânico ≥ 1. Mínimo 25 s. | nível, lugar e zumbis num raio de 6 tiles |
| `exhaustion` | Moodle de endurance ≥ 2. Mínimo 30 s. | nível |
| `soaked` | Moodle de molhado ≥ 3. Mínimo 60 s. | `encharcado` |
| `hunger` | A fome sobe de 0 para ≥ 1. | nível |
| `hunger_resolved` | A fome volta a 0, pelo menos 30 s depois do aviso. | `saciado` |
| `thirst` | Sede ≥ 2. Mínimo 40 s. | nível |
| `boredom` | Tédio ou infelicidade ≥ 2. Mínimo 60 s. | `tedio` |
| `sickness` | Enjoo ≥ 1. Mínimo 45 s. | `enjoo` |
| `nightmare` | Acordou de um sono com pânico ≥ 1. | `pesadelo` |
| `loot_rare` | O inventário cresceu e o item novo é arma, comida, literatura ou drainable. Mínimo 3 s, e 60 s para o mesmo nome. | `Categoria:Nome do item` |
| `combat_clear` | O contador de abates do jogador subiu. Mínimo 3 s. | `limpou_area` |
| `stealth_broken` | Está agachado e um zumbi que o mira está a até 5 tiles. Mínimo 15 s. | `descoberto` |
| `weapon_jammed` | A arma de fogo na mão principal acabou de travar. Mínimo 10 s. | `travou` |
| `ammo_empty` | Essa arma está com 0 munições. Mínimo 15 s. | `sem_municao` |

A primeira leitura do inventário e do contador de abates é só uma linha de base: entrar no jogo não dispara loot nem combate.

`checkVehicle` acompanha se o jogador está num veículo, mas hoje não emite evento.

## Status enviado no descanso

O detalhe de `rest` é o retrato do personagem, usado depois pelo daemon na reflexão do dia:

```
profession=Cozinheiro;days=12;hours=290;Cooking=3;Aiming=2
```

Entram profissão, horas e dias sobrevividos, e o nível de cada perk rastreado que estiver acima de 0 (armas, furtividade, fitness, culinária, medicina, mecânica, eletricidade, agricultura, pesca, alfaiataria e afins). A lista está em `TRACKED_PERKS` no script.

O daemon também aceita o mesmo conteúdo em JSON, mas este mod grava o formato `chave=valor` separado por `;`.

## Instalação

1. Deixe a pasta `MeuTTSMod` entre os mods do Project Zomboid build 42 (a definição do mod está em `42/mod.info`).
2. Ative **TTS Dynamic Voice Mod** e comece um jogo.
3. No console, a linha de sucesso é `[TTS MOD] Mod de Eventos de Voz carregado com sucesso!`.
4. Rode `daemon-ia` (`python tts_daemon.py`) para transformar essas linhas em fala.

O mod sozinho não sintetiza áudio e não fala com o NPC. O companheiro é o `TTS_NPC_Bridge`.
