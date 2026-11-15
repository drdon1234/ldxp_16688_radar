"""商品查询、筛选和本地存储；不操作浏览器，不调用交易接口。"""
from __future__ import annotations

import csv
import json
import math
import os
import re
import tempfile
import threading
import time
import unicodedata
from dataclasses import asdict, dataclass, field
from datetime import datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import quote, urlsplit

from PySide6.QtCore import QByteArray, QEventLoop, QTimer, QUrl
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest
from shiboken6 import delete


class NetworkSession:
    """每个查询线程独占 Qt 网络会话，使用系统 TLS；硬超时限制单次请求。"""
    def __enter__(self):
        self.manager = QNetworkAccessManager()
        self.headers = {}
        self.last_request = 0
        return self

    def __exit__(self, *_):
        delete(self.manager)

    def post(self, url, json, timeout, allow_redirects):
        request = QNetworkRequest(QUrl(url))
        request.setHeader(QNetworkRequest.ContentTypeHeader, 'application/json')
        request.setAttribute(QNetworkRequest.RedirectPolicyAttribute, QNetworkRequest.ManualRedirectPolicy)
        for key, value in self.headers.items():
            request.setRawHeader(key.encode(), value.encode())
        request.setTransferTimeout(15000)
        reply = self.manager.post(request, QByteArray(__import__('json').dumps(json).encode('utf-8')))
        loop = QEventLoop()
        timer = QTimer(); timer.setSingleShot(True); timer.timeout.connect(reply.abort)
        reply.finished.connect(loop.quit)
        timer.start(15000)
        if not reply.isFinished(): loop.exec()
        timer.stop()
        status = reply.attribute(QNetworkRequest.HttpStatusCodeAttribute)
        body = bytes(reply.readAll())
        error = reply.errorString()
        raw_retry = bytes(reply.rawHeader('Retry-After')).decode('ascii',errors='ignore')
        delete(reply)
        if status is None:
            raise ValueError('网络请求失败或超时：' + error)
        class Response:
            status_code = status
            content = body
            retry_after = raw_retry
            def json(self):
                return __import__('json').loads(body)
        return Response()

DEFAULT_URLS = [
    'https://wzyp.cn/shop/OUJ1HPBV',
    'https://wzyp.cn/shop/oaoi',
    'https://wzyp.cn/shop/2VWX76A4',
    'https://wzyp.cn/shop/moyanovo',
    'https://www.16688.com.cn/shop/S943903',
    'https://www.16688.com.cn/shop/S396961',
    'https://www.16688.com.cn/shop/S104052',
    'https://wzyp.cn/shop/5H4X93E5',
    'https://wzyp.cn/shop/QHN4YVQP',
    'https://wzyp.cn/shop/Z65QS0QG',
    'https://wzyp.cn/shop/mirage',
    'https://wzyp.cn/shop/youzhi',
    'https://www.16688.com.cn/shop/S967696',
    'https://wzyp.cn/shop/GUEOI7Z9',
    'https://wzyp.cn/shop/PAXOVOVJ',
    'https://wzyp.cn/shop/KIJSS7TJ',
    'https://wzyp.cn/shop/nailong888',
    'https://wzyp.cn/shop/XSMWW894',
    'https://www.16688.com.cn/shop/S335138',
    'https://wzyp.cn/shop/YA3NLPX6',
    'https://wzyp.cn/shop/NFCG5CVM',
    'https://www.16688.com.cn/shop/S461375',
    'https://wzyp.cn/shop/YUJI',
    'https://www.16688.com.cn/shop/S265669',
    'https://www.16688.com.cn/shop/S609525',
    'https://wzyp.cn/shop/2E2KPQD1',
    'https://wzyp.cn/shop/GU3XQH61',
    'https://www.16688.com.cn/shop/S414108',
    'https://wzyp.cn/shop/THSDTX79',
    'https://wzyp.cn/shop/FC6GCKGG',
    'https://wzyp.cn/shop/ton',
    'https://wzyp.cn/shop/lanyy',
    'https://wzyp.cn/shop/V4E0E6T7',
    'https://wzyp.cn/shop/TH52WUW7',
    'https://wzyp.cn/shop/7HVUEC3Y',
    'https://wzyp.cn/shop/S5UL3UHI',
    'https://wzyp.cn/shop/worgforde',
    'https://wzyp.cn/shop/B9KFCWFO',
    'https://wzyp.cn/shop/JYO0X15L',
    'https://wzyp.cn/shop/7LFUCYI0',
    'https://wzyp.cn/shop/4UOATQTU',
    'https://wzyp.cn/shop/ai888',
    'https://wzyp.cn/shop/qingwaAA',
    'https://wzyp.cn/shop/FAJMDFWV',
    'https://www.16688.com.cn/shop/S783117',
    'https://wzyp.cn/shop/M18V0XVF',
    'https://www.16688.com.cn/shop/S545395',
    'https://wzyp.cn/shop/FRNX1ZU8',
    'https://wzyp.cn/shop/DJFT26BF',
    'https://wzyp.cn/shop/hzapi',
    'https://wzyp.cn/shop/RRIM3VSF',
    'https://www.16688.com.cn/shop/S522379',
    'https://www.16688.com.cn/shop/S889034',
]
DEFAULT_FILTERS = {'any': '5x,10x', 'all': 'team', 'exclude': '1x, 网页, 不是5x, 不是10x', 'minimum': '', 'maximum': '35', 'inclusive': False, 'stock': True, 'category': '', 'search': '', 'sort': 'asc', 'stock_min': '', 'stock_max': ''}
DEFAULT_PRESET_NAME = 'GPT_TEAM_5X'
ALLOWED_HOSTS = {'wzyp.cn', 'www.wzyp.cn', 'ldxp.cn', 'www.ldxp.cn', '16688.com.cn', 'www.16688.com.cn'}


