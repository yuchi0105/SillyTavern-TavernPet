// =====================================================
// 🐾 酒館桌寵 TavernPet — SillyTavern Extension
//
// 會在酒館畫面上養一隻可拖曳、會散步、會看氣氛做反應的
// 動畫小寵物。動畫採用 Codex pet 相容精靈圖（8 欄 x 9 列、
// 每格 192x208），可直接換裝任何 hatch-pet 產出的圖集。
//
// 定位/拖曳/夾限邏輯參考 SillyTavern-GreenGuaiGuai (MIT)。
// =====================================================

(async function () {
    const MODULE_NAME = 'tavern_pet';
    const extensionName = 'SillyTavern-TavernPet';

    // ── 圖集規格（Codex pet contract） ──
    const ATLAS = { cols: 8, rows: 9, cellW: 192, cellH: 208 };

    // 各狀態所在列與逐格時長（ms），依 hatch-pet animation-rows.md
    const STATES = {
        'idle':          { row: 0, durations: [280, 110, 110, 140, 140, 320] },
        'running-right': { row: 1, durations: [120, 120, 120, 120, 120, 120, 120, 220] },
        'running-left':  { row: 2, durations: [120, 120, 120, 120, 120, 120, 120, 220] },
        'waving':        { row: 3, durations: [140, 140, 140, 280] },
        'jumping':       { row: 4, durations: [140, 140, 140, 140, 280] },
        'failed':        { row: 5, durations: [140, 140, 140, 140, 140, 140, 140, 240] },
        'waiting':       { row: 6, durations: [150, 150, 150, 150, 150, 260] },
        'running':       { row: 7, durations: [120, 120, 120, 120, 120, 220] },
        'review':        { row: 8, durations: [150, 150, 150, 150, 150, 280] },
    };

    // ── 預設設定 ──
    const defaultSettings = {
        enabled: true,
        size: 96,           // 顯示寬度 px，高度依 192:208 比例換算
        opacity: 100,
        autoWalk: true,     // 自由活動（散步、東張西望）
        reactions: true,    // 酒館事件反應（生成中/回覆/中斷…）
        customAtlas: '',    // 自訂精靈圖 URL，留空 = 預設桃兔
        posX: null,
        posY: null,
    };

    let petEl = null;

    // 拖曳狀態
    let isDragging = false;
    let dragOffsetX = 0;
    let dragOffsetY = 0;
    let hasMoved = false;
    let dragStartX = 0;
    let dragStartY = 0;
    let dragLastX = 0;

    // 行為狀態
    let busy = false;          // 酒館正在生成回覆
    let walking = null;        // { targetX, lastT }
    let lastInteraction = 0;   // 最近一次使用者互動時間
    let lastGreet = 0;
    let petTimes = [];         // 連續摸頭偵測

    const reducedMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false;

    // ── 設定管理 ──
    function getSettings() {
        const context = SillyTavern.getContext();
        if (!context.extensionSettings[MODULE_NAME]) {
            context.extensionSettings[MODULE_NAME] = Object.assign({}, defaultSettings);
        }
        const settings = context.extensionSettings[MODULE_NAME];
        for (const key of Object.keys(defaultSettings)) {
            if (settings[key] === undefined) settings[key] = defaultSettings[key];
        }
        return settings;
    }

    function saveSettings() {
        SillyTavern.getContext().saveSettingsDebounced();
    }

    // ── 尺寸換算 ──
    function cellSize() {
        const settings = getSettings();
        const w = settings.size;
        const h = Math.round(settings.size * ATLAS.cellH / ATLAS.cellW);
        return { w, h };
    }

    // =====================================================
    // 動畫引擎：以 setTimeout 逐格推進 background-position
    // =====================================================
    let animState = 'idle';
    let animFrame = 0;
    let animTimer = null;
    let transient = null; // { loopsLeft }：播完 N 輪自動回到基底狀態

    function baseState() {
        if (busy) return 'running';
        return 'idle';
    }

    function applyFrame() {
        if (!petEl) return;
        const st = STATES[animState];
        const { w, h } = cellSize();
        petEl.style.backgroundPosition = `-${animFrame * w}px -${st.row * h}px`;
    }

    function scheduleNext() {
        clearTimeout(animTimer);
        if (reducedMotion) return; // 減少動態：停在各狀態第 0 格
        const st = STATES[animState];
        animTimer = setTimeout(() => {
            animFrame += 1;
            if (animFrame >= st.durations.length) {
                animFrame = 0;
                if (transient) {
                    transient.loopsLeft -= 1;
                    if (transient.loopsLeft <= 0) {
                        transient = null;
                        animState = walking ? animState : baseState();
                    }
                }
            }
            applyFrame();
            scheduleNext();
        }, st.durations[animFrame]);
    }

    /** 切換為持續狀態（idle / running / 走路方向） */
    function setAnim(name) {
        if (!STATES[name]) return;
        transient = null;
        animState = name;
        animFrame = 0;
        applyFrame();
        scheduleNext();
    }

    /** 插播一段動畫，播完 loops 輪自動回基底狀態 */
    function playOnce(name, loops = 1) {
        if (!STATES[name]) return;
        if (walking) stopWalk(false);
        if (reducedMotion) {
            // 減少動態：靜態顯示該狀態第 0 格一小段時間後歸位
            animState = name;
            animFrame = 0;
            applyFrame();
            clearTimeout(animTimer);
            animTimer = setTimeout(() => {
                animState = baseState();
                applyFrame();
            }, 1500);
            return;
        }
        transient = { loopsLeft: loops };
        animState = name;
        animFrame = 0;
        applyFrame();
        scheduleNext();
    }

    /** 回到基底狀態（生成中 → running，否則 idle） */
    function settle() {
        if (walking) return;
        transient = null;
        setAnim(baseState());
    }

    // =====================================================
    // 建立寵物元素
    // =====================================================
    function createPet() {
        if (petEl) return;

        petEl = document.createElement('div');
        petEl.id = 'tavernpet';
        petEl.title = '酒館桌寵 🐾\n點我互動、拖我散步！';

        document.body.appendChild(petEl);

        applySettings();
        requestAnimationFrame(clampIntoView);
        setAnim('idle');

        // 滑鼠拖曳
        petEl.addEventListener('mousedown', onMouseDown);
        document.addEventListener('mousemove', onMouseMove);
        document.addEventListener('mouseup', onMouseUp);

        // 觸控拖曳
        petEl.addEventListener('touchstart', onTouchStart, { passive: false });
        document.addEventListener('touchmove', onTouchMove, { passive: false });
        document.addEventListener('touchend', onTouchEnd);

        // 視口變化時夾回畫面內
        window.addEventListener('resize', scheduleClamp);
        window.addEventListener('orientationchange', scheduleClamp);

        // 自由活動排程
        setInterval(idleTick, 15000);

        // 開場打招呼
        setTimeout(() => playOnce('waving'), 1200);
    }

    // ── 套用設定到 DOM ──
    function applySettings() {
        if (!petEl) return;
        const settings = getSettings();
        const { w, h } = cellSize();
        petEl.style.width = `${w}px`;
        petEl.style.height = `${h}px`;
        petEl.style.backgroundSize = `${w * ATLAS.cols}px ${h * ATLAS.rows}px`;
        petEl.style.backgroundImage = settings.customAtlas
            ? `url("${settings.customAtlas.replace(/"/g, '%22')}")`
            : '';
        petEl.style.opacity = settings.opacity / 100;
        petEl.style.display = settings.enabled ? 'block' : 'none';
        if (!settings.enabled) stopWalk(false);
        applyFrame();
        clampIntoView();
    }

    // =====================================================
    // 拖曳（沿用 GreenGuaiGuai 的座標策略：一律 top/left 定位）
    // =====================================================
    function onMouseDown(e) {
        if (e.button !== 0) return;
        beginDrag(e.clientX, e.clientY);
        e.preventDefault();
    }
    function onMouseMove(e) {
        if (!isDragging) return;
        movePet(e.clientX, e.clientY);
    }
    function onMouseUp() {
        if (!isDragging) return;
        endDrag();
    }
    function onTouchStart(e) {
        const touch = e.touches[0];
        beginDrag(touch.clientX, touch.clientY);
        e.preventDefault();
    }
    function onTouchMove(e) {
        if (!isDragging) return;
        const touch = e.touches[0];
        movePet(touch.clientX, touch.clientY);
        e.preventDefault();
    }
    function onTouchEnd() {
        if (!isDragging) return;
        endDrag();
    }

    function beginDrag(clientX, clientY) {
        isDragging = true;
        hasMoved = false;
        dragStartX = clientX;
        dragStartY = clientY;
        dragLastX = clientX;
        lastInteraction = Date.now();
        stopWalk(false);
        const baseX = parseFloat(petEl.style.left);
        const baseY = parseFloat(petEl.style.top);
        dragOffsetX = clientX - (Number.isFinite(baseX) ? baseX : petEl.offsetLeft);
        dragOffsetY = clientY - (Number.isFinite(baseY) ? baseY : petEl.offsetTop);
        petEl.classList.add('tavernpet-dragging');
        petEl.style.right = 'auto';
        petEl.style.bottom = 'auto';
    }

    function movePet(clientX, clientY) {
        // 超過 3px 才算真的拖動（吸收手指微抖，避免點擊被當成移動）
        if (!hasMoved && Math.hypot(clientX - dragStartX, clientY - dragStartY) > 3) {
            hasMoved = true;
        }
        // 依水平方向切換左右奔跑動畫
        if (hasMoved) {
            const dx = clientX - dragLastX;
            if (dx > 1.5 && animState !== 'running-right') setAnim('running-right');
            else if (dx < -1.5 && animState !== 'running-left') setAnim('running-left');
        }
        dragLastX = clientX;
        const x = Math.max(0, Math.min(window.innerWidth - petEl.offsetWidth, clientX - dragOffsetX));
        const y = Math.max(0, Math.min(window.innerHeight - petEl.offsetHeight, clientY - dragOffsetY));
        petEl.style.left = `${x}px`;
        petEl.style.top = `${y}px`;
    }

    function endDrag() {
        isDragging = false;
        petEl.classList.remove('tavernpet-dragging');
        lastInteraction = Date.now();

        if (!hasMoved) {
            // 純點擊 → 摸頭互動，不寫存檔
            onPetted();
            return;
        }

        // 放下後小小彈跳一下，然後記住新位置
        playOnce('jumping');
        const nx = parseInt(petEl.style.left, 10);
        const ny = parseInt(petEl.style.top, 10);
        if (Number.isNaN(nx) || Number.isNaN(ny)) return;
        const settings = getSettings();
        settings.posX = nx;
        settings.posY = ny;
        saveSettings();
    }

    // ── 摸頭 / 點擊互動 ──
    function onPetted() {
        const now = Date.now();
        petTimes = petTimes.filter((t) => now - t < 4000);
        petTimes.push(now);
        if (petTimes.length >= 3) {
            petTimes = [];
            playOnce('waving', 2);
        } else {
            playOnce(Math.random() < 0.5 ? 'jumping' : 'waving');
        }
    }

    // =====================================================
    // 定位輔助（同 GreenGuaiGuai：ST 的 html transform 使
    // fixed 元素以 <html> 為 containing block，bottom 不可靠，
    // 一律以 JS 計算 top/left）
    // =====================================================
    function setPos(x, y) {
        petEl.style.right = 'auto';
        petEl.style.bottom = 'auto';
        petEl.style.left = `${x}px`;
        petEl.style.top = `${y}px`;
    }

    function placeDefault() {
        if (!petEl) return;
        const { w, h } = cellSize();
        setPos(
            Math.max(0, window.innerWidth - w - 20),
            Math.max(0, window.innerHeight - h - 20),
        );
    }

    // 夾回視口。刻意不寫回 settings：保留使用者在大螢幕拖到的座標，
    // 只有實際拖動 / 散步抵達才更新存檔。
    function clampIntoView() {
        if (!petEl) return;
        const settings = getSettings();
        if (!settings.enabled) return;
        if (!Number.isFinite(settings.posX) || !Number.isFinite(settings.posY)) {
            placeDefault();
            return;
        }
        const w = petEl.offsetWidth || settings.size;
        const h = petEl.offsetHeight || settings.size;
        setPos(
            Math.max(0, Math.min(window.innerWidth - w, settings.posX)),
            Math.max(0, Math.min(window.innerHeight - h, settings.posY)),
        );
    }

    let clampTimer = null;
    function scheduleClamp() {
        if (isDragging) return;
        clearTimeout(clampTimer);
        clampTimer = setTimeout(() => {
            stopWalk(false); // 視口變化時先停下散步再夾限
            clampIntoView();
        }, 150);
    }

    // =====================================================
    // 自由活動：散步、東張西望、發呆
    // =====================================================
    function startWalk() {
        if (!petEl || isDragging || busy || walking) return;
        const w = petEl.offsetWidth;
        const maxX = Math.max(0, window.innerWidth - w);
        const curX = parseFloat(petEl.style.left) || 0;
        let targetX = Math.random() * maxX;
        if (Math.abs(targetX - curX) < 80) {
            targetX = curX > maxX / 2
                ? Math.max(0, curX - 150 - Math.random() * 200)
                : Math.min(maxX, curX + 150 + Math.random() * 200);
        }
        walking = { targetX, lastT: performance.now() };
        setAnim(targetX > curX ? 'running-right' : 'running-left');
        requestAnimationFrame(walkStep);
    }

    function walkStep(t) {
        if (!walking || !petEl) return;
        const dt = Math.min(64, t - walking.lastT);
        walking.lastT = t;
        const curX = parseFloat(petEl.style.left) || 0;
        const maxX = Math.max(0, window.innerWidth - petEl.offsetWidth);
        // 視窗中途縮小時，目標點也要夾回可行範圍，否則永遠走不到
        const target = Math.max(0, Math.min(maxX, walking.targetX));
        const dirSign = target > curX ? 1 : -1;
        const speed = 0.07 * (getSettings().size / 96); // 約 70px/s（隨體型縮放）
        let nx = curX + dirSign * speed * dt;
        nx = Math.max(0, Math.min(maxX, nx));
        const arrived = (dirSign > 0 && nx >= target) || (dirSign < 0 && nx <= target);
        petEl.style.left = `${arrived ? target : nx}px`;
        if (arrived) {
            stopWalk(true);
            return;
        }
        requestAnimationFrame(walkStep);
    }

    function stopWalk(arrivedNaturally) {
        if (!walking) return;
        walking = null;
        settle(); // 不論怎麼停下，動畫都要歸位（呼叫端要接手可再覆蓋）
        if (arrivedNaturally) {
            // 散步抵達後記住新位置，重整不會跳回原點
            const nx = parseInt(petEl.style.left, 10);
            const ny = parseInt(petEl.style.top, 10);
            if (!Number.isNaN(nx) && !Number.isNaN(ny)) {
                const settings = getSettings();
                settings.posX = nx;
                settings.posY = ny;
                saveSettings();
            }
        }
    }

    function idleTick() {
        const settings = getSettings();
        if (!settings.enabled || !settings.autoWalk || reducedMotion) return;
        if (busy || walking || isDragging || transient) return;
        if (Date.now() - lastInteraction < 12000) return;
        const r = Math.random();
        if (r < 0.45) {
            startWalk();
        } else if (r < 0.62) {
            playOnce('review', 2);          // 東看看西看看
        } else if (r < 0.76) {
            playOnce('waiting', 2);         // 期待地看著你
        } else if (r < 0.85) {
            playOnce('waving');
        }
        // 其餘機率：這輪安靜待著
    }

    // =====================================================
    // SillyTavern 事件連動
    // =====================================================
    function bindTavernEvents(context) {
        const es = context.eventSource;
        const et = context.eventTypes || context.event_types;
        if (!es || !et) {
            console.warn(`[${extensionName}] 找不到 eventSource，事件反應停用`);
            return;
        }
        const on = (key, fn) => {
            if (et[key]) {
                es.on(et[key], (...args) => {
                    try {
                        if (!getSettings().enabled || !getSettings().reactions) return;
                        fn(...args);
                    } catch (err) {
                        console.error(`[${extensionName}] 事件處理失敗:`, err);
                    }
                });
            }
        };

        on('GENERATION_STARTED', (type, params, dryRun) => {
            if (dryRun) return;
            busy = true;
            stopWalk(false);
            settle(); // → running（工作中）
        });
        on('GENERATION_ENDED', () => {
            busy = false;
            if (!transient) settle();
        });
        on('GENERATION_STOPPED', () => {
            busy = false;
            playOnce('failed');
        });
        on('MESSAGE_RECEIVED', () => {
            busy = false;
            playOnce('waving');
        });
        on('MESSAGE_SENT', () => {
            playOnce('jumping');
        });
        on('CHAT_CHANGED', () => {
            const now = Date.now();
            if (now - lastGreet < 8000) return;
            lastGreet = now;
            playOnce('waving');
        });
    }

    // =====================================================
    // 設定面板
    // =====================================================
    async function initSettingsPanel() {
        const context = SillyTavern.getContext();
        const settingsHtml = await context.renderExtensionTemplateAsync(
            `third-party/${extensionName}`,
            'templates/settings',
        );
        const root = document.querySelector('#extensions_settings');
        if (!root || !settingsHtml) return;
        root.insertAdjacentHTML('beforeend', settingsHtml);

        const settings = getSettings();
        const $ = (id) => document.querySelector(id);

        const bindCheckbox = (id, key, after) => {
            const el = $(id);
            if (!el) return;
            el.checked = settings[key];
            el.addEventListener('change', () => {
                settings[key] = el.checked;
                applySettings();
                saveSettings();
                if (after) after();
            });
        };

        bindCheckbox('#tavernpet_enabled', 'enabled');
        bindCheckbox('#tavernpet_autowalk', 'autoWalk');
        bindCheckbox('#tavernpet_reactions', 'reactions');

        const sizeEl = $('#tavernpet_size');
        const sizeLabel = $('#tavernpet_size_value');
        if (sizeEl && sizeLabel) {
            sizeEl.value = settings.size;
            sizeLabel.textContent = `${settings.size}px`;
            sizeEl.addEventListener('input', () => {
                settings.size = parseInt(sizeEl.value);
                sizeLabel.textContent = `${settings.size}px`;
                applySettings();
                saveSettings();
            });
        }

        const opacityEl = $('#tavernpet_opacity');
        const opacityLabel = $('#tavernpet_opacity_value');
        if (opacityEl && opacityLabel) {
            opacityEl.value = settings.opacity;
            opacityLabel.textContent = `${settings.opacity}%`;
            opacityEl.addEventListener('input', () => {
                settings.opacity = parseInt(opacityEl.value);
                opacityLabel.textContent = `${settings.opacity}%`;
                applySettings();
                saveSettings();
            });
        }

        const atlasEl = $('#tavernpet_atlas');
        if (atlasEl) {
            atlasEl.value = settings.customAtlas;
            atlasEl.addEventListener('change', () => {
                settings.customAtlas = atlasEl.value.trim();
                applySettings();
                saveSettings();
            });
        }

        const resetEl = $('#tavernpet_reset_pos');
        if (resetEl) {
            resetEl.addEventListener('click', () => {
                settings.posX = null;
                settings.posY = null;
                placeDefault();
                saveSettings();
            });
        }
    }

    // =====================================================
    // 主入口
    // =====================================================
    try {
        const context = SillyTavern.getContext();
        getSettings();
        await initSettingsPanel();
        createPet();
        bindTavernEvents(context);

        // 除錯 / STscript / 預覽頁可用的小 API
        window.TavernPet = {
            play: playOnce,
            walk: startWalk,
            setBusy: (v) => { busy = !!v; settle(); },
            states: Object.keys(STATES),
        };

        console.log(`[${extensionName}] ✅ 酒館桌寵已就位！`);
    } catch (err) {
        console.error(`[${extensionName}] ❌ 載入失敗:`, err);
    }
})();
