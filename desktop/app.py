from __future__ import annotations

import copy
import json
import os
import sys
import threading
from contextlib import nullcontext
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QThread, Qt, Signal, QTimer, QUrl, QLockFile, QItemSelectionModel, QItemSelection
from PySide6.QtGui import QColor, QDesktopServices, QKeySequence, QShortcut, QPalette
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QLineEdit, QPlainTextEdit, QComboBox, QCheckBox, QFormLayout,
    QTableView, QHeaderView, QSplitter, QScrollArea, QAbstractItemView, QMessageBox,
    QInputDialog, QFileDialog, QFrame, QTabWidget)
from core import DEFAULT_FILTERS, DEFAULT_URLS, Store, parse_shops, fetch_shop, filter_products, validate_filters, export_csv, norm, reset_platform_limits, configure_cooldowns, NetworkSession


class Worker(QThread):
    progress = Signal(str, str)
    result = Signal(object)

    def __init__(self, shops):
        super().__init__()
        self.shops = shops
        self.cancel = threading.Event()

    def run(self):
        reset_platform_limits()
        def run_platform(shops):
            with NetworkSession() as session:
                for shop in shops:
                    self.progress.emit(shop.url, '排队查询 · 同平台串行、限速及分批休息')
                    self.result.emit(fetch_shop(shop, self.cancel, self.progress.emit, lambda: nullcontext(session)))
        groups = [[s for s in self.shops if s.platform == platform] for platform in dict.fromkeys(s.platform for s in self.shops)]
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(run_platform, shops) for shops in groups]
            for future in as_completed(futures):
                future.result()


class NoWheelComboBox(QComboBox):
    """下拉框未展开时不响应滚轮，避免鼠标经过时误改选项。"""
    def wheelEvent(self, event):
        if self.view().isVisible():
            super().wheelEvent(event)
        else:
            event.ignore()


class ProductsModel(QAbstractTableModel):
    headers = ['商品名称', '价格 / 元', '库存状态', '分类', '商家', '平台', '库存数量']

    def __init__(self):
        super().__init__()
        self.items = []

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.items)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.headers)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self.headers[section]

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        p = self.items[index.row()]
        values = [p.name, f'{p.price:.2f}' if p.price is not None else '—',
                  '有货' if p.stock else '缺货' if p.stock is False else '未识别', p.category, p.shop_name, p.platform, str(p.stock_count) if p.stock_count is not None else '未公开']
        if role in (Qt.DisplayRole, Qt.ToolTipRole):
            return values[index.column()]
        if role == Qt.ForegroundRole and index.column() == 2:
            return QColor('#087f5b' if p.stock else '#8a5260')
        if role == Qt.TextAlignmentRole and index.column() == 1:
            return int(Qt.AlignRight | Qt.AlignVCenter)

    def replace(self, items):
        self.beginResetModel()
        self.items = items
        self.endResetModel()