def norm(value):
    return unicodedata.normalize('NFKC', str(value)).casefold()


def number(value):
    if value is None or isinstance(value, bool) or value == '':
        return None
    try:
        n = float(value)
        return n if math.isfinite(n) else None
    except (ValueError, TypeError):
        return None


@dataclass(frozen=True)
class Shop:
    origin: str
    token: str
    platform: str

    @property
    def url(self):
        return f'{self.origin}/shop/{quote(self.token)}'


def parse_shops(text):
    shops, seen = [], set()
    for line in re.split(r'[\s,，;；]+', text.strip()):
        if not line:
            continue
        candidate = line if '://' in line else 'https://' + line
        u = urlsplit(candidate)
        if u.scheme not in ('http', 'https') or u.hostname not in ALLOWED_HOSTS or u.username or u.password or u.port:
            raise ValueError('不支持的商家链接：' + line)
        match = re.fullmatch(r'/shop/([A-Za-z0-9_-]+)(?:/[A-Za-z0-9_-]+)?/?', u.path)
        if not match:
            raise ValueError('请填写店铺链接（/shop/商家编号），不是商品链接：' + line)
        platform = '16688' if u.hostname.endswith('16688.com.cn') else '链动小铺'
        host = 'www.16688.com.cn' if platform == '16688' else u.hostname.removeprefix('www.')
        shop = Shop('https://' + host, match[1], platform)
        key = (platform, shop.token)
        if key not in seen:
            seen.add(key)
            shops.append(shop)
    if not shops:
        raise ValueError('请至少填写一个商家链接。')
    if len(shops) > 500:
        raise ValueError('一次最多查询500个商家，请分批查询。')
    return shops


@dataclass
class Product:
    id: str
    name: str
    price: float | None
    stock: bool | None
    category: str
    shop_name: str
    shop_url: str
    platform: str
    url: str
    stock_count: int | None = None


@dataclass
class Outcome:
    shop: Shop
    products: list[Product] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)
    shop_name: str = ''
    complete: bool = False
    error: str = ''
    fetched_at: str = ''


class Cancelled(Exception):
    pass


_rate_lock = threading.Lock()
_next_request = {}
_blocked_platforms = set()
_cooldowns = {}
_cooldown_path = None
_request_counts = {}


def configure_cooldowns(directory):
    global _cooldown_path
    _cooldown_path = Path(directory) / 'platform_cooldowns.json'
    if _cooldown_path.exists():
        try:
            data = json.loads(_cooldown_path.read_text(encoding='utf-8'))
            with _rate_lock:
                for key, value in data.items():
                    if key in ('链动小铺', '16688') and number(value) is not None:
                        _cooldowns[key] = float(value)
        except (OSError, ValueError, AttributeError):
            pass


