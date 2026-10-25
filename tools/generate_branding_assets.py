#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2026 i7Exceed, Sumeragi Native+ Contributors.
"""Generates the original visual identity assets for Sumeragi Native+.

Produces:
  assets/sumeragi_icon.svg  - Vector emblem (Japanese technical crest)
  assets/sumeragi_logo.svg  - Vector wordmark & emblem with tagline
  launcher/sumeragi.ico     - Windows multi-resolution icon (16..256px)
  launcher/sumeragi.png     - Master transparent PNG icon (512x512)
"""

from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter

REPO_ROOT = Path(__file__).resolve().parent.parent
ASSETS_DIR = REPO_ROOT / "assets"
LAUNCHER_DIR = REPO_ROOT / "launcher"

# Palette: Dark Charcoal, Antique Gold, Warm Ivory, Lacquer Crimson
BG_DARK = "#12100e"
PANEL_DARK = "#1c1916"
GOLD_PRIMARY = "#c9a24a"
GOLD_LIGHT = "#e5c572"
GOLD_DARK = "#917028"
IVORY_LIGHT = "#eadfcb"
IVORY_PURE = "#f8f3ea"
CRIMSON_ACCENT = "#a93226"

SIZES = (16, 24, 32, 48, 64, 128, 256)


def create_svg_icon() -> str:
    """Returns SVG XML for the Sumeragi Native+ emblem."""
    return """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" width="512" height="512">
  <defs>
    <linearGradient id="goldGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#f3d88b"/>
      <stop offset="50%" stop-color="#c9a24a"/>
      <stop offset="100%" stop-color="#8d6b1e"/>
    </linearGradient>
    <linearGradient id="ivoryGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#ffffff"/>
      <stop offset="100%" stop-color="#eadfcb"/>
    </linearGradient>
    <radialGradient id="crimsonCenter" cx="50%" cy="50%" r="50%">
      <stop offset="0%" stop-color="#d63f33"/>
      <stop offset="100%" stop-color="#8a1a12"/>
    </radialGradient>
    <filter id="subtleGlow" x="-20%" y="-20%" width="140%" height="140%">
      <feGaussianBlur stdDeviation="8" result="blur"/>
      <feComposite in="SourceGraphic" in2="blur" operator="over"/>
    </filter>
  </defs>

  <!-- Outer Protective Ornamental Hexagon / Mon Frame -->
  <polygon points="256,24 456,140 456,372 256,488 56,372 56,140"
           fill="none" stroke="url(#goldGrad)" stroke-width="10" stroke-linejoin="round" opacity="0.9"/>
  <polygon points="256,42 440,148 440,364 256,470 72,364 72,148"
           fill="none" stroke="#25211b" stroke-width="4" stroke-linejoin="round"/>

  <!-- Corner Technical Accent Nodes -->
  <circle cx="256" cy="24" r="7" fill="#f3d88b"/>
  <circle cx="456" cy="140" r="7" fill="#f3d88b"/>
  <circle cx="456" cy="372" r="7" fill="#f3d88b"/>
  <circle cx="256" cy="488" r="7" fill="#f3d88b"/>
  <circle cx="56" cy="372" r="7" fill="#f3d88b"/>
  <circle cx="56" cy="140" r="7" fill="#f3d88b"/>

  <!-- Four-Diamond Crest (Sumeragi Hishi / Crest Motif) -->
  <!-- Top Lozenge -->
  <polygon points="256,76 336,196 256,236 176,196" fill="url(#goldGrad)" stroke="#12100e" stroke-width="4"/>
  <polygon points="256,96 316,190 256,220 196,190" fill="url(#ivoryGrad)" opacity="0.85"/>

  <!-- Bottom Lozenge -->
  <polygon points="256,436 336,316 256,276 176,316" fill="url(#goldGrad)" stroke="#12100e" stroke-width="4"/>
  <polygon points="256,416 316,322 256,292 196,322" fill="url(#ivoryGrad)" opacity="0.85"/>

  <!-- Left Lozenge -->
  <polygon points="76,256 196,176 236,256 196,336" fill="url(#goldGrad)" stroke="#12100e" stroke-width="4"/>
  <polygon points="96,256 190,196 220,256 190,316" fill="url(#ivoryGrad)" opacity="0.85"/>

  <!-- Right Lozenge -->
  <polygon points="436,256 316,176 276,256 316,336" fill="url(#goldGrad)" stroke="#12100e" stroke-width="4"/>
  <polygon points="416,256 322,196 292,256 322,316" fill="url(#ivoryGrad)" opacity="0.85"/>

  <!-- Center Focal Emblem: The '+' (Native Plus Core) in Lacquer Crimson -->
  <rect x="240" y="216" width="32" height="80" rx="4" fill="url(#crimsonCenter)" stroke="#f3d88b" stroke-width="3"/>
  <rect x="216" y="240" width="80" height="32" rx="4" fill="url(#crimsonCenter)" stroke="#f3d88b" stroke-width="3"/>

  <!-- Inner Diamond Highlight Accent -->
  <polygon points="256,242 270,256 256,270 242,256" fill="#ffffff" opacity="0.95"/>
</svg>
"""


