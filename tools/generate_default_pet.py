# =====================================================
# 🐾 酒館桌寵 — 預設寵物「小綠」精靈圖產生器
#
# 以程式繪製像素風小史萊姆，輸出 Codex pet 相容圖集：
#   1536x1872、8 欄 x 9 列、每格 192x208、透明背景
# 列定義與逐格時長依 openai/skills hatch-pet 的
# references/animation-rows.md 規格。
#
# 用法：
#   python tools/generate_default_pet.py            # 輸出圖集
#   python tools/generate_default_pet.py --qa DIR   # 加產 QA 圖（濾鏡條/GIF）
# =====================================================

import argparse
import math
import os
import sys

from PIL import Image

# Windows 主控台預設 cp950，印 emoji/中文會炸
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

# ── 幾何常數 ──
GW, GH = 24, 26          # 低解析度繪圖格
SCALE = 8                # 放大倍率 → 192x208
CELL_W, CELL_H = GW * SCALE, GH * SCALE
COLS, ROWS = 8, 9

# ── 調色盤 ──
C_FILL = (126, 207, 114, 255)      # 主體綠
C_SHADE = (100, 176, 92, 255)      # 底部陰影綠
C_OUTLINE = (54, 105, 62, 255)     # 外框深綠
C_HILITE = (204, 240, 190, 255)    # 頂部高光
C_EYE = (42, 52, 47, 255)          # 眼睛
C_GLINT = (245, 252, 245, 255)     # 眼神光
C_BLUSH = (255, 166, 150, 200)     # 腮紅
C_MOUTH = (54, 105, 62, 255)       # 嘴
C_TEAR = (122, 192, 240, 255)      # 眼淚 / 汗滴
C_TONGUE = (235, 130, 120, 255)    # 張嘴內色


class Grid:
    """24x26 像素畫布，最後最近鄰放大 8 倍。"""

    def __init__(self):
        self.cells = {}

    def put(self, x, y, c):
        if 0 <= x < GW and 0 <= y < GH:
            self.cells[(int(x), int(y))] = c

    def to_image(self):
        img = Image.new('RGBA', (GW, GH), (0, 0, 0, 0))
        for (x, y), c in self.cells.items():
            img.putpixel((x, y), c)
        return img.resize((CELL_W, CELL_H), Image.NEAREST)


def body_profile(u, rx):
    """史萊姆縱向半寬曲線：頂部圓潤、腰腹最寬、底部微收。u=0 頂 → 1 底。"""
    peak = 0.68  # 最寬處
    if u <= peak:
        t = (peak - u) / peak
        hw = rx * (1 - t ** 2.2) ** 0.42
    else:
        t = (u - peak) / (1 - peak)
        hw = rx * (1 - 0.18 * t ** 2)
    return max(hw, 0.0)


def body_mask(cx, bottom, rx, height, lean=0.0):
    """回傳身體像素集合。lean>0 頂部向右傾（底部錨定）。"""
    cells = set()
    top = bottom - height
    for y in range(int(math.floor(top)), int(bottom) + 1):
        u = (y - top) / height
        u = min(max(u, 0.0), 1.0)
        hw = body_profile(u, rx)
        if hw < 0.4:
            hw = 0.6 if u > 0.02 else hw
        shift = lean * (0.35 + 0.65 * (1 - u))
        x0 = int(round(cx + shift - hw))
        x1 = int(round(cx + shift + hw))
        for x in range(x0, x1 + 1):
            if 0 <= x < GW and 0 <= y < GH:
                cells.add((x, y))
    return cells


