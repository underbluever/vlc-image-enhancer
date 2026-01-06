import sys
import cv2
import ctypes
import numpy as np
import os
import time
import glob
import tkinter as tk
from tkinter import ttk
import threading
from google import genai
from PIL import Image, ImageTk, ImageOps
from animation_utils import RecursiveResolveUI, ComparisonUI

PROJECT_ID = os.getenv("NANO_BANANA_PROJECT", "YOUR_GCP_PROJECT_ID")
LOCATION = os.getenv("NANO_BANANA_LOCATION", "global")
MODEL_ID = os.getenv("NANO_BANANA_MODEL", "gemini-3-pro-image-preview")
DEFAULT_SNAPSHOT_DIR = os.getenv(
    "NANO_BANANA_SNAPSHOT_DIR",
    os.path.join(os.path.expanduser("~"), "Pictures", "VLC Snapshots"),
)

# FORCE Windows to give us the real 4K/Retina resolution
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

def get_latest_file(folder_path):
    print(f"Watching {folder_path} for new snapshot...")

    # We record the time RIGHT NOW. We only want files created AFTER this script started.
    # (Actually, we'll just look for the absolute newest file to be safe)

    # Retry Loop: Check for ~3 seconds (10 checks * 0.3s)
    for i in range(10):
        # 1. Get all images
        search_path = os.path.join(folder_path, "*")
        files = glob.glob(search_path)
        image_files = [f for f in files if f.lower().endswith(('.png', '.jpg', '.jpeg', '.tiff'))]

        if image_files:
            # 2. Find the newest one
            newest_file = max(image_files, key=os.path.getmtime)

            # 3. Check if it's "fresh" (created in the last 10 seconds)
            # This prevents opening an old screenshot from last week
            if time.time() - os.path.getmtime(newest_file) < 10:
                print(f"Found fresh snapshot: {newest_file}")
                return newest_file

        # Wait and try again
        print(f"Waiting for VLC... ({i+1}/10)")
        time.sleep(0.3)

    return None


def fix_orientation(image_path, vlc_orientation="Normal"):
    """
    Magic line that reads EXIF metadata and rotates.
    FALLBACK: If VLC told us the orientation explicitly, we force it.
    """
    with Image.open(image_path) as img:
        # 1. Try automatic EXIF fix (Standard)
        fixed_img = ImageOps.exif_transpose(img)

        # 2. Check if we need to force manual rotation (Fallback for VLC)
        # VLC Orientation strings: "Left bottom", "Right top", "Bottom right", "Normal"
        # Mapping to PIL rotations/transposes:
        # "Left bottom"  = Rotate 90 CCW (or 270 CW)
        # "Right top"    = Rotate 90 CW
        # "Bottom right" = Rotate 180

        # If the image is still the same size/orientation after exif_transpose,
        # but VLC says it's rotated, we apply manual fix.
        if fixed_img.size == img.size:
            if "Left bottom" in vlc_orientation:
                # EXIF 8: Top is Left. Fix: Rotate 90 CW (270 CCW in PIL)
                fixed_img = fixed_img.transpose(Image.ROTATE_270)
            elif "Right top" in vlc_orientation:
                # EXIF 6: Top is Right. Fix: Rotate 90 CCW
                fixed_img = fixed_img.transpose(Image.ROTATE_90)
            elif "Bottom right" in vlc_orientation:
                fixed_img = fixed_img.transpose(Image.ROTATE_180)

    fixed_img.save(image_path)
    return image_path

