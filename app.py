import os
import sys
import subprocess
import threading
import random
import json
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog

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

def pick_clips(material_dir, first_video, audio_dur):
    files = [f for f in os.listdir(material_dir) if f.lower().endswith(".mp4")]
    if not files:
        raise RuntimeError("素材文件夹中没有 MP4 文件！")
    random.shuffle(files)
    clips, total = [], 0.0
    if first_video:
        clips.append(first_video)
        total += get_duration(first_video)
    for name in files:
        if total >= audio_dur:
            break
        abs_path = os.path.join(material_dir, name)
        if first_video and os.path.abspath(abs_path) == os.path.abspath(first_video):
            continue
        clips.append(abs_path)
        total += get_duration(abs_path)
    return clips

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

def run_cmd(cmd, log_fn, proc_setter):
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            encoding="utf-8", errors="replace")
    proc_setter(proc)
    for line in proc.stdout:
        log_fn(line.rstrip())
    proc.wait()
    proc_setter(None)
    return proc.returncode

# ── GUI ─────────────────────────────────────────────────────────
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("批量视频生成工具")
        self.resizable(False, False)
        self.configure(bg="#FAFAFA")
        self._cancelled = False
        self._cur_proc  = None
        self._build()
        self.update_idletasks()
        w, h = 760, 800
        x = (self.winfo_screenwidth()  - w) // 2
        y = (self.winfo_screenheight() - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")
        self._apply_config(load_config())  # 启动时恢复上次关闭时的配置
        self.protocol("WM_DELETE_WINDOW", self._on_close)  # 关闭时自动保存

    def _build(self):
        main_bg = "#FAFAFA"
        card_bg = "#FFFFFF"
        text_color = "#333333"
        accent_color = "#1677FF"
        border_color = "#E5E5E5"
        font_family = "微软雅黑"

        # 主容器
        container = tk.Frame(self, bg=main_bg)
        container.pack(fill="both", expand=True, padx=20, pady=20)

        # ── 顶部标题区 ──
        header = tk.Frame(container, bg=main_bg)
        header.pack(fill="x", pady=(0, 15))
        tk.Label(header, text="批量视频生成工具", font=(font_family, 18, "bold"), fg=text_color, bg=main_bg).pack(side="left")
        
        btn_frame = tk.Frame(header, bg=main_bg)
        btn_frame.pack(side="right", fill="y", pady=4)
        tk.Button(btn_frame, text="📂 加载配置", font=(font_family, 9), cursor="hand2",
                  bg=main_bg, fg=accent_color, activeforeground="#0958d9",
                  relief="flat", bd=0, command=self._load_config_dialog).pack(side="left", padx=(0, 10))
        tk.Button(btn_frame, text="💾 保存配置", font=(font_family, 9), cursor="hand2",
                  bg=main_bg, fg=accent_color, activeforeground="#0958d9",
                  relief="flat", bd=0, command=self._save_config).pack(side="left")

        # ── 参数配置区 (Card) ──
        cfg_card = tk.Frame(container, bg=card_bg, highlightbackground=border_color, highlightthickness=1)
        cfg_card.pack(fill="x", pady=(0, 15))
        
        cfg_inner = tk.Frame(cfg_card, bg=card_bg)
        cfg_inner.pack(fill="both", expand=True, padx=20, pady=15)

        self.var_material = tk.StringVar()
        self.var_first    = tk.StringVar()
        self.var_audio    = tk.StringVar()
        self.var_output   = tk.StringVar()
        self.var_count    = tk.IntVar(value=1)
        self.var_orient   = tk.StringVar(value="portrait")

        rows = [
            ("📁 素材文件夹", self.var_material, "dir",  None),
            ("🎬 固定片头",   self.var_first,    "file", [("MP4", "*.mp4")]),
            ("💾 输出目录",   self.var_output,   "dir",  None),
        ]
        
        cfg_inner.columnconfigure(1, weight=1)
        label_font = (font_family, 10)
        
        row_idx = 0
        for i, (lbl, var, mode, ftypes) in enumerate(rows):
            tk.Label(cfg_inner, text=lbl, bg=card_bg, font=label_font, fg=text_color, width=12, anchor="w").grid(row=row_idx, column=0, sticky="w", pady=(0, 12))
            entry_frame = tk.Frame(cfg_inner, bg=card_bg, highlightbackground=border_color, highlightthickness=1)
            entry_frame.grid(row=row_idx, column=1, sticky="ew", pady=(0, 12))
            entry = tk.Entry(entry_frame, textvariable=var, font=(font_family, 10), bg="#FCFCFC", relief="flat")
            entry.pack(fill="both", expand=True, padx=5, pady=4)
            entry.bind("<Button-1>", lambda e, v=var, m=mode, ft=ftypes: self._browse(v, m, ft))
            entry.config(cursor="hand2")
            row_idx += 1

        # 音频行
        tk.Label(cfg_inner, text="🎵 音频文件", bg=card_bg, font=label_font, fg=text_color, width=12, anchor="w").grid(row=row_idx, column=0, sticky="w", pady=(0, 12))
        audio_container = tk.Frame(cfg_inner, bg=card_bg)
        audio_container.grid(row=row_idx, column=1, sticky="ew", pady=(0, 12))
        audio_container.columnconfigure(0, weight=1)
        
        audio_entry_frame = tk.Frame(audio_container, bg=card_bg, highlightbackground=border_color, highlightthickness=1)
        audio_entry_frame.grid(row=0, column=0, sticky="ew")
        audio_entry = tk.Entry(audio_entry_frame, textvariable=self.var_audio, font=(font_family, 10), bg="#FCFCFC", relief="flat")
        audio_entry.pack(fill="both", expand=True, padx=5, pady=4)
        audio_entry.bind("<Button-1>", lambda e: self._browse(self.var_audio, "file", [("Audio", "*.mp3 *.wav *.aac"), ("所有文件", "*.*")]))
        audio_entry.config(cursor="hand2")
        
        tk.Button(audio_container, text="提取音频", font=(font_family, 9), cursor="hand2",
                  bg="#E6F4FF", fg=accent_color, activebackground="#BAE0FF",
                  relief="flat", bd=0, command=self._extract_audio).grid(row=0, column=1, padx=(10, 0), ipadx=8, ipady=3)
        row_idx += 1

        # 分隔线
        tk.Frame(cfg_inner, bg=border_color, height=1).grid(row=row_idx, column=0, columnspan=2, sticky="ew", pady=(5, 15))
        row_idx += 1

        # 选项行
        opt_frame = tk.Frame(cfg_inner, bg=card_bg)
        opt_frame.grid(row=row_idx, column=0, columnspan=2, sticky="ew")
        
        tk.Label(opt_frame, text="生成数量:", bg=card_bg, font=label_font, fg=text_color).pack(side="left")
        spin_frame = tk.Frame(opt_frame, bg=card_bg, highlightbackground=border_color, highlightthickness=1)
        spin_frame.pack(side="left", padx=(8, 30))
        tk.Spinbox(spin_frame, from_=1, to=999, textvariable=self.var_count, width=6, font=(font_family, 10), relief="flat", bg="#FCFCFC").pack(fill="both", expand=True, padx=2, pady=2)
        
        tk.Label(opt_frame, text="视频画幅:", bg=card_bg, font=label_font, fg=text_color).pack(side="left")
        
        style = ttk.Style()
        style.configure("TRadiobutton", background=card_bg, font=label_font, foreground=text_color)
        ttk.Radiobutton(opt_frame, text="📱 竖屏 (9:16)", variable=self.var_orient, value="portrait", style="TRadiobutton", cursor="hand2").pack(side="left", padx=(8, 15))
        ttk.Radiobutton(opt_frame, text="🖥️ 横屏 (16:9)", variable=self.var_orient, value="landscape", style="TRadiobutton", cursor="hand2").pack(side="left")

        # ── 动作区 ──
        action_frame = tk.Frame(container, bg=main_bg)
        action_frame.pack(fill="x", pady=(0, 15))
        
        self.btn_preprocess = tk.Button(action_frame, text="🔧 预处理素材 (统一转码)",
                                        font=(font_family, 11, "bold"), bg="#FAAD14", fg="white",
                                        activebackground="#D48806", activeforeground="white",
                                        relief="flat", bd=0, cursor="hand2", command=self._preprocess_toggle)
        self.btn_preprocess.pack(side="left", fill="x", expand=True, padx=(0, 10), ipady=10)

        self.btn_start = tk.Button(action_frame, text="▶ 开始生成",
                                   font=(font_family, 11, "bold"), bg=accent_color, fg="white",
                                   activebackground="#0958d9", activeforeground="white",
                                   relief="flat", bd=0, cursor="hand2", command=self._toggle)
        self.btn_start.pack(side="right", fill="x", expand=True, ipady=10)

        # ── 日志区 ──
        log_card = tk.Frame(container, bg=card_bg, highlightbackground=border_color, highlightthickness=1)
        log_card.pack(fill="both", expand=True, pady=(0, 10))
        
        log_header = tk.Frame(log_card, bg=card_bg)
        log_header.pack(fill="x", padx=15, pady=10)
        tk.Label(log_header, text="📝 运行日志", bg=card_bg, font=(font_family, 10, "bold"), fg=text_color).pack(side="left")
        tk.Button(log_header, text="🗑️ 清空", font=(font_family, 9), cursor="hand2",
                  bg=card_bg, fg="#999999", activebackground=card_bg, activeforeground=text_color,
                  relief="flat", bd=0, command=self._clear_log).pack(side="right")
                  
        log_inner = tk.Frame(log_card, bg="#1E1E1E")
        log_inner.pack(fill="both", expand=True)
        
        self.log_text = tk.Text(log_inner, bg="#1E1E1E", fg="#D4D4D4", font=("Consolas", 10), state="disabled",
                                relief="flat", bd=0, wrap="word", padx=10, pady=10)
        self.log_text.pack(fill="both", expand=True, side="left")
        
        sb = ttk.Scrollbar(log_inner, orient="vertical", command=self.log_text.yview)
        sb.pack(fill="y", side="right")
        self.log_text.configure(yscrollcommand=sb.set)

        # ── 底部状态区 ──
        status_frame = tk.Frame(container, bg=main_bg)
        status_frame.pack(fill="x")
        
        self.lbl_status = tk.Label(status_frame, text="✅ 就绪", bg=main_bg, font=(font_family, 9), fg="#666666")
        self.lbl_status.pack(side="left")
        
        self.progress = ttk.Progressbar(status_frame, mode="determinate")
        self.progress.pack(side="right", fill="x", expand=True, padx=(20, 0))

    def _on_close(self):
        save_config({
            "material": self.var_material.get(),
            "first":    self.var_first.get(),
            "audio":    self.var_audio.get(),
            "output":   self.var_output.get(),
            "count":    self.var_count.get(),
            "orient":   self.var_orient.get(),
        })
        self.destroy()

    # ── 配置保存/加载 ────────────────────────────────────────────
    def _apply_config(self, cfg):
        if not cfg:
            return
        self.var_material.set(cfg.get("material", ""))
        self.var_first.set(cfg.get("first", ""))
        self.var_audio.set(cfg.get("audio", ""))
        self.var_output.set(cfg.get("output", ""))
        self.var_count.set(cfg.get("count", 1))
        self.var_orient.set(cfg.get("orient", "portrait"))

    def _save_config(self):
        name = tk.simpledialog.askstring("保存配置", "请输入配置名称：", parent=self)
        if not name:
            return
        name = name.strip()
        if not name:
            return
        path = os.path.join(resource_dir(), f"{name}.json")
        save_config({
            "material": self.var_material.get(),
            "first":    self.var_first.get(),
            "audio":    self.var_audio.get(),
            "output":   self.var_output.get(),
            "count":    self.var_count.get(),
            "orient":   self.var_orient.get(),
        }, path)
        self._set_status(f"配置已保存：{name}.json ✓")

    def _load_config_dialog(self):
        path = filedialog.askopenfilename(
            title="选择配置文件",
            filetypes=[("配置文件", "*.json"), ("所有文件", "*.*")],
            initialdir=resource_dir()
        )
        if path:
            with open(path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            self._apply_config(cfg)
            self._set_status("配置已加载 ✓")

    # ── 提取音频 ────────────────────────────────────────────────
    def _extract_audio(self):
        src = filedialog.askopenfilename(
            title="选择要提取音频的视频文件",
            filetypes=[
                ("视频文件", "*.mp4"),
                ("视频文件", "*.mov"),
                ("视频文件", "*.avi"),
                ("视频文件", "*.mkv"),
                ("所有文件", "*.*")
            ]
        )
        if not src:
            return

        # 先检测是否有音频流
        probe = subprocess.run(
            [ffprobe_exe(), "-v", "error",
             "-select_streams", "a",
             "-show_entries", "stream=codec_type",
             "-of", "default=noprint_wrappers=1:nokey=1", src],
            capture_output=True, text=True, encoding="utf-8"
        )
        if "audio" not in probe.stdout:
            messagebox.showwarning("无音频", f"所选视频没有音频轨道，无法提取：\n{os.path.basename(src)}")
            return

        out = os.path.splitext(src)[0] + ".mp3"
        self._log(f"\n🎵 提取音频: {os.path.basename(src)}")
        self._log(f"输出路径: {out}")
        self._set_status("正在提取音频…")

        def run():
            cmd = [ffmpeg_exe(), "-y", "-i", src,
                   "-vn", "-c:a", "libmp3lame", "-b:a", "128k", out]
            self._log("执行: " + " ".join(cmd))
            code = run_cmd(cmd, self._log, lambda p: setattr(self, "_cur_proc", p))
            if code == 0:
                self.var_audio.set(out)
                self._log(f"✅ 提取成功：{out}")
                self.after(0, self._set_status, "音频提取完成 ✓")
            else:
                self._log("❌ 提取失败，请检查日志")
                self.after(0, self._set_status, "音频提取失败")
        threading.Thread(target=run, daemon=True).start()

    # ── 文件选择 ────────────────────────────────────────────────
    def _browse(self, var, mode, ftypes):
        path = filedialog.askdirectory() if mode == "dir" else \
               filedialog.askopenfilename(filetypes=ftypes or [("所有文件", "*.*")])
        if path:
            var.set(path)

    # ── 日志 / 状态 ─────────────────────────────────────────────
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

    def _set_busy(self, busy):
        """运行中禁用两个按钮互相干扰"""
        state = "disabled" if busy else "normal"
        self.btn_preprocess.configure(state=state)
        self.btn_start.configure(state=state)

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
        confirm = messagebox.askyesno(
            "确认预处理",
            f"将对 {len(files)} 个素材统一转码为 {res}（30fps）。\n"
            f"原文件会备份到素材文件夹/_backup/ 下。\n\n确认开始？"
        )
        if not confirm:
            return

        self._cancelled = False
        self._cur_proc  = None
        self.btn_preprocess.configure(text="⛔  取消预处理", bg="#E53935")
        self.btn_start.configure(state="disabled")
        self.progress["maximum"] = len(files)
        self.progress["value"]   = 0
        self._clear_log()
        self._log(f"🔧 开始预处理，共 {len(files)} 个素材，目标规格：{res} 30fps\n")

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
                self._log(f"\n[{idx}/{len(files)}] {name}")

                cmd = [
                    ffmpeg_exe(), "-y", "-i", src,
                    "-vf", f"setpts=PTS-STARTPTS,"
                           f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
                           f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,fps=30",
                    "-vsync", "cfr",
                    "-c:v", "libx264", "-preset", "fast",
                    "-pix_fmt", "yuv420p", "-an",
                    tmp_out
                ]
                code = run_cmd(cmd, self._log, lambda p: setattr(self, "_cur_proc", p))

                if code == 0 and not self._cancelled:
                    # 备份原文件，替换为转码后文件
                    os.replace(src, bak)
                    os.replace(tmp_out, src)
                    self._log(f"  ✅ 完成（原文件已备份）")
                    ok += 1
                else:
                    if os.path.exists(tmp_out):
                        os.remove(tmp_out)
                    self._log(f"  ❌ 失败，跳过")
                    fail += 1

                self.after(0, lambda v=idx: self.progress.configure(value=v))

            if not self._cancelled:
                self._log(f"\n🎉 预处理完成！成功 {ok} 个，失败 {fail} 个")
                self._log(f"原始素材备份在：{backup}")
                self.after(0, self._set_status, f"预处理完成 ✓ （{ok}/{len(files)}）")
                self.after(0, messagebox.showinfo, "完成",
                           f"预处理完成！成功 {ok} 个，失败 {fail} 个\n原文件备份在 _backup/")
            else:
                self.after(0, self._set_status, "已取消")

            self._cur_proc  = None
            self._cancelled = False
            self.after(0, self.btn_preprocess.configure,
                       {"text": "🔧  预处理素材（统一转码）", "bg": "#F57C00"})
            self.after(0, self.btn_start.configure, {"state": "normal"})

        threading.Thread(target=run, daemon=True).start()

    # ── 开始生成 / 取消 ─────────────────────────────────────────
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
        self.btn_preprocess.configure(
            text="🔧  预处理素材（统一转码）", bg="#F57C00", state="normal")

    def _start(self):
        material = self.var_material.get().strip()
        first    = self.var_first.get().strip()
        audio    = self.var_audio.get().strip()
        output   = self.var_output.get().strip()
        total    = self.var_count.get()
        portrait = self.var_orient.get() == "portrait"

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
                    clips = pick_clips(material, first, dur)
                    self._log(f"选取素材 {len(clips)} 段")

                    # 写 concat 列表
                    with open(concat_txt, "w", encoding="utf-8") as f:
                        for c in clips:
                            f.write(f"file '{c.replace(chr(92), '/')}'\n")

                    # 拼接 + 合并音频
                    cmd = [
                        ffmpeg_exe(), "-y",
                        "-f", "concat", "-safe", "0", "-i", concat_txt,
                        "-i", audio,
                        "-map", "0:v:0", "-map", "1:a:0",
                        "-vf", f"setpts=PTS-STARTPTS,scale={res.replace('x', ':')}:force_original_aspect_ratio=decrease,pad={res.replace('x', ':')}:(ow-iw)/2:(oh-ih)/2",
                        "-vsync", "cfr",
                        "-c:v", "libx265",
                        "-b:v", "7071k", "-maxrate", "7071k", "-minrate", "7071k",
                        "-bufsize", "14M",
                        "-r", "30", "-pix_fmt", "yuv420p",
                        "-color_primaries", "bt709", "-color_trc", "bt709",
                        "-colorspace", "bt709",
                        "-preset", "fast",
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
            self.after(0, self.btn_start.configure,
                       {"text": "▶  开始生成", "bg": "#1677FF"})
            self.after(0, self.btn_preprocess.configure, {"state": "normal"})

        threading.Thread(target=run, daemon=True).start()


if __name__ == "__main__":
    App().mainloop()
