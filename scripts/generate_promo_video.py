import os
import sys
import math
import subprocess
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps

WIDTH = 1080
HEIGHT = 1920
FPS = 30
DURATION_SEC = 18
TOTAL_FRAMES = FPS * DURATION_SEC

# Paths
ASSETS_DIR = r"C:\Users\Admin\.gemini\antigravity\brain\0ed903bb-b5f7-4f3c-b3f6-43c857de24e7"
AQYL_IMG_PATH = os.path.join(ASSETS_DIR, "saq_mascot_aqyl_1786365746072.jpg")
GRAPH_IMG_PATH = os.path.join(ASSETS_DIR, "saq_graph_visual_1786365760730.jpg")
WATCHLIST_IMG_PATH = os.path.join(ASSETS_DIR, "saq_card_watchlist_1786366010717.jpg")
LEARN_IMG_PATH = os.path.join(ASSETS_DIR, "saq_card_learn_1786366027772.jpg")

OUTPUT_MP4 = os.path.join(r"d:\Новая папка", "saq_promo_review.mp4")

# Load fonts
FONT_REGULAR_PATH = r"C:\Windows\Fonts\segoeui.ttf"
FONT_BOLD_PATH = r"C:\Windows\Fonts\segoeuib.ttf"
FONT_BLACK_PATH = r"C:\Windows\Fonts\ariblk.ttf" if os.path.exists(r"C:\Windows\Fonts\ariblk.ttf") else FONT_BOLD_PATH

font_title_large = ImageFont.truetype(FONT_BOLD_PATH, 72)
font_title_med = ImageFont.truetype(FONT_BOLD_PATH, 56)
font_body_bold = ImageFont.truetype(FONT_BOLD_PATH, 42)
font_body_reg = ImageFont.truetype(FONT_REGULAR_PATH, 36)
font_small = ImageFont.truetype(FONT_REGULAR_PATH, 28)
font_hero = ImageFont.truetype(FONT_BOLD_PATH, 96)