def arm_cells(side, pose, cx, bottom, rx, height, lean=0.0):
    """手臂小肉球。side: -1 左 / +1 右。全部緊貼身體輪廓（不脫離剪影）。"""
    u = 0.52
    top = bottom - height
    ay = int(round(top + u * height))
    shift = lean * (0.35 + 0.65 * (1 - u))
    ax = int(round(cx + shift + side * (body_profile(u, rx))))
    s = side
    poses = {
        'down':  [(ax + s, ay + 1), (ax + s, ay + 2)],
        'mid':   [(ax + s, ay), (ax + 2 * s, ay), (ax + s, ay + 1), (ax + 2 * s, ay + 1)],
        'up':    [(ax + s, ay - 1), (ax + s, ay - 2), (ax + 2 * s, ay - 2), (ax + 2 * s, ay - 3)],
        'up2':   [(ax + s, ay - 1), (ax + s, ay - 2), (ax + s, ay - 3), (ax + 2 * s, ay - 4)],
        'plead': [(ax + s, ay - 1), (ax + s, ay), (ax + 2 * s, ay - 1)],
        'chin':  [(ax + s, ay - 1), (ax + s, ay - 2), (ax + 2 * s, ay - 2)],
        'none':  [],
    }
    return set(poses[pose])


def feet_cells(cx, bottom, rx, phase=0):
    """腳丫：兩顆小肉球。phase 讓左右腳交互前後（走路用）。"""
    fy = bottom + 1
    off = [(0, 0), (1, -1), (0, 0), (-1, 1)][phase % 4]
    lx = int(round(cx - rx * 0.45)) + off[0]
    rx_ = int(round(cx + rx * 0.45)) + off[1]
    cells = set()
    for fx in (lx, rx_):
        cells.add((fx, fy))
        cells.add((fx + 1, fy))
    return cells


def draw_eye(g, ex, ey, style, look=(0, 0)):
    lx, ly = look
    x, y = ex + lx, ey + ly
    if style == 'open':
        for dy in range(3):
            g.put(x, y + dy, C_EYE)
            g.put(x + 1, y + dy, C_EYE)
        g.put(x, y, C_GLINT)
    elif style == 'closed':
        g.put(x, y + 1, C_EYE)
        g.put(x + 1, y + 1, C_EYE)
    elif style == 'happy':      # ^ 彎彎笑眼
        g.put(x, y + 1, C_EYE)
        g.put(x + 1, y, C_EYE)
        g.put(x + 2, y + 1, C_EYE)
    elif style == 'sad':        # 外側下垂
        g.put(x, y, C_EYE)
        g.put(x + 1, y + 1, C_EYE)
        g.put(x, y + 1, C_EYE)
        g.put(x + 1, y + 2, C_EYE)
    elif style == 'focus':      # 半瞇專注
        g.put(x, y + 1, C_EYE)
        g.put(x + 1, y + 1, C_EYE)
        g.put(x, y + 2, C_EYE)
        g.put(x + 1, y + 2, C_EYE)
    elif style == 'wide':       # 圓亮大眼
        for dy in range(3):
            for dx in range(3):
                g.put(x - 1 + dx, y + dy, C_EYE)
        g.put(x, y + 1, C_GLINT)


def draw_mouth(g, mx, my, style):
    if style == 'smile':
        g.put(mx - 1, my, C_MOUTH)
        g.put(mx, my, C_MOUTH)
        g.put(mx - 2, my - 1, C_MOUTH)
        g.put(mx + 1, my - 1, C_MOUTH)
    elif style == 'open':
        for dx in (-1, 0, 1):
            g.put(mx + dx, my, C_MOUTH)
        g.put(mx - 1, my + 1, C_MOUTH)
        g.put(mx, my + 1, C_TONGUE)
        g.put(mx + 1, my + 1, C_MOUTH)
    elif style == 'o':
        g.put(mx, my, C_MOUTH)
        g.put(mx + 1, my, C_MOUTH)
        g.put(mx, my + 1, C_MOUTH)
        g.put(mx + 1, my + 1, C_MOUTH)
    elif style == 'flat':
        for dx in (-1, 0, 1):
            g.put(mx + dx, my, C_MOUTH)
    elif style == 'wavy':
        g.put(mx - 2, my, C_MOUTH)
        g.put(mx - 1, my + 1, C_MOUTH)
        g.put(mx, my, C_MOUTH)
        g.put(mx + 1, my + 1, C_MOUTH)