STYLE = '''
QWidget {font-family: "Microsoft YaHei UI"; font-size: 13px; color:#25334a;}
QDialog, QMessageBox {background:#f8faff;}
QWidget:disabled {color:#586880;}
QMainWindow {background:#edf1f7;}
QWidget#searchConditions, QWidget#filterConditions {background:#f8faff; border:1px solid #d6dfec; border-radius:8px;}
QWidget#sidebar, QWidget#results {background:white; border-radius:12px;}
QLabel#title {font-size:25px; font-weight:700; color:#152c50;}
QLabel#section {font-size:15px; font-weight:700; margin-top:8px;}
QLabel#muted {color:#586880; font-size:12px;}
QLineEdit,QPlainTextEdit,QComboBox {background:#f8faff; border:1px solid #d6dfec; border-radius:6px; padding:6px; selection-background-color:#245dcc; selection-color:white; placeholder-text-color:#586880;}
QComboBox QAbstractItemView, QMenu {background:white; color:#25334a; border:1px solid #b5c3d8; selection-background-color:#dce9ff; selection-color:#173b71;}
QComboBox {padding-right:28px;}
QComboBox::drop-down {width:26px; border:0; border-left:1px solid #d6dfec; background:#f1f5fc; border-top-right-radius:6px; border-bottom-right-radius:6px;}
QComboBox::drop-down:hover {background:#e4edfc;}
QTabWidget::pane {border:1px solid #d6dfec; border-radius:8px; background:white; top:-1px;}
QTabBar::tab {background:#edf2fa; color:#52627a; padding:9px 16px; border:1px solid transparent; border-top-left-radius:7px; border-top-right-radius:7px;}
QTabBar::tab:selected {background:white; color:#173b71; border-color:#d6dfec; border-bottom-color:white; font-weight:600;}
QToolTip {background:#f8faff; color:#25334a; border:1px solid #b5c3d8; padding:6px;}
QLineEdit:focus,QPlainTextEdit:focus,QComboBox:focus {border:1px solid #2864d7;}
QPushButton {background:#f1f5fc; border:1px solid #d9e2f0; border-radius:6px; padding:7px 11px;}
QPushButton:hover {background:#e4edfc; border-color:#8aaae0;}
QPushButton:disabled {color:#586880; background:#f1f3f6;}
QPushButton#primary {background:#245dcc; color:white; border-color:#245dcc; font-weight:600;}
QPushButton#primary:hover {background:#194eaf;}
QPushButton#primary:disabled {color:#435470; background:#e2e9f5; border-color:#c9d5e7;}
QPushButton:focus {border:1px solid #245dcc;}
QCheckBox {spacing:7px; padding:3px 0;}
QTableView {border:0; gridline-color:#edf1f7; background:white; alternate-background-color:#f7f9fd; selection-background-color:#dce9ff; selection-color:#173b71;}
QHeaderView::section {background:#f0f4fa; border:0; border-bottom:1px solid #dbe3ef; padding:9px; font-weight:600;}
QScrollArea {border:0; background:transparent;}
QSplitter::handle {background:transparent; width:12px;}
QScrollBar:vertical {background:#edf1f7; width:12px; margin:0;}
QScrollBar:horizontal {background:#edf1f7; height:12px; margin:0;}
QScrollBar::handle {background:#8b9cb5; border-radius:5px; min-height:24px; min-width:24px;}
QScrollBar::handle:hover {background:#586880;}
QScrollBar::add-line, QScrollBar::sub-line {width:0; height:0;}
QScrollBar::add-page, QScrollBar::sub-page {background:transparent;}
'''


def apply_theme(app):
    """固定完整浅色调色板，避免系统深色背景与局部样式的深色文字混用。"""
    app.setStyle('Fusion')
    app.styleHints().setColorScheme(Qt.ColorScheme.Light)
    palette = QPalette()
    colors = {
        'Window':'#edf1f7', 'WindowText':'#25334a', 'Base':'#ffffff',
        'AlternateBase':'#f7f9fd', 'Text':'#25334a', 'Button':'#f1f5fc',
        'ButtonText':'#25334a', 'Highlight':'#245dcc', 'HighlightedText':'#ffffff',
        'ToolTipBase':'#f8faff', 'ToolTipText':'#25334a', 'PlaceholderText':'#586880',
        'Light':'#ffffff', 'Midlight':'#e4ebf5', 'Mid':'#b5c3d8', 'Dark':'#586880',
        'Shadow':'#435470', 'BrightText':'#ffffff', 'Link':'#245dcc',
        'LinkVisited':'#6247a6', 'Accent':'#245dcc',
    }
    for role, color in colors.items():
        palette.setColor(getattr(QPalette.ColorRole, role), QColor(color))
    for role in ('WindowText','Text','ButtonText','PlaceholderText'):
        palette.setColor(QPalette.ColorGroup.Disabled, getattr(QPalette.ColorRole,role), QColor('#586880'))
    app.setPalette(palette)
    app.setStyleSheet(STYLE)


