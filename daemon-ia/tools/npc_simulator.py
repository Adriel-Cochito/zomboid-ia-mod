"""
Simulador do lado Lua: escreve eventos em NPC_events.txt e mostra os comandos que o daemon devolve.
Permite testar voz, decisão e conversa SEM o jogo aberto.

Uso (na raiz do projeto, com o daemon rodando em outro terminal):
    python tools/npc_simulator.py state "hp=80;player_hp=90;threats=0;loot_near=0"
    python tools/npc_simulator.py state "hp=80;player_hp=25;threats=2"
    python tools/npc_simulator.py loot "item=Lata de Feijão"
    python tools/npc_simulator.py say "fica aí um pouco"
    python tools/npc_simulator.py cmd defender
    python tools/npc_simulator.py watch
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.npc.npc_config import NPC_EVENTS_FILE, NPC_COMMANDS_FILE  # noqa: E402


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    evt = sys.argv[1]
    if evt == "watch":
        print(f"Observando {NPC_COMMANDS_FILE} (Ctrl+C para sair)")
        seen = set()
        while True:
            try:
                for line in NPC_COMMANDS_FILE.read_text(encoding="utf-8").splitlines():
                    if line and line not in seen:
                        seen.add(line)
                        print(line)
            except FileNotFoundError:
                pass
            time.sleep(0.5)
    payload = sys.argv[2] if len(sys.argv) > 2 else ""
    NPC_EVENTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(NPC_EVENTS_FILE, "a", encoding="utf-8") as f:
        f.write(f"{evt}|{payload}\n")
    print(f"enviado: {evt}|{payload}")


if __name__ == "__main__":
    main()