def render_frame(
    bottom=22, rx=7.0, height=13.0, lean=0.0,
    eye='open', look=(0, 0), mouth='smile', blush=True,
    arm_l='down', arm_r='down', feet=True, foot_phase=0,
    tear=0, sweat=False,
):
    """組合一格：身體遮罩 → 外框/填色/陰影/高光 → 臉 → 附著特效。"""
    g = Grid()
    cx = GW // 2

    body = body_mask(cx, bottom, rx, height, lean)
    parts = set(body)
    parts |= arm_cells(-1, arm_l, cx, bottom, rx, height, lean)
    parts |= arm_cells(+1, arm_r, cx, bottom, rx, height, lean)
    if feet:
        parts |= feet_cells(cx, bottom, rx, foot_phase)

    # 外框：貼著剪影外圍一圈
    outline = set()
    for (x, y) in parts:
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            n = (x + dx, y + dy)
            if n not in parts:
                outline.add(n)

    for (x, y) in outline:
        g.put(x, y, C_OUTLINE)

    max_y = max(y for (_, y) in parts)
    for (x, y) in parts:
        if y >= max_y - 1:
            g.put(x, y, C_SHADE)
        else:
            g.put(x, y, C_FILL)

    # 高光：頂部偏左小弧
    top = bottom - height
    shift_top = lean * 0.9
    for (hx, hy) in ((-3, 1), (-2, 1), (-4, 2), (-3, 2)):
        px, py = int(round(cx + shift_top + hx)), int(round(top + hy))
        if (px, py) in body:
            g.put(px, py, C_HILITE)

    # 臉部
    eye_y = int(round(top + height * 0.34))
    face_shift = int(round(lean * 0.6))
    lx_eye = cx - 3 + face_shift
    rx_eye = cx + 2 + face_shift
    draw_eye(g, lx_eye, eye_y, eye, look)
    draw_eye(g, rx_eye, eye_y, eye, look)
    mouth_y = eye_y + 4
    draw_mouth(g, cx + face_shift, mouth_y, mouth)
    if blush:
        g.put(lx_eye - 2, eye_y + 3, C_BLUSH)
        g.put(rx_eye + 3, eye_y + 3, C_BLUSH)

    # 附著特效（緊貼臉部/頭頂，不脫離剪影）
    if tear:
        tx = rx_eye + 2 + look[0]
        ty = eye_y + 2
        g.put(tx, ty, C_TEAR)
        if tear >= 2:
            g.put(tx, ty + 1, C_TEAR)
    if sweat:
        sx = int(round(cx + shift_top + 4))
        sy = int(round(top + 1))
        g.put(sx, sy, C_TEAR)
        g.put(sx, sy + 1, C_TEAR)

    return g.to_image()


# ── 各狀態逐格定義（依 animation-rows.md） ──

def frames_idle():
    """0 idle：呼吸起伏 + 眨眼，6 格。"""
    return [
        render_frame(),
        render_frame(height=13.4),
        render_frame(height=14.0, rx=6.8),
        render_frame(height=14.0, rx=6.8, eye='closed'),
        render_frame(height=13.4),
        render_frame(arm_l='down', arm_r='down'),
    ]


