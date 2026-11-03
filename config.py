import os
import json

# ── Telegram API ────────────────────────────────────────
API_ID    = int(os.environ.get('API_ID',    '30949016'))
API_HASH  =     os.environ.get('API_HASH',  '29610b037ec08cccfcc219057143a818')
BOT_TOKEN =     os.environ.get('BOT_TOKEN', '8715573932:AAEDYrrJ2DOmyoJI--Zp0lwrjGte9nPq9RU')
TG_API    = f"https://api.telegram.org/bot{BOT_TOKEN}"

# ── Brand ───────────────────────────────────────────────
BOT_BRAND      = "𝑶𝑮𝑮𝒀'𝑺 𝑷𝑹𝑰𝑴𝑬 𝑩𝑶𝑻"
OWNER_NAME     = '𝑶𝑮𝑮𝒀 𝑷𝑹𝑶𝑶'
OWNER_USERNAME = 'oggyproo'
OWNER_ID       = 8919487892
DEV_LINE       = f'💻 <b>Dev</b>  »  <a href="https://t.me/{OWNER_USERNAME}">{OWNER_NAME}</a>'

# ── Runtime ─────────────────────────────────────────────
MASS_WORKERS = int(os.environ.get('MASS_WORKERS', '60'))

# ── Files ───────────────────────────────────────────────
_ADMIN_FILE             = os.path.join(os.path.dirname(__file__), 'admin.json')
PREMIUM_FILE            = 'premium.txt'
SITES_FILE              = 'sites.txt'
PROXY_FILE              = 'proxy.txt'
USER_PROXY_FILE         = 'user_proxies.json'
USER_POOL_FILE          = 'user_pool.json'
API_ENDPOINTS_FILE      = 'api_endpoints.json'
GC_CONFIG_FILE          = 'gc_config.json'
KEYS_FILE               = 'keys.json'

# ── Defaults ────────────────────────────────────────────
DEFAULT_API_ENDPOINTS = ["https://check.yzio.app"]
KEY_PREFIX            = "OGGY-PROO"

LIMITS = {
    "admin":   100000,
    "premium": 5000,
}

# ── Admin helpers ───────────────────────────────────────
_DEFAULT_ADMINS = (
    {int(x.strip()) for x in os.environ.get('ADMIN_ID', '').split(',') if x.strip().isdigit()}
    | ({OWNER_ID} if OWNER_ID else set())
)

def _load_admin_ids() -> set:
    try:
        with open(_ADMIN_FILE) as f:
            data = json.load(f)
            ids  = data.get('admin_ids', [])
            return (set(ids) | _DEFAULT_ADMINS) if ids else _DEFAULT_ADMINS
    except Exception:
        return _DEFAULT_ADMINS

def _save_admin_ids(ids: set):
    try:
        with open(_ADMIN_FILE) as f:
            data = json.load(f)
    except Exception:
        data = {}
    data['admin_ids'] = list(ids)
    with open(_ADMIN_FILE, 'w') as f:
        json.dump(data, f)

ADMIN_IDS = _load_admin_ids()
ADMIN_ID  = OWNER_ID
