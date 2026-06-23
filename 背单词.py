import tkinter as tk
from tkinter import filedialog, messagebox
import os
import sys
import re

# 尝试导入 PDF 解析库
try:
    import pdfplumber
    PDF_SUPPORT = True
except ImportError:
    PDF_SUPPORT = False

# ---------------------------- 获取基础路径（支持 exe 打包）---------------------------------
def get_base_path():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    else:
        return os.path.dirname(os.path.abspath(__file__))

# ---------------------------- 默认单词库（备选）---------------------------------
DEFAULT_WORDS = [
    {"word": "Apple", "phonetic": "/ˈæpəl/", "meaning": "苹果；苹果公司"},
    {"word": "Persistence", "phonetic": "/pərˈsɪstəns/", "meaning": "坚持；毅力"},
    {"word": "Serendipity", "phonetic": "/ˌserənˈdɪpəti/", "meaning": "意外发现珍奇事物的本领；机缘巧合"},
]

# ---------------------------- 指定默认 PDF 路径（与 exe 同目录）---------------------------------
PDF_FILENAME = "2026年6月英语六级1500核心词.pdf"
DEFAULT_PDF_PATH = os.path.join(get_base_path(), PDF_FILENAME)

class WordFloater:
    """桌面悬浮滚动背单词窗口（支持从 PDF 导入单词）"""
    def __init__(self, root, word_list=None):
        self.root = root
        self.root.title("悬浮背单词 - CET6")
        self.root.geometry("360x240")
        self.root.attributes('-topmost', True)
        self.root.overrideredirect(True)
        self.root.attributes('-alpha', 0.92)
        self.root.configure(bg='#1e1e2f')

        if word_list:
            self.word_list = word_list
        else:
            # 先尝试加载默认路径的 PDF
            self.word_list = self.load_word_list(DEFAULT_PDF_PATH)
            if not self.word_list:
                # 若失败则弹窗让用户手动选择
                self.word_list = self.load_word_list()
        if not self.word_list:
            self.word_list = DEFAULT_WORDS.copy()
            messagebox.showwarning("提示", "未成功加载 PDF 单词库，使用默认示例单词。")

        self.current_index = 0
        self.total_words = len(self.word_list)
        self.current_word_data = self.word_list[self.current_index]

        self.animating = False
        self.auto_roll = True
        self.roll_interval = 5000
        self.after_id = None
        self.timer_label_ref = None

        self.setup_ui()
        self.setup_drag()
        self.setup_menu()
        self.update_content(self.current_word_data)
        self.start_auto_roll()

    # ---------------------------- 单词数据管理（PDF 解析）---------------------------
    def load_word_list(self, pdf_path=None):
        if not PDF_SUPPORT:
            messagebox.showerror("缺少依赖", "请先安装 pdfplumber 库：\npip install pdfplumber")
            return None

        if pdf_path is not None:
            if not os.path.exists(pdf_path):
                messagebox.showerror("文件不存在", f"找不到文件：\n{pdf_path}")
                return None
            try:
                words = self.extract_words_from_pdf(pdf_path)
                if words:
                    return words
                else:
                    messagebox.showwarning("解析失败", "PDF 中未提取到有效单词，请检查格式。")
                    return None
            except Exception as e:
                messagebox.showerror("错误", f"读取 PDF 失败：{str(e)}")
                return None

        # 未指定路径，弹出选择对话框
        desktop_path = os.path.join(os.path.expanduser("~"), "Desktop")
        pdf_path = filedialog.askopenfilename(
            title="选择单词本 PDF 文件",
            initialdir=desktop_path,
            filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")]
        )
        if not pdf_path:
            return None
        return self.load_word_list(pdf_path)  # 递归调用带路径版本

    def extract_words_from_pdf(self, pdf_path):
        """从 PDF 中提取单词和释义，支持常见格式"""
        word_list = []
        with pdfplumber.open(pdf_path) as pdf:
            full_text = ""
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    full_text += text + "\n"

        lines = full_text.splitlines()
        chinese_pattern = re.compile(r'[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]+')
        phonetic_pattern = re.compile(r'[\[/][^\]/]+[]/]')

        for line in lines:
            line = line.strip()
            if not line:
                continue

            word_match = re.search(r'\b([A-Za-z][A-Za-z\'-]*)\b', line)
            if not word_match:
                continue
            word = word_match.group(1)
            remaining = line[word_match.end():].strip()

            phonetic_match = phonetic_pattern.search(remaining)
            phonetic = ""
            if phonetic_match:
                phonetic = phonetic_match.group(0)
                remaining = remaining.replace(phonetic, "").strip()

            ch_match = chinese_pattern.search(remaining)
            if ch_match:
                meaning = remaining[ch_match.start():].strip()
            else:
                meaning = remaining
                if not meaning:
                    continue

            meaning = re.sub(r'\s+', ' ', meaning).strip()
            if meaning:
                word_list.append({
                    "word": word,
                    "phonetic": phonetic,
                    "meaning": meaning
                })

        # 去重
        seen = set()
        unique_words = []
        for w in word_list:
            key = w["word"].lower()
            if key not in seen:
                seen.add(key)
                unique_words.append(w)
        return unique_words

    # ---------------------------- 以下方法保持不变（UI、动画、拖拽等）----------------------
    def next_word(self, event=None):
        if self.animating:
            return
        new_index = (self.current_index + 1) % self.total_words
        new_data = self.word_list[new_index]
        self._slide_transition(new_data, direction=1)
        self.current_index = new_index
        self.current_word_data = new_data
        self.reset_auto_timer()

    def prev_word(self, event=None):
        if self.animating:
            return
        new_index = (self.current_index - 1) % self.total_words
        new_data = self.word_list[new_index]
        self._slide_transition(new_data, direction=-1)
        self.current_index = new_index
        self.current_word_data = new_data
        self.reset_auto_timer()

    def _slide_transition(self, new_word_data, direction=1):
        if self.animating:
            return
        self.animating = True
        if self.after_id:
            self.root.after_cancel(self.after_id)
            self.after_id = None
        width = self.root.winfo_width()
        if width <= 10:
            width = 360

        self.update_frame_content(self.backup_frame, new_word_data)

        cur_x = self.content_frame.winfo_x()
        if direction == 1:
            new_start_x = width
            cur_target_x = -width
        else:
            new_start_x = -width
            cur_target_x = width

        self.backup_frame.place(x=new_start_x, y=0, width=width, height=self.root.winfo_height())
        self.backup_frame.lift()
        self.content_frame.lift()

        steps = 12
        delay = 10
        step_cur = (cur_target_x - cur_x) / steps
        step_new = (0 - new_start_x) / steps

        def animate(step=0):
            if step >= steps:
                self.content_frame.place_forget()
                self.backup_frame.place(x=0, y=0, width=width, height=self.root.winfo_height())
                self.content_frame, self.backup_frame = self.backup_frame, self.content_frame
                self.clear_frame_content(self.backup_frame)
                self.animating = False
                if self.auto_roll:
                    self.start_auto_roll()
                return
            new_cur_x = self.content_frame.winfo_x() + step_cur
            new_new_x = self.backup_frame.winfo_x() + step_new
            self.content_frame.place(x=new_cur_x, y=0, width=width, height=self.root.winfo_height())
            self.backup_frame.place(x=new_new_x, y=0, width=width, height=self.root.winfo_height())
            self.root.after(delay, animate, step+1)

        animate(0)

    def update_frame_content(self, frame, word_data):
        for widget in frame.winfo_children():
            widget.destroy()
        self._build_word_card(frame, word_data)

    def clear_frame_content(self, frame):
        for widget in frame.winfo_children():
            widget.destroy()
        tk.Label(frame, text="", bg='#1e1e2f').pack()

    def _build_word_card(self, parent, word_data):
        word_label = tk.Label(parent, text=word_data['word'], font=("微软雅黑", 22, "bold"),
                              fg="#f5c542", bg='#1e1e2f')
        word_label.pack(pady=(20, 5))
        phonetic = word_data.get('phonetic', '')
        if phonetic:
            phonetic_label = tk.Label(parent, text=phonetic, font=("Segoe UI", 10),
                                      fg="#aaaaaa", bg='#1e1e2f')
            phonetic_label.pack(pady=(0, 10))
        meaning_label = tk.Label(parent, text=word_data['meaning'], font=("微软雅黑", 12),
                                 fg="#e0e0e0", bg='#1e1e2f', wraplength=320, justify='center')
        meaning_label.pack(pady=(5, 20), fill='both', expand=True)

    def start_auto_roll(self):
        if self.after_id:
            self.root.after_cancel(self.after_id)
        if self.auto_roll and not self.animating:
            self.update_timer_display(self.roll_interval // 1000)
            self.after_id = self.root.after(self.roll_interval, self._auto_next)
        else:
            self.update_timer_display(None)

    def _auto_next(self):
        if self.auto_roll and not self.animating:
            self.next_word()
        elif self.auto_roll:
            self.after_id = self.root.after(200, self._auto_next)

    def reset_auto_timer(self):
        if self.auto_roll and not self.animating:
            if self.after_id:
                self.root.after_cancel(self.after_id)
            self.start_auto_roll()

    def update_timer_display(self, remaining_seconds):
        if self.timer_label_ref and self.timer_label_ref.winfo_exists():
            if remaining_seconds is not None and self.auto_roll and not self.animating:
                self.timer_label_ref.config(text=f"⏱ {remaining_seconds}s")
            else:
                self.timer_label_ref.config(text="⏸")

    def setup_ui(self):
        main_frame = tk.Frame(self.root, bg='#1e1e2f')
        main_frame.pack(fill='both', expand=True)

        self.content_frame = tk.Frame(main_frame, bg='#1e1e2f')
        self.backup_frame = tk.Frame(main_frame, bg='#1e1e2f')
        self.content_frame.place(x=0, y=0, relwidth=1, relheight=0.85)
        self.backup_frame.place_forget()

        control_bar = tk.Frame(main_frame, bg='#2a2a3b', height=40)
        control_bar.pack(side='bottom', fill='x')
        control_bar.pack_propagate(False)

        prev_btn = tk.Button(control_bar, text="◀", font=("Arial", 12), bg='#2a2a3b', fg='#dddddd',
                             bd=0, activebackground='#3a3a4b', command=self.prev_word)
        prev_btn.pack(side='left', padx=10, pady=5)

        self.play_btn = tk.Button(control_bar, text="⏸", font=("Arial", 12), bg='#2a2a3b', fg='#dddddd',
                                  bd=0, activebackground='#3a3a4b', command=self.toggle_auto_roll)
        self.play_btn.pack(side='left', expand=True)

        next_btn = tk.Button(control_bar, text="▶", font=("Arial", 12), bg='#2a2a3b', fg='#dddddd',
                             bd=0, activebackground='#3a3a4b', command=self.next_word)
        next_btn.pack(side='right', padx=10, pady=5)

        self.counter_label = tk.Label(control_bar, text=f"1/{self.total_words}", font=("Segoe UI", 9),
                                      fg="#aaaaaa", bg='#2a2a3b')
        self.counter_label.pack(side='right', padx=5)

        self.timer_label = tk.Label(self.root, text="⏱ 5s", font=("Segoe UI", 9),
                                    fg="#aaaaaa", bg='#1e1e2f')
        self.timer_label.place(x=self.root.winfo_width()-60, y=8)
        self.timer_label_ref = self.timer_label
        self.root.bind('<Configure>', self._on_resize)

    def _on_resize(self, event):
        if event.widget == self.root:
            self.timer_label.place(x=self.root.winfo_width()-60, y=8)

    def toggle_auto_roll(self):
        self.auto_roll = not self.auto_roll
        if self.auto_roll:
            self.play_btn.config(text="⏸")
            self.start_auto_roll()
        else:
            self.play_btn.config(text="▶")
            if self.after_id:
                self.root.after_cancel(self.after_id)
                self.after_id = None
            self.update_timer_display(None)

    def update_content(self, word_data):
        self.update_frame_content(self.content_frame, word_data)
        self.clear_frame_content(self.backup_frame)
        self.update_counter_display()

    def update_counter_display(self):
        if hasattr(self, 'counter_label') and self.counter_label.winfo_exists():
            self.counter_label.config(text=f"{self.current_index+1}/{self.total_words}")

    def setup_drag(self):
        self.drag_start_x = 0
        self.drag_start_y = 0
        self.root.bind('<Button-1>', self.on_mouse_down)
        self.root.bind('<B1-Motion>', self.on_mouse_move)

    def on_mouse_down(self, event):
        self.drag_start_x = event.x
        self.drag_start_y = event.y

    def on_mouse_move(self, event):
        x = self.root.winfo_x() + event.x - self.drag_start_x
        y = self.root.winfo_y() + event.y - self.drag_start_y
        self.root.geometry(f'+{x}+{y}')

    def setup_menu(self):
        self.menu = tk.Menu(self.root, tearoff=0)
        self.menu.add_command(label="暂停滚动", command=self.toggle_auto_roll)
        self.menu.add_separator()
        self.menu.add_command(label="下一个单词", command=self.next_word)
        self.menu.add_command(label="上一个单词", command=self.prev_word)
        self.menu.add_separator()
        self.menu.add_command(label="重新加载 PDF", command=self.reload_pdf)
        self.menu.add_command(label="退出程序", command=self.quit_app)
        self.root.bind('<Button-3>', self.show_menu)

    def reload_pdf(self):
        new_list = self.load_word_list()  # 弹出对话框选择
        if new_list:
            self.word_list = new_list
            self.total_words = len(self.word_list)
            self.current_index = 0
            self.current_word_data = self.word_list[0]
            if self.after_id:
                self.root.after_cancel(self.after_id)
                self.after_id = None
            self.update_content(self.current_word_data)
            self.update_counter_display()
            self.start_auto_roll()

    def show_menu(self, event):
        self.menu.post(event.x_root, event.y_root)

    def quit_app(self):
        if self.after_id:
            self.root.after_cancel(self.after_id)
        self.root.quit()
        self.root.destroy()

    def run(self):
        self.root.mainloop()


def main():
    root = tk.Tk()
    if not PDF_SUPPORT:
        root.withdraw()
        messagebox.showerror("缺少依赖", "请先安装 pdfplumber 库：\npip install pdfplumber")
        sys.exit(1)
    app = WordFloater(root)
    app.run()

if __name__ == "__main__":
    main()