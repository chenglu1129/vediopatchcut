import os
import sys
import subprocess
import threading
import random
import json
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import sv_ttk

# ── ffmpeg 路径 ──────────────────────────────────────────────────
def resource_dir():
    return os.path.dirname(sys.executable if getattr(sys, "frozen", False) else os.path.abspath(__file__))

def ffmpeg_exe():
    p = os.path.join(resource_dir(), "ffmpeg", "ffmpeg.exe")
    return p if os.path.exists(p) else "ffmpeg"

def ffprobe_exe():
    p = os.path.join(resource_dir(), "ffmpeg", "ffprobe.exe")
    return p if os.path.exists(p) else "ffprobe"

# ── 核心逻辑 ────────────────────────────────────────────────────
def get_duration(path):
    result = subprocess.run(
        [ffprobe_exe(), "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", path],
        capture_output=True, text=True, encoding="utf-8"
    )
    return float(result.stdout.strip())

def pick_clips(material_dir, first_videos, audio_dur):
    """first_videos: list of candidate intro paths (may be empty). One is chosen at random."""
    files = [f for f in os.listdir(material_dir) if f.lower().endswith(".mp4")]
    if not files:
        raise RuntimeError("素材文件夹中没有 MP4 文件！")
    random.shuffle(files)
    clips, total = [], 0.0
    chosen_first = random.choice(first_videos) if first_videos else None
    if chosen_first:
        clips.append(chosen_first)
        total += get_duration(chosen_first)
    for name in files:
        if total >= audio_dur:
            break
        abs_path = os.path.join(material_dir, name)
        if chosen_first and os.path.abspath(abs_path) == os.path.abspath(chosen_first):
            continue
        clips.append(abs_path)
        total += get_duration(abs_path)
    return clips, chosen_first

def run_cmd(cmd, log_fn, proc_setter):
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            encoding="utf-8", errors="replace")
    proc_setter(proc)
    for line in proc.stdout:
        log_fn(line.rstrip())
    proc.wait()
    proc_setter(None)
    return proc.returncode

# ── 配置存读 ─────────────────────────────────────────────────────
CONFIG_PATH = os.path.join(resource_dir(), "config.json")

def load_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_config(data, path=CONFIG_PATH):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ── 辅助：只读输入框（点击弹出选择器）────────────────────────────
def make_path_entry(parent, var, browse_fn, hint=""):
    frame = ttk.Frame(parent)
    entry = ttk.Entry(frame, textvariable=var, state="readonly")
    entry.pack(side="left", fill="x", expand=True)
    entry.bind("<Button-1>", lambda e: browse_fn())
    entry.config(cursor="hand2")
    if hint:
        tk.Label(frame, text=hint, font=("微软雅黑", 8), fg="#999999",
                 bg=parent.cget("background") if hasattr(parent, "cget") else "#FAFAFA"
                 ).pack(side="left", padx=(6, 0))
    return frame, entry