def select_crop_with_black_bars(image_path):
    # 1. Get standard screen resolution
    user32 = ctypes.windll.user32
    screen_w, screen_h = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)

    # 2. Load the original vertical image
    original_img = cv2.imread(image_path)
    if original_img is None:
        return None

    orig_h, orig_w = original_img.shape[:2]

    # 3. Calculate the Scaling Factor (fit within screen)
    # We want to fit the image inside the screen without stretching
    scale = min(screen_w / orig_w, screen_h / orig_h)
    new_w = int(orig_w * scale)
    new_h = int(orig_h * scale)

    # 4. Resize the image (keeping aspect ratio)
    resized_img = cv2.resize(original_img, (new_w, new_h))

    # 5. Create the Black Canvas (Fullscreen)
    canvas = np.zeros((screen_h, screen_w, 3), dtype=np.uint8)

    # 6. Calculate offsets to center the image
    x_offset = (screen_w - new_w) // 2
    y_offset = (screen_h - new_h) // 2

    # 7. Paste the resized image onto the canvas
    canvas[y_offset:y_offset + new_h, x_offset:x_offset + new_w] = resized_img

    # 8. Open the Fullscreen Window
    window_name = "Nano Banana Selector (Enter to Confirm)"
    cv2.namedWindow(window_name, cv2.WND_PROP_FULLSCREEN)
    cv2.setWindowProperty(window_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
    cv2.setWindowProperty(window_name, cv2.WND_PROP_TOPMOST, 1)

    # 9. Let user draw the rectangle on the CANVAS
    r = cv2.selectROI(window_name, canvas, fromCenter=False, showCrosshair=True)
    cv2.destroyAllWindows()

    # --- THE TRAP: COORDINATE MAPPING ---
    # The user drew on the screen (canvas), but we need the coordinates
    # for the ORIGINAL high-res image.

    # r is (x, y, w, h) on the screen
    screen_x, screen_y, screen_w_crop, screen_h_crop = r

    if screen_w_crop == 0:
        return None

    # 1. Map Start Coordinates (Top-Left)
    real_x = int((screen_x - x_offset) / scale)
    real_y = int((screen_y - y_offset) / scale)

    # 2. Map End Coordinates (Bottom-Right)
    # We calculate the absolute end point first
    real_x_end = int((screen_x + screen_w_crop - x_offset) / scale)
    real_y_end = int((screen_y + screen_h_crop - y_offset) / scale)

    # 3. CLAMP EVERYONE (The Safety Armor)
    # Ensure start is at least 0, and no more than image width
    real_x = max(0, min(orig_w, real_x))
    real_y = max(0, min(orig_h, real_y))

    # Ensure end is at least 0, and no more than image width
    real_x_end = max(0, min(orig_w, real_x_end))
    real_y_end = max(0, min(orig_h, real_y_end))

    # 4. Calculate final width/height from the clamped coordinates
    final_w = real_x_end - real_x
    final_h = real_y_end - real_y

    # 5. FINAL CHECK: Did they select nothing? (e.g. clicked entirely in black bar)
    if final_w <= 0 or final_h <= 0:
        print("Selection was outside the image area!")
        return None

    # 6. Crop
    final_crop = original_img[real_y:real_y_end, real_x:real_x_end]

    return final_crop

def vibe_snip(folder_path, vlc_orientation="Normal"):
    # 1. FIND THE FILE
    image_path = get_latest_file(folder_path)

    if not image_path:
        print("Error: VLC didn't save the file in time (or saved it somewhere else).")
        print("Please check: Tools -> Preferences -> Video -> Directory")
        input("Press Enter to exit...")
        return

    # NEW: Fix orientation before processing
    fix_orientation(image_path, vlc_orientation)

    # 2. SELECTION (Smart Letterboxing)
    crop = select_crop_with_black_bars(image_path)

    if crop is not None:
        print("Enhancing selection...")

        # Generate permanent crop path: name_crop.png
        folder, filename = os.path.split(image_path)
        name, ext = os.path.splitext(filename)
        save_crop_path = os.path.join(folder, f"{name}_crop{ext}")

        cv2.imwrite(save_crop_path, crop)
        print(f"Crop saved: {save_crop_path}")

        # Send original path so we can save the result next to it
        send_to_banana(save_crop_path, image_path)
    else:
        print("Selection cancelled.")

def send_to_banana(crop_path, original_full_path):
    # 1. SETUP ENVIRONMENT
    client = genai.Client(
        vertexai=True,
        project=PROJECT_ID,
        location=LOCATION
    )

    # Pre-calculate save path
    folder, filename = os.path.split(original_full_path)
    name, ext = os.path.splitext(filename)
    new_filename = f"{name}_enhanced{ext}"
    save_path = os.path.join(folder, new_filename)

    # 2. INITIALIZE ANIMATION GUI
    base_pil = Image.open(crop_path).convert("RGB")
    ui = RecursiveResolveUI(base_pil)
    ui.root.attributes("-topmost", True)

    def open_comparison():
        ComparisonUI(ui.root, crop_path, save_path)
        ui.root.attributes("-topmost", False)

    ui.on_complete = open_comparison

    # 3. DEFINE GEMINI WORKER
    def gemini_worker():
        print("Nano Enhancement Protocol: Contacting Central Server...")
        try:
            prompt = "You are a professional image enhancer. Analyze this movie frame. Generate a high-fidelity, 4K remastered version of this specific scene. Keep the character identity and lighting exactly the same, but sharpen details, remove noise, and improve texture quality. Output: A photorealistic replica of the input. "
            with Image.open(crop_path) as image_file:
                image_file.load()
                response = client.models.generate_content(
                    model=MODEL_ID,
                    contents=[prompt, image_file]
                )

            candidates = getattr(response, "candidates", None)
            if not candidates:
                print("No candidates returned from the model.")
                return

            content = getattr(candidates[0], "content", None)
            parts = getattr(content, "parts", []) if content else []
            image_part = next((part for part in parts if getattr(part, "inline_data", None)), None)

            if not image_part:
                for part in parts:
                    if getattr(part, "text", None):
                        print(part.text)
                print("No image part returned.")
                return

            final_img = image_part.as_image()
            final_img.save(save_path)
            print(f"Enhancement Downloaded: {save_path}")

            with Image.open(save_path) as pil_final:
                final_pil = pil_final.convert("RGB")
            ui.root.after(0, lambda img=final_pil: ui.set_enhanced_image(img))

        except Exception as e:
            print(f"CSI Protocol Error: {e}")
            ui.root.after(0, ui.root.destroy)

    # 4. START THE BRAIN
    t = threading.Thread(target=gemini_worker)
    t.daemon = True
    t.start()

    ui.mainloop()

if __name__ == "__main__":
    if len(sys.argv) > 2:
        # Case: Passed via VLC (Folder, Orientation)
        vibe_snip(sys.argv[1], sys.argv[2])
    elif len(sys.argv) > 1:
        # Case: Manual Folder call
        vibe_snip(sys.argv[1])
    else:
        # Default for testing
        vibe_snip(DEFAULT_SNAPSHOT_DIR)