def frames_run_right():
    """1 running-right：面朝右的彈跳前進，8 格。"""
    f = []
    hop = [
        dict(height=12.0, rx=8.0, bottom=22, foot_phase=0),            # 蹲
        dict(height=15.0, rx=6.2, bottom=21, foot_phase=1),            # 蹬
        dict(height=14.2, rx=6.5, bottom=19, foot_phase=1, feet=True), # 升
        dict(height=13.5, rx=6.8, bottom=18, foot_phase=2),            # 頂
        dict(height=13.8, rx=6.8, bottom=20, foot_phase=3),            # 落
        dict(height=12.0, rx=8.0, bottom=22, foot_phase=2),            # 觸地
        dict(height=13.0, rx=7.2, bottom=22, foot_phase=3),            # 回彈
        dict(height=13.2, rx=7.0, bottom=22, foot_phase=0),            # 收
    ]
    for i, kw in enumerate(hop):
        f.append(render_frame(
            lean=1.6, look=(1, 0), eye='open',
            mouth='smile' if i not in (1, 2) else 'open',
            arm_l='mid', arm_r='down', **kw,
        ))
    return f


def frames_wave():
    """3 waving：舉手打招呼，4 格。"""
    return [
        render_frame(eye='happy', mouth='smile', arm_r='up'),
        render_frame(eye='happy', mouth='open', arm_r='up2', lean=-0.6),
        render_frame(eye='happy', mouth='open', arm_r='up', lean=0.6),
        render_frame(eye='happy', mouth='smile', arm_r='up2'),
    ]


def frames_jump():
    """4 jumping：蹲 → 蹬 → 頂點 → 下落 → 落地回穩，5 格。"""
    return [
        render_frame(height=11.0, rx=8.6, eye='open', mouth='o'),
        render_frame(height=16.0, rx=6.0, bottom=17, eye='open', mouth='open', arm_l='up', arm_r='up'),
        render_frame(height=14.0, rx=6.6, bottom=14, eye='happy', mouth='open', arm_l='up', arm_r='up'),
        render_frame(height=14.2, rx=6.8, bottom=18, eye='open', mouth='smile', arm_l='mid', arm_r='mid'),
        render_frame(height=12.2, rx=8.0, bottom=22, eye='happy', mouth='smile'),
    ]


def frames_failed():
    """5 failed：驚訝 → 消沉 → 掉淚 → 抽泣，8 格。"""
    return [
        render_frame(mouth='flat'),
        render_frame(eye='wide', mouth='o'),
        render_frame(height=12.6, eye='sad', mouth='flat'),
        render_frame(height=12.0, eye='sad', mouth='wavy', tear=1, arm_l='down', arm_r='down'),
        render_frame(height=11.8, eye='sad', mouth='wavy', tear=2),
        render_frame(height=11.4, rx=7.4, eye='sad', mouth='wavy', tear=2, blush=False),
        render_frame(height=12.0, rx=7.2, eye='closed', mouth='wavy', tear=2, blush=False),
        render_frame(height=11.8, rx=7.3, eye='sad', mouth='flat', tear=1, blush=False),
    ]


def frames_waiting():
    """6 waiting：眨著大眼期待輸入、左右輕晃，6 格。"""
    return [
        render_frame(eye='wide', look=(0, -1), mouth='o', arm_l='plead', arm_r='plead'),
        render_frame(eye='wide', look=(0, -1), mouth='o', arm_l='plead', arm_r='plead', lean=-0.8),
        render_frame(eye='closed', mouth='o', arm_l='plead', arm_r='plead', lean=-0.8),
        render_frame(eye='wide', look=(0, -1), mouth='o', arm_l='plead', arm_r='plead'),
        render_frame(eye='wide', look=(0, -1), mouth='o', arm_l='plead', arm_r='plead', lean=0.8),
        render_frame(eye='wide', look=(0, -1), mouth='smile', arm_l='plead', arm_r='plead'),
    ]


def frames_working():
    """7 running（工作中）：專注打字微震動 + 汗滴，6 格。非移動跑步。"""
    f = []
    for i in range(6):
        f.append(render_frame(
            eye='focus', mouth='flat', blush=False,
            lean=0.5 if i % 2 else -0.5,
            arm_l='mid' if i % 2 else 'down',
            arm_r='down' if i % 2 else 'mid',
            sweat=(i >= 3),
            height=13.0 + (0.3 if i % 2 else 0.0),
        ))
    return f


