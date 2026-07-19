# 把 AI 生成的動畫條放這裡

照 [AI_ART_GUIDE.md](../AI_ART_GUIDE.md) 的 prompt 生成後，存成以下檔名（png/webp/jpg 皆可）：

```
base.png            定裝照（參考用，不進圖集）
idle.png            待機 6 格
running-right.png   向右跑 8 格
running-left.png    向左跑 8 格（可省略 → 自動鏡像）
waving.png          揮手 4 格
jumping.png         跳躍 5 格
failed.png          失落 8 格
waiting.png         期待輸入 6 格
running.png         工作中 6 格（不是跑步！）
review.png          端詳 6 格
```

然後在專案根目錄執行：

```bash
python tools/build_atlas_from_rows.py rows --id mypet --name 寵物名
```
