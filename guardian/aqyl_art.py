"""
Aqyl — маскот SAQ, отрисованный на PIL по той же геометрии, что и
SVG-версия на сайте (web/src/components/SaqMark.tsx): та же сетка 48×48,
те же градиенты, те же пропорции головы, ушей и лицевой панели.

Рисуем с суперсэмплингом (×SS, потом downscale) — PIL не умеет
сглаживание сам, а без него у круглых форм видны ступеньки.
"""

from PIL import Image, ImageDraw

SS = 8  # supersampling factor

NAVY = (19, 42, 99)
TONGUE = (224, 82, 109)
BLUSH = (123, 163, 245)
WHITE = (255, 255, 255)

HEAD_G = [(0.0, (95, 148, 249)), (0.55, (47, 106, 232)), (1.0, (28, 78, 207))]
EAR_G = [(0.0, (77, 131, 242)), (1.0, (30, 77, 196))]
FACE_G = [(0.0, (255, 255, 255)), (1.0, (238, 244, 255))]


def _lerp(a, b, t):
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def _sample_stops(stops, t):
    t = max(0.0, min(1.0, t))
    for i in range(len(stops) - 1):
        p0, c0 = stops[i]
        p1, c1 = stops[i + 1]
        if p0 <= t <= p1:
            local = 0 if p1 == p0 else (t - p0) / (p1 - p0)
            return _lerp(c0, c1, local)
    return stops[-1][1]


def _gradient(size, stops, p0, p1):
    """Линейный градиент по вектору p0→p1 (в координатах картинки)."""
    w, h = size
    img = Image.new("RGB", size)
    px = img.load()
    x0, y0 = p0
    x1, y1 = p1
    dx, dy = x1 - x0, y1 - y0
    denom = dx * dx + dy * dy or 1
    for y in range(h):
        for x in range(w):
            t = ((x - x0) * dx + (y - y0) * dy) / denom
            px[x, y] = _sample_stops(stops, t)
    return img


def _rot_ellipse(draw, cx, cy, rx, ry, angle_deg, fill, k=1.0):
    """Повёрнутый эллипс полигоном — PIL сам такого не умеет."""
    import math

    a = math.radians(angle_deg)
    pts = []
    for i in range(72):
        th = 2 * math.pi * i / 72
        ex, ey = rx * math.cos(th), ry * math.sin(th)
        pts.append(
            (
                (cx + ex * math.cos(a) - ey * math.sin(a)) * k,
                (cy + ex * math.sin(a) + ey * math.cos(a)) * k,
            )
        )
    draw.polygon(pts, fill=fill)


def render_aqyl(size: int = 128, mood: str = "happy", ss: int = SS) -> Image.Image:
    """Маскот Aqyl как RGBA-картинка. mood: happy | neutral | alert.

    ss — суперсэмплинг. Градиенты считаются попиксельно на чистом Python,
    поэтому цена растёт как (size*ss)²: для иконки в трее хватает ss=3,
    ss=8 держим только для крупных превью.
    """
    k = size * ss / 48.0  # масштаб из SVG-сетки 48 в пиксели
    W = H = size * ss
    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))

    def S(v):
        return v * k

    # ---- уши (под головой) ----
    ear_mask = Image.new("L", (W, H), 0)
    ed = ImageDraw.Draw(ear_mask)
    _rot_ellipse(ed, 14, 11, 4.6, 6.4, -24, 255, k)
    _rot_ellipse(ed, 34, 11, 4.6, 6.4, 24, 255, k)
    ear_grad = _gradient((W, H), EAR_G, (S(8), S(4)), (S(40), S(18)))
    canvas.paste(ear_grad, (0, 0), ear_mask)

    # блики на ушах
    hl = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    hd = ImageDraw.Draw(hl)
    _rot_ellipse(hd, 13.4, 9.6, 1.7, 2.6, -24, (141, 179, 250, 140), k)
    _rot_ellipse(hd, 34.6, 9.6, 1.7, 2.6, 24, (141, 179, 250, 140), k)
    canvas = Image.alpha_composite(canvas, hl)

    # ---- голова ----
    head_mask = Image.new("L", (W, H), 0)
    hdm = ImageDraw.Draw(head_mask)
    # SVG-путь головы — скруглённый блоб x 6..42, y 10..43; эллипс совпадает
    # с ним в пределах пары пикселей на нашем размере
    hdm.ellipse([S(6), S(10), S(42), S(43)], fill=255)
    head_grad = _gradient((W, H), HEAD_G, (S(10), S(8)), (S(38), S(44)))
    canvas.paste(head_grad, (0, 0), head_mask)

    # глянцевый блик на макушке
    gloss = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(gloss)
    _rot_ellipse(gd, 19, 14.6, 7.5, 3, -12, (255, 255, 255, 77), k)
    canvas = Image.alpha_composite(canvas, gloss)

    # ---- лицевая панель ----
    face_mask = Image.new("L", (W, H), 0)
    fd = ImageDraw.Draw(face_mask)
    fd.ellipse([S(11), S(18.4), S(37), S(36.6)], fill=255)
    face_grad = _gradient((W, H), FACE_G, (S(24), S(18)), (S(24), S(37)))
    canvas.paste(face_grad, (0, 0), face_mask)

    d = ImageDraw.Draw(canvas)

    # ---- глаза ----
    if mood in ("happy", "excited"):
        # закрытые «улыбающиеся» дуги
        for cx in (18.6, 29.4):
            d.arc(
                [S(cx - 3.2), S(26.4), S(cx + 3.2), S(31.2)],
                start=200, end=340, fill=NAVY, width=int(S(1.1)),
            )
    else:
        r = 3.1
        for cx, hx in ((18.6, 19.7), (29.4, 30.5)):
            d.ellipse([S(cx - r), S(28 - r), S(cx + r), S(28 + r)], fill=NAVY)
            d.ellipse([S(hx - 1), S(25.9), S(hx + 1), S(27.9)], fill=WHITE)

    # ---- рот ----
    if mood in ("happy", "excited"):
        d.chord([S(20.4), S(29.2), S(27.6), S(36)], start=0, end=180, fill=NAVY)
        d.chord([S(21.8), S(33.2), S(26.2), S(36.4)], start=0, end=180, fill=TONGUE)
    elif mood == "alert":
        d.arc([S(21.2), S(32.6), S(26.8), S(36.4)], start=190, end=350, fill=NAVY, width=int(S(1.1)))
        # брови
        d.line([S(14.6), S(23.4), S(20.8), S(25.3)], fill=NAVY, width=int(S(1.3)))
        d.line([S(33.4), S(23.4), S(27.2), S(25.3)], fill=NAVY, width=int(S(1.3)))
    else:
        d.arc([S(21.4), S(31), S(26.6), S(34.6)], start=15, end=165, fill=NAVY, width=int(S(1.1)))

    # ---- румянец ----
    if mood in ("happy", "excited"):
        blush = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        bd = ImageDraw.Draw(blush)
        bd.ellipse([S(12.4), S(30.4), S(16.4), S(32.8)], fill=BLUSH + (128,))
        bd.ellipse([S(31.6), S(30.4), S(35.6), S(32.8)], fill=BLUSH + (128,))
        canvas = Image.alpha_composite(canvas, blush)

    return canvas.resize((size, size), Image.LANCZOS)