def frames_review():
    """8 review：托腮左右端詳，6 格。"""
    return [
        render_frame(eye='focus', look=(-1, 0), mouth='flat', arm_r='chin', lean=0.8),
        render_frame(eye='focus', look=(-1, 0), mouth='flat', arm_r='chin', lean=0.8, height=13.3),
        render_frame(eye='closed', mouth='flat', arm_r='chin', lean=0.8),
        render_frame(eye='focus', look=(1, 0), mouth='flat', arm_r='chin', lean=0.8),
        render_frame(eye='focus', look=(1, 0), mouth='flat', arm_r='chin', lean=0.8, height=13.3),
        render_frame(eye='wide', look=(0, 0), mouth='smile', arm_r='chin'),
    ]


# 逐格時長（ms），與 animation-rows.md 完全一致
DURATIONS = {
    'idle': [280, 110, 110, 140, 140, 320],
    'running-right': [120] * 7 + [220],
    'running-left': [120] * 7 + [220],
    'waving': [140, 140, 140, 280],
    'jumping': [140, 140, 140, 140, 280],
    'failed': [140] * 7 + [240],
    'waiting': [150] * 5 + [260],
    'running': [120] * 5 + [220],
    'review': [150] * 5 + [280],
}


def build_rows():
    right = frames_run_right()
    # running-left：逐格鏡像（保留時間順序，同 hatch-pet 的鏡像原則）
    left = [f.transpose(Image.FLIP_LEFT_RIGHT) for f in right]
    return [
        ('idle', frames_idle()),
        ('running-right', right),
        ('running-left', left),
        ('waving', frames_wave()),
        ('jumping', frames_jump()),
        ('failed', frames_failed()),
        ('waiting', frames_waiting()),
        ('running', frames_working()),
        ('review', frames_review()),
    ]


def compose_atlas(rows):
    atlas = Image.new('RGBA', (COLS * CELL_W, ROWS * CELL_H), (0, 0, 0, 0))
    for r, (name, frames) in enumerate(rows):
        assert len(frames) <= COLS, f'{name} 超過 {COLS} 格'
        assert len(frames) == len(DURATIONS[name]), f'{name} 格數與時長表不符'
        for c, frame in enumerate(frames):
            atlas.paste(frame, (c * CELL_W, r * CELL_H))
    return atlas


def write_qa(rows, qa_dir):
    os.makedirs(qa_dir, exist_ok=True)
    for name, frames in rows:
        strip = Image.new('RGBA', (len(frames) * (GW * 4 + 2), GH * 4), (30, 30, 30, 255))
        for i, f in enumerate(frames):
            small = f.resize((GW * 4, GH * 4), Image.NEAREST)
            strip.paste(small, (i * (GW * 4 + 2), 0), small)
        strip.save(os.path.join(qa_dir, f'strip-{name}.png'))
        gif_frames = [f.convert('RGBA') for f in frames]
        gif_frames[0].save(
            os.path.join(qa_dir, f'preview-{name}.gif'),
            save_all=True, append_images=gif_frames[1:],
            duration=DURATIONS[name], loop=0, disposal=2,
        )


def main():
    ap = argparse.ArgumentParser()
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ap.add_argument('--out', default=os.path.join(root, 'assets', 'pets', 'greenie', 'spritesheet.png'))
    ap.add_argument('--qa', default=None, help='QA 輸出資料夾（濾鏡條 PNG + 動畫 GIF）')
    args = ap.parse_args()

    rows = build_rows()
    atlas = compose_atlas(rows)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    atlas.save(args.out)
    print(f'✅ 圖集輸出：{args.out} ({atlas.width}x{atlas.height})')

    if args.qa:
        write_qa(rows, args.qa)
        print(f'✅ QA 輸出：{args.qa}')


if __name__ == '__main__':
    main()