def block_platform(shop, reason, seconds=900):
    with _rate_lock:
        _blocked_platforms.add(shop.platform)
        _cooldowns[shop.platform] = max(_cooldowns.get(shop.platform, 0), time.time() + seconds)
        if _cooldown_path is not None:
            try:
                _cooldown_path.parent.mkdir(parents=True, exist_ok=True)
                temporary = _cooldown_path.with_suffix('.tmp')
                temporary.write_text(json.dumps(_cooldowns), encoding='utf-8')
                os.replace(temporary, _cooldown_path)
            except OSError:
                pass
    raise ValueError(reason + '；已停止该平台后续请求，至少冷却15分钟；其他平台继续。冷却结束不代表限制已解除')


def reset_platform_limits():
    with _rate_lock:
        _blocked_platforms.clear()


def wait_for_platform(shop, cancel):
    # 所有店铺共享平台限速，商家数增加也不提高对平台的请求速率。
    while True:
        ensure_active(cancel)
        with _rate_lock:
            remaining = _cooldowns.get(shop.platform, 0) - time.time()
            if remaining > 0:
                raise ValueError(f'平台冷却中，还需约{math.ceil(remaining / 60)}分钟；本次跳过，不发送请求')
            if shop.platform in _blocked_platforms:
                raise ValueError('该平台已限制访问，本次查询已停止该平台后续请求；商家是否存在待核验')
            now = time.monotonic()
            delay = _next_request.get(shop.platform, 0) - now
            if delay <= 0:
                count = _request_counts.get(shop.platform, 0) + 1
                _request_counts[shop.platform] = count
                interval = 3.0 if shop.platform == '链动小铺' else 1.5
                _next_request[shop.platform] = now + (60 if count % 20 == 0 else interval)
                return
        cancel.wait(min(delay, .2))


def ensure_active(cancel):
    if cancel.is_set():
        raise Cancelled('已停止；该商家数据可能不完整')


def post(session, shop, path, payload, cancel):
    ensure_active(cancel)
    wait_for_platform(shop, cancel)
    # 同一店铺请求间隔，避免短时间翻页触发平台限流。
    delay = max(0, .35 - (time.monotonic() - getattr(session, 'last_request', 0)))
    if cancel.wait(delay):
        ensure_active(cancel)
    session.last_request = time.monotonic()
    response = session.post(shop.origin + path, json=payload, timeout=(5, 10), allow_redirects=False)
    ensure_active(cancel)
    if response.status_code != 200:
        if response.status_code in (403, 429):
            retry = getattr(response, 'retry_after', '')
            seconds = number(retry)
            if seconds is None and retry:
                try: seconds = parsedate_to_datetime(retry).timestamp() - time.time()
                except (ValueError, TypeError, OverflowError): pass
            block_platform(shop, f'平台限制访问（HTTP {response.status_code}）', max(900, seconds or 0))
        raise ValueError(f'接口返回HTTP {response.status_code}')
    try:
        result = response.json()
    except ValueError as exc:
        block_platform(shop, '接口返回非JSON内容，可能是验证页或服务异常')
    if not isinstance(result, dict) or result.get('code') != 1:
        message = str(result.get('msg', '接口查询失败') if isinstance(result, dict) else '接口结构异常')[:180]
        if any(word in message for word in ('频繁', '验证码', '访问受限', '风控', '请求过多')):
            block_platform(shop, message)
        raise ValueError(message)
    return result.get('data')


def parse_product(raw, shop, shop_name, categories):
    if not isinstance(raw, dict):
        raise ValueError('商品结构异常')
    is16688 = shop.platform == '16688'
    identifier = raw.get('goods_no' if is16688 else 'goods_key')
    if not isinstance(identifier, str) or not identifier or not isinstance(raw.get('name'), str):
        raise ValueError('商品缺少编号或名称')
    count = number(raw.get('stock_available_quantity') if is16688 else (raw.get('extend') or {}).get('stock_count'))
    stock = count > 0 if count is not None else None
    if is16688:
        state = raw.get('stock_available_status')
        if state == 'out':
            stock = False
        elif state in ('low', 'normal', 'high', ''):
            stock = True
        category = categories.get(str(raw.get('goods_category_no') or ''), '未分类')
    else:
        category = str((raw.get('category') or {}).get('name') or '未分类')
        shop_name = str((raw.get('user') or {}).get('nickname') or shop_name)
    return Product(identifier, raw['name'], number(raw.get('price')), stock, category,
                   shop_name, shop.url, shop.platform,
                   shop.origin + ('/goods/' if is16688 else '/item/') + quote(identifier, safe=''),
                   int(count) if count is not None and count >= 0 and count.is_integer() else None)


