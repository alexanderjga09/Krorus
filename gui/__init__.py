import flet as ft

from .core import BotSetupCore
from .ui import BotSetupUI
from .actions import BotSetupActions


class BotSetupApp(BotSetupCore, BotSetupUI, BotSetupActions):
    pass


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
