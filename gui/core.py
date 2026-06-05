import atexit
import collections
import logging
import sys
import threading
import time
from pathlib import Path

import flet as ft

logger = logging.getLogger("krorus.gui")

CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0
_ICON_PATH = Path(__file__).parent.parent / "krorus.ico"
_CONFIG_FILE = Path.home() / ".krorus_gui_config.json"


class BotSetupCore:
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

        self.running_process = None
        self.process_lock = threading.Lock()
        self._restart_lock = threading.Lock()
        self._restart_requested = False
        self.is_busy = False
        self._config_changed = False
        self._log_queue: collections.deque = collections.deque()
        self._update_lock = threading.Lock()

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

        self.console = ft.ListView(
            expand=True, spacing=2, auto_scroll=True,
            on_scroll=self._on_console_scroll,
        )

        self.status_dot = ft.Icon(ft.Icons.CIRCLE, color=ft.Colors.GREY_400, size=12)
        self.status_text = ft.Text("Esperando directorio...", color=ft.Colors.GREY_400)
        self.progress_bar = ft.ProgressBar(visible=False, color=ft.Colors.BLUE_ACCENT)

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

        self.update_badge = ft.Container(
            content=ft.Text(
                "", size=12, weight=ft.FontWeight.W_600, color=ft.Colors.WHITE
            ),
            padding=6,
            bgcolor=ft.Colors.ORANGE_600,
            border_radius=6,
            visible=False,
        )

        self.switch_log_multimedia = None
        self.switch_transcribe_audio = None
        self.switch_log_message_edits = None
        self.switch_enable_whisper = None
        self.switch_monitor_voice = None
        self.switch_detailed_logging = None
        self.switch_check_exif = None

        self.cache_hits_text = ft.Text("—", size=13)
        self.cache_misses_text = ft.Text("—", size=13)
        self.cache_size_text = ft.Text("—", size=13)
        self.refresh_cache_btn = ft.Button("Refrescar", icon=ft.Icons.REFRESH, on_click=self._refresh_cache_stats)
        self.clear_cache_btn = ft.Button("Limpiar", icon=ft.Icons.DELETE, on_click=self._clear_cache, disabled=True)

        self.theme_switch = ft.Switch(label="Modo claro", value=False, on_change=self._toggle_theme)

        self.bot_uptime_text = ft.Text("—", size=13)
        self.bot_pid_text = ft.Text("—", size=13)
        self.bot_status_refresh_btn = ft.IconButton(icon=ft.Icons.REFRESH, tooltip="Actualizar", on_click=self._refresh_bot_status)

        self.save_logs_btn = ft.IconButton(ft.Icons.SAVE, tooltip="Guardar logs", on_click=self._save_logs)

        self.version_text = ft.Text("—", size=12, color=ft.Colors.GREY, selectable=True)

        self.restore_backup_btn = ft.Button("Restaurar respaldo", icon=ft.Icons.RESTORE, on_click=self._restore_backup, disabled=True)

        self._bot_start_time = None

        self.setup_ui()
        self._restore_last_path()
        self.version_text.value = self._get_git_hash()
        self._cleanup_zombies()
        atexit.register(self._cleanup_process_ref)
        try:
            threading.Thread(target=self._startup_update_check, daemon=True).start()
        except Exception:
            logger.debug("No se pudo lanzar el hilo de chequeo de updates", exc_info=True)

    def _safe_update(self):
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

    def _run_on_thread(self, func):
        threading.Thread(target=func, daemon=True).start()

    def _cleanup_zombies(self):
        def do_cleanup():
            killed_pids = self._kill_existing_bot_processes()
            if killed_pids:
                self.log(
                    f"Se cerraron {len(killed_pids)} instancia(s) zombie del bot: {', '.join(str(p) for p in killed_pids)}.",
                    ft.Colors.ORANGE_400,
                )
            else:
                self.log("No hay instancias zombie del bot.", ft.Colors.GREEN_400)

        self._run_on_thread(do_cleanup)

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

    def _venv_python(self) -> Path:
        base = Path(self.project_path_text.value) / ".venv"
        return (
            base
            / ("Scripts" if sys.platform == "win32" else "bin")
            / ("python.exe" if sys.platform == "win32" else "python")
        )

    def _venv_pip(self) -> Path:
        base = Path(self.project_path_text.value) / ".venv"
        return (
            base
            / ("Scripts" if sys.platform == "win32" else "bin")
            / ("pip.exe" if sys.platform == "win32" else "pip")
        )

    def log(self, message, color=ft.Colors.GREY_300):
        timestamp = time.strftime("%H:%M:%S")
        self._log_queue.append((timestamp, message, color))
        self._flush_console()

    def _flush_console(self):
        if not self._log_queue:
            return
        controls = self.console.controls
        if controls is None:
            return
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
        if controls is not None:
            controls.clear()
        self._safe_update()

    def _on_console_scroll(self, e):
        if e.event_type != "user_scroll":
            return
        if e.pixels is not None and e.max_scroll_extent is not None:
            near_bottom = e.pixels >= e.max_scroll_extent - 50
            if near_bottom != self.console.auto_scroll:
                self.console.auto_scroll = near_bottom
                self._safe_update()

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
