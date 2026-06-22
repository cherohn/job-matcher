"""Modern desktop launcher for Job Matcher."""

import ctypes
import logging
import os
import queue
import smtplib
import sys
import threading
import time
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk
import requests
from PIL import Image

import main as engine
from core.report import REPORT_DIR, list_report_summaries, save_manual_analysis_report, save_resume_optimization_report
from core.tracker import (
    STATUS_LABELS,
    STATUS_ORDER,
    calculate_metrics,
    get_follow_up_alerts,
    load_applications,
    register_application,
    update_application,
)
from core.user_config import get_config_path, import_user_file, load_user_config, save_user_config


FONT = "Segoe UI"

COLORS = {
    "bg_deep": "#0F0F0F",
    "bg_base": "#141414",
    "bg_surface": "#1C1C1C",
    "bg_elevated": "#252525",
    "bg_hover": "#2C2C2C",
    "amber": "#C49A3C",
    "amber_dim": "#8B6B2A",
    "amber_subtle": "#2A2318",
    "text_primary": "#E8E8E8",
    "text_secondary": "#999999",
    "text_muted": "#555555",
    "border": "#2A2A2A",
    "border_bright": "#3A3A3A",
    "green": "#27AE60",
    "green_subtle": "#1A2E22",
    "red": "#C0392B",
    "red_subtle": "#2E1A1A",
}
C = COLORS

BG = COLORS["bg_deep"]
BASE = COLORS["bg_base"]
SURFACE = COLORS["bg_surface"]
SURFACE_2 = COLORS["bg_elevated"]
BORDER = COLORS["border"]
ACCENT = COLORS["amber"]
ACCENT_DIM = COLORS["amber_dim"]
TEXT = COLORS["text_primary"]
MUTED = COLORS["text_secondary"]
DANGER = COLORS["red"]
DANGER_DARK = COLORS["red_subtle"]


def resource_path(relative_path):
    base_path = getattr(sys, "_MEIPASS", os.path.abspath("."))
    return os.path.join(base_path, relative_path)


def app_version():
    try:
        return Path(resource_path("VERSION")).read_text(encoding="utf-8").strip()
    except Exception:
        return "0.1.1"


def friendly_log_message(level, message):
    clean = " ".join(str(message).split())
    if not clean or clean == "=" * len(clean):
        return None

    low = clean.lower()
    if "varredura" in low and "/" in clean:
        return "Nova varredura iniciada."
    if "queries ativas" in low:
        count = clean.split(":", 1)[-1].strip()
        return f"Aguarde. {count} pesquisas serao feitas no Google/Serper."
    if "aguarde" in low:
        return clean
    if "google/serper:" in low and "vagas" in low:
        return clean.replace("Google/Serper:", "Google:")
    if "total coletado" in low:
        return clean.replace("Unicas", "unicas")
    if "novas para analisar" in low:
        return clean
    if "nenhuma vaga nova" in low:
        return clean
    if "limitando analise" in low:
        return clean
    if "proxima tentativa" in low:
        return clean
    if clean.startswith("Analisando:"):
        return clean.replace("Analisando:", "Analisando vaga:")
    if "descricao insuficiente" in low:
        return "Vaga ignorada: descricao insuficiente."
    if "relatorio salvo" in low:
        return clean
    if "abrindo pasta de relatorios" in low:
        return clean
    if "enviando resumo" in low:
        return "Enviando e-mail com os melhores matches."
    if "resumo enviado" in low:
        return "Resumo enviado por e-mail."
    if "e-mail de teste enviado" in low:
        return clean
    if "nenhuma vaga atingiu" in low:
        return clean
    if "concluida" in low:
        return "Varredura concluida."
    if "monitoramento iniciado" in low:
        return "Monitoramento iniciado."
    if "monitoramento parado" in low:
        return "Monitoramento parado."
    if "parada solicitada" in low:
        return "Parada solicitada. Finalizando no proximo ponto seguro."
    if level in {"ERROR", "WARNING"}:
        return clean
    return None


class QueueLogHandler(logging.Handler):
    def __init__(self, messages):
        super().__init__()
        self.messages = messages

    def emit(self, record):
        message = friendly_log_message(record.levelname, record.getMessage())
        if message:
            self.messages.put((record.levelname, time.strftime("%H:%M:%S"), message))