# Load images
def load_and_contain(path, max_w, max_h, rounded=24):
    if not os.path.exists(path):
        # Fallback dark image
        img = Image.new("RGBA", (max_w, max_h), (20, 30, 50, 255))
        return img
    img = Image.open(path).convert("RGBA")
    img.thumbnail((max_w, max_h), Image.Resampling.LANCZOS)
    
    # Add rounded corners
    mask = Image.new("L", img.size, 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle((0, 0, img.size[0], img.size[1]), radius=rounded, fill=255)
    
    rounded_img = Image.new("RGBA", img.size, (0, 0, 0, 0))
    rounded_img.paste(img, (0, 0), mask=mask)
    return rounded_img

img_aqyl = load_and_contain(AQYL_IMG_PATH, 700, 700, rounded=36)
img_graph = load_and_contain(GRAPH_IMG_PATH, 650, 750, rounded=28)
img_watchlist = load_and_contain(WATCHLIST_IMG_PATH, 650, 500, rounded=28)
img_learn = load_and_contain(LEARN_IMG_PATH, 650, 500, rounded=28)

def draw_glowing_background(draw, frame_idx):
    # Base dark gradient
    for y in range(HEIGHT):
        r = int(11 + (y / HEIGHT) * 8)
        g = int(15 + (y / HEIGHT) * 12)
        b = int(25 + (y / HEIGHT) * 20)
        draw.line([(0, y), (WIDTH, y)], fill=(r, g, b))
    
    # Animated radial glows
    t = frame_idx / 30.0
    pulse1 = (math.sin(t * 2.0) + 1) * 0.5
    cx1 = int(WIDTH * 0.5 + math.sin(t * 1.5) * 100)
    cy1 = int(HEIGHT * 0.35 + math.cos(t * 1.2) * 80)
    
    # Draw glow circle
    glow_color = (0, 242, 254, int(15 + pulse1 * 10))
    draw.ellipse((cx1 - 350, cy1 - 350, cx1 + 350, cy1 + 350), fill=glow_color)

def draw_pill_highlight(draw, text, x, y, font, text_color, bg_color, border_color=None, padding=(24, 12), radius=16):
    bbox = font.getbbox(text)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    px, py = padding
    
    x1, y1 = x - px, y - py
    x2, y2 = x + tw + px, y + th + py
    
    draw.rounded_rectangle((x1, y1, x2, y2), radius=radius, fill=bg_color, outline=border_color, width=2 if border_color else 0)
    draw.text((x, y - bbox[1]), text, font=font, fill=text_color)
    return x2 + px

def draw_underline(draw, text, x, y, font, text_color, line_color, thickness=6):
    bbox = font.getbbox(text)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    
    draw.text((x, y - bbox[1]), text, font=font, fill=text_color)
    ly = y + th + 10
    draw.line([(x, ly), (x + tw, ly)], fill=line_color, width=thickness)
    return x + tw

def render_frame(frame_idx):
    base = Image.new("RGBA", (WIDTH, HEIGHT), (11, 15, 25, 255))
    draw = ImageDraw.Draw(base)
    draw_glowing_background(draw, frame_idx)
    
    t = frame_idx / 30.0
    
    # Scene 1: 0 - 90 frames (0 - 3.0s)
    if frame_idx < 90:
        alpha1 = min(1.0, frame_idx / 15.0)
        # "Хотите защитить себя"
        draw.text((100, 750), "Хотите защитить себя", font=font_title_med, fill=(255, 255, 255, int(255 * alpha1)))
        
        if frame_idx >= 25:
            alpha2 = min(1.0, (frame_idx - 25) / 15.0)
            # "от финансовых пирамид?" with red neon underline
            draw_underline(draw, "от финансовых пирамид?", 100, 860, font_title_large, (255, 255, 255, int(255 * alpha2)), (255, 65, 108, int(255 * alpha2)), thickness=8)
            
            # Subtle question mark badge
            draw.text((100, 1000), "SAQ • Финансовый OSINT-Щит", font=font_body_reg, fill=(0, 242, 254, int(200 * alpha2)))
            
    # Scene 2: 90 - 180 frames (3.0 - 6.0s)
    elif frame_idx < 180:
        local_f = frame_idx - 90
        alpha1 = min(1.0, local_f / 15.0)
        
        draw.text((100, 750), "Проверьте любой проект", font=font_title_med, fill=(255, 255, 255, int(255 * alpha1)))
        
        if local_f >= 20:
            alpha2 = min(1.0, (local_f - 20) / 15.0)
            
            # Draw pill around "ДО того"
            rx = draw_pill_highlight(draw, "ДО того,", 100, 860, font_title_large, (11, 15, 25), (0, 242, 254), radius=20, padding=(28, 14))
            draw.text((rx + 20, 860), "как вложить деньги", font=font_title_large, fill=(255, 255, 255, int(255 * alpha2)))
            
            draw.text((100, 1020), "Сайт • Telegram • Крипто-кошелёк • Компания", font=font_body_reg, fill=(160, 180, 210, int(230 * alpha2)))

    # Scene 3: 180 - 270 frames (6.0 - 9.0s) -> Brand Reveal & Mascot Aqyl
    elif frame_idx < 270:
        local_f = frame_idx - 180
        alpha1 = min(1.0, local_f / 15.0)
        
        # "Представляем"
        draw.text((WIDTH//2 - 160, 320), "Представляем", font=font_body_bold, fill=(160, 180, 210, int(255 * alpha1)))
        
        # SAQ logo reveal
        scale = min(1.0, local_f / 20.0)
        draw.text((WIDTH//2 - 130, 400), "SAQ", font=font_hero, fill=(0, 242, 254, int(255 * alpha1)))
        draw.text((WIDTH//2 - 240, 520), "Умный ассистент расследований", font=font_body_reg, fill=(255, 255, 255, int(255 * alpha1)))
        
        # Paste Mascot Aqyl centered
        if local_f >= 15:
            scale_f = min(1.0, (local_f - 15) / 20.0)
            pop_y = int(680 + (1.0 - scale_f) * 60)
            
            # Draw glow ring behind Aqyl
            draw.ellipse((WIDTH//2 - 280, pop_y - 20, WIDTH//2 + 280, pop_y + 540), fill=(0, 242, 254, 30))
            
            w_a, h_a = img_aqyl.size
            base.paste(img_aqyl, (WIDTH//2 - w_a//2, pop_y), mask=img_aqyl)
            
            # Badge under Aqyl
            draw_pill_highlight(draw, "Маскот Aqyl • ИИ-Детектив", WIDTH//2 - 250, pop_y + h_a + 30, font_body_bold, (255, 255, 255), (20, 30, 50, 230), border_color=(0, 242, 254), radius=16, padding=(30, 12))

    # Scene 4: 270 - 450 frames (9.0 - 15.0s) -> Horizontal 3D Carousel Showcase
    elif frame_idx < 450:
        local_f = frame_idx - 270
        
        # Top persistent header
        draw.text((100, 220), "Единая платформа OSINT-защиты", font=font_body_bold, fill=(0, 242, 254))
        draw.text((100, 280), "Автоматический разбор угроз за секунды", font=font_title_med, fill=(255, 255, 255))
        
        # Cards carousel progression
        cards = [
            {"title": "1. ИИ-Расследователь Aqyl", "subtitle": "Claude tool-use • 15+ источников", "img": img_aqyl},
            {"title": "2. Интерактивный Граф Связей", "subtitle": "Визуализация рисков 0-100", "img": img_graph},
            {"title": "3. Watchlist & Автомониторинг", "subtitle": "CertStream сканирование фишинга", "img": img_watchlist},
            {"title": "4. Школа Защиты & SAQ Балалар", "subtitle": "Обучение и викторины для всех", "img": img_learn},
        ]
        
        # Smooth scrolling position based on time
        scroll_x = local_f * 13.5  # pixels scrolled
        
        card_w = 680
        card_spacing = 740
        start_base_x = 100
        
        for i, card in enumerate(cards):
            cx = int(start_base_x + i * card_spacing - scroll_x)
            cy = 440
            
            if cx + card_w < -100 or cx > WIDTH + 100:
                continue
                
            # Card background shadow / container
            draw.rounded_rectangle((cx, cy, cx + card_w, cy + 980), radius=32, fill=(18, 25, 42, 240), outline=(42, 54, 79), width=3)
            
            # Card Title & Subtitle
            draw.text((cx + 40, cy + 40), card["title"], font=font_body_bold, fill=(255, 255, 255))
            draw.text((cx + 40, cy + 95), card["subtitle"], font=font_small, fill=(0, 242, 254))
            
            # Card Image inside container
            c_img = card["img"]
            iw, ih = c_img.size
            # center image inside card
            ix = cx + (card_w - iw) // 2
            iy = cy + 160
            base.paste(c_img, (ix, iy), mask=c_img)
            
            # Bottom action tag
            draw_pill_highlight(draw, "Подробнее →", cx + 40, cy + 880, font_small, (255, 255, 255), (0, 242, 254, 40), border_color=(0, 242, 254), radius=12, padding=(18, 8))

    # Scene 5: 450 - 540 frames (15.0 - 18.0s) -> Slogan & Outro Call To Action
    else:
        local_f = frame_idx - 450
        alpha1 = min(1.0, local_f / 15.0)
        
        # Centered SAQ Logo
        draw.text((WIDTH//2 - 140, 380), "SAQ", font=font_hero, fill=(0, 242, 254, int(255 * alpha1)))
        
        # Mascot Aqyl small preview
        w_a, h_a = img_aqyl.size
        # scale down aqyl slightly for outro
        sq_aqyl = img_aqyl.resize((450, 450), Image.Resampling.LANCZOS)
        base.paste(sq_aqyl, (WIDTH//2 - 225, 520), mask=sq_aqyl)
        
        # Main slogan
        draw.text((WIDTH//2 - 380, 1020), "Проверь до того, как вложишь!", font=font_title_med, fill=(255, 255, 255, int(255 * alpha1)))
        
        # Web link pill button
        draw_pill_highlight(draw, "saq-kz.org  •  Начать проверку", WIDTH//2 - 340, 1160, font_body_bold, (11, 15, 25), (0, 242, 254), radius=24, padding=(40, 20))
        
        # Subtitle feature badges
        draw.text((WIDTH//2 - 330, 1300), "15+ Источников  •  ИИ Aqyl  •  Watchlist", font=font_body_reg, fill=(160, 180, 210, int(230 * alpha1)))
        
    return base.convert("RGB")

def main():
    print(f"Starting video generation ({TOTAL_FRAMES} frames @ {FPS} FPS)...")
    
    # Launch ffmpeg process writing raw RGB24 frames from stdin
    cmd = [
        "ffmpeg", "-y",
        "-f", "rawvideo",
        "-vcodec", "rawvideo",
        "-s", f"{WIDTH}x{HEIGHT}",
        "-pix_fmt", "rgb24",
        "-r", str(FPS),
        "-i", "-",
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "18",
        "-pix_fmt", "yuv420p",
        OUTPUT_MP4
    ]
    
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    
    for i in range(TOTAL_FRAMES):
        frame = render_frame(i)
        proc.stdin.write(frame.tobytes())
        if (i + 1) % 30 == 0:
            print(f"Rendered {i + 1}/{TOTAL_FRAMES} frames ({(i + 1)//30}s / {DURATION_SEC}s)")
            
    proc.stdin.close()
    proc.wait()
    
    print(f"SUCCESS! Promo Video saved to: {OUTPUT_MP4}")

if __name__ == "__main__":
    main()
