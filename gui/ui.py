import os
import re
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog
from typing import Any

import flet as ft

from .core import _ICON_PATH


class BotSetupUI:
    def _build_tabs(
        self, labels: list[tuple[str, Any]], views: list[ft.Control]
    ) -> ft.Control:
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
                                ft.Text("Tamano:", size=12, color=ft.Colors.GREY),
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
        self.log(f"Carpeta seleccionada: {path}", ft.Colors.BLUE_200)
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
            self.log("Valores cargados desde .env", ft.Colors.GREEN_200)
            self._safe_update()
        except Exception as e:
            self.log(f"Error al leer .env: {e}", ft.Colors.RED_400)

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