def fetch_shop(shop, cancel, progress=lambda *_: None, session_factory=NetworkSession):
    outcome = Outcome(shop=shop, shop_name=shop.token)
    seen = set()
    try:
        with session_factory() as session:
            session.headers.update({'User-Agent': 'MerchantFilter/1.0', 'Accept': 'application/json'})
            if shop.platform == '16688':
                detail = post(session, shop, '/shopApi/shop/detail', {'shop_no': shop.token}, cancel)
                canonical = detail.get('shop_no') if isinstance(detail, dict) else None
                if not isinstance(canonical, str) or not canonical:
                    raise ValueError('店铺资料结构异常')
                outcome.shop_name = str(detail.get('name') or shop.token)
                categories = post(session, shop, '/shopApi/goodsCategory/list', {'shop_no': canonical}, cancel)
                if not isinstance(categories, list):
                    raise ValueError('分类结构异常')
                lookup = {str(c['goods_category_no']): str(c['name']) for c in categories}
                outcome.categories = list(lookup.values()) + ['未分类']
                data = post(session, shop, '/shopApi/goods/list', {'shop_no': canonical, 'goods_category_no': '', 'keywords': '', 'sort': 'default'}, cancel)
                if not isinstance(data, dict) or not isinstance(data.get('list'), list):
                    raise ValueError('商品列表结构异常')
                for raw in data['list']:
                    item = parse_product(raw, shop, outcome.shop_name, lookup)
                    if item.id in seen:
                        raise ValueError('商品编号重复，请重新查询')
                    seen.add(item.id)
                    outcome.products.append(item)
            else:
                categories = post(session, shop, '/shopApi/Shop/categoryList', {'token': shop.token, 'goods_type': 'card'}, cancel)
                if not isinstance(categories, list):
                    raise ValueError('分类结构异常')
                outcome.categories = [str(c['name']) for c in categories if c.get('id') != 0]
                expected = None
                for current in range(1, 1001):
                    progress(shop.url, f'第{current}页 · 已获取{len(outcome.products)}件')
                    data = post(session, shop, '/shopApi/Shop/goodsList', {'token': shop.token, 'goods_type': 'card', 'category_id': 0, 'keywords': '', 'current': current, 'pageSize': 20}, cancel)
                    total = number(data.get('total')) if isinstance(data, dict) else None
                    if not isinstance(data, dict) or not isinstance(data.get('list'), list) or total is None or total < 0 or int(total) != total:
                        raise ValueError('商品分页结构异常')
                    if expected is not None and total != expected:
                        raise ValueError('查询期间商品总数发生变化，请重新查询')
                    expected = total
                    page_items = [parse_product(raw, shop, outcome.shop_name, {}) for raw in data['list']]
                    page_ids = [p.id for p in page_items]
                    if len(set(page_ids)) != len(page_ids) or seen.intersection(page_ids):
                        raise ValueError('分页商品编号重复，请重新查询')
                    seen.update(page_ids)
                    outcome.products.extend(page_items)
                    if page_items:
                        outcome.shop_name = page_items[0].shop_name
                    if len(outcome.products) == total:
                        break
                    if not page_items or len(outcome.products) > total:
                        raise ValueError('分页数据与总数不一致')
                else:
                    raise ValueError('达到分页保护上限')
            ensure_active(cancel)
            outcome.complete = True
    except Exception as exc:
        outcome.error = str(exc)[:300] or type(exc).__name__
    outcome.fetched_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    return outcome


def validate_filters(values):
    f = dict(DEFAULT_FILTERS, **{k: v for k, v in values.items() if k in DEFAULT_FILTERS})
    for key, default in DEFAULT_FILTERS.items():
        if not isinstance(f[key], type(default)):
            raise ValueError('筛选条件格式错误：' + key)
    for key in ('minimum', 'maximum'):
        if f[key] and (number(f[key]) is None or number(f[key]) < 0):
            raise ValueError('价格必须是非负数字，留空表示不限')
    if f['minimum'] and f['maximum'] and float(f['minimum']) > float(f['maximum']):
        raise ValueError('最低价格不能高于最高价格')
    for key in ('stock_min', 'stock_max'):
        if f[key] and (number(f[key]) is None or number(f[key]) < 0 or not number(f[key]).is_integer()):
            raise ValueError('库存数量必须是非负整数，留空表示不限')
    if f['stock_min'] and f['stock_max'] and int(float(f['stock_min'])) > int(float(f['stock_max'])):
        raise ValueError('最低库存不能高于最高库存')
    if f['sort'] not in ('asc', 'desc', 'original'):
        raise ValueError('排序条件不正确')
    return f