class Window(QMainWindow):
    def __init__(self, store):
        super().__init__()
        self.store = store
        self.worker = None
        self.outcomes = []
        self.shops = []
        self.statuses = {}
        self.fetched_at = ''
        self.close_pending = False
        self.loading = True
        self.setWindowTitle('商家联合筛选器 · 链动小铺 / 16688')
        self.resize(1320, 860)
        self.setMinimumSize(1120, 680)
        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(22, 18, 22, 16)
        title = QLabel('商家联合筛选器'); title.setObjectName('title')
        layout.addWidget(title)
        subtitle = QLabel('多个店铺，一次查询。条件即时生效，预设独立保存。'); subtitle.setObjectName('muted')
        layout.addWidget(subtitle)
        self.main_tabs = QTabWidget(); layout.addWidget(self.main_tabs, 1)
        sidebar = QWidget(); sidebar.setObjectName('sidebar')
        left = QVBoxLayout(sidebar); left.setContentsMargins(16, 12, 16, 16)
        self.section(left, '商家链接')
        self.urls = QPlainTextEdit(store.data['urls']); self.urls.setFixedHeight(100)
        self.urls.setPlaceholderText('每行一个商家链接；支持两平台混合输入')
        self.urls.setToolTip('支持 wzyp.cn、ldxp.cn、16688.com.cn 的 /shop/店铺编号 链接。自动去重，最多500家。')
        left.addWidget(self.urls)
        self.defaults_button = QPushButton('恢复 GPT_TEAM_5X 配置')
        self.defaults_button.clicked.connect(self.restore_builtin)
        left.addWidget(self.defaults_button)
        row = QHBoxLayout()
        self.start_button = self.button(row, '查询全部商家', self.start); self.start_button.setObjectName('primary')
        self.stop_button = self.button(row, '停止', self.stop); self.stop_button.setEnabled(False)
        left.addLayout(row)
        self.retry_button = QPushButton('仅重试未完成商家'); self.retry_button.clicked.connect(lambda: self.start(retry=True)); self.retry_button.setEnabled(False); left.addWidget(self.retry_button)
        search_box = QWidget(); search_box.setObjectName('searchConditions')
        search_layout = QVBoxLayout(search_box)
        self.section(search_layout, '搜索条件（固定查询）')
        form = QFormLayout(); form.setSpacing(9)
        self.fields = {}; self.search_fields = {}; self.filter_fields = {}
        for key, label, hint in [('any','包含任一','例如：5x,10x'),('all','同时包含','例如：team'),('exclude','排除关键词','例如：1x')]:
            edit = QLineEdit(); edit.setPlaceholderText(hint); self.fields[key] = edit; self.search_fields[key] = edit; form.addRow(label, edit)
        hint = QLabel('查询时固定使用；修改后点击“查询全部商家”才会更新商品集合。多个词用逗号分隔。'); hint.setObjectName('muted'); hint.setWordWrap(True)
        form.addRow(hint)
        search_layout.addLayout(form)
        clear_search = QPushButton('清空搜索词'); clear_search.clicked.connect(self.clear_search_conditions); search_layout.addWidget(clear_search)
        left.insertWidget(3, search_box)
        filter_box = QWidget(); filter_box.setObjectName('filterConditions')
        filter_layout = QVBoxLayout(filter_box); filter_layout.setAlignment(Qt.AlignTop)
        self.section(filter_layout, '筛选条件（本地即时）')
        form = QFormLayout(); form.setSpacing(9)
        for key, label, hint in [('filter_any','包含任一','例如：5x,10x'),('filter_all','同时包含','例如：team'),('filter_exclude','排除关键词','例如：1x')]:
            edit = QLineEdit(); edit.setPlaceholderText(hint); self.fields[key] = edit; self.filter_fields[key] = edit; form.addRow(label, edit)
        keyword_hint = QLabel('只影响右侧已获取结果，修改后立即生效，不会重新请求接口。'); keyword_hint.setWordWrap(True); keyword_hint.setObjectName('muted'); form.addRow(keyword_hint)
        price = QHBoxLayout()
        for key, hint_text in [('minimum','最低 / 不限'),('maximum','最高 / 不限')]:
            edit = QLineEdit(); edit.setPlaceholderText(hint_text); self.fields[key] = edit; self.filter_fields[key] = edit; price.addWidget(edit)
        form.addRow('价格范围', price)
        self.inclusive = QCheckBox('包含价格上限（≤）'); form.addRow('', self.inclusive)
        self.stock = QCheckBox('仅看有货'); form.addRow('', self.stock)
        quantity = QHBoxLayout()
        for key, placeholder in [('stock_min','最少 / 不限'),('stock_max','最多 / 不限')]:
            edit = QLineEdit(); edit.setPlaceholderText(placeholder); self.fields[key]=edit; self.filter_fields[key] = edit; quantity.addWidget(edit)
        form.addRow('库存数量',quantity)
        hint = QLabel('数量范围包含上下限；设置后排除未公开数量的商品。'); hint.setWordWrap(True); hint.setObjectName('muted'); form.addRow(hint)
        self.category = NoWheelComboBox(); self.category.setEditable(True); self.category.addItem(''); self.category.lineEdit().setPlaceholderText('全部分类 / 输入分类名称')
        self.category.setToolTip('空白表示全部分类。指定分类按名称精确匹配所有商家；未包含该分类的商家不会命中。')
        form.addRow('分类', self.category)
        self.sort = NoWheelComboBox(); self.sort.addItem('价格从低到高','asc'); self.sort.addItem('价格从高到低','desc'); self.sort.addItem('商家原始顺序','original')
        form.addRow('排序', self.sort)
        filter_layout.addLayout(form)
        clear_filter = QPushButton('清空筛选限制'); clear_filter.clicked.connect(self.clear_filter_conditions); filter_layout.addWidget(clear_filter)
        resetrow = QHBoxLayout(); self.button(resetrow,'清空条件', self.clear_filters); self.button(resetrow,'恢复自带条件',lambda: self.set_filters(DEFAULT_FILTERS)); left.addLayout(resetrow)
        self.section(left, '命名预设')
        self.presets = NoWheelComboBox(); left.addWidget(self.presets)
        row = QHBoxLayout(); self.button(row,'另存为',self.save_preset); self.button(row,'更新',self.update_preset); self.button(row,'重命名',self.rename_preset); self.button(row,'删除',self.delete_preset); left.addLayout(row)
        hint = QLabel('选中即恢复商家链接、搜索词及全部筛选条件。修改后点击“更新”保存到预设。'); hint.setObjectName('muted'); hint.setWordWrap(True); left.addWidget(hint)
        left.addStretch()
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setWidget(sidebar); scroll.setMinimumWidth(335)
        search_page = QWidget(); search_page_layout = QVBoxLayout(search_page); search_page_layout.setContentsMargins(0,0,0,0); search_page_layout.addWidget(scroll)
        filter_scroll = QScrollArea(); filter_scroll.setWidgetResizable(True); filter_scroll.setFrameShape(QFrame.NoFrame); filter_scroll.setMaximumHeight(300); filter_scroll.setWidget(filter_box)
        self.summary = QLabel('填写商家链接，开始第一次查询'); self.summary.setObjectName('section')
        self.search = QLineEdit(); self.search.setPlaceholderText('在结果中搜索商品名称或商家…')
        self.model = ProductsModel(); self.table = QTableView(); self.table.setModel(self.model)
        self.table.setAlternatingRowColors(True); self.table.setSelectionBehavior(QAbstractItemView.SelectRows); self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers); self.table.setWordWrap(False)
        self.table.verticalHeader().setVisible(False); self.table.verticalHeader().setDefaultSectionSize(38)
        for i, width in enumerate([260,72,68,92,96,72,72]): self.table.setColumnWidth(i,width)
        header = self.table.horizontalHeader(); header.setSectionResizeMode(0,QHeaderView.Stretch)
        for i in range(1, self.model.columnCount()): header.setSectionResizeMode(i,QHeaderView.Fixed)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        result_page = QWidget(); result_split = QSplitter(); result_split.setObjectName('resultSplit'); result_split.setOrientation(Qt.Horizontal); filter_scroll.setMaximumHeight(16777215); result_split.addWidget(filter_scroll)
        result_panel = QWidget(); result_layout_page = QVBoxLayout(result_panel); result_layout_page.setContentsMargins(10,10,10,10); result_layout_page.addWidget(self.summary); result_layout_page.addWidget(self.search); result_layout_page.addWidget(self.table,1)
        self.detail = QLabel('选中商品查看完整名称，双击打开商品页。'); self.detail.setWordWrap(True); self.detail.setMinimumHeight(34); self.detail.setTextFormat(Qt.PlainText); result_layout_page.addWidget(self.detail)
        row = QHBoxLayout(); self.button(row,'打开商品',self.open_product); self.button(row,'复制选中链接',self.copy_selected); self.button(row,'复制全部结果',self.copy_all); self.button(row,'导出 CSV',self.export); result_layout_page.addLayout(row)
        result_split.addWidget(result_panel); result_split.setSizes([345, 950]); result_page_layout = QVBoxLayout(result_page); result_page_layout.setContentsMargins(0,0,0,0); result_page_layout.addWidget(result_split)
        status_page = QWidget(); status_layout_page = QVBoxLayout(status_page); status_layout_page.setContentsMargins(10,10,10,10); self.log = QPlainTextEdit(); self.log.setReadOnly(True); self.log.setPlaceholderText('每个商家的查询状态会显示在这里；不自动访问网页。'); status_layout_page.addWidget(self.log)
        self.main_tabs.addTab(search_page,'搜索'); self.main_tabs.addTab(result_page,'结果与筛选'); self.main_tabs.addTab(status_page,'查询状态')
        self.notice = QLabel('就绪 · 数据仅在点击查询时刷新'); self.notice.setWordWrap(True); layout.addWidget(self.notice)
        self.setCentralWidget(root)
        self.timer = QTimer(self); self.timer.setSingleShot(True); self.timer.setInterval(250); self.timer.timeout.connect(self.changed)
        for field in self.filter_fields.values(): field.textChanged.connect(self.schedule)
        self.search.textChanged.connect(self.schedule); self.urls.textChanged.connect(self.schedule)
        self.category.currentTextChanged.connect(self.schedule); self.sort.currentIndexChanged.connect(self.schedule)
        self.inclusive.toggled.connect(self.schedule); self.stock.toggled.connect(self.schedule)
        self.presets.currentIndexChanged.connect(self.apply_preset)
        self.table.doubleClicked.connect(self.open_product)
        self.table.selectionModel().selectionChanged.connect(self.show_detail)
        QShortcut(QKeySequence('Ctrl+F'),self,activated=self.search.setFocus)
        QShortcut(QKeySequence('Ctrl+R'),self,activated=self.start)
        QShortcut(QKeySequence('Ctrl+C'),self.table,activated=self.copy_selected)
        self.set_filters(store.data['filters']); self.active_search = {k: self.fields[k].text().strip() for k in self.search_fields}; self.refresh_presets()
        self.loading = False
        if store.error: self.notice.setText(store.error)

    def section(self, layout, text):
        label = QLabel(text); label.setObjectName('section'); layout.addWidget(label)

    def button(self, layout, text, action):
        button = QPushButton(text); button.clicked.connect(action); layout.addWidget(button); return button

    def schedule(self, *_):
        if not self.loading: self.timer.start()

    def filters(self):
        return validate_filters({**{k:v.text().strip() for k,v in self.fields.items()},'stock':self.stock.isChecked(),
            'inclusive':self.inclusive.isChecked(),'category':self.category.currentText().strip(),
            'sort':self.sort.currentData(),'search':self.search.text().strip()})

    def set_filters(self, values):
        old = self.loading; self.loading = True
        for k,v in self.fields.items(): v.setText(values.get(k, ''))
        self.stock.setChecked(values['stock']); self.inclusive.setChecked(values['inclusive'])
        self.category.setCurrentText(values['category']); self.sort.setCurrentIndex(self.sort.findData(values['sort'])); self.search.setText(values['search'])
        self.loading = old
        if not old: self.changed()

    def clear_search_conditions(self):
        self.set_filters(dict(self.filters(), any='', all='', exclude='', search=''))

    def clear_filter_conditions(self):
        self.set_filters(dict(self.filters(), filter_any='', filter_all='', filter_exclude='', minimum='', maximum='', inclusive=False, stock=False, category='', stock_min='', stock_max=''))

    def clear_filters(self):
        self.set_filters(dict(DEFAULT_FILTERS, any='', all='', exclude='', filter_any='', filter_all='', filter_exclude='', maximum='', minimum='', stock=False, category='', search=''))

    def persist(self, presets=None):
        data = copy.deepcopy(self.store.data)
        data.update(urls=self.urls.toPlainText(), filters=self.filters())
        if presets is not None: data['presets'] = presets
        self.store.write(data)

    def changed(self):
        try:
            self.render_results(); self.persist()
            self.notice.setText('条件已保存 · 结果即时筛选 · Ctrl+R 重新查询，Ctrl+F 搜索')
        except (ValueError,OSError) as exc: self.notice.setText(str(exc))

    def render_results(self):
        ordered = sorted(self.outcomes,key=lambda o: next((i for i,s in enumerate(self.shops) if s.url==o.shop.url),0))
        products = [p for o in ordered for p in o.products]
        current_filters = self.filters()
        current_filters.update(self.active_search)
        matches = filter_products(products,current_filters)
        key = lambda p: (p.shop_url, p.id)
        selected_keys = {key(p) for p in self.selected()}
        current = self.table.currentIndex()
        current_key = key(self.model.items[current.row()]) if current.isValid() else None
        top = self.table.rowAt(0)
        anchor = key(self.model.items[top]) if top >= 0 else None
        offset = self.table.rowViewportPosition(top) if top >= 0 else 0
        horizontal = self.table.horizontalScrollBar().value()
        selection = self.table.selectionModel(); selection.blockSignals(True)
        self.model.replace(matches)
        rows = {key(p):i for i,p in enumerate(matches)}
        restored = QItemSelection()
        for identity in selected_keys:
            if identity in rows:
                row = rows[identity]; restored.select(self.model.index(row,0),self.model.index(row,self.model.columnCount()-1))
        selection.select(restored,QItemSelectionModel.ClearAndSelect | QItemSelectionModel.Rows)
        if current_key in rows: selection.setCurrentIndex(self.model.index(rows[current_key],0),QItemSelectionModel.NoUpdate)
        if anchor in rows:
            self.table.scrollTo(self.model.index(rows[anchor],0),QAbstractItemView.PositionAtTop)
            if self.table.verticalScrollMode() == QAbstractItemView.ScrollPerPixel:
                bar = self.table.verticalScrollBar(); bar.setValue(bar.value()-offset)
        self.table.horizontalScrollBar().setValue(horizontal)
        selection.blockSignals(False)
        done = sum(o.complete for o in self.outcomes)
        state = '查询中' if self.worker is not None else '全部完成' if self.shops and done==len(self.shops) else '部分数据' if self.shops else '尚未查询'
        known = sum(p.stock_count for p in matches if p.stock_count is not None)
        unknown = sum(p.stock_count is None for p in matches)
        self.summary.setText(f'已公开库存合计 {known} 件' + (f' · {unknown}款数量未公开' if unknown else '') + '\n' + f'{len(matches)} 件命中 / {len(products)} 件已获取 · {done}/{len(self.shops)} 家完整 · {state}')
        if self.selected(): self.show_detail()
        else: self.detail.setText('选中商品查看完整名称，双击打开商品页。')

    def start(self, checked=False, retry=False):
        if self.worker is not None: return
        try:
            shops = parse_shops(self.urls.toPlainText()); self.filters(); self.active_search = {k: self.fields[k].text().strip() for k in self.search_fields}; self.persist()
        except (ValueError,OSError) as exc:
            self.notice.setText(str(exc)); return
        if retry:
            completed = {o.shop.url for o in self.outcomes if o.complete}
            pending = [s for s in shops if s.url not in completed]
            if not pending: self.notice.setText('没有未完成的商家。'); return
            self.outcomes = [o for o in self.outcomes if o.shop.url in {s.url for s in shops}]
        else:
            pending = shops; self.outcomes = []; self.statuses = {}
        self.timer.stop(); self.shops=shops
        self.statuses = {s.url:self.statuses.get(s.url,'等待查询') for s in shops}
        for s in pending: self.statuses[s.url]='等待查询'
        self.fetched_at=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self.worker=Worker(pending); self.worker.progress.connect(self.progress); self.worker.result.connect(self.received); self.worker.finished.connect(self.finished)
        self.retry_button.setEnabled(False)
        self.start_button.setEnabled(False); self.urls.setEnabled(False); self.defaults_button.setEnabled(False); self.stop_button.setEnabled(True)
        self.render_results(); self.update_log(); self.notice.setText('后台查询中，可继续调整筛选条件。'); self.worker.start()

    def progress(self,url,message):
        self.statuses[url]=message; self.update_log()

    def update_log(self):
        bar=self.log.verticalScrollBar(); position=bar.value(); following=position==bar.maximum()
        self.log.setPlainText('\n'.join(f'{url}  ·  {state}' for url,state in self.statuses.items()))
        bar.setValue(bar.maximum() if following else position)

    def received(self,outcome):
        previous = next((o for o in self.outcomes if o.shop.url==outcome.shop.url),None)
        if previous and not outcome.complete and len(outcome.products)<len(previous.products):
            outcome.products=previous.products; outcome.categories=previous.categories; outcome.shop_name=previous.shop_name
            outcome.fetched_at=previous.fetched_at
            outcome.error+='；保留此前未完整获取的数据'
        self.outcomes=[o for o in self.outcomes if o.shop.url!=outcome.shop.url]+[outcome]
        self.statuses[outcome.shop.url]=f'{outcome.shop_name} · {len(outcome.products)}件 · '+('完成' if outcome.complete else outcome.error)
        self.update_log()
        selected=self.category.currentText(); self.category.blockSignals(True)
        names=sorted({c for o in self.outcomes for c in o.categories}|{p.category for o in self.outcomes for p in o.products},key=norm)
        self.category.clear(); self.category.addItems(['']+names); self.category.setCurrentText(selected); self.category.blockSignals(False)
        try: self.render_results()
        except ValueError as exc: self.notice.setText(str(exc))

    def stop(self):
        if self.worker:
            self.worker.cancel.set(); self.stop_button.setEnabled(False); self.notice.setText('正在停止，等待当前网络请求结束；已获取数据将保留。')

    def finished(self):
        worker=self.worker; self.worker=None; worker.deleteLater()
        self.start_button.setEnabled(True); self.urls.setEnabled(True); self.defaults_button.setEnabled(True); self.stop_button.setEnabled(False)
        try: self.render_results()
        except ValueError as exc: self.notice.setText(str(exc))
        failures=sum(not o.complete for o in self.outcomes)
        self.retry_button.setEnabled(bool(failures))
        self.notice.setText(f'获取时间：{self.fetched_at} · '+(f'{failures}家未完整获取，请查看状态；结果可能不完整。' if failures else '所有商家获取完成。价格和库存以商品页为准。'))
        if self.close_pending: self.close()

    def refresh_presets(self,index=0):
        self.presets.blockSignals(True); self.presets.clear(); self.presets.addItem('选择预设，一键应用')
        self.presets.addItems([p['name'] for p in self.store.data['presets']]); self.presets.setCurrentIndex(index); self.presets.blockSignals(False)

    def restore_builtin(self):
        self.urls.setPlainText('\n'.join(DEFAULT_URLS))
        self.set_filters(DEFAULT_FILTERS)

    def apply_preset(self,index):
        if index>0:
            preset = self.store.data['presets'][index-1]
            self.urls.setPlainText(preset['urls'])
            self.set_filters(preset['filters'])

    def preset_name(self, initial=''):
        name, ok=QInputDialog.getText(self,'预设名称','输入名称（最多80字）',text=initial)
        name=name.strip()
        if not ok: return None
        if not name or len(name)>80: raise ValueError('预设名称需要1至80字。')
        return name

    def save_preset(self):
        try:
            filters=self.filters(); name=self.preset_name()
            if name is None: return
            presets=copy.deepcopy(self.store.data['presets'])
            if any(norm(p['name'])==norm(name) for p in presets): raise ValueError('名称已存在，请换一个名称或使用“更新”。')
            presets.append(dict(name=name,filters=filters,urls='\n'.join(s.url for s in parse_shops(self.urls.toPlainText())))); self.persist(presets); self.refresh_presets(len(presets)); self.notice.setText('预设已保存。')
        except (ValueError,OSError) as exc: self.notice.setText(str(exc))

    def update_preset(self):
        index=self.presets.currentIndex()-1
        if index<0: self.notice.setText('请先选择需要更新的预设。'); return
        try:
            presets=copy.deepcopy(self.store.data['presets']); presets[index]['filters']=self.filters(); presets[index]['urls']='\n'.join(s.url for s in parse_shops(self.urls.toPlainText())); self.persist(presets); self.notice.setText('预设已更新。')
        except (ValueError,OSError) as exc: self.notice.setText(str(exc))

    def rename_preset(self):
        index=self.presets.currentIndex()-1
        if index<0: self.notice.setText('请先选择需要重命名的预设。'); return
        try:
            presets=copy.deepcopy(self.store.data['presets']); name=self.preset_name(presets[index]['name'])
            if name is None: return
            if any(i!=index and norm(p['name'])==norm(name) for i,p in enumerate(presets)): raise ValueError('名称已存在。')
            presets[index]['name']=name; self.persist(presets); self.refresh_presets(index+1)
        except (ValueError,OSError) as exc: self.notice.setText(str(exc))

    def delete_preset(self):
        index=self.presets.currentIndex()-1
        if index<0: self.notice.setText('请先选择需要删除的预设。'); return
        presets=copy.deepcopy(self.store.data['presets'])
        if QMessageBox.question(self,'删除预设',f'删除“{presets[index]["name"]}”？')!=QMessageBox.Yes: return
        try:
            presets.pop(index); self.persist(presets); self.refresh_presets()
        except (ValueError,OSError) as exc: self.notice.setText(str(exc))

    def selected(self):
        return [self.model.items[i.row()] for i in sorted(self.table.selectionModel().selectedRows(),key=lambda i:i.row())]

    def show_detail(self,*_):
        rows=self.selected()
        if rows: self.detail.setText(rows[0].name+'\n'+rows[0].shop_name+' · '+rows[0].url)

    def open_product(self,*_):
        rows=self.selected()
        if rows: QDesktopServices.openUrl(QUrl(rows[0].url))
        else: self.notice.setText('请先选中一个商品。')

    def copy_selected(self):
        rows=self.selected()
        if rows: QApplication.clipboard().setText('\n'.join(p.url for p in rows)); self.notice.setText(f'已复制{len(rows)}个商品链接。')
        else: self.notice.setText('请先选中商品，可按 Ctrl / Shift 多选。')

    def copy_all(self):
        if not self.model.items: self.notice.setText('当前没有筛选结果。'); return
        QApplication.clipboard().setText('\n'.join(f'{p.name}\t{p.price if p.price is not None else "价格未知"}\t{p.shop_name}\t{p.url}' for p in self.model.items)); self.notice.setText(f'已复制{len(self.model.items)}条结果。')

    def export(self):
        if not self.model.items: self.notice.setText('当前没有筛选结果。'); return
        path,_=QFileDialog.getSaveFileName(self,'导出当前筛选结果','筛选结果.csv','CSV 文件 (*.csv)',options=QFileDialog.DontUseNativeDialog)
        if not path: return
        if not path.lower().endswith('.csv'): path+='.csv'
        try:
            export_csv(path,self.model.items,self.outcomes,self.fetched_at); self.notice.setText(f'已导出{len(self.model.items)}条结果：{path}')
        except OSError as exc: self.notice.setText(f'导出失败：{exc}')

    def closeEvent(self,event):
        if self.worker is not None:
            self.close_pending=True; self.stop(); event.ignore(); return
        self.timer.stop()
        try: self.persist()
        except (ValueError,OSError): pass
        event.accept()


def main():
    diagnostic = len(sys.argv)>2 and sys.argv[1]=='--diagnose'
    if diagnostic: os.environ['QT_QPA_PLATFORM']='offscreen'
    app=QApplication(sys.argv); apply_theme(app)
    directory=Path(os.getenv('LOCALAPPDATA',str(Path.home()))) / 'MerchantFilter'
    if diagnostic:
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            window=Window(Store(tmp)); window.show(); app.processEvents()
            Path(sys.argv[2]).write_text(json.dumps({'ready':True,'widgets':len(window.findChildren(QWidget))}),encoding='utf-8'); window.close()
        return
    directory.mkdir(parents=True,exist_ok=True)
    configure_cooldowns(directory)
    lock=QLockFile(str(directory/'app.lock'))
    if not lock.tryLock(100):
        QMessageBox.information(None,'商家联合筛选器','程序已在运行，请切换到已打开的窗口。'); return
    window=Window(Store(directory)); window.show(); app.exec(); lock.unlock()


if __name__=='__main__': main()
