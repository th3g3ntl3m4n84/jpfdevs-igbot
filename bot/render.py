"""Render a post definition into a branded 1080x1350 JPEG (terminal aesthetic)."""
from __future__ import annotations

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
FONTS = ROOT / "assets" / "fonts"


def _font(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONTS / name), size)


def _hex(c: str) -> tuple[int, int, int]:
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_w: int) -> list[str]:
    lines, cur = [], ""
    for word in text.split():
        trial = f"{cur} {word}".strip()
        if draw.textlength(trial, font=font) <= max_w:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def _fit_headline(draw, text, max_w, max_h, start=104, minimum=56):
    """Largest Inter Bold size whose wrapped headline fits the box."""
    size = start
    while size >= minimum:
        f = _font("Inter-Bold.otf", size)
        lines = _wrap(draw, text, f, max_w)
        lh = int(size * 1.12)
        if len(lines) * lh <= max_h:
            return f, lines, lh
        size -= 4
    f = _font("Inter-Bold.otf", minimum)
    return f, _wrap(draw, text, f, max_w), int(minimum * 1.12)


def render_post(post: dict, cfg: dict, out_path: Path) -> Path:
    d = cfg["design"]
    W, H = d["width"], d["height"]
    bg, panel = _hex(d["background"]), _hex(d["panel"])
    text_c, muted, accent, red = (_hex(d[k]) for k in ("text", "muted", "accent", "accent2"))

    img = Image.new("RGB", (W, H), bg)
    draw = ImageDraw.Draw(img)

    # subtle grid
    grid = tuple(min(255, v + 7) for v in bg)
    for x in range(0, W, 54):
        draw.line([(x, 0), (x, H)], fill=grid, width=1)
    for y in range(0, H, 54):
        draw.line([(0, y), (W, y)], fill=grid, width=1)

    M = 72                       # outer margin
    inner = W - 2 * M

    # ── terminal window bar ─────────────────────────────────────
    bar_top, bar_h = 90, 64
    draw.rounded_rectangle([M, bar_top, W - M, bar_top + bar_h + 120], radius=18, fill=panel)
    draw.rectangle([M, bar_top + bar_h, W - M, bar_top + bar_h + 2], fill=bg)
    for i, col in enumerate([red, (255, 189, 46), (39, 201, 63)]):
        cx = M + 36 + i * 34
        draw.ellipse([cx - 10, bar_top + 22, cx + 10, bar_top + 42], fill=col)
    mono_s = _font("DejaVuSansMono.ttf", 26)
    title = f'{cfg["brand"]["prompt_user"]}@pentest: ~'
    tw = draw.textlength(title, font=mono_s)
    draw.text(((W - tw) / 2, bar_top + 18), title, font=mono_s, fill=muted)

    # command line
    mono = _font("DejaVuSansMono-Bold.ttf", 32)
    prompt = f'{cfg["brand"]["prompt_user"]}@pentest:~$ '
    cy = bar_top + bar_h + 42
    draw.text((M + 34, cy), prompt, font=mono, fill=accent)
    px = M + 34 + draw.textlength(prompt, font=mono)
    cmd = post.get("command", "")
    cmd_font = mono
    while draw.textlength(cmd + "_", font=cmd_font) > (W - M - 34 - px) and cmd_font.size > 18:
        cmd_font = _font("DejaVuSansMono-Bold.ttf", cmd_font.size - 2)
    draw.text((px, cy + (mono.size - cmd_font.size) / 2), cmd, font=cmd_font, fill=text_c)
    cur_x = px + draw.textlength(cmd, font=cmd_font) + 6
    draw.rectangle([cur_x, cy + 4, cur_x + 16, cy + 36], fill=accent)

    # ── body ────────────────────────────────────────────────────
    y = bar_top + bar_h + 120 + 90
    style = post.get("style", "statement")
    bullets = post.get("bullets") or []
    footer_top = H - 170

    if style == "stat":
        big = _font("Inter-Bold.otf", 260)
        draw.text((M - 8, y - 40), post["headline"], font=big, fill=accent)
        y += 270
        sub_f = _font("Inter-SemiBold.otf", 46)
        for line in _wrap(draw, post.get("sub", ""), sub_f, inner):
            draw.text((M, y), line, font=sub_f, fill=text_c)
            y += 58
        y += 40
    else:
        head_space = (footer_top - y) * (0.48 if bullets else 0.62)
        hf, lines, lh = _fit_headline(draw, post["headline"], inner, head_space)
        if not bullets:  # vertically centre short statement cards
            sub_lines = _wrap(draw, post.get("sub", ""), _font("Inter-Regular.otf", 40), inner)
            block = len(lines) * lh + 78 + len(sub_lines) * 52
            y += max(0, int((footer_top - y - block) / 2) - 40)
        for line in lines:
            draw.text((M, y), line, font=hf, fill=text_c)
            y += lh
        y += 26
        draw.rectangle([M, y, M + 120, y + 8], fill=accent)
        y += 44
        if post.get("sub"):
            sub_f = _font("Inter-Regular.otf", 40)
            for line in _wrap(draw, post["sub"], sub_f, inner):
                draw.text((M, y), line, font=sub_f, fill=muted)
                y += 52
            y += 30

    if bullets:
        bf = _font("Inter-SemiBold.otf", 40 if len(bullets) <= 4 else 34)
        gap = max(62, min(84, int((footer_top - 30 - y) / max(1, len(bullets)))))
        for b in bullets[:5]:
            draw.text((M, y), ">", font=_font("DejaVuSansMono-Bold.ttf", 40), fill=accent)
            blines = _wrap(draw, b, bf, inner - 56)
            for i, bl in enumerate(blines):
                draw.text((M + 56, y + i * 48), bl, font=bf, fill=text_c)
            y += gap + (len(blines) - 1) * 48

    # ── footer ──────────────────────────────────────────────────
    draw.line([(M, footer_top), (W - M, footer_top)], fill=tuple(min(255, v + 30) for v in bg), width=2)
    hf2 = _font("DejaVuSansMono-Bold.ttf", 34)
    draw.text((M, footer_top + 40), cfg["brand"]["handle"], font=hf2, fill=accent)
    tag = cfg["markets"][post["market"]]["tag"]
    tf = _font("Inter-SemiBold.otf", 28)
    tw = draw.textlength(tag, font=tf)
    draw.rounded_rectangle([W - M - tw - 40, footer_top + 36, W - M, footer_top + 86], radius=25,
                           outline=muted, width=2)
    draw.text((W - M - tw - 20, footer_top + 44), tag, font=tf, fill=muted)
    cf = _font("Inter-Regular.otf", 28)
    creds = "  •  ".join(cfg["brand"]["credentials"])
    draw.text((M, footer_top + 96), creds, font=cf, fill=muted)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, "JPEG", quality=92, optimize=True)
    return out_path
