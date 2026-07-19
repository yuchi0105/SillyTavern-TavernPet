# 🎨 寵物圖片生成指南（丟給任何會生圖的 AI 用）

這份文件讓你請**任何圖片生成 AI**（GPT-4o、Gemini、Midjourney、NanoBanana…）
幫你畫一隻新桌寵。照著順序做，最後用一行指令自動組裝進擴充。

## 📋 流程總覽

1. **定裝照**：先生 1 張角色設計圖（之後每次都要附上這張，保持長相一致）
2. **動畫條**：逐一生成 8 張橫向動畫條（`running-left` 可跳過，會自動鏡像）
3. **存檔**：把圖存進本專案的 `rows/` 資料夾，照指定檔名命名
4. **組裝**：跑 `python tools/build_atlas_from_rows.py rows --id mypet --name 寵物名`
5. **檢查**：看輸出資料夾裡 `qa/contact-sheet.png` 與 `qa/preview-*.gif`
6. **上場**：把寵物 id 加進 `assets/pets/pets.json`，就會出現在
   酒館設定面板的「寵物」選單裡（或用「自訂圖集」直接填圖集網址）

---

## ⚠️ 每一張都必須遵守的規則（很重要，請連同 prompt 一起貼給 AI）

```text
GLOBAL RULES for every image in this task:
- Same character in every frame: identical design, colors, proportions, face and style.
- One horizontal row of frames, evenly spaced, left to right, none touching or overlapping.
- Flat solid magenta background (#FF00FF). Nothing else in the background.
- The whole body must be fully visible in every frame (nothing cropped).
- NO shadows, NO ground/floor, NO motion lines, NO speed lines, NO afterimages,
  NO floating particles/stars/sparkles, NO text, NO labels, NO frame numbers,
  NO grid lines, NO watermarks.
- Effects must physically touch the body (a tear on the cheek is OK,
  a falling teardrop in mid-air is NOT).
- Express motion only through pose, squash & stretch, and expression.
- Flat 2D game-sprite look with clean, crisp edges (any art style is fine:
  pixel, chibi, plush, vector...).
```

