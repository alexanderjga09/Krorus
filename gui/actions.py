import json
import logging
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import flet as ft

from .core import _CONFIG_FILE, CREATE_NO_WINDOW

logger = logging.getLogger("krorus.gui")


class BotSetupActions:
    def _escape_env_val(self, val: str | None) -> str:
        if val is None:
            return ""
        v = str(val).strip()
        v = v.replace("\\", "\\\\").replace('"', '\\"')
        return v

    def _build_env_content(self) -> str:
        return (
            f'TOKEN="{self._escape_env_val(self.token_entry.value)}"\n'
            f'GROQ_API_KEY="{self._escape_env_val(self.groq_entry.value)}"\n'
            f'VIRUSTOTAL_API_KEY="{self._escape_env_val(self.vt_entry.value)}"\n'
            f'ALLOWED_GUILD_ID="{self._escape_env_val(self.guild_entry.value)}"'
        )

    def _validate_fields(self) -> str | None:
        if not (self.token_entry.value or "").strip():
            return "El campo 'Discord Bot Token' es obligatorio."
        guild = (self.guild_entry.value or "").strip()
        if not guild:
            return "El campo 'Allowed Guild ID' es obligatorio."
        if not guild.isdigit():
            return "El 'Allowed Guild ID' debe ser un numero entero valido."
        return None

    def _warn_optional_fields(self):
        if not (self.groq_entry.value or "").strip():
            self.log(
                "'Groq API Key' esta vacia — el analisis de IA no funcionara.",
                ft.Colors.ORANGE_400,
            )
        if not (self.vt_entry.value or "").strip():
            self.log(
                "'VirusTotal API Key' esta vacia — el analisis de URLs no funcionara.",
                ft.Colors.ORANGE_400,
            )

    def _save_last_path(self, path: str):
        try:
            _CONFIG_FILE.write_text(json.dumps({"last_path": path}), encoding="utf-8")
        except Exception:
            logger.debug("No se pudo guardar la ultima ruta usada", exc_info=True)

    def _restore_last_path(self):
        try:
            if _CONFIG_FILE.exists():
                data = json.loads(_CONFIG_FILE.read_text(encoding="utf-8"))
                last = data.get("last_path", "")
                if last and Path(last).is_dir():
                    self.project_path_text.value = last
                    self.log(f"Directorio restaurado: {last}", ft.Colors.BLUE_200)
                    self.load_env_file(last)
                    try:
                        self.load_bot_config_file(last)
                    except Exception:
                        pass
                    self.update_states()
                    self._refresh_backup_list_ui()
        except Exception:
            logger.debug("No se pudo restaurar la ultima ruta de proyecto", exc_info=True)

    def _find_bot_pids(self) -> list:
        project = self.project_path_text.value
        if not project:
            return []

        my_pid = os.getpid()
        project_path = Path(project).resolve()
        project_str = str(project_path).lower()

        def is_ours(cmdline: str) -> bool:
            # Solo procesos cuyo cmdline referencia ESTE proyecto. Aceptar
            # cualquier "main.py" mataria bots/scripts de otros proyectos.
            low = (cmdline or "").lower()
            return project_str in low and "main.py" in low

        if sys.platform != "win32":
            try:
                res = subprocess.run(
                    ["pgrep", "-af", "python"],
                    capture_output=True,
                    text=True,
                )
                pids: list[int] = []
                for line in (res.stdout or "").splitlines():
                    pid_str, _, cmdline = line.strip().partition(" ")
                    if (
                        pid_str.isdigit()
                        and int(pid_str) != my_pid
                        and is_ours(cmdline)
                    ):
                        pids.append(int(pid_str))
                return pids
            except Exception:
                return []

        # Windows: una sola consulta CIM via PowerShell. wmic esta deprecado y
        # ya no existe en builds recientes de Windows 11; ademas se lanzaba un
        # proceso wmic por cada PID encontrado.
        try:
            ps_cmd = (
                "Get-CimInstance Win32_Process -Filter \"Name LIKE '%python%'\" | "
                "Select-Object ProcessId,CommandLine | ConvertTo-Json -Compress"
            )
            res = subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps_cmd],
                capture_output=True,
                text=True,
                creationflags=CREATE_NO_WINDOW,
            )
            raw = (res.stdout or "").strip()
            if not raw:
                return []
            data = json.loads(raw)
            if isinstance(data, dict):
                data = [data]
            pids = []
            for proc in data:
                pid_val = proc.get("ProcessId")
                if (
                    isinstance(pid_val, int)
                    and pid_val != my_pid
                    and is_ours(proc.get("CommandLine") or "")
                ):
                    pids.append(pid_val)
            return pids
        except Exception:
            return []

    def _kill_existing_bot_processes(self) -> set[int]:
        pids = self._find_bot_pids()
        killed_pids: set[int] = set()
        for pid in pids:
            try:
                subprocess.run(
                    ["taskkill", "/F", "/PID", str(pid)],
                    capture_output=True,
                    creationflags=CREATE_NO_WINDOW,
                )
                killed_pids.add(pid)
            except Exception:
                pass
        return killed_pids

    def load_bot_config_file(self, folder_path: str) -> None:
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
        cfg_path = cfg_dir / "bot_config.json"
        # Merge con el archivo existente: la GUI solo conoce los switches, pero
        # el archivo puede tener claves manuales (groq_timeout, etc.) que no
        # deben perderse al auto-guardar.
        existing: dict = {}
        try:
            if cfg_path.exists():
                loaded = json.loads(cfg_path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    existing = loaded
        except Exception:
            existing = {}
        existing.update(cfg)
        try:
            cfg_path.write_text(json.dumps(existing, indent=4), encoding="utf-8")
            self._config_changed = False
        except Exception as e:
            self.log(f"Error al guardar bot_config.json: {e}", ft.Colors.RED_400)

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
            "Valores restablecidos y guardados automaticamente.", ft.Colors.BLUE_200
        )

    def _git_behind_count(self, repo_path: str) -> int | None:
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
                f"Hay {count} actualizaciones disponibles!", ft.Colors.GREEN_400
            )
            self._show_update_badge(count)

    def save_env(self, _):
        if not self.project_path_text.value:
            return
        err = self._validate_fields()
        if err:
            self.show_snackbar(f"{err}", ft.Colors.ORANGE_800)
            return
        self._warn_optional_fields()
        env_path = Path(self.project_path_text.value) / ".env"
        try:
            env_path.write_text(self._build_env_content(), encoding="utf-8")
            self.log("Credenciales guardadas en .env", ft.Colors.GREEN_200)
            self._auto_save_bot_config()
        except Exception as e:
            self.log(f"Error al guardar .env: {e}", ft.Colors.RED_400)

    def start_setup(self, _):
        if not self.project_path_text.value:
            return
        err = self._validate_fields()
        if err:
            self.show_snackbar(f"{err}", ft.Colors.ORANGE_800)
            return

        self.is_busy = True
        self.progress_bar.visible = True
        self.clear_console(None)
        self.log("Iniciando configuracion...", ft.Colors.BLUE_200)
        self.update_states()

        self._warn_optional_fields()

        env_path = Path(self.project_path_text.value) / ".env"
        try:
            env_path.write_text(self._build_env_content(), encoding="utf-8")
            self.log("Archivo .env guardado", ft.Colors.GREEN_200)
        except Exception as e:
            self.log(f"Error al guardar .env: {e}", ft.Colors.RED_400)
            self.is_busy = False
            self.progress_bar.visible = False
            self.update_states()
            return

        venv_dir = Path(self.project_path_text.value) / ".venv"
        self.log("Creando/Verificando entorno virtual...", ft.Colors.BLUE_200)
        self.run_command(
            [sys.executable, "-m", "venv", str(venv_dir)],
            cwd=self.project_path_text.value,
            on_finish=self.after_venv,
        )

    def after_venv(self, rc):
        if rc != 0:
            self.log("Error al crear entorno virtual", ft.Colors.RED_400)
            self.is_busy = False
            self.progress_bar.visible = False
            self.update_states()
            return

        pip_exe = self._venv_pip()
        req_file = Path(self.project_path_text.value) / "requirements.txt"
        if req_file.exists():
            self.log("Instalando dependencias...", ft.Colors.BLUE_200)
            self.run_command(
                [str(pip_exe), "install", "-r", str(req_file)],
                cwd=self.project_path_text.value,
                on_finish=self.after_requirements,
            )
        else:
            self.log("No se encontro requirements.txt", ft.Colors.ORANGE_400)
            self.after_requirements(0)

    def _crate_dirs(self, project: str) -> list[str]:
        """Carpetas de crates con pyproject.toml (extensiones nativas del bot)."""
        return [
            str(p.parent)
            for p in sorted((Path(project) / "crates").glob("*/pyproject.toml"))
        ]

    def after_requirements(self, rc):
        if rc != 0:
            self.after_setup_complete(rc)
            return
        # Las extensiones nativas (chainlog_rs, exif_rs) son obligatorias para
        # el bot; sin este paso una instalacion nueva fallaba con
        # ModuleNotFoundError al iniciar.
        crate_dirs = self._crate_dirs(self.project_path_text.value)
        if not crate_dirs:
            self.after_setup_complete(0)
            return
        self.log(
            "Compilando extensiones nativas de Rust (puede tardar unos minutos)...",
            ft.Colors.BLUE_200,
        )
        self.run_command(
            [str(self._venv_pip()), "install", "--upgrade", *crate_dirs],
            cwd=self.project_path_text.value,
            on_finish=self.after_crates,
        )

    def after_crates(self, rc):
        if rc != 0:
            self.log(
                "Error compilando las extensiones de Rust. Verifica que Rust este "
                "instalado y en el PATH: https://rustup.rs",
                ft.Colors.RED_400,
            )
        self.after_setup_complete(rc)

    def after_setup_complete(self, rc):
        self.is_busy = False
        self.progress_bar.visible = False
        if rc == 0:
            self.log("Configuracion finalizada con exito!", ft.Colors.GREEN_400)
        else:
            self.log("Hubo errores en la instalacion", ft.Colors.RED_400)
        self.update_states()

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
                self.is_busy = False
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

    def start_bot(self, _):
        if self.is_busy or self.is_process_running():
            return

        python_bin = self._venv_python()
        main_file = Path(self.project_path_text.value) / "main.py"

        if not main_file.exists():
            self.log(
                "No se encontro main.py en la carpeta seleccionada.",
                ft.Colors.RED_400,
            )
            return

        if not python_bin.exists():
            self.log(
                "No se encontro el entorno virtual. Ejecuta 'Configurar' primero.",
                ft.Colors.RED_400,
            )
            return

        zombie_pids = self._find_bot_pids()
        if zombie_pids:
            self.log(
                f"Se encontraron {len(zombie_pids)} instancia(s) zombie. Cerrandolas...",
                ft.Colors.ORANGE_400,
            )
            for pid in zombie_pids:
                subprocess.run(
                    ["taskkill", "/F", "/PID", str(pid)],
                    capture_output=True,
                    creationflags=CREATE_NO_WINDOW,
                )
            time.sleep(0.5)

        self.is_busy = True
        self._do_update_states()

        self.clear_console(None)
        self.log("Iniciando bot...", ft.Colors.GREEN_200)
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
            self.log(f"Bot detenido (Codigo: {rc})", ft.Colors.ORANGE_400)
        self.update_states()

    def _kill_process_tree(self, pid: int):
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
        zombie_pids = self._kill_existing_bot_processes()
        with self.process_lock:
            if self.running_process:
                try:
                    pid = self.running_process.pid
                    if self.running_process.poll() is None:
                        self._kill_process_tree(pid)
                    zombie_pids.discard(pid)
                except Exception:
                    pass
                self.running_process = None
        if zombie_pids:
            time.sleep(0.3)
        self.update_states()

    def stop_bot(self):
        self._cleanup_process_ref()
        self.log("Bot detenido.", ft.Colors.ORANGE_400)

    def restart_bot(self, _):
        with self._restart_lock:
            self._restart_requested = True
        self.stop_bot()

    def _stream_pip(self, args: list[str], cwd: str) -> int:
        """Ejecuta pip mostrando su salida en la consola. Devuelve el returncode."""
        proc = subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=cwd,
            creationflags=CREATE_NO_WINDOW,
        )
        if proc.stdout:
            for line in proc.stdout:
                line = line.rstrip()
                if line:
                    self.log(line)
            proc.stdout.close()
        return proc.wait()

    def _update_dependencies(self, repo_path: str):
        pip_exe = self._venv_pip()
        req_file = Path(repo_path) / "requirements.txt"
        if not pip_exe.exists() or not req_file.exists():
            return
        self.log("Verificando nuevas dependencias...", ft.Colors.BLUE_200)
        try:
            self._stream_pip(
                [str(pip_exe), "install", "-r", str(req_file)], cwd=repo_path
            )
            # Recompilar tambien las extensiones nativas: un git pull puede
            # haber cambiado el codigo Rust.
            crate_dirs = self._crate_dirs(repo_path)
            if crate_dirs:
                self.log("Recompilando extensiones nativas (Rust)...", ft.Colors.BLUE_200)
                rc = self._stream_pip(
                    [str(pip_exe), "install", "--upgrade", *crate_dirs],
                    cwd=repo_path,
                )
                if rc != 0:
                    self.log(
                        "Error recompilando extensiones de Rust.", ft.Colors.RED_400
                    )
                    return
            self.log("Dependencias al dia.", ft.Colors.GREEN_200)
        except Exception as e:
            self.log(f"Error actualizando dependencias: {e}", ft.Colors.ORANGE_400)

    def check_for_updates(self, _):
        self.is_busy = True
        self.update_states()
        self.log(
            "Buscando actualizaciones en el repositorio Git...", ft.Colors.BLUE_200
        )

        def update():
            repo_path = self.project_path_text.value
            try:
                count = self._git_behind_count(repo_path)
                if count is None:
                    self.log("No se pudo consultar el remoto.", ft.Colors.ORANGE_400)
                    return

                if count == 0:
                    self.log("El repositorio esta al dia.", ft.Colors.BLUE_200)
                    return

                self.log(
                    f"Hay {count} actualizaciones disponibles!",
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
                        f"Error al hacer pull: {pull_res.stderr}",
                        ft.Colors.RED_400,
                    )
                    return

                self.log("Codigo actualizado con exito.", ft.Colors.GREEN_400)
                self._update_dependencies(repo_path)
            except Exception as e:
                self.log(f"Error durante la actualizacion: {e}", ft.Colors.ORANGE_400)
            finally:
                self.is_busy = False
                self.update_states()

        threading.Thread(target=update, daemon=True).start()

    def _refresh_cache_stats(self, e=None):
        try:
            from scripts.modules.misconduct_cache import get_misconduct_cache_stats
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
        try:
            from scripts.modules.misconduct_cache import clear_misconduct_cache

            clear_misconduct_cache()
            self.log("Cache de Groq limpiada.", ft.Colors.GREEN_400)
        except Exception as ex:
            self.log(f"Error al limpiar cache: {ex}", ft.Colors.RED_400)
        self._refresh_cache_stats()

    def _restore_backup(self, e):
        try:
            from scripts.modules.database import restore_latest_backup
        except ImportError:
            self.log(
                "No se pudo importar restore_latest_backup", ft.Colors.RED_400
            )
            return
        try:
            restore_latest_backup()
            self.log("Respaldo restaurado correctamente.", ft.Colors.GREEN_400)
        except Exception as ex:
            self.log(f"Error al restaurar respaldo: {ex}", ft.Colors.RED_400)

    def _backup_dir(self) -> Path:
        from scripts.modules.database import BACKUP_DIR
        return BACKUP_DIR

    def _open_backup_folder(self, e):
        path = self._backup_dir()
        if path.exists():
            os.startfile(str(path))

    def _create_backup(self, e):
        try:
            from scripts.modules.database import backup_db
            ok = backup_db()
            if ok:
                self.log("Respaldo creado exitosamente.", ft.Colors.GREEN_400)
            else:
                self.log("No se pudo crear el respaldo.", ft.Colors.RED_400)
        except Exception as ex:
            self.log(f"Error al crear respaldo: {ex}", ft.Colors.RED_400)
        self._refresh_backup_list_ui()

    def _restore_selected_backup(self, e):
        path = getattr(self, "_selected_backup_path", None)
        if not path:
            self.log("Selecciona un respaldo de la lista.", ft.Colors.YELLOW_400)
            return
        import shutil
        from scripts.modules.database import DB_PATH
        try:
            shutil.copy2(path, DB_PATH)
            self.log(f"Restaurado desde: {path.name}", ft.Colors.GREEN_400)
        except Exception as ex:
            self.log(f"Error al restaurar: {ex}", ft.Colors.RED_400)
        self._refresh_backup_list_ui()

    def _on_backup_click(self, path: Path):
        def _inner(e):
            self._selected_backup_path = path
            self.backup_restore_btn.disabled = False
            for c in (self.backup_list_view.controls or []):
                if isinstance(c, ft.Container):
                    c.bgcolor = None
            e.control.bgcolor = ft.Colors.BLUE_900
            self._safe_update()
        return _inner

    def _refresh_backup_list_ui(self):
        controls = self.backup_list_view.controls
        if controls is None:
            return
        controls.clear()
        backup_dir = self._backup_dir()
        if not backup_dir.exists():
            self.backup_status_text.value = "No existe el directorio de respaldos."
            self.backup_restore_btn.disabled = True
            self._safe_update()
            return
        files = sorted(
            backup_dir.glob("settings_*.db"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if not files:
            self.backup_status_text.value = "No hay respaldos disponibles."
            self.backup_restore_btn.disabled = True
            self._safe_update()
            return
        self.backup_status_text.value = f"{len(files)} respaldo(s) encontrado(s)"
        from datetime import datetime
        for f in files:
            mtime = datetime.fromtimestamp(f.stat().st_mtime)
            size = f.stat().st_size
            label = f"{mtime.strftime('%Y-%m-%d %H:%M:%S')}  |  {size:,} bytes"
            controls.append(
                ft.Container(
                    content=ft.Text(label, size=13, font_family="Consolas", selectable=True),
                    padding=6,
                    border_radius=4,
                    ink=True,
                    on_click=self._on_backup_click(f),
                )
            )
        self.backup_restore_btn.disabled = True
        self._safe_update()

    def _toggle_theme(self, e):
        self.page.theme_mode = (
            ft.ThemeMode.LIGHT if e.control.value else ft.ThemeMode.DARK
        )
        self._safe_update()

    def _start_uptime_timer(self):
        # Un solo hilo para toda la vida de la GUI: antes se creaba un hilo
        # infinito nuevo en cada arranque del bot (fuga de hilos).
        if getattr(self, "_uptime_timer_started", False):
            return
        self._uptime_timer_started = True

        def _loop():
            while True:
                with self.process_lock:
                    running = (
                        self.running_process is not None
                        and self.running_process.poll() is None
                    )
                if not running:
                    time.sleep(1)
                    continue
                self._refresh_bot_status()
                time.sleep(5)

        threading.Thread(target=_loop, daemon=True).start()

    def _refresh_bot_status(self, e=None):
        with self.process_lock:
            running = (
                self.running_process is not None
                and self.running_process.poll() is None
            )
            pid = self.running_process.pid if running and self.running_process else None

        def _do():
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

        try:
            self.page.run_thread(_do)
        except Exception:
            _do()

    def _save_logs(self, e):
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        base = (
            Path(self.project_path_text.value)
            if self.project_path_text.value
            else Path.cwd()
        )
        filepath = base / f"console_log_{timestamp}.txt"
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                for rec in self._log_records:
                    f.write(rec["text"] + "\n")
            self.log(f"Logs guardados en {filepath.name}", ft.Colors.GREEN_200)
        except Exception as ex:
            self.log(f"Error al guardar logs: {ex}", ft.Colors.RED_400)

    def _get_git_hash(self) -> str:
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
