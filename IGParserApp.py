
# IGParserApp.py
# macOS-friendly GUI for Instagram parser with Virality tab.
# Requires: Python 3.9+, instagrapi, pandas, openpyxl, numpy, pyinstaller (for packaging).
# Note: Use responsibly and in accordance with Instagram Terms.

import os
import re
import threading
from datetime import datetime
from pathlib import Path
from tkinter import Tk, StringVar, IntVar, filedialog, messagebox
from tkinter import ttk

# External deps
# pip install instagrapi pandas openpyxl numpy
from instagrapi import Client
import pandas as pd
import numpy as np

PROFILE_RE = re.compile(r"(?:https?://)?(?:www\.)?instagram\.com/([A-Za-z0-9_.]+)/?")

def parse_username(value: str) -> str:
    m = PROFILE_RE.match(value.strip())
    if m:
        return m.group(1)
    return value.strip().lstrip("@")

def extract_hashtags(text: str):
    if not text:
        return []
    return sorted(set(re.findall(r"#(\w+)", text)))

def extract_mentions(text: str):
    if not text:
        return []
    return sorted(set(re.findall(r"@([A-Za-z0-9_.]+)", text)))

def media_to_row(m):
    def get(obj, name, default=None):
        return getattr(obj, name, default)
    caption = get(m, "caption_text", None)
    taken_at = get(m, "taken_at", None)
    taken_at_iso = taken_at.isoformat() if hasattr(taken_at, "isoformat") else taken_at
    code = get(m, "code", None)
    post_url = f"https://www.instagram.com/p/{code}/" if code else None
    width = get(m, "thumbnail_width", None) or get(m, "width", None)
    height = get(m, "thumbnail_height", None) or get(m, "height", None)
    duration = get(m, "video_duration", None)

    loc = get(m, "location", None)
    location_name = None
    if loc:
        location_name = getattr(loc, "name", None) or getattr(loc, "slug", None)

    d = {
        "id": get(m, "id", None),
        "pk": get(m, "pk", None),
        "shortcode": code,
        "url": post_url,
        "taken_at": taken_at_iso,
        "media_type": get(m, "media_type", None),
        "product_type": get(m, "product_type", None),
        "like_count": get(m, "like_count", None),
        "comment_count": get(m, "comment_count", None),
        "view_count": get(m, "view_count", None) or get(m, "play_count", None),
        "play_count": get(m, "play_count", None),
        "caption": caption,
        "hashtags": ", ".join(extract_hashtags(caption)),
        "mentions": ", ".join(extract_mentions(caption)),
        "duration_sec": duration,
        "width": width,
        "height": height,
        "location": location_name,
        "is_paid_partnership": get(m, "is_paid_partnership", None),
        "is_comments_disabled": get(m, "commenting_disabled_for_viewer", None),
        "thumbnail_url": get(m, "thumbnail_url", None),
        "video_url": get(m, "video_url", None),
    }

    resources = getattr(m, "resources", None)
    if resources and isinstance(resources, list):
        d["carousel_count"] = len(resources)
    else:
        d["carousel_count"] = None
    return d

def compute_virality(df: pd.DataFrame, followers: int) -> pd.DataFrame:
    df = df.copy()
    if not followers or followers <= 0:
        df["followers_at_scrape"] = np.nan
        df["views_per_follower"] = np.nan
        df["likes_per_follower"] = np.nan
        df["comments_per_follower"] = np.nan
        df["er_per_follower"] = np.nan
        return df

    df["followers_at_scrape"] = followers
    vc = pd.to_numeric(df.get("view_count"), errors="coerce")
    lc = pd.to_numeric(df.get("like_count"), errors="coerce")
    cc = pd.to_numeric(df.get("comment_count"), errors="coerce")
    df["views_per_follower"] = vc / followers
    df["likes_per_follower"] = lc / followers
    df["comments_per_follower"] = cc / followers
    df["er_per_follower"] = (lc + cc) / followers
    return df

