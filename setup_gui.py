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
        self.process_lock = threading.Lock()

        # Banderas de estado
        self._restart_requested = False
        self.is_busy = False  # Previene doble clics o solapamiento de acciones

        # Escuchar cambios en la ruta del proyecto para habilitar/deshabilitar botones dinámicamente
        self.project_path.trace_add("write", lambda *args: self.update_button_states())

        # Configurar protocolo de cierre
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

        # Configurar grid principal
        self.root.columnconfigure(0, weight=1)  # panel izquierdo
        self.root.columnconfigure(1, weight=2)  # consola
        self.root.rowconfigure(0, weight=1)

        self.create_left_panel()
        self.create_right_panel()
        self.poll_queue()

        # Inicializar estado de los botones al arrancar
        self.update_button_states()

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
        ttk.Entry(path_frame, textvariable=self.project_path, state="readonly").grid(
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
        ttk.Label(left_frame, text="VirusTotal API:").grid(
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
            left_frame, text="● Esperando directorio...", font=("TkDefaultFont", 10)
        )
        self.status_label.grid(row=6, column=0, columnspan=2, pady=(10, 5))
        self.status_label.config(foreground="gray")

        # Botones
        btn_frame = ttk.Frame(left_frame)
        btn_frame.grid(row=7, column=0, columnspan=2, pady=10)

        self.setup_btn = ttk.Button(
            btn_frame, text="⚙️ Configurar", command=self.start_setup, bootstyle=SUCCESS
        )
        self.setup_btn.pack(side="left", padx=3)

        self.start_btn = ttk.Button(
            btn_frame, text="▶️ Iniciar", command=self.start_bot, bootstyle=INFO
        )
        self.start_btn.pack(side="left", padx=3)

        self.stop_btn = ttk.Button(
            btn_frame, text="⏹️ Detener", command=self.stop_bot, bootstyle=DANGER
        )
        self.stop_btn.pack(side="left", padx=3)

        self.restart_btn = ttk.Button(
            btn_frame,
            text="🔄 Reiniciar",
            command=self.restart_bot,
            bootstyle="warning",
        )
        self.restart_btn.pack(side="left", padx=3)

        self.update_btn = ttk.Button(
            btn_frame,
            text="⬇️ Actualizar",
            command=self.check_for_updates,
            bootstyle="secondary",
        )
        self.update_btn.pack(side="left", padx=3)

        # Estados de visibilidad
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

    # --- Gestor de Estados Dinámico ---
    def update_button_states(self):
        """Habilita/deshabilita los botones basándose en el estado actual del bot."""
        has_project = bool(self.project_path.get().strip())
        is_running = self.is_process_running()

        if self.is_busy:
            # Bloquear todo si hay una tarea asíncrona bloqueante ejecutándose (ej. instalando, actualizando, matando proceso)
            self.setup_btn.config(state="disabled")
            self.start_btn.config(state="disabled")
            self.stop_btn.config(state="disabled")
            self.restart_btn.config(state="disabled")
            self.update_btn.config(state="disabled")
            return

        # Configurar y Start requieren que HAYA un proyecto y que NO esté corriendo
        normal_if_ready = "normal" if (has_project and not is_running) else "disabled"
        self.setup_btn.config(state=normal_if_ready)
        self.start_btn.config(state=normal_if_ready)

        # Detener y Reiniciar requieren que el bot SÍ esté corriendo
        normal_if_running = "normal" if is_running else "disabled"
        self.stop_btn.config(state=normal_if_running)
        self.restart_btn.config(state=normal_if_running)

        # Actualizar requiere que haya un proyecto cargado (puede ejecutarse aunque el bot corra o no)
        self.update_btn.config(state="normal" if has_project else "disabled")

        # Etiqueta de estado visual
        if not is_running and not self.is_busy:
            if has_project:
                self.status_label.config(text="● Inactivo (Listo)", foreground="gray")
            else:
                self.status_label.config(
                    text="● Esperando directorio...", foreground="gray"
                )

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
            self.log(f"📁 Carpeta seleccionada: {folder}", "info")
            self.load_env_file(folder)

    def load_env_file(self, folder_path):
        env_path = Path(folder_path) / ".env"
        if not env_path.exists():
            return
        try:
            content = env_path.read_text(encoding="utf-8")

            # Mejorado: Ahora capta valores tanto si tienen comillas como si no las tienen
            patterns = {
                "TOKEN": r'^TOKEN\s*=\s*["\']?(.*?)["\']?$',
                "GROQ_API_KEY": r'^GROQ_API_KEY\s*=\s*["\']?(.*?)["\']?$',
                "VIRUSTOTAL_API_KEY": r'^VIRUSTOTAL_API_KEY\s*=\s*["\']?(.*?)["\']?$',
                "ALLOWED_GUILD_ID": r'^ALLOWED_GUILD_ID\s*=\s*["\']?(.*?)["\']?$',
            }

            updates = 0
            for key, pattern in patterns.items():
                match = re.search(pattern, content, re.MULTILINE)
                if match:
                    val = match.group(1).strip()
                    if key == "TOKEN" and not self.token.get():
                        self.token.set(val)
                        updates += 1
                    elif key == "GROQ_API_KEY" and not self.groq_key.get():
                        self.groq_key.set(val)
                        updates += 1
                    elif key == "VIRUSTOTAL_API_KEY" and not self.vt_key.get():
                        self.vt_key.set(val)
                        updates += 1
                    elif key == "ALLOWED_GUILD_ID" and not self.guild_id.get():
                        self.guild_id.set(val)
                        updates += 1

            if updates > 0:
                self.log("🔑 Valores cargados desde .env existente", "info")
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
                subprocess.run(["pkill", "-P", str(pid)], check=False)
                os.kill(pid, 15)
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
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = subprocess.SW_HIDE
                kwargs["startupinfo"] = startupinfo
                kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
                kwargs["shell"] = False
            else:
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

            if on_finish is not None:
                safe_on_finish = on_finish
                self.root.after(0, lambda rc=return_code: safe_on_finish(rc))

        threading.Thread(target=target, daemon=True).start()

    def poll_queue(self):
        """Recoge los logs de los procesos en segundo plano."""
        try:
            while True:
                msg_type, content = self.process_queue.get_nowait()
                if msg_type == "log":
                    self.log(content)
        except queue.Empty:
            pass
        finally:
            self.root.after(100, self.poll_queue)

    def on_closing(self):
        if self.is_process_running():
            if messagebox.askokcancel(
                "Salir", "Hay un bot en ejecución. ¿Deseas detenerlo y salir?"
            ):
                self.stop_bot(wait=True)
            else:
                return
        self.root.destroy()

    # --- Configuración e Instalación ---
    def start_setup(self):
        if not self.validate_inputs() or self.is_busy:
            return

        self.clear_console()
        self.is_busy = True
        self.update_button_states()
        self.status_label.config(text="● Configurando Entorno...", foreground="orange")
        self.log("🚀 Iniciando configuración...", "info")

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
            self._end_setup_process()
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
            self._end_setup_process()
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
            self._end_setup_process()
            return

        self.log("📦 Instalando dependencias...", "info")
        self.run_command_in_thread(
            [str(pip_exec), "install", "-r", str(req_file)],
            cwd=self.project_path.get(),
            on_finish=lambda code: self.after_deps_installed(code, venv_path),
        )

    def after_deps_installed(self, return_code, venv_path):
        if return_code != 0:
            self.log("❌ Fallo en la instalación de dependencias.", "error")
            self._end_setup_process()
            return

        self.log("✅ Dependencias instaladas.", "success")
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
        self._end_setup_process()

    def _end_setup_process(self):
        """Helper para liberar la interfaz al terminar de configurar."""
        self.is_busy = False
        self.update_button_states()

    # --- Ejecución del bot ---
    def start_bot(self):
        if not self.project_path.get() or self.is_busy:
            return

        if self.is_process_running():
            return

        venv_path = Path(self.project_path.get()) / ".venv"
        python_venv = (
            venv_path
            / ("Scripts" if sys.platform == "win32" else "bin")
            / ("python.exe" if sys.platform == "win32" else "python")
        )

        if not python_venv.exists():
            self.log(
                "⚠️ Entorno virtual no encontrado. Ejecuta primero 'Configurar e Instalar'.",
                "warning",
            )
            return

        self.clear_console()
        self.log("🤖 Ejecutando bot...", "info")
        self.status_label.config(text="● Ejecutando Bot", foreground="green")

        self.run_command_in_thread(
            [str(python_venv), "main.py"],
            cwd=self.project_path.get(),
            on_finish=lambda code: self.after_bot_finished(code),
        )

        # Le damos un pequeño respiro a Tkinter para asegurar que capture el nuevo proceso antes de actualizar botones
        self.root.after(100, self.update_button_states)

    def after_bot_finished(self, return_code):
        self.is_busy = (
            False  # Liberamos interfaz por si venía de un bloqueo de reinicio/detención
        )

        if return_code != 0 and not self._restart_requested:
            self.log("⚠️ El bot se detuvo con errores.", "error")
        elif not self._restart_requested:
            self.log("✅ Bot finalizado.", "success")

        # Flujo de Reinicio Automático
        if self._restart_requested:
            self._restart_requested = False
            self.start_bot()
        else:
            self.update_button_states()

    def stop_bot(self, wait=False):
        if not self.is_process_running() or self.is_busy:
            return

        self.log("🛑 Deteniendo bot...", "warning")
        self.is_busy = True  # Bloqueamos clics múltiples
        self.update_button_states()
        self.status_label.config(text="● Deteniendo...", foreground="orange")

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
                # NOTA: NO llamamos a self.update_button_states() aquí.
                # Dejamos que el hilo en background detecte la muerte del proceso y dispare 'after_bot_finished'

    def restart_bot(self):
        if getattr(self, "is_busy", False) or not self.is_process_running():
            return

        self.log("🔄 Reiniciando bot...", "info")
        self._restart_requested = True
        self.stop_bot()  # Stop bot ya se encarga del manejo de is_busy y killing

    # --- Verificación de actualizaciones (Git) ---
    def check_for_updates(self):
        if not self.project_path.get() or self.is_busy:
            return

        self.log("🔍 Verificando actualizaciones...", "info")
        self.is_busy = True
        self.update_button_states()
        threading.Thread(target=self._check_for_updates_thread, daemon=True).start()

    def _check_for_updates_thread(self):
        try:
            self._do_update_check()
        except FileNotFoundError:
            self.root.after(
                0,
                lambda: self.log(
                    "Git no está instalado o no se encuentra en PATH", "error"
                ),
            )
        except Exception as e:
            error = str(e)
            self.root.after(0, lambda: self.log(f"Error inesperado: {error}", "error"))
        finally:
            self.root.after(0, self._finish_update_check)

    def _finish_update_check(self):
        self.is_busy = False
        self.update_button_states()

    def _do_update_check(self):
        project_dir = self.project_path.get()
        if not (Path(project_dir) / ".git").exists():
            self.root.after(
                0, lambda: self.log("⚠️ No es un repositorio Git", "warning")
            )
            return

        try:
            subprocess.run(
                ["git", "fetch", "origin"],
                cwd=project_dir,
                check=True,
                capture_output=True,
                timeout=30,
            )
        except subprocess.CalledProcessError:
            self.root.after(
                0, lambda: self.log("Error al obtener datos del remoto", "error")
            )
            return

        upstream_branch = None
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "@{u}"],
                cwd=project_dir,
                capture_output=True,
                text=True,
                check=True,
            )
            upstream_branch = result.stdout.strip()
        except subprocess.CalledProcessError:
            try:
                result = subprocess.run(
                    ["git", "remote", "show", "origin"],
                    cwd=project_dir,
                    capture_output=True,
                    text=True,
                    check=True,
                    timeout=10,
                )
                for line in result.stdout.splitlines():
                    if "HEAD branch:" in line:
                        default_branch = line.split("HEAD branch:")[1].strip()
                        upstream_branch = f"origin/{default_branch}"
                        break
            except Exception:
                pass

        if not upstream_branch:
            for branch in ["origin/main", "origin/master"]:
                try:
                    subprocess.run(
                        ["git", "rev-parse", "--verify", branch],
                        cwd=project_dir,
                        capture_output=True,
                        check=True,
                    )
                    upstream_branch = branch
                    break
                except Exception:
                    continue

        if not upstream_branch:
            self.root.after(
                0, lambda: self.log("No se pudo determinar la rama remota", "warning")
            )
            return

        try:
            result = subprocess.run(
                ["git", "rev-list", "--count", f"HEAD..{upstream_branch}"],
                cwd=project_dir,
                capture_output=True,
                text=True,
                check=True,
            )
            ahead_count = int(result.stdout.strip())
        except Exception as e:
            error = str(e)
            self.root.after(
                0, lambda: self.log(f"Error al comparar commits: {error}", "error")
            )
            return

        msg = (
            f"¡Actualizaciones disponibles! ({ahead_count} commits nuevos)"
            if ahead_count > 0
            else "Ya está actualizado"
        )
        tag = "success" if ahead_count > 0 else "info"
        self.root.after(0, lambda: self.log(msg, tag))


if __name__ == "__main__":
    root = ttk.Window(themename="darkly")
    style = ttk.Style()
    style.configure(".", font=("Segoe UI", 10))
    app = BotSetupGUI(root)
    root.mainloop()