def render_shield(size: int = 128, mood: str = "happy", ss: int = SS) -> Image.Image:
    """Логотип SAQ — щит с Aqyl внутри (как SaqMark на сайте)."""
    k = size * ss / 48.0
    W = H = size * ss
    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(canvas)

    def S(v):
        return v * k

    shield = [
        (S(24), S(2.5)), (S(5), S(9.8)), (S(5), S(21.2)),
        (S(9), S(33)), (S(16), S(41.5)), (S(24), S(46.5)),
        (S(32), S(41.5)), (S(39), S(33)), (S(43), S(21.2)),
        (S(43), S(9.8)),
    ]
    d.polygon(shield, fill=(20, 31, 54, 255), outline=(47, 106, 232, 255))
    # контур потолще — PIL не даёт width у polygon
    d.line(shield + [shield[0]], fill=(47, 106, 232, 255), width=int(S(1.3)), joint="curve")

    canvas = canvas.resize((size, size), Image.LANCZOS)

    inner = render_aqyl(int(size * 0.62), mood=mood, ss=ss)
    canvas.alpha_composite(inner, (int(size * 0.19), int(size * 0.16)))
    return canvas


def rounded_card(
    w: int, h: int, radius: int = 18,
    top=(20, 31, 54), bottom=(15, 23, 42), border=(30, 41, 59), border_w: int = 1,
    ss: int = 3,
) -> Image.Image:
    """Скруглённая карточка с вертикальным градиентом — тот же приём, что
    в CSS-фоне карточек сайта (linear-gradient 160deg). Используется как
    фон под Tkinter-виджетами через ImageTk.PhotoImage, потому что нативные
    tk-виджеты рисовать градиенты и скругления не умеют."""
    W, H, R = w * ss, h * ss, radius * ss
    grad = _gradient((W, H), [(0.0, top), (1.0, bottom)], (0, 0), (0, H))
    mask = Image.new("L", (W, H), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, W - 1, H - 1], radius=R, fill=255)
    card = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    card.paste(grad, (0, 0), mask)
    if border_w:
        bd = ImageDraw.Draw(card)
        bd.rounded_rectangle(
            [border_w * ss / 2, border_w * ss / 2, W - 1 - border_w * ss / 2, H - 1 - border_w * ss / 2],
            radius=R, outline=border, width=max(1, border_w * ss),
        )
    return card.resize((w, h), Image.LANCZOS)


def rounded_button(w: int, h: int, color, radius=None, ss: int = 3) -> Image.Image:
    """Заливка одним цветом со скруглением — под кнопки/пилюли/бейджи."""
    radius = radius if radius is not None else h // 2
    W, H, R = w * ss, h * ss, radius * ss
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(img).rounded_rectangle([0, 0, W - 1, H - 1], radius=R, fill=color)
    return img.resize((w, h), Image.LANCZOS)


def dot(size: int, color, ss: int = 4) -> Image.Image:
    S = size * ss
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(img).ellipse([0, 0, S - 1, S - 1], fill=color)
    return img.resize((size, size), Image.LANCZOS)


if __name__ == "__main__":
    render_aqyl(256, "happy").save("aqyl_preview.png")
    render_shield(256, "happy").save("shield_preview.png")
    print("saved previews")
