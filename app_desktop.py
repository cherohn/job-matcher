"""Modern desktop launcher for Job Matcher."""

import logging
import os
import queue
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox

import customtkinter as ctk
from PIL import Image

import main as engine
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
        return clean.replace("Queries ativas", "Buscas preparadas")
    if "google/serper:" in low and "vagas" in low:
        return clean.replace("Google/Serper:", "Google:")
    if "total coletado" in low:
        return clean.replace("Unicas", "unicas")
    if "novas para analisar" in low:
        return clean
    if "limitando analise" in low:
        return clean
    if clean.startswith("Analisando:"):
        return clean.replace("Analisando:", "Analisando vaga:")
    if "descricao insuficiente" in low:
        return "Vaga ignorada: descricao insuficiente."
    if "relatorio salvo" in low:
        return "Relatorio salvo em reports/."
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
        self.geometry("1000x640")
        self.minsize(900, 560)

        self.messages = queue.Queue()
        self.stop_event = threading.Event()
        self.worker = None
        self.monitoring = False

        self.max_jobs = tk.StringVar(value=str(getattr(engine.settings, "MAX_JOBS_TO_ANALYZE_PER_SCAN", 25)))
        self.interval = tk.StringVar(value=str(engine.SCAN_INTERVAL_MINUTES))
        self.min_score = tk.StringVar(value=str(engine.MIN_SCORE))
        self.status_text = tk.StringVar(value="Pronto")
        self.next_scan_text = tk.StringVar(value="-")

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

        main = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        main.grid(row=0, column=1, sticky="nsew", padx=0, pady=0)
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
            text="Controle varreduras, acompanhe eventos importantes e envie os melhores matches por e-mail.",
            font=("Segoe UI", 13),
            text_color=MUTED,
        ).grid(row=1, column=0, pady=(6, 0), sticky="w")

        settings = ctk.CTkFrame(main, fg_color=BASE, corner_radius=10, border_width=1, border_color=BORDER)
        settings.grid(row=1, column=0, padx=26, pady=(0, 16), sticky="ew")
        settings.grid_columnconfigure((0, 1, 2), weight=1)
        self._number_field(settings, 0, "Vagas por varredura", self.max_jobs)
        self._number_field(settings, 1, "Score minimo", self.min_score)
        self._number_field(settings, 2, "Intervalo (min)", self.interval)

        actions = ctk.CTkFrame(main, fg_color="transparent")
        actions.grid(row=2, column=0, padx=26, pady=(0, 16), sticky="ew")
        actions.grid_columnconfigure((0, 1, 2, 3), weight=1)
        self._action_button(actions, 0, "Iniciar", self.start_monitoring, primary=True)
        self._action_button(actions, 1, "Varredura unica", self.run_once)
        self._action_button(actions, 2, "Parar", self.stop_monitoring, danger=True)
        self._action_button(actions, 3, "E-mail teste", self.send_test_email)

        log_panel = ctk.CTkFrame(main, fg_color=BASE, corner_radius=10, border_width=1, border_color=BORDER)
        log_panel.grid(row=3, column=0, padx=26, pady=(0, 24), sticky="nsew")
        log_panel.grid_columnconfigure(0, weight=1)
        log_panel.grid_rowconfigure(1, weight=1)

        log_header = ctk.CTkFrame(log_panel, fg_color="transparent")
        log_header.grid(row=0, column=0, padx=18, pady=(16, 8), sticky="ew")
        log_header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(log_header, text="Atividade", font=("Segoe UI", 17, "bold"), text_color=TEXT).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(log_header, text="Somente eventos relevantes", font=("Segoe UI", 12), text_color=MUTED).grid(row=1, column=0, sticky="w")
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
        self.log_box.insert("end", "Pronto. Configure a busca e clique em Iniciar ou Varredura unica.\n")
        self.log_box.configure(state="disabled")

    def open_setup_window(self):
        data = load_user_config()
        window = ctk.CTkToplevel(self)
        window.title("Configurar Job Matcher")
        window.geometry("760x720")
        window.minsize(720, 620)
        window.transient(self)
        window.grab_set()

        window.grid_columnconfigure(0, weight=1)
        window.grid_rowconfigure(0, weight=1)
        body = ctk.CTkScrollableFrame(window, fg_color=BG)
        body.grid(row=0, column=0, sticky="nsew", padx=18, pady=18)
        body.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(body, text="Configuração do usuário", font=("Segoe UI", 22, "bold"), text_color=TEXT).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(
            body,
            text=f"Arquivo local: {get_config_path()}",
            font=("Segoe UI", 11),
            text_color=MUTED,
        ).grid(row=1, column=0, sticky="w", pady=(2, 14))

        fields = {}
        row = 2

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

        add_entry("groq_api_key", "API de IA Groq", secret=True)
        add_entry("groq_model", "Modelo Groq")
        if not fields["groq_model"].get():
            fields["groq_model"].set("llama-3.3-70b-versatile")
        add_entry("serper_api_key", "API Serper", secret=True)
        add_entry("email_remetente", "Gmail remetente")
        add_entry("email_senha_app", "Senha de app do Gmail", secret=True)
        add_entry("email_destinatario", "E-mail que receberá os matches")
        add_entry("location", "Localização da busca")
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

        add_file_picker("profile_text_path", "Arquivo TXT com tudo que o usuário sabe sobre si", [("Texto", "*.txt"), ("Todos", "*.*")], "perfil.txt")
        add_file_picker("resume_pdf_path", "Currículo em PDF", [("PDF", "*.pdf"), ("Todos", "*.*")], "curriculo.pdf")

        text_frame = ctk.CTkFrame(body, fg_color="transparent")
        text_frame.grid(row=row, column=0, sticky="ew", pady=(0, 10))
        text_frame.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(text_frame, text="Termos de busca, um por linha", text_color=MUTED, font=("Segoe UI", 12)).grid(row=0, column=0, sticky="w")
        queries_box = ctk.CTkTextbox(text_frame, height=120, corner_radius=7, fg_color=BASE, border_color=BORDER, text_color=TEXT)
        queries_box.grid(row=1, column=0, sticky="ew", pady=(4, 0))
        queries = data.get("search_queries") or getattr(engine.settings, "SEARCH_QUERIES", [])
        queries_box.insert("1.0", "\n".join(queries))
        row += 1

        def save_setup():
            payload = {key: var.get().strip() for key, var in fields.items()}
            payload["profile_text_path"] = path_vars["profile_text_path"].get().strip()
            payload["resume_pdf_path"] = path_vars["resume_pdf_path"].get().strip()
            payload["search_queries"] = [line.strip() for line in queries_box.get("1.0", "end").splitlines() if line.strip()]
            payload["min_score"] = self._parse_int(self.min_score, 90, 1, 100)
            payload["scan_interval_minutes"] = self._parse_int(self.interval, 60, 1, 720)
            payload["max_jobs_to_analyze_per_scan"] = self._parse_int(self.max_jobs, 25, 1, 200)
            save_user_config(payload)
            engine.refresh_runtime_settings()
            logging.info("Configuracao salva. O Job Matcher ja pode usar os dados do usuario.")
            messagebox.showinfo("Job Matcher", "Configuracao salva com sucesso.")
            window.destroy()

        actions = ctk.CTkFrame(body, fg_color="transparent")
        actions.grid(row=row, column=0, sticky="ew", pady=(8, 0))
        actions.grid_columnconfigure((0, 1), weight=1)
        ctk.CTkButton(
            actions,
            text="Salvar configuração",
            height=40,
            corner_radius=8,
            fg_color=ACCENT,
            hover_color=ACCENT_DIM,
            text_color=BG,
            command=save_setup,
        ).grid(row=0, column=0, sticky="ew", padx=(0, 8))
        ctk.CTkButton(
            actions,
            text="Cancelar",
            height=40,
            corner_radius=8,
            fg_color=SURFACE,
            hover_color=SURFACE_2,
            text_color=TEXT,
            command=window.destroy,
        ).grid(row=0, column=1, sticky="ew")

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
        frame.grid(row=0, column=column, padx=14, pady=14, sticky="ew")
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
        self.stop_event.clear()
        self.monitoring = True
        self.worker = threading.Thread(target=self._monitor_loop, daemon=True)
        self.worker.start()

    def run_once(self):
        if self.worker and self.worker.is_alive():
            messagebox.showinfo("Job Matcher", "Aguarde a tarefa atual terminar.")
            return

        self._apply_runtime_settings()
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
        self.worker = threading.Thread(target=self._send_email_worker, daemon=True)
        self.worker.start()

    def open_reports_folder(self):
        path = os.path.abspath("reports")
        os.makedirs(path, exist_ok=True)
        os.startfile(path)

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
