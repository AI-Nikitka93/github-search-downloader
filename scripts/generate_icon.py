from __future__ import annotations

import math
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter

ROOT_DIR = Path(__file__).resolve().parents[1]
ASSETS_DIR = ROOT_DIR / "assets"
ASSETS_DIR.mkdir(parents=True, exist_ok=True)

SIZE = 1024
CENTER = SIZE // 2
RADIUS = 460


def create_base_icon() -> Image.Image:
    # 1. Create transparent canvas
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))

    # 2. Draw background rounded squircle/circle with gradient
    mask = Image.new("L", (SIZE, SIZE), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.ellipse(
        [CENTER - RADIUS, CENTER - RADIUS, CENTER + RADIUS, CENTER + RADIUS],
        fill=255,
    )

    # Gradient background: Deep Navy to Cyber Dark Slate (#0a0f1d -> #0f1c2e)
    bg = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    for y in range(SIZE):
        factor = y / SIZE
        r = int(10 + factor * 8)
        g = int(18 + factor * 22)
        b = int(36 + factor * 30)
        line = Image.new("RGBA", (SIZE, 1), (r, g, b, 255))
        bg.paste(line, (0, y))

    img.paste(bg, (0, 0), mask)

    # 3. Outer glowing border
    overlay = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)

    # Border gradient arc (Emerald #10b981 to Cyan #06b6d4)
    border_width = 24
    overlay_draw.ellipse(
        [
            CENTER - RADIUS + border_width // 2,
            CENTER - RADIUS + border_width // 2,
            CENTER + RADIUS - border_width // 2,
            CENTER + RADIUS - border_width // 2,
        ],
        outline=(16, 185, 129, 230),
        width=border_width,
    )

    # 4. Radar concentric rings
    radar_radii = [110, 220, 330]
    for r_dist in radar_radii:
        overlay_draw.ellipse(
            [CENTER - r_dist, CENTER - r_dist, CENTER + r_dist, CENTER + r_dist],
            outline=(16, 185, 129, 70),
            width=6,
        )

    # Radar crosshair grid
    grid_color = (6, 182, 212, 60)
    overlay_draw.line([(CENTER - 400, CENTER), (CENTER + 400, CENTER)], fill=grid_color, width=4)
    overlay_draw.line([(CENTER, CENTER - 400), (CENTER, CENTER + 400)], fill=grid_color, width=4)
    # Diagonal ticks
    d_len = 280
    overlay_draw.line(
        [(CENTER - d_len, CENTER - d_len), (CENTER + d_len, CENTER + d_len)],
        fill=(16, 185, 129, 35),
        width=3,
    )
    overlay_draw.line(
        [(CENTER - d_len, CENTER + d_len), (CENTER + d_len, CENTER - d_len)],
        fill=(16, 185, 129, 35),
        width=3,
    )

    # 5. Radar sweep beam (sector gradient from 45 deg to 135 deg)
    sweep = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    sweep_draw = ImageDraw.Draw(sweep)
    sweep_start = 30
    sweep_end = 120
    for deg in range(sweep_start, sweep_end):
        alpha = int(140 * ((deg - sweep_start) / (sweep_end - sweep_start)) ** 1.8)
        sweep_draw.pieslice(
            [CENTER - 380, CENTER - 380, CENTER + 380, CENTER + 380],
            start=deg,
            end=deg + 2,
            fill=(16, 185, 129, alpha),
        )
    # Leading edge of the sweep line
    rad_edge = math.radians(sweep_end)
    edge_x = CENTER + int(380 * math.cos(rad_edge))
    edge_y = CENTER + int(380 * math.sin(rad_edge))
    sweep_draw.line([(CENTER, CENTER), (edge_x, edge_y)], fill=(56, 239, 125, 240), width=8)

    # Combine sweep
    img = Image.alpha_composite(img, sweep)
    img = Image.alpha_composite(img, overlay)

    # 6. Git graph telemetry topology (GitHub branching nodes)
    git_layer = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    git_draw = ImageDraw.Draw(git_layer)

    # Node positions
    node_main_1 = (CENTER - 160, CENTER + 180)
    node_main_2 = (CENTER - 160, CENTER - 40)
    node_main_3 = (CENTER - 160, CENTER - 220)
    node_branch_1 = (CENTER + 130, CENTER - 60)
    node_branch_2 = (CENTER + 130, CENTER + 130)

    # Draw trunk line
    git_draw.line([node_main_1, node_main_3], fill=(230, 241, 255, 200), width=14)

    # Draw branch arc curves (Bézier-like via line segments)
    points_b1 = []
    for step in range(30):
        t = step / 29.0
        p0 = node_main_2
        p1 = (CENTER, CENTER - 120)
        p2 = node_branch_1
        bx = (1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * p1[0] + t**2 * p2[0]
        by = (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * p1[1] + t**2 * p2[1]
        points_b1.append((bx, by))
    git_draw.line(points_b1, fill=(6, 182, 212, 220), width=12)

    points_b2 = []
    for step in range(30):
        t = step / 29.0
        p0 = node_main_1
        p1 = (CENTER - 20, CENTER + 180)
        p2 = node_branch_2
        bx = (1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * p1[0] + t**2 * p2[0]
        by = (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * p1[1] + t**2 * p2[1]
        points_b2.append((bx, by))
    git_draw.line(points_b2, fill=(16, 185, 129, 220), width=12)

    # Draw Git nodes (circles with glow)
    nodes = [
        (node_main_1, (16, 185, 129), 28),
        (node_main_2, (6, 182, 212), 32),
        (node_main_3, (56, 239, 125), 36),
        (node_branch_1, (59, 130, 246), 30),
        (node_branch_2, (16, 185, 129), 28),
    ]

    for (nx, ny), color, radius in nodes:
        # Outer glow
        git_draw.ellipse(
            [nx - radius - 12, ny - radius - 12, nx + radius + 12, ny + radius + 12],
            fill=(*color, 80),
        )
        # Main node body
        git_draw.ellipse(
            [nx - radius, ny - radius, nx + radius, ny + radius],
            fill=(*color, 255),
            outline=(255, 255, 255, 230),
            width=6,
        )
        # Inner dot
        inner_r = radius // 2.5
        git_draw.ellipse(
            [nx - inner_r, ny - inner_r, nx + inner_r, ny + inner_r],
            fill=(255, 255, 255, 255),
        )

    # 7. Search telemetry pulse target on top node (node_main_3)
    target_x, target_y = node_main_3
    for tr in [58, 82]:
        git_draw.ellipse(
            [target_x - tr, target_y - tr, target_x + tr, target_y + tr],
            outline=(56, 239, 125, 180),
            width=5,
        )
    t_tick = 20
    git_draw.line([(target_x - 95, target_y), (target_x - 95 + t_tick, target_y)], fill=(56, 239, 125, 220), width=5)
    git_draw.line([(target_x + 95 - t_tick, target_y), (target_x + 95, target_y)], fill=(56, 239, 125, 220), width=5)
    git_draw.line([(target_x, target_y - 95), (target_x, target_y - 95 + t_tick)], fill=(56, 239, 125, 220), width=5)
    git_draw.line([(target_x, target_y + 95 - t_tick), (target_x, target_y + 95)], fill=(56, 239, 125, 220), width=5)

    img = Image.alpha_composite(img, git_layer)

    return img


def generate_assets() -> None:
    high_res = create_base_icon()

    # Save 256x256 PNG
    png_256 = high_res.resize((256, 256), Image.Resampling.LANCZOS)
    png_path = ASSETS_DIR / "icon.png"
    png_256.save(png_path, format="PNG")
    print(f"Saved {png_path} ({png_path.stat().st_size} bytes)")

    # Generate multi-size ICO
    ico_sizes = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)]
    ico_images = [high_res.resize(size, Image.Resampling.LANCZOS) for size in ico_sizes]

    ico_path = ASSETS_DIR / "icon.ico"
    ico_images[0].save(
        ico_path,
        format="ICO",
        sizes=ico_sizes,
        append_images=ico_images[1:],
    )
    print(f"Saved {ico_path} ({ico_path.stat().st_size} bytes)")


if __name__ == "__main__":
    generate_assets()
