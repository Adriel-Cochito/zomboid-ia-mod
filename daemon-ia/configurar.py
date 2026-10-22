"""
Janela de configuração do daemon. Não carrega o XTTS.
Na pasta daemon-ia:  python configurar.py
"""
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from src.user_settings import (
    app_dir,
    attach_voice,
    connection_status,
    detach_voice,
    load,
    prepare_runtime_env,
    python_executable,
    save,
    sync_voices,
)


def daemon_command():
    if getattr(sys, "frozen", False):
        return [sys.executable, "--daemon"]
    return [python_executable(), str(app_dir() / "tts_daemon.py")]


class ConfigApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Daemon Zomboid")
        self.root.minsize(520, 560)
        self.data = sync_voices(load())
        self.proc = None
        self._choices = []

        pad = {"padx": 10, "pady": 4}
        frame = ttk.Frame(root, padding=10)
        frame.pack(fill="both", expand=True)

        ttk.Label(frame, text="Biblioteca de vozes").pack(anchor="w")
        self.voices = tk.Listbox(frame, height=6, exportselection=False)
        self.voices.pack(fill="x", **pad)

        name_row = ttk.Frame(frame)
        name_row.pack(fill="x", **pad)
        ttk.Label(name_row, text="Nome").pack(side="left")
        self.name_var = tk.StringVar()
        ttk.Entry(name_row, textvariable=self.name_var).pack(side="left", fill="x", expand=True, padx=8)
        ttk.Button(name_row, text="Anexar áudio", command=self._attach).pack(side="left")
        ttk.Button(name_row, text="Remover", command=self._remove).pack(side="left", padx=(6, 0))

        self.player_var = tk.StringVar()
        self.npc_var = tk.StringVar()
        self._combo(frame, "Personagem principal", self.player_var)
        self._combo(frame, "NPC amigável", self.npc_var)

        talk = ttk.LabelFrame(frame, text="Quantidade de falas", padding=8)
        talk.pack(fill="x", pady=8)
        self.player_talk = tk.StringVar(value=self.data["talk"]["player"])
        self.npc_talk = tk.StringVar(value=self.data["talk"]["npc"])
        self._levels(talk, "Personagem", self.player_talk)
        self._levels(talk, "NPC", self.npc_talk)

        self.npc_on = tk.BooleanVar(value=bool(self.data.get("npc_enabled", True)))
        ttk.Checkbutton(
            frame,
            text="NPC amigável ligado (desmarque se não usa o mod Bandits)",
            variable=self.npc_on,
        ).pack(anchor="w", pady=4)

        status = ttk.LabelFrame(frame, text="Estado", padding=8)
        status.pack(fill="x", pady=8)
        self.lua_label = ttk.Label(status, text="Pasta do Zomboid: …")
        self.tts_label = ttk.Label(status, text="TTS_events.txt: …")
        self.npc_file_label = ttk.Label(status, text="NPC_events.txt: …")
        self.ollama_label = ttk.Label(status, text="Ollama: …")
        self.model_label = ttk.Label(status, text="A primeira execução do daemon baixa o modelo de voz.")
        self.run_label = ttk.Label(status, text="Daemon: parado")
        for label in (
            self.lua_label, self.tts_label, self.npc_file_label,
            self.ollama_label, self.model_label, self.run_label,
        ):
            label.pack(anchor="w")
        ttk.Button(status, text="Atualizar", command=self.refresh_status).pack(anchor="w", pady=(6, 0))

        buttons = ttk.Frame(frame)
        buttons.pack(fill="x", pady=8)
        ttk.Button(buttons, text="Salvar", command=self.save_settings).pack(side="left")
        ttk.Button(buttons, text="Iniciar", command=self.start_daemon).pack(side="left", padx=6)
        ttk.Button(buttons, text="Parar", command=self.stop_daemon).pack(side="left")

        self._fill_voices()
        self.refresh_status()
        self._watch_process()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _combo(self, parent, label, variable):
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=2)
        ttk.Label(row, text=label, width=24).pack(side="left")
        box = ttk.Combobox(row, textvariable=variable, state="readonly")
        box.pack(side="left", fill="x", expand=True)
        if label.startswith("Personagem"):
            self.player_box = box
        else:
            self.npc_box = box

    def _levels(self, parent, label, variable):
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=2)
        ttk.Label(row, text=label, width=16).pack(side="left")
        for value, text in (("baixo", "Baixo"), ("medio", "Médio"), ("alto", "Alto")):
            ttk.Radiobutton(row, text=text, value=value, variable=variable).pack(side="left", padx=6)

    def _labels(self):
        counts = {}
        for voice in self.data["voices"]:
            counts[voice["name"]] = counts.get(voice["name"], 0) + 1
        options = [("Padrão", "")]
        for voice in self.data["voices"]:
            label = voice["name"]
            if counts[voice["name"]] > 1:
                label = f"{voice['name']} ({voice['file']})"
            options.append((label, voice["id"]))
        return options

    def _fill_voices(self):
        self.voices.delete(0, "end")
        for voice in self.data["voices"]:
            self.voices.insert("end", f"{voice['name']}  —  {voice['file']}")
        self._choices = self._labels()
        labels = [label for label, _voice_id in self._choices]
        self.player_box["values"] = labels
        self.npc_box["values"] = labels
        self.player_var.set(self._label_for(self.data["assign"].get("player", "")))
        self.npc_var.set(self._label_for(self.data["assign"].get("npc", "")))

    def _label_for(self, voice_id: str) -> str:
        for label, vid in self._choices:
            if vid == (voice_id or ""):
                return label
        return "Padrão"

    def _id_for(self, label: str) -> str:
        for text, voice_id in self._choices:
            if text == label:
                return voice_id
        return ""

    def _selected_voice_id(self):
        index = self.voices.curselection()
        if not index:
            return None
        voices = self.data["voices"]
        if index[0] >= len(voices):
            return None
        return voices[index[0]]["id"]

    def _attach(self):
        path = filedialog.askopenfilename(
            title="Áudio de referência",
            filetypes=[("Áudio", "*.wav *.mp3 *.flac *.ogg"), ("Todos", "*.*")],
        )
        if not path:
            return
        try:
            attach_voice(self.data, path, self.name_var.get())
        except ValueError as exc:
            messagebox.showerror("Voz", str(exc))
            return
        self.name_var.set("")
        self._fill_voices()

    def _remove(self):
        voice_id = self._selected_voice_id()
        if not voice_id:
            return
        detach_voice(self.data, voice_id)
        self._fill_voices()

    def _collect(self):
        self.data["assign"]["player"] = self._id_for(self.player_var.get())
        self.data["assign"]["npc"] = self._id_for(self.npc_var.get())
        self.data["talk"]["player"] = self.player_talk.get()
        self.data["talk"]["npc"] = self.npc_talk.get()
        self.data["npc_enabled"] = bool(self.npc_on.get())

    def save_settings(self):
        self._collect()
        save(self.data)
        messagebox.showinfo("Daemon Zomboid", "Configuração salva.")

    def _alive(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def start_daemon(self):
        self._collect()
        save(self.data)
        if self._alive():
            return
        try:
            self.proc = subprocess.Popen(daemon_command(), cwd=str(app_dir()))
        except OSError as exc:
            messagebox.showerror("Daemon", str(exc))

    def stop_daemon(self):
        if not self._alive():
            self.proc = None
            return
        self.proc.terminate()
        try:
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.proc.kill()
        self.proc = None

    def _watch_process(self):
        self.run_label.config(text="Daemon: rodando" if self._alive() else "Daemon: parado")
        self.root.after(1000, self._watch_process)

    def refresh_status(self):
        def work():
            report = connection_status()
            self.root.after(0, lambda: self._show_status(report))
        threading.Thread(target=work, daemon=True).start()

    def _show_status(self, report: dict):
        lua = "encontrada" if report["lua_ok"] else "não encontrada"
        self.lua_label.config(text=f"Pasta do Zomboid: {lua} ({report['lua_dir']})")
        self.tts_label.config(text="TTS_events.txt: " + ("encontrado" if report["tts_events"] else "ainda não"))
        self.npc_file_label.config(text="NPC_events.txt: " + ("encontrado" if report["npc_events"] else "ainda não"))
        self.ollama_label.config(text="Ollama: " + ("respondendo" if report["ollama_ok"] else "sem resposta"))

    def _on_close(self):
        self.stop_daemon()
        self.root.destroy()


def main():
    prepare_runtime_env()
    if "--daemon" in sys.argv:
        from tts_daemon import TTSDaemon
        TTSDaemon().run()
        return
    root = tk.Tk()
    ConfigApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
