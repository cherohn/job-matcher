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
from core.user_config import get_config_path, import_user_file, load_user_config, save_user_config


BG = "#0F0F0F"
BASE = "#181818"
SURFACE = "#202020"
SURFACE_2 = "#2A2A2A"
BORDER = "#303030"
ACCENT = "#C49A3C"
ACCENT_DIM = "#8E6E2B"
TEXT = "#DCDCDC"
MUTED = "#6A6A6A"
DANGER = "#9E3B3B"
DANGER_DARK = "#3A1B1B"


def resource_path(relative_path):
    base_path = getattr(sys, "_MEIPASS", os.path.abspath("."))
    return os.path.join(base_path, relative_path)


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
        ctk.set_default_color_theme("blue")

        super().__init__(fg_color=BG)
        self.title("Job Matcher")
        self.geometry("1170x770")
        self.minsize(1030, 670)
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
        self.last_analysis_text = ""
        self.last_job_context = None
        self.optimization_status = tk.StringVar(value="Cole uma vaga e gere uma otimizacao.")
        self.optimization_title = tk.StringVar()
        self.optimization_company = tk.StringVar()
        self.optimization_worker = None
        self.last_optimization_text = ""
        self.report_rows = []
        self.nav_buttons = {}
        self.tab_frames = {}
        self.current_tab = "Busca"

        self._set_window_icon()
        self._configure_logging()
        self._build_layout()
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

    def _build_layout(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.sidebar = ctk.CTkFrame(self, width=205, corner_radius=0, fg_color=BG)
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_rowconfigure(7, weight=1)

        brand = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        brand.grid(row=0, column=0, padx=20, pady=(22, 26), sticky="ew")
        logo = self._load_logo()
        if logo:
            ctk.CTkLabel(brand, image=logo, text="").pack(side="left", padx=(0, 12))
            self._logo = logo
        title = ctk.CTkFrame(brand, fg_color="transparent")
        title.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(title, text="Job Matcher", font=("Segoe UI", 18, "bold"), text_color=TEXT).pack(anchor="w")
        ctk.CTkLabel(title, text="Monitoramento", font=("Segoe UI", 12), text_color=MUTED).pack(anchor="w", pady=(1, 0))

        self.status_card = self._sidebar_card("Status", self.status_text, accent=ACCENT)
        self.status_card.grid(row=1, column=0, padx=16, pady=(0, 16), sticky="ew")
        self._sidebar_card("Proxima busca", self.next_scan_text, accent=TEXT).grid(row=2, column=0, padx=16, pady=(0, 16), sticky="ew")
        self._static_sidebar_card("Fonte", "Google/Serper", accent=ACCENT).grid(row=3, column=0, padx=16, pady=(0, 16), sticky="ew")

        ctk.CTkButton(
            self.sidebar,
            text="Configurar",
            height=42,
            corner_radius=8,
            fg_color=ACCENT,
            hover_color=ACCENT_DIM,
            text_color=BG,
            border_width=1,
            border_color=ACCENT,
            command=self.open_setup_window,
        ).grid(row=4, column=0, padx=16, pady=(0, 16), sticky="ew")

        ctk.CTkButton(
            self.sidebar,
            text="Abrir relatorios",
            height=42,
            corner_radius=8,
            fg_color=SURFACE,
            hover_color=SURFACE_2,
            text_color=TEXT,
            border_width=1,
            border_color=BORDER,
            command=self.open_reports_folder,
        ).grid(row=8, column=0, padx=16, pady=(0, 10), sticky="ew")
        ctk.CTkButton(
            self.sidebar,
            text="Sair",
            height=42,
            corner_radius=8,
            fg_color=DANGER_DARK,
            hover_color=DANGER,
            text_color=TEXT,
            border_width=1,
            border_color=DANGER,
            command=self._on_close,
        ).grid(row=9, column=0, padx=16, pady=(0, 20), sticky="ew")

        content = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        content.grid(row=0, column=1, sticky="nsew", padx=0, pady=0)
        content.grid_columnconfigure(0, weight=1)
        content.grid_rowconfigure(0, weight=1)

        shell = ctk.CTkFrame(content, fg_color=BG, corner_radius=0)
        shell.grid(row=0, column=0, sticky="nsew", padx=18, pady=18)
        shell.grid_columnconfigure(0, weight=1)
        shell.grid_rowconfigure(1, weight=1)

        nav = ctk.CTkFrame(shell, fg_color="transparent")
        nav.grid(row=0, column=0, padx=26, pady=(0, 14), sticky="ew")
        nav.grid_columnconfigure(4, weight=1)
        self._nav_button(nav, 0, "Busca")
        self._nav_button(nav, 1, "Analisar vaga")
        self._nav_button(nav, 2, "Otimizar curriculo")
        self._nav_button(nav, 3, "Relatorios")

        tab_area = ctk.CTkFrame(shell, fg_color=BG, corner_radius=0)
        tab_area.grid(row=1, column=0, sticky="nsew")
        tab_area.grid_columnconfigure(0, weight=1)
        tab_area.grid_rowconfigure(0, weight=1)

        search_tab = ctk.CTkFrame(tab_area, fg_color=BG, corner_radius=0)
        analysis_tab = ctk.CTkFrame(tab_area, fg_color=BG, corner_radius=0)
        optimization_tab = ctk.CTkFrame(tab_area, fg_color=BG, corner_radius=0)
        reports_tab = ctk.CTkFrame(tab_area, fg_color=BG, corner_radius=0)
        self.tab_frames = {
            "Busca": search_tab,
            "Analisar vaga": analysis_tab,
            "Otimizar curriculo": optimization_tab,
            "Relatorios": reports_tab,
        }

        main = search_tab
        main.configure(fg_color=BG)
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(3, weight=1)

        header = ctk.CTkFrame(main, fg_color="transparent")
        header.grid(row=0, column=0, padx=26, pady=(26, 16), sticky="ew")
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            header,
            text="Painel de busca",
            font=("Segoe UI", 26, "bold"),
            text_color=TEXT,
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            header,
            text="Configure a varredura, execute buscas pontuais e acompanhe os eventos importantes.",
            font=("Segoe UI", 13),
            text_color=MUTED,
        ).grid(row=1, column=0, pady=(6, 0), sticky="w")

        settings = ctk.CTkFrame(main, fg_color=BASE, corner_radius=10, border_width=1, border_color=BORDER)
        settings.grid(row=1, column=0, padx=26, pady=(0, 16), sticky="ew")
        settings.grid_columnconfigure((0, 1, 2), weight=1)
        settings.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(settings, text="Parametros da varredura", font=("Segoe UI", 15, "bold"), text_color=TEXT).grid(
            row=0, column=0, columnspan=3, padx=14, pady=(14, 0), sticky="w"
        )
        self._number_field(settings, 0, "Vagas por varredura", self.max_jobs)
        self._number_field(settings, 1, "Score minimo", self.min_score)
        self._number_field(settings, 2, "Intervalo (min)", self.interval)

        actions = ctk.CTkFrame(main, fg_color="transparent")
        actions.grid(row=2, column=0, padx=26, pady=(0, 16), sticky="ew")
        actions.grid_columnconfigure((0, 1, 2, 3), weight=1)
        self._action_button(actions, 0, "Iniciar monitoramento", self.start_monitoring, primary=True)
        self._action_button(actions, 1, "Buscar agora", self.run_once)
        self._action_button(actions, 2, "Parar", self.stop_monitoring, danger=True)
        self._action_button(actions, 3, "E-mail teste", self.send_test_email)

        log_panel = ctk.CTkFrame(main, fg_color=BASE, corner_radius=10, border_width=1, border_color=BORDER)
        log_panel.grid(row=3, column=0, padx=26, pady=(0, 24), sticky="nsew")
        log_panel.grid_columnconfigure(0, weight=1)
        log_panel.grid_rowconfigure(1, weight=1)

        log_header = ctk.CTkFrame(log_panel, fg_color="transparent")
        log_header.grid(row=0, column=0, padx=18, pady=(16, 8), sticky="ew")
        log_header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(log_header, text="Atividade da busca", font=("Segoe UI", 17, "bold"), text_color=TEXT).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(log_header, text="Eventos filtrados para mostrar apenas o que importa.", font=("Segoe UI", 12), text_color=MUTED).grid(row=1, column=0, sticky="w")
        ctk.CTkButton(
            log_header,
            text="Limpar",
            width=92,
            height=34,
            corner_radius=8,
            fg_color=SURFACE,
            hover_color=SURFACE_2,
            text_color=TEXT,
            border_width=1,
            border_color=SURFACE_2,
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
        self._build_reports_tab(reports_tab)
        self._show_tab("Busca")

    def _nav_button(self, parent, column, name):
        button = ctk.CTkButton(
            parent,
            text=name,
            height=38,
            width=156 if name == "Otimizar curriculo" else 132 if name == "Analisar vaga" else 100 if name == "Relatorios" else 86,
            corner_radius=8,
            fg_color=SURFACE,
            hover_color=SURFACE_2,
            text_color=TEXT,
            border_width=1,
            border_color=BORDER,
            font=("Segoe UI", 12, "bold"),
            command=lambda: self._show_tab(name),
        )
        button.grid(row=0, column=column, padx=(0, 8), sticky="w")
        self.nav_buttons[name] = button

    def _show_tab(self, name):
        for frame in self.tab_frames.values():
            frame.grid_forget()
        self.tab_frames[name].grid(row=0, column=0, sticky="nsew")
        if name == "Relatorios":
            self.refresh_reports()
        self.current_tab = name

        for tab_name, button in self.nav_buttons.items():
            if tab_name == name:
                button.configure(
                    fg_color=ACCENT,
                    hover_color=ACCENT_DIM,
                    text_color=BG,
                    border_color=ACCENT,
                )
            else:
                button.configure(
                    fg_color=SURFACE,
                    hover_color=SURFACE_2,
                    text_color=TEXT,
                    border_color=BORDER,
                )

    def _build_analysis_tab(self, parent):
        parent.configure(fg_color=BG)
        parent.grid_columnconfigure(0, weight=6)
        parent.grid_columnconfigure(1, weight=5)
        parent.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(parent, fg_color="transparent")
        header.grid(row=0, column=0, columnspan=2, padx=26, pady=(26, 16), sticky="ew")
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            header,
            text="Analisar vaga",
            font=("Segoe UI", 26, "bold"),
            text_color=TEXT,
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            header,
            textvariable=self.analysis_status,
            font=("Segoe UI", 13),
            text_color=MUTED,
        ).grid(row=1, column=0, pady=(6, 0), sticky="w")

        form = ctk.CTkFrame(parent, fg_color=BASE, corner_radius=10, border_width=1, border_color=BORDER)
        form.grid(row=1, column=0, padx=(26, 10), pady=(0, 24), sticky="nsew")
        form.grid_columnconfigure((0, 1), weight=1)
        form.grid_rowconfigure(3, weight=1)

        ctk.CTkLabel(
            form,
            text="Dados da vaga",
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
        ctk.CTkLabel(desc_frame, text="Descricao da vaga", text_color=MUTED, font=("Segoe UI", 12)).grid(row=0, column=0, sticky="w")
        self.analysis_description = ctk.CTkTextbox(
            desc_frame,
            height=260,
            corner_radius=7,
            fg_color=BG,
            border_width=1,
            border_color=BORDER,
            text_color=TEXT,
            font=("Segoe UI", 12),
            wrap="word",
        )
        self.analysis_description.grid(row=1, column=0, sticky="nsew", pady=(6, 0))

        actions = ctk.CTkFrame(form, fg_color="transparent")
        actions.grid(row=4, column=0, columnspan=2, padx=18, pady=(0, 18), sticky="ew")
        actions.grid_columnconfigure((0, 1, 2, 3, 4), weight=1)
        self.analyze_button = ctk.CTkButton(
            actions,
            text="Analisar compatibilidade",
            height=38,
            corner_radius=8,
            fg_color=ACCENT,
            hover_color=ACCENT_DIM,
            text_color=BG,
            command=self.analyze_single_job,
        )
        self.analyze_button.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.ats_button = ctk.CTkButton(
            actions,
            text="Simular ATS",
            height=38,
            corner_radius=8,
            fg_color=SURFACE,
            hover_color=SURFACE_2,
            text_color=TEXT,
            border_width=1,
            border_color=SURFACE_2,
            command=self.simulate_ats,
        )
        self.ats_button.grid(row=0, column=1, sticky="ew", padx=(0, 8))
        ctk.CTkButton(
            actions,
            text="Copiar analise",
            height=38,
            corner_radius=8,
            fg_color=SURFACE,
            hover_color=SURFACE_2,
            text_color=TEXT,
            border_width=1,
            border_color=SURFACE_2,
            command=self.copy_analysis,
        ).grid(row=0, column=2, sticky="ew", padx=(0, 8))
        self.analysis_optimize_button = ctk.CTkButton(
            actions,
            text="Otimizar esta vaga",
            height=38,
            corner_radius=8,
            fg_color=SURFACE,
            hover_color=SURFACE_2,
            text_color=TEXT,
            border_width=1,
            border_color=SURFACE_2,
            state="disabled",
            command=self.use_last_analyzed_job,
        )
        self.analysis_optimize_button.grid(row=0, column=3, sticky="ew", padx=(0, 8))
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
        ).grid(row=0, column=4, sticky="ew")

        result_panel = ctk.CTkFrame(parent, fg_color=BASE, corner_radius=10, border_width=1, border_color=BORDER)
        result_panel.grid(row=1, column=1, padx=(10, 26), pady=(0, 24), sticky="nsew")
        result_panel.grid_columnconfigure(0, weight=1)
        result_panel.grid_rowconfigure(1, weight=1)
        result_header = ctk.CTkFrame(result_panel, fg_color="transparent")
        result_header.grid(row=0, column=0, padx=18, pady=(18, 8), sticky="ew")
        result_header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            result_header,
            text="Resultado",
            font=("Segoe UI", 17, "bold"),
            text_color=TEXT,
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
        parent.configure(fg_color=BG)
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
            font=("Segoe UI", 26, "bold"),
            text_color=TEXT,
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            header,
            textvariable=self.optimization_status,
            font=("Segoe UI", 13),
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
            border_color=BORDER,
            font=("Segoe UI", 12, "bold"),
            command=self.use_last_analyzed_job,
        ).grid(row=0, column=1, rowspan=2, padx=(20, 0), sticky="e")

        form = ctk.CTkFrame(parent, fg_color=BASE, corner_radius=10, border_width=1, border_color=BORDER)
        form.grid(row=1, column=0, padx=(26, 10), pady=(0, 24), sticky="nsew")
        form.grid_columnconfigure((0, 1), weight=1)
        form.grid_rowconfigure(2, weight=1, minsize=170)

        form_header = ctk.CTkFrame(form, fg_color="transparent")
        form_header.grid(row=0, column=0, columnspan=2, padx=18, pady=(18, 10), sticky="ew")
        form_header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            form_header,
            text="Vaga alvo",
            font=("Segoe UI", 18, "bold"),
            text_color=TEXT,
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            form_header,
            text="Use a ultima vaga analisada ou cole uma descricao nova para direcionar o curriculo.",
            font=("Segoe UI", 12),
            text_color=MUTED,
            justify="left",
        ).grid(row=1, column=0, columnspan=2, pady=(5, 0), sticky="w")

        self._text_field(form, 1, 0, "Titulo da vaga", self.optimization_title)
        self._text_field(form, 1, 1, "Empresa", self.optimization_company)

        desc_frame = ctk.CTkFrame(form, fg_color="transparent")
        desc_frame.grid(row=2, column=0, columnspan=2, padx=18, pady=(0, 14), sticky="nsew")
        desc_frame.grid_columnconfigure(0, weight=1)
        desc_frame.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(desc_frame, text="Descricao da vaga", text_color=MUTED, font=("Segoe UI", 12)).grid(row=0, column=0, sticky="w")
        self.optimization_description = ctk.CTkTextbox(
            desc_frame,
            height=260,
            corner_radius=7,
            fg_color=BG,
            border_width=1,
            border_color=BORDER,
            text_color=TEXT,
            font=("Segoe UI", 12),
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
            height=38,
            corner_radius=8,
            fg_color=SURFACE,
            hover_color=SURFACE_2,
            text_color=TEXT,
            border_width=1,
            border_color=SURFACE_2,
            command=self.clear_optimization,
        ).grid(row=0, column=2, sticky="ew")

        result_panel = ctk.CTkFrame(parent, fg_color=BASE, corner_radius=10, border_width=1, border_color=BORDER)
        result_panel.grid(row=1, column=1, padx=(10, 26), pady=(0, 24), sticky="nsew")
        result_panel.grid_columnconfigure(0, weight=1)
        result_panel.grid_rowconfigure(1, weight=1)
        result_header = ctk.CTkFrame(result_panel, fg_color="transparent")
        result_header.grid(row=0, column=0, padx=18, pady=(18, 8), sticky="ew")
        result_header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            result_header,
            text="Curriculo direcionado",
            font=("Segoe UI", 17, "bold"),
            text_color=TEXT,
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            result_header,
            text="Sugestoes editaveis, baseadas no que ja existe no perfil.",
            font=("Segoe UI", 12),
            text_color=MUTED,
        ).grid(row=1, column=0, sticky="w")

        self.optimization_result_box = ctk.CTkTextbox(
            result_panel,
            corner_radius=8,
            fg_color=BG,
            border_width=1,
            border_color=BORDER,
            text_color=TEXT,
            font=("Segoe UI", 12),
            wrap="word",
        )
        self.optimization_result_box.grid(row=1, column=0, padx=18, pady=(0, 18), sticky="nsew")
        self.optimization_result_box.insert(
            "end",
            "A otimizacao vai aparecer aqui.\n\n"
            "O app vai sugerir headline, resumo, skills, bullets e alertas de honestidade.\n",
        )
        self.optimization_result_box.configure(state="disabled")

    def _build_reports_tab(self, parent):
        parent.configure(fg_color=BG)
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(parent, fg_color="transparent")
        header.grid(row=0, column=0, padx=26, pady=(26, 16), sticky="ew")
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            header,
            text="Relatorios",
            font=("Segoe UI", 26, "bold"),
            text_color=TEXT,
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            header,
            text="Historico local das varreduras, analises manuais e otimizacoes de curriculo.",
            font=("Segoe UI", 13),
            text_color=MUTED,
        ).grid(row=1, column=0, pady=(6, 0), sticky="w")
        ctk.CTkButton(
            header,
            text="Atualizar",
            width=110,
            height=36,
            corner_radius=8,
            fg_color=SURFACE,
            hover_color=SURFACE_2,
            text_color=TEXT,
            border_width=1,
            border_color=BORDER,
            command=self.refresh_reports,
        ).grid(row=0, column=1, rowspan=2, sticky="e")

        panel = ctk.CTkFrame(parent, fg_color=BASE, corner_radius=10, border_width=1, border_color=BORDER)
        panel.grid(row=1, column=0, padx=26, pady=(0, 24), sticky="nsew")
        panel.grid_columnconfigure(0, weight=1)
        panel.grid_rowconfigure(0, weight=1)

        self.reports_list = ctk.CTkScrollableFrame(panel, fg_color="transparent")
        self.reports_list.grid(row=0, column=0, padx=18, pady=18, sticky="nsew")
        self.reports_list.grid_columnconfigure(0, weight=1)

    def _text_field(self, parent, row, column, label, variable):
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.grid(row=row, column=column, padx=14, pady=14, sticky="ew")
        frame.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(frame, text=label, text_color=MUTED, font=("Segoe UI", 12)).grid(row=0, column=0, sticky="w")
        ctk.CTkEntry(
            frame,
            textvariable=variable,
            height=36,
            corner_radius=7,
            fg_color=BG,
            border_color=BORDER,
            text_color=TEXT,
            font=("Segoe UI", 13),
        ).grid(row=1, column=0, sticky="ew", pady=(6, 0))

    def open_setup_window(self):
        data = load_user_config()
        window = ctk.CTkToplevel(self)
        window.title("Configurar Job Matcher")
        window.geometry("1090x810")
        window.minsize(990, 710)
        window.transient(self)
        window.grab_set()
        self._set_setup_window_style(window)
        window.after(100, lambda: self._set_setup_window_style(window))

        window.grid_columnconfigure(0, weight=1)
        window.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(window, fg_color=BG, corner_radius=0)
        header.grid(row=0, column=0, sticky="ew", padx=22, pady=(18, 10))
        header.grid_columnconfigure(0, weight=1)

        title_block = ctk.CTkFrame(header, fg_color="transparent")
        title_block.grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            title_block,
            text="Configuracao do usuario",
            font=("Segoe UI", 24, "bold"),
            text_color=TEXT,
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            title_block,
            text=f"Arquivo local: {get_config_path()}",
            font=("Segoe UI", 11),
            text_color=MUTED,
        ).grid(row=1, column=0, sticky="w", pady=(3, 0))

        body = ctk.CTkScrollableFrame(window, fg_color=BG)
        body.grid(row=1, column=0, sticky="nsew", padx=22, pady=(0, 18))
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
        actions.grid(row=0, column=1, sticky="e")
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

    def _sidebar_card(self, title, value_var, accent):
        frame = ctk.CTkFrame(self.sidebar, fg_color=SURFACE, corner_radius=10, border_width=1, border_color=BORDER)
        ctk.CTkLabel(frame, text=title, text_color=MUTED, font=("Segoe UI", 12)).pack(anchor="w", padx=14, pady=(12, 2))
        ctk.CTkLabel(frame, textvariable=value_var, text_color=accent, font=("Segoe UI", 15, "bold")).pack(anchor="w", padx=14, pady=(0, 12))
        return frame

    def _static_sidebar_card(self, title, value, accent):
        var = tk.StringVar(value=value)
        return self._sidebar_card(title, var, accent)

    def _number_field(self, parent, column, label, variable):
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.grid(row=1, column=column, padx=14, pady=14, sticky="ew")
        ctk.CTkLabel(frame, text=label, text_color=MUTED, font=("Segoe UI", 12)).pack(anchor="w")
        ctk.CTkEntry(
            frame,
            textvariable=variable,
            height=36,
            corner_radius=7,
            fg_color=BG,
            border_color=BORDER,
            text_color=TEXT,
            font=("Segoe UI", 13),
        ).pack(fill="x", pady=(6, 0))

    def _action_button(self, parent, column, text, command, primary=False, danger=False):
        fg = ACCENT if primary else SURFACE
        hover = ACCENT_DIM if primary else SURFACE_2
        text_color = BG if primary else TEXT
        border_color = ACCENT if primary else SURFACE_2
        if danger:
            fg = DANGER
            hover = DANGER_DARK
            text_color = TEXT
            border_color = DANGER
        ctk.CTkButton(
            parent,
            text=text,
            height=34,
            corner_radius=8,
            fg_color=fg,
            hover_color=hover,
            text_color=text_color,
            border_width=1,
            border_color=border_color,
            font=("Segoe UI", 12, "bold"),
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

    def clear_analysis(self):
        self.analysis_title.set("")
        self.analysis_company.set("")
        self.analysis_description.delete("1.0", "end")
        self.last_analysis_text = ""
        self.last_job_context = None
        if hasattr(self, "analysis_optimize_button"):
            self.analysis_optimize_button.configure(state="disabled")
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
            row.grid_columnconfigure(0, weight=1)

            title = report.get("title") or "Relatorio"
            company = report.get("company") or ""
            score = report.get("score")
            title_line = title if not company else f"{title} @ {company}"
            if score is not None:
                title_line = f"{score}% - {title_line}"

            ctk.CTkLabel(
                row,
                text=title_line,
                text_color=TEXT,
                font=("Segoe UI", 14, "bold"),
                anchor="w",
            ).grid(row=0, column=0, padx=14, pady=(12, 2), sticky="ew")
            ctk.CTkLabel(
                row,
                text=f"{report.get('detail', '')} | {report.get('created_at', '')}",
                text_color=MUTED,
                font=("Segoe UI", 12),
                anchor="w",
            ).grid(row=1, column=0, padx=14, pady=(0, 12), sticky="ew")
            ctk.CTkButton(
                row,
                text="Abrir",
                width=90,
                height=34,
                corner_radius=8,
                fg_color=BG,
                hover_color=SURFACE_2,
                text_color=TEXT,
                border_width=1,
                border_color=BORDER,
                command=lambda path=report.get("open_path") or report.get("md_path"): self.open_report_file(path),
            ).grid(row=0, column=1, rowspan=2, padx=14, pady=12, sticky="e")

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
            }
            self.last_analysis_text = output
            self.after(0, self._set_analysis_result, output)
            self.after(0, lambda: self.analysis_optimize_button.configure(state="normal"))
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
