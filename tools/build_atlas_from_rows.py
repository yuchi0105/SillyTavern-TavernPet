# =====================================================
# 🐾 酒館桌寵 — 動畫條組裝器
#
# 把「其他 AI 生成的 9 張橫向動畫條」自動處理成標準精靈圖：
#   去背（純色背景 → 透明）→ 切格 → 統一縮放對齊 → 組圖集 → 驗證
#
# 輸入：一個資料夾，內含以狀態命名的圖片（png/webp/jpg）：
#   idle / running-right / running-left(可省略，會自動鏡像)
#   waving / jumping / failed / waiting / running / review
#
# 輸出：Codex pet 相容圖集 1536x1872（8欄x9列、每格192x208）
#   外加 qa/ 檢查圖（contact sheet、切格示意、逐列 GIF）
#
# 用法：
#   python tools/build_atlas_from_rows.py rows --out assets/pets/mypet --name 小藍
#   python tools/build_atlas_from_rows.py rows --tolerance 80 --erode 1   # 去背調整
# =====================================================

import argparse
import os
import sys

from PIL import Image, ImageChops, ImageDraw, ImageFilter

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

CELL_W, CELL_H = 192, 208
COLS, ROWS = 8, 9
PAD_X = 6        # 每格左右安全邊
PAD_TOP = 6      # 頂部安全邊
BASELINE = 12    # 腳底距格底

# 列順序與格數（Codex pet contract / hatch-pet animation-rows.md）
STATES = [
    ('idle', 6),
    ('running-right', 8),
    ('running-left', 8),
    ('waving', 4),
    ('jumping', 5),
    ('failed', 8),
    ('waiting', 6),
    ('running', 6),
    ('review', 6),
]

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

EXTS = ('.png', '.webp', '.jpg', '.jpeg')


def find_row_file(rows_dir, state):
    """尋找該狀態的圖檔：不分大小寫、容許底線代替連字號。"""
    want = state.replace('-', '_')
    for fn in sorted(os.listdir(rows_dir)):
        base, ext = os.path.splitext(fn)
        if ext.lower() not in EXTS:
            continue
        norm = base.lower().replace('-', '_')
        if norm == want or norm == state.lower():
            return os.path.join(rows_dir, fn)
    return None