def create_svg_wordmark() -> str:
    """Returns SVG XML for the Sumeragi Native+ logo with wordmark and tagline."""
    return """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 280" width="1000" height="280">
  <defs>
    <linearGradient id="goldText" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="#f3d88b"/>
      <stop offset="60%" stop-color="#c9a24a"/>
      <stop offset="100%" stop-color="#af8930"/>
    </linearGradient>
    <linearGradient id="crimsonPlus" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#e74c3c"/>
      <stop offset="100%" stop-color="#962d22"/>
    </linearGradient>
  </defs>

  <!-- Left Icon Emblem (scaled and translated) -->
  <g transform="translate(30, 20) scale(0.47)">
    <polygon points="256,24 456,140 456,372 256,488 56,372 56,140"
             fill="none" stroke="#c9a24a" stroke-width="12" stroke-linejoin="round"/>
    <!-- Top -->
    <polygon points="256,76 336,196 256,236 176,196" fill="#c9a24a"/>
    <polygon points="256,96 316,190 256,220 196,190" fill="#eadfcb"/>
    <!-- Bottom -->
    <polygon points="256,436 336,316 256,276 176,316" fill="#c9a24a"/>
    <polygon points="256,416 316,322 256,292 196,322" fill="#eadfcb"/>
    <!-- Left -->
    <polygon points="76,256 196,176 236,256 196,336" fill="#c9a24a"/>
    <polygon points="96,256 190,196 220,256 190,316" fill="#eadfcb"/>
    <!-- Right -->
    <polygon points="436,256 316,176 276,256 316,336" fill="#c9a24a"/>
    <polygon points="416,256 322,196 292,256 322,316" fill="#eadfcb"/>
    <!-- Center Plus -->
    <rect x="238" y="214" width="36" height="84" rx="4" fill="#a93226" stroke="#f3d88b" stroke-width="3"/>
    <rect x="214" y="238" width="84" height="36" rx="4" fill="#a93226" stroke="#f3d88b" stroke-width="3"/>
    <polygon points="256,244 268,256 256,268 244,256" fill="#ffffff"/>
  </g>

  <!-- Typography: SUMERAGI NATIVE + -->
  <text x="310" y="125" font-family="'Segoe UI', 'Cinzel', 'Trajan Pro', 'Georgia', serif" font-size="64" font-weight="bold" fill="url(#goldText)" letter-spacing="3">SUMERAGI</text>
  <text x="680" y="125" font-family="'Segoe UI', 'Inter', 'Helvetica Neue', sans-serif" font-size="52" font-weight="300" fill="#eadfcb" letter-spacing="4">NATIVE</text>
  <text x="895" y="125" font-family="'Segoe UI', sans-serif" font-size="68" font-weight="900" fill="url(#crimsonPlus)">+</text>

  <!-- Divider Line -->
  <line x1="310" y1="155" x2="940" y2="155" stroke="#c9a24a" stroke-width="2" opacity="0.6"/>

  <!-- Tagline -->
  <text x="312" y="195" font-family="'Segoe UI', 'Inter', sans-serif" font-size="24" font-weight="400" fill="#a49a8b" letter-spacing="2">The Sumeragi experience, evolved.</text>
  <text x="312" y="235" font-family="'Segoe UI', sans-serif" font-size="16" font-weight="400" fill="#6a6358">High-Performance Open-Source Native PS4 PC Runtime Environment</text>
</svg>
"""


