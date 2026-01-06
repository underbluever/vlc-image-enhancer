import math
import time
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk, ImageEnhance, ImageDraw


class RecursiveResolveUI:
    """
    Sci-fi enhance animation:
      - Loading: pixel mosaic breathes + grid overlay
      - Reveal: recursive subdivision to full-res + grid fades
      - Final snap: subtle flash
    """

    def __init__(
        self,
        base_pil,
        on_complete=None,
        title="Nano Banana - Recursive Resolve",
        max_window=(980, 720),
        fps=30,
        start_block_px=32,
        breathe_strength=0.035,
        breathe_hz=0.55,
        grid_alpha=70,
        grid_min_block=6,
        reveal_step_ms=90,
        flash_ms=170,
    ):
        self.base_original = base_pil.convert("RGB")
        self.enhanced_original = None
        self.enhanced_preview = None

        self.on_complete = on_complete

        self.fps = fps
        self.dt_ms = int(1000 / max(1, fps))

        self.start_block_px = max(1, int(start_block_px))
        self.breathe_strength = float(breathe_strength)
        self.breathe_hz = float(breathe_hz)

        self.grid_alpha = int(grid_alpha)
        self.grid_min_block = int(grid_min_block)

        self.reveal_step_ms = int(reveal_step_ms)
        self.flash_ms = int(flash_ms)

        self.state = "loading"  # loading -> reveal -> final
        self._t0 = time.perf_counter()

        self._reveal_blocks = self._make_reveal_sequence(self.start_block_px)
        self._reveal_i = 0
        self._grid_fade = 1.0
        self._flash_left_ms = 0
        self._reveal_stepper_started = False
        self._on_complete_called = False
        self._running = True
        self._compare_button = None

        self.root = tk.Tk()
        self.root.title(title)
        self.root.configure(bg="#0b0f14")
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        init_w = min(max_window[0] + 200, screen_w - 80)
        init_h = min(max_window[1] + 220, screen_h - 80)
        init_w = max(720, init_w)
        init_h = max(540, init_h)
        self.root.geometry(f"{init_w}x{init_h}")
        self.root.minsize(720, 540)

        self.preview = self._fit_to_window(self.base_original, max_window)

        self.main = tk.Frame(self.root, bg="#0b0f14")
        self.main.pack(fill="both", expand=True)

        self.canvas = tk.Canvas(self.main, bg="#0b0f14", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)

        self.footer = tk.Frame(self.root, bg="#0b0f14")
        self.footer.pack(fill="x", side="bottom")
        self.footer.columnconfigure(0, weight=1)

        self._tk_img = None
        self._img_item = self.canvas.create_image(0, 0, anchor="nw")
        self._status_text = self.canvas.create_text(
            16,
            16,
            anchor="nw",
            text="ENHANCE: resolving...",
            fill="#a8c0ff",
            font=("Segoe UI", 12, "bold"),
        )

        self.root.bind("<Escape>", lambda e: self.root.destroy())
        self.root.after(0, self._tick)
        self.root.bind("<Configure>", self._on_resize)

        self._last_render = None

    def mainloop(self):
        self.root.mainloop()

    def set_enhanced_image(self, enhanced_pil):
        """Call from main thread (or via root.after) when result is ready."""
        self.enhanced_original = enhanced_pil.convert("RGB")
        self.enhanced_preview = self._fit_exact(self.enhanced_original, self.preview.size)
        self.state = "reveal"
        self._reveal_i = 0
        self._grid_fade = 1.0
        self._flash_left_ms = 0
        self._reveal_stepper_started = False
        self._on_complete_called = False
        self.canvas.itemconfigure(self._status_text, text="ENHANCE: applying detail passes...")

    def close_after(self, ms=350):
        self.root.after(ms, self.root.destroy)

    def stop(self):
        self._running = False

    def _make_reveal_sequence(self, start_block):
        seq = [max(1, start_block)]
        while seq[-1] > 1:
            next_block = max(1, int(round(seq[-1] * 0.75)))
            if next_block >= seq[-1]:
                next_block = max(1, seq[-1] - 1)
            seq.append(next_block)
        if seq[-1] != 1:
            seq.append(1)
        return seq

    def _fit_to_window(self, img, max_window):
        mw, mh = max_window
        w, h = img.size
        scale = min(mw / w, mh / h, 1.0)
        nw, nh = max(1, int(w * scale)), max(1, int(h * scale))
        return img.resize((nw, nh), Image.Resampling.LANCZOS)

    def _fit_exact(self, img, size):
        return img.resize(size, Image.Resampling.LANCZOS)

    def _pixelate(self, img, block_px):
        block_px = max(1, int(block_px))
        w, h = img.size
        sw = max(1, w // block_px)
        sh = max(1, h // block_px)
        small = img.resize((sw, sh), Image.Resampling.BILINEAR)
        return small.resize((w, h), Image.Resampling.NEAREST)

    def _apply_breathe(self, img, strength):
        t = time.perf_counter() - self._t0
        osc = math.sin(2 * math.pi * self.breathe_hz * t)
        factor = 1.0 + strength * osc
        return ImageEnhance.Brightness(img).enhance(factor)

    def _overlay_grid(self, img, block_px, alpha):
        if block_px < self.grid_min_block or alpha <= 0:
            return img

        w, h = img.size
        overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(overlay)

        step = block_px
        col = (160, 195, 255, int(alpha))
        for x in range(0, w, step):
            d.line([(x, 0), (x, h)], fill=col, width=1)
        for y in range(0, h, step):
            d.line([(0, y), (w, y)], fill=col, width=1)

        return Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")

    def _apply_flash(self, img, flash_left_ms):
        if flash_left_ms <= 0:
            return img
        a = max(0.0, min(1.0, flash_left_ms / max(1, self.flash_ms)))
        white = Image.new("RGB", img.size, (255, 255, 255))
        return Image.blend(img, white, 0.25 * a)

    def _render_frame(self):
        if self.state == "loading":
            frame = self._apply_breathe(self.preview, self.breathe_strength)
            frame = self._overlay_grid(frame, self.start_block_px, self.grid_alpha)
            return frame

        if self.state == "reveal":
            base = self.enhanced_preview if self.enhanced_preview else self.preview
            block = self._reveal_blocks[min(self._reveal_i, len(self._reveal_blocks) - 1)]
            frame = self._pixelate(base, block)

            steps = max(1, len(self._reveal_blocks) - 1)
            progress = min(1.0, self._reveal_i / steps)
            smooth = progress * progress * (3.0 - 2.0 * progress)
            self._grid_fade = 1.0 - smooth
            frame = self._overlay_grid(frame, block, int(self.grid_alpha * self._grid_fade))
            if smooth > 0.1:
                blend = (smooth - 0.1) / 0.9
                frame = Image.blend(frame, base, blend)

            frame = self._apply_flash(frame, self._flash_left_ms)
            return frame

        base = self.enhanced_preview if self.enhanced_preview else self.preview
        frame = self._apply_flash(base, self._flash_left_ms)
        return frame

    def _redraw_centered(self):
        if self._last_render is None:
            return
        self._draw_to_canvas(self._last_render)

    def _on_resize(self, event):
        if event.widget != self.root:
            return
        self._redraw_centered()

    def _draw_to_canvas(self, pil_img):
        try:
            cw = max(1, self.canvas.winfo_width())
            ch = max(1, self.canvas.winfo_height())
        except tk.TclError:
            self._running = False
            return

        w, h = pil_img.size
        scale = min(cw / w, ch / h)
        target_w = max(1, int(w * scale))
        target_h = max(1, int(h * scale))
        if target_w != w or target_h != h:
            if self.state == "reveal":
                resample = Image.Resampling.NEAREST
            else:
                resample = Image.Resampling.LANCZOS
            pil_img = pil_img.resize((target_w, target_h), resample=resample)
            w, h = pil_img.size
        x = (cw - w) // 2
        y = (ch - h) // 2

        try:
            self._tk_img = ImageTk.PhotoImage(pil_img)
            self.canvas.coords(self._img_item, x, y)
            self.canvas.itemconfigure(self._img_item, image=self._tk_img)
            self.canvas.coords(self._status_text, 16, 16)
        except tk.TclError:
            self._running = False
            return

    def _tick(self):
        if not self._running:
            return
        try:
            if not self.canvas.winfo_exists():
                self._running = False
                return
        except tk.TclError:
            self._running = False
            return

        if self._flash_left_ms > 0:
            self._flash_left_ms -= self.dt_ms

        frame = self._render_frame()
        self._last_render = frame
        self._draw_to_canvas(frame)
        if not self._running:
            return

        if self.state == "reveal" and not self._reveal_stepper_started:
            self._reveal_stepper_started = True
            self.root.after(self.reveal_step_ms, self._reveal_step)

        try:
            self.root.after(self.dt_ms, self._tick)
        except tk.TclError:
            self._running = False

    def _reveal_step(self):
        if self.state != "reveal":
            return

        self._reveal_i += 1

        if self._reveal_i >= len(self._reveal_blocks) - 1:
            self._flash_left_ms = self.flash_ms
            self.canvas.itemconfigure(self._status_text, text="ENHANCE: complete.")
            self.state = "final"

            if self.on_complete and not self._on_complete_called:
                self._on_complete_called = True
                self.root.after(self.flash_ms, self._show_compare_button)
            return

        self.root.after(self.reveal_step_ms, self._reveal_step)

    def _show_compare_button(self):
        if not self.on_complete or self._compare_button is not None:
            return
        btn = ttk.Button(self.footer, text="Compare Results", command=self._handle_compare)
        self._compare_button = btn
        try:
            btn.grid(row=0, column=1, sticky="e", padx=16, pady=(8, 8))
        except tk.TclError:
            self._compare_button = None

    def _handle_compare(self):
        self.stop()
        if self.on_complete:
            self.on_complete()


class ComparisonUI:
    def __init__(self, root, original_path, final_path):
        self.root = root
        for widget in root.winfo_children():
            widget.destroy()

        root.title("Nano Banana Enhancer - AI Result")
        root.configure(bg="#1e1e1e")
        root.geometry("900x600")

        self.orig_pil = Image.open(original_path)
        self.enh_pil = Image.open(final_path)

        header = tk.Label(
            root,
            text="Nano Banana Enhancement Complete",
            font=("Arial", 18, "bold"),
            fg="yellow",
            bg="#1e1e1e",
            pady=10,
        )
        header.pack(fill="x")

        self.display_frame = tk.Frame(root, bg="#1e1e1e")
        self.display_frame.pack(expand=True, fill="both", padx=20, pady=10)

        self.display_frame.columnconfigure(0, weight=1)
        self.display_frame.columnconfigure(1, weight=1)
        self.display_frame.rowconfigure(0, weight=1)

        self.orig_box = tk.Label(
            self.display_frame,
            bg="#1e1e1e",
            text="Original Crop",
            compound="top",
            fg="white",
        )
        self.orig_box.grid(row=0, column=0, sticky="nsew", padx=10)

        self.enh_box = tk.Label(
            self.display_frame,
            bg="#1e1e1e",
            text="AI Enhanced",
            compound="top",
            fg="cyan",
        )
        self.enh_box.grid(row=0, column=1, sticky="nsew", padx=10)

        root.bind("<Configure>", lambda e: root.after(50, self.update_images) if e.widget == root else None)

        btn = ttk.Button(root, text="Return to VLC", command=root.destroy)
        btn.pack(pady=20)

        self.root.after(100, self.update_images)

    def update_images(self, event=None):
        win_w = self.display_frame.winfo_width()
        win_h = self.display_frame.winfo_height()

        if win_w < 100 or win_h < 100:
            return

        target_w = (win_w // 2) - 40
        target_h = win_h - 40

        def get_resized_tk(pil_img, tw, th):
            pw, ph = pil_img.size
            ratio = min(tw / pw, th / ph)
            new_w, new_h = int(pw * ratio), int(ph * ratio)
            if new_w <= 0 or new_h <= 0:
                return None
            resized = pil_img.resize((new_w, new_h), Image.Resampling.LANCZOS)
            return ImageTk.PhotoImage(resized)

        tk_orig = get_resized_tk(self.orig_pil, target_w, target_h)
        tk_enh = get_resized_tk(self.enh_pil, target_w, target_h)

        if tk_orig and tk_enh:
            self.orig_box.configure(image=tk_orig)
            self.orig_box.image = tk_orig
            self.enh_box.configure(image=tk_enh)
            self.enh_box.image = tk_enh