# ── 自定义命名弹窗 ───────────────────────────────────────────────
def _ask_config_name(parent):
    """现代风格的配置命名弹窗，返回输入的名称字符串，取消返回 None。"""
    result = []
    F = "微软雅黑"

    dlg = tk.Toplevel(parent)
    dlg.title("保存配置")
    dlg.resizable(False, False)
    dlg.grab_set()
    dlg.transient(parent)

    # 居中于父窗口
    parent.update_idletasks()
    px, py = parent.winfo_x(), parent.winfo_y()
    pw, ph = parent.winfo_width(), parent.winfo_height()
    w, h = 380, 196
    dlg.geometry(f"{w}x{h}+{px + (pw - w)//2}+{py + (ph - h)//2}")

    outer = ttk.Frame(dlg, padding=(28, 24, 28, 20))
    outer.pack(fill="both", expand=True)
    outer.columnconfigure(0, weight=1)

    ttk.Label(outer, text="保存配置", font=(F, 13, "bold")).grid(
        row=0, column=0, sticky="w")
    ttk.Label(outer, text="请为本次配置输入一个名称", font=(F, 9),
              foreground="#888888").grid(row=1, column=0, sticky="w", pady=(3, 12))

    var = tk.StringVar()
    entry = ttk.Entry(outer, textvariable=var, font=(F, 11))
    entry.grid(row=2, column=0, sticky="ew", ipady=5)
    entry.focus_set()

    btn_row = ttk.Frame(outer)
    btn_row.grid(row=3, column=0, sticky="ew", pady=(18, 0))
    btn_row.columnconfigure(0, weight=1)
    btn_row.columnconfigure(1, weight=1)

    def confirm():
        name = var.get().strip()
        if not name:
            entry.focus_set()
            return
        result.append(name)
        dlg.destroy()

    def cancel():
        dlg.destroy()

    BTN_OPTS = dict(relief="flat", bd=0, cursor="hand2",
                    font=(F, 10), height=2)

    tk.Button(btn_row, text="取消",
              bg="#F0F0F0", fg="#333333",
              activebackground="#E0E0E0", activeforeground="#333333",
              command=cancel, **BTN_OPTS).grid(row=0, column=0, sticky="ew", padx=(0, 6))

    tk.Button(btn_row, text="保存",
              bg="#1677FF", fg="white",
              activebackground="#0958d9", activeforeground="white",
              font=(F, 10, "bold"), relief="flat", bd=0, cursor="hand2", height=2,
              command=confirm).grid(row=0, column=1, sticky="ew", padx=(6, 0))

    entry.bind("<Return>", lambda _: confirm())
    entry.bind("<Escape>", lambda _: cancel())
    dlg.protocol("WM_DELETE_WINDOW", cancel)
    dlg.wait_window()

    return result[0] if result else None