> 背景用洋紅色 (#FF00FF) 是為了自動去背。如果你的角色本身是粉紫色系，
> 改用亮綠色 (#00FF00) 也行——組裝腳本會自動偵測背景色。

---

## Step 0️⃣ 定裝照（存成 `rows/base.png`，只當參考、不進圖集）

把下面的 `<描述>` 換成你想要的角色，貼給 AI：

```text
Character design sheet: a cute mascot pet for a desktop widget.
<描述：例如 a round fluffy orange fox cub with big eyes and a tiny scarf>
Single centered full-body pose, front-facing, friendly expression.
Flat solid magenta background (#FF00FF). Flat 2D game-sprite style, clean edges.
No shadows, no text, no props unless part of the character design.
```

✅ 生出滿意的定裝照後，**之後每一張動畫條都要附上這張圖**，並在 prompt 開頭加：

```text
Use the attached image as the exact character reference.
Keep the same design, colors, proportions, face and art style.
```

---

## Step 1️⃣ ~ 8️⃣ 動畫條（每張 = 一個狀態）

> 每次：附上定裝照 + 貼「全域規則」+ 貼該狀態的 prompt。
> 生成後存到 `rows/<檔名>`。格數不對就請 AI 重生成（「exactly N frames」要強調）。

### 1. `rows/idle.png` — 待機（6 格）

```text
Sprite animation strip: EXACTLY 6 frames in one horizontal row.
Animation: "idle" — a calm, subtle breathing loop.
Gentle body rise and fall across frames; eyes blink (closed) on frame 4 only.
No walking, no waving, no big gestures. Keep it quiet and cute.
```

### 2. `rows/running-right.png` — 向右跑（8 格）

```text
Sprite animation strip: EXACTLY 8 frames in one horizontal row.
Animation: "running-right" — the character runs/hops facing RIGHT.
A full run cycle: crouch, push off, airborne, peak, falling, landing, recover.
Body leans right, limbs clearly alternate between frames so the gait reads.
Facing direction must be RIGHT in all 8 frames.
```

### 3. `rows/running-left.png` — 向左跑（8 格）｜🟡 可跳過

角色左右對稱就跳過（組裝時自動鏡像）。不對稱（例如單邊配件）才需要生成：

```text
Sprite animation strip: EXACTLY 8 frames in one horizontal row.
Animation: "running-left" — same run cycle as running-right but facing LEFT
and traveling LEFT in all 8 frames.
```

### 4. `rows/waving.png` — 揮手（4 格）

```text
Sprite animation strip: EXACTLY 4 frames in one horizontal row.
Animation: "waving" — a friendly greeting.
One arm/paw raises and waves side to side across the frames; happy face.
The wave is shown ONLY through the limb pose (no motion arcs or lines).
```

### 5. `rows/jumping.png` — 跳躍（5 格）

```text
Sprite animation strip: EXACTLY 5 frames in one horizontal row.
Animation: "jumping" — one happy jump, shown only through body position:
frame 1 crouch (squashed), frame 2 launch (stretched, higher in the frame),
frame 3 peak (highest, joyful), frame 4 descending, frame 5 landed and settled.
No dust, no impact marks, no shadows.
```

### 6. `rows/failed.png` — 失落（8 格）

```text
Sprite animation strip: EXACTLY 8 frames in one horizontal row.
Animation: "failed" — something went wrong and the character is sad.
Progression: normal → startled wide eyes → drooping → teary sad eyes with a
tear ON the cheek → deflated slump → small sniffle bob → settled sad pose.
Tears must touch the face. No red X marks, no floating symbols, no rain of tears.
```

### 7. `rows/waiting.png` — 期待輸入（6 格）

```text
Sprite animation strip: EXACTLY 6 frames in one horizontal row.
Animation: "waiting" — expectantly asking the user for input.
Big hopeful eyes looking up/at the viewer, pleading paws-together pose,
gentle sway left and right across frames, one blink frame.
Clearly different from idle: this is an eager "please?" pose.
```

### 8. `rows/running.png` — 工作中（6 格）⚠️ 不是跑步！

```text
Sprite animation strip: EXACTLY 6 frames in one horizontal row.
Animation: "working" — the character is busy processing a task in place.
Focused half-lidded eyes, leaning into the work, tiny busy vibrating motion,
paws making small typing-like movements; a sweat drop ON the head in later frames.
ABSOLUTELY NO jogging, foot-running, or directional travel — it works in place.
```

### 9. `rows/review.png` — 端詳（6 格）

```text
Sprite animation strip: EXACTLY 6 frames in one horizontal row.
Animation: "review" — carefully inspecting something.
Leaning forward, squinting focused eyes, slow head tilt looking left then right,
one paw raised to the chin, final frame a bright wide-eyed "aha" look.
No magnifying glass, no papers, no new props.
```

---

## 🛠️ 組裝與檢查

```bash
# 在專案根目錄執行（需要 Python + Pillow：pip install pillow）
python tools/build_atlas_from_rows.py rows --id mypet --name 寵物名
```

腳本會自動：去背 → 切格（偵測不到就平均切）→ 整列統一縮放（不會忽大忽小）→
底部對齊 → 組成 1536×1872 圖集 → 產出 QA 檢查圖。

| 問題 | 解法 |
|------|------|
| 背景沒去乾淨 / 有色邊 | `--tolerance 80`（調大）、jpg 毛邊加 `--erode 1` |
| 「第 X 格是空的」 | 看 `qa/split-*.png`，通常是 AI 沒畫滿格數，重生成那條 |
| 某格切到隔壁的手腳 | 請 AI 重生成，強調 frames never touching |
| 動作方向錯（如 running 變慢跑） | 把該狀態 prompt 的大寫警告再貼一次重生成 |

檢查 `qa/contact-sheet.png`（全列總覽）和 `qa/preview-*.gif`（動起來的樣子），
滿意後把寵物 id 加進 `assets/pets/pets.json`，即可在酒館設定面板的
「寵物」選單選用（或用「自訂圖集」直接貼圖集網址）。

## 📐 附錄：圖集規格（給想手動做圖的人）

- PNG/WebP、`1536x1872`、透明背景、8 欄 × 9 列、每格 `192x208`
- 列順序：`idle(6)`、`running-right(8)`、`running-left(8)`、`waving(4)`、
  `jumping(5)`、`failed(8)`、`waiting(6)`、`running(6)`、`review(6)`
- 未使用的格必須完全透明；與 openai/skills 的 hatch-pet（Codex pet）完全相容