class JobMatcherApp(ctk.CTk):
    def __init__(self):
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")

        super().__init__(fg_color=BG)
        self.title("Job Matcher")
        self.geometry("1280x820")
        self.minsize(1024, 720)
        self.after(0, self._maximize_window)

        self.messages = queue.Queue()
        self.stop_event = threading.Event()
        self.worker = None
        self.monitoring = False

        self.max_jobs = tk.StringVar(value=str(getattr(engine.settings, "MAX_JOBS_TO_ANALYZE_PER_SCAN", 25)))
        self.interval = tk.StringVar(value=str(engine.SCAN_INTERVAL_MINUTES))
        self.min_score = tk.StringVar(value=str(engine.MIN_SCORE))
        self.status_text = tk.StringVar(value="Pronto")
        self.next_scan_text = tk.StringVar(value="-")
        self.analysis_status = tk.StringVar(value="Cole uma vaga e clique em Analisar.")
        self.analysis_title = tk.StringVar()
        self.analysis_company = tk.StringVar()
        self.analysis_worker = None
        self.ats_worker = None
        self.cover_letter_worker = None
        self.last_analysis_text = ""
        self.last_job_context = None
        self.optimization_status = tk.StringVar(value="Cole uma vaga e gere uma otimizacao.")
        self.optimization_title = tk.StringVar()
        self.optimization_company = tk.StringVar()
        self.optimization_worker = None
        self.last_optimization_text = ""
        self.market_status = tk.StringVar(value="Historico pronto para analisar.")
        self.market_worker = None
        self.selected_application_id = None
        self.tracker_cards = {}
        self.report_rows = []
        self.nav_buttons = {}
        self.nav_indicators = {}
        self.tab_frames = {}
        self.current_tab = "Busca"

        self._set_window_icon()
        self._configure_logging()
        self._build_layout()
        self._log_follow_up_alerts()
        self._refresh_log()

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _set_window_icon(self):
        ico_path = resource_path(os.path.join("assets", "jobmatcher.ico"))
        png_path = resource_path(os.path.join("assets", "jobmatcher-icon.png"))
        try:
            if os.path.exists(ico_path):
                self.iconbitmap(ico_path)
            if os.path.exists(png_path):
                self._icon_photo = tk.PhotoImage(file=png_path)
                self.iconphoto(True, self._icon_photo)
        except tk.TclError:
            pass
        self._apply_dark_title_bar(self)

    def _maximize_window(self):
        try:
            self.state("zoomed")
        except tk.TclError:
            try:
                self.attributes("-zoomed", True)
            except tk.TclError:
                pass

    def _apply_dark_title_bar(self, window):
        if sys.platform != "win32":
            return
        try:
            window.update_idletasks()
            hwnd = ctypes.windll.user32.GetParent(window.winfo_id()) or window.winfo_id()
            enabled = ctypes.c_int(1)
            for attribute in (20, 19):
                result = ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    ctypes.c_void_p(hwnd),
                    ctypes.c_int(attribute),
                    ctypes.byref(enabled),
                    ctypes.sizeof(enabled),
                )
                if result == 0:
                    break
        except Exception:
            pass

    def _set_setup_window_style(self, window):
        ico_path = resource_path(os.path.join("assets", "settings.ico"))
        try:
            if os.path.exists(ico_path):
                window.iconbitmap(ico_path)
        except tk.TclError:
            pass
        self._apply_dark_title_bar(window)

    def _load_logo(self, size=(48, 48)):
        path = resource_path(os.path.join("assets", "jobmatcher-icon.png"))
        if not os.path.exists(path):
            return None
        return ctk.CTkImage(Image.open(path), size=size)

    def _configure_logging(self):
        handler = QueueLogHandler(self.messages)
        logging.getLogger().addHandler(handler)
        logging.getLogger().setLevel(logging.INFO)

    def _log_follow_up_alerts(self):
        alerts = get_follow_up_alerts()
        if not alerts:
            return
        names = "; ".join(f"{item.get('cargo')} @ {item.get('empresa')}" for item in alerts[:4])
        if len(alerts) > 4:
            names += f"; +{len(alerts) - 4}"
        logging.warning("Follow-up pendente em candidaturas: %s", names)

    def _build_layout(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.sidebar = ctk.CTkFrame(self, width=160, corner_radius=0, fg_color=BG, border_width=0)
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_propagate(False)
        self.sidebar.grid_rowconfigure(6, weight=1)
        ctk.CTkFrame(self.sidebar, width=1, fg_color=C["border"], corner_radius=0).grid(row=0, column=1, rowspan=9, sticky="nse")

        brand = ctk.CTkFrame(self.sidebar, fg_color="transparent", corner_radius=0)
        brand.grid(row=0, column=0, padx=12, pady=(16, 12), sticky="ew")
        icon = ctk.CTkFrame(brand, width=28, height=28, corner_radius=6, fg_color=COLORS["amber_subtle"], border_width=1, border_color=ACCENT_DIM)
        icon.pack(side="left", padx=(0, 8))
        icon.pack_propagate(False)
        ctk.CTkLabel(icon, text="*", text_color=ACCENT, font=(FONT, 16, "bold")).place(relx=0.5, rely=0.5, anchor="center")
        title = ctk.CTkFrame(brand, fg_color="transparent")
        title.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(title, text="Job Matcher", font=(FONT, 13, "bold"), text_color=TEXT).pack(anchor="w")
        ctk.CTkLabel(title, text=f"v{app_version()}", font=(FONT, 10), text_color=COLORS["text_muted"]).pack(anchor="w")

        separator = ctk.CTkFrame(self.sidebar, fg_color=BORDER, height=1, corner_radius=0)
        separator.grid(row=1, column=0, sticky="ew")

        self.status_card = self._sidebar_card("STATUS", self.status_text, accent=COLORS["green"])
        self.status_card.grid(row=2, column=0, padx=12, pady=(12, 8), sticky="ew")
        self.next_card = self._sidebar_card("PROXIMA BUSCA", self.next_scan_text, accent=TEXT)
        self.next_card.grid(row=3, column=0, padx=12, pady=(0, 8), sticky="ew")
        self.context_card_var = tk.StringVar(value="Google / Serper")
        self.context_card = self._sidebar_card("FONTE", self.context_card_var, accent=ACCENT)
        self.context_card.grid(row=4, column=0, padx=12, pady=(0, 12), sticky="ew")

        ctk.CTkButton(
            self.sidebar,
            text="Configurar",
            height=34,
            corner_radius=6,
            fg_color=ACCENT,
            hover_color=ACCENT_DIM,
            text_color=BG,
            border_width=1,
            border_color=ACCENT,
            font=(FONT, 12, "bold"),
            command=self.open_setup_window,
        ).grid(row=5, column=0, padx=12, pady=(0, 12), sticky="ew")

        ctk.CTkButton(
            self.sidebar,
            text="Abrir relatorios",
            height=34,
            corner_radius=6,
            fg_color=SURFACE,
            hover_color=SURFACE_2,
            text_color=MUTED,
            border_width=1,
            border_color=BORDER,
            font=(FONT, 12),
            command=self.open_reports_folder,
        ).grid(row=7, column=0, padx=12, pady=(0, 6), sticky="ew")
        ctk.CTkButton(
            self.sidebar,
            text="Sair",
            height=34,
            corner_radius=6,
            fg_color=SURFACE,
            hover_color=DANGER_DARK,
            text_color=DANGER,
            border_width=1,
            border_color="#3A1A1A",
            font=(FONT, 12),
            command=self._on_close,
        ).grid(row=8, column=0, padx=12, pady=(0, 14), sticky="ew")

        content = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        content.grid(row=0, column=1, sticky="nsew", padx=0, pady=0)
        content.grid_columnconfigure(0, weight=1)
        content.grid_rowconfigure(0, weight=1)

        shell = ctk.CTkFrame(content, fg_color=BG, corner_radius=0)
        shell.grid(row=0, column=0, sticky="nsew")
        shell.grid_columnconfigure(0, weight=1)
        shell.grid_rowconfigure(1, weight=1)

        nav = ctk.CTkFrame(shell, fg_color=BG, height=42, corner_radius=0)
        nav.grid(row=0, column=0, sticky="ew")
        nav.grid_propagate(False)
        nav.grid_columnconfigure(6, weight=1)
        self._nav_button(nav, 0, "Busca")
        self._nav_button(nav, 1, "Analisar vaga")
        self._nav_button(nav, 2, "Otimizar curriculo")
        self._nav_button(nav, 3, "Candidaturas")
        self._nav_button(nav, 4, "Mercado")
        self._nav_button(nav, 5, "Relatorios")
        ctk.CTkFrame(shell, fg_color=BORDER, height=1, corner_radius=0).grid(row=0, column=0, sticky="sew")

        tab_area = ctk.CTkFrame(shell, fg_color=BASE, corner_radius=0)
        tab_area.grid(row=1, column=0, sticky="nsew")
        tab_area.grid_columnconfigure(0, weight=1)
        tab_area.grid_rowconfigure(0, weight=1)

        search_tab = ctk.CTkFrame(tab_area, fg_color=BASE, corner_radius=0)
        analysis_tab = ctk.CTkFrame(tab_area, fg_color=BASE, corner_radius=0)
        optimization_tab = ctk.CTkFrame(tab_area, fg_color=BASE, corner_radius=0)
        tracker_tab = ctk.CTkFrame(tab_area, fg_color=BASE, corner_radius=0)
        trends_tab = ctk.CTkFrame(tab_area, fg_color=BASE, corner_radius=0)
        reports_tab = ctk.CTkFrame(tab_area, fg_color=BASE, corner_radius=0)
        self.tab_frames = {
            "Busca": search_tab,
            "Analisar vaga": analysis_tab,
            "Otimizar curriculo": optimization_tab,
            "Candidaturas": tracker_tab,
            "Mercado": trends_tab,
            "Relatorios": reports_tab,
        }

        main = search_tab
        main.configure(fg_color=BASE)
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(2, weight=1)

        header = ctk.CTkFrame(main, fg_color="transparent")
        header.grid(row=0, column=0, padx=26, pady=(26, 16), sticky="ew")
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            header,
            text="Painel de busca",
            font=(FONT, 20, "bold"),
            text_color=TEXT,
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            header,
            text="Configure a varredura, execute buscas pontuais e acompanhe os eventos importantes.",
            font=(FONT, 12),
            text_color=COLORS["text_muted"],
        ).grid(row=1, column=0, pady=(6, 0), sticky="w")

        settings = ctk.CTkFrame(main, fg_color=SURFACE, corner_radius=10, border_width=1, border_color=BORDER)
        settings.grid(row=1, column=0, padx=26, pady=(0, 16), sticky="ew")
        settings.grid_columnconfigure((0, 1, 2), weight=1)
        settings.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(settings, text="PARAMETROS DA VARREDURA", font=(FONT, 10, "bold"), text_color=MUTED).grid(
            row=0, column=0, columnspan=3, padx=18, pady=(14, 10), sticky="w"
        )
        ctk.CTkFrame(settings, height=1, fg_color=BORDER, corner_radius=0).grid(row=1, column=0, columnspan=3, padx=18, sticky="ew")
        self._number_field(settings, 0, "Vagas por varredura", self.max_jobs)
        self._number_field(settings, 1, "Score minimo", self.min_score)
        self._number_field(settings, 2, "Intervalo (min)", self.interval)

        actions = ctk.CTkFrame(settings, fg_color="transparent")
        actions.grid(row=3, column=0, columnspan=3, padx=18, pady=(4, 18), sticky="ew")
        actions.grid_columnconfigure((0, 1, 2, 3), weight=1)
        self._action_button(actions, 0, "Iniciar monitoramento", self.start_monitoring, primary=True)
        self._action_button(actions, 1, "Buscar agora", self.run_once)
        self._action_button(actions, 2, "Parar", self.stop_monitoring, danger=True)
        self._action_button(actions, 3, "E-mail teste", self.send_test_email)

        log_panel = ctk.CTkFrame(main, fg_color=SURFACE, corner_radius=10, border_width=1, border_color=BORDER)
        log_panel.grid(row=2, column=0, padx=26, pady=(0, 24), sticky="nsew")
        log_panel.grid_columnconfigure(0, weight=1)
        log_panel.grid_rowconfigure(1, weight=1)

        log_header = ctk.CTkFrame(log_panel, fg_color="transparent")
        log_header.grid(row=0, column=0, padx=18, pady=(16, 8), sticky="ew")
        log_header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(log_header, text="ATIVIDADE DA BUSCA", font=(FONT, 10, "bold"), text_color=MUTED).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(log_header, text="Eventos filtrados para mostrar apenas o que importa.", font=(FONT, 12), text_color=COLORS["text_muted"]).grid(row=1, column=0, sticky="w")
        ctk.CTkButton(
            log_header,
            text="Limpar",
            width=92,
            height=28,
            corner_radius=6,
            fg_color="transparent",
            hover_color=SURFACE_2,
            text_color=MUTED,
            border_width=1,
            border_color=COLORS["border_bright"],
            command=self._clear_log,
        ).grid(row=0, column=1, rowspan=2, sticky="e")

        self.log_box = ctk.CTkTextbox(
            log_panel,
            corner_radius=8,
            fg_color=BG,
            border_width=1,
            border_color=BORDER,
            text_color=TEXT,
            font=("Segoe UI", 12),
            wrap="word",
        )
        self.log_box.grid(row=1, column=0, padx=18, pady=(0, 18), sticky="nsew")
        self.log_box.insert("end", "Pronto. Configure a busca e clique em Iniciar monitoramento ou Buscar agora.\n")
        self.log_box.configure(state="disabled")

        self._build_analysis_tab(analysis_tab)
        self._build_optimization_tab(optimization_tab)
        self._build_tracker_tab(tracker_tab)
        self._build_trends_tab(trends_tab)
        self._build_reports_tab(reports_tab)
        self._show_tab("Busca")
        self._refresh_sidebar_status(self.status_text.get())

    def _nav_button(self, parent, column, name):
        cell = ctk.CTkFrame(parent, fg_color="transparent", corner_radius=0)
        cell.grid(row=0, column=column, padx=(20 if column == 0 else 0, 4), sticky="nsw")
        cell.grid_rowconfigure(0, weight=1)
        button = ctk.CTkButton(
            cell,
            text=name,
            height=40,
            width=150 if name == "Otimizar curriculo" else 122 if name == "Analisar vaga" else 118 if name == "Candidaturas" else 88 if name in {"Relatorios", "Mercado"} else 74,
            corner_radius=0,
            fg_color="transparent",
            hover_color=SURFACE,
            text_color=COLORS["text_muted"],
            border_width=0,
            font=(FONT, 12),
            command=lambda: self._show_tab(name),
        )
        button.grid(row=0, column=0, sticky="nsew")
        indicator = ctk.CTkFrame(cell, height=2, fg_color=ACCENT, corner_radius=0)
        indicator.grid(row=1, column=0, sticky="ew")
        indicator.grid_remove()
        self.nav_buttons[name] = button
        self.nav_indicators[name] = indicator

    def _show_tab(self, name):
        for frame in self.tab_frames.values():
            frame.grid_forget()
        self.tab_frames[name].grid(row=0, column=0, sticky="nsew")
        if name == "Relatorios":
            self.refresh_reports()
        if name == "Candidaturas":
            self.refresh_tracker()
        if name == "Mercado":
            self.refresh_trends_tab()
        self.current_tab = name

        for tab_name, button in self.nav_buttons.items():
            if tab_name == name:
                button.configure(
                    fg_color="transparent",
                    hover_color=SURFACE,
                    text_color=ACCENT,
                )
                self.nav_indicators[tab_name].grid()
            else:
                button.configure(
                    fg_color="transparent",
                    hover_color=SURFACE,
                    text_color=COLORS["text_muted"],
                )
                self.nav_indicators[tab_name].grid_remove()
        self._refresh_sidebar_context()

    def _build_analysis_tab(self, parent):
        parent.configure(fg_color=BASE)
        parent.grid_columnconfigure(0, weight=6)
        parent.grid_columnconfigure(1, weight=5)
        parent.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(parent, fg_color="transparent")
        header.grid(row=0, column=0, columnspan=2, padx=26, pady=(26, 16), sticky="ew")
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            header,
            text="Analisar vaga",
            font=(FONT, 20, "bold"),
            text_color=TEXT,
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            header,
            textvariable=self.analysis_status,
            font=("Segoe UI", 13),
            text_color=MUTED,
        ).grid(row=1, column=0, pady=(6, 0), sticky="w")

        form = ctk.CTkFrame(parent, fg_color=SURFACE, corner_radius=10, border_width=1, border_color=BORDER)
        form.grid(row=1, column=0, padx=(26, 10), pady=(0, 24), sticky="nsew")
        form.grid_columnconfigure((0, 1), weight=1)
        form.grid_rowconfigure(3, weight=1)

        ctk.CTkLabel(
            form,
            text="DADOS DA VAGA",
            font=("Segoe UI", 17, "bold"),
            text_color=TEXT,
        ).grid(row=0, column=0, columnspan=2, padx=18, pady=(18, 2), sticky="w")
        ctk.CTkLabel(
            form,
            text="Cole a descricao completa. Titulo e empresa ajudam, mas sao opcionais.",
            font=("Segoe UI", 12),
            text_color=MUTED,
        ).grid(row=1, column=0, columnspan=2, padx=18, pady=(0, 12), sticky="w")

        self._text_field(form, 2, 0, "Titulo da vaga", self.analysis_title)
        self._text_field(form, 2, 1, "Empresa", self.analysis_company)

        desc_frame = ctk.CTkFrame(form, fg_color="transparent")
        desc_frame.grid(row=3, column=0, columnspan=2, padx=18, pady=(0, 14), sticky="nsew")
        desc_frame.grid_columnconfigure(0, weight=1)
        desc_frame.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(desc_frame, text="Descricao da vaga", text_color=C["text_muted"], font=(FONT, 11)).grid(row=0, column=0, sticky="w")
        self.analysis_description = ctk.CTkTextbox(
            desc_frame,
            height=320,
            corner_radius=6,
            fg_color=SURFACE_2,
            border_width=1,
            border_color=BORDER,
            text_color=TEXT,
            font=("Segoe UI", 12),
            wrap="word",
        )
        self.analysis_description.grid(row=1, column=0, sticky="nsew", pady=(6, 0))

        actions = ctk.CTkFrame(form, fg_color="transparent")
        actions.grid(row=4, column=0, columnspan=2, padx=18, pady=(0, 18), sticky="ew")
        actions.grid_columnconfigure((0, 1, 2, 3, 4, 5, 6), weight=1)
        self.analyze_button = ctk.CTkButton(
            actions,
            text="Analisar compatibilidade",
            height=36,
            corner_radius=6,
            fg_color=ACCENT,
            hover_color=ACCENT_DIM,
            text_color=BG,
            font=(FONT, 12, "bold"),
            command=self.analyze_single_job,
        )
        self.analyze_button.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.ats_button = ctk.CTkButton(
            actions,
            text="Simular ATS",
            height=36,
            corner_radius=6,
            fg_color="transparent",
            hover_color=COLORS["amber_subtle"],
            text_color=ACCENT,
            border_width=1,
            border_color=ACCENT_DIM,
            font=(FONT, 12),
            command=self.simulate_ats,
        )
        self.ats_button.grid(row=0, column=1, sticky="ew", padx=(0, 8))
        self.cover_letter_button = ctk.CTkButton(
            actions,
            text="Gerar carta",
            height=36,
            corner_radius=6,
            fg_color="transparent",
            hover_color=COLORS["amber_subtle"],
            text_color=ACCENT,
            border_width=1,
            border_color=ACCENT_DIM,
            font=(FONT, 12),
            command=self.generate_cover_letter,
        )
        self.cover_letter_button.grid(row=0, column=2, sticky="ew", padx=(0, 8))
        self.register_application_button = ctk.CTkButton(
            actions,
            text="Registrar",
            height=36,
            corner_radius=6,
            fg_color="transparent",
            hover_color=SURFACE_2,
            text_color=MUTED,
            border_width=1,
            border_color=COLORS["border_bright"],
            font=(FONT, 12),
            state="disabled",
            command=self.register_last_application,
        )
        self.register_application_button.grid(row=0, column=3, sticky="ew", padx=(0, 8))
        ctk.CTkButton(
            actions,
            text="Copiar analise",
            height=36,
            corner_radius=6,
            fg_color="transparent",
            hover_color=SURFACE_2,
            text_color=MUTED,
            border_width=1,
            border_color=COLORS["border_bright"],
            font=(FONT, 12),
            command=self.copy_analysis,
        ).grid(row=0, column=4, sticky="ew", padx=(0, 8))
        self.analysis_optimize_button = ctk.CTkButton(
            actions,
            text="Otimizar esta vaga",
            height=36,
            corner_radius=6,
            fg_color="transparent",
            hover_color=SURFACE_2,
            text_color=MUTED,
            border_width=1,
            border_color=COLORS["border_bright"],
            font=(FONT, 12),
            state="disabled",
            command=self.use_last_analyzed_job,
        )
        self.analysis_optimize_button.grid(row=0, column=5, sticky="ew", padx=(0, 8))
        ctk.CTkButton(
            actions,
            text="Limpar",
            height=38,
            corner_radius=8,
            fg_color=SURFACE,
            hover_color=SURFACE_2,
            text_color=TEXT,
            border_width=1,
            border_color=SURFACE_2,
            command=self.clear_analysis,
        ).grid(row=0, column=6, sticky="ew")

        result_panel = ctk.CTkFrame(parent, fg_color=SURFACE, corner_radius=10, border_width=1, border_color=BORDER)
        result_panel.grid(row=1, column=1, padx=(10, 26), pady=(0, 24), sticky="nsew")
        result_panel.grid_columnconfigure(0, weight=1)
        result_panel.grid_rowconfigure(1, weight=1)
        result_header = ctk.CTkFrame(result_panel, fg_color="transparent")
        result_header.grid(row=0, column=0, padx=18, pady=(18, 8), sticky="ew")
        result_header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            result_header,
            text="RESULTADO",
            font=(FONT, 10, "bold"),
            text_color=MUTED,
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            result_header,
            text="Diagnostico, nao geracao de curriculo.",
            font=("Segoe UI", 12),
            text_color=MUTED,
        ).grid(row=1, column=0, sticky="w")

        self.analysis_result_box = ctk.CTkTextbox(
            result_panel,
            corner_radius=8,
            fg_color=BG,
            border_width=1,
            border_color=BORDER,
            text_color=TEXT,
            font=("Segoe UI", 12),
            wrap="word",
        )
        self.analysis_result_box.grid(row=1, column=0, padx=18, pady=(0, 18), sticky="nsew")
        self.analysis_result_box.insert(
            "end",
            "A analise vai aparecer aqui.\n\n"
            "O app vai mostrar compatibilidade, pontos fortes, gaps e melhorias recomendadas para o curriculo atual.\n",
        )
        self.analysis_result_box.configure(state="disabled")

    def _build_optimization_tab(self, parent):
        parent.configure(fg_color=BASE)
        parent.grid_columnconfigure(0, weight=3, minsize=520)
        parent.grid_columnconfigure(1, weight=2, minsize=320)
        parent.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(parent, fg_color="transparent")
        header.grid(row=0, column=0, columnspan=2, padx=26, pady=(26, 16), sticky="ew")
        header.grid_columnconfigure(0, weight=1)
        header.grid_columnconfigure(1, weight=0)
        ctk.CTkLabel(
            header,
            text="Otimizar curriculo",
            font=(FONT, 20, "bold"),
            text_color=TEXT,
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            header,
            textvariable=self.optimization_status,
            font=(FONT, 12),
            text_color=MUTED,
        ).grid(row=1, column=0, pady=(6, 0), sticky="w")
        ctk.CTkButton(
            header,
            text="Usar vaga analisada",
            height=38,
            width=240,
            corner_radius=8,
            fg_color=SURFACE,
            hover_color=SURFACE_2,
            text_color=TEXT,
            border_width=1,
            border_color=C["border_bright"],
            font=("Segoe UI", 12, "bold"),
            command=self.use_last_analyzed_job,
        ).grid(row=0, column=1, rowspan=2, padx=(20, 0), sticky="e")

        form = ctk.CTkFrame(parent, fg_color=SURFACE, corner_radius=10, border_width=1, border_color=BORDER)
        form.grid(row=1, column=0, padx=(26, 10), pady=(0, 24), sticky="nsew")
        form.grid_columnconfigure((0, 1), weight=1)
        form.grid_rowconfigure(2, weight=1, minsize=170)

        form_header = ctk.CTkFrame(form, fg_color="transparent")
        form_header.grid(row=0, column=0, columnspan=2, padx=18, pady=(18, 10), sticky="ew")
        form_header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            form_header,
            text="VAGA ALVO",
            font=(FONT, 10, "bold"),
            text_color=MUTED,
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            form_header,
            text="Use a ultima vaga analisada ou cole uma descricao nova para direcionar o curriculo.",
            font=(FONT, 12),
            text_color=COLORS["text_muted"],
            justify="left",
        ).grid(row=1, column=0, columnspan=2, pady=(5, 0), sticky="w")

        self._text_field(form, 1, 0, "Titulo da vaga", self.optimization_title)
        self._text_field(form, 1, 1, "Empresa", self.optimization_company)

        desc_frame = ctk.CTkFrame(form, fg_color="transparent")
        desc_frame.grid(row=2, column=0, columnspan=2, padx=18, pady=(0, 14), sticky="nsew")
        desc_frame.grid_columnconfigure(0, weight=1)
        desc_frame.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(desc_frame, text="Descricao da vaga", text_color=COLORS["text_muted"], font=(FONT, 11)).grid(row=0, column=0, sticky="w")
        self.optimization_description = ctk.CTkTextbox(
            desc_frame,
            height=260,
            corner_radius=6,
            fg_color=SURFACE_2,
            border_width=1,
            border_color=COLORS["border_bright"],
            text_color=MUTED,
            font=("Consolas", 11),
            wrap="word",
        )
        self.optimization_description.grid(row=1, column=0, sticky="nsew", pady=(6, 0))

        actions = ctk.CTkFrame(form, fg_color="transparent")
        actions.grid(row=3, column=0, columnspan=2, padx=18, pady=(0, 18), sticky="ew")
        actions.grid_columnconfigure((0, 1, 2), weight=1)
        self.optimize_button = ctk.CTkButton(
            actions,
            text="Gerar otimizacao",
            height=38,
            corner_radius=8,
            fg_color=ACCENT,
            hover_color=ACCENT_DIM,
            text_color=BG,
            command=self.optimize_resume,
        )
        self.optimize_button.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        ctk.CTkButton(
            actions,
            text="Copiar otimizacao",
            height=38,
            corner_radius=8,
            fg_color=SURFACE,
            hover_color=SURFACE_2,
            text_color=TEXT,
            border_width=1,
            border_color=SURFACE_2,
            command=self.copy_optimization,
        ).grid(row=0, column=1, sticky="ew", padx=(0, 8))
        ctk.CTkButton(
            actions,
            text="Limpar",
            height=36,
            corner_radius=6,
            fg_color="transparent",
            hover_color=SURFACE_2,
            text_color=MUTED,
            border_width=1,
            border_color=COLORS["border_bright"],
            font=(FONT, 12),
            command=self.clear_optimization,
        ).grid(row=0, column=2, sticky="ew")

        result_panel = ctk.CTkFrame(parent, fg_color=SURFACE, corner_radius=10, border_width=1, border_color=BORDER)
        result_panel.grid(row=1, column=1, padx=(10, 26), pady=(0, 24), sticky="nsew")
        result_panel.grid_columnconfigure(0, weight=1)
        result_panel.grid_rowconfigure(1, weight=1)
        result_header = ctk.CTkFrame(result_panel, fg_color="transparent")
        result_header.grid(row=0, column=0, padx=18, pady=(18, 8), sticky="ew")
        result_header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            result_header,
            text="CURRICULO DIRECIONADO",
            font=(FONT, 10, "bold"),
            text_color=TEXT,
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            result_header,
            text="Sugestoes editaveis, baseadas no que ja existe no perfil.",
            font=(FONT, 12),
            text_color=MUTED,
        ).grid(row=1, column=0, sticky="w")

        self.optimization_result_box = ctk.CTkTextbox(
            result_panel,
            corner_radius=8,
            fg_color=BG,
            border_width=1,
            border_color=BORDER,
            text_color=MUTED,
            font=(FONT, 12),
            wrap="word",
        )
        self.optimization_result_box.grid(row=1, column=0, padx=18, pady=(0, 18), sticky="nsew")
        self.optimization_result_box.insert(
            "end",
            "A otimizacao vai aparecer aqui.\n\n"
            "O app vai sugerir headline, resumo, skills, bullets e alertas de honestidade.\n",
        )
        self.optimization_result_box.configure(state="disabled")

    def _build_tracker_tab(self, parent):
        parent.configure(fg_color=BASE)
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_columnconfigure(1, weight=0, minsize=320)
        parent.grid_rowconfigure(2, weight=1)

        header = ctk.CTkFrame(parent, fg_color="transparent")
        header.grid(row=0, column=0, columnspan=2, padx=26, pady=(26, 16), sticky="ew")
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            header,
            text="Candidaturas",
            font=(FONT, 20, "bold"),
            text_color=TEXT,
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            header,
            text="Acompanhe o funil, mova vagas entre etapas e registre proximas acoes.",
            font=(FONT, 12),
            text_color=C["text_muted"],
        ).grid(row=1, column=0, pady=(6, 0), sticky="w")
        ctk.CTkButton(
            header,
            text="Atualizar",
            width=110,
            height=36,
            corner_radius=6,
            fg_color="transparent",
            hover_color=SURFACE_2,
            text_color=MUTED,
            border_width=1,
            border_color=C["border_bright"],
            font=(FONT, 12),
            command=self.refresh_tracker,
        ).grid(row=0, column=1, rowspan=2, sticky="e")

        self.tracker_metrics = ctk.CTkFrame(parent, fg_color="transparent")
        self.tracker_metrics.grid(row=1, column=0, columnspan=2, padx=26, pady=(0, 14), sticky="ew")
        self.tracker_metrics.grid_columnconfigure((0, 1, 2, 3), weight=1)

        self.tracker_board = ctk.CTkFrame(parent, fg_color="transparent")
        self.tracker_board.grid(row=2, column=0, padx=(26, 10), pady=(0, 24), sticky="nsew")
        self.tracker_board.grid_columnconfigure(tuple(range(len(STATUS_ORDER))), weight=1)
        self.tracker_board.grid_rowconfigure(1, weight=1)
        self.tracker_columns = {}
        for index, status in enumerate(STATUS_ORDER):
            ctk.CTkLabel(
                self.tracker_board,
                text=STATUS_LABELS[status],
                font=(FONT, 10, "bold"),
                text_color=C["text_muted"],
            ).grid(row=0, column=index, sticky="w", padx=(0 if index == 0 else 8, 0), pady=(0, 8))
            column = ctk.CTkScrollableFrame(
                self.tracker_board,
                fg_color=SURFACE,
                corner_radius=8,
                border_width=1,
                border_color=BORDER,
                scrollbar_button_color=C["border"],
                scrollbar_button_hover_color=C["border_bright"],
            )
            column.grid(row=1, column=index, sticky="nsew", padx=(0 if index == 0 else 8, 0))
            self.tracker_columns[status] = column

        self.tracker_detail = ctk.CTkFrame(parent, fg_color=SURFACE, corner_radius=10, border_width=1, border_color=BORDER)
        self.tracker_detail.grid(row=2, column=1, padx=(10, 26), pady=(0, 24), sticky="nsew")
        self.tracker_detail.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            self.tracker_detail,
            text="Detalhes",
            font=(FONT, 10, "bold"),
            text_color=MUTED,
        ).grid(row=0, column=0, padx=18, pady=(18, 4), sticky="w")
        self.tracker_detail_title = ctk.CTkLabel(
            self.tracker_detail,
            text="Selecione uma candidatura.",
            font=(FONT, 13),
            text_color=MUTED,
            wraplength=280,
            justify="left",
        )
        self.tracker_detail_title.grid(row=1, column=0, padx=18, pady=(0, 12), sticky="ew")

        self.tracker_contact = tk.StringVar()
        self.tracker_next_action = tk.StringVar()
        self._tracker_entry("Contato", self.tracker_contact, 2)
        self._tracker_entry("Proxima acao", self.tracker_next_action, 3)
        ctk.CTkLabel(self.tracker_detail, text="Notas", text_color=C["text_muted"], font=(FONT, 11)).grid(row=4, column=0, padx=18, sticky="w")
        self.tracker_notes = ctk.CTkTextbox(
            self.tracker_detail,
            height=120,
            corner_radius=6,
            fg_color=SURFACE_2,
            border_width=1,
            border_color=C["border_bright"],
            text_color=TEXT,
            font=(FONT, 12),
            wrap="word",
        )
        self.tracker_notes.grid(row=5, column=0, padx=18, pady=(6, 12), sticky="ew")

        ctk.CTkButton(
            self.tracker_detail,
            text="Salvar detalhes",
            height=36,
            corner_radius=6,
            fg_color=ACCENT,
            hover_color=ACCENT_DIM,
            text_color=BG,
            font=(FONT, 12, "bold"),
            command=self.save_tracker_details,
        ).grid(row=6, column=0, padx=18, pady=(0, 12), sticky="ew")

        self.tracker_move_frame = ctk.CTkFrame(self.tracker_detail, fg_color="transparent")
        self.tracker_move_frame.grid(row=7, column=0, padx=18, pady=(0, 18), sticky="ew")
        self.tracker_move_frame.grid_columnconfigure(0, weight=1)
        self.refresh_tracker()

    def _tracker_entry(self, label, variable, row):
        frame = ctk.CTkFrame(self.tracker_detail, fg_color="transparent")
        frame.grid(row=row, column=0, padx=18, pady=(0, 10), sticky="ew")
        frame.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(frame, text=label, text_color=C["text_muted"], font=(FONT, 11)).grid(row=0, column=0, sticky="w")
        ctk.CTkEntry(
            frame,
            textvariable=variable,
            height=36,
            corner_radius=6,
            fg_color=SURFACE_2,
            border_width=1,
            border_color=C["border_bright"],
            text_color=TEXT,
            font=(FONT, 13),
        ).grid(row=1, column=0, sticky="ew", pady=(6, 0))

    def _build_trends_tab(self, parent):
        parent.configure(fg_color=BASE)
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(2, weight=1)

        header = ctk.CTkFrame(parent, fg_color="transparent")
        header.grid(row=0, column=0, padx=26, pady=(26, 16), sticky="ew")
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            header,
            text="Mercado",
            font=(FONT, 20, "bold"),
            text_color=TEXT,
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            header,
            textvariable=self.market_status,
            font=(FONT, 12),
            text_color=C["text_muted"],
        ).grid(row=1, column=0, pady=(6, 0), sticky="w")
        self.market_button = ctk.CTkButton(
            header,
            text="Gerar relatorio de mercado",
            height=36,
            corner_radius=6,
            fg_color=ACCENT,
            hover_color=ACCENT_DIM,
            text_color=BG,
            font=(FONT, 12, "bold"),
            command=self.generate_market_trends,
        )
        self.market_button.grid(row=0, column=1, rowspan=2, sticky="e")

        market_wrap = ctk.CTkFrame(parent, fg_color="transparent")
        market_wrap.grid(row=1, column=0, padx=26, pady=(0, 16), sticky="ew")
        market_wrap.grid_columnconfigure(1, weight=1)
        ctk.CTkFrame(market_wrap, width=2, fg_color=ACCENT, corner_radius=0).grid(row=0, column=0, sticky="ns")

        summary = ctk.CTkFrame(market_wrap, fg_color=SURFACE, corner_radius=8, border_width=1, border_color=BORDER)
        summary.grid(row=0, column=1, sticky="ew")
        summary.grid_columnconfigure(0, weight=1)
        self.market_new_jobs = tk.StringVar(value="Vagas novas para tendencias: -")
        ctk.CTkLabel(summary, text="TOTAL DE VAGAS COLETADAS", text_color=C["text_muted"], font=(FONT, 11)).grid(
            row=0, column=0, padx=16, pady=(14, 2), sticky="w"
        )
        self.market_total_label = ctk.CTkLabel(summary, text="Historico local", text_color=TEXT, font=(FONT, 20, "bold"))
        self.market_total_label.grid(row=1, column=0, padx=16, pady=(0, 14), sticky="w")
        self.market_badge = ctk.CTkLabel(
            summary,
            text="- novas",
            fg_color=C["amber_subtle"],
            text_color=ACCENT,
            corner_radius=4,
            font=(FONT, 10, "bold"),
        )
        self.market_badge.grid(row=0, column=1, rowspan=2, padx=16, pady=14, sticky="e")

        log_panel = ctk.CTkFrame(parent, fg_color=SURFACE, corner_radius=10, border_width=1, border_color=BORDER)
        log_panel.grid(row=2, column=0, padx=26, pady=(0, 24), sticky="nsew")
        log_panel.grid_columnconfigure(0, weight=1)
        log_panel.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(log_panel, text="PROGRESSO", text_color=MUTED, font=(FONT, 10, "bold")).grid(
            row=0, column=0, padx=18, pady=(18, 8), sticky="w"
        )
        self.market_log = ctk.CTkTextbox(
            log_panel,
            corner_radius=8,
            fg_color=BG,
            border_width=1,
            border_color=BORDER,
            text_color=MUTED,
            font=("Consolas", 11),
            wrap="word",
        )
        self.market_log.grid(row=1, column=0, padx=18, pady=(0, 18), sticky="nsew")
        self.market_log.insert("end", "Aguardando geracao de relatorio.\n")
        self.market_log.configure(state="disabled")
        self.refresh_trends_tab()

    def _build_reports_tab(self, parent):
        parent.configure(fg_color=BASE)
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(parent, fg_color="transparent")
        header.grid(row=0, column=0, padx=26, pady=(26, 16), sticky="ew")
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            header,
            text="Relatorios",
            font=(FONT, 20, "bold"),
            text_color=TEXT,
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            header,
            text="Historico local das varreduras, analises manuais e otimizacoes de curriculo.",
            font=(FONT, 12),
            text_color=C["text_muted"],
        ).grid(row=1, column=0, pady=(6, 0), sticky="w")
        ctk.CTkButton(
            header,
            text="Atualizar",
            width=110,
            height=34,
            corner_radius=6,
            fg_color="transparent",
            hover_color=SURFACE_2,
            text_color=MUTED,
            border_width=1,
            border_color=C["border_bright"],
            font=(FONT, 12),
            command=self.refresh_reports,
        ).grid(row=0, column=1, rowspan=2, sticky="e")

        panel = ctk.CTkFrame(parent, fg_color=SURFACE, corner_radius=10, border_width=1, border_color=BORDER)
        panel.grid(row=1, column=0, padx=26, pady=(0, 24), sticky="nsew")
        panel.grid_columnconfigure(0, weight=1)
        panel.grid_rowconfigure(0, weight=1)

        self.reports_list = ctk.CTkScrollableFrame(
            panel,
            fg_color="transparent",
            scrollbar_button_color=C["border"],
            scrollbar_button_hover_color=C["border_bright"],
        )
        self.reports_list.grid(row=0, column=0, padx=18, pady=18, sticky="nsew")
        self.reports_list.grid_columnconfigure(0, weight=1)

    def _text_field(self, parent, row, column, label, variable):
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.grid(row=row, column=column, padx=14, pady=(10, 14), sticky="ew")
        frame.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(frame, text=label, text_color=COLORS["text_muted"], font=(FONT, 11)).grid(row=0, column=0, sticky="w")
        ctk.CTkEntry(
            frame,
            textvariable=variable,
            height=36,
            corner_radius=6,
            fg_color=SURFACE_2,
            border_width=1,
            border_color=COLORS["border_bright"],
            text_color=TEXT,
            placeholder_text_color=COLORS["text_muted"],
            font=(FONT, 13),
        ).grid(row=1, column=0, sticky="ew", pady=(6, 0))

    def open_setup_window(self):
        data = load_user_config()
        window = ctk.CTkToplevel(self)
        window.title("Configurar Job Matcher")
        window.configure(fg_color=BASE)
        window.geometry("720x600")
        window.minsize(720, 600)
        window.transient(self)
        window.grab_set()
        self._set_setup_window_style(window)
        window.after(100, lambda: self._set_setup_window_style(window))

        window.grid_columnconfigure(0, weight=1)
        window.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(window, fg_color=BG, corner_radius=0)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(0, weight=1)

        title_block = ctk.CTkFrame(header, fg_color="transparent")
        title_block.grid(row=0, column=0, padx=18, pady=14, sticky="w")
        ctk.CTkLabel(
            title_block,
            text="Configuracao do usuario",
            font=(FONT, 15, "bold"),
            text_color=TEXT,
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            title_block,
            text=f"Arquivo local: {get_config_path()}",
            font=(FONT, 10),
            text_color=COLORS["text_muted"],
        ).grid(row=1, column=0, sticky="w", pady=(3, 0))

        body = ctk.CTkScrollableFrame(window, fg_color=BASE, scrollbar_button_color=COLORS["border_bright"], scrollbar_fg_color=BORDER)
        body.grid(row=1, column=0, sticky="nsew", padx=18, pady=18)
        body.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(body, text="Configuração do usuário", font=("Segoe UI", 22, "bold"), text_color=TEXT).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            body,
            text=f"Arquivo local: {get_config_path()}",
            font=("Segoe UI", 11),
            text_color=MUTED,
        ).grid(row=1, column=0, sticky="w", pady=(2, 14))

        for child in body.winfo_children():
            child.destroy()

        fields = {}
        row = 0

        def add_entry(key, label, secret=False):
            nonlocal row
            frame = ctk.CTkFrame(body, fg_color="transparent")
            frame.grid(row=row, column=0, sticky="ew", pady=(0, 10))
            frame.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(frame, text=label, text_color=MUTED, font=("Segoe UI", 12)).grid(row=0, column=0, sticky="w")
            var = tk.StringVar(value=str(data.get(key, "")))
            fields[key] = var
            ctk.CTkEntry(
                frame,
                textvariable=var,
                show="*" if secret else "",
                height=36,
                corner_radius=7,
                fg_color=BASE,
                border_color=BORDER,
                text_color=TEXT,
            ).grid(row=1, column=0, sticky="ew", pady=(4, 0))
            row += 1

        ctk.CTkLabel(body, text="Credenciais", font=("Segoe UI", 16, "bold"), text_color=TEXT).grid(row=row, column=0, sticky="w", pady=(0, 8))
        row += 1
        add_entry("groq_api_key", "API da IA", secret=True)
        add_entry("groq_model", "Modelo da IA")
        if not fields["groq_model"].get():
            fields["groq_model"].set("llama-3.3-70b-versatile")
        add_entry("serper_api_key", "API Serper", secret=True)
        add_entry("email_remetente", "Gmail remetente")
        add_entry("email_senha_app", "Senha de app do Gmail", secret=True)
        add_entry("email_destinatario", "E-mail que recebera os matches")

        test_status = tk.StringVar(value="Teste cada servico quando quiser validar a configuracao.")

        def run_config_test(kind):
            def worker():
                try:
                    if kind == "ia":
                        key = fields["groq_api_key"].get().strip()
                        model = fields["groq_model"].get().strip() or "llama-3.3-70b-versatile"
                        if not key:
                            raise ValueError("Informe a API da IA antes de testar.")
                        from groq import Groq
                        client = Groq(api_key=key)
                        client.chat.completions.create(
                            model=model,
                            messages=[{"role": "user", "content": "Responda apenas OK."}],
                            temperature=0,
                            max_tokens=8,
                        )
                        message = "IA funcionando."
                    elif kind == "serper":
                        key = fields["serper_api_key"].get().strip()
                        if not key:
                            raise ValueError("Informe a API Serper antes de testar.")
                        response = requests.post(
                            "https://google.serper.dev/search",
                            headers={"X-API-KEY": key, "Content-Type": "application/json"},
                            json={"q": "site:linkedin.com/jobs Java developer", "num": 1},
                            timeout=20,
                        )
                        if response.status_code >= 400:
                            raise ValueError(f"Serper retornou HTTP {response.status_code}.")
                        message = "Serper funcionando."
                    else:
                        sender = fields["email_remetente"].get().strip()
                        password = fields["email_senha_app"].get().strip()
                        if not sender or not password:
                            raise ValueError("Informe Gmail remetente e senha de app antes de testar.")
                        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=20) as smtp:
                            smtp.login(sender, password)
                        message = "Gmail funcionando."
                    self.after(0, test_status.set, message)
                    self.after(0, messagebox.showinfo, "Job Matcher", message)
                except Exception as exc:
                    error = f"Teste falhou: {exc}"
                    self.after(0, test_status.set, error)
                    self.after(0, messagebox.showerror, "Job Matcher", error)

            test_status.set("Testando, aguarde...")
            threading.Thread(target=worker, daemon=True).start()

        test_panel = ctk.CTkFrame(body, fg_color=BASE, corner_radius=10, border_width=1, border_color=BORDER)
        test_panel.grid(row=row, column=0, sticky="ew", pady=(0, 12))
        test_panel.grid_columnconfigure((0, 1, 2), weight=1)
        ctk.CTkLabel(
            test_panel,
            text="Testes rapidos",
            text_color=TEXT,
            font=("Segoe UI", 14, "bold"),
        ).grid(row=0, column=0, columnspan=3, padx=14, pady=(12, 2), sticky="w")
        ctk.CTkLabel(
            test_panel,
            textvariable=test_status,
            text_color=MUTED,
            font=("Segoe UI", 12),
        ).grid(row=1, column=0, columnspan=3, padx=14, pady=(0, 10), sticky="w")
        for col, (label, kind) in enumerate((("Testar IA", "ia"), ("Testar Serper", "serper"), ("Testar Gmail", "gmail"))):
            ctk.CTkButton(
                test_panel,
                text=label,
                height=36,
                corner_radius=8,
                fg_color=SURFACE,
                hover_color=SURFACE_2,
                text_color=TEXT,
                border_width=1,
                border_color=BORDER,
                command=lambda selected=kind: run_config_test(selected),
            ).grid(row=2, column=col, padx=(14 if col == 0 else 6, 14 if col == 2 else 6), pady=(0, 14), sticky="ew")
        row += 1

        ctk.CTkLabel(body, text="Busca", font=("Segoe UI", 16, "bold"), text_color=TEXT).grid(row=row, column=0, sticky="w", pady=(8, 8))
        row += 1
        add_entry("location", "Pais/regiao principal da busca")
        if not fields["location"].get():
            fields["location"].set("Brasil")

        path_vars = {
            "profile_text_path": tk.StringVar(value=str(data.get("profile_text_path", ""))),
            "resume_pdf_path": tk.StringVar(value=str(data.get("resume_pdf_path", ""))),
        }

        def add_file_picker(key, label, filetypes, target_name):
            nonlocal row
            frame = ctk.CTkFrame(body, fg_color="transparent")
            frame.grid(row=row, column=0, sticky="ew", pady=(0, 10))
            frame.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(frame, text=label, text_color=MUTED, font=("Segoe UI", 12)).grid(row=0, column=0, columnspan=2, sticky="w")
            ctk.CTkEntry(
                frame,
                textvariable=path_vars[key],
                height=36,
                corner_radius=7,
                fg_color=BASE,
                border_color=BORDER,
                text_color=TEXT,
            ).grid(row=1, column=0, sticky="ew", pady=(4, 0), padx=(0, 8))

            def choose_file():
                selected = filedialog.askopenfilename(parent=window, filetypes=filetypes)
                if selected:
                    try:
                        path_vars[key].set(import_user_file(selected, target_name))
                    except Exception as exc:
                        messagebox.showerror("Job Matcher", f"Nao foi possivel importar o arquivo:\n{exc}")

            ctk.CTkButton(
                frame,
                text="Selecionar",
                width=110,
                height=36,
                corner_radius=7,
                fg_color=SURFACE,
                hover_color=SURFACE_2,
                text_color=TEXT,
                command=choose_file,
            ).grid(row=1, column=1, pady=(4, 0))
            row += 1

        ctk.CTkLabel(body, text="Perfil e curriculo", font=("Segoe UI", 16, "bold"), text_color=TEXT).grid(row=row, column=0, sticky="w", pady=(8, 8))
        row += 1
        add_file_picker("profile_text_path", "Arquivo TXT com tudo que o usuario sabe sobre si", [("Texto", "*.txt"), ("Todos", "*.*")], "perfil.txt")
        add_file_picker("resume_pdf_path", "Curriculo em PDF", [("PDF", "*.pdf"), ("Todos", "*.*")], "curriculo.pdf")

        multiline_boxes = {}

        def add_list_box(key, label, default_attr, height=96, help_text=None):
            nonlocal row
            frame = ctk.CTkFrame(body, fg_color="transparent")
            frame.grid(row=row, column=0, sticky="ew", pady=(0, 10))
            frame.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(frame, text=label, text_color=MUTED, font=("Segoe UI", 12)).grid(row=0, column=0, sticky="w")
            if help_text:
                ctk.CTkLabel(
                    frame,
                    text=help_text,
                    text_color=MUTED,
                    font=("Segoe UI", 11),
                ).grid(row=1, column=0, sticky="w", pady=(2, 0))
            box = ctk.CTkTextbox(
                frame,
                height=height,
                corner_radius=7,
                fg_color=BASE,
                border_color=BORDER,
                text_color=TEXT,
            )
            box.grid(row=2 if help_text else 1, column=0, sticky="ew", pady=(4, 0))
            values = data.get(key) or getattr(engine.settings, default_attr, [])
            box.insert("1.0", "\n".join(values))
            multiline_boxes[key] = box
            row += 1

        ctk.CTkLabel(body, text="Termos e filtros", font=("Segoe UI", 16, "bold"), text_color=TEXT).grid(row=row, column=0, sticky="w", pady=(8, 8))
        row += 1
        add_list_box("search_base_terms", "Areas, cargos ou stacks principais", "SEARCH_BASE_TERMS")
        add_list_box("search_seniority_terms", "Senioridade desejada", "SEARCH_SENIORITY_TERMS")
        add_list_box("search_work_modes", "Modalidade de trabalho", "SEARCH_WORK_MODES")
        add_list_box("job_location_filters", "Filtros de localizacao aceitos", "JOB_LOCATION_FILTERS")
        add_list_box(
            "target_companies",
            "Empresas alvo opcionais",
            "TARGET_COMPANIES",
            height=72,
            help_text="Deixe vazio para verificar vagas de todas as empresas.",
        )
        add_list_box("search_queries", "Queries manuais extras", "SEARCH_QUERIES", height=120)

        def save_setup():
            payload = {key: var.get().strip() for key, var in fields.items()}
            payload["profile_text_path"] = path_vars["profile_text_path"].get().strip()
            payload["resume_pdf_path"] = path_vars["resume_pdf_path"].get().strip()
            for key, box in multiline_boxes.items():
                payload[key] = [line.strip() for line in box.get("1.0", "end").splitlines() if line.strip()]
            payload["min_score"] = self._parse_int(self.min_score, 90, 1, 100)
            payload["scan_interval_minutes"] = self._parse_int(self.interval, 60, 1, 720)
            payload["max_jobs_to_analyze_per_scan"] = self._parse_int(self.max_jobs, 25, 1, 200)
            save_user_config(payload)
            engine.refresh_runtime_settings()
            logging.info("Configuracao salva. O Job Matcher ja pode usar os dados do usuario.")
            messagebox.showinfo("Job Matcher", "Configuracao salva com sucesso.")
            window.destroy()

        actions = ctk.CTkFrame(header, fg_color="transparent")
        actions.grid(row=0, column=1, padx=18, pady=14, sticky="e")
        ctk.CTkButton(
            actions,
            text="Salvar configuracao",
            width=180,
            height=42,
            corner_radius=8,
            fg_color=ACCENT,
            hover_color=ACCENT_DIM,
            text_color=BG,
            font=("Segoe UI", 12, "bold"),
            command=save_setup,
        ).grid(row=0, column=0, sticky="e", padx=(0, 10))
        ctk.CTkButton(
            actions,
            text="Cancelar",
            width=120,
            height=42,
            corner_radius=8,
            fg_color=SURFACE,
            hover_color=SURFACE_2,
            text_color=TEXT,
            border_width=1,
            border_color=BORDER,
            command=window.destroy,
        ).grid(row=0, column=1, sticky="e")
        window.bind("<Control-s>", lambda _event: save_setup())
        window.bind("<Escape>", lambda _event: window.destroy())

    def open_setup_window(self):
        data = load_user_config()
        window = ctk.CTkToplevel(self)
        window.title("Configurar Job Matcher")
        window.geometry("1120x760")
        window.minsize(980, 700)
        window.resizable(True, True)
        window.configure(fg_color=BASE)
        window.transient(self)
        window.grab_set()
        self._set_setup_window_style(window)
        window.after(100, lambda: self._set_setup_window_style(window))

        fields = {}
        path_vars = {
            "profile_text_path": tk.StringVar(value=str(data.get("profile_text_path", ""))),
            "resume_pdf_path": tk.StringVar(value=str(data.get("resume_pdf_path", ""))),
        }
        multiline_boxes = {}
        test_status = tk.StringVar(value="Teste cada servico quando quiser validar a configuracao.")

        header = ctk.CTkFrame(window, fg_color=BG, height=72, corner_radius=0)
        header.pack(fill="x")
        header.pack_propagate(False)
        ctk.CTkFrame(header, height=1, fg_color=BORDER, corner_radius=0).pack(side="bottom", fill="x")

        title_block = ctk.CTkFrame(header, fg_color="transparent")
        title_block.pack(side="left", padx=24, pady=16)
        ctk.CTkLabel(title_block, text="Configuracao do usuario", font=(FONT, 16, "bold"), text_color=TEXT).pack(anchor="w")
        ctk.CTkLabel(title_block, text=str(get_config_path()), font=(FONT, 10), text_color=C["text_muted"]).pack(anchor="w", pady=(2, 0))

        body = ctk.CTkFrame(window, fg_color="transparent")
        body.pack(fill="both", expand=True)
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(0, weight=1)

        nav = ctk.CTkFrame(body, width=150, fg_color=BG, corner_radius=0)
        nav.grid(row=0, column=0, sticky="nsew")
        nav.grid_propagate(False)
        ctk.CTkFrame(nav, width=1, fg_color=BORDER, corner_radius=0).pack(side="right", fill="y")

        content_area = ctk.CTkScrollableFrame(
            body,
            fg_color=BASE,
            corner_radius=0,
            scrollbar_button_color=C["border"],
            scrollbar_button_hover_color=C["border_bright"],
        )
        content_area.grid(row=0, column=1, sticky="nsew")

        section_frames = {}
        nav_buttons = {}

        def section_group(parent, title):
            row = ctk.CTkFrame(parent, fg_color="transparent")
            row.pack(fill="x", pady=(16, 10))
            ctk.CTkLabel(row, text=title.upper(), font=(FONT, 10, "bold"), text_color=C["text_muted"]).pack(side="left")
            ctk.CTkFrame(row, height=1, fg_color=BORDER, corner_radius=0).pack(side="left", fill="x", expand=True, padx=(8, 0), pady=6)

        def add_entry(parent, key, label, secret=False, mono=False, default=""):
            ctk.CTkLabel(parent, text=label, font=(FONT, 11), text_color=C["text_muted"]).pack(anchor="w", pady=(8, 4))
            var = tk.StringVar(value=str(data.get(key, default)))
            fields[key] = var
            entry = ctk.CTkEntry(
                parent,
                textvariable=var,
                show="*" if secret else "",
                height=36,
                corner_radius=6,
                fg_color=SURFACE_2,
                border_width=1,
                border_color=C["border_bright"],
                text_color=C["text_muted"] if mono else TEXT,
                font=("Consolas", 12) if mono else (FONT, 13),
            )
            entry.pack(fill="x")
            return entry

        def add_list_box(parent, key, label, default_attr, height=90, help_text=None):
            ctk.CTkLabel(parent, text=label, font=(FONT, 11), text_color=C["text_muted"]).pack(anchor="w", pady=(10, 4))
            if help_text:
                ctk.CTkLabel(parent, text=help_text, font=(FONT, 11), text_color=C["text_muted"]).pack(anchor="w", pady=(0, 4))
            box = ctk.CTkTextbox(
                parent,
                height=height,
                corner_radius=6,
                fg_color=SURFACE_2,
                border_width=1,
                border_color=C["border_bright"],
                text_color=TEXT,
                font=(FONT, 12),
            )
            box.pack(fill="x")
            values = data.get(key) or getattr(engine.settings, default_attr, [])
            box.insert("1.0", "\n".join(values))
            multiline_boxes[key] = box
            return box

        def add_file_picker(parent, key, label, filetypes, target_name):
            ctk.CTkLabel(parent, text=label, font=(FONT, 11), text_color=C["text_muted"]).pack(anchor="w", pady=(10, 4))
            row = ctk.CTkFrame(parent, fg_color="transparent")
            row.pack(fill="x")
            row.grid_columnconfigure(0, weight=1)
            ctk.CTkEntry(
                row,
                textvariable=path_vars[key],
                height=36,
                corner_radius=6,
                fg_color=SURFACE_2,
                border_width=1,
                border_color=C["border_bright"],
                text_color=C["text_muted"],
                font=(FONT, 11),
            ).grid(row=0, column=0, sticky="ew", padx=(0, 8))

            def choose_file():
                selected = filedialog.askopenfilename(parent=window, filetypes=filetypes)
                if selected:
                    try:
                        path_vars[key].set(import_user_file(selected, target_name))
                    except Exception as exc:
                        messagebox.showerror("Job Matcher", f"Nao foi possivel importar o arquivo:\n{exc}")

            ctk.CTkButton(
                row,
                text="Selecionar",
                width=100,
                height=36,
                corner_radius=6,
                fg_color="transparent",
                hover_color=SURFACE_2,
                text_color=MUTED,
                border_width=1,
                border_color=C["border_bright"],
                font=(FONT, 12),
                command=choose_file,
            ).grid(row=0, column=1)

        def show_section(name):
            for section, frame in section_frames.items():
                if section == name:
                    frame.pack(fill="both", expand=True, padx=24, pady=20)
                else:
                    frame.pack_forget()
            for section, button in nav_buttons.items():
                if section == name:
                    button.configure(fg_color=C["amber_subtle"], text_color=ACCENT)
                else:
                    button.configure(fg_color="transparent", text_color=C["text_muted"])

        for name in ("Credenciais", "Busca", "Perfil e curriculo", "Termos e filtros"):
            button = ctk.CTkButton(
                nav,
                text=name,
                height=36,
                corner_radius=6,
                fg_color="transparent",
                hover_color=SURFACE,
                text_color=C["text_muted"],
                border_width=0,
                anchor="w",
                font=(FONT, 12),
                command=lambda selected=name: show_section(selected),
            )
            button.pack(fill="x", padx=8, pady=(8 if not nav_buttons else 2, 0))
            nav_buttons[name] = button

        cred = ctk.CTkFrame(content_area, fg_color="transparent")
        section_frames["Credenciais"] = cred
        section_group(cred, "IA - Groq")
        add_entry(cred, "groq_api_key", "API Key do Groq", secret=True, mono=True)
        add_entry(cred, "groq_model", "Modelo da IA", default="llama-3.3-70b-versatile")
        if not fields["groq_model"].get():
            fields["groq_model"].set("llama-3.3-70b-versatile")
        section_group(cred, "Busca - Serper")
        add_entry(cred, "serper_api_key", "API Key do Serper", secret=True, mono=True)
        section_group(cred, "Gmail")
        add_entry(cred, "email_remetente", "Remetente")
        add_entry(cred, "email_senha_app", "Senha de app do Gmail", secret=True, mono=True)
        add_entry(cred, "email_destinatario", "E-mail que recebera os matches")

        def run_config_test(kind):
            def worker():
                try:
                    if kind == "ia":
                        key = fields["groq_api_key"].get().strip()
                        model = fields["groq_model"].get().strip() or "llama-3.3-70b-versatile"
                        if not key:
                            raise ValueError("Informe a API da IA antes de testar.")
                        from groq import Groq
                        client = Groq(api_key=key)
                        client.chat.completions.create(
                            model=model,
                            messages=[{"role": "user", "content": "Responda apenas OK."}],
                            temperature=0,
                            max_tokens=8,
                        )
                        message = "IA funcionando."
                    elif kind == "serper":
                        key = fields["serper_api_key"].get().strip()
                        if not key:
                            raise ValueError("Informe a API Serper antes de testar.")
                        response = requests.post(
                            "https://google.serper.dev/search",
                            headers={"X-API-KEY": key, "Content-Type": "application/json"},
                            json={"q": "site:linkedin.com/jobs Java developer", "num": 1},
                            timeout=20,
                        )
                        if response.status_code >= 400:
                            raise ValueError(f"Serper retornou HTTP {response.status_code}.")
                        message = "Serper funcionando."
                    else:
                        sender = fields["email_remetente"].get().strip()
                        password = fields["email_senha_app"].get().strip()
                        if not sender or not password:
                            raise ValueError("Informe Gmail remetente e senha de app antes de testar.")
                        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=20) as smtp:
                            smtp.login(sender, password)
                        message = "Gmail funcionando."
                    self.after(0, test_status.set, message)
                    self.after(0, messagebox.showinfo, "Job Matcher", message)
                except Exception as exc:
                    error = f"Teste falhou: {exc}"
                    self.after(0, test_status.set, error)
                    self.after(0, messagebox.showerror, "Job Matcher", error)

            test_status.set("Testando, aguarde...")
            threading.Thread(target=worker, daemon=True).start()

        section_group(cred, "Testes rapidos")
        ctk.CTkLabel(cred, textvariable=test_status, font=(FONT, 11), text_color=C["text_muted"]).pack(anchor="w", pady=(0, 8))
        test_row = ctk.CTkFrame(cred, fg_color="transparent")
        test_row.pack(fill="x")
        test_row.grid_columnconfigure((0, 1, 2), weight=1)
        for col, (label, kind) in enumerate((("Testar IA", "ia"), ("Testar Serper", "serper"), ("Testar Gmail", "gmail"))):
            ctk.CTkButton(
                test_row,
                text=label,
                height=34,
                corner_radius=6,
                fg_color="transparent",
                hover_color=SURFACE_2,
                text_color=MUTED,
                border_width=1,
                border_color=C["border_bright"],
                font=(FONT, 12),
                command=lambda selected=kind: run_config_test(selected),
            ).grid(row=0, column=col, sticky="ew", padx=(0 if col == 0 else 10, 0))

        search = ctk.CTkFrame(content_area, fg_color="transparent")
        section_frames["Busca"] = search
        section_group(search, "Localizacao")
        add_entry(search, "location", "Pais ou regiao principal da busca", default="Brasil")
        if not fields["location"].get():
            fields["location"].set("Brasil")

        profile = ctk.CTkFrame(content_area, fg_color="transparent")
        section_frames["Perfil e curriculo"] = profile
        section_group(profile, "Arquivos")
        add_file_picker(profile, "profile_text_path", "Arquivo TXT com tudo que voce sabe sobre si", [("Texto", "*.txt"), ("Todos", "*.*")], "perfil.txt")
        add_file_picker(profile, "resume_pdf_path", "Curriculo em PDF", [("PDF", "*.pdf"), ("Todos", "*.*")], "curriculo.pdf")

        filters = ctk.CTkFrame(content_area, fg_color="transparent")
        section_frames["Termos e filtros"] = filters
        section_group(filters, "Termos de busca")
        add_list_box(filters, "search_base_terms", "Areas, cargos ou stacks principais", "SEARCH_BASE_TERMS")
        two_col = ctk.CTkFrame(filters, fg_color="transparent")
        two_col.pack(fill="x")
        two_col.grid_columnconfigure((0, 1), weight=1)
        senior = ctk.CTkFrame(two_col, fg_color="transparent")
        senior.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        mode = ctk.CTkFrame(two_col, fg_color="transparent")
        mode.grid(row=0, column=1, sticky="ew", padx=(6, 0))
        add_list_box(senior, "search_seniority_terms", "Senioridade desejada", "SEARCH_SENIORITY_TERMS")
        add_list_box(mode, "search_work_modes", "Modalidade de trabalho", "SEARCH_WORK_MODES")
        section_group(filters, "Filtros avancados")
        add_list_box(filters, "job_location_filters", "Filtros de localizacao aceitos", "JOB_LOCATION_FILTERS")
        add_list_box(filters, "target_companies", "Empresas-alvo opcionais", "TARGET_COMPANIES", height=72, help_text="Deixe vazio para verificar vagas de todas as empresas.")
        add_list_box(filters, "search_queries", "Queries manuais extras", "SEARCH_QUERIES", height=120)

        def save_setup():
            payload = {key: var.get().strip() for key, var in fields.items()}
            payload["profile_text_path"] = path_vars["profile_text_path"].get().strip()
            payload["resume_pdf_path"] = path_vars["resume_pdf_path"].get().strip()
            for key, box in multiline_boxes.items():
                payload[key] = [line.strip() for line in box.get("1.0", "end").splitlines() if line.strip()]
            payload["min_score"] = self._parse_int(self.min_score, 90, 1, 100)
            payload["scan_interval_minutes"] = self._parse_int(self.interval, 60, 1, 720)
            payload["max_jobs_to_analyze_per_scan"] = self._parse_int(self.max_jobs, 25, 1, 200)
            save_user_config(payload)
            engine.refresh_runtime_settings()
            logging.info("Configuracao salva. O Job Matcher ja pode usar os dados do usuario.")
            messagebox.showinfo("Job Matcher", "Configuracao salva com sucesso.")
            window.destroy()

        header_actions = ctk.CTkFrame(header, fg_color="transparent")
        header_actions.pack(side="right", padx=24)
        ctk.CTkButton(
            header_actions,
            text="Salvar configuracao",
            width=170,
            height=36,
            corner_radius=6,
            fg_color=ACCENT,
            hover_color=ACCENT_DIM,
            text_color=BG,
            font=(FONT, 12, "bold"),
            command=save_setup,
        ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            header_actions,
            text="Cancelar",
            width=100,
            height=36,
            corner_radius=6,
            fg_color="transparent",
            hover_color=SURFACE_2,
            text_color=MUTED,
            border_width=1,
            border_color=C["border_bright"],
            font=(FONT, 12),
            command=window.destroy,
        ).pack(side="left")
        window.bind("<Control-s>", lambda _event: save_setup())
        window.bind("<Escape>", lambda _event: window.destroy())
        show_section("Credenciais")

    def _sidebar_card(self, title, value_var, accent, parent=None):
        frame = ctk.CTkFrame(parent or self.sidebar, fg_color=SURFACE, corner_radius=8, border_width=1, border_color=BORDER)
        ctk.CTkLabel(frame, text=title.upper(), text_color=COLORS["text_muted"], font=(FONT, 10, "bold")).pack(anchor="w", padx=12, pady=(10, 2))
        value_label = ctk.CTkLabel(frame, textvariable=value_var, text_color=accent, font=(FONT, 13, "bold"), wraplength=112, justify="left")
        value_label.pack(anchor="w", padx=12, pady=(0, 10))
        frame.value_label = value_label
        return frame

    def _static_sidebar_card(self, title, value, accent):
        var = tk.StringVar(value=value)
        return self._sidebar_card(title, var, accent)

    def _refresh_sidebar_status(self, status):
        if not hasattr(self, "status_card"):
            return
        normalized = (status or "").casefold()
        if "monitorando" in normalized:
            color = ACCENT
            border = ACCENT
        elif "erro" in normalized or "falh" in normalized:
            color = DANGER
            border = BORDER
        elif "parando" in normalized:
            color = ACCENT
            border = BORDER
        else:
            color = COLORS["green"]
            border = BORDER
        self.status_card.configure(border_color=border)
        self.status_card.value_label.configure(text_color=color)

    def _refresh_sidebar_context(self):
        if not hasattr(self, "context_card_var"):
            return
        if self.current_tab == "Candidaturas":
            try:
                total = calculate_metrics(load_applications()).get("total", 0)
                self.context_card_var.set(f"{total} candidaturas")
            except Exception:
                self.context_card_var.set("Candidaturas")
        elif self.current_tab == "Mercado":
            try:
                count = engine.count_new_market_trend_jobs()
                self.context_card_var.set(f"{count} novas")
            except Exception:
                self.context_card_var.set("Tendencias")
        else:
            self.context_card_var.set("Google / Serper")

    def _number_field(self, parent, column, label, variable):
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.grid(row=2, column=column, padx=(18 if column == 0 else 12, 18 if column == 2 else 0), pady=(14, 14), sticky="ew")
        ctk.CTkLabel(frame, text=label, text_color=COLORS["text_muted"], font=(FONT, 11)).pack(anchor="w")
        ctk.CTkEntry(
            frame,
            textvariable=variable,
            height=36,
            corner_radius=6,
            fg_color=SURFACE_2,
            border_width=1,
            border_color=COLORS["border_bright"],
            text_color=TEXT,
            placeholder_text_color=COLORS["text_muted"],
            font=(FONT, 13),
        ).pack(fill="x", pady=(6, 0))

    def _action_button(self, parent, column, text, command, primary=False, danger=False):
        fg = ACCENT if primary else "transparent"
        hover = ACCENT_DIM if primary else SURFACE_2
        text_color = BG if primary else MUTED
        border_color = ACCENT if primary else COLORS["border_bright"]
        if danger:
            fg = "transparent"
            hover = DANGER_DARK
            text_color = DANGER
            border_color = "#3A2020"
        ctk.CTkButton(
            parent,
            text=text,
            height=36,
            corner_radius=6,
            fg_color=fg,
            hover_color=hover,
            text_color=text_color,
            border_width=1,
            border_color=border_color,
            font=(FONT, 12, "bold" if primary else "normal"),
            command=command,
        ).grid(row=0, column=column, padx=(0 if column == 0 else 8, 0), sticky="ew")

    def _parse_int(self, variable, fallback, min_value, max_value):
        try:
            value = int(variable.get())
        except ValueError:
            value = fallback
        value = max(min_value, min(max_value, value))
        variable.set(str(value))
        return value

    def _apply_runtime_settings(self):
        engine.MIN_SCORE = self._parse_int(self.min_score, engine.MIN_SCORE, 1, 100)
        engine.SCAN_INTERVAL_MINUTES = self._parse_int(self.interval, engine.SCAN_INTERVAL_MINUTES, 1, 720)
        engine.settings.MAX_JOBS_TO_ANALYZE_PER_SCAN = self._parse_int(self.max_jobs, 25, 1, 200)
        save_user_config({
            "min_score": engine.MIN_SCORE,
            "scan_interval_minutes": engine.SCAN_INTERVAL_MINUTES,
            "max_jobs_to_analyze_per_scan": engine.settings.MAX_JOBS_TO_ANALYZE_PER_SCAN,
        })
        engine.refresh_runtime_settings()

    def _set_status(self, text):
        self.after(0, self.status_text.set, text)
        self.after(0, self._refresh_sidebar_status, text)

    def _set_next_scan(self, text):
        self.after(0, self.next_scan_text.set, text)

    def start_monitoring(self):
        if self.worker and self.worker.is_alive():
            messagebox.showinfo("Job Matcher", "Ja existe uma tarefa em execucao.")
            return

        self._apply_runtime_settings()
        logging.info("Aguarde. Preparando monitoramento e primeira busca.")
        self.stop_event.clear()
        self.monitoring = True
        self.worker = threading.Thread(target=self._monitor_loop, daemon=True)
        self.worker.start()

    def run_once(self):
        if self.worker and self.worker.is_alive():
            messagebox.showinfo("Job Matcher", "Aguarde a tarefa atual terminar.")
            return

        self._apply_runtime_settings()
        logging.info("Aguarde. Preparando busca e analise das vagas.")
        self.stop_event.clear()
        self.monitoring = False
        self.worker = threading.Thread(target=self._scan_once_worker, daemon=True)
        self.worker.start()

    def stop_monitoring(self):
        self.stop_event.set()
        self.monitoring = False
        self._set_status("Parando...")
        self._set_next_scan("-")
        logging.info("Parada solicitada. A varredura atual sera finalizada no proximo ponto seguro.")

    def send_test_email(self):
        if self.worker and self.worker.is_alive():
            messagebox.showinfo("Job Matcher", "Aguarde a tarefa atual terminar.")
            return

        self._apply_runtime_settings()
        if not engine.GROQ_API_KEY or not engine.EMAIL_REMETENTE or not engine.EMAIL_SENHA_APP or not engine.EMAIL_DESTINATARIO:
            messagebox.showinfo("Job Matcher", "Abra Configurar e preencha IA e e-mail antes do teste.")
            return
        logging.info("Aguarde. Enviando e-mail de teste.")
        self.worker = threading.Thread(target=self._send_email_worker, daemon=True)
        self.worker.start()

    def analyze_single_job(self):
        if self.analysis_worker and self.analysis_worker.is_alive():
            messagebox.showinfo("Job Matcher", "A analise atual ainda esta em execucao.")
            return

        description = self.analysis_description.get("1.0", "end").strip()
        if len(description) < 80:
            messagebox.showinfo("Job Matcher", "Cole uma descricao de vaga mais completa antes de analisar.")
            return

        self.analysis_status.set("Analisando esta vaga com IA...")
        self.analyze_button.configure(state="disabled", text="Analisando...")
        self.analysis_worker = threading.Thread(
            target=self._analysis_worker,
            args=(self.analysis_title.get().strip(), self.analysis_company.get().strip(), description),
            daemon=True,
        )
        self.analysis_worker.start()

    def simulate_ats(self):
        if self.ats_worker and self.ats_worker.is_alive():
            messagebox.showinfo("Job Matcher", "A simulacao ATS atual ainda esta em execucao.")
            return

        description = self.analysis_description.get("1.0", "end").strip()
        if len(description) < 80:
            messagebox.showinfo("Job Matcher", "Cole uma descricao de vaga mais completa antes de simular ATS.")
            return

        self.analysis_status.set("Simulando leitura ATS do curriculo...")
        self.ats_button.configure(state="disabled", text="Simulando...")
        self.ats_worker = threading.Thread(
            target=self._ats_worker,
            args=(self.analysis_title.get().strip(), self.analysis_company.get().strip(), description),
            daemon=True,
        )
        self.ats_worker.start()

    def generate_cover_letter(self):
        if self.cover_letter_worker and self.cover_letter_worker.is_alive():
            messagebox.showinfo("Job Matcher", "A carta atual ainda esta em geracao.")
            return

        description = self.analysis_description.get("1.0", "end").strip()
        if len(description) < 80:
            messagebox.showinfo("Job Matcher", "Cole uma descricao de vaga mais completa antes de gerar carta.")
            return

        self.analysis_status.set("Gerando carta contextualizada...")
        self.cover_letter_button.configure(state="disabled", text="Gerando...")
        self.cover_letter_worker = threading.Thread(
            target=self._cover_letter_worker,
            args=(self.analysis_title.get().strip(), self.analysis_company.get().strip(), description),
            daemon=True,
        )
        self.cover_letter_worker.start()

    def clear_analysis(self):
        self.analysis_title.set("")
        self.analysis_company.set("")
        self.analysis_description.delete("1.0", "end")
        self.last_analysis_text = ""
        self.last_job_context = None
        if hasattr(self, "analysis_optimize_button"):
            self.analysis_optimize_button.configure(state="disabled")
        if hasattr(self, "register_application_button"):
            self.register_application_button.configure(state="disabled")
        self.analysis_status.set("Cole uma vaga e clique em Analisar.")
        self._set_analysis_result(
            "A analise vai aparecer aqui.\n\n"
            "O app vai mostrar compatibilidade, pontos fortes, gaps e melhorias recomendadas para o curriculo atual.\n"
        )

    def copy_analysis(self):
        if not self.last_analysis_text:
            messagebox.showinfo("Job Matcher", "Ainda nao ha analise para copiar.")
            return
        self.clipboard_clear()
        self.clipboard_append(self.last_analysis_text)
        self.analysis_status.set("Analise copiada para a area de transferencia.")

    def use_last_analyzed_job(self):
        if not self.last_job_context:
            messagebox.showinfo("Job Matcher", "Ainda nao ha vaga analisada para reutilizar.")
            return
        self.optimization_title.set(self.last_job_context.get("title", ""))
        self.optimization_company.set(self.last_job_context.get("company", ""))
        self.optimization_description.delete("1.0", "end")
        self.optimization_description.insert("1.0", self.last_job_context.get("description", ""))
        self.optimization_status.set("Vaga analisada carregada. Clique em Gerar otimizacao.")
        self._show_tab("Otimizar curriculo")

    def register_last_application(self):
        if not self.last_job_context:
            messagebox.showinfo("Job Matcher", "Analise uma vaga antes de registrar candidatura.")
            return
        app_id, created = register_application(
            title=self.last_job_context.get("title", ""),
            company=self.last_job_context.get("company", ""),
            url=self.last_job_context.get("url", ""),
            score_fit=self.last_job_context.get("score"),
            source=self.last_job_context.get("source", "Manual"),
        )
        if created:
            self.analysis_status.set("Candidatura registrada na aba Candidaturas.")
        else:
            self.analysis_status.set("Essa candidatura ja estava registrada.")
        self.selected_application_id = app_id
        self.refresh_tracker()
        self._show_tab("Candidaturas")

    def optimize_resume(self):
        if self.optimization_worker and self.optimization_worker.is_alive():
            messagebox.showinfo("Job Matcher", "A otimizacao atual ainda esta em execucao.")
            return

        description = self.optimization_description.get("1.0", "end").strip()
        if len(description) < 80:
            messagebox.showinfo("Job Matcher", "Cole uma descricao de vaga mais completa antes de otimizar.")
            return

        self.optimization_status.set("Gerando otimizacao com IA...")
        self.optimize_button.configure(state="disabled", text="Gerando...")
        self.optimization_worker = threading.Thread(
            target=self._optimization_worker,
            args=(self.optimization_title.get().strip(), self.optimization_company.get().strip(), description),
            daemon=True,
        )
        self.optimization_worker.start()

    def clear_optimization(self):
        self.optimization_title.set("")
        self.optimization_company.set("")
        self.optimization_description.delete("1.0", "end")
        self.last_optimization_text = ""
        self.optimization_status.set("Cole uma vaga e gere uma otimizacao.")
        self._set_optimization_result(
            "A otimizacao vai aparecer aqui.\n\n"
            "O app vai sugerir headline, resumo, skills, bullets e alertas de honestidade.\n"
        )

    def copy_optimization(self):
        if not self.last_optimization_text:
            messagebox.showinfo("Job Matcher", "Ainda nao ha otimizacao para copiar.")
            return
        self.clipboard_clear()
        self.clipboard_append(self.last_optimization_text)
        self.optimization_status.set("Otimizacao copiada para a area de transferencia.")

    def open_reports_folder(self):
        path = REPORT_DIR
        path.mkdir(parents=True, exist_ok=True)
        logging.info("Abrindo pasta de relatorios: %s", path)
        os.startfile(str(path))

    def refresh_tracker(self):
        if not hasattr(self, "tracker_columns"):
            return

        applications = load_applications()
        metrics = calculate_metrics(applications)
        alerts = get_follow_up_alerts()

        for child in self.tracker_metrics.winfo_children():
            child.destroy()
        metric_items = [
            ("Total", metrics["total"]),
            ("Responderam", metrics["respondidas"]),
            ("Entrevista", f"{metrics['taxa_entrevista']}%"),
            ("Media resposta", f"{metrics['tempo_medio_resposta']}d"),
        ]
        for index, (label, value) in enumerate(metric_items):
            card = ctk.CTkFrame(self.tracker_metrics, fg_color=SURFACE, corner_radius=8, border_width=1, border_color=BORDER)
            card.grid(row=0, column=index, sticky="ew", padx=(0 if index == 0 else 8, 0))
            ctk.CTkLabel(card, text=label.upper(), text_color=COLORS["text_muted"], font=(FONT, 10, "bold")).pack(anchor="w", padx=14, pady=(10, 2))
            ctk.CTkLabel(card, text=str(value), text_color=ACCENT if index != 3 else TEXT, font=(FONT, 20, "bold")).pack(anchor="w", padx=14, pady=(0, 10))
        if alerts:
            names = "; ".join(f"{item.get('cargo')} @ {item.get('empresa')}" for item in alerts[:4])
            if len(alerts) > 4:
                names += f"; +{len(alerts) - 4}"
            banner = ctk.CTkFrame(self.tracker_metrics, fg_color=COLORS["amber_subtle"], corner_radius=8, border_width=1, border_color=ACCENT_DIM)
            banner.grid(row=1, column=0, columnspan=4, sticky="ew", pady=(10, 0))
            ctk.CTkLabel(
                banner,
                text=f"Follow-up pendente: {names}",
                text_color=ACCENT,
                font=(FONT, 12, "bold"),
                wraplength=900,
                justify="left",
            ).pack(anchor="w", padx=14, pady=10)

        for column in self.tracker_columns.values():
            for child in column.winfo_children():
                child.destroy()
        grouped = {status: [] for status in STATUS_ORDER}
        for app_id, item in applications.items():
            grouped.setdefault(item.get("status", "enviado"), []).append((app_id, item))
        for status in STATUS_ORDER:
            items = sorted(grouped.get(status, []), key=lambda pair: pair[1].get("updated_at", ""), reverse=True)
            if not items:
                ctk.CTkLabel(
                    self.tracker_columns[status],
                    text="Sem candidaturas.",
                    text_color=MUTED,
                    font=("Segoe UI", 12),
                ).pack(anchor="w", padx=10, pady=10)
                continue
            for app_id, item in items:
                self._tracker_card(self.tracker_columns[status], app_id, item)

        if self.selected_application_id in applications:
            self._load_tracker_detail(self.selected_application_id, applications[self.selected_application_id])
        else:
            self.selected_application_id = None
            self._clear_tracker_detail()

    def _tracker_card(self, parent, app_id, item):
        selected = app_id == self.selected_application_id
        card = ctk.CTkFrame(parent, fg_color=SURFACE_2 if selected else SURFACE, corner_radius=7, border_width=1, border_color=ACCENT if selected else BORDER)
        card.pack(fill="x", padx=8, pady=(8, 0))
        title = item.get("cargo", "Vaga sem titulo")
        company = item.get("empresa", "Nao informada")
        score = item.get("score_fit")
        score_text = f"\n* {score}% fit" if score is not None else ""
        button = ctk.CTkButton(
            card,
            text=f"{title}\n{company}{score_text}",
            height=76,
            corner_radius=7,
            fg_color="transparent",
            hover_color=SURFACE_2,
            text_color=TEXT,
            anchor="w",
            font=(FONT, 12, "bold"),
            command=lambda: self.select_tracker_application(app_id),
        )
        button.pack(fill="x", padx=8, pady=8)

    def select_tracker_application(self, app_id):
        applications = load_applications()
        if app_id not in applications:
            return
        self.selected_application_id = app_id
        self.refresh_tracker()

    def _clear_tracker_detail(self):
        self.tracker_detail_title.configure(text="Selecione uma candidatura.")
        self.tracker_contact.set("")
        self.tracker_next_action.set("")
        self.tracker_notes.delete("1.0", "end")
        for child in self.tracker_move_frame.winfo_children():
            child.destroy()

    def _load_tracker_detail(self, app_id, item):
        self.tracker_detail_title.configure(
            text=f"{item.get('cargo', 'Vaga')} @ {item.get('empresa', 'Empresa')}\nStatus: {STATUS_LABELS.get(item.get('status'), item.get('status'))}"
        )
        self.tracker_contact.set(item.get("contato", ""))
        self.tracker_next_action.set(item.get("proxima_acao", ""))
        self.tracker_notes.delete("1.0", "end")
        self.tracker_notes.insert("1.0", item.get("notas", ""))
        for child in self.tracker_move_frame.winfo_children():
            child.destroy()
        ctk.CTkLabel(self.tracker_move_frame, text="Mover para", text_color=C["text_muted"], font=(FONT, 11)).grid(row=0, column=0, sticky="w", pady=(0, 6))
        row = 1
        current = item.get("status", "enviado")
        for status in STATUS_ORDER:
            if status == current:
                continue
            ctk.CTkButton(
                self.tracker_move_frame,
                text=STATUS_LABELS[status],
                height=32,
                corner_radius=6,
                fg_color="transparent",
                hover_color=SURFACE_2,
                text_color=ACCENT if status in {"triagem", "entrevista"} else MUTED,
                border_width=1,
                border_color=ACCENT_DIM if status in {"triagem", "entrevista"} else C["border_bright"],
                font=(FONT, 12),
                command=lambda target=status: self.move_tracker_application(target),
            ).grid(row=row, column=0, sticky="ew", pady=(0, 6))
            row += 1

    def save_tracker_details(self):
        if not self.selected_application_id:
            messagebox.showinfo("Job Matcher", "Selecione uma candidatura primeiro.")
            return
        update_application(self.selected_application_id, {
            "contato": self.tracker_contact.get().strip(),
            "proxima_acao": self.tracker_next_action.get().strip(),
            "notas": self.tracker_notes.get("1.0", "end").strip(),
        })
        self.refresh_tracker()

    def move_tracker_application(self, status):
        if not self.selected_application_id:
            return
        update_application(self.selected_application_id, {"status": status})
        self.refresh_tracker()

    def refresh_trends_tab(self):
        if not hasattr(self, "market_new_jobs"):
            return
        try:
            count = engine.count_new_market_trend_jobs()
            self.market_new_jobs.set(f"Vagas novas para tendencias: {count}")
            if hasattr(self, "market_badge"):
                self.market_badge.configure(text=f"{count} novas")
        except Exception as exc:
            self.market_new_jobs.set("Vagas novas para tendencias: erro ao contar")
            if hasattr(self, "market_badge"):
                self.market_badge.configure(text="erro")
            self.market_status.set(str(exc))

    def generate_market_trends(self):
        if self.market_worker and self.market_worker.is_alive():
            messagebox.showinfo("Job Matcher", "O relatorio de mercado ainda esta sendo gerado.")
            return
        self.market_status.set("Gerando relatorio de mercado...")
        self.market_button.configure(state="disabled", text="Gerando...")
        self._set_market_log("Iniciando processamento em lotes...\n")
        self.market_worker = threading.Thread(target=self._market_worker, daemon=True)
        self.market_worker.start()

    def _market_worker(self):
        try:
            def progress(message):
                self.after(0, self._append_market_log, message)

            html_path, summary = engine.generate_manual_market_trends(progress=progress)
            self.after(0, self._append_market_log, f"Relatorio aberto: {html_path}")
            self.after(0, self.market_status.set, f"Relatorio gerado com {summary.get('total_jobs', 0)} vaga(s) analisada(s).")
            self.after(0, self.refresh_reports)
            self.after(0, self.refresh_trends_tab)
        except Exception as exc:
            self.after(0, self._append_market_log, f"Erro: {exc}")
            self.after(0, self.market_status.set, "Nao foi possivel gerar o relatorio de mercado.")
            self.after(0, messagebox.showerror, "Job Matcher", str(exc))
        finally:
            self.after(0, lambda: self.market_button.configure(state="normal", text="Gerar relatorio de mercado"))

    def _set_market_log(self, text):
        self.market_log.configure(state="normal")
        self.market_log.delete("1.0", "end")
        self.market_log.insert("end", text)
        self.market_log.configure(state="disabled")

    def _append_market_log(self, text):
        self.market_log.configure(state="normal")
        self.market_log.insert("end", f"{text}\n")
        self.market_log.see("end")
        self.market_log.configure(state="disabled")

    def refresh_reports(self):
        if not hasattr(self, "reports_list"):
            return
        for child in self.reports_list.winfo_children():
            child.destroy()

        reports = list_report_summaries()
        if not reports:
            ctk.CTkLabel(
                self.reports_list,
                text="Nenhum relatorio gerado ainda.",
                text_color=MUTED,
                font=("Segoe UI", 13),
            ).grid(row=0, column=0, sticky="w", pady=(0, 8))
            return

        for index, report in enumerate(reports):
            row = ctk.CTkFrame(self.reports_list, fg_color=SURFACE, corner_radius=8, border_width=1, border_color=BORDER)
            row.grid(row=index, column=0, sticky="ew", pady=(0, 10))
            row.grid_columnconfigure(1, weight=1)

            title = report.get("title") or "Relatorio"
            company = report.get("company") or ""
            score = report.get("score")
            title_line = title if not company else f"{title} @ {company}"
            if score is not None:
                title_line = f"{score}% - {title_line}"

            icon_text = {
                "job_analysis": "DOC",
                "ats": "ATS",
                "cover_letter": "TXT",
                "market_trends": "BAR",
                "scan": "LOG",
                "resume_optimization": "CV",
            }.get(report.get("type"), "REP")
            icon = ctk.CTkFrame(row, width=32, height=32, fg_color=COLORS["amber_subtle"], corner_radius=6)
            icon.grid(row=0, column=0, rowspan=2, padx=(14, 10), pady=12, sticky="w")
            icon.grid_propagate(False)
            ctk.CTkLabel(icon, text=icon_text, text_color=ACCENT, font=(FONT, 9, "bold")).grid(row=0, column=0, sticky="nsew")
            icon.grid_columnconfigure(0, weight=1)
            icon.grid_rowconfigure(0, weight=1)

            ctk.CTkLabel(
                row,
                text=title_line,
                text_color=TEXT,
                font=(FONT, 13, "bold"),
                anchor="w",
            ).grid(row=0, column=1, padx=0, pady=(12, 2), sticky="ew")
            ctk.CTkLabel(
                row,
                text=f"{report.get('detail', '')} | {report.get('created_at', '')}",
                text_color=COLORS["text_muted"],
                font=(FONT, 11),
                anchor="w",
            ).grid(row=1, column=1, padx=0, pady=(0, 12), sticky="ew")
            ctk.CTkButton(
                row,
                text="Abrir",
                width=90,
                height=28,
                corner_radius=6,
                fg_color="transparent",
                hover_color=SURFACE_2,
                text_color=MUTED,
                border_width=1,
                border_color=COLORS["border_bright"],
                font=(FONT, 12),
                command=lambda path=report.get("open_path") or report.get("md_path"): self.open_report_file(path),
            ).grid(row=0, column=2, rowspan=2, padx=14, pady=12, sticky="e")

    def open_report_file(self, path):
        if not path:
            return
        try:
            path = Path(path)
            if path.suffix.lower() == ".html":
                webbrowser.open(path.resolve().as_uri())
            else:
                os.startfile(str(path))
        except Exception as exc:
            messagebox.showerror("Job Matcher", f"Nao foi possivel abrir o relatorio:\n{exc}")

    def _analysis_worker(self, title, company, description):
        try:
            result = engine.analyze_manual_job(title, company, description)
            if result is None:
                raise ValueError("A IA nao retornou uma analise valida para esta vaga.")
            report_json, report_md = save_manual_analysis_report(title, company, description, result)
            output = self._format_analysis(title, company, result, report_md)
            self.last_job_context = {
                "title": title,
                "company": company,
                "description": description,
                "score": result.score,
                "url": "",
                "source": "Manual",
            }
            self.last_analysis_text = output
            self.after(0, self._set_analysis_result, output)
            self.after(0, lambda: self.analysis_optimize_button.configure(state="normal"))
            self.after(0, lambda: self.register_application_button.configure(state="normal"))
            self.after(0, self.analysis_status.set, f"Analise salva em reports/{report_md.name}. Voce pode otimizar essa vaga na aba Otimizar curriculo.")
            self.after(0, self.refresh_reports)
        except Exception as exc:
            self.after(0, messagebox.showerror, "Job Matcher", str(exc))
            self.after(0, self.analysis_status.set, "Nao foi possivel analisar esta vaga.")
        finally:
            self.after(0, lambda: self.analyze_button.configure(state="normal", text="Analisar compatibilidade"))

    def _ats_worker(self, title, company, description):
        try:
            result = engine.simulate_manual_ats(title, company, description)
            output = self._format_ats_result(title, company, result)
            self.after(0, self._set_analysis_result, output)
            self.after(0, self.analysis_status.set, f"Simulacao ATS salva em {result.html_path}.")
            self.after(0, self.refresh_reports)
        except Exception as exc:
            self.after(0, messagebox.showerror, "Job Matcher", str(exc))
            self.after(0, self.analysis_status.set, "Nao foi possivel simular ATS para esta vaga.")
        finally:
            self.after(0, lambda: self.ats_button.configure(state="normal", text="Simular ATS"))

    def _cover_letter_worker(self, title, company, description):
        try:
            result = engine.generate_manual_cover_letter(title, company, description)
            output = self._format_cover_letter_result(title, company, result)
            self.after(0, self._set_analysis_result, output)
            self.after(0, self.analysis_status.set, f"Carta salva em {result.html_path}.")
            self.after(0, self.refresh_reports)
        except Exception as exc:
            self.after(0, messagebox.showerror, "Job Matcher", str(exc))
            self.after(0, self.analysis_status.set, "Nao foi possivel gerar carta para esta vaga.")
        finally:
            self.after(0, lambda: self.cover_letter_button.configure(state="normal", text="Gerar carta"))

    def _optimization_worker(self, title, company, description):
        try:
            result = engine.optimize_manual_resume(title, company, description)
            if result is None:
                raise ValueError("A IA nao retornou uma otimizacao valida para esta vaga.")
            report_json, report_md = save_resume_optimization_report(title, company, description, result)
            output = self._format_optimization(title, company, result, report_md)
            self.last_optimization_text = output
            self.after(0, self._set_optimization_result, output)
            self.after(0, self.optimization_status.set, f"Otimizacao concluida e salva em reports/{report_md.name}.")
            self.after(0, self.refresh_reports)
        except Exception as exc:
            self.after(0, messagebox.showerror, "Job Matcher", str(exc))
            self.after(0, self.optimization_status.set, "Nao foi possivel otimizar para esta vaga.")
        finally:
            self.after(0, lambda: self.optimize_button.configure(state="normal", text="Gerar otimizacao"))

    def _format_analysis(self, title, company, result, report_path=None):
        lines = []
        heading = title or "Vaga analisada"
        if company:
            heading = f"{heading} @ {company}"
        lines.append(heading)
        lines.append("")
        lines.append(f"Score: {result.score}%")
        lines.append(f"Prioridade de ajuste: {result.prioridade_ajuste}")
        lines.append("Regua: mesma analise usada na busca automatica.")
        if result.veredito:
            lines.append(f"Veredito: {result.veredito}")
        lines.append("")
        self._append_section(lines, "Pontos fortes para esta vaga", result.pontos_fortes)
        self._append_section(lines, "Pontos fracos ou gaps", result.pontos_fracos)
        self._append_section(lines, "Melhorias recomendadas no curriculo", result.melhorias_curriculo)
        self._append_section(lines, "Itens que podem perder destaque nesta candidatura", result.itens_menos_relevantes)
        if result.proxima_acao:
            lines.append("Proxima acao")
            lines.append(f"- {result.proxima_acao}")
            lines.append("")
        if report_path:
            lines.append("Relatorio salvo")
            lines.append(f"- {report_path}")
        return "\n".join(lines).strip() + "\n"

    def _format_ats_result(self, title, company, result):
        lines = []
        heading = title or "Vaga analisada"
        if company:
            heading = f"{heading} @ {company}"
        lines.append(f"Simulacao ATS - {heading}")
        lines.append("")
        lines.append(f"Score de cobertura: {result.coverage_score}%")
        lines.append(f"Risco: {result.risk}")
        lines.append(f"Diagnostico: {result.diagnostico}")
        lines.append("")
        self._append_section(lines, "Keywords presentes", result.keywords_presentes)
        self._append_section(lines, "Keywords ausentes", result.keywords_ausentes)
        self._append_section(lines, "Avisos de formato do PDF", result.avisos_pdf)
        lines.append("Relatorio HTML")
        lines.append(f"- {result.html_path}")
        return "\n".join(lines).strip() + "\n"

    def _format_cover_letter_result(self, title, company, result):
        lines = []
        heading = title or "Vaga analisada"
        if company:
            heading = f"{heading} @ {company}"
        lines.append(f"Carta de apresentacao - {heading}")
        lines.append("")
        lines.append(f"Idioma detectado: {result.idioma}")
        lines.append(f"Palavras: {result.word_count}")
        lines.append("")
        if result.avisos:
            self._append_section(lines, "Avisos para revisar", result.avisos)
        lines.append("Carta")
        lines.append(result.carta or "Nao gerada.")
        lines.append("")
        lines.append("Relatorio HTML")
        lines.append(f"- {result.html_path}")
        return "\n".join(lines).strip() + "\n"

    def _append_section(self, lines, title, items):
        lines.append(title)
        if items:
            for item in items:
                lines.append(f"- {item}")
        else:
            lines.append("- Nenhum ponto especifico identificado.")
        lines.append("")

    def _format_optimization(self, title, company, result, report_path=None):
        lines = []
        heading = title or "Vaga alvo"
        if company:
            heading = f"{heading} @ {company}"
        lines.append(heading)
        lines.append("")
        if result.headline_sugerida:
            lines.append("Headline sugerida")
            lines.append(result.headline_sugerida)
            lines.append("")
        if result.resumo_profissional_sugerido:
            lines.append("Resumo profissional sugerido")
            lines.append(result.resumo_profissional_sugerido)
            lines.append("")
        self._append_section(lines, "Skills para priorizar", result.skills_prioritarias)
        self._append_section(lines, "Experiencias ou projetos para priorizar", result.experiencias_prioritarias)
        self._append_section(lines, "Bullets sugeridos", result.bullets_sugeridos)
        self._append_section(lines, "Reduzir ou remover destaque", result.reduzir_ou_remover)
        self._append_section(lines, "Evidencias ausentes", result.evidencias_ausentes)
        self._append_section(lines, "Avisos de honestidade", result.avisos_honestidade)
        if result.proxima_acao:
            lines.append("Proxima acao")
            lines.append(f"- {result.proxima_acao}")
            lines.append("")
        if report_path:
            lines.append("Relatorio salvo")
            lines.append(f"- {report_path}")
        return "\n".join(lines).strip() + "\n"

    def _ui_card(self, parent, **kwargs):
        return ctk.CTkFrame(
            parent,
            fg_color=kwargs.pop("fg_color", SURFACE),
            corner_radius=kwargs.pop("corner_radius", 10),
            border_width=kwargs.pop("border_width", 1),
            border_color=kwargs.pop("border_color", BORDER),
            **kwargs,
        )

    def _ui_button(self, parent, text, command, kind="ghost", width=None):
        styles = {
            "primary": {
                "fg_color": ACCENT,
                "hover_color": ACCENT_DIM,
                "text_color": BG,
                "border_width": 0,
                "border_color": ACCENT,
                "font": (FONT, 12, "bold"),
            },
            "ghost": {
                "fg_color": "transparent",
                "hover_color": SURFACE_2,
                "text_color": MUTED,
                "border_width": 1,
                "border_color": C["border_bright"],
                "font": (FONT, 12),
            },
            "outline": {
                "fg_color": "transparent",
                "hover_color": C["amber_subtle"],
                "text_color": ACCENT,
                "border_width": 1,
                "border_color": ACCENT_DIM,
                "font": (FONT, 12),
            },
            "danger": {
                "fg_color": "transparent",
                "hover_color": DANGER_DARK,
                "text_color": DANGER,
                "border_width": 1,
                "border_color": "#3A2020",
                "font": (FONT, 12),
            },
        }
        return ctk.CTkButton(
            parent,
            text=text,
            height=36,
            width=width or 120,
            corner_radius=6,
            command=command,
            **styles[kind],
        )

    def _ui_entry(self, parent, variable):
        return ctk.CTkEntry(
            parent,
            textvariable=variable,
            height=36,
            corner_radius=6,
            fg_color=SURFACE_2,
            border_width=1,
            border_color=C["border_bright"],
            text_color=TEXT,
            placeholder_text_color=C["text_muted"],
            font=(FONT, 13),
        )

    def _ui_textbox(self, parent, height=220, mono=False):
        return ctk.CTkTextbox(
            parent,
            height=height,
            corner_radius=6,
            fg_color=SURFACE_2,
            border_width=1,
            border_color=C["border_bright"],
            text_color=TEXT,
            font=("Consolas", 11) if mono else (FONT, 13),
            wrap="word",
        )

    def _page_header(self, parent, title, subtitle=None, action=None):
        header = ctk.CTkFrame(parent, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=28, pady=(26, 18))
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(header, text=title, font=(FONT, 22, "bold"), text_color=TEXT).grid(row=0, column=0, sticky="w")
        if subtitle:
            ctk.CTkLabel(header, text=subtitle, font=(FONT, 12), text_color=C["text_muted"]).grid(row=1, column=0, sticky="w", pady=(4, 0))
        if action is not None:
            action.grid(row=0, column=1, rowspan=2, sticky="e", padx=(18, 0))
        return header

    def _section_label(self, parent, text, row=0, column=0, **grid):
        label = ctk.CTkLabel(parent, text=text.upper(), font=(FONT, 10, "bold"), text_color=MUTED)
        label.grid(row=row, column=column, sticky="w", **grid)
        return label

    def _field(self, parent, label, variable, row, column, padx=(0, 0)):
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.grid(row=row, column=column, sticky="ew", padx=padx, pady=(12, 0))
        frame.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(frame, text=label, text_color=C["text_muted"], font=(FONT, 11)).grid(row=0, column=0, sticky="w", pady=(0, 5))
        self._ui_entry(frame, variable).grid(row=1, column=0, sticky="ew")

    def _build_layout(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.sidebar = ctk.CTkFrame(self, width=154, fg_color=BG, corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_propagate(False)
        self.sidebar.grid_rowconfigure(3, weight=1)
        ctk.CTkFrame(self.sidebar, width=1, fg_color=BORDER, corner_radius=0).grid(row=0, column=1, rowspan=8, sticky="nse")

        brand = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        brand.grid(row=0, column=0, sticky="ew", padx=14, pady=(20, 16))
        brand.grid_columnconfigure(0, weight=1)
        mark = ctk.CTkFrame(brand, width=36, height=36, fg_color=C["amber_subtle"], border_width=1, border_color=ACCENT_DIM, corner_radius=8)
        mark.grid(row=0, column=0, sticky="n", pady=(0, 8))
        mark.grid_propagate(False)
        ctk.CTkLabel(mark, text="JM", text_color=ACCENT, font=(FONT, 12, "bold")).place(relx=0.5, rely=0.5, anchor="center")
        ctk.CTkLabel(brand, text=f"v{app_version()}", font=(FONT, 10), text_color=C["text_muted"]).grid(row=1, column=0, sticky="n")

        self.nav_area = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        self.nav_area.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 10))
        self.nav_buttons = {}
        nav_items = (
            ("Menu", "Menu"),
            ("Busca", "Busca"),
            ("Analisar vaga", "Analisar"),
            ("Otimizar curriculo", "Otimizar"),
            ("Candidaturas", "Candidaturas"),
            ("Mercado", "Mercado"),
            ("Relatorios", "Relatorios"),
        )
        for index, (name, label) in enumerate(nav_items):
            button = ctk.CTkButton(
                self.nav_area,
                text=label,
                height=36,
                corner_radius=7,
                fg_color="transparent",
                hover_color=SURFACE,
                text_color=MUTED,
                border_width=0,
                anchor="w",
                font=(FONT, 12),
                command=lambda selected=name: self._show_tab(selected),
            )
            button.grid(row=index, column=0, sticky="ew", pady=(0, 4))
            self.nav_buttons[name] = button

        footer = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        footer.grid(row=4, column=0, sticky="ew", padx=10, pady=(0, 16))
        self._ui_button(footer, "Configurar", self.open_setup_window, "primary", width=118).pack(fill="x", pady=(0, 8))
        self._ui_button(footer, "Sair", self._on_close, "danger").pack(fill="x")

        self.content = ctk.CTkFrame(self, fg_color=BASE, corner_radius=0)
        self.content.grid(row=0, column=1, sticky="nsew")
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(0, weight=1)

        self.tab_frames = {
            "Menu": ctk.CTkFrame(self.content, fg_color=BASE, corner_radius=0),
            "Busca": ctk.CTkFrame(self.content, fg_color=BASE, corner_radius=0),
            "Analisar vaga": ctk.CTkFrame(self.content, fg_color=BASE, corner_radius=0),
            "Otimizar curriculo": ctk.CTkFrame(self.content, fg_color=BASE, corner_radius=0),
            "Candidaturas": ctk.CTkFrame(self.content, fg_color=BASE, corner_radius=0),
            "Mercado": ctk.CTkFrame(self.content, fg_color=BASE, corner_radius=0),
            "Relatorios": ctk.CTkFrame(self.content, fg_color=BASE, corner_radius=0),
        }
        for frame in self.tab_frames.values():
            frame.grid_columnconfigure(0, weight=1)
            frame.grid_rowconfigure(1, weight=1)

        self._new_home_page(self.tab_frames["Menu"])
        self._new_search_page(self.tab_frames["Busca"])
        self._new_analysis_page(self.tab_frames["Analisar vaga"])
        self._new_optimization_page(self.tab_frames["Otimizar curriculo"])
        self._new_tracker_page(self.tab_frames["Candidaturas"])
        self._new_market_page(self.tab_frames["Mercado"])
        self._new_reports_page(self.tab_frames["Relatorios"])
        self._show_tab("Menu")
        self._refresh_sidebar_status(self.status_text.get())

    def _show_tab(self, name):
        for frame in self.tab_frames.values():
            frame.grid_forget()
        if name == "Menu":
            self.sidebar.grid_remove()
            self.content.grid(row=0, column=0, columnspan=2, sticky="nsew")
        else:
            self.sidebar.grid(row=0, column=0, sticky="nsew")
            self.content.grid(row=0, column=1, columnspan=1, sticky="nsew")
        self.tab_frames[name].grid(row=0, column=0, sticky="nsew")
        self.current_tab = name
        for tab_name, button in self.nav_buttons.items():
            if tab_name == name:
                button.configure(fg_color=C["amber_subtle"], text_color=ACCENT, font=(FONT, 12, "bold"))
            else:
                button.configure(fg_color="transparent", text_color=MUTED, font=(FONT, 12))
        if name == "Relatorios":
            self.refresh_reports()
        elif name == "Candidaturas":
            self.refresh_tracker()
        elif name == "Mercado":
            self.refresh_trends_tab()
        self._refresh_sidebar_context()

    def _new_home_page(self, parent):
        self._page_header(parent, "Job Matcher", "Menu principal com status, atalhos e acesso rapido as areas do app.")
        body = ctk.CTkFrame(parent, fg_color="transparent")
        body.grid(row=1, column=0, sticky="nsew", padx=36, pady=(0, 36))
        body.grid_columnconfigure((0, 1, 2), weight=1)
        body.grid_rowconfigure(3, weight=1)

        self.context_card_var = tk.StringVar(value="Google / Serper")
        status_cards = (
            ("Status", self.status_text, C["green"]),
            ("Proxima busca", self.next_scan_text, TEXT),
            ("Fonte", self.context_card_var, ACCENT),
        )
        for index, (title, variable, accent) in enumerate(status_cards):
            card = self._sidebar_card(title, variable, accent, parent=body)
            card.grid(row=0, column=index, sticky="ew", padx=(0 if index == 0 else 12, 0), pady=(0, 18))
            if index == 0:
                self.status_card = card

        menu_items = (
            ("Busca", "Varredura automatica, busca pontual e logs de execucao."),
            ("Analisar vaga", "Cole uma vaga, veja compatibilidade e registre candidaturas."),
            ("Otimizar curriculo", "Gere uma versao direcionada para uma vaga especifica."),
            ("Candidaturas", "Acompanhe o funil depois de clicar em Registrar em uma analise."),
            ("Mercado", "Leia tendencias a partir das vagas novas encontradas."),
            ("Relatorios", "Abra historicos HTML, Markdown e JSON gerados pelo app."),
        )
        for index, (title, description) in enumerate(menu_items):
            row = 1 + (index // 3)
            column = index % 3
            card = self._ui_card(body)
            card.grid(row=row, column=column, sticky="nsew", padx=(0 if column == 0 else 12, 0), pady=(0 if row == 1 else 12, 0))
            card.grid_columnconfigure(0, weight=1)
            card.grid_rowconfigure(2, weight=1)
            ctk.CTkLabel(card, text=title, font=(FONT, 18, "bold"), text_color=TEXT).grid(row=0, column=0, sticky="w", padx=20, pady=(20, 6))
            ctk.CTkLabel(card, text=description, font=(FONT, 12), text_color=C["text_muted"], wraplength=360, justify="left").grid(row=1, column=0, sticky="nw", padx=20)
            self._ui_button(card, "Abrir", lambda target=title: self._show_tab(target), "ghost", width=92).grid(row=3, column=0, sticky="w", padx=20, pady=(18, 20))

        actions = self._ui_card(body, border_color=ACCENT_DIM)
        actions.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(18, 0))
        actions.grid_columnconfigure(0, weight=1)
        actions.grid_columnconfigure((1, 2, 3, 4), weight=0)
        ctk.CTkLabel(
            actions,
            text="Acoes rapidas",
            font=(FONT, 16, "bold"),
            text_color=TEXT,
        ).grid(row=0, column=0, sticky="w", padx=20, pady=20)
        self._ui_button(actions, "Configurar", self.open_setup_window, "primary", width=150).grid(row=0, column=1, sticky="e", padx=(0, 10), pady=20)
        self._ui_button(actions, "Abrir relatorios", self.open_reports_folder, "ghost", width=150).grid(row=0, column=2, sticky="e", padx=(0, 10), pady=20)
        self._ui_button(actions, "E-mail teste", self.send_test_email, "ghost", width=130).grid(row=0, column=3, sticky="e", padx=(0, 10), pady=20)
        self._ui_button(actions, "Sair", self._on_close, "danger", width=100).grid(row=0, column=4, sticky="e", padx=(0, 20), pady=20)

    def _new_search_page(self, parent):
        self._page_header(parent, "Painel de busca", "Configure a varredura, execute buscas pontuais e acompanhe os eventos importantes.")
        body = ctk.CTkFrame(parent, fg_color="transparent")
        body.grid(row=1, column=0, sticky="nsew", padx=28, pady=(0, 28))
        body.grid_columnconfigure(0, weight=0, minsize=460)
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(0, weight=1)

        params = self._ui_card(body)
        params.grid(row=0, column=0, sticky="new", padx=(0, 16))
        params.grid_columnconfigure(0, weight=1)
        self._section_label(params, "Parametros da varredura", row=0, column=0, padx=18, pady=(16, 12))
        ctk.CTkFrame(params, height=1, fg_color=BORDER, corner_radius=0).grid(row=1, column=0, padx=18, sticky="ew")
        self._field(params, "Vagas por varredura", self.max_jobs, 2, 0, padx=18)
        self._field(params, "Score minimo", self.min_score, 3, 0, padx=18)
        self._field(params, "Intervalo (min)", self.interval, 4, 0, padx=18)
        buttons = ctk.CTkFrame(params, fg_color="transparent")
        buttons.grid(row=5, column=0, sticky="ew", padx=18, pady=(18, 18))
        buttons.grid_columnconfigure((0, 1), weight=1)
        self._ui_button(buttons, "Iniciar monitoramento", self.start_monitoring, "primary").grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        self._ui_button(buttons, "Buscar agora", self.run_once, "ghost").grid(row=1, column=0, sticky="ew", padx=(0, 8))
        self._ui_button(buttons, "E-mail teste", self.send_test_email, "ghost").grid(row=1, column=1, sticky="ew")
        self._ui_button(buttons, "Parar", self.stop_monitoring, "danger").grid(row=2, column=0, columnspan=2, sticky="ew", pady=(8, 0))

        log_card = self._ui_card(body)
        log_card.grid(row=0, column=1, sticky="nsew")
        log_card.grid_columnconfigure(0, weight=1)
        log_card.grid_rowconfigure(1, weight=1)
        log_head = ctk.CTkFrame(log_card, fg_color="transparent")
        log_head.grid(row=0, column=0, sticky="ew", padx=18, pady=(16, 10))
        log_head.grid_columnconfigure(0, weight=1)
        self._section_label(log_head, "Atividade da busca")
        self._ui_button(log_head, "Limpar", self._clear_log, "ghost", width=72).grid(row=0, column=1, sticky="e")
        self.log_box = ctk.CTkTextbox(log_card, fg_color=BG, border_width=1, border_color=BORDER, text_color=C["text_secondary"], font=("Consolas", 11), corner_radius=8, wrap="word")
        self.log_box.grid(row=1, column=0, sticky="nsew", padx=18, pady=(0, 18))
        self.log_box.insert("end", "Pronto. Configure a busca e clique em Iniciar monitoramento ou Buscar agora.\n")
        self.log_box.configure(state="disabled")

    def _new_analysis_page(self, parent):
        self._page_header(parent, "Analisar vaga", "Cole a descricao completa. Titulo e empresa ajudam, mas sao opcionais.")
        body = ctk.CTkFrame(parent, fg_color="transparent")
        body.grid(row=1, column=0, sticky="nsew", padx=28, pady=(0, 28))
        body.grid_columnconfigure(0, weight=1)
        body.grid_columnconfigure(1, weight=0, minsize=360)
        body.grid_rowconfigure(0, weight=1)
        form = self._ui_card(body)
        form.grid(row=0, column=0, sticky="nsew", padx=(0, 16))
        form.grid_columnconfigure((0, 1), weight=1)
        form.grid_rowconfigure(2, weight=1)
        self._field(form, "Titulo da vaga", self.analysis_title, 0, 0, padx=(18, 8))
        self._field(form, "Empresa", self.analysis_company, 0, 1, padx=(8, 18))
        ctk.CTkLabel(form, text="Descricao da vaga", font=(FONT, 11), text_color=C["text_muted"]).grid(row=1, column=0, columnspan=2, sticky="w", padx=18, pady=(16, 6))
        self.analysis_description = self._ui_textbox(form, height=320)
        self.analysis_description.grid(row=2, column=0, columnspan=2, sticky="nsew", padx=18)
        ctk.CTkFrame(form, height=1, fg_color=BORDER, corner_radius=0).grid(row=3, column=0, columnspan=2, sticky="ew", padx=18, pady=(16, 14))
        actions = ctk.CTkFrame(form, fg_color="transparent")
        actions.grid(row=4, column=0, columnspan=2, sticky="ew", padx=18, pady=(0, 18))
        actions.grid_columnconfigure((0, 1, 2, 3), weight=1)
        self.analyze_button = self._ui_button(actions, "Analisar compatibilidade", self.analyze_single_job, "primary")
        self.analyze_button.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.ats_button = self._ui_button(actions, "Simular ATS", self.simulate_ats, "outline")
        self.ats_button.grid(row=0, column=1, sticky="ew", padx=(0, 8))
        self.cover_letter_button = self._ui_button(actions, "Gerar carta", self.generate_cover_letter, "outline")
        self.cover_letter_button.grid(row=0, column=2, sticky="ew", padx=(0, 8))
        self.register_application_button = self._ui_button(actions, "Registrar", self.register_last_application, "ghost")
        self.register_application_button.configure(state="disabled")
        self.register_application_button.grid(row=0, column=3, sticky="ew")
        self._ui_button(actions, "Copiar analise", self.copy_analysis, "ghost").grid(row=1, column=0, sticky="ew", padx=(0, 8), pady=(8, 0))
        self.analysis_optimize_button = self._ui_button(actions, "Otimizar esta vaga", self.use_last_analyzed_job, "ghost")
        self.analysis_optimize_button.configure(state="disabled")
        self.analysis_optimize_button.grid(row=1, column=1, sticky="ew", padx=(0, 8), pady=(8, 0))
        self._ui_button(actions, "Limpar", self.clear_analysis, "ghost").grid(row=1, column=2, sticky="ew", padx=(0, 8), pady=(8, 0))

        result = self._ui_card(body)
        result.grid(row=0, column=1, sticky="nsew")
        result.grid_columnconfigure(0, weight=1)
        result.grid_rowconfigure(1, weight=1)
        self._section_label(result, "Resultado", row=0, column=0, padx=18, pady=(18, 10))
        self.analysis_result_box = ctk.CTkTextbox(result, fg_color=BG, border_width=1, border_color=BORDER, text_color=C["text_secondary"], font=(FONT, 12), corner_radius=8, wrap="word")
        self.analysis_result_box.grid(row=1, column=0, sticky="nsew", padx=18, pady=(0, 18))
        self.analysis_result_box.insert("end", "A analise vai aparecer aqui.\n\nO app vai mostrar compatibilidade, pontos fortes, gaps e melhorias recomendadas para o curriculo atual.\n")
        self.analysis_result_box.configure(state="disabled")

    def _new_optimization_page(self, parent):
        header = self._page_header(parent, "Otimizar curriculo", "Direcione seu curriculo para uma vaga sem inventar experiencia.")
        self._ui_button(header, "Usar vaga analisada", self.use_last_analyzed_job, "ghost", width=180).grid(row=0, column=1, rowspan=2, sticky="e", padx=(18, 0))
        body = ctk.CTkFrame(parent, fg_color="transparent")
        body.grid(row=1, column=0, sticky="nsew", padx=28, pady=(0, 28))
        body.grid_columnconfigure(0, weight=1)
        body.grid_columnconfigure(1, weight=0, minsize=400)
        body.grid_rowconfigure(0, weight=1)
        form = self._ui_card(body)
        form.grid(row=0, column=0, sticky="nsew", padx=(0, 16))
        form.grid_columnconfigure((0, 1), weight=1)
        form.grid_rowconfigure(2, weight=1)
        self._field(form, "Titulo da vaga", self.optimization_title, 0, 0, padx=(18, 8))
        self._field(form, "Empresa", self.optimization_company, 0, 1, padx=(8, 18))
        ctk.CTkLabel(form, text="Descricao da vaga", font=(FONT, 11), text_color=C["text_muted"]).grid(row=1, column=0, columnspan=2, sticky="w", padx=18, pady=(16, 6))
        self.optimization_description = self._ui_textbox(form, height=320)
        self.optimization_description.grid(row=2, column=0, columnspan=2, sticky="nsew", padx=18)
        actions = ctk.CTkFrame(form, fg_color="transparent")
        actions.grid(row=3, column=0, columnspan=2, sticky="ew", padx=18, pady=18)
        actions.grid_columnconfigure((0, 1, 2), weight=1)
        self.optimize_button = self._ui_button(actions, "Gerar otimizacao", self.optimize_resume, "primary")
        self.optimize_button.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self._ui_button(actions, "Copiar otimizacao", self.copy_optimization, "ghost").grid(row=0, column=1, sticky="ew", padx=(0, 8))
        self._ui_button(actions, "Limpar", self.clear_optimization, "ghost").grid(row=0, column=2, sticky="ew")
        result = self._ui_card(body)
        result.grid(row=0, column=1, sticky="nsew")
        result.grid_columnconfigure(0, weight=1)
        result.grid_rowconfigure(1, weight=1)
        self._section_label(result, "Curriculo direcionado", row=0, column=0, padx=18, pady=(18, 10))
        self.optimization_result_box = ctk.CTkTextbox(result, fg_color=BG, border_width=1, border_color=BORDER, text_color=C["text_secondary"], font=(FONT, 12), corner_radius=8, wrap="word")
        self.optimization_result_box.grid(row=1, column=0, sticky="nsew", padx=18, pady=(0, 18))
        self.optimization_result_box.insert("end", "A otimizacao vai aparecer aqui.\n\nO app vai sugerir headline, resumo, skills, bullets e alertas de honestidade.\n")
        self.optimization_result_box.configure(state="disabled")

    def _new_tracker_page(self, parent):
        header = self._page_header(
            parent,
            "Candidaturas",
            "Acompanhe o funil, registre contatos e organize proximas acoes. Para adicionar uma vaga aqui, analise uma vaga e clique em Registrar.",
        )
        self._ui_button(header, "Atualizar", self.refresh_tracker, "ghost", width=110).grid(row=0, column=1, rowspan=2, sticky="e", padx=(18, 0))
        body = ctk.CTkFrame(parent, fg_color="transparent")
        body.grid(row=1, column=0, sticky="nsew", padx=28, pady=(0, 28))
        body.grid_columnconfigure(0, weight=1)
        body.grid_columnconfigure(1, weight=0, minsize=320)
        body.grid_rowconfigure(1, weight=1)
        self.tracker_metrics = ctk.CTkFrame(body, fg_color="transparent")
        self.tracker_metrics.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 14))
        self.tracker_metrics.grid_columnconfigure((0, 1, 2, 3), weight=1)
        self.tracker_board = ctk.CTkFrame(body, fg_color="transparent")
        self.tracker_board.grid(row=1, column=0, sticky="nsew", padx=(0, 16))
        self.tracker_board.grid_columnconfigure(tuple(range(len(STATUS_ORDER))), weight=1)
        self.tracker_board.grid_rowconfigure(1, weight=1)
        self.tracker_columns = {}
        for index, status in enumerate(STATUS_ORDER):
            ctk.CTkLabel(self.tracker_board, text=STATUS_LABELS[status].upper(), font=(FONT, 10, "bold"), text_color=C["text_muted"]).grid(row=0, column=index, sticky="w", padx=(0 if index == 0 else 8, 0), pady=(0, 8))
            col = ctk.CTkScrollableFrame(self.tracker_board, fg_color=SURFACE, border_width=1, border_color=BORDER, corner_radius=8, scrollbar_button_color=C["border"], scrollbar_button_hover_color=C["border_bright"])
            col.grid(row=1, column=index, sticky="nsew", padx=(0 if index == 0 else 8, 0))
            self.tracker_columns[status] = col
        self.tracker_detail = self._ui_card(body)
        self.tracker_detail.grid(row=1, column=1, sticky="nsew")
        self.tracker_detail.grid_columnconfigure(0, weight=1)
        self._section_label(self.tracker_detail, "Detalhes", row=0, column=0, padx=18, pady=(18, 10))
        self.tracker_detail_title = ctk.CTkLabel(self.tracker_detail, text="Selecione uma candidatura.", font=(FONT, 13), text_color=MUTED, wraplength=280, justify="left")
        self.tracker_detail_title.grid(row=1, column=0, padx=18, pady=(0, 14), sticky="ew")
        self.tracker_contact = tk.StringVar()
        self.tracker_next_action = tk.StringVar()
        self._tracker_entry("Contato", self.tracker_contact, 2)
        self._tracker_entry("Proxima acao", self.tracker_next_action, 3)
        ctk.CTkLabel(self.tracker_detail, text="Notas", text_color=C["text_muted"], font=(FONT, 11)).grid(row=4, column=0, padx=18, sticky="w")
        self.tracker_notes = self._ui_textbox(self.tracker_detail, height=110)
        self.tracker_notes.grid(row=5, column=0, sticky="ew", padx=18, pady=(6, 12))
        self._ui_button(self.tracker_detail, "Salvar detalhes", self.save_tracker_details, "primary").grid(row=6, column=0, sticky="ew", padx=18, pady=(0, 12))
        self.tracker_move_frame = ctk.CTkFrame(self.tracker_detail, fg_color="transparent")
        self.tracker_move_frame.grid(row=7, column=0, sticky="ew", padx=18, pady=(0, 18))
        self.tracker_move_frame.grid_columnconfigure(0, weight=1)
        self.refresh_tracker()

    def _new_market_page(self, parent):
        header = self._page_header(parent, "Mercado", "Transforme as vagas encontradas em leitura de tendencia.")
        self.market_button = self._ui_button(header, "Gerar relatorio de mercado", self.generate_market_trends, "primary", width=210)
        self.market_button.grid(row=0, column=1, rowspan=2, sticky="e", padx=(18, 0))
        body = ctk.CTkFrame(parent, fg_color="transparent")
        body.grid(row=1, column=0, sticky="nsew", padx=28, pady=(0, 28))
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(1, weight=1)
        market = self._ui_card(body, border_color=ACCENT_DIM)
        market.grid(row=0, column=0, sticky="ew", pady=(0, 16))
        market.grid_columnconfigure(0, weight=1)
        self.market_new_jobs = tk.StringVar(value="Vagas novas para tendencias: -")
        ctk.CTkLabel(market, text="VAGAS NOVAS PARA ANALISE", font=(FONT, 10, "bold"), text_color=C["text_muted"]).grid(row=0, column=0, sticky="w", padx=18, pady=(16, 2))
        self.market_badge = ctk.CTkLabel(market, text="- novas", fg_color=C["amber_subtle"], text_color=ACCENT, font=(FONT, 12, "bold"), corner_radius=6)
        self.market_badge.grid(row=0, column=1, rowspan=2, padx=18, pady=16, sticky="e")
        self.market_total_label = ctk.CTkLabel(market, text="Historico local", text_color=TEXT, font=(FONT, 20, "bold"))
        self.market_total_label.grid(row=1, column=0, sticky="w", padx=18, pady=(0, 16))
        progress = self._ui_card(body)
        progress.grid(row=1, column=0, sticky="nsew")
        progress.grid_columnconfigure(0, weight=1)
        progress.grid_rowconfigure(1, weight=1)
        self._section_label(progress, "Progresso", row=0, column=0, padx=18, pady=(18, 10))
        self.market_log = ctk.CTkTextbox(progress, fg_color=BG, border_width=1, border_color=BORDER, text_color=C["text_secondary"], font=("Consolas", 11), corner_radius=8, wrap="word")
        self.market_log.grid(row=1, column=0, sticky="nsew", padx=18, pady=(0, 18))
        self.market_log.insert("end", "Aguardando geracao de relatorio.\n")
        self.market_log.configure(state="disabled")
        self.refresh_trends_tab()

    def _new_reports_page(self, parent):
        header = self._page_header(parent, "Relatorios", "Historico local das varreduras, analises manuais e otimizacoes.")
        self._ui_button(header, "Atualizar", self.refresh_reports, "ghost", width=110).grid(row=0, column=1, rowspan=2, sticky="e", padx=(18, 0))
        body = self._ui_card(parent)
        body.grid(row=1, column=0, sticky="nsew", padx=28, pady=(0, 28))
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(0, weight=1)
        self.reports_list = ctk.CTkScrollableFrame(body, fg_color="transparent", scrollbar_button_color=C["border"], scrollbar_button_hover_color=C["border_bright"])
        self.reports_list.grid(row=0, column=0, sticky="nsew", padx=18, pady=18)
        self.reports_list.grid_columnconfigure(0, weight=1)

    def _set_analysis_result(self, text):
        self.analysis_result_box.configure(state="normal")
        self.analysis_result_box.delete("1.0", "end")
        self.analysis_result_box.insert("end", text)
        self.analysis_result_box.configure(state="disabled")

    def _set_optimization_result(self, text):
        self.optimization_result_box.configure(state="normal")
        self.optimization_result_box.delete("1.0", "end")
        self.optimization_result_box.insert("end", text)
        self.optimization_result_box.configure(state="disabled")

    def _scan_once_worker(self):
        self._set_status("Varredura unica")
        try:
            engine.run_scan(max_jobs_override=int(self.max_jobs.get()), should_stop=self.stop_event.is_set)
        finally:
            self._set_status("Pronto")
            self._set_next_scan("-")

    def _monitor_loop(self):
        self._set_status("Monitorando")
        logging.info("Monitoramento iniciado pela interface desktop.")

        while not self.stop_event.is_set():
            engine.run_scan(max_jobs_override=int(self.max_jobs.get()), should_stop=self.stop_event.is_set)
            if self.stop_event.is_set():
                break

            seconds = max(1, int(self.interval.get()) * 60)
            next_at = time.strftime("%H:%M:%S", time.localtime(time.time() + seconds))
            self._set_next_scan(next_at)
            minutes = max(1, int(self.interval.get()))
            logging.info(
                "Proxima tentativa em %s minuto(s), por volta de %s. "
                "Se nao quiser aguardar, clique em Parar e depois feche o app.",
                minutes,
                next_at,
            )
            for _ in range(seconds):
                if self.stop_event.is_set():
                    break
                time.sleep(1)

        self._set_status("Pronto")
        self._set_next_scan("-")
        logging.info("Monitoramento parado.")

    def _send_email_worker(self):
        self._set_status("Enviando e-mail")
        try:
            engine.send_startup_email(
                engine.EMAIL_REMETENTE,
                engine.EMAIL_SENHA_APP,
                engine.EMAIL_DESTINATARIO,
                engine.get_search_queries(),
                int(self.min_score.get()),
            )
            logging.info("E-mail de teste enviado para %s", engine.EMAIL_DESTINATARIO)
        finally:
            self._set_status("Pronto")

    def _clear_log(self):
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.insert("end", "Log limpo. Aguardando nova atividade.\n")
        self.log_box.configure(state="disabled")

    def _append_log(self, level, stamp, message):
        prefix = "[OK]" if level == "INFO" else f"[{level}]"
        if "concluida" in message.lower() or "enviado" in message.lower():
            prefix = "[OK]"
        self.log_box.configure(state="normal")
        self.log_box.insert("end", f"{stamp}  {prefix}  {message}\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def _refresh_log(self):
        try:
            while True:
                level, stamp, message = self.messages.get_nowait()
                self._append_log(level, stamp, message)
        except queue.Empty:
            pass
        self.after(200, self._refresh_log)

    def _on_close(self):
        if self.worker and self.worker.is_alive():
            if not messagebox.askyesno("Sair", "Existe uma tarefa em execucao. Deseja parar e sair?"):
                return
            self.stop_event.set()
        self.destroy()


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        app = JobMatcherApp()
        app.withdraw()
        app.update_idletasks()
        app.update()
        app.destroy()
        raise SystemExit(0)

    app = JobMatcherApp()
    app.mainloop()