# ── GUI ─────────────────────────────────────────────────────────
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("批量视频生成工具")
        self.resizable(True, True)
        self.minsize(780, 820)
        self._cancelled = False
        self._cur_proc  = None
        sv_ttk.set_theme("light")
        self._build()
        self.update_idletasks()
        w, h = 820, 900
        x = (self.winfo_screenwidth()  - w) // 2
        y = (self.winfo_screenheight() - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")
        self._apply_config(load_config())
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build(self):
        F = "微软雅黑"

        root = ttk.Frame(self, padding=20)
        root.pack(fill="both", expand=True)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(2, weight=1)  # 日志区可伸缩

        # ══ 顶部标题栏 ══════════════════════════════════════════
        hdr = ttk.Frame(root)
        hdr.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        ttk.Label(hdr, text="批量视频生成工具",
                  font=(F, 17, "bold")).pack(side="left")
        ttk.Button(hdr, text="💾 保存配置",
                   command=self._save_config).pack(side="right", padx=(6, 0))
        ttk.Button(hdr, text="📂 加载配置",
                   command=self._load_config_dialog).pack(side="right")

        # ══ 参数卡片区 ══════════════════════════════════════════
        cards = ttk.Frame(root)
        cards.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        cards.columnconfigure(0, weight=1)
        cards.columnconfigure(1, weight=1)

        # ─ 左卡：输入源 ─────────────────────────────────────────
        src_card = ttk.LabelFrame(cards, text=" 📦 输入源设置 ", padding=14)
        src_card.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        src_card.columnconfigure(1, weight=1)

        self.var_material = tk.StringVar()
        self.var_audio    = tk.StringVar()
        self._first_paths: list = []   # 备选片头完整路径列表

        # 素材文件夹 + 预处理按钮
        ttk.Label(src_card, text="素材文件夹", font=(F, 10)).grid(
            row=0, column=0, sticky="w", pady=(0, 8), padx=(0, 10))
        mat_row = ttk.Frame(src_card)
        mat_row.grid(row=0, column=1, sticky="ew", pady=(0, 8))
        mat_row.columnconfigure(0, weight=1)
        mat_entry = ttk.Entry(mat_row, textvariable=self.var_material, state="readonly")
        mat_entry.grid(row=0, column=0, sticky="ew")
        mat_entry.bind("<Button-1>", lambda e: self._browse(self.var_material, "dir"))
        mat_entry.config(cursor="hand2")
        self.btn_preprocess = ttk.Button(mat_row, text="🔧 预处理",
                                         command=self._preprocess_toggle)
        self.btn_preprocess.grid(row=0, column=1, padx=(6, 0))

        # 备选片头（Listbox，支持逐条删除）
        ttk.Label(src_card, text="备选片头", font=(F, 10)).grid(
            row=1, column=0, sticky="nw", pady=(4, 0), padx=(0, 10))
        first_outer = ttk.Frame(src_card)
        first_outer.grid(row=1, column=1, sticky="ew", pady=(4, 0))
        first_outer.columnconfigure(0, weight=1)

        # Listbox + 滚动条
        lb_frame = ttk.Frame(first_outer)
        lb_frame.grid(row=0, column=0, columnspan=2, sticky="ew")
        lb_frame.columnconfigure(0, weight=1)
        self.lb_first = tk.Listbox(
            lb_frame, selectmode="extended", height=3,
            font=("微软雅黑", 9), activestyle="none",
            relief="solid", bd=1, highlightthickness=0,
            selectbackground="#1677FF", selectforeground="white"
        )
        self.lb_first.grid(row=0, column=0, sticky="ew")
        lb_sb = ttk.Scrollbar(lb_frame, orient="vertical", command=self.lb_first.yview)
        lb_sb.grid(row=0, column=1, sticky="ns")
        self.lb_first.configure(yscrollcommand=lb_sb.set)

        # 操作按钮行
        btn_first_row = ttk.Frame(first_outer)
        btn_first_row.grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 0))
        ttk.Button(btn_first_row, text="＋ 添加",
                   command=self._browse_first).pack(side="left", padx=(0, 6))
        ttk.Button(btn_first_row, text="－ 删除选中",
                   command=self._remove_selected_first).pack(side="left")

        ttk.Label(src_card, text="💡 可选；多个片头每条视频等权重随机抽取一个",
                  font=(F, 8), foreground="#999999").grid(
            row=2, column=1, sticky="w", pady=(2, 8))

        # 音频文件
        ttk.Label(src_card, text="音频文件", font=(F, 10)).grid(
            row=3, column=0, sticky="w", pady=(0, 8), padx=(0, 10))
        audio_row = ttk.Frame(src_card)
        audio_row.grid(row=3, column=1, sticky="ew", pady=(0, 4))
        audio_row.columnconfigure(0, weight=1)
        audio_entry = ttk.Entry(audio_row, textvariable=self.var_audio, state="readonly")
        audio_entry.grid(row=0, column=0, sticky="ew")
        audio_entry.bind("<Button-1>", lambda e: self._browse(
            self.var_audio, "file", [("音频文件", "*.mp3"), ("音频文件", "*.wav"), ("所有文件", "*.*")]))
        audio_entry.config(cursor="hand2")
        ttk.Button(audio_row, text="提取音频",
                   command=self._extract_audio).grid(row=0, column=1, padx=(6, 0))
        ttk.Label(src_card, text="💡 将随机拼接素材直至匹配音频总时长",
                  font=(F, 8), foreground="#999999").grid(
            row=4, column=1, sticky="w", pady=(0, 0))

        # ─ 右卡：规格与输出 ──────────────────────────────────────
        out_card = ttk.LabelFrame(cards, text=" ⚙️ 规格与输出 ", padding=14)
        out_card.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        out_card.columnconfigure(1, weight=1)

        self.var_output = tk.StringVar()
        self.var_count  = tk.IntVar(value=30)
        self.var_orient = tk.StringVar(value="portrait")

        # 视频画幅
        ttk.Label(out_card, text="视频画幅", font=(F, 10)).grid(
            row=0, column=0, sticky="w", pady=(0, 12), padx=(0, 10))
        orient_frame = ttk.Frame(out_card)
        orient_frame.grid(row=0, column=1, sticky="w", pady=(0, 12))
        ttk.Radiobutton(orient_frame, text="📱 竖屏 9:16",
                        variable=self.var_orient, value="portrait").pack(side="left", padx=(0, 16))
        ttk.Radiobutton(orient_frame, text="🖥️ 横屏 16:9",
                        variable=self.var_orient, value="landscape").pack(side="left")

        # 生成数量
        ttk.Label(out_card, text="生成数量", font=(F, 10)).grid(
            row=1, column=0, sticky="w", pady=(0, 12), padx=(0, 10))
        ttk.Spinbox(out_card, from_=1, to=999, textvariable=self.var_count,
                    width=8, font=(F, 10)).grid(row=1, column=1, sticky="w", pady=(0, 12))

        # 输出目录
        ttk.Label(out_card, text="输出目录", font=(F, 10)).grid(
            row=2, column=0, sticky="w", pady=(0, 8), padx=(0, 10))
        out_entry = ttk.Entry(out_card, textvariable=self.var_output, state="readonly")
        out_entry.grid(row=2, column=1, sticky="ew", pady=(0, 8))
        out_entry.bind("<Button-1>", lambda e: self._browse(self.var_output, "dir"))
        out_entry.config(cursor="hand2")

        # ══ 开始生成按钮（独占，全宽）══════════════════════════════
        self.btn_start = tk.Button(
            root, text="▶  开始生成",
            font=(F, 14, "bold"),
            bg="#1677FF", fg="white",
            activebackground="#0958d9", activeforeground="white",
            relief="flat", bd=0, cursor="hand2", height=2,
            command=self._toggle
        )
        self.btn_start.grid(row=2, column=0, sticky="ew", pady=(0, 12))

        # ══ 日志区 ══════════════════════════════════════════════
        log_frame = ttk.LabelFrame(root, text=" 📝 运行日志 ", padding=0)
        log_frame.grid(row=3, column=0, sticky="nsew", pady=(0, 10))
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        root.rowconfigure(3, weight=1)

        self.log_text = tk.Text(
            log_frame, bg="#1E1E1E", fg="#D4D4D4",
            font=("Consolas", 10), state="disabled",
            relief="flat", bd=0, wrap="word", padx=10, pady=10
        )
        self.log_text.grid(row=0, column=0, sticky="nsew")
        sb = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        sb.grid(row=0, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=sb.set)

        # ══ 底部状态栏 ══════════════════════════════════════════
        bar = ttk.Frame(root)
        bar.grid(row=4, column=0, sticky="ew")
        bar.columnconfigure(1, weight=1)

        self.lbl_status = ttk.Label(bar, text="就绪", font=(F, 9), foreground="#666666")
        self.lbl_status.grid(row=0, column=0, sticky="w")

        self.progress = ttk.Progressbar(bar, mode="determinate")
        self.progress.grid(row=0, column=1, sticky="ew", padx=(16, 16))

        ttk.Button(bar, text="🗑 清空日志",
                   command=self._clear_log).grid(row=0, column=2, sticky="e")

    # ── 关闭时保存 ───────────────────────────────────────────────
    def _on_close(self):
        save_config(self._current_config())
        self.destroy()

    def _current_config(self):
        return {
            "material": self.var_material.get(),
            "first":    " | ".join(self._first_paths),
            "audio":    self.var_audio.get(),
            "output":   self.var_output.get(),
            "count":    self.var_count.get(),
            "orient":   self.var_orient.get(),
        }

    # ── 配置 ─────────────────────────────────────────────────────
    def _apply_config(self, cfg):
        if not cfg:
            return
        self.var_material.set(cfg.get("material", ""))
        self.var_audio.set(cfg.get("audio", ""))
        self.var_output.set(cfg.get("output", ""))
        self.var_count.set(cfg.get("count", 30))
        self.var_orient.set(cfg.get("orient", "portrait"))
        # 片头列表
        raw = cfg.get("first", "")
        paths = [p.strip() for p in raw.split("|") if p.strip()]
        self._first_paths = paths
        self._refresh_first_lb()

    def _save_config(self):
        name = _ask_config_name(self)
        if not name:
            return
        path = os.path.join(resource_dir(), f"{name}.json")
        save_config(self._current_config(), path)
        self._set_status(f"配置已保存：{name}.json ✓")

    def _load_config_dialog(self):
        path = filedialog.askopenfilename(
            title="选择配置文件",
            filetypes=[("配置文件", "*.json"), ("所有文件", "*.*")],
            initialdir=resource_dir()
        )
        if path:
            with open(path, "r", encoding="utf-8") as f:
                self._apply_config(json.load(f))
            self._set_status("配置已加载 ✓")

    # ── 文件选择 ─────────────────────────────────────────────────
    def _browse(self, var, mode, ftypes=None):
        path = filedialog.askdirectory() if mode == "dir" else \
               filedialog.askopenfilename(filetypes=ftypes or [("所有文件", "*.*")])
        if path:
            var.set(path)

    def _browse_first(self):
        paths = filedialog.askopenfilenames(
            title="选择备选片头（可多选）",
            filetypes=[("MP4", "*.mp4"), ("所有文件", "*.*")]
        )
        if not paths:
            return
        for p in paths:
            if p not in self._first_paths:
                self._first_paths.append(p)
        self._refresh_first_lb()

    def _remove_selected_first(self):
        selected = list(self.lb_first.curselection())
        for idx in reversed(selected):   # 从后往前删，索引不会漂移
            del self._first_paths[idx]
        self._refresh_first_lb()

    def _refresh_first_lb(self):
        self.lb_first.delete(0, "end")
        for p in self._first_paths:
            self.lb_first.insert("end", os.path.basename(p))
        # Tooltip：悬停显示完整路径（直接用 lb 的 title 模拟）
        self.lb_first.config(
            height=max(2, min(5, len(self._first_paths)))
        )

    # ── 日志 / 状态 ──────────────────────────────────────────────
    def _log(self, msg):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", msg + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _clear_log(self):
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    def _set_status(self, text):
        self.lbl_status.configure(text=text)

    # ── 提取音频 ─────────────────────────────────────────────────
    def _extract_audio(self):
        src = filedialog.askopenfilename(
            title="选择要提取音频的视频文件",
            filetypes=[("视频文件", "*.mp4"), ("视频文件", "*.mov"),
                       ("视频文件", "*.avi"), ("视频文件", "*.mkv"), ("所有文件", "*.*")]
        )
        if not src:
            return
        probe = subprocess.run(
            [ffprobe_exe(), "-v", "error", "-select_streams", "a",
             "-show_entries", "stream=codec_type",
             "-of", "default=noprint_wrappers=1:nokey=1", src],
            capture_output=True, text=True, encoding="utf-8"
        )
        if "audio" not in probe.stdout:
            messagebox.showwarning("无音频", f"所选视频没有音频轨道：\n{os.path.basename(src)}")
            return
        out = os.path.splitext(src)[0] + ".mp3"
        self._log(f"\n🎵 提取音频: {os.path.basename(src)}\n输出: {out}")
        self._set_status("正在提取音频…")
        def run():
            cmd = [ffmpeg_exe(), "-y", "-i", src, "-vn", "-c:a", "libmp3lame", "-b:a", "128k", out]
            code = run_cmd(cmd, self._log, lambda p: setattr(self, "_cur_proc", p))
            if code == 0:
                self.var_audio.set(out)
                self._log(f"✅ 提取成功")
                self.after(0, self._set_status, "音频提取完成 ✓")
            else:
                self._log("❌ 提取失败")
                self.after(0, self._set_status, "音频提取失败")
        threading.Thread(target=run, daemon=True).start()

    # ── 预处理素材 ───────────────────────────────────────────────
    def _preprocess_toggle(self):
        if self._cur_proc is None and not self._cancelled:
            self._preprocess_start()
        else:
            self._cancel()

    def _preprocess_start(self):
        material = self.var_material.get().strip()
        portrait = self.var_orient.get() == "portrait"
        if not material:
            messagebox.showwarning("参数缺失", "请先选择素材文件夹")
            return
        files = [f for f in os.listdir(material) if f.lower().endswith(".mp4")]
        if not files:
            messagebox.showwarning("无素材", "素材文件夹中没有 MP4 文件")
            return
        res = "1080x1920" if portrait else "1920x1080"
        if not messagebox.askyesno("确认预处理",
            f"将对 {len(files)} 个素材统一转码为 {res} 30fps。\n"
            f"原文件备份到 _backup/ 目录。\n\n确认开始？"):
            return
        self._cancelled = False
        self._cur_proc  = None
        self.btn_preprocess.configure(text="⛔ 取消")
        self.btn_start.configure(state="disabled")
        self.progress["maximum"] = len(files)
        self.progress["value"]   = 0
        self._clear_log()
        self._log(f"🔧 预处理 {len(files)} 个素材 → {res} 30fps\n")

        def run():
            w, h   = res.split("x")
            backup = os.path.join(material, "_backup")
            os.makedirs(backup, exist_ok=True)
            ok, fail = 0, 0
            for idx, name in enumerate(files, 1):
                if self._cancelled:
                    break
                src     = os.path.join(material, name)
                bak     = os.path.join(backup, name)
                tmp_out = src + ".tmp.mp4"
                self.after(0, self._set_status, f"预处理 {idx}/{len(files)}: {name}")
                self._log(f"[{idx}/{len(files)}] {name}")
                cmd = [
                    ffmpeg_exe(), "-y", "-i", src,
                    "-vf", f"setpts=PTS-STARTPTS,"
                           f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
                           f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,fps=30",
                    "-vsync", "cfr", "-c:v", "libx264", "-preset", "fast",
                    "-pix_fmt", "yuv420p", "-an", tmp_out
                ]
                code = run_cmd(cmd, self._log, lambda p: setattr(self, "_cur_proc", p))
                if code == 0 and not self._cancelled:
                    os.replace(src, bak)
                    os.replace(tmp_out, src)
                    self._log("  ✅ 完成")
                    ok += 1
                else:
                    if os.path.exists(tmp_out):
                        os.remove(tmp_out)
                    self._log("  ❌ 失败，跳过")
                    fail += 1
                self.after(0, lambda v=idx: self.progress.configure(value=v))

            if not self._cancelled:
                self._log(f"\n🎉 预处理完成！成功 {ok}，失败 {fail}")
                self.after(0, self._set_status, f"预处理完成 ✓ {ok}/{len(files)}")
                self.after(0, messagebox.showinfo, "完成",
                           f"预处理完成！成功 {ok} 个，失败 {fail} 个")
            self._cur_proc  = None
            self._cancelled = False
            self.after(0, self.btn_preprocess.configure, {"text": "🔧 预处理"})
            self.after(0, self.btn_start.configure, {"state": "normal"})

        threading.Thread(target=run, daemon=True).start()

    # ── 开始生成 / 取消 ──────────────────────────────────────────
    def _toggle(self):
        if not self._cancelled and self._cur_proc is None:
            self._start()
        else:
            self._cancel()

    def _cancel(self):
        self._cancelled = True
        if self._cur_proc:
            self._cur_proc.kill()
        self._log("⛔ 已取消")
        self._set_status("已取消")
        self.btn_start.configure(text="▶  开始生成", bg="#1677FF")
        self.btn_preprocess.configure(text="🔧 预处理", state="normal")

    def _start(self):
        material    = self.var_material.get().strip()
        first_list  = list(self._first_paths)          # 备选片头列表快照
        audio       = self.var_audio.get().strip()
        output      = self.var_output.get().strip()
        total       = self.var_count.get()
        portrait    = self.var_orient.get() == "portrait"

        if not material or not audio or not output:
            messagebox.showwarning("参数缺失", "请填写：素材文件夹、音频文件、输出目录")
            return

        os.makedirs(output, exist_ok=True)
        self._cancelled = False
        self._cur_proc  = None
        self.btn_start.configure(text="⛔  取消", bg="#E53935")
        self.btn_preprocess.configure(state="disabled")
        self.progress["maximum"] = total
        self.progress["value"]   = 0
        self._clear_log()
        self._log(f"ffmpeg:  {ffmpeg_exe()}")
        self._log(f"ffprobe: {ffprobe_exe()}")
        self._log(f"▶ 开始批量生成，共 {total} 条\n")

        def run():
            res = "1080x1920" if portrait else "1920x1080"
            for i in range(1, total + 1):
                if self._cancelled:
                    break
                self.after(0, self._set_status, f"正在处理 {i} / {total}")
                self._log(f"\n── 第 {i} / {total} 条 ──────────────────────")
                out_file   = os.path.join(output, f"output_{i}.mp4")
                concat_txt = os.path.join(output, f"concat_tmp_{i}.txt")
                try:
                    dur = get_duration(audio)
                    self._log(f"音频时长: {dur:.1f} 秒")
                    clips, chosen_first = pick_clips(material, first_list, dur)
                    if chosen_first:
                        self._log(f"片头抽取: {os.path.basename(chosen_first)}")
                    self._log(f"选取素材 {len(clips)} 段")
                    with open(concat_txt, "w", encoding="utf-8") as f:
                        for c in clips:
                            f.write(f"file '{c.replace(chr(92), '/')}'\n")
                    cmd = [
                        ffmpeg_exe(), "-y",
                        "-f", "concat", "-safe", "0", "-i", concat_txt,
                        "-i", audio,
                        "-map", "0:v:0", "-map", "1:a:0",
                        "-vf", f"setpts=PTS-STARTPTS,"
                               f"scale={res.replace('x', ':')}:force_original_aspect_ratio=decrease,"
                               f"pad={res.replace('x', ':')}:(ow-iw)/2:(oh-ih)/2",
                        "-vsync", "cfr",
                        "-c:v", "libx265",
                        "-b:v", "7071k", "-maxrate", "7071k", "-minrate", "7071k",
                        "-bufsize", "14M", "-r", "30", "-pix_fmt", "yuv420p",
                        "-color_primaries", "bt709", "-color_trc", "bt709",
                        "-colorspace", "bt709", "-preset", "fast",
                        "-c:a", "aac", "-b:a", "128k",
                        "-shortest", out_file
                    ]
                    code = run_cmd(cmd, self._log, lambda p: setattr(self, "_cur_proc", p))
                    self._log(f"✅ 第 {i} 条成功" if code == 0 else f"❌ 第 {i} 条失败（退出码 {code}）")
                except Exception as ex:
                    self._log(f"❌ 第 {i} 条异常：{ex}")
                finally:
                    if os.path.exists(concat_txt):
                        os.remove(concat_txt)
                self.after(0, lambda v=i: self.progress.configure(value=v))

            if not self._cancelled:
                self._log(f"\n🎉 全部完成！输出目录：{output}")
                self.after(0, self._set_status, "完成 ✓")
                self.after(0, messagebox.showinfo, "完成", f"全部 {total} 条视频处理完毕！")
            self._cur_proc  = None
            self._cancelled = False
            self.after(0, self.btn_start.configure, {"text": "▶  开始生成", "bg": "#1677FF"})
            self.after(0, self.btn_preprocess.configure, {"state": "normal"})

        threading.Thread(target=run, daemon=True).start()


if __name__ == "__main__":
    App().mainloop()
