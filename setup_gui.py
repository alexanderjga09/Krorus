import json
import os
import re
import subprocess
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog

import flet as ft

# Flags para subprocesos (evita ventana de consola en Windows)
CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

# Rutas absolutas para no depender del CWD
_ICON_PATH = Path(__file__).parent / "krorus.ico"
_CONFIG_FILE = Path.home() / ".krorus_gui_config.json"


class BotSetupApp:
    def __init__(self, page: ft.Page):
        self.page = page
        self.page.title = "Krorus - Discord Bot Dashboard"
        self.page.theme_mode = ft.ThemeMode.DARK
        self.page.window.icon = str(_ICON_PATH)
        self.page.window.width = 1100
        self.page.window.height = 750
        self.page.window.min_width = 900
        self.page.window.min_height = 600
        self.page.padding = 20
        self.page.theme = ft.Theme(color_scheme_seed=ft.Colors.BLUE_ACCENT)

        # Estado
        self.running_process = None
        self.process_lock = threading.Lock()
        self._restart_lock = threading.Lock()
        self._restart_requested = False
        self.is_busy = False

        # ── Controles ──────────────────────────────────────────────────────
        self.project_path_text = ft.TextField(
            label="Carpeta del Proyecto",
            read_only=True,
            expand=True,
            border_color=ft.Colors.BLUE_700,
            hint_text="Selecciona la carpeta donde está tu bot...",
        )
        self.token_entry = ft.TextField(
            label="Discord Bot Token",
            password=True,
            can_reveal_password=True,
            prefix_icon=ft.Icons.TOKEN,
        )
        self.groq_entry = ft.TextField(
            label="Groq API Key",
            password=True,
            can_reveal_password=True,
            prefix_icon=ft.Icons.KEY,
        )
        self.vt_entry = ft.TextField(
            label="VirusTotal API Key",
            password=True,
            can_reveal_password=True,
            prefix_icon=ft.Icons.SECURITY,
        )
        self.guild_entry = ft.TextField(
            label="Allowed Guild ID",
            prefix_icon=ft.Icons.GROUPS,
        )

        # Consola
        self.console = ft.ListView(expand=True, spacing=2, auto_scroll=True)

        # Status y Progreso
        self.status_dot = ft.Icon(ft.Icons.CIRCLE, color=ft.Colors.GREY_400, size=12)
        self.status_text = ft.Text("Esperando directorio...", color=ft.Colors.GREY_400)
        self.progress_bar = ft.ProgressBar(visible=False, color=ft.Colors.BLUE_ACCENT)

        # ── Botones ────────────────────────────────────────────────────────
        self.save_btn = ft.Button(
            "Guardar",
            icon=ft.Icons.SAVE,
            on_click=self.save_env,
            disabled=True,
            tooltip="Guarda las credenciales en .env sin reinstalar dependencias",
        )
        self.setup_btn = ft.Button(
            "Configurar",
            icon=ft.Icons.SETTINGS,
            on_click=self.start_setup,
            disabled=True,
            tooltip="Instala el entorno virtual y dependencias",
        )
        self.start_btn = ft.Button(
            "Iniciar",
            icon=ft.Icons.PLAY_ARROW,
            on_click=self.start_bot,
            disabled=True,
            style=ft.ButtonStyle(bgcolor=ft.Colors.GREEN_800, color=ft.Colors.WHITE),
            tooltip="Ejecuta main.py",
        )
        self.stop_btn = ft.Button(
            "Detener",
            icon=ft.Icons.STOP,
            on_click=lambda _: self.stop_bot(),
            disabled=True,
            style=ft.ButtonStyle(bgcolor=ft.Colors.RED_800, color=ft.Colors.WHITE),
            tooltip="Detiene el proceso actual",
        )
        self.restart_btn = ft.IconButton(
            icon=ft.Icons.REFRESH,
            tooltip="Reiniciar Bot",
            on_click=self.restart_bot,
            disabled=True,
        )
        self.update_btn = ft.IconButton(
            icon=ft.Icons.SYSTEM_UPDATE_ALT,
            tooltip="Actualizar Proyecto (Git Pull)",
            on_click=self.check_for_updates,
            disabled=True,
        )

        self.page.update()
        self.setup_ui()
        self._restore_last_path()

    # ── Helpers ────────────────────────────────────────────────────────────

    def _venv_python(self) -> Path:
        """Ruta al ejecutable Python del entorno virtual del proyecto."""
        base = Path(self.project_path_text.value) / ".venv"
        return (
            base
            / ("Scripts" if sys.platform == "win32" else "bin")
            / ("python.exe" if sys.platform == "win32" else "python")
        )

    def _venv_pip(self) -> Path:
        """Ruta al ejecutable pip del entorno virtual del proyecto."""
        base = Path(self.project_path_text.value) / ".venv"
        return (
            base
            / ("Scripts" if sys.platform == "win32" else "bin")
            / ("pip.exe" if sys.platform == "win32" else "pip")
        )

    def _build_env_content(self) -> str:
        """Construye el contenido del archivo .env con los valores actuales."""
        return (
            f'TOKEN="{self.token_entry.value}"\n'
            f'GROQ_API_KEY="{self.groq_entry.value}"\n'
            f'VIRUSTOTAL_API_KEY="{self.vt_entry.value}"\n'
            f'ALLOWED_GUILD_ID="{self.guild_entry.value}"'
        )

    def _validate_fields(self) -> str | None:
        """
        Valida los campos obligatorios.
        Devuelve un mensaje de error si algo es inválido, o None si todo está bien.
        """
        if not (self.token_entry.value or "").strip():
            return "El campo 'Discord Bot Token' es obligatorio."
        guild = (self.guild_entry.value or "").strip()
        if not guild:
            return "El campo 'Allowed Guild ID' es obligatorio."
        if not guild.isdigit():
            return "El 'Allowed Guild ID' debe ser un número entero válido."
        return None

    def _warn_optional_fields(self):
        """Registra advertencias si los campos opcionales pero importantes están vacíos."""
        if not (self.groq_entry.value or "").strip():
            self.log(
                "⚠️  'Groq API Key' está vacía — el análisis de IA no funcionará.",
                ft.Colors.ORANGE_400,
            )
        if not (self.vt_entry.value or "").strip():
            self.log(
                "⚠️  'VirusTotal API Key' está vacía — el análisis de URLs no funcionará.",
                ft.Colors.ORANGE_400,
            )

    def _save_last_path(self, path: str):
        """Persiste la última carpeta seleccionada en el directorio home del usuario."""
        try:
            _CONFIG_FILE.write_text(json.dumps({"last_path": path}), encoding="utf-8")
        except Exception:
            pass  # No crítico

    def _restore_last_path(self):
        """Restaura la última carpeta usada al iniciar la aplicación."""
        try:
            if _CONFIG_FILE.exists():
                data = json.loads(_CONFIG_FILE.read_text(encoding="utf-8"))
                last = data.get("last_path", "")
                if last and Path(last).is_dir():
                    self.project_path_text.value = last
                    self.log(f"📁 Directorio restaurado: {last}", ft.Colors.BLUE_200)
                    self.load_env_file(last)
                    self.update_states()
        except Exception:
            pass  # No crítico

    # ── UI ─────────────────────────────────────────────────────────────────

    def show_snackbar(self, text, color=ft.Colors.BLUE_ACCENT):
        # En Flet 0.84.0+ los SnackBars se muestran con page.show_dialog()
        self.page.show_dialog(ft.SnackBar(content=ft.Text(text), bgcolor=color))
        self.page.update()

    def pick_folder(self, _):
        try:
            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            selected_path = filedialog.askdirectory()
            root.quit()
            root.destroy()
            if selected_path:
                self.on_folder_selected(selected_path)
        except Exception as ex:
            self.log(f"Error al abrir el selector de archivos: {ex}", ft.Colors.RED_400)

    def open_in_explorer(self, _):
        path = self.project_path_text.value
        if not path or not os.path.exists(path):
            return
        if sys.platform == "win32":
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.run(["open", path], check=False)
        else:
            subprocess.run(["xdg-open", path], check=False)

    def setup_ui(self):
        settings_column = ft.Column(
            [
                ft.Row(
                    [
                        self.project_path_text,
                        ft.IconButton(
                            ft.Icons.FOLDER_OPEN,
                            on_click=self.pick_folder,
                            tooltip="Seleccionar carpeta",
                        ),
                        ft.IconButton(
                            ft.Icons.OPEN_IN_NEW,
                            on_click=self.open_in_explorer,
                            tooltip="Abrir en Explorador",
                        ),
                    ]
                ),
                self.token_entry,
                self.groq_entry,
                self.vt_entry,
                self.guild_entry,
            ],
            scroll=ft.ScrollMode.AUTO,
        )

        buttons_column = ft.Column(
            [
                ft.Divider(height=20),
                ft.Row([self.status_dot, self.status_text]),
                self.progress_bar,
                ft.Row(
                    [self.save_btn, self.setup_btn],
                    alignment=ft.MainAxisAlignment.CENTER,
                ),
                ft.Row(
                    [self.start_btn, self.stop_btn],
                    alignment=ft.MainAxisAlignment.CENTER,
                ),
                ft.Row(
                    [self.restart_btn, self.update_btn],
                    alignment=ft.MainAxisAlignment.CENTER,
                ),
            ],
            spacing=10,
        )

        icon_widget = (
            ft.Image(src=str(_ICON_PATH), width=30, height=30)
            if _ICON_PATH.exists()
            else ft.Icon(ft.Icons.TERMINAL, color=ft.Colors.BLUE_ACCENT, size=30)
        )

        self.page.add(
            ft.Row(
                [
                    icon_widget,
                    ft.Text("Krorus GUI", size=24, weight=ft.FontWeight.BOLD),
                ]
            ),
            ft.Divider(height=10, color=ft.Colors.TRANSPARENT),
            ft.Row(
                [
                    # Panel Izquierdo
                    ft.Container(
                        content=ft.Column(
                            [
                                ft.Row(
                                    [
                                        ft.Text(
                                            "Configuración",
                                            size=18,
                                            weight=ft.FontWeight.W_500,
                                            expand=True,
                                        ),
                                    ]
                                ),
                                settings_column,
                                ft.Container(expand=True),
                                buttons_column,
                            ],
                        ),
                        width=380,
                        padding=20,
                        border_radius=10,
                        bgcolor=ft.Colors.SURFACE,
                    ),
                    # Panel Derecho (Consola)
                    ft.Container(
                        content=ft.Column(
                            [
                                ft.Row(
                                    [
                                        ft.Text(
                                            "Consola de Salida",
                                            size=18,
                                            weight=ft.FontWeight.W_500,
                                            expand=True,
                                        ),
                                        ft.IconButton(
                                            ft.Icons.DELETE_SWEEP,
                                            on_click=self.clear_console,
                                            tooltip="Limpiar Consola",
                                        ),
                                    ]
                                ),
                                ft.Container(
                                    content=self.console,
                                    bgcolor=ft.Colors.BLACK,
                                    padding=10,
                                    border_radius=5,
                                    expand=True,
                                    border=ft.Border.all(1, ft.Colors.GREY_800),
                                ),
                            ]
                        ),
                        expand=True,
                    ),
                ],
                expand=True,
            ),
        )

    def on_folder_selected(self, path: str):
        self.project_path_text.value = path
        self.log(f"📁 Carpeta seleccionada: {path}", ft.Colors.BLUE_200)
        self._save_last_path(path)
        self.load_env_file(path)
        self.update_states()

    def load_env_file(self, folder_path):
        env_path = Path(folder_path) / ".env"
        if not env_path.exists():
            return
        try:
            content = env_path.read_text(encoding="utf-8")
            fields = {
                "TOKEN": (r'^TOKEN\s*=\s*["\']?(.*?)["\']?$', self.token_entry),
                "GROQ_API_KEY": (
                    r'^GROQ_API_KEY\s*=\s*["\']?(.*?)["\']?$',
                    self.groq_entry,
                ),
                "VIRUSTOTAL_API_KEY": (
                    r'^VIRUSTOTAL_API_KEY\s*=\s*["\']?(.*?)["\']?$',
                    self.vt_entry,
                ),
                "ALLOWED_GUILD_ID": (
                    r'^ALLOWED_GUILD_ID\s*=\s*["\']?(.*?)["\']?$',
                    self.guild_entry,
                ),
            }
            for _key, (pattern, field) in fields.items():
                match = re.search(pattern, content, re.MULTILINE)
                if match and not field.value:
                    field.value = match.group(1).strip()
            self.log("🔑 Valores cargados desde .env", ft.Colors.GREEN_200)
            self.page.update()
        except Exception as e:
            self.log(f"Error al leer .env: {e}", ft.Colors.RED_400)

    def log(self, message, color=ft.Colors.GREY_300):
        timestamp = time.strftime("%H:%M:%S")
        # Eliminar 50 líneas de golpe cuando se supera el límite (más eficiente que pop(0))
        if len(self.console.controls) > 500:
            del self.console.controls[:50]
        self.console.controls.append(
            ft.Text(
                f"[{timestamp}] {message}",
                color=color,
                font_family="Consolas",
                size=13,
                selectable=True,
            )
        )
        self.console.update()

    def clear_console(self, _):
        self.console.controls.clear()
        self.console.update()

    def update_states(self):
        has_project = bool(self.project_path_text.value)
        is_running = self.is_process_running()

        self.save_btn.disabled = self.is_busy or not has_project
        self.setup_btn.disabled = self.is_busy or is_running or not has_project
        self.start_btn.disabled = self.is_busy or is_running or not has_project
        self.stop_btn.disabled = self.is_busy or not is_running
        self.restart_btn.disabled = self.is_busy or not is_running
        self.update_btn.disabled = self.is_busy or not has_project

        if is_running:
            self.status_dot.color = ft.Colors.GREEN_400
            self.status_text.value = "Bot en ejecución"
            self.status_text.color = ft.Colors.GREEN_400
        elif self.is_busy:
            self.status_dot.color = ft.Colors.ORANGE_400
            self.status_text.value = "Procesando..."
            self.status_text.color = ft.Colors.ORANGE_400
        else:
            self.status_dot.color = ft.Colors.GREY_400
            self.status_text.value = (
                "Listo" if has_project else "Esperando directorio..."
            )
            self.status_text.color = ft.Colors.GREY_400

        self.page.update()

    def is_process_running(self):
        with self.process_lock:
            return (
                self.running_process is not None and self.running_process.poll() is None
            )

    def run_command(self, cmd, cwd=None, on_finish=None):
        def target():
            env = os.environ.copy()
            env["PYTHONUNBUFFERED"] = "1"
            try:
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    cwd=cwd,
                    env=env,
                    bufsize=1,
                    creationflags=CREATE_NO_WINDOW,
                )
                with self.process_lock:
                    self.running_process = process
                self.update_states()

                if process.stdout:
                    for line in process.stdout:
                        line = line.rstrip()
                        if line:
                            self.log(line)
                    process.stdout.close()
                rc = process.wait()
                with self.process_lock:
                    self.running_process = None

                if on_finish:
                    on_finish(rc)
                self.update_states()
            except Exception as e:
                self.log(f"Error de ejecución: {e}", ft.Colors.RED_400)
                self.is_busy = False
                self.update_states()

        threading.Thread(target=target, daemon=True).start()

    # ── Acciones ───────────────────────────────────────────────────────────

    def save_env(self, _):
        """Guarda las credenciales en .env sin reinstalar dependencias."""
        if not self.project_path_text.value:
            return
        err = self._validate_fields()
        if err:
            self.show_snackbar(f"⚠️ {err}", ft.Colors.ORANGE_800)
            return
        self._warn_optional_fields()
        env_path = Path(self.project_path_text.value) / ".env"
        try:
            env_path.write_text(self._build_env_content(), encoding="utf-8")
            self.log("✅ Credenciales guardadas en .env", ft.Colors.GREEN_200)
            self.show_snackbar("Credenciales guardadas", ft.Colors.GREEN_700)
        except Exception as e:
            self.log(f"❌ Error al guardar .env: {e}", ft.Colors.RED_400)

    def start_setup(self, _):
        if not self.project_path_text.value:
            return
        err = self._validate_fields()
        if err:
            self.show_snackbar(f"⚠️ {err}", ft.Colors.ORANGE_800)
            return

        self.is_busy = True
        self.progress_bar.visible = True
        self.clear_console(None)
        self.log("🚀 Iniciando configuración...", ft.Colors.BLUE_200)
        self.update_states()

        self._warn_optional_fields()

        env_path = Path(self.project_path_text.value) / ".env"
        try:
            env_path.write_text(self._build_env_content(), encoding="utf-8")
            self.log("✅ Archivo .env guardado", ft.Colors.GREEN_200)
        except Exception as e:
            self.log(f"❌ Error al guardar .env: {e}", ft.Colors.RED_400)
            self.is_busy = False
            self.progress_bar.visible = False
            self.update_states()
            return

        venv_dir = Path(self.project_path_text.value) / ".venv"
        self.log("🐍 Creando/Verificando entorno virtual...", ft.Colors.BLUE_200)
        self.run_command(
            [sys.executable, "-m", "venv", str(venv_dir)],
            cwd=self.project_path_text.value,
            on_finish=self.after_venv,
        )

    def after_venv(self, rc):
        if rc != 0:
            self.log("❌ Error al crear entorno virtual", ft.Colors.RED_400)
            self.is_busy = False
            self.progress_bar.visible = False
            self.update_states()
            return

        pip_exe = self._venv_pip()
        req_file = Path(self.project_path_text.value) / "requirements.txt"
        if req_file.exists():
            self.log("📦 Instalando dependencias...", ft.Colors.BLUE_200)
            self.run_command(
                [str(pip_exe), "install", "-r", str(req_file)],
                cwd=self.project_path_text.value,
                on_finish=self.after_setup_complete,
            )
        else:
            self.log("⚠️ No se encontró requirements.txt", ft.Colors.ORANGE_400)
            self.after_setup_complete(0)

    def after_setup_complete(self, rc):
        self.is_busy = False
        self.progress_bar.visible = False
        if rc == 0:
            self.log("🎉 Configuración finalizada con éxito!", ft.Colors.GREEN_400)
            self.show_snackbar("Configuración completada", ft.Colors.GREEN_700)
        else:
            self.log("❌ Hubo errores en la instalación", ft.Colors.RED_400)
        self.update_states()

    def start_bot(self, _):
        if self.is_process_running():
            return

        python_bin = self._venv_python()
        main_file = Path(self.project_path_text.value) / "main.py"

        if not main_file.exists():
            self.log(
                "❌ No se encontró main.py en la carpeta seleccionada.",
                ft.Colors.RED_400,
            )
            self.show_snackbar("Error: main.py no encontrado", ft.Colors.RED_800)
            return

        if not python_bin.exists():
            self.log(
                "❌ No se encontró el entorno virtual. Ejecuta 'Configurar' primero.",
                ft.Colors.RED_400,
            )
            return

        self.clear_console(None)
        self.log("🤖 Iniciando bot...", ft.Colors.GREEN_200)
        self.show_snackbar("Bot iniciado", ft.Colors.GREEN_700)
        self.run_command(
            [str(python_bin), "main.py"],
            cwd=self.project_path_text.value,
            on_finish=self.on_bot_exit,
        )

    def on_bot_exit(self, rc):
        with self._restart_lock:
            restart = self._restart_requested
            self._restart_requested = False
        if restart:
            # Pequeño retardo para asegurar que el proceso anterior se libere
            time.sleep(0.5)
            self.start_bot(None)
        else:
            self.log(f"⏹️ Bot detenido (Código: {rc})", ft.Colors.ORANGE_400)
            self.show_snackbar(f"Bot detenido (RC: {rc})", ft.Colors.ORANGE_800)
        self.update_states()

    def stop_bot(self):
        """Detiene el proceso del bot. El subprocess de taskkill se ejecuta fuera del lock."""
        pid = None
        with self.process_lock:
            if self.running_process:
                self.log("🛑 Solicitando detención...", ft.Colors.ORANGE_400)
                pid = self.running_process.pid
                if sys.platform != "win32":
                    self.running_process.terminate()

        # Ejecutar taskkill fuera del lock para no bloquearlo
        if pid and sys.platform == "win32":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                capture_output=True,
                creationflags=CREATE_NO_WINDOW,
            )
        self.update_states()

    def restart_bot(self, _):
        with self._restart_lock:
            self._restart_requested = True
        self.stop_bot()

    def check_for_updates(self, _):
        self.is_busy = True
        self.update_states()
        self.log(
            "🔍 Buscando actualizaciones en el repositorio Git...", ft.Colors.BLUE_200
        )

        def update():
            repo_path = self.project_path_text.value
            try:
                subprocess.run(
                    ["git", "fetch"],
                    cwd=repo_path,
                    capture_output=True,
                    creationflags=CREATE_NO_WINDOW,
                )

                res = subprocess.run(
                    ["git", "rev-list", "--count", "HEAD..@{u}"],
                    cwd=repo_path,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    creationflags=CREATE_NO_WINDOW,
                )
                count = int(res.stdout.strip() or 0)

                if count > 0:
                    self.log(
                        f"💡 ¡Hay {count} actualizaciones disponibles!",
                        ft.Colors.GREEN_400,
                    )
                    pull_res = subprocess.run(
                        ["git", "pull"],
                        cwd=repo_path,
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        creationflags=CREATE_NO_WINDOW,
                    )
                    if pull_res.returncode == 0:
                        self.log(
                            "✅ Código actualizado con éxito.", ft.Colors.GREEN_400
                        )
                        self.show_snackbar(
                            "Proyecto actualizado via Git", ft.Colors.BLUE_800
                        )

                        pip_exe = self._venv_pip()
                        req_file = Path(repo_path) / "requirements.txt"
                        if pip_exe.exists() and req_file.exists():
                            self.log(
                                "📦 Verificando nuevas dependencias...",
                                ft.Colors.BLUE_200,
                            )
                            proc = subprocess.Popen(
                                [str(pip_exe), "install", "-r", str(req_file)],
                                stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT,
                                text=True,
                                encoding="utf-8",
                                errors="replace",
                                cwd=repo_path,
                                creationflags=CREATE_NO_WINDOW,
                            )
                            if proc.stdout:
                                for line in proc.stdout:
                                    line = line.rstrip()
                                    if line:
                                        self.log(line)
                                proc.stdout.close()
                            proc.wait()
                            self.log("✅ Dependencias al día.", ft.Colors.GREEN_200)
                    else:
                        self.log(
                            f"❌ Error al hacer pull: {pull_res.stderr}",
                            ft.Colors.RED_400,
                        )
                else:
                    self.log("✅ El repositorio está al día.", ft.Colors.BLUE_200)
                    self.show_snackbar("No hay actualizaciones disponibles")
            except Exception as e:
                self.log(f"⚠️ Error durante la actualización: {e}", ft.Colors.ORANGE_400)
            finally:
                self.is_busy = False
                self.update_states()

        threading.Thread(target=update, daemon=True).start()


def main(page: ft.Page):
    BotSetupApp(page)


if __name__ == "__main__":
    ft.run(main)