def render_master_icon(dim: int = 2048) -> Image.Image:
    """Renders high-quality master raster emblem using Pillow with anti-aliasing."""
    img = Image.new("RGBA", (dim, dim), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    cx, cy = dim / 2, dim / 2
    r_outer = dim * 0.40

    # 1. Hexagonal Crest Outline
    import math
    hex_pts = []
    for i in range(6):
        angle = math.radians(60 * i - 30)
        px = cx + r_outer * math.cos(angle)
        py = cy + r_outer * math.sin(angle)
        hex_pts.append((px, py))

    # Outer gold hexagon
    draw.polygon(hex_pts, outline=(201, 162, 74, 245), width=int(dim * 0.024))

    # Inner dark accent hexagon
    r_inner_hex = r_outer * 0.94
    hex_inner_pts = []
    for i in range(6):
        angle = math.radians(60 * i - 30)
        px = cx + r_inner_hex * math.cos(angle)
        py = cy + r_inner_hex * math.sin(angle)
        hex_inner_pts.append((px, py))
    draw.polygon(hex_inner_pts, outline=(37, 33, 27, 220), width=int(dim * 0.008))

    # Corner accent dots
    dot_r = dim * 0.016
    for pt in hex_pts:
        draw.ellipse([pt[0] - dot_r, pt[1] - dot_r, pt[0] + dot_r, pt[1] + dot_r], fill=(243, 216, 139, 255))

    # 2. Four Diamond Lozenges (Hishi Mon Motif)
    d_lozenge = dim * 0.142
    w_h = dim * 0.088
    h_h = dim * 0.148

    def draw_diamond(center_x, center_y, is_vert):
        if is_vert:
            pts = [
                (center_x, center_y - h_h),
                (center_x + w_h, center_y),
                (center_x, center_y + h_h),
                (center_x - w_h, center_y),
            ]
            inner = [
                (center_x, center_y - h_h * 0.72),
                (center_x + w_h * 0.72, center_y),
                (center_x, center_y + h_h * 0.72),
                (center_x - w_h * 0.72, center_y),
            ]
        else:
            pts = [
                (center_x - h_h, center_y),
                (center_x, center_y - w_h),
                (center_x + h_h, center_y),
                (center_x, center_y + w_h),
            ]
            inner = [
                (center_x - h_h * 0.72, center_y),
                (center_x, center_y - w_h * 0.72),
                (center_x + h_h * 0.72, center_y),
                (center_x, center_y + w_h * 0.72),
            ]
        # Outer Gold
        draw.polygon(pts, fill=(201, 162, 74, 255), outline=(18, 16, 14, 255), width=int(dim * 0.007))
        # Inner Ivory
        draw.polygon(inner, fill=(234, 223, 203, 240))

    # Top
    draw_diamond(cx, cy - d_lozenge, True)
    # Bottom
    draw_diamond(cx, cy + d_lozenge, True)
    # Left
    draw_diamond(cx - d_lozenge, cy, False)
    # Right
    draw_diamond(cx + d_lozenge, cy, False)

    # 3. Central Red "+" Emblem (Native Plus)
    cross_arm = dim * 0.036
    cross_len = dim * 0.092
    # Vertical arm
    draw.rounded_rectangle(
        [cx - cross_arm, cy - cross_len, cx + cross_arm, cy + cross_len],
        radius=int(dim * 0.008),
        fill=(169, 50, 38, 255),
        outline=(243, 216, 139, 255),
        width=int(dim * 0.006),
    )
    # Horizontal arm
    draw.rounded_rectangle(
        [cx - cross_len, cy - cross_arm, cx + cross_len, cy + cross_arm],
        radius=int(dim * 0.008),
        fill=(169, 50, 38, 255),
        outline=(243, 216, 139, 255),
        width=int(dim * 0.006),
    )

    # Center white highlight
    center_d = dim * 0.016
    draw.polygon(
        [(cx, cy - center_d), (cx + center_d, cy), (cx, cy + center_d), (cx - center_d, cy)],
        fill=(255, 255, 255, 240)
    )

    return img


def main():
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    LAUNCHER_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Save SVG files
    icon_svg = ASSETS_DIR / "sumeragi_icon.svg"
    icon_svg.write_text(create_svg_icon(), encoding="utf-8")
    print(f"Generated: {icon_svg}")

    logo_svg = ASSETS_DIR / "sumeragi_logo.svg"
    logo_svg.write_text(create_svg_wordmark(), encoding="utf-8")
    print(f"Generated: {logo_svg}")

    # 2. Render high-resolution master
    master = render_master_icon(2048)

    # 3. Save master PNG (512x512)
    master_png = LAUNCHER_DIR / "sumeragi.png"
    img_512 = master.resize((512, 512), Image.Resampling.LANCZOS)
    img_512.save(master_png, format="PNG")
    print(f"Generated: {master_png}")

    # 4. Render Windows multi-resolution .ico from the exact same master
    ico_frames = []
    for s in SIZES:
        frame = master.resize((s, s), Image.Resampling.LANCZOS)
        if s <= 24:
            frame = frame.filter(ImageFilter.UnsharpMask(radius=1, percent=120, threshold=0))
        ico_frames.append(frame)

    sumeragi_ico = LAUNCHER_DIR / "sumeragi.ico"
    ico_frames[-1].save(
        sumeragi_ico,
        format="ICO",
        sizes=[(s, s) for s in SIZES],
        append_images=ico_frames[:-1]
    )
    print(f"Generated: {sumeragi_ico} (Sizes: {SIZES})")


if __name__ == "__main__":
    main()