def filter_products(products, values):
    f = validate_filters(values)
    words = lambda s: [norm(x.strip()) for x in re.split(r'[,，;；|\n]+', s) if x.strip()]
    any_words, all_words, exclude = words(f['any']), words(f['all']), words(f['exclude'])
    found = []
    for item in products:
        name = norm(item.name)
        if any_words and not any(k in name for k in any_words):
            continue
        if not all(k in name for k in all_words) or any(k in name for k in exclude):
            continue
        if f['stock'] and item.stock is not True:
            continue
        if f['category'] and norm(f['category'].strip()) != norm(item.category.strip()):
            continue
        if f['search'] and norm(f['search']) not in norm(item.name + ' ' + item.shop_name):
            continue
        if f['minimum'] and (item.price is None or item.price < float(f['minimum'])):
            continue
        if f['maximum'] and (item.price is None or (item.price > float(f['maximum']) if f['inclusive'] else item.price >= float(f['maximum']))):
            continue
        if f['stock_min'] and (item.stock_count is None or item.stock_count < int(float(f['stock_min']))):
            continue
        if f['stock_max'] and (item.stock_count is None or item.stock_count > int(float(f['stock_max']))):
            continue
        found.append(item)
    if f['sort'] != 'original':
        direction = -1 if f['sort'] == 'desc' else 1
        found.sort(key=lambda p: (p.price is None, (p.price or 0) * direction))
    return found


def export_csv(path, products, outcomes, fetched_at):
    complete = {o.shop.url: o.complete for o in outcomes}
    times = {o.shop.url: o.fetched_at or fetched_at for o in outcomes}
    def safe(value):
        s = str(value)
        return "'" + s if re.match(r'^\s*[=+@-]', s) else s
    with open(path, 'w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.writer(handle)
        writer.writerow(['商品名称','价格（元）','库存状态','库存数量','分类','商家','平台','商品链接','该商家数据完整','获取时间'])
        for p in products:
            writer.writerow([safe(v) for v in [p.name, p.price if p.price is not None else '', '有货' if p.stock else '缺货' if p.stock is False else '未识别', p.stock_count if p.stock_count is not None else '未公开', p.category, p.shop_name, p.platform, p.url, '是' if complete.get(p.shop_url, False) else '否', times.get(p.shop_url,fetched_at)]])


class Store:
    def __init__(self, directory):
        self.path = Path(directory) / 'settings.json'
        self.error = ''
        self.data = {'urls': '\n'.join(DEFAULT_URLS), 'filters': dict(DEFAULT_FILTERS), 'presets': [dict(name=DEFAULT_PRESET_NAME, urls='\n'.join(DEFAULT_URLS), filters=dict(DEFAULT_FILTERS))]}
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding='utf-8'))
                if not isinstance(data, dict) or not isinstance(data.get('urls'), str) or not isinstance(data.get('presets'), list):
                    raise ValueError('配置结构错误')
                data['filters'] = validate_filters(data.get('filters', {}))
                names = set()
                for p in data['presets']:
                    if not isinstance(p, dict) or not isinstance(p.get('name'), str) or not p['name'].strip() or norm(p['name']) in names:
                        raise ValueError('预设结构或名称错误')
                    names.add(norm(p['name']))
                    p['filters'] = validate_filters(p['filters'])
                    p.setdefault('urls', data['urls'])
                    if not isinstance(p['urls'], str): raise ValueError('预设商家链接格式错误')
                self.data = data
            except Exception as exc:
                self.error = f'配置读取失败，原文件未被覆盖：{exc}'

    def write(self, data):
        if self.error:
            raise ValueError(self.error)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix='settings-', suffix='.tmp', dir=self.path.parent)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as handle:
                json.dump(data, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
            self.data = json.loads(json.dumps(data))
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