def detect_background(img):
    """取四角小塊的眾數顏色當背景色；若圖片本身已有透明背景則回傳 None。"""
    alpha = img.getchannel('A')
    hist = alpha.histogram()
    transparent_ratio = sum(hist[:16]) / (img.width * img.height)
    if transparent_ratio > 0.05:
        return None  # 已去背
    n = max(4, min(12, img.width // 40))
    counts = {}
    for cx, cy in ((0, 0), (img.width - n, 0), (0, img.height - n), (img.width - n, img.height - n)):
        raw = img.crop((cx, cy, cx + n, cy + n)).convert('RGB').tobytes()
        for i in range(0, len(raw), 3):
            px = (raw[i], raw[i + 1], raw[i + 2])
            counts[px] = counts.get(px, 0) + 1
    return max(counts, key=counts.get)


def key_out_background(img, bg, tolerance, erode):
    """把接近背景色的像素變透明。以各通道最大差值當距離。"""
    rgb = img.convert('RGB')
    solid = Image.new('RGB', img.size, bg)
    diff = ImageChops.difference(rgb, solid)
    r, g, b = diff.split()
    dist = ImageChops.lighter(ImageChops.lighter(r, g), b)
    mask = dist.point(lambda v: 255 if v > tolerance else 0)
    mask = mask.filter(ImageFilter.MedianFilter(3))   # 去除孤立噪點
    for _ in range(max(0, erode)):
        mask = mask.filter(ImageFilter.MinFilter(3))  # 收縮 1px，吃掉背景色毛邊
    out = img.copy()
    out.putalpha(mask)
    return out


def column_runs(alpha, min_px=3):
    """找出「有內容的欄位連續區段」。回傳 [(x0, x1), ...]（含端點）。"""
    w, h = alpha.size
    data = alpha.tobytes()
    occupied = []
    for x in range(w):
        cnt = 0
        for y in range(h):
            if data[y * w + x] > 8:
                cnt += 1
                if cnt >= min_px:
                    break
        occupied.append(cnt >= min_px)
    runs = []
    start = None
    for x, occ in enumerate(occupied):
        if occ and start is None:
            start = x
        elif not occ and start is not None:
            runs.append((start, x - 1))
            start = None
    if start is not None:
        runs.append((start, w - 1))
    # 只合併極小間隙（抗鋸齒殘影）。橫向生圖常會把相鄰姿勢排得很近；
    # 先前使用寬度的 0.8% 會在 2K 圖上把約 17px 的合法格間距誤合併。
    merge_gap = max(2, round(w * 0.002))
    merged = []
    for run in runs:
        if merged and run[0] - merged[-1][1] <= merge_gap:
            merged[-1] = (merged[-1][0], run[1])
        else:
            merged.append(list(run))
    return [tuple(r) for r in merged]


def trim_bbox(frame, noise=2):
    """依 alpha 投影修出緊貼的 bbox，忽略每行/列少於 noise 像素的雜訊。"""
    alpha = frame.getchannel('A')
    w, h = alpha.size
    data = alpha.tobytes()
    col = [0] * w
    row = [0] * h
    for y in range(h):
        base = y * w
        for x in range(w):
            if data[base + x] > 8:
                col[x] += 1
                row[y] += 1
    xs = [x for x in range(w) if col[x] > noise]
    ys = [y for y in range(h) if row[y] > noise]
    if not xs or not ys:
        return None
    return (min(xs), min(ys), max(xs) + 1, max(ys) + 1)


def split_row(img, n, state, qa_dir):
    """把一條橫向動畫條切成 n 格。優先用內容區段偵測，數量不符時平均切。"""
    alpha = img.getchannel('A')
    runs = column_runs(alpha)
    mode = 'auto'
    if len(runs) == n:
        bounds = [(max(0, x0 - 1), min(img.width, x1 + 2)) for x0, x1 in runs]
    else:
        mode = f'even（偵測到 {len(runs)} 段 ≠ {n} 格）'
        step = img.width / n
        bounds = [(round(i * step), round((i + 1) * step)) for i in range(n)]

    # 切格示意圖（除錯用）
    if qa_dir:
        dbg = img.convert('RGB').copy()
        d = ImageDraw.Draw(dbg)
        for x0, x1 in bounds:
            d.rectangle([x0, 0, x1 - 1, img.height - 1], outline=(255, 0, 0), width=2)
        dbg.save(os.path.join(qa_dir, f'split-{state}.png'))

    frames = []
    bottoms = []
    for i, (x0, x1) in enumerate(bounds):
        seg = img.crop((x0, 0, x1, img.height))
        box = trim_bbox(seg)
        if box is None:
            raise SystemExit(
                f'❌ {state} 第 {i + 1} 格是空的（共需 {n} 格，切法：{mode}）。\n'
                f'   請檢查 qa/split-{state}.png，通常是 AI 沒畫滿 {n} 格，重新生成該條即可。')
        frames.append(seg.crop(box))
        bottoms.append(box[3])  # 內容底部在原條中的 y（各格同座標系，可比較）
    return frames, bottoms, mode


# 這些狀態的「垂直位移」是動畫語意的一部分（跳躍弧線），要保留原條中的高度差；
# 其他列一律貼齊基準線，順便吸收 AI 畫圖時的底線抖動。
PRESERVE_Y_STATES = {'jumping'}


def fit_frames_to_cells(frames, bottoms, preserve_y):
    """整列共用同一縮放比（避免格與格之間大小跳動），底部對齊基準線。
    preserve_y 時按原條的底部落差抬升各格（跳躍的空中格）。"""
    max_w = max(f.width for f in frames)
    max_h = max(f.height for f in frames)
    ground = max(bottoms)
    lifts = [ground - b for b in bottoms] if preserve_y else [0] * len(frames)
    scale = min(
        (CELL_W - 2 * PAD_X) / max_w,
        (CELL_H - PAD_TOP - BASELINE) / max(1, max(f.height + lift for f, lift in zip(frames, lifts))),
        3.0,
    )
    cells = []
    for f, lift in zip(frames, lifts):
        w = max(1, round(f.width * scale))
        h = max(1, round(f.height * scale))
        resized = f.resize((w, h), Image.LANCZOS)
        cell = Image.new('RGBA', (CELL_W, CELL_H), (0, 0, 0, 0))
        y = max(PAD_TOP, CELL_H - BASELINE - h - round(lift * scale))
        cell.paste(resized, ((CELL_W - w) // 2, y), resized)
        cells.append(cell)
    return cells


def make_contact_sheet(atlas, path):
    scale = 0.5
    label_h = 18
    sw = int(atlas.width * scale)
    ch = int(CELL_H * scale)
    sheet = Image.new('RGB', (sw, (ch + label_h) * ROWS), (24, 24, 24))
    d = ImageDraw.Draw(sheet)
    for r, (state, n) in enumerate(STATES):
        y = r * (ch + label_h)
        d.text((4, y + 3), f'row {r}: {state} ({n} frames)', fill=(220, 220, 220))
        row_img = atlas.crop((0, r * CELL_H, atlas.width, (r + 1) * CELL_H)) \
                       .resize((sw, ch), Image.LANCZOS)
        # 棋盤格底，透明處看得出來
        for bx in range(0, sw, 16):
            for by in range(0, ch, 16):
                if (bx // 16 + by // 16) % 2 == 0:
                    d.rectangle([bx, y + label_h + by, bx + 15, y + label_h + by + 15], fill=(40, 40, 40))
        sheet.paste(row_img, (0, y + label_h), row_img)
    sheet.save(path)


def write_gifs(rows, qa_dir):
    for state, frames in rows.items():
        frames[0].save(
            os.path.join(qa_dir, f'preview-{state}.gif'),
            save_all=True, append_images=frames[1:],
            duration=DURATIONS[state], loop=0, disposal=2,
        )


def main():
    ap = argparse.ArgumentParser(description='把 AI 生成的動畫條組成 TavernPet 精靈圖')
    ap.add_argument('rows_dir', help='放動畫條圖片的資料夾')
    ap.add_argument('--out', default=None, help='輸出資料夾（預設 assets/pets/custom）')
    ap.add_argument('--id', dest='pet_id', default='custom', help='寵物 id（英文）')
    ap.add_argument('--name', default='自訂寵物', help='顯示名稱')
    ap.add_argument('--desc', default='由 AI 生成圖片組裝的桌寵。', help='一句話描述')
    ap.add_argument('--tolerance', type=int, default=60, help='去背容差 0-255（預設 60）')
    ap.add_argument('--erode', type=int, default=0, help='去背後收縮 N px（jpg 毛邊建議 1）')
    args = ap.parse_args()

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out_dir = args.out or os.path.join(root, 'assets', 'pets', args.pet_id)
    qa_dir = os.path.join(out_dir, 'qa')
    os.makedirs(qa_dir, exist_ok=True)

    processed = {}
    report = []

    for state, n in STATES:
        path = find_row_file(args.rows_dir, state)
        if path is None:
            if state == 'running-left':
                report.append(f'  {state:14s} 缺檔 → 之後由 running-right 鏡像')
                continue
            raise SystemExit(f'❌ 找不到 {state} 的圖（放在 {args.rows_dir}/{state}.png，格式 png/webp/jpg）')

        img = Image.open(path).convert('RGBA')
        bg = detect_background(img)
        if bg is not None:
            img = key_out_background(img, bg, args.tolerance, args.erode)
            bg_note = f'去背 {bg}'
        else:
            bg_note = '原生透明'
        frames, bottoms, mode = split_row(img, n, state, qa_dir)
        processed[state] = fit_frames_to_cells(frames, bottoms, state in PRESERVE_Y_STATES)
        report.append(f'  {state:14s} {n} 格｜{bg_note}｜切法 {mode}')

    if 'running-left' not in processed:
        processed['running-left'] = [
            f.transpose(Image.FLIP_LEFT_RIGHT) for f in processed['running-right']
        ]

    # 組圖集
    atlas = Image.new('RGBA', (COLS * CELL_W, ROWS * CELL_H), (0, 0, 0, 0))
    for r, (state, n) in enumerate(STATES):
        for c, cell in enumerate(processed[state]):
            atlas.paste(cell, (c * CELL_W, r * CELL_H))

    # 透明像素 RGB 歸零（Codex 規格：不得有隱藏色殘留）
    binmask = atlas.getchannel('A').point(lambda a: 255 if a > 0 else 0)
    atlas = Image.composite(atlas, Image.new('RGBA', atlas.size, (0, 0, 0, 0)), binmask)

    sheet_path = os.path.join(out_dir, 'spritesheet.png')
    atlas.save(sheet_path)

    import json
    with open(os.path.join(out_dir, 'pet.json'), 'w', encoding='utf-8') as f:
        json.dump({
            'id': args.pet_id,
            'displayName': args.name,
            'description': args.desc,
            'spritesheetPath': 'spritesheet.png',
        }, f, ensure_ascii=False, indent=4)

    make_contact_sheet(atlas, os.path.join(qa_dir, 'contact-sheet.png'))
    write_gifs(processed, qa_dir)

    print('各列處理結果：')
    print('\n'.join(report))
    print(f'\n✅ 圖集：{sheet_path} ({atlas.width}x{atlas.height})')
    print(f'✅ QA 檢查圖：{qa_dir}（先看 contact-sheet.png 和 preview-*.gif！）')
    print('\n下一步：')
    print(f'  1. 打開 {qa_dir}\\contact-sheet.png 確認每列動作正確、背景乾淨')
    print('  2. 去背有殘留 → 調 --tolerance（調大）或 --erode 1 重跑')
    print('  3. 滿意後，在酒館設定面板「自訂圖集」填入此 spritesheet 的網址，')
    print(f'     目前圖集位於 {sheet_path}；要設為預設寵物時，請讓 style.css 指向這個 pet id。')


if __name__ == '__main__':
    main()
