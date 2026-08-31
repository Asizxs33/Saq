# SAQ — промт для референсного кадра талисмана (text-to-image)

Сгенерируй этим промтом ОДНО изображение — и используй его как reference/character-lock во всех 8 видео-промтах, чтобы персонаж не менялся между сценами.

---

## Основной промт (анфас, для reference image)

"Character design reference sheet, single clean illustration on a plain dark navy background (#0a1428), centered, studio-lit. A friendly round blue robotic guardian mascot character: a soft rounded body like a small plush robot, smooth matte cyan-blue and light-blue gradient shell, two large rounded ears standing up on top of its head (like a small bear/rabbit hybrid), big soft dark eyes with a calm, warm, confident expression, a small simple smile, no visible mouth machinery — friendly and approachable, not mechanical-scary. A glowing soft cyan-white light embedded in the center of its chest, like a heartbeat/status indicator, casting a subtle gentle glow onto the surrounding dark background. Small simple rounded arms and stubby legs, no visible joints or wires — smooth toy-like silhouette. 2D flat-vector illustration style, clean bold outlines, soft cel-shading, minimal gradient shading, no photorealism, no 3D render look, no textures or grain. Standing in a simple front-facing pose, arms relaxed at its sides. High detail on the face and chest light, simple flat body. Square-ish composition, character fills about 60% of frame height, centered, symmetrical lighting, no background elements, no props, no other characters."

---

## Опционально — доп. ракурсы (если сервис поддерживает несколько картинок за раз)

**3/4 ракурс (для вариативности в сценах):**
"Same character, same design, 3/4 turned pose facing slightly right, one arm raised as if pointing, same dark navy background, same flat-vector style, same glowing chest light."

**Профиль в движении (для сцен с полётом узлов графа):**
"Same character, same design, side profile, mid-stride walking pose, slight motion blur suggestion only in the ears, same style and background."

---

## Как использовать
1. Сгенерируй основной промт (анфас) — это твой мастер-референс.
2. При генерации каждой из 8 сцен из `video_prompts_animated.md` — если сервис (Kling / Pika / Higgsfield) даёт поле "reference image" / "character reference" / "image-to-video seed" — прикрепи туда этот кадр.
3. Если поля для референса нет — просто скопируй абзац описания персонажа (второе предложение промта выше, про "a friendly round blue robotic guardian mascot...") дословно в начало каждого из 8 видео-промтов — точное повторение формулировок тоже ощутимо помогает генератору держать один и тот же дизайн.
