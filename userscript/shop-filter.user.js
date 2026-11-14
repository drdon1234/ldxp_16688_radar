// ==UserScript==
// @name         链动小铺 / 16688 组合筛选
// @namespace    local.shop-filter
// @version      1.4.0
// @description  按分类、标题关键词、价格与是否有货组合筛选；支持全部分类汇总。
// @match        https://wzyp.cn/shop/*
// @match        https://www.wzyp.cn/shop/*
// @match        https://ldxp.cn/shop/*
// @match        https://www.ldxp.cn/shop/*
// @match        https://16688.com.cn/shop/*
// @match        https://www.16688.com.cn/shop/*
// @run-at       document-idle
// @grant        GM_getValue
// @grant        GM_setValue
// @grant        GM_addValueChangeListener
// @noframes
// ==/UserScript==

(() => {
  'use strict';
  if (document.getElementById('shop-filter-panel')) return;
  const $ = (s, root = document) => root.querySelector(s);
  const $$ = (s, root = document) => [...root.querySelectorAll(s)];
  const text = e => e?.textContent?.trim() || '';
  const normalize = s => String(s).normalize('NFKC').toLowerCase();
  const tokens = s => normalize(s).split(/[\n,，;；|]+/).map(x => x.trim()).filter(Boolean);
  const defaults = { any: '5x,10x', all: 'team', not: '1x', min: '', max: '35', inclusive: false, stock: true, sort: 'asc', query: '', compact: false };
  const storageKey = () => 'shop-filter:' + location.pathname;
  const is16688 = /(^|\.)16688\.com\.cn$/.test(location.hostname);
  const categorySelector = is16688 ? '.category-side .category-item' : '.fl_box_leng, .arco-menu-item:has(.category-name-text)';
  function currentCategoryName() {
    const selected = $$(categorySelector).find(e => e.matches('.fl_box_leng_xz, .arco-menu-selected, .category-active'));
    return text($('.category-name-text, .category-name', selected || document.createElement('div'))) || text(selected?.children[0]);
  }
  const number = value => value === null || value === undefined || value === '' || typeof value === 'boolean' ? NaN : Number(value);
  function parseProduct(item, categories) {
    const id = is16688 ? item.goods_no : item.goods_key;
    if (typeof id !== 'string' || !id || typeof item.name !== 'string') throw new Error('接口商品结构已变化，缺少商品编号或标题。');
    const price = number(item.price);
    const count = number(is16688 ? item.stock_available_quantity : item.extend?.stock_count);
    let stock = Number.isFinite(count) ? count > 0 : null;
    if (is16688) {
      if (item.stock_available_status === 'out') stock = false;
      else if (['low', 'normal', 'high'].includes(item.stock_available_status)) stock = true;
      // 手工发货等商品可能没有数量；与原站的非 out 可购买状态保持一致。
      else if (item.stock_available_status === '') stock = true;
    }
    const categoryId = String(is16688 ? item.goods_category_no || 'uncategorized' : item.category?.id ?? '');
    const category = categories.find(c => c.id === categoryId) || { id: categoryId, name: is16688 ? '未分类' : item.category?.name || '未分类' };
    const url = new URL((is16688 ? '/goods/' : '/item/') + encodeURIComponent(id), location.origin);
    return { id, name: item.name, price, stock, category, url: url.href };
  }
  function matches(item, f) {
    const name = normalize(item.name);
    const any = tokens(f.any), all = tokens(f.all), not = tokens(f.not);
    return !!name && (!any.length || any.some(k => name.includes(k)))
      && all.every(k => name.includes(k)) && !not.some(k => name.includes(k))
      && (!f.stock || item.stock === true)
      && (f.min === '' || Number.isFinite(item.price) && item.price >= Number(f.min))
      && (f.max === '' || Number.isFinite(item.price) && (f.inclusive ? item.price <= Number(f.max) : item.price < Number(f.max)));
  }

  const host = document.createElement('section');
  host.id = 'shop-filter-panel';
  // Shadow DOM 隔离样式；不改 Vue 管理的商品节点，不破坏原站购买事件和瀑布流。
  const root = host.attachShadow({ mode: 'open' });
  root.innerHTML = `<style>
    :host{display:block;position:fixed;z-index:2147483000;top:24px;right:24px;width:420px;max-width:calc(100vw - 24px);color:#1d2635;font:14px/1.5 system-ui,sans-serif;color-scheme:light;text-align:left}
    *{box-sizing:border-box}.window{background:#fff;border:1px solid #d6dfec;border-radius:16px;box-shadow:0 16px 48px #152b4d26,0 3px 10px #152b4d12;overflow:hidden;display:flex;flex-direction:column;max-height:calc(100dvh - 24px)}
    .header{display:flex;align-items:center;gap:12px;padding:16px 18px;border-bottom:1px solid #e6ecf4;cursor:grab;touch-action:none;user-select:none;background:#f7faff}.header:active{cursor:grabbing}.brand{width:36px;height:36px;display:grid;place-items:center;background:#e5efff;color:#165dce;border-radius:10px;flex:none}.brand svg{width:21px;height:21px}.heading{flex:1;min-width:0}.title{font-size:16px;font-weight:700;letter-spacing:.01em}.subtitle{font-size:12px;color:#5d6b80;margin-top:2px}.header button{padding:6px;width:32px;min-height:32px;display:grid;place-items:center;border:0;background:transparent;color:#56657a}.header button:hover{background:#e6edf7}.header button svg{width:18px;height:18px}
    form{margin:0;padding:18px;overflow:auto;overscroll-behavior:contain;scrollbar-width:thin;scrollbar-color:#bbc9dc #f7faff}.fields{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.wide{grid-column:1/-1}
    label{display:flex;flex-direction:column;gap:6px;font-size:12px;font-weight:550;color:#45556b}input,select,button{font:14px/1.5 system-ui,sans-serif;border-radius:8px;border:1px solid #bdc9da;min-height:38px;padding:8px 10px;color:#1d2635;background:white;min-width:0}
    input,select{width:100%;caret-color:#165dce}input::placeholder{color:#606c7e}input[type=checkbox]{width:17px;min-height:17px;accent-color:#165dce}
    .check{display:flex;flex-direction:row;align-items:center;gap:7px}.options{display:flex;flex-wrap:wrap;gap:16px;padding:16px 0}.actions{display:flex;align-items:center;flex-wrap:wrap;gap:8px}.actions .primary{flex:1}.actions [data-action=clear],.actions [data-action=preset]{font-size:12px;padding:8px}
    button{cursor:pointer}button:hover{background:#edf3fc}button.primary{background:#165dce;color:#fff;border-color:#165dce}button.primary:hover{background:#104bac}
    button:disabled{cursor:wait;opacity:.55}input:focus-visible,select:focus-visible,button:focus-visible{outline:2px solid #165dce;outline-offset:2px}
    .hint,.status{color:#52627a;margin:12px 0 0;font-size:12px}.hint{line-height:1.7}.status{font-weight:550;padding-top:12px;border-top:1px solid #e6ecf4}.error{color:#b42318}.results{margin-top:8px}.results:empty{display:none}
    article{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:start;gap:8px 12px;padding:14px 0;border-bottom:1px solid #e6ecf4}article:last-child{border-bottom:0}article .product-link{grid-column:1/-1;justify-self:end;min-height:30px;padding:4px 9px;font-size:12px;color:#165dce;border-color:#ccdcf4;background:#f6f9ff}
    .product-link{display:inline-block;text-decoration:none;border:1px solid #ccdcf4;border-radius:8px;font:12px/1.5 system-ui,sans-serif}.product-link:hover{background:#e5efff}.product-link:focus-visible{outline:2px solid #165dce;outline-offset:2px}
    .result-tools{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:14px;padding-top:14px;border-top:1px solid #e6ecf4}.result-tools .wide{grid-column:1/-1}.result-actions{display:flex;gap:8px;align-items:center;flex-wrap:wrap}.result-actions button,.export{font:12px/1.5 system-ui,sans-serif;min-height:30px;padding:5px 9px}.export{color:#165dce;text-decoration:none;border:1px solid #ccdcf4;border-radius:8px}.export:hover{background:#edf3fc}.row-actions{grid-column:1/-1;display:flex;gap:8px;justify-content:flex-end}.row-actions button{font-size:12px;min-height:30px;padding:4px 9px;color:#165dce;border-color:#ccdcf4;background:#f6f9ff}.results.compact article{padding:9px 0;gap:4px 10px}.results.compact .name{display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}.timestamp{font-size:11px;color:#5d6b80;margin-top:6px}.notice{font-size:12px;color:#165dce;margin-top:6px}.notice:empty{display:none}
    .filter-settings>summary{cursor:pointer;color:#45556b;font-size:13px;font-weight:600;padding-bottom:10px}.filter-settings>summary:focus-visible,.export:focus-visible{outline:2px solid #165dce;outline-offset:2px}
    .presets{padding-bottom:16px;margin-bottom:14px;border-bottom:1px solid #e6ecf4;display:grid;gap:9px}.preset-edit{display:flex;gap:7px}.preset-edit input{flex:1;width:0}.preset-buttons{display:flex;gap:6px;flex-wrap:wrap}.preset-buttons button,.preset-edit button{font-size:12px;padding:6px 9px;min-height:32px}.preset-status{font-size:12px;color:#52627a;overflow-wrap:anywhere;min-height:18px}.preset-status.error{color:#b42318}.preset-buttons .danger{color:#a42525}
    .name{overflow-wrap:anywhere}.meta{color:#536075;font-size:12px;margin-top:3px}.price{font-weight:650;font-variant-numeric:tabular-nums;white-space:nowrap}
    ::selection{background:#d5e6ff;color:#153966}[hidden]{display:none!important}
    .launcher{display:flex;align-items:center;gap:9px;background:#165dce;color:white;border:1px solid #165dce;border-radius:28px;padding:12px 18px;box-shadow:0 6px 20px #163c7133;font-weight:650;white-space:nowrap}.launcher:hover{background:#104bac}.launcher svg{width:19px;height:19px}:host([data-collapsed]){width:max-content}.launcher[data-busy=true]::after{content:'';width:6px;height:6px;background:#fff;border-radius:50%}
    @media(max-width:480px){:host{top:12px;right:12px}form{padding:14px}.header{padding:13px 14px}.window{border-radius:12px}.actions{gap:6px}.actions button{padding:8px}}
    @media(prefers-reduced-motion:no-preference){button{transition:background-color .15s ease,border-color .15s ease}}
  </style><section class="window" aria-label="商品组合筛选悬浮窗"><header class="header" title="拖动标题栏移动窗口">
    <span class="brand" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M4 6h16M7 12h10M10 18h4"/></svg></span>
    <div class="heading"><div class="title">商品组合筛选</div><div class="subtitle">跨分类查找 · 拖动标题栏移动</div></div>
    <button type="button" data-action="minimize" aria-label="收起筛选窗口" title="收起（Esc）"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M5 12h14"/></svg></button>
  </header><form><section class="presets" aria-label="筛选预设管理">
    <label>命名预设<select name="presetChoice"><option value="">选择预设即可应用</option></select></label>
    <div class="preset-edit"><input name="presetName" aria-label="预设名称" maxlength="80" placeholder="预设名称，例如：低价有货 Team"><button type="button" data-preset="save">另存为预设</button></div>
    <div class="preset-buttons"><button type="button" data-preset="apply">应用所选</button><button type="button" data-preset="update">更新条件</button><button type="button" data-preset="rename">重命名</button><button class="danger" type="button" data-preset="delete">删除</button><button type="button" data-preset="undo" hidden>撤销删除</button></div>
    <div class="preset-status" role="status" aria-live="polite">独立预设 · 同一油猴脚本跨商家、跨平台共享。</div>
  </section><details class="filter-settings" open><summary>筛选条件</summary>
    <div class="fields">
      <label class="wide">筛选分类<select name="scope"><option value="current">当前分类</option><option value="all">全部分类</option></select></label>
      <label>最低价格（元，含）<input name="min" type="number" min="0" step="any" placeholder="不限"></label>
      <label>最高价格（元）<input name="max" type="number" min="0" step="any" placeholder="不限"></label>
      <label class="wide">包含任意一个词（或）<input name="any" placeholder="5x,10x"></label>
      <label>同时包含所有词（且）<input name="all" placeholder="team"></label>
      <label>排除任意一个词<input name="not" placeholder="1x"></label>
    </div>
    <div class="options"><label class="check"><input name="stock" type="checkbox">仅看有货</label><label class="check"><input name="inclusive" type="checkbox">包含最高价</label></div><div class="actions">
      <button class="primary" type="submit" title="重新获取最新商品（Ctrl / ⌘ + Enter）">加载并筛选</button><button type="button" data-action="stop" hidden>停止</button><button type="button" data-action="preset">恢复默认</button><button type="button" data-action="clear">清除筛选</button></div>
    <p class="hint">关键词用逗号分隔，忽略大小写，按标题字面匹配。通过接口后台读取，不改变原页面分类和滚动位置。</p>
    </details>
    <div class="result-tools"><label>结果排序<select name="sort"><option value="asc">价格：从低到高</option><option value="desc">价格：从高到低</option><option value="original">原始顺序</option></select></label><label>结果内搜索<input name="query" type="search" placeholder="进一步查找标题"></label><div class="result-actions wide"><label class="check"><input name="compact" type="checkbox">紧凑显示</label><button type="button" data-action="copy-all">复制结果链接</button><a class="export" href="#" download="商品筛选结果.csv">导出 CSV</a></div></div>
    <p class="status" role="status" aria-live="polite">请选择分类，然后加载并筛选。</p><div class="timestamp"></div><div class="notice" role="status" aria-live="polite"></div><div class="results" aria-label="筛选结果"></div>
  </form></section><button class="launcher" type="button" aria-label="展开商品筛选" aria-expanded="false" hidden><svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><path d="M4 6h16M7 12h10M10 18h4"/></svg>商品筛选</button>`;
  document.body.prepend(host);
  const form = $('form', root), status = $('.status', root), results = $('.results', root);
  const windowPanel = $('.window', root), launcher = $('.launcher', root), header = $('.header', root);
  const windowStorageKey = 'shop-filter-window';
  let position = null, drag = null;
  function keepInViewport() {
    const rect = host.getBoundingClientRect();
    const x = position?.x ?? Math.max(12, innerWidth - rect.width - 24);
    const y = position?.y ?? 24;
    const left = Math.max(12, Math.min(x, innerWidth - rect.width - 12));
    const top = Math.max(12, Math.min(y, innerHeight - rect.height - 12));
    host.style.left = left + 'px'; host.style.top = top + 'px'; host.style.right = 'auto';
  }
  function saveWindow() {
    try { localStorage.setItem(windowStorageKey, JSON.stringify({ position, collapsed: host.hasAttribute('data-collapsed') })); } catch {}
  }
  function collapse(value, focus = true) {
    host.toggleAttribute('data-collapsed', value); windowPanel.hidden = value; launcher.hidden = !value;
    launcher.setAttribute('aria-expanded', String(!value));
    keepInViewport(); saveWindow();
    if (focus) (value ? launcher : $('[data-action=minimize]', root)).focus({ preventScroll: true });
  }
  try {
    const saved = JSON.parse(localStorage.getItem(windowStorageKey) || '{}');
    if (Number.isFinite(saved.position?.x) && Number.isFinite(saved.position?.y)) position = saved.position;
    collapse(!!saved.collapsed, false);
  } catch { keepInViewport(); }
  $('[data-action=minimize]', root).addEventListener('click', () => collapse(true));
  launcher.addEventListener('click', () => collapse(false));
  root.addEventListener('keydown', event => { if (event.key === 'Escape' && !host.hasAttribute('data-collapsed')) { event.preventDefault(); collapse(true); } });
  header.addEventListener('pointerdown', event => {
    if (event.button !== 0 || event.target.closest('button')) return;
    const rect = host.getBoundingClientRect();
    drag = { id: event.pointerId, dx: event.clientX - rect.left, dy: event.clientY - rect.top };
    header.setPointerCapture(event.pointerId); event.preventDefault();
  });
  header.addEventListener('pointermove', event => {
    if (!drag || event.pointerId !== drag.id) return;
    position = { x: event.clientX - drag.dx, y: event.clientY - drag.dy }; keepInViewport();
    const rect = host.getBoundingClientRect(); position = { x: rect.left, y: rect.top };
  });
  const finishDrag = () => { if (drag) { drag = null; saveWindow(); } };
  header.addEventListener('pointerup', finishDrag); header.addEventListener('pointercancel', finishDrag); header.addEventListener('lostpointercapture', finishDrag);
  window.addEventListener('resize', keepInViewport);
  new ResizeObserver(keepInViewport).observe(host);
  let generation = 0, busy = false, cache = [], complete = false, lastPath = location.pathname;
  let controller = null, catalog = [], canonicalShop = '', fetchedAt = null, loadedCategoryId = null;
  const field = name => form.elements.namedItem(name);
  function setFields(value) { for (const k of Object.keys(defaults)) typeof defaults[k] === 'boolean' ? field(k).checked = !!value[k] : field(k).value = value[k] ?? defaults[k]; if (!field('sort').value) field('sort').value = 'asc'; }
  function filters() { return Object.fromEntries(Object.keys(defaults).map(k => [k, typeof defaults[k] === 'boolean' ? field(k).checked : field(k).value.trim()])); }
  try { setFields({ ...defaults, ...JSON.parse(localStorage.getItem(storageKey()) || '{}') }); } catch { setFields(defaults); }
  function message(s, error = false) { status.textContent = s; status.classList.toggle('error', error); }
  function saveFilters() { try { localStorage.setItem(storageKey(), JSON.stringify(filters())); } catch {} }
  function notice(value) { $('.notice', root).textContent = value; }
  const presetStorageKey = 'shop-filter-presets';
  let deletedPreset = null;
  function presetMessage(value, error = false) { const node = $('.preset-status', root); node.textContent = value; node.classList.toggle('error', error); }
  function readPresets() {
    const raw = GM_getValue(presetStorageKey, null);
    const items = raw === null ? [] : JSON.parse(raw);
    const ids = new Set(), names = new Set();
    if (!Array.isArray(items) || items.some(p => {
      if (!p || typeof p.id !== 'string' || !p.id || typeof p.name !== 'string' || !p.name.trim() || p.name.length > 80 || ids.has(p.id) || names.has(normalize(p.name)) || !p.category || !['all','named'].includes(p.category.kind) || (p.category.kind === 'named' && (typeof p.category.name !== 'string' || !p.category.name.trim())) || !p.filters || typeof p.filters !== 'object') return true;
      ids.add(p.id); names.add(normalize(p.name));
      return Object.keys(defaults).some(k => typeof p.filters[k] !== typeof defaults[k]) || !['asc','desc','original'].includes(p.filters.sort)
        || ['min','max'].some(k => p.filters[k] !== '' && (!Number.isFinite(Number(p.filters[k])) || Number(p.filters[k]) < 0))
        || (p.filters.min !== '' && p.filters.max !== '' && Number(p.filters.min) > Number(p.filters.max));
    })) throw new Error('预设数据格式异常，已保留原数据，未进行覆盖。');
    return items;
  }
  function refreshPresets(selected = field('presetChoice').value) {
    const items = readPresets(), select = field('presetChoice');
    select.replaceChildren(new Option(items.length ? '选择预设即可应用' : '尚无预设，请保存当前条件', ''));
    for (const p of items) select.add(new Option(p.name, p.id));
    if (items.some(p => p.id === selected)) select.value = selected;
    updatePresetButtons();
  }
  function updatePresetButtons() {
    const selected = !!field('presetChoice').value;
    for (const button of $$('[data-preset]', root)) button.disabled = busy || (!selected && ['apply','update','rename','delete'].includes(button.dataset.preset));
    $('[data-preset=undo]', root).hidden = !deletedPreset;
  }
  function persistPresets(items, selected) {
    // 先成功写入，再更新界面；额度不足或禁用存储时不伪报成功。
    GM_setValue(presetStorageKey, JSON.stringify(items));
    refreshPresets(selected);
  }
  function presetName(items, exceptId = '') {
    const name = field('presetName').value.trim();
    if (!name || name.length > 80) throw new Error('请输入1至80字的预设名称。');
    if (items.some(p => p.id !== exceptId && normalize(p.name) === normalize(name))) throw new Error('已有同名预设，请换一个名称，或选中后更新条件。');
    return name;
  }
  function snapshotPreset() {
    const f = filters();
    if (!form.checkValidity() || (f.min !== '' && f.max !== '' && Number(f.min) > Number(f.max))) throw new Error('请先修正价格范围和输入内容，再保存预设。');
    const category = resolveCategory(field('scope').value, currentCategoryName());
    // 分类编号属于商家；独立预设只保存“全部”或分类名称。
    return { category: category.all ? { kind: 'all' } : { kind: 'named', name: category.name }, filters: f };
  }
  async function applyPreset() {
    if (busy) return;
    try {
      const p = readPresets().find(item => item.id === field('presetChoice').value);
      if (!p) { updatePresetButtons(); return; }
      updatePresetButtons(); field('presetName').value = p.name;
      const candidates = catalog.filter(c => p.category.kind === 'all' ? c.all : !c.all && normalize(c.name.trim()) === normalize(p.category.name.trim()));
      if (candidates.length !== 1) throw new Error('当前店铺没有可唯一匹配的分类“' + (p.category.name || '全部') + '”。请手动选择分类后更新预设，或另存为全部分类预设。');
      const category = candidates[0];
      const reuse = complete && loadedCategoryId === category.id;
      field('scope').value = category.all ? 'all' : 'category:' + category.id; setFields(p.filters); field('presetName').value = p.name; saveFilters();
      presetMessage('已应用“' + p.name + '” · ' + category.name);
      updatePresetButtons();
      if (reuse) { notice('已使用现有数据应用预设；点击加载可获取最新数据。'); render(); }
      else await run();
    } catch (e) { presetMessage(e.message + ' 预设仍然保留。', true); }
  }
  function mutatePreset(action) {
    if (busy) return;
    try {
      const items = readPresets(), selected = field('presetChoice').value, index = items.findIndex(p => p.id === selected);
      if (action === 'save') {
        const name = presetName(items), snapshot = snapshotPreset();
        const p = { id: crypto.randomUUID(), name, ...snapshot };
        persistPresets([...items,p],p.id); field('presetName').value = name; presetMessage('已保存“' + name + '” · ' + (snapshot.category.name || '全部分类'));
      } else if (action === 'undo') {
        if (!deletedPreset) return;
        if (items.some(p => p.id === deletedPreset.id || normalize(p.name) === normalize(deletedPreset.name))) throw new Error('已存在同名预设，请先重命名后再撤销。');
        const restored = deletedPreset; persistPresets([...items,restored],restored.id); deletedPreset = null;
        field('presetName').value = restored.name; updatePresetButtons(); presetMessage('已恢复“' + restored.name + '”。');
      } else {
        if (index < 0) throw new Error('请选择一个已保存的预设。');
        const p = items[index];
        if (action === 'rename') {
          const name = presetName(items,p.id); items[index] = { ...p,name }; persistPresets(items,p.id); presetMessage('已重命名为“' + name + '”。');
        } else if (action === 'update') {
          items[index] = { ...p,...snapshotPreset() }; persistPresets(items,p.id); presetMessage('已更新“' + p.name + '”的条件。');
        } else if (action === 'delete') {
          persistPresets(items.filter(item => item.id !== p.id),''); deletedPreset = p; field('presetName').value = ''; updatePresetButtons(); presetMessage('已删除“' + p.name + '”，本次页面内可撤销。');
        }
      }
    } catch (e) { presetMessage('操作未完成：' + e.message, true); }
  }
  field('presetChoice').addEventListener('change', applyPreset);
  $('[data-preset=apply]', root).addEventListener('click', applyPreset);
  for (const button of $$('[data-preset]', root)) if (button.dataset.preset !== 'apply') button.addEventListener('click', () => mutatePreset(button.dataset.preset));
  function markPresetEdited() {
    if (field('presetChoice').value) presetMessage('条件已修改；点击“更新条件”保存到所选预设，或另存为新预设。');
  }
  function visibleItems() {
    const f = filters(), query = normalize(f.query.trim());
    const found = cache.filter(item => matches(item, f) && (!query || normalize(item.name).includes(query)));
    if (f.sort !== 'original') found.sort((a, b) => {
      const av = Number.isFinite(a.price), bv = Number.isFinite(b.price);
      if (av !== bv) return av ? -1 : 1;
      if (!av) return 0;
      return (a.price - b.price) * (f.sort === 'desc' ? -1 : 1);
    });
    return found;
  }
  async function copyText(value, success) {
    if (!value) { notice('没有可复制的结果。'); return; }
    try { await navigator.clipboard.writeText(value); notice(success); }
    catch { notice('剪贴板权限不可用，可使用“导出 CSV”，或右键商品链接复制。'); }
  }
  function check(id) { if (id !== generation || location.pathname !== lastPath) throw new Error('操作已停止或商家已切换；当前结果不代表全部商品。'); }

  function setBusy(value) {
    busy = value;
    launcher.dataset.busy = String(value);
    launcher.setAttribute('aria-label', value ? '展开商品筛选，正在加载' : '展开商品筛选');
    $('button[type=submit]', root).disabled = value;
    $('[data-action=stop]', root).hidden = !value;
    for (const e of $$('input,select,[data-action=preset]', root)) e.disabled = value;
    updatePresetButtons();
  }
  function refreshCategories() {
    const select = field('scope'), selected = select.value;
    select.replaceChildren(new Option('当前分类', 'current'), new Option('全部分类', 'all'));
    for (const c of catalog.filter(c => !c.all)) select.add(new Option(c.name, 'category:' + c.id));
    if ([...select.options].some(o => o.value === selected)) select.value = selected;
  }
  async function request(path, body, signal) {
    const timeoutController = new AbortController();
    const abort = () => timeoutController.abort();
    if (signal.aborted) abort(); else signal.addEventListener('abort', abort, { once: true });
    let timedOut = false;
    const timer = setTimeout(() => { timedOut = true; timeoutController.abort(); }, 20000);
    try {
      const response = await fetch(new URL(path, location.origin), {
        method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body), signal: timeoutController.signal
      });
      if (!response.ok) throw new Error('商品查询失败：HTTP ' + response.status);
      let json;
      try { json = await response.json(); } catch { throw new Error('接口未返回JSON；请在原站正常访问后重试。'); }
      if (json.code !== 1) throw new Error(String(json.msg || '商品查询接口返回失败').slice(0,200));
      return json.data;
    } catch (error) {
      if (timedOut) throw new Error('商品查询超时，请稍后重试。');
      throw error;
    } finally { clearTimeout(timer); signal.removeEventListener('abort', abort); }
  }
  async function loadCatalog(id, signal) {
    const path = location.pathname;
    const shop = decodeURIComponent(path.split('/')[2] || '');
    if (!shop) throw new Error('无法识别商家编号。');
    let data, next, canonical = shop;
    if (is16688) {
      const detail = await request('/shopApi/shop/detail', { shop_no: shop }, signal); check(id);
      if (typeof detail?.shop_no !== 'string' || !detail.shop_no) throw new Error('无法解析店铺资料。');
      canonical = detail.shop_no;
      data = await request('/shopApi/goodsCategory/list', { shop_no: canonical }, signal); check(id);
      if (!Array.isArray(data)) throw new Error('分类接口结构已变化。');
      next = [{ id: '', name: '全部宝贝', all: true }, ...data.map(c => ({ id: String(c.goods_category_no), name: c.name })), { id: 'uncategorized', name: '未分类' }];
    } else {
      data = await request('/shopApi/Shop/categoryList', { token: shop, goods_type: 'card' }, signal); check(id);
      if (!Array.isArray(data)) throw new Error('分类接口结构已变化。');
      next = data.map(c => ({ id: String(c.id), name: c.name, all: Number(c.id) === 0 }));
      if (!next.some(c => c.all)) next.unshift({ id: '0', name: '全部', all: true });
    }
    if (next.some(c => !c.name || c.id === 'undefined')) throw new Error('分类接口缺少分类编号或名称。');
    check(id); catalog = next; canonicalShop = canonical; refreshCategories();
  }
  function resolveCategory(scope, currentName) {
    if (scope === 'all') return catalog.find(c => c.all);
    if (scope.startsWith('category:')) {
      const found = catalog.find(c => c.id === scope.slice(9));
      if (!found) throw new Error('所选分类已不存在，请重新选择。');
      return found;
    }
    if (!currentName) throw new Error('无法识别原页当前分类，请在悬浮窗选择具体分类或全部分类。');
    if (/^(全部|全部宝贝|全部商品)$/.test(currentName)) return catalog.find(c => c.all);
    const found = catalog.filter(c => c.name === currentName);
    if (found.length !== 1) throw new Error('当前分类无法唯一对应接口分类，请在悬浮窗直接选择。');
    return found[0];
  }
  async function loadProducts(category, id, signal) {
    const seen = new Set();
    function append(list) {
      for (const raw of list) {
        const item = parseProduct(raw, catalog);
        if (seen.has(item.id)) throw new Error('分页中出现重复商品编号，列表可能正在变化；请重新查询。');
        seen.add(item.id); cache.push(item);
      }
    }
    if (is16688) {
      message('正在后台读取：' + category.name + '…');
      const data = await request('/shopApi/goods/list', { shop_no: canonicalShop, goods_category_no: category.id, keywords: '', sort: 'default' }, signal); check(id);
      if (!Array.isArray(data?.list)) throw new Error('商品列表接口结构已变化。');
      append(data.list); return;
    }
    let expected = null;
    for (let current = 1; current <= 1000; current++) {
      check(id); message('正在后台读取：' + category.name + '，第 ' + current + ' 页（已获取 ' + cache.length + ' 件）…');
      const data = await request('/shopApi/Shop/goodsList', { token: canonicalShop, goods_type: 'card', category_id: Number(category.id), keywords: '', current, pageSize: 20 }, signal); check(id);
      const total = number(data?.total);
      if (!Array.isArray(data?.list) || !Number.isInteger(total) || total < 0) throw new Error('商品分页接口结构已变化。');
      if (expected !== null && expected !== total) throw new Error('查询期间商品总数发生变化，请重新查询以确保完整。');
      expected = total; append(data.list);
      if (cache.length === total) return;
      if (cache.length > total || !data.list.length) throw new Error('接口返回的商品数量与总数不一致，请重试。');
    }
    throw new Error('已达到分页保护上限，结果未完成。');
  }
  function render() {
    const found = visibleItems();
    results.classList.toggle('compact', field('compact').checked);
    $('.timestamp', root).textContent = fetchedAt ? '数据获取于 ' + fetchedAt.toLocaleString('zh-CN', { hour12: false }) + ' · 点击加载可刷新' : '';
    results.replaceChildren();
    for (const item of found) {
      const row = document.createElement('article');
      const detail = document.createElement('div'), name = document.createElement('div'), meta = document.createElement('div');
      name.className = 'name'; name.textContent = item.name; name.title = item.name;
      meta.className = 'meta'; meta.textContent = `${item.category?.name || '当前分类'} · ${item.stock === true ? '有货' : item.stock === false ? '缺货' : '库存未识别'}`;
      detail.append(name, meta);
      const price = document.createElement('span'); price.className = 'price'; price.textContent = Number.isFinite(item.price) ? `¥${item.price}` : '价格未识别';
      const locate = document.createElement('a'); locate.className = 'product-link'; locate.textContent = '查看商品';
      locate.href = item.url; locate.target = '_blank'; locate.rel = 'noopener noreferrer';
      const rowActions = document.createElement('div'); rowActions.className = 'row-actions';
      const copy = document.createElement('button'); copy.type = 'button'; copy.textContent = '复制链接';
      copy.setAttribute('aria-label', '复制链接：' + item.name);
      copy.addEventListener('click', () => copyText(item.url, '已复制商品链接。'));
      rowActions.append(copy, locate); row.append(detail, price, rowActions); results.append(row);
    }
    const unknown = cache.filter(x => x.stock === null).length;
    message(`${complete ? '筛选完成' : '已加载部分'}：${found.length} / ${cache.length} 件匹配${unknown ? `；${unknown} 件库存未识别，“仅看有货”已排除` : ''}${found.length ? '' : '。可放宽条件后重试'}。`);
  }
  async function run(event) {
    event?.preventDefault();
    if (busy) return;
    if (!form.checkValidity()) $('.filter-settings', root).open = true;
    if (!form.reportValidity()) return;
    const f = filters();
    if (f.min !== '' && f.max !== '' && Number(f.min) > Number(f.max)) { message('最低价格不能高于最高价格。', true); return; }
    const scope = field('scope').value, currentName = currentCategoryName();
    controller?.abort(); controller = new AbortController();
    const signal = controller.signal, id = ++generation;
    cache = []; complete = false; fetchedAt = null; loadedCategoryId = null; results.replaceChildren(); $('.timestamp', root).textContent = ''; notice(''); setBusy(true);
    try {
      try { localStorage.setItem(storageKey(), JSON.stringify(f)); } catch {}
      message('正在后台读取商品分类…');
      await loadCatalog(id, signal);
      const category = resolveCategory(scope, currentName);
      await loadProducts(category, id, signal); check(id);
      complete = true; loadedCategoryId = category.id; fetchedAt = new Date(); setBusy(false); render();
    } catch (e) {
      if (id === generation) { complete = false; setBusy(false); render(); message(e.message + ' 已获取 ' + cache.length + ' 件，仅供部分参考。', true); }
    } finally { if (id === generation) { controller = null; setBusy(false); } }
  }
  function stop() { controller?.abort(); controller = null; generation++; setBusy(false); complete = false; render(); message('已停止，当前结果仅覆盖已接收的数据。'); }
  form.addEventListener('submit', run);
  $('[data-action=stop]', root).addEventListener('click', stop);
  $('[data-action=preset]', root).addEventListener('click', () => { setFields(defaults); saveFilters(); markPresetEdited(); notice('已恢复默认条件和价格升序。'); render(); });
  $('[data-action=clear]', root).addEventListener('click', () => { controller?.abort(); controller = null; generation++; setBusy(false); setFields({ ...defaults,any:'',all:'',not:'',min:'',max:'',stock:false }); saveFilters(); markPresetEdited(); render(); notice('已清除限制，保留已获取商品；默认按价格升序。'); });
  form.addEventListener('input', event => { if (['scope','presetName','presetChoice'].includes(event.target.name)) return; saveFilters(); markPresetEdited(); if (!busy) { notice(''); render(); } });
  field('scope').addEventListener('change', () => { cache = []; complete = false; fetchedAt = null; loadedCategoryId = null; results.replaceChildren(); $('.timestamp', root).textContent = ''; notice(''); markPresetEdited(); message('分类已改变，请点击“加载并筛选”。'); });
  root.addEventListener('keydown', event => {
    if (event.key !== 'Enter') return;
    if (event.ctrlKey || event.metaKey) { event.preventDefault(); if (!busy) form.requestSubmit(); }
    else if (event.target === field('query') || event.target === field('presetName')) event.preventDefault();
  });
  $('[data-action=copy-all]', root).addEventListener('click', () => {
    if (busy) { notice('请等待加载完成，或先停止查询。'); return; }
    const items = visibleItems(); copyText(items.map(item => item.name + '\n' + item.url).join('\n\n'), '已复制 ' + items.length + ' 件商品的标题和链接。');
  });
  let exportUrl = null;
  $('.export', root).addEventListener('click', event => {
    const items = visibleItems();
    if (busy || !items.length) { event.preventDefault(); notice(busy ? '请等待加载完成，或先停止查询。' : '没有可导出的结果。'); return; }
    const cell = value => { let s = String(value ?? ''); if (/^[\s]*[=+@-]/.test(s)) s = "'" + s; return '"' + s.replaceAll('"', '""') + '"'; };
    const rows = [['商品名称','价格（元）','库存','分类','商品链接','查询范围完整','获取时间'], ...items.map(item => [item.name,Number.isFinite(item.price) ? item.price : '',item.stock === true ? '有货' : item.stock === false ? '缺货' : '未识别',item.category.name,item.url,complete ? '是' : '否',fetchedAt?.toISOString() || ''])];
    if (exportUrl) URL.revokeObjectURL(exportUrl);
    exportUrl = URL.createObjectURL(new Blob(['\uFEFF' + rows.map(row => row.map(cell).join(',')).join('\r\n')], { type: 'text/csv;charset=utf-8' }));
    event.currentTarget.href = exportUrl;
    event.currentTarget.download = '商品筛选-' + canonicalShop + (complete ? '' : '-部分结果') + '.csv';
    notice('已导出当前排序下的 ' + items.length + ' 件结果' + (complete ? '。' : '（部分数据）。'));
  });
  window.addEventListener('pagehide', () => { if (exportUrl) URL.revokeObjectURL(exportUrl); });
  async function initialize() {
    controller?.abort(); controller = new AbortController();
    const id = ++generation, signal = controller.signal; setBusy(true);
    try { await loadCatalog(id, signal); check(id); message('分类已就绪，点击“加载并筛选”后台获取商品。'); }
    catch (e) { if (id === generation) message('分类读取失败：' + e.message + ' 点击加载可重试。', true); }
    finally { if (id === generation) { controller = null; setBusy(false); } }
  }
  // 只监听商家路由变化，不操作页面，不轮询商品接口。
  setInterval(() => {
    if (location.pathname !== lastPath) {
      lastPath = location.pathname; cache = []; complete = false; fetchedAt = null; loadedCategoryId = null; deletedPreset = null; catalog = []; results.replaceChildren(); $('.timestamp', root).textContent = ''; notice(''); refreshCategories();
      field('presetName').value = ''; try { refreshPresets(''); presetMessage('独立预设 · 同一油猴脚本跨商家、跨平台共享。'); } catch (e) { field('presetChoice').replaceChildren(new Option('预设读取失败','')); presetMessage(e.message,true); }
      try { setFields({ ...defaults, ...JSON.parse(localStorage.getItem(storageKey()) || '{}') }); } catch { setFields(defaults); }
      initialize();
    }
  }, 1000);
  try { refreshPresets(); } catch (e) { presetMessage('预设读取失败：' + e.message,true); }
  GM_addValueChangeListener(presetStorageKey, (key, oldValue, newValue, remote) => { if (remote) { try { refreshPresets(); presetMessage('预设列表已与其他标签页同步。'); } catch (e) { presetMessage(e.message,true); } } });
  initialize();
})();
