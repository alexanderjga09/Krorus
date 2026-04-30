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

# Configuración de flags para subprocesos (Evita errores en sistemas no-Windows)
CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


class BotSetupApp:
    def __init__(self, page: ft.Page):
        self.page = page
        self.page.title = "Krorus - Discord Bot Dashboard"
        self.page.theme_mode = ft.ThemeMode.DARK

        # Icono de la ventana
        self.page.window.icon = "krorus.ico"

        # Propiedades de ventana
        self.page.window.width = 1100
        self.page.window.height = 750
        self.page.window.min_width = 900
        self.page.window.min_height = 600

        self.page.padding = 20
        self.page.theme = ft.Theme(color_scheme_seed=ft.Colors.BLUE_ACCENT)

        # Variables de estado
        self.running_process = None
        self.process_lock = threading.Lock()
        self._restart_requested = False
        self.is_busy = False

        # Referencias a controles
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
        self.console = ft.ListView(
            expand=True,
            spacing=2,
            auto_scroll=True,
        )

        # Status y Progreso
        self.status_dot = ft.Icon(ft.Icons.CIRCLE, color=ft.Colors.GREY_400, size=12)
        self.status_text = ft.Text("Esperando directorio...", color=ft.Colors.GREY_400)
        self.progress_bar = ft.ProgressBar(visible=False, color=ft.Colors.BLUE_ACCENT)

        # Botones
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
            style=ft.ButtonStyle(
                bgcolor=ft.Colors.GREEN_800,
                color=ft.Colors.WHITE,
            ),
            tooltip="Ejecuta main.py",
        )
        self.stop_btn = ft.Button(
            "Detener",
            icon=ft.Icons.STOP,
            on_click=lambda _: self.stop_bot(),
            disabled=True,
            style=ft.ButtonStyle(
                bgcolor=ft.Colors.RED_800,
                color=ft.Colors.WHITE,
            ),
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

        # Se utiliza Tkinter para la selección de carpetas y evitar el TimeoutException de Flet
        self.page.update()

        self.setup_ui()

    def show_snackbar(self, text, color=ft.Colors.BLUE_ACCENT):
        self.page.snack_bar = ft.SnackBar(
            ft.Text(text),
            bgcolor=color,
            action="Cerrar",
        )
        self.page.snack_bar.open = True
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

                class MockResultEvent:
                    def __init__(self, path):
                        self.path = path

                self.on_folder_selected(MockResultEvent(selected_path))
        except Exception as ex:
            self.log(f"Error al abrir el selector de archivos: {ex}", ft.Colors.RED_400)

    def open_in_explorer(self, _):
        path = self.project_path_text.value
        if not path or not os.path.exists(path):
            return

        if sys.platform == "win32":
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.run(["open", path])
        else:
            subprocess.run(["xdg-open", path])

    def setup_ui(self):
        # --- Construcción del Panel Izquierdo ---

        # 1. Contenedor para los inputs
        self.settings_container = ft.Container(
            content=ft.Column(
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
            ),
        )

        # 2. Contenedor estático para los botones
        self.buttons_container = ft.Column(
            [
                ft.Divider(height=20),
                ft.Row([self.status_dot, self.status_text]),
                self.progress_bar,
                ft.Row(
                    [self.setup_btn, self.start_btn],
                    alignment=ft.MainAxisAlignment.CENTER,
                ),
                ft.Row(
                    [
                        self.stop_btn,
                        self.restart_btn,
                        self.update_btn,
                    ],
                    alignment=ft.MainAxisAlignment.CENTER,
                ),
            ],
            spacing=10,
        )

        # Layout Principal
        self.page.add(
            ft.Row(
                [
                    ft.Image(src="krorus.ico", width=30, height=30)
                    if os.path.exists("krorus.ico")
                    else ft.Icon(
                        ft.Icons.TERMINAL, color=ft.Colors.BLUE_ACCENT, size=30
                    ),
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
                                self.settings_container,
                                ft.Container(expand=True),
                                self.buttons_container,
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

    def on_folder_selected(self, e):
        if e.path:
            self.project_path_text.value = e.path
            self.log(f"📁 Carpeta seleccionada: {e.path}", ft.Colors.BLUE_200)
            self.load_env_file(e.path)
            self.update_states()

    def load_env_file(self, folder_path):
        env_path = Path(folder_path) / ".env"
        if not env_path.exists():
            return
        try:
            content = env_path.read_text(encoding="utf-8")
            patterns = {
                "TOKEN": r'^TOKEN\s*=\s*["\']?(.*?)["\']?$',
                "GROQ_API_KEY": r'^GROQ_API_KEY\s*=\s*["\']?(.*?)["\']?$',
                "VIRUSTOTAL_API_KEY": r'^VIRUSTOTAL_API_KEY\s*=\s*["\']?(.*?)["\']?$',
                "ALLOWED_GUILD_ID": r'^ALLOWED_GUILD_ID\s*=\s*["\']?(.*?)["\']?$',
            }
            for key, pattern in patterns.items():
                match = re.search(pattern, content, re.MULTILINE)
                if match:
                    val = match.group(1).strip()
                    if key == "TOKEN" and not self.token_entry.value:
                        self.token_entry.value = val
                    elif key == "GROQ_API_KEY" and not self.groq_entry.value:
                        self.groq_entry.value = val
                    elif key == "VIRUSTOTAL_API_KEY" and not self.vt_entry.value:
                        self.vt_entry.value = val
                    elif key == "ALLOWED_GUILD_ID" and not self.guild_entry.value:
                        self.guild_entry.value = val
            self.log("🔑 Valores cargados desde .env", ft.Colors.GREEN_200)
        except Exception as e:
            self.log(f"Error al leer .env: {e}", ft.Colors.RED_400)

    def log(self, message, color=ft.Colors.GREY_300):
        timestamp = time.strftime("%H:%M:%S")

        # Limitar cantidad de líneas para mantener rendimiento de la UI
        if len(self.console.controls) > 300:
            self.console.controls.pop(0)

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
                    cwd=cwd,
                    env=env,
                    bufsize=1,
                    creationflags=CREATE_NO_WINDOW,
                )
                with self.process_lock:
                    self.running_process = process

                self.update_states()

                # Leemos línea por línea
                while True:
                    line = process.stdout.readline()
                    if not line and process.poll() is not None:
                        break
                    if line:
                        self.log(line.strip())
                        # Pausa mínima para asegurar que el thread ceda el control y el bridge de Flet
                        # procese los mensajes de actualización de la consola fluidamente.
                        time.sleep(0.01)

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

    def start_setup(self, _):
        if not self.project_path_text.value:
            return
        self.is_busy = True
        self.progress_bar.visible = True
        self.clear_console(None)
        self.log("🚀 Iniciando configuración...", ft.Colors.BLUE_200)
        self.update_states()

        env_path = Path(self.project_path_text.value) / ".env"
        env_content = (
            f'TOKEN="{self.token_entry.value}"\n'
            f'GROQ_API_KEY="{self.groq_entry.value}"\n'
            f'VIRUSTOTAL_API_KEY="{self.vt_entry.value}"\n'
            f'ALLOWED_GUILD_ID="{self.guild_entry.value}"'
        )
        try:
            env_path.write_text(env_content, encoding="utf-8")
            self.log("✅ Archivo .env guardado", ft.Colors.GREEN_200)
        except Exception as e:
            self.log(f"❌ Error al guardar .env: {e}", ft.Colors.RED_400)
            self.is_busy = False
            self.progress_bar.visible = False
            self.update_states()
            return

        python_exe = sys.executable
        venv_dir = Path(self.project_path_text.value) / ".venv"
        self.log("🐍 Creando/Verificando entorno virtual...", ft.Colors.BLUE_200)
        self.run_command(
            [python_exe, "-m", "venv", str(venv_dir)],
            cwd=self.project_path_text.value,
            on_finish=lambda rc: self.after_venv(rc, venv_dir),
        )

    def after_venv(self, rc, venv_dir):
        if rc != 0:
            self.log("❌ Error al crear entorno virtual", ft.Colors.RED_400)
            self.is_busy = False
            self.update_states()
            return

        pip_exe = (
            venv_dir
            / ("Scripts" if sys.platform == "win32" else "bin")
            / ("pip.exe" if sys.platform == "win32" else "pip")
        )

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

        project_dir = Path(self.project_path_text.value)
        venv_path = project_dir / ".venv"
        python_bin = (
            venv_path
            / ("Scripts" if sys.platform == "win32" else "bin")
            / ("python.exe" if sys.platform == "win32" else "python")
        )
        main_file = project_dir / "main.py"

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
        if self._restart_requested:
            self._restart_requested = False
            # Pequeño retardo para asegurar que el proceso anterior se libere
            time.sleep(0.5)
            self.start_bot(None)
        else:
            self.log(f"⏹️ Bot detenido (Código: {rc})", ft.Colors.ORANGE_400)
            self.show_snackbar(f"Bot detenido (RC: {rc})", ft.Colors.ORANGE_800)
        self.update_states()

    def stop_bot(self):
        with self.process_lock:
            if self.running_process:
                self.log("🛑 Solicitando detención...", ft.Colors.ORANGE_400)
                if sys.platform == "win32":
                    subprocess.run(
                        ["taskkill", "/F", "/T", "/PID", str(self.running_process.pid)],
                        capture_output=True,
                        creationflags=CREATE_NO_WINDOW,
                    )
                else:
                    self.running_process.terminate()
        self.update_states()

    def restart_bot(self, _):
        self._restart_requested = True
        self.stop_bot()

    def check_for_updates(self, _):
        self.is_busy = True
        self.update_states()
        self.log(
            "🔍 Buscando actualizaciones en el repositorio Git...", ft.Colors.BLUE_200
        )

        def update():
            try:
                repo_path = self.project_path_text.value
                # Sincronizar
                subprocess.run(
                    ["git", "fetch"],
                    cwd=repo_path,
                    capture_output=True,
                    creationflags=CREATE_NO_WINDOW,
                )

                # Verificar cambios
                res = subprocess.run(
                    ["git", "rev-list", "--count", "HEAD..@{u}"],
                    cwd=repo_path,
                    capture_output=True,
                    text=True,
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
                        creationflags=CREATE_NO_WINDOW,
                    )

                    if pull_res.returncode == 0:
                        self.log(
                            "✅ Código actualizado con éxito.", ft.Colors.GREEN_400
                        )
                        self.show_snackbar(
                            "Proyecto actualizado via Git", ft.Colors.BLUE_800
                        )

                        # Re-instalar dependencias por si cambiaron
                        venv_dir = Path(repo_path) / ".venv"
                        req_file = Path(repo_path) / "requirements.txt"
                        if venv_dir.exists() and req_file.exists():
                            self.log(
                                "📦 Verificando nuevas dependencias...",
                                ft.Colors.BLUE_200,
                            )
                            pip_exe = (
                                venv_dir
                                / ("Scripts" if sys.platform == "win32" else "bin")
                                / ("pip.exe" if sys.platform == "win32" else "pip")
                            )
                            subprocess.run(
                                [str(pip_exe), "install", "-r", str(req_file)],
                                cwd=repo_path,
                                capture_output=True,
                                creationflags=CREATE_NO_WINDOW,
                            )
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