class IGParserGUI:
    def __init__(self, root: Tk):
        self.root = root
        root.title("Instagram Parser (macOS) — Virality")
        root.geometry("640x540")

        # Vars
        self.user_var = StringVar()
        self.sessionid_var = StringVar()
        self.login_var = StringVar()
        self.pass_var = StringVar()
        self.limit_var = IntVar(value=0)
        self.out_var = StringVar(value=str(Path.home() / "IGParserOutput" / "instagram_posts"))

        # Layout
        pad = {"padx": 10, "pady": 6}
        frm = ttk.Frame(root)
        frm.pack(fill="both", expand=True)

        row = 0
        ttk.Label(frm, text="Профиль (ник или URL):").grid(row=row, column=0, sticky="w", **pad)
        ttk.Entry(frm, textvariable=self.user_var, width=40).grid(row=row, column=1, columnspan=2, sticky="we", **pad)

        row += 1
        ttk.Label(frm, text="SessionID (рекомендуется):").grid(row=row, column=0, sticky="w", **pad)
        ttk.Entry(frm, textvariable=self.sessionid_var, width=40).grid(row=row, column=1, sticky="we", **pad)
        ttk.Button(frm, text="Папка sessionid?", command=self.how_sessionid).grid(row=row, column=2, **pad)

        row += 1
        ttk.Label(frm, text="ИЛИ логин/пароль:").grid(row=row, column=0, sticky="w", **pad)
        ttk.Entry(frm, textvariable=self.login_var, width=20).grid(row=row, column=1, sticky="we", **pad)
        ttk.Entry(frm, textvariable=self.pass_var, width=20, show="•").grid(row=row, column=2, sticky="we", **pad)

        row += 1
        ttk.Label(frm, text="Лимит постов (0 = все):").grid(row=row, column=0, sticky="w", **pad)
        ttk.Entry(frm, textvariable=self.limit_var, width=10).grid(row=row, column=1, sticky="w", **pad)

        row += 1
        ttk.Label(frm, text="Путь вывода (без расширения):").grid(row=row, column=0, sticky="w", **pad)
        ttk.Entry(frm, textvariable=self.out_var, width=40).grid(row=row, column=1, sticky="we", **pad)
        ttk.Button(frm, text="Выбрать...", command=self.choose_out).grid(row=row, column=2, **pad)

        row += 1
        self.run_btn = ttk.Button(frm, text="Запустить", command=self.run_parser)
        self.run_btn.grid(row=row, column=0, **pad)
        ttk.Button(frm, text="Открыть папку", command=self.open_output_folder).grid(row=row, column=1, **pad)

        row += 1
        ttk.Label(frm, text="Журнал:").grid(row=row, column=0, sticky="w", **pad)
        row += 1
        self.log = ttk.Treeview(frm, columns=("msg",), show="headings", height=12)
        self.log.heading("msg", text="Сообщение")
        self.log.grid(row=row, column=0, columnspan=3, sticky="nsew", padx=10, pady=(0,10))
        frm.grid_rowconfigure(row, weight=1)
        frm.grid_columnconfigure(1, weight=1)

    def add_log(self, message: str):
        self.log.insert("", "end", values=(message,))
        children = self.log.get_children()
        if children:
            self.log.see(children[-1])

    def how_sessionid(self):
        messagebox.showinfo("Где взять sessionid", "Зайди в instagram.com → войди → Открой инструменты разработчика → Application/Storage → Cookies → sessionid. Скопируй значение.")

    def choose_out(self):
        path = filedialog.askdirectory()
        if path:
            base = Path(path) / "instagram_posts"
            self.out_var.set(str(base))

    def open_output_folder(self):
        out = Path(self.out_var.get()).expanduser()
        folder = out.parent if out.suffix else out
        folder.mkdir(parents=True, exist_ok=True)
        os.system(f'open "{folder}"')

    def run_parser(self):
        user_input = self.user_var.get().strip()
        if not user_input:
            messagebox.showerror("Ошибка", "Укажи ник или ссылку на профиль.")
            return
        sessionid = self.sessionid_var.get().strip() or None
        login = self.login_var.get().strip() or None
        password = self.pass_var.get().strip() or None
        limit = self.limit_var.get()
        out_base = Path(self.out_var.get()).expanduser()

        t = threading.Thread(target=self._run_parser_thread, args=(user_input, sessionid, login, password, limit, out_base))
        t.daemon = True
        t.start()

    def _run_parser_thread(self, user_input, sessionid, login, password, limit, out_base: Path):
        try:
            self.run_btn.config(state="disabled")
            self.add_log("Старт…")

            target_username = parse_username(user_input)
            self.add_log(f"Профиль: @{target_username}")

            cl = Client()
            cl.request_timeout = 30
            cl.retry_login = True

            if sessionid:
                try:
                    cl.load_settings({})
                    cl.set_settings({})
                    cl.set_uuids({})
                    cl.login_by_sessionid(sessionid)
                    self.add_log("Вход по sessionid выполнен.")
                except Exception as e:
                    self.add_log(f"Ошибка входа sessionid: {e}")
                    messagebox.showerror("Вход", f"Не удалось войти по sessionid:\\n{e}")
                    return
            elif login and password:
                try:
                    cl.login(login, password)
                    self.add_log("Вход по логину/паролю выполнен.")
                except Exception as e:
                    self.add_log(f"Ошибка входа: {e}")
                    messagebox.showerror("Вход", f"Не удалось войти:\\n{e}")
                    return
            else:
                self.add_log("⚠️ Без входа возможны ограничения и неполные данные.")

            try:
                user_id = cl.user_id_from_username(target_username)
                uinfo = cl.user_info(user_id)
                followers = getattr(uinfo, "follower_count", None)
                self.add_log(f"Подписчики: {followers}")
            except Exception as e:
                self.add_log(f"Не удалось получить информацию о пользователе: {e}")
                messagebox.showerror("Ошибка", f"Не удалось получить информацию о пользователе:\\n{e}")
                return

            amount = int(limit) if limit and int(limit) > 0 else 0
            self.add_log("Загружаю публикации…")
            try:
                medias = cl.user_medias(user_id, amount=amount)
            except Exception as e:
                self.add_log(f"Ошибка загрузки постов: {e}")
                messagebox.showerror("Ошибка", f"Не удалось получить публикации:\\n{e}")
                return

            rows = [media_to_row(m) for m in medias]
            df = pd.DataFrame(rows)
            self.add_log(f"Получено постов: {len(df)}")

            df = compute_virality(df, followers)

            out_base.parent.mkdir(parents=True, exist_ok=True)
            csv_path = out_base.with_suffix(".csv")
            xlsx_path = out_base.with_suffix(".xlsx")
            vir_csv_path = out_base.with_name(out_base.stem + "_virality").with_suffix(".csv")

            df.to_csv(csv_path, index=False, encoding="utf-8-sig")

            try:
                sort_cols = []
                if "views_per_follower" in df.columns:
                    sort_cols.append(("views_per_follower", False))
                if "er_per_follower" in df.columns:
                    sort_cols.append(("er_per_follower", False))
                if sort_cols:
                    sort_by = [c for c, _ in sort_cols]
                    ascending = [asc for _, asc in sort_cols]
                    df_sorted = df.sort_values(by=sort_by, ascending=ascending)
                else:
                    df_sorted = df
            except Exception:
                df_sorted = df

            with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
                df.to_excel(writer, index=False, sheet_name="All Posts")
                df_sorted.to_excel(writer, index=False, sheet_name="Virality")

            df_sorted.to_csv(vir_csv_path, index=False, encoding="utf-8-sig")

            self.add_log(f"Сохранено: {csv_path}")
            self.add_log(f"Сохранено: {xlsx_path}")
            self.add_log(f"Сохранено: {vir_csv_path}")
            messagebox.showinfo("Готово", f"Готово!\\n\\n{xlsx_path}")
        except Exception as e:
            self.add_log(f"Неожиданная ошибка: {e}")
            messagebox.showerror("Ошибка", str(e))
        finally:
            self.run_btn.config(state="normal")

def main():
    root = Tk()
    style = ttk.Style()
    try:
        style.theme_use("clam")
    except Exception:
        pass
    IGParserGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()
