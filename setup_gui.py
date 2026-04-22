import os
import queue
import re
import subprocess
import sys
import threading
from pathlib import Path
from tkinter import filedialog, messagebox

import ttkbootstrap as ttk
from ttkbootstrap.constants import DANGER, INFO, SUCCESS
from ttkbootstrap.scrolled import ScrolledText


class BotSetupGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Configurador de Bot de Discord")
        self.root.geometry("1000x650")
        self.root.minsize(800, 500)

        # Variables de control
        self.project_path = ttk.StringVar()
        self.token = ttk.StringVar()
        self.groq_key = ttk.StringVar()
        self.vt_key = ttk.StringVar()
        self.guild_id = ttk.StringVar()

        self.process_queue = queue.Queue()
        self.running_process = None
        self.process_lock = threading.Lock()  # Para evitar condiciones de carrera

        # Configurar protocolo de cierre
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

        # Configurar grid principal
        self.root.columnconfigure(0, weight=1)  # panel izquierdo
        self.root.columnconfigure(1, weight=2)  # consola
        self.root.rowconfigure(0, weight=1)

        self.create_left_panel()
        self.create_right_panel()
        self.poll_queue()

    def create_left_panel(self):
        """Panel izquierdo con configuración."""
        left_frame = ttk.Frame(self.root, padding=10, relief="ridge")
        left_frame.grid(row=0, column=0, sticky="nsew")
        left_frame.columnconfigure(1, weight=1)

        # Título
        ttk.Label(
            left_frame, text="Configuración del Bot", font=("TkDefaultFont", 11, "bold")
        ).grid(row=0, column=0, columnspan=2, pady=(0, 15))

        # Carpeta
        ttk.Label(left_frame, text="Carpeta:").grid(row=1, column=0, sticky="w", pady=5)
        path_frame = ttk.Frame(left_frame)
        path_frame.grid(row=1, column=1, sticky="ew", pady=5)
        path_frame.columnconfigure(0, weight=1)
        ttk.Entry(path_frame, textvariable=self.project_path).grid(
            row=0, column=0, sticky="ew"
        )
        ttk.Button(path_frame, text="Examinar...", command=self.browse_folder).grid(
            row=0, column=1, padx=(5, 0)
        )

        # Token Discord
        ttk.Label(left_frame, text="Token Discord:").grid(
            row=2, column=0, sticky="w", pady=5
        )
        token_frame = ttk.Frame(left_frame)
        token_frame.grid(row=2, column=1, sticky="ew", pady=5)
        token_frame.columnconfigure(0, weight=1)
        self.token_entry = ttk.Entry(token_frame, textvariable=self.token, show="*")
        self.token_entry.grid(row=0, column=0, sticky="ew")
        self.show_token_btn = ttk.Button(
            token_frame, text="👁", width=3, command=self.toggle_token_visibility
        )
        self.show_token_btn.grid(row=0, column=1, padx=(5, 0))

        # Groq API Key
        ttk.Label(left_frame, text="Groq API Key:").grid(
            row=3, column=0, sticky="w", pady=5
        )
        groq_frame = ttk.Frame(left_frame)
        groq_frame.grid(row=3, column=1, sticky="ew", pady=5)
        groq_frame.columnconfigure(0, weight=1)
        self.groq_entry = ttk.Entry(groq_frame, textvariable=self.groq_key, show="*")
        self.groq_entry.grid(row=0, column=0, sticky="ew")
        self.show_groq_btn = ttk.Button(
            groq_frame, text="👁", width=3, command=self.toggle_groq_visibility
        )
        self.show_groq_btn.grid(row=0, column=1, padx=(5, 0))

        # VirusTotal API Key
        ttk.Label(left_frame, text="VirusTotal API Key:").grid(
            row=4, column=0, sticky="w", pady=5
        )
        vt_frame = ttk.Frame(left_frame)
        vt_frame.grid(row=4, column=1, sticky="ew", pady=5)
        vt_frame.columnconfigure(0, weight=1)
        self.vt_entry = ttk.Entry(vt_frame, textvariable=self.vt_key, show="*")
        self.vt_entry.grid(row=0, column=0, sticky="ew")
        self.show_vt_btn = ttk.Button(
            vt_frame, text="👁", width=3, command=self.toggle_vt_visibility
        )
        self.show_vt_btn.grid(row=0, column=1, padx=(5, 0))

        # Guild ID
        ttk.Label(left_frame, text="Allowed Guild ID:").grid(
            row=5, column=0, sticky="w", pady=5
        )
        ttk.Entry(left_frame, textvariable=self.guild_id).grid(
            row=5, column=1, sticky="ew", pady=5
        )

        # Estado de ejecución
        self.status_label = ttk.Label(
            left_frame, text="● Inactivo", font=("TkDefaultFont", 10)
        )
        self.status_label.grid(row=6, column=0, columnspan=2, pady=(10, 5))
        self.status_label.config(foreground="gray")

        # Botones
        btn_frame = ttk.Frame(left_frame)
        btn_frame.grid(row=7, column=0, columnspan=2, pady=10)
        self.setup_btn = ttk.Button(
            btn_frame,
            text="⚙️ Configurar e Instalar",
            command=self.start_setup,
            bootstyle=SUCCESS,
        )
        self.setup_btn.pack(side="left", padx=5)
        self.start_btn = ttk.Button(
            btn_frame, text="▶️ Ejecutar Bot", command=self.start_bot, bootstyle=INFO
        )
        self.start_btn.pack(side="left", padx=5)
        self.stop_btn = ttk.Button(
            btn_frame,
            text="⏹️ Detener",
            command=self.stop_bot,
            bootstyle=DANGER,
            state="disabled",
        )
        self.stop_btn.pack(side="left", padx=5)

        # Estado de visibilidad
        self.token_visible = False
        self.groq_visible = False
        self.vt_visible = False

        left_frame.rowconfigure(8, weight=1)  # Espacio flexible

    def create_right_panel(self):
        """Panel derecho: consola con ScrolledText de ttkbootstrap."""
        right_frame = ttk.Frame(self.root, padding=10)
        right_frame.grid(row=0, column=1, sticky="nsew")
        right_frame.columnconfigure(0, weight=1)
        right_frame.rowconfigure(1, weight=1)

        ttk.Label(
            right_frame, text="Consola de salida", font=("TkDefaultFont", 10, "bold")
        ).grid(row=0, column=0, sticky="w", pady=(0, 5))

        # Usamos ScrolledText de ttkbootstrap para estilo consistente
        self.console = ScrolledText(
            right_frame,
            wrap="word",
            bg="#1e1e1e",
            fg="#d4d4d4",
            insertbackground="white",
            font=("Consolas", 10),
            autohide=True,
        )
        self.console.grid(row=1, column=0, sticky="nsew")

        # Tags para colores en el texto
        self.console.tag_config("error", foreground="#f44747")
        self.console.tag_config("success", foreground="#6a9955")
        self.console.tag_config("info", foreground="#4ec9b0")
        self.console.tag_config("warning", foreground="#dcdcaa")

    # --- Métodos de visibilidad ---
    def toggle_token_visibility(self):
        self.token_visible = not self.token_visible
        self.token_entry.config(show="" if self.token_visible else "*")
        self.show_token_btn.config(text="🔒" if self.token_visible else "👁")

    def toggle_groq_visibility(self):
        self.groq_visible = not self.groq_visible
        self.groq_entry.config(show="" if self.groq_visible else "*")
        self.show_groq_btn.config(text="🔒" if self.groq_visible else "👁")

    def toggle_vt_visibility(self):
        self.vt_visible = not self.vt_visible
        self.vt_entry.config(show="" if self.vt_visible else "*")
        self.show_vt_btn.config(text="🔒" if self.vt_visible else "👁")

    # --- Lógica de archivo .env ---
    def browse_folder(self):
        folder = filedialog.askdirectory(title="Selecciona la carpeta del proyecto")
        if folder:
            self.project_path.set(folder)
            self.log(f"Carpeta seleccionada: {folder}", "info")
            self.load_env_file(folder)

    def load_env_file(self, folder_path):
        env_path = Path(folder_path) / ".env"
        if not env_path.exists():
            return
        try:
            content = env_path.read_text(encoding="utf-8")
            patterns = {
                "TOKEN": r'TOKEN\s*=\s*["\']([^"\']*)["\']',
                "GROQ_API_KEY": r'GROQ_API_KEY\s*=\s*["\']([^"\']*)["\']',
                "VIRUSTOTAL_API_KEY": r'VIRUSTOTAL_API_KEY\s*=\s*["\']([^"\']*)["\']',
                "ALLOWED_GUILD_ID": r'ALLOWED_GUILD_ID\s*=\s*["\']([^"\']*)["\']',
            }
            if not self.token.get():
                match = re.search(patterns["TOKEN"], content)
                if match:
                    self.token.set(match.group(1))
            if not self.groq_key.get():
                match = re.search(patterns["GROQ_API_KEY"], content)
                if match:
                    self.groq_key.set(match.group(1))
            if not self.vt_key.get():
                match = re.search(patterns["VIRUSTOTAL_API_KEY"], content)
                if match:
                    self.vt_key.set(match.group(1))
            if not self.guild_id.get():
                match = re.search(patterns["ALLOWED_GUILD_ID"], content)
                if match:
                    self.guild_id.set(match.group(1))
            self.log("📁 Valores cargados desde .env existente", "info")
        except Exception as e:
            self.log(f"Error al leer .env: {e}", "error")

    # --- Logging ---
    def log(self, message, tag=None):
        self.console.insert("end", message + "\n", tag)
        self.console.see("end")
        self.root.update_idletasks()

    def clear_console(self):
        self.console.delete(1.0, "end")

    # --- Validación ---
    def validate_inputs(self):
        if not self.project_path.get():
            messagebox.showerror("Error", "Selecciona la carpeta del proyecto.")
            return False
        if not self.token.get():
            messagebox.showerror("Error", "El Token del bot es obligatorio.")
            return False
        if not self.guild_id.get():
            messagebox.showerror("Error", "El Allowed Guild ID es obligatorio.")
            return False
        return True

    # --- Manejo de procesos ---
    def kill_process_tree(self, pid):
        """Mata el proceso y todos sus hijos de forma recursiva."""
        if pid is None:
            return
        try:
            if sys.platform == "win32":
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(pid)],
                    capture_output=True,
                    check=False,
                )
            else:
                # En sistemas Unix, usar pkill con el PGID
                subprocess.run(["pkill", "-P", str(pid)], check=False)
                os.kill(pid, 15)  # SIGTERM
        except Exception as e:
            self.log(f"Error al matar proceso: {e}", "error")

    def is_process_running(self):
        """Devuelve True si hay un proceso en ejecución."""
        with self.process_lock:
            return (
                self.running_process is not None and self.running_process.poll() is None
            )

    def run_command_in_thread(self, cmd, cwd=None, env=None, on_finish=None):
        def target():
            process_env = os.environ.copy()
            process_env["PYTHONUNBUFFERED"] = "1"
            if env:
                process_env.update(env)

            kwargs = {
                "stdout": subprocess.PIPE,
                "stderr": subprocess.STDOUT,
                "text": True,
                "cwd": cwd,
                "env": process_env,
                "bufsize": 1,
                "universal_newlines": True,
            }

            if sys.platform == "win32":
                # Ocultar ventana de consola en Windows
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = subprocess.SW_HIDE
                kwargs["startupinfo"] = startupinfo
                kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
                # Usar shell=False es más seguro, pero si se requiere shell por rutas con espacios
                # se puede usar shell=True manteniendo los flags de ocultamiento.
                kwargs["shell"] = False
            else:
                # En Unix, crear nueva sesión para poder matar el grupo de procesos
                kwargs["preexec_fn"] = os.setsid

            process = subprocess.Popen(cmd, **kwargs)
            with self.process_lock:
                self.running_process = process

            for line in iter(process.stdout.readline, ""):
                self.process_queue.put(("log", line.strip()))
            process.stdout.close()
            return_code = process.wait()

            with self.process_lock:
                self.running_process = None
            self.process_queue.put(("finish", return_code))

            if on_finish is not None:
                cb = on_finish
                self.root.after(0, lambda rc=return_code: cb(rc))

        threading.Thread(target=target, daemon=True).start()

    def poll_queue(self):
        try:
            while True:
                msg_type, content = self.process_queue.get_nowait()
                if msg_type == "log":
                    self.log(content)
                elif msg_type == "finish":
                    # El proceso terminó, actualizar UI
                    self.root.after(0, self.update_ui_after_process)
        except queue.Empty:
            pass
        finally:
            self.root.after(100, self.poll_queue)

    def update_ui_after_process(self):
        """Actualiza la interfaz después de que termine el proceso."""
        if not self.is_process_running():
            self.status_label.config(text="● Inactivo", foreground="gray")
            self.stop_btn.config(state="disabled")
            self.start_btn.config(state="normal")
            self.setup_btn.config(state="normal")

    def on_closing(self):
        """Maneja el cierre de la ventana."""
        if self.is_process_running():
            if messagebox.askokcancel(
                "Salir",
                "Hay un bot en ejecución. ¿Deseas detenerlo y salir?",
            ):
                self.stop_bot(wait=True)
            else:
                return
        self.root.destroy()

    # --- Configuración ---
    def start_setup(self):
        if not self.validate_inputs():
            return
        self.clear_console()
        self.log("🚀 Iniciando configuración...", "info")
        self.set_buttons_state("disabled", except_stop=False)

        env_path = Path(self.project_path.get()) / ".env"
        env_content = "\n".join(
            [
                f'TOKEN="{self.token.get()}"',
                f'GROQ_API_KEY="{self.groq_key.get() or ""}"',
                f'VIRUSTOTAL_API_KEY="{self.vt_key.get() or ""}"',
                f'ALLOWED_GUILD_ID="{self.guild_id.get()}"',
            ]
        )
        try:
            env_path.write_text(env_content, encoding="utf-8")
            self.log("✅ Archivo .env creado/actualizado", "success")
        except Exception as e:
            self.log(f"❌ Error al crear .env: {e}", "error")
            self.set_buttons_state("normal")
            return

        venv_path = Path(self.project_path.get()) / ".venv"
        python_exe = sys.executable
        self.log("🐍 Creando entorno virtual...", "info")
        self.run_command_in_thread(
            [python_exe, "-m", "venv", str(venv_path)],
            cwd=self.project_path.get(),
            on_finish=lambda code: self.after_venv_created(code, venv_path),
        )

    def after_venv_created(self, return_code, venv_path):
        if return_code != 0:
            self.log("❌ Fallo al crear el entorno virtual.", "error")
            self.set_buttons_state("normal")
            return
        self.log("✅ Entorno virtual creado.", "success")

        if sys.platform == "win32":
            pip_exec = venv_path / "Scripts" / "pip.exe"
        else:
            pip_exec = venv_path / "bin" / "pip"

        req_file = Path(self.project_path.get()) / "requirements.txt"
        if not req_file.exists():
            self.log(
                "⚠️ No se encontró requirements.txt, se omite instalación.", "warning"
            )
            self.log("🎉 ¡Configuración completada con éxito!", "success")
            self.set_buttons_state("normal")
            return

        self.log("📦 Instalando dependencias...", "info")
        self.run_command_in_thread(
            [str(pip_exec), "install", "-r", str(req_file)],
            cwd=self.project_path.get(),
            on_finish=lambda code: self.after_deps_installed(code),
        )

    def after_deps_installed(self, return_code):
        if return_code != 0:
            self.log("❌ Fallo en la instalación de dependencias.", "error")
            self.set_buttons_state("normal")
            return

        self.log("✅ Dependencias instaladas.", "success")

        # Verificar importación de módulos críticos
        venv_path = Path(self.project_path.get()) / ".venv"
        python_exe = (
            venv_path / ("Scripts" if sys.platform == "win32" else "bin") / "python.exe"
        )
        try:
            subprocess.run(
                [str(python_exe), "-c", "import aiohttp, discord, groq"],
                check=True,
                capture_output=True,
                text=True,
                cwd=self.project_path.get(),
            )
            self.log("✅ Módulos verificados correctamente.", "success")
        except subprocess.CalledProcessError:
            self.log("⚠️ Fallo al importar módulos. Reinstalando aiohttp...", "warning")
            pip_exec = (
                venv_path
                / ("Scripts" if sys.platform == "win32" else "bin")
                / "pip.exe"
            )
            subprocess.run(
                [str(pip_exec), "uninstall", "aiohttp", "yarl", "multidict", "-y"],
                check=False,
            )
            subprocess.run(
                [
                    str(pip_exec),
                    "install",
                    "aiohttp==3.13.5",
                    "--force-reinstall",
                    "--no-cache-dir",
                ],
                check=True,
            )
            self.log("✅ aiohttp reinstalado correctamente.", "success")

        self.log("🎉 ¡Configuración completada con éxito!", "success")
        self.set_buttons_state("normal")

    # --- Ejecución del bot ---
    def start_bot(self):
        if not self.project_path.get():
            messagebox.showerror("Error", "No se ha seleccionado carpeta del proyecto.")
            return

        # Verificar si ya hay un proceso corriendo
        if self.is_process_running():
            response = messagebox.askyesno(
                "Bot en ejecución",
                "Ya hay un bot ejecutándose. ¿Deseas detenerlo y ejecutar uno nuevo?",
            )
            if response:
                self.stop_bot(wait=True)
            else:
                return

        venv_path = Path(self.project_path.get()) / ".venv"
        if sys.platform == "win32":
            python_venv = venv_path / "Scripts" / "python.exe"
        else:
            python_venv = venv_path / "bin" / "python"
        if not python_venv.exists():
            messagebox.showerror(
                "Error",
                "Entorno virtual no encontrado. Ejecuta primero 'Configurar e Instalar'.",
            )
            return

        self.clear_console()
        self.log("🤖 Ejecutando bot...", "info")
        self.status_label.config(text="● Ejecutando", foreground="green")
        self.set_buttons_state("disabled", except_stop=True)

        self.run_command_in_thread(
            [str(python_venv), "main.py"],
            cwd=self.project_path.get(),
            on_finish=lambda code: self.after_bot_finished(code),
        )

    def after_bot_finished(self, return_code):
        if return_code != 0:
            self.log("⚠️ El bot se detuvo con errores.", "error")
        else:
            self.log("✅ Bot finalizado correctamente.", "success")
        self.update_ui_after_process()

    def stop_bot(self, wait=False):
        """Detiene el bot y todos sus procesos hijos.
        Si wait=True, espera hasta que el proceso termine (para cierre de app)."""
        if not self.is_process_running():
            self.log("No hay ningún bot en ejecución.", "info")
            self.update_ui_after_process()
            return

        self.log("🛑 Deteniendo bot...", "warning")
        with self.process_lock:
            if self.running_process:
                pid = self.running_process.pid
                self.kill_process_tree(pid)
                if wait:
                    try:
                        self.running_process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        self.running_process.kill()
                        self.running_process.wait()
                self.running_process = None

        self.log("✅ Bot detenido.", "success")
        self.update_ui_after_process()

    def set_buttons_state(self, state, except_stop=False):
        """Habilita/deshabilita botones principales."""
        if except_stop:
            self.setup_btn.config(state="disabled")
            self.start_btn.config(state="disabled")
            self.stop_btn.config(state="normal")
        else:
            for btn in [self.setup_btn, self.start_btn, self.stop_btn]:
                btn.config(state=state)
            if self.is_process_running():
                self.stop_btn.config(state="normal")
                self.start_btn.config(state="disabled")
                self.setup_btn.config(state="disabled")
            else:
                self.stop_btn.config(state="disabled")


if __name__ == "__main__":
    root = ttk.Window(themename="darkly")

    # Fuente global
    style = ttk.Style()
    default_font = ("Segoe UI", 10)
    style.configure(".", font=default_font)

    app = BotSetupGUI(root)
    root.mainloop()
