import atexit
import collections
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
from typing import Any

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
        self._config_changed = False

        # Cola thread-safe para mensajes de consola
        self._log_queue: collections.deque = collections.deque()

        # Lock exclusivo para page.update() — evita race conditions entre threads
        self._update_lock = threading.Lock()

        # ── Controles ──────────────────────────────────────────────────────
        self.project_path_text = ft.TextField(
            label="Carpeta del Proyecto",
            read_only=True,
            expand=True,
            border_color=ft.Colors.BLUE_700,
            hint_text="Selecciona la carpeta donde esta tu bot...",
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

        # Badge numerico discreto para indicar commits pendientes
        self.update_badge = ft.Container(
            content=ft.Text(
                "", size=12, weight=ft.FontWeight.W_600, color=ft.Colors.WHITE
            ),
            padding=6,
            bgcolor=ft.Colors.ORANGE_600,
            border_radius=6,
            visible=False,
        )

        # Switches de funciones (se crearan en setup_ui)
        self.switch_log_multimedia = None
        self.switch_transcribe_audio = None
        self.switch_log_message_edits = None
        self.switch_enable_whisper = None
        self.switch_monitor_voice = None
        self.switch_detailed_logging = None
        self.switch_check_exif = None

        # Cache de Groq
        self.cache_hits_text = ft.Text("—", size=13)
        self.cache_misses_text = ft.Text("—", size=13)
        self.cache_size_text = ft.Text("—", size=13)
        self.refresh_cache_btn = ft.Button("Refrescar", icon=ft.Icons.REFRESH, on_click=self._refresh_cache_stats)
        self.clear_cache_btn = ft.Button("Limpiar", icon=ft.Icons.DELETE, on_click=self._clear_cache, disabled=True)

        # Theme toggle
        self.theme_switch = ft.Switch(label="Modo claro", value=False, on_change=self._toggle_theme)

        # Bot status
        self.bot_uptime_text = ft.Text("—", size=13)
        self.bot_pid_text = ft.Text("—", size=13)
        self.bot_status_refresh_btn = ft.IconButton(icon=ft.Icons.REFRESH, tooltip="Actualizar", on_click=self._refresh_bot_status)

        # Save logs
        self.save_logs_btn = ft.IconButton(ft.Icons.SAVE, tooltip="Guardar logs", on_click=self._save_logs)

        # Version indicator
        self.version_text = ft.Text("—", size=12, color=ft.Colors.GREY, selectable=True)

        # Restore backup
        self.restore_backup_btn = ft.Button("Restaurar respaldo", icon=ft.Icons.RESTORE, on_click=self._restore_backup, disabled=True)

        # Bot start time tracking
        self._bot_start_time = None

        self.setup_ui()
        self._restore_last_path()
        self.version_text.value = self._get_git_hash()
        # Limpiar procesos zombie del bot antes de cualquier cosa
        self._cleanup_zombies()
        # Mata el proceso hijo si se cierra la ventana
        atexit.register(self._cleanup_process_ref)
        # Verificacion silenciosa de actualizaciones al abrir la GUI
        try:
            threading.Thread(target=self._startup_update_check, daemon=True).start()
        except Exception:
            pass

    def _cleanup_zombies(self):
        """Busca y mata procesos zombie del bot al iniciar la GUI."""

        def do_cleanup():
            killed_pids = self._kill_existing_bot_processes()
            if killed_pids:
                self.log(
                    f"🧹 Se cerraron {len(killed_pids)} instancia(s) zombie del bot: {', '.join(str(p) for p in killed_pids)}.",
                    ft.Colors.ORANGE_400,
                )
            else:
                self.log("✅ No hay instancias zombie del bot.", ft.Colors.GREEN_400)

        self._run_on_thread(do_cleanup)

    def _run_on_thread(self, func):
        """Ejecuta una funcion en un thread separado."""
        threading.Thread(target=func, daemon=True).start()

    def _build_tabs(
        self, labels: list[tuple[str, Any]], views: list[ft.Control]
    ) -> ft.Control:
        """Construye pestañas probando la API de Flet disponible."""
        tabs = [ft.Tab(label=label, icon=icon) for label, icon in labels]
        try:
            return ft.Tabs(
                selected_index=0,
                animation_duration=300,
                tabs=tabs,
                controls=views,
                expand=True,
            )
        except Exception:
            pass
        try:
            return ft.Tabs(
                selected_index=0,
                animation_duration=300,
                tabs=tabs,
                views=views,
                expand=True,
            )
        except Exception:
            pass
        # Fallback: botones manuales
        self._tab_views = views
        self._selected_tab = 0

        def make_on_click(i):
            def _on(e):
                self._selected_tab = i
                self.tab_view_container.content = self._tab_views[i]
                self._safe_update()

            return _on

        buttons = [
            ft.ElevatedButton(label, icon=icon, on_click=make_on_click(i))
            for i, (label, icon) in enumerate(labels)
        ]
        self.tab_view_container = ft.Container(content=views[0], expand=True)
        return ft.Column([ft.Row(buttons), self.tab_view_container], expand=True)

    # ── Thread-safe UI update ─────────────────────────────────────────────

    def _safe_update(self):
        """Llama a page.update() en el hilo principal de Flet."""
        def _do():
            with self._update_lock:
                try:
                    self.page.update()
                except Exception:
                    pass
        try:
            self.page.run_thread(_do)
        except Exception:
            _do()

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

    def _escape_env_val(self, val: str | None) -> str:
        if val is None:
            return ""
        v = str(val).strip()
        v = v.replace("\\", "\\\\").replace('"', '\\"')
        return v

    def _build_env_content(self) -> str:
        """Construye el contenido del archivo .env con los valores actuales."""
        return (
            f'TOKEN="{self._escape_env_val(self.token_entry.value)}"\n'
            f'GROQ_API_KEY="{self._escape_env_val(self.groq_entry.value)}"\n'
            f'VIRUSTOTAL_API_KEY="{self._escape_env_val(self.vt_entry.value)}"\n'
            f'ALLOWED_GUILD_ID="{self._escape_env_val(self.guild_entry.value)}"'
        )

    def _validate_fields(self) -> str | None:
        """
        Valida los campos obligatorios.
        Devuelve un mensaje de error si algo es invalido, o None si todo esta bien.
        """
        if not (self.token_entry.value or "").strip():
            return "El campo 'Discord Bot Token' es obligatorio."
        guild = (self.guild_entry.value or "").strip()
        if not guild:
            return "El campo 'Allowed Guild ID' es obligatorio."
        if not guild.isdigit():
            return "El 'Allowed Guild ID' debe ser un numero entero valido."
        return None

    def _warn_optional_fields(self):
        """Registra advertencias si los campos opcionales pero importantes estan vacios."""
        if not (self.groq_entry.value or "").strip():
            self.log(
                "⚠️  'Groq API Key' esta vacia — el analisis de IA no funcionara.",
                ft.Colors.ORANGE_400,
            )
        if not (self.vt_entry.value or "").strip():
            self.log(
                "⚠️  'VirusTotal API Key' esta vacia — el analisis de URLs no funcionara.",
                ft.Colors.ORANGE_400,
            )

    def _save_last_path(self, path: str):
        """Persiste la ultima carpeta seleccionada en el directorio home del usuario."""
        try:
            _CONFIG_FILE.write_text(json.dumps({"last_path": path}), encoding="utf-8")
        except Exception:
            pass

    def _restore_last_path(self):
        """Restaura la ultima carpeta usada al iniciar la aplicacion."""
        try:
            if _CONFIG_FILE.exists():
                data = json.loads(_CONFIG_FILE.read_text(encoding="utf-8"))
                last = data.get("last_path", "")
                if last and Path(last).is_dir():
                    self.project_path_text.value = last
                    self.log(f"📁 Directorio restaurado: {last}", ft.Colors.BLUE_200)
                    self.load_env_file(last)
                    try:
                        self.load_bot_config_file(last)
                    except Exception:
                        pass
                    self.update_states()
        except Exception:
            pass

    # ── Deteccion y limpieza de instancias ──────────────────────────────

    def _find_bot_pids(self) -> list:
        """Devuelve lista de PIDs de procesos del bot usando tasklist."""
        project = self.project_path_text.value
        if not project:
            return []

        project_path = Path(project).resolve()
        project_str = str(project_path).lower()
        pids: list[int] = []

        if sys.platform != "win32":
            try:
                res = subprocess.run(
                    ["pgrep", "-f", "python.*main\\.py|krorus"],
                    capture_output=True,
                    text=True,
                )
                if res.stdout:
                    return [int(pid) for pid in res.stdout.strip().split()]
            except Exception:
                pass
            return []

        try:
            res = subprocess.run(
                ["tasklist", "/FO", "CSV", "/NH"],
                capture_output=True,
                text=True,
                creationflags=CREATE_NO_WINDOW,
            )
            for line in res.stdout.strip().splitlines():
                parts = line.strip('"').split('","')
                if len(parts) < 2:
                    continue
                pid_str, image = parts[1], parts[0].lower()
                if "python" not in image:
                    continue
                try:
                    cmd_res = subprocess.run(
                        [
                            "wmic",
                            "process",
                            f"where ProcessId={pid_str}",
                            "get",
                            "CommandLine",
                            "/format:value",
                        ],
                        capture_output=True,
                        text=True,
                        creationflags=CREATE_NO_WINDOW,
                    )
                    cmdline = cmd_res.stdout.lower()
                    if (
                        project_str in cmdline
                        or "main.py" in cmdline
                        or "krorus" in cmdline
                    ):
                        pids.append(int(pid_str))
                except Exception:
                    pass
        except Exception:
            pass

        return pids

    def _kill_existing_bot_processes(self) -> list:
        """Termina procesos del bot existentes. Devuelve PIDs cerrados."""
        pids = self._find_bot_pids()
        killed_pids = []
        for pid in pids:
            try:
                subprocess.run(
                    ["taskkill", "/F", "/PID", str(pid)],
                    capture_output=True,
                    creationflags=CREATE_NO_WINDOW,
                )
                killed_pids.append(pid)
            except Exception:
                pass
        return killed_pids

    # ── Configuracion del bot (bot_config.json) ─────────────────────────────

    def load_bot_config_file(self, folder_path: str) -> None:
        """Carga las opciones de configuracion del bot desde data/bot_config.json si existe."""
        cfg_path = Path(folder_path) / "data" / "bot_config.json"
        if not cfg_path.exists():
            return
        try:
            data = json.loads(cfg_path.read_text(encoding="utf-8"))
        except Exception as e:
            self.log(f"Error al leer bot_config.json: {e}", ft.Colors.ORANGE_400)
            return

        self.switch_log_multimedia.value = data.get("log_multimedia", True)
        self.switch_transcribe_audio.value = data.get("transcribe_audio", True)
        self.switch_log_message_edits.value = data.get("log_message_edits", True)
        self.switch_enable_whisper.value = data.get("enable_whisper", True)
        self.switch_monitor_voice.value = data.get("monitor_voice_channels", True)
        self.switch_detailed_logging.value = data.get("detailed_logging", False)
        self.switch_check_exif.value = data.get("check_exif_metadata", True)
        self._safe_update()

    def _mark_config_changed(self, e=None):
        self._auto_save_bot_config()

    def _auto_save_bot_config(self):
        """Guarda bot_config.json automaticamente cuando cambia un switch."""
        project = self.project_path_text.value
        if not project:
            return
        cfg = {
            "log_multimedia": bool(self.switch_log_multimedia.value)
            if self.switch_log_multimedia
            else True,
            "transcribe_audio": bool(self.switch_transcribe_audio.value)
            if self.switch_transcribe_audio
            else True,
            "log_message_edits": bool(self.switch_log_message_edits.value)
            if self.switch_log_message_edits
            else True,
            "enable_whisper": bool(self.switch_enable_whisper.value)
            if self.switch_enable_whisper
            else True,
            "monitor_voice_channels": bool(self.switch_monitor_voice.value)
            if self.switch_monitor_voice
            else True,
            "detailed_logging": bool(self.switch_detailed_logging.value)
            if self.switch_detailed_logging
            else False,
            "check_exif_metadata": bool(self.switch_check_exif.value)
            if self.switch_check_exif
            else True,
        }
        cfg_dir = Path(project) / "data"
        cfg_dir.mkdir(parents=True, exist_ok=True)
        try:
            (cfg_dir / "bot_config.json").write_text(
                json.dumps(cfg, indent=4), encoding="utf-8"
            )
            self._config_changed = False
        except Exception as e:
            self.log(f"❌ Error al guardar bot_config.json: {e}", ft.Colors.RED_400)

    def reset_config_defaults(self, _):
        defaults = {
            "log_multimedia": True,
            "transcribe_audio": True,
            "log_message_edits": True,
            "enable_whisper": True,
            "monitor_voice_channels": True,
            "detailed_logging": False,
            "check_exif_metadata": True,
        }
        self.switch_log_multimedia.value = defaults["log_multimedia"]
        self.switch_transcribe_audio.value = defaults["transcribe_audio"]
        self.switch_log_message_edits.value = defaults["log_message_edits"]
        self.switch_enable_whisper.value = defaults["enable_whisper"]
        self.switch_monitor_voice.value = defaults["monitor_voice_channels"]
        self.switch_detailed_logging.value = defaults["detailed_logging"]
        self.switch_check_exif.value = defaults["check_exif_metadata"]
        self._auto_save_bot_config()
        self.log(
            "⚙️  Valores restablecidos y guardados automaticamente.", ft.Colors.BLUE_200
        )

    def _git_behind_count(self, repo_path: str) -> int | None:
        """Devuelve cuántos commits está detrás del remoto, o None si falla."""
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
            return int(res.stdout.strip() or 0)
        except Exception:
            return None

    def _show_update_badge(self, count: int):
        self.update_btn.icon = ft.Icon(
            ft.Icons.SYSTEM_UPDATE_ALT, color=ft.Colors.ORANGE_400
        )
        self.update_btn.tooltip = f"Hay {count} actualizaciones disponibles"
        self.update_badge.content.value = str(count)
        self.update_badge.visible = True
        self._safe_update()

    def _startup_update_check(self):
        repo_path = self.project_path_text.value
        if not repo_path:
            return
        count = self._git_behind_count(repo_path)
        if count is not None and count > 0:
            self.log(
                f"💡 ¡Hay {count} actualizaciones disponibles!", ft.Colors.GREEN_400
            )
            self._show_update_badge(count)

    def show_snackbar(self, text: str, color=ft.Colors.BLUE_ACCENT):
        def do_snack():
            try:
                snack = ft.SnackBar(content=ft.Text(text), bgcolor=color)
                for method_name in ("open_snack_bar", "show_snack_bar"):
                    if hasattr(self.page, method_name):
                        try:
                            self.page.snack_bar = snack
                            getattr(self.page, method_name)()
                            return
                        except Exception:
                            continue
                dlg = ft.AlertDialog(content=ft.Text(text))
                self.page.dialog = dlg
                self.page.open_dialog()
            except Exception:
                self.log(text, color)

        try:
            self.page.run_thread(do_snack)
        except Exception:
            do_snack()

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
        # Panel de ajustes principales
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
                ft.Divider(),
                ft.Text("Apariencia", size=14, weight=ft.FontWeight.W_600),
                self.theme_switch,
                ft.Divider(),
                ft.Text("Base de datos", size=14, weight=ft.FontWeight.W_600),
                ft.Row([self.restore_backup_btn]),
            ],
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        )

        # ── Switches de funciones ──────────────────────────────────────────
        self.switch_log_multimedia = ft.Switch(
            label="Registrar mensajes multimedia (imagenes, videos, archivos)",
            value=True,
            on_change=self._mark_config_changed,
        )
        self.switch_transcribe_audio = ft.Switch(
            label="Transcribir audios automaticamente (usa Groq AI)",
            value=True,
            on_change=self._mark_config_changed,
        )
        self.switch_log_message_edits = ft.Switch(
            label="Registrar y analizar mensajes editados en tiempo real",
            value=True,
            on_change=self._mark_config_changed,
        )
        self.switch_enable_whisper = ft.Switch(
            label="Habilitar comando /whisper (mensajes secretos cifrados)",
            value=True,
            on_change=self._mark_config_changed,
        )
        self.switch_monitor_voice = ft.Switch(
            label="Monitorizar canales de voz (alertas de supervision en vivo)",
            value=True,
            on_change=self._mark_config_changed,
        )
        self.switch_detailed_logging = ft.Switch(
            label="Registro detallado (modo debug, informacion extendida)",
            value=False,
            on_change=self._mark_config_changed,
        )
        self.switch_check_exif = ft.Switch(
            label="Verificar metadatos EXIF en archivos (GPS, camara, etc.)",
            value=True,
            on_change=self._mark_config_changed,
        )

        reset_btn = ft.Button(
            "Restablecer predeterminados",
            icon=ft.Icons.RESTART_ALT,
            on_click=self.reset_config_defaults,
        )

        features_list = ft.ListView(
            [
                ft.Text("Funciones disponibles", size=16, weight=ft.FontWeight.W_600),
                ft.Text(
                    "Los cambios se guardan automaticamente al cambiar un interruptor.",
                    size=12,
                    color=ft.Colors.GREY,
                ),
                ft.Divider(),
                self.switch_log_multimedia,
                self.switch_transcribe_audio,
                self.switch_log_message_edits,
                self.switch_monitor_voice,
                self.switch_check_exif,
                self.switch_detailed_logging,
                ft.Divider(),
                ft.Text(
                    "Funciones importantes (no desactivables):",
                    weight=ft.FontWeight.W_600,
                ),
                ft.Text(
                    "- Verificacion de integridad de la cadena (verify-chain)\n"
                    "- Allowed Guild enforcement (evita que el bot opere en servidores no autorizados)",
                    size=12,
                    color=ft.Colors.GREY,
                ),
                ft.Divider(),
                self.switch_enable_whisper,
                reset_btn,
                ft.Divider(),
                ft.Text("Cache de Groq", size=14, weight=ft.FontWeight.W_600),
                ft.Row(
                    [
                        ft.Column(
                            [
                                ft.Text("Aciertos:", size=12, color=ft.Colors.GREY),
                                self.cache_hits_text,
                            ]
                        ),
                        ft.Column(
                            [
                                ft.Text("Fallos:", size=12, color=ft.Colors.GREY),
                                self.cache_misses_text,
                            ]
                        ),
                        ft.Column(
                            [
                                ft.Text("Tamaño:", size=12, color=ft.Colors.GREY),
                                self.cache_size_text,
                            ]
                        ),
                    ]
                ),
                ft.Row([self.refresh_cache_btn, self.clear_cache_btn]),
            ],
            expand=True,
            spacing=4,
            padding=10,
        )

        buttons_column = ft.Column(
            [
                ft.Divider(height=20),
                ft.Row([self.status_dot, self.status_text]),
                ft.Row(
                    [
                        ft.Column(
                            [
                                ft.Text("Uptime:", size=12, color=ft.Colors.GREY),
                                self.bot_uptime_text,
                            ]
                        ),
                        ft.Column(
                            [
                                ft.Text("PID:", size=12, color=ft.Colors.GREY),
                                self.bot_pid_text,
                            ]
                        ),
                        self.bot_status_refresh_btn,
                    ]
                ),
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
                    [self.restart_btn, self.update_btn, self.update_badge],
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

        # ── Pestanas ─────────────────────────────────────────────────────
        tab_labels = [
            ("Principal", ft.Icons.SETTINGS),
            ("Funciones", ft.Icons.TOGGLE_ON),
        ]
        tab_views = [
            ft.Column([settings_column, buttons_column]),
            ft.Column([features_list], expand=True),
        ]

        self.tabs_control = self._build_tabs(tab_labels, tab_views)
        left_panel = ft.Column(
            [
                self.tabs_control,
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Icon(ft.Icons.CODE, size=14, color=ft.Colors.GREY),
                            self.version_text,
                        ]
                    ),
                    padding=ft.Padding(10, 0, 10, 10),
                ),
            ]
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
                    ft.Container(
                        content=left_panel,
                        width=380,
                        padding=20,
                        border_radius=10,
                        bgcolor=ft.Colors.SURFACE,
                    ),
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
                                            self.save_logs_btn,
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
        try:
            self.load_bot_config_file(path)
        except Exception:
            pass
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
            self._safe_update()
        except Exception as e:
            self.log(f"Error al leer .env: {e}", ft.Colors.RED_400)

    def log(self, message, color=ft.Colors.GREY_300):
        timestamp = time.strftime("%H:%M:%S")
        self._log_queue.append((timestamp, message, color))

        # Flush inmediato en el thread actual con lock
        self._flush_console()

    def _flush_console(self):
        """Vacia la cola de logs y actualiza la consola. Thread-safe con lock."""
        if not self._log_queue:
            return
        controls = self.console.controls
        if controls is None:
            return
        if len(controls) > 500:
            del controls[:50]
        batch = 0
        while self._log_queue and batch < 20:
            timestamp, message, color = self._log_queue.popleft()
            controls.append(
                ft.Text(
                    f"[{timestamp}] {message}",
                    color=color,
                    font_family="Consolas",
                    size=13,
                    selectable=True,
                )
            )
            batch += 1
        self._safe_update()

    def clear_console(self, _):
        self._log_queue.clear()
        controls = self.console.controls
        if controls:
            controls.clear()
        self._safe_update()

    def update_states(self):
        """Actualiza el estado de los botones y status. Thread-safe."""
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
            self.status_text.value = "Bot en ejecucion"
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

        self._refresh_bot_status()
        self._safe_update()

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
                self.log(f"Error de ejecucion: {e}", ft.Colors.RED_400)
                self.is_busy = False
                self.update_states()

        threading.Thread(target=target, daemon=True).start()

    # ── Acciones ───────────────────────────────────────────────────────────

    def save_env(self, _):
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
            self._auto_save_bot_config()
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
        self.log("🚀 Iniciando configuracion...", ft.Colors.BLUE_200)
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
            self.log("⚠️ No se encontro requirements.txt", ft.Colors.ORANGE_400)
            self.after_setup_complete(0)

    def after_setup_complete(self, rc):
        self.is_busy = False
        self.progress_bar.visible = False
        if rc == 0:
            self.log("🎉 Configuracion finalizada con exito!", ft.Colors.GREEN_400)
        else:
            self.log("❌ Hubo errores en la instalacion", ft.Colors.RED_400)
        self.update_states()

    def start_bot(self, _):
        if self.is_process_running():
            return

        python_bin = self._venv_python()
        main_file = Path(self.project_path_text.value) / "main.py"

        if not main_file.exists():
            self.log(
                "❌ No se encontro main.py en la carpeta seleccionada.",
                ft.Colors.RED_400,
            )
            return

        if not python_bin.exists():
            self.log(
                "❌ No se encontro el entorno virtual. Ejecuta 'Configurar' primero.",
                ft.Colors.RED_400,
            )
            return

        # Si hay instancias zombie, matarlas antes de iniciar
        zombie_pids = self._find_bot_pids()
        if zombie_pids:
            self.log(
                f"🧹 Se encontraron {len(zombie_pids)} instancia(s) zombie. Cerrandolas...",
                ft.Colors.ORANGE_400,
            )
            for pid in zombie_pids:
                subprocess.run(
                    ["taskkill", "/F", "/PID", str(pid)],
                    capture_output=True,
                    creationflags=CREATE_NO_WINDOW,
                )
            time.sleep(0.5)

        self.clear_console(None)
        self.log("🤖 Iniciando bot...", ft.Colors.GREEN_200)
        self._bot_start_time = time.time()
        self._start_uptime_timer()
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
            time.sleep(0.5)
            self.start_bot(None)
        else:
            self.log(f"⏹️ Bot detenido (Codigo: {rc})", ft.Colors.ORANGE_400)
        self.update_states()

    def _kill_process_tree(self, pid: int):
        """Mata un proceso y todo su arbol de hijos."""
        if sys.platform == "win32":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                capture_output=True,
                creationflags=CREATE_NO_WINDOW,
            )
        else:
            try:
                subprocess.run(["kill", "-TERM", f"-{pid}"], capture_output=True)
            except Exception:
                subprocess.run(["kill", "-TERM", str(pid)], capture_output=True)

    def _cleanup_process_ref(self):
        """Limpia la referencia al proceso y actualiza UI."""
        with self.process_lock:
            if self.running_process:
                try:
                    if self.running_process.poll() is None:
                        self._kill_process_tree(self.running_process.pid)
                except Exception:
                    pass
                self.running_process = None
        self.update_states()

    def stop_bot(self):
        self._cleanup_process_ref()
        self.log("🛑 Bot detenido.", ft.Colors.ORANGE_400)

    def restart_bot(self, _):
        with self._restart_lock:
            self._restart_requested = True
        self.stop_bot()

    def _update_dependencies(self, repo_path: str):
        pip_exe = self._venv_pip()
        req_file = Path(repo_path) / "requirements.txt"
        if not pip_exe.exists() or not req_file.exists():
            return
        self.log("📦 Verificando nuevas dependencias...", ft.Colors.BLUE_200)
        try:
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
            self.log("✅ Dependencias al dia.", ft.Colors.GREEN_200)
        except Exception as e:
            self.log(f"⚠️ Error actualizando dependencias: {e}", ft.Colors.ORANGE_400)

    def check_for_updates(self, _):
        self.is_busy = True
        self.update_states()
        self.log(
            "🔍 Buscando actualizaciones en el repositorio Git...", ft.Colors.BLUE_200
        )

        def update():
            repo_path = self.project_path_text.value
            try:
                count = self._git_behind_count(repo_path)
                if count is None:
                    self.log("⚠️ No se pudo consultar el remoto.", ft.Colors.ORANGE_400)
                    return

                if count == 0:
                    self.log("✅ El repositorio esta al dia.", ft.Colors.BLUE_200)
                    return

                self.log(
                    f"💡 ¡Hay {count} actualizaciones disponibles!",
                    ft.Colors.GREEN_400,
                )
                self._show_update_badge(count)

                pull_res = subprocess.run(
                    ["git", "pull"],
                    cwd=repo_path,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    creationflags=CREATE_NO_WINDOW,
                )
                if pull_res.returncode != 0:
                    self.log(
                        f"❌ Error al hacer pull: {pull_res.stderr}",
                        ft.Colors.RED_400,
                    )
                    return

                self.log("✅ Codigo actualizado con exito.", ft.Colors.GREEN_400)
                self._update_dependencies(repo_path)
            except Exception as e:
                self.log(f"⚠️ Error durante la actualizacion: {e}", ft.Colors.ORANGE_400)
            finally:
                self.is_busy = False
                self.update_states()

        threading.Thread(target=update, daemon=True).start()

    # ── Cache de Groq ───────────────────────────────────────────────────

    def _refresh_cache_stats(self, e=None):
        """Actualiza las estadisticas de cache de Groq desde modules.message."""
        try:
            from modules.message import get_misconduct_cache_stats
        except ImportError:
            self.cache_hits_text.value = "N/A"
            self.cache_misses_text.value = "N/A"
            self.cache_size_text.value = "N/A"
            self._safe_update()
            return
        try:
            stats = get_misconduct_cache_stats()
            self.cache_hits_text.value = str(stats.get("hits", "—"))
            self.cache_misses_text.value = str(stats.get("misses", "—"))
            self.cache_size_text.value = str(stats.get("size", "—"))
            self.clear_cache_btn.disabled = False
        except Exception as ex:
            self.log(f"Error al obtener stats de cache: {ex}", ft.Colors.RED_400)
        self._safe_update()

    def _clear_cache(self, e):
        """Limpia la cache de Groq."""
        try:
            from modules.message import clear_misconduct_cache

            clear_misconduct_cache()
            self.log("🧹 Cache de Groq limpiada.", ft.Colors.GREEN_400)
        except Exception as ex:
            self.log(f"Error al limpiar cache: {ex}", ft.Colors.RED_400)
        self._refresh_cache_stats()

    # ── Restore backup ──────────────────────────────────────────────────

    def _restore_backup(self, e):
        """Restaura el respaldo mas reciente de la base de datos."""
        try:
            from modules.database import restore_latest_backup
        except ImportError:
            self.log(
                "❌ No se pudo importar restore_latest_backup", ft.Colors.RED_400
            )
            return
        try:
            restore_latest_backup()
            self.log("✅ Respaldo restaurado correctamente.", ft.Colors.GREEN_400)
        except Exception as ex:
            self.log(f"❌ Error al restaurar respaldo: {ex}", ft.Colors.RED_400)

    # ── Theme toggle ────────────────────────────────────────────────────

    def _toggle_theme(self, e):
        """Alterna entre modo claro y oscuro."""
        self.page.theme_mode = (
            ft.ThemeMode.LIGHT if e.control.value else ft.ThemeMode.DARK
        )
        self._safe_update()

    def _start_uptime_timer(self):
        """Actualiza el uptime cada 5s mientras el bot corre."""

        def _loop():
            while True:
                with self.process_lock:
                    running = (
                        self.running_process is not None
                        and self.running_process.poll() is None
                    )
                if not running:
                    break
                self._refresh_bot_status()
                time.sleep(5)

        threading.Thread(target=_loop, daemon=True).start()

    # ── Bot status ──────────────────────────────────────────────────────

    def _refresh_bot_status(self, e=None):
        """Actualiza el uptime y PID del bot si esta en ejecucion."""
        with self.process_lock:
            running = (
                self.running_process is not None
                and self.running_process.poll() is None
            )
            pid = self.running_process.pid if running and self.running_process else None
        if running and pid and self._bot_start_time:
            uptime_secs = int(time.time() - self._bot_start_time)
            hours = uptime_secs // 3600
            minutes = (uptime_secs % 3600) // 60
            seconds = uptime_secs % 60
            self.bot_uptime_text.value = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
            self.bot_pid_text.value = str(pid)
        else:
            self.bot_uptime_text.value = "—"
            self.bot_pid_text.value = "—"
        self._safe_update()

    # ── Save logs ───────────────────────────────────────────────────────

    def _save_logs(self, e):
        """Guarda los logs de la consola en un archivo de texto."""
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        base = (
            Path(self.project_path_text.value)
            if self.project_path_text.value
            else Path.cwd()
        )
        filepath = base / f"console_log_{timestamp}.txt"
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                for ctrl in self.console.controls:
                    if isinstance(ctrl, ft.Text) and ctrl.value:
                        f.write(ctrl.value + "\n")
            self.log(f"💾 Logs guardados en {filepath.name}", ft.Colors.GREEN_200)
        except Exception as ex:
            self.log(f"❌ Error al guardar logs: {ex}", ft.Colors.RED_400)

    # ── Version ─────────────────────────────────────────────────────────

    def _get_git_hash(self) -> str:
        """Obtiene el hash corto de Git del repositorio del proyecto."""
        project = self.project_path_text.value
        if not project:
            return "—"
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                capture_output=True,
                text=True,
                cwd=project,
                creationflags=CREATE_NO_WINDOW,
            )
            if result.returncode == 0 and result.stdout.strip():
                return f"v{result.stdout.strip()}"
        except Exception:
            pass
        return "—"


def main(page: ft.Page):
    BotSetupApp(page)


if __name__ == "__main__":
    try:
        if hasattr(ft, "app"):
            try:
                ft.app(target=main)
            except TypeError:
                ft.app(main)
        else:
            ft.run(main)
    except Exception:
        try:
            ft.run(main)
        except Exception as e:
            print("No se pudo iniciar la interfaz Flet:", e)
