from telethon import TelegramClient, events, Button
from telethon.tl.custom.message import Message as _TLMessage
import asyncio
import itertools
import aiofiles
import os
import random
import time
import json
import re

import config
from config import (
    API_ID, API_HASH, BOT_TOKEN,
    BOT_BRAND, OWNER_NAME, OWNER_USERNAME, OWNER_ID, DEV_LINE,
    PREMIUM_FILE, SITES_FILE, PROXY_FILE, USER_PROXY_FILE, USER_POOL_FILE,
    ADMIN_IDS, ADMIN_ID, _DEFAULT_ADMINS, _save_admin_ids,
    LIMITS, MASS_WORKERS,
)
from emojis import pe, SEP
from keyboards import (
    _raw_post, raw_send, raw_edit, nav_edit,
    rows_main, rows_gates, rows_proxy, rows_admin, rows_admin_users,
    rows_admin_sites, rows_admin_proxy_pool, rows_owner_api_eps, rows_owner_keys, rows_owner_gc,
    rows_stop, _get_chat_member,
)
from storage import (
    user_proxies, user_pool_enabled,
    load_user_proxies, save_user_proxies,
    load_user_pool, save_user_pool,
    get_user_proxy_list, set_user_proxies, remove_user_proxy,
    get_file_lines, load_premium_users, load_sites, load_proxies,
    is_admin, is_premium, get_user_limit,
    get_proxies_for_user, extract_cc, make_progress_bar,
    load_gc_config, save_gc_config,
    load_keys, save_keys, generate_key, redeem_key, list_keys,
)
from bin_db import get_bin_info, load_bins
from cards import build_result_card, checker_line
from check_engine import (
    check_card_with_retry, test_proxy, test_site, get_proxy_ip,
    clear_session_bad_sites, clear_error_log,
    load_api_endpoints, save_api_endpoints,
)
from extra_gates import check_st1, check_st5, check_stripe_auth
from keyboards import _send_notification, _pin_message_botapi

from datetime import datetime

bot = TelegramClient('checker_bot', API_ID, API_HASH).start(bot_token=BOT_TOKEN)

active_sessions: dict = {}
pending_checks:  dict = {}

_orig_send_message = bot.send_message
_orig_edit_message = bot.edit_message
import re as _re

def _strip_tg_emoji(text):
    if not text:
        return text
    return _re.sub(r'<tg-emoji[^>]*>([^<]*)</tg-emoji>', r'\1', text)

def _is_doc_invalid(e):
    s = str(e).upper()
    return 'DOCUMENT_INVALID' in s or 'FILE_REFERENCE_INVALID' in s

_orig_tl_edit = _TLMessage.edit

async def _safe_tl_edit(self, *args, **kwargs):
    kwargs.setdefault('link_preview', False)
    try:
        return await _orig_tl_edit(self, *args, **kwargs)
    except Exception as e:
        if _is_doc_invalid(e):
            new_args = list(args)
            if new_args and isinstance(new_args[0], str):
                new_args[0] = _strip_tg_emoji(new_args[0])
            if 'text' in kwargs:
                kwargs['text'] = _strip_tg_emoji(kwargs['text'])
            if 'message' in kwargs and isinstance(kwargs['message'], str):
                kwargs['message'] = _strip_tg_emoji(kwargs['message'])
            return await _orig_tl_edit(self, *new_args, **kwargs)
        raise

_TLMessage.edit = _safe_tl_edit

async def _send_message_no_preview(*args, **kwargs):
    kwargs.setdefault('link_preview', False)
    try:
        return await _orig_send_message(*args, **kwargs)
    except Exception as e:
        if _is_doc_invalid(e):
            if len(args) >= 2 and isinstance(args[1], str):
                args = (args[0], _strip_tg_emoji(args[1])) + args[2:]
            if 'message' in kwargs and isinstance(kwargs['message'], str):
                kwargs['message'] = _strip_tg_emoji(kwargs['message'])
            return await _orig_send_message(*args, **kwargs)
        raise

async def _edit_message_no_preview(*args, **kwargs):
    kwargs.setdefault('link_preview', False)
    try:
        return await _orig_edit_message(*args, **kwargs)
    except Exception as e:
        if _is_doc_invalid(e):
            if len(args) >= 3 and isinstance(args[2], str):
                args = args[:2] + (_strip_tg_emoji(args[2]),) + args[3:]
            if 'text' in kwargs and isinstance(kwargs['text'], str):
                kwargs['text'] = _strip_tg_emoji(kwargs['text'])
            if 'message' in kwargs and isinstance(kwargs['message'], str):
                kwargs['message'] = _strip_tg_emoji(kwargs['message'])
            return await _orig_edit_message(*args, **kwargs)
        raise

bot.send_message = _send_message_no_preview
bot.edit_message = _edit_message_no_preview

# ═══════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════
async def get_display_name(uid):
    try:
        entity = await bot.get_entity(uid)
        name   = getattr(entity, 'first_name', None) or ''
        lname  = getattr(entity, 'last_name',  None) or ''
        full   = (name + ' ' + lname).strip()
        return full if full else str(uid)
    except:
        return str(uid)

async def get_user_info(uid):
    try:
        entity   = await bot.get_entity(uid)
        name     = getattr(entity, 'first_name', None) or str(uid)
        username = getattr(entity, 'username', None)
        return name, username
    except:
        return str(uid), None

def _is_3ds(msg: str) -> bool:
    m = msg.lower()
    return any(x in m for x in ('3d secure', '3ds', 'authentication required', 'otp required'))

def _is_insuf(msg: str) -> bool:
    return 'insufficient' in msg.lower()

def _normalize_extra(result: dict, gate_key: str, card: str) -> dict:
    """Convert extra_gates dict to standard result format."""
    s = result.get('Status', 'Error')
    if 'Charged' in s:
        status = 'Charged'
    elif 'Approved' in s:
        status = 'Approved'
    elif 'Declined' in s:
        status = 'Dead'
    else:
        status = 'Dead'

    gateway_map = {
        'st1':  'Stripe 1$ (FormStack)',
        'st5':  'Stripe 5$ (GiveWP)',
        'auth': 'Stripe Auth2 $0 (WooCommerce)',
    }
    price_map = {'st1': '$1.00', 'st5': '$5.00', 'auth': '$0.00'}

    return {
        'card':        card,
        'status':      status,
        'message':     result.get('Response', ''),
        'gateway':     gateway_map.get(gate_key, '-'),
        'price':       price_map.get(gate_key, '-'),
        'receipt_url': '',
        'time':        0,
    }

# ═══════════════════════════════════════════════════════
# GC forwarding
# ═══════════════════════════════════════════════════════
def _mask_card(card: str) -> str:
    parts = card.split('|')
    if len(parts) != 4:
        return card
    pan, mm, yy, cvv = parts
    return pan[:6] + 'x' * (len(pan) - 10) + pan[-4:] + f'|{mm}|{yy}|***'

async def _forward_charged(result, gate_name, user_id):
    cfg = load_gc_config()
    user_name, _ = await get_user_info(user_id)

    private_gc = cfg.get('private_gc')
    if private_gc:
        msg = pe(
            f"💎 <b>CHARGED  —  {gate_name}</b>\n"
            f"<b>{SEP}</b>\n"
            f"🃏 <b>Card</b>      »  <code>{result['card']}</code>\n"
            f"🌐 <b>Gateway</b>   »  {result.get('gateway', '-')}\n"
            f"💵 <b>Amount</b>    »  {result.get('price', '-')}\n"
            f"💬 <b>Response</b>  »  {result.get('message', '-')}\n"
            f"<b>{SEP}</b>\n"
            f"👤 <b>By</b>  »  {user_name} (<code>{user_id}</code>)\n"
            f"{DEV_LINE}"
        )
        try:
            await bot.send_message(int(private_gc), msg, parse_mode='html')
        except:
            pass

    masked = _mask_card(result['card'])
    for key, label in [('public_gc', 'Public GC'), ('public_channel', 'Public Channel')]:
        target = cfg.get(key)
        if target:
            msg = pe(
                f"💎 <b>CHARGED  —  {gate_name}</b>\n"
                f"<b>{SEP}</b>\n"
                f"🃏 <code>{masked}</code>\n"
                f"🌐 {result.get('gateway', '-')}\n"
                f"💵 {result.get('price', '-')}\n"
                f"<b>{SEP}</b>\n"
                f"👤 {user_name}"
            )
            try:
                await bot.send_message(int(target), msg, parse_mode='html')
            except:
                pass

async def _log_to_gc(result, gate_name, user_id):
    cfg = load_gc_config()
    log_gc = cfg.get('log_gc')
    if not log_gc:
        return
    user_name, _ = await get_user_info(user_id)
    icon = {'Charged': '💎', 'Approved': '✅', 'Dead': '❌'}.get(result.get('status'), '❓')
    msg = pe(
        f"{icon} <b>{result.get('status', '?').upper()}  —  {gate_name}</b>\n"
        f"<b>{SEP}</b>\n"
        f"🃏 <code>{result['card']}</code>\n"
        f"💬 {result.get('message', '-')}\n"
        f"👤 {user_name} (<code>{user_id}</code>)"
    )
    try:
        await bot.send_message(int(log_gc), msg, parse_mode='html')
    except:
        pass

# ═══════════════════════════════════════════════════════
# Single check result
# ═══════════════════════════════════════════════════════
async def send_realtime_hit(user_id, result, hit_type):
    bin_info           = await get_bin_info(result['card'].split('|')[0])
    result['bin_info'] = bin_info
    name, username     = await get_user_info(user_id)
    checker_name       = name if username else str(user_id)
    msg    = build_result_card(result, bin_info, user_id, checker_name)
    msg_id = await asyncio.to_thread(_send_notification, user_id, msg)
    if msg_id and hit_type == "Charged":
        await asyncio.to_thread(_pin_message_botapi, user_id, msg_id)

async def send_insufficient_log(user_id, result):
    from cards import _clean_response
    card     = result['card']
    resp_msg = _clean_response(result.get('message', ''))
    await bot.send_message(
        user_id,
        pe(
            f"💸 <b>Insufficient Funds</b>\n"
            f"<b>{SEP}</b>\n"
            f"🃏 <b>Card</b>    »  <tg-spoiler>{card}</tg-spoiler>\n"
            f"💬 <b>Reason</b>  »  {resp_msg}\n"
            f"<b>{SEP}</b>\n"
            f"{DEV_LINE}"
        ),
        parse_mode='html'
    )

# ═══════════════════════════════════════════════════════
# Mass runner
# ═══════════════════════════════════════════════════════
async def update_mass_progress(user_id, message_id, results, checked, last_res=None, gate_name="Mass Check"):
    bar = make_progress_bar(checked, results['total'])
    latest = ""
    if last_res:
        st    = last_res['status']
        msg_r = last_res.get('message', '') or ''
        if st == 'Charged':
            se = "💎"; label = "CHARGED"
        elif st == 'Approved':
            se = "✅"; label = "APPROVED"
        elif _is_insuf(msg_r):
            se = "💸"; label = "Insufficient"
        elif _is_3ds(msg_r):
            se = "⚠️"; label = "3DS"
        else:
            se = "🚫"; label = "Declined"
        reason = msg_r[:45] if msg_r else label
        t = round(time.time() - results.get('last_card_time', time.time()), 2)
        latest = (
            f"\n<b>{SEP}</b>\n"
            f"⚡ <b>Last Result</b>\n"
            f"{se}  <tg-spoiler>{last_res['card']}</tg-spoiler>\n"
            f"💫  {reason}  ·  {t}s"
        )
    text = pe(
        f"<b>🔥 {gate_name}  —  Running</b>\n"
        f"<b>{SEP}</b>\n"
        f"📋 <b>Total</b>      »  {results['total']}\n"
        f"☄️ <b>Checked</b>   »  {checked}\n"
        f"💎 <b>Charged</b>   »  {len(results['charged'])}\n"
        f"✅ <b>Approved</b>  »  {len(results['approved'])}\n"
        f"⚠️ <b>3DS</b>       »  {len(results.get('tds', []))}\n"
        f"<code>{bar}</code>"
        f"{latest}"
    )
    await raw_edit(user_id, message_id, text, rows_stop())

def _file_row(label, r):
    gate  = r.get('gateway', 'Shopify')
    price = r.get('price', '-')
    bi    = r.get('bin_info')
    if bi:
        brand, btype, level, bank, country, flag = bi
        bank_line = f"  Bank    : {bank} | {country} {flag} | {brand} {btype} {level}\n"
    else:
        bank_line = ""
    return (
        f"  [{label}]\n"
        f"  CC      : {r['card']}\n"
        f"  Gateway : {gate}\n"
        f"  Amount  : {price}\n"
        f"  Message : {r.get('message','')[:80]}\n"
        + bank_line +
        f"  {'─'*36}\n"
    )

async def send_final_results(user_id, results, gate_name="Mass Check"):
    elapsed  = int(time.time() - results['start_time'])
    h, m, s  = elapsed // 3600, (elapsed % 3600) // 60, elapsed % 60
    bar      = make_progress_bar(results['total'], results['total'])
    ch_count = len(results['charged'])
    ap_count = len(results['approved'])
    td_count = len(results.get('tds', []))
    cname    = await get_display_name(user_id)
    time_fmt = f"{h}h {m}m {s}s" if h else (f"{m}m {s}s" if m else f"{s}s")
    summary  = pe(
        f"<b>🔥 {gate_name}  —  Complete</b>\n"
        f"<b>{SEP}</b>\n"
        f"<blockquote>"
        f"📋 <b>Total</b>      »  {results['total']}\n"
        f"💎 <b>Charged</b>   »  {ch_count}\n"
        f"✅ <b>Approved</b>  »  {ap_count}\n"
        f"⚠️ <b>3DS</b>       »  {td_count}\n"
        f"❌ <b>Dead</b>      »  {len(results.get('dead', []))}\n"
        f"<code>{bar}</code>"
        f"</blockquote>\n"
        f"<b>{SEP}</b>\n"
        f"⏱️ <b>Time</b>  »  {time_fmt}\n"
        f"<b>{SEP}</b>\n"
        f"{checker_line(user_id, cname)}\n"
        f"{DEV_LINE}"
    )
    await bot.send_message(user_id, summary, parse_mode='html')

    if results['charged']:
        D = "─" * 44
        lines = [f"{D}\n  {BOT_BRAND}  ◈  💎 CHARGED HITS\n{D}\n\n"]
        for r in results['charged']:
            lines.append(_file_row("💎 CHARGED", r))
        lines.append(f"\n  Charged  »  {ch_count}\n{D}\n")
        async with aiofiles.open("charged.txt", 'w') as f:
            await f.write("".join(lines))
        await bot.send_file(
            user_id, "charged.txt",
            caption=pe(f"💎 <b>Charged Hits  »  {ch_count}</b>\n{DEV_LINE}"),
            parse_mode='html'
        )
        try: os.remove("charged.txt")
        except: pass

    combo = results['approved'] + results.get('tds', [])
    if combo:
        D = "─" * 44
        lines = [f"{D}\n  {BOT_BRAND}  ◈  HITS FILE\n{D}\n\n"]
        if results['approved']:
            lines.append(f"  ── ✅ APPROVED  ({ap_count}) ────────────────────\n\n")
            for r in results['approved']:
                lines.append(_file_row("✅ APPROVED", r))
        if results.get('tds'):
            lines.append(f"\n  ── ⚠️  3DS  ({td_count}) ──────────────────────\n\n")
            for r in results['tds']:
                lines.append(_file_row("⚠️ 3DS", r))
        lines.append(f"\n{D}\n  Approved: {ap_count}  ·  3DS: {td_count}\n{D}\n")
        async with aiofiles.open("approved.txt", 'w') as f:
            await f.write("".join(lines))
        caption = pe(
            f"✅ <b>Hits File</b>\n"
            f"<b>{SEP}</b>\n"
            f"✅ <b>Approved</b>  »  {ap_count}\n"
            f"⚠️ <b>3DS</b>       »  {td_count}\n"
            f"{DEV_LINE}"
        )
        await bot.send_file(user_id, "approved.txt", caption=caption, parse_mode='html')
        try: os.remove("approved.txt")
        except: pass

    error_path = os.path.join(os.path.dirname(__file__), 'error.txt')
    try:
        async with aiofiles.open(error_path, 'r') as f:
            err_content = await f.read()
        err_lines = [l for l in err_content.strip().splitlines() if l.strip()]
        if err_lines:
            await bot.send_file(
                user_id, error_path,
                caption=pe(
                    f"❌ <b>Failed Cards  »  {len(err_lines)}</b>\n"
                    f"<b>{SEP}</b>\n"
                    f"⚠️ Cards that errored after all retries\n"
                    f"{DEV_LINE}"
                ),
                parse_mode='html'
            )
    except FileNotFoundError:
        pass
    except Exception:
        pass

async def run_mass_check(user_id, cards, progress_msg_id, gate_key="shopify", gate_name="Mass Check", concurrency=None):
    session_key = f"{user_id}_{progress_msg_id}"
    clear_session_bad_sites()
    clear_error_log()
    active_sessions[session_key] = {'paused': False}
    all_results = {
        'charged': [], 'approved': [], 'dead': [], 'tds': [],
        'total': len(cards), 'start_time': time.time(), 'last_card_time': time.time(),
    }

    proxies = get_proxies_for_user(user_id) or load_proxies()
    sites   = load_sites()

    # Gate dispatcher
    if gate_key == 'shopify':
        gate_fn = lambda c: check_card_with_retry(c, sites, proxies)
    elif gate_key == 'st1':
        gate_fn = lambda c: check_st1(c, random.choice(proxies) if proxies else None)
    elif gate_key == 'st5':
        gate_fn = lambda c: check_st5(c, random.choice(proxies) if proxies else None)
    elif gate_key == 'auth':
        gate_fn = lambda c: check_stripe_auth(c, random.choice(proxies) if proxies else None)
    else:
        gate_fn = lambda c: check_card_with_retry(c, sites, proxies)

    n_workers = concurrency or (MASS_WORKERS if gate_key == 'shopify' else 30)

    try:
        queue       = asyncio.Queue()
        last_update = [time.time()]
        for c in cards:
            queue.put_nowait(c)

        async def worker():
            while not queue.empty() and session_key in active_sessions:
                sess = active_sessions.get(session_key)
                if not sess:
                    break
                while sess.get('paused', False):
                    await asyncio.sleep(1)
                    sess = active_sessions.get(session_key)
                    if not sess:
                        return
                try:
                    card = queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
                t0 = time.time()
                try:
                    raw = await gate_fn(card)
                except Exception:
                    raw = {'Status': 'Error', 'Response': 'Exception', 'Card': card}

                if gate_key == 'shopify':
                    result = raw
                else:
                    result = _normalize_extra(raw, gate_key, card)
                result['time'] = round(time.time() - t0, 2)
                all_results['last_card_time'] = time.time()

                st    = result.get('status', '')
                msg_r = result.get('message', '') or ''

                if st == 'Charged':
                    bin_info = await get_bin_info(card.split('|')[0])
                    result['bin_info'] = bin_info
                    all_results['charged'].append(result)
                    await send_realtime_hit(user_id, result, 'Charged')
                    await _forward_charged(result, gate_name, user_id)
                elif st == 'Approved':
                    bin_info = await get_bin_info(card.split('|')[0])
                    result['bin_info'] = bin_info
                    all_results['approved'].append(result)
                    await send_realtime_hit(user_id, result, 'Approved')
                elif _is_3ds(msg_r):
                    bin_info = await get_bin_info(card.split('|')[0])
                    result['bin_info'] = bin_info
                    all_results['tds'].append(result)
                elif _is_insuf(msg_r):
                    all_results['approved'].append(result)
                    await send_insufficient_log(user_id, result)
                else:
                    all_results['dead'].append(result)

                await _log_to_gc(result, gate_name, user_id)

                checked = (len(all_results['charged']) + len(all_results['approved']) +
                           len(all_results['dead']) + len(all_results.get('tds', [])))
                now = time.time()
                if now - last_update[0] >= 3:
                    last_update[0] = now
                    try:
                        await update_mass_progress(user_id, progress_msg_id, all_results, checked, result, gate_name)
                    except Exception:
                        pass

        workers = [asyncio.create_task(worker()) for _ in range(min(n_workers, len(cards)))]
        await asyncio.gather(*workers)
    except Exception:
        pass
    finally:
        active_sessions.pop(session_key, None)
        await send_final_results(user_id, all_results, gate_name)

# ═══════════════════════════════════════════════════════
# Admin panel text
# ═══════════════════════════════════════════════════════
def _admin_panel_text():
    pcount  = len(load_premium_users())
    scount  = len(load_sites())
    prcount = len(load_proxies())
    return pe(
        f"<b>👑 Admin Panel</b>  —  <b>{BOT_BRAND}</b>\n"
        f"<b>{SEP}</b>\n"
        f"<blockquote>"
        f"🟢 <b>Status</b>      »  Online\n"
        f"👤 <b>Users</b>       »  {pcount} trusted\n"
        f"🌐 <b>Sites</b>        »  {scount} loaded\n"
        f"📡 <b>Proxy Pool</b>  »  {prcount} proxies"
        f"</blockquote>\n"
        f"<b>{SEP}</b>\n"
        f"{DEV_LINE}"
    )

# ═══════════════════════════════════════════════════════
# Force join
# ═══════════════════════════════════════════════════════
async def _check_force_join(uid) -> list:
    cfg = load_gc_config()
    req = cfg.get('required_channels', [])
    if not req:
        return []
    missing = []
    for ch in req:
        ok = await asyncio.to_thread(_get_chat_member, ch, uid)
        if not ok:
            missing.append(ch)
    return missing

# ═══════════════════════════════════════════════════════
# /start
# ═══════════════════════════════════════════════════════
@bot.on(events.NewMessage(pattern='/start'))
async def start(event):
    uid      = event.sender_id
    chat_id  = event.chat_id
    in_group = (chat_id != uid)

    if not in_group:
        try:
            rm_msg = await bot.send_message(uid, "\u200b", buttons=Button.clear())
            await asyncio.sleep(0.3)
            await bot.delete_messages(uid, rm_msg.id)
        except Exception:
            pass

    # Force join
    missing = await _check_force_join(uid)
    if missing and not is_admin(uid):
        btns = []
        for ch in missing:
            uname = ch if ch.startswith('@') else None
            if uname:
                btns.append([{"text": f"📢 Join {uname}", "url": f"https://t.me/{uname.lstrip('@')}"}])
        btns.append([{"text": "✅ I Joined", "callback_data": "check_join"}])
        text = pe(
            f"<b>🛡 Join Required</b>\n"
            f"<b>{SEP}</b>\n"
            f"Please join the required channel(s) to use the bot.\n"
            f"<b>{SEP}</b>\n"
            f"Then tap <b>✅ I Joined</b>."
        )
        await raw_send(uid, text, btns)
        return

    try:
        sender    = await event.get_sender()
        username  = f"@{sender.username}" if sender.username else f"ID:{uid}"
        firstname = sender.first_name or "User"
    except:
        username  = f"ID:{uid}"
        firstname = "User"

    lim = get_user_limit(uid)
    if is_admin(uid):
        status_icon = "👑"; status_line = "Admin"
    elif is_premium(uid):
        status_icon = "✅"; status_line = "Premium"
    else:
        status_icon = "🚫"; status_line = "No Access"

    text = pe(
        f"<b>⚡ Welcome, {firstname}!</b>\n"
        f"<b>{SEP}</b>\n"
        f"<blockquote>"
        f"👤 <b>User</b>     »  {username}\n"
        f"🆔 <b>ID</b>       »  <code>{uid}</code>\n"
        f"{status_icon} <b>Status</b>  »  {status_line}\n"
        f"📋 <b>Limit</b>   »  {lim if lim else '—'} cards/file"
        f"</blockquote>\n"
        f"<b>{SEP}</b>\n"
        f"Select an option below to get started.\n"
        f"<b>{SEP}</b>\n"
        f"{DEV_LINE}"
    )
    dest = chat_id if in_group else uid
    await raw_send(dest, text, rows_main(),
                   reply_to=event.message.id if in_group else None)

# ═══════════════════════════════════════════════════════
# /redeem
# ═══════════════════════════════════════════════════════
@bot.on(events.NewMessage(pattern=r'^/redeem(\s+.*)?$'))
async def redeem_cmd(event):
    uid = event.sender_id
    parts = event.message.text.strip().split(maxsplit=1)
    if len(parts) < 2:
        await event.reply(pe(
            f"🔑 <b>Redeem Key</b>\n"
            f"<b>{SEP}</b>\n"
            f"Usage: <code>/redeem OGGY-PROO-XXXX</code>"
        ), parse_mode='html')
        return
    key = parts[1].strip()
    ok, msg = redeem_key(key, uid)
    if not ok:
        await event.reply(pe(
            f"❌ <b>Redemption Failed</b>\n"
            f"<b>{SEP}</b>\n"
            f"{msg}"
        ), parse_mode='html')
        return
    # Add to premium
    curr = load_premium_users()
    if str(uid) not in curr:
        async with aiofiles.open(PREMIUM_FILE, 'a') as f:
            await f.write(f"{uid}\n")
    await event.reply(pe(
        f"✅ <b>Key Redeemed</b>\n"
        f"<b>{SEP}</b>\n"
        f"🎉 You now have premium access!\n"
        f"Use /start to open the dashboard.\n"
        f"<b>{SEP}</b>\n"
        f"{DEV_LINE}"
    ), parse_mode='html')

# ═══════════════════════════════════════════════════════
# Single-check helpers
# ═══════════════════════════════════════════════════════
async def _run_single_gate(event, card, gate_key, gate_name):
    uid = event.sender_id
    sites   = load_sites()
    proxies = get_proxies_for_user(uid) or load_proxies()

    if gate_key == 'shopify' and not sites:
        await event.reply(pe(f"❌ <b>No Sites Available</b>\n<b>{SEP}</b>\nContact the admin."), parse_mode='html')
        return
    if not proxies and gate_key == 'shopify':
        await event.reply(pe(f"❌ <b>No Proxy Configured</b>\n<b>{SEP}</b>\nUse <code>/setproxy</code>"), parse_mode='html')
        return

    smsg = await event.reply(
        pe(
            f"⚡ <b>Checking  —  {gate_name}...</b>\n"
            f"<b>{SEP}</b>\n"
            f"🃏 <tg-spoiler><code>{card}</code></tg-spoiler>\n"
            f"<b>{SEP}</b>\n"
            f"⏳ Please wait..."
        ),
        parse_mode='html',
    )
    try:
        t0 = time.time()
        if gate_key == 'shopify':
            result, (name, username) = await asyncio.gather(
                check_card_with_retry(card, sites, proxies),
                get_user_info(uid),
            )
            bin_info = await get_bin_info(card.split('|')[0])
        else:
            proxy = random.choice(proxies) if proxies else None
            if gate_key == 'st1':
                raw = await check_st1(card, proxy)
            elif gate_key == 'st5':
                raw = await check_st5(card, proxy)
            else:
                raw = await check_stripe_auth(card, proxy)
            result = _normalize_extra(raw, gate_key, card)
            bin_info = await get_bin_info(card.split('|')[0])
            name, username = await get_user_info(uid)

        cname = name if username else str(uid)
        result['time'] = round(time.time() - t0, 2)

        # log + forward
        await _log_to_gc(result, gate_name, uid)
        if result['status'] == 'Charged':
            await _forward_charged(result, gate_name, uid)

        resp = build_result_card(result, bin_info, uid, cname)
        await raw_edit(uid, smsg.id, resp, [])
        if result.get('status') == 'Charged':
            await asyncio.to_thread(_pin_message_botapi, uid, smsg.id)
    except Exception as e:
        await smsg.edit(pe(
            f"❌ <b>Check Failed</b>\n"
            f"<b>{SEP}</b>\n"
            f"⚠️ Error: <code>{e}</code>"
        ), parse_mode='html')

async def _run_mass_gate(event, cards, gate_key, gate_name):
    uid = event.sender_id
    if not cards:
        return
    limit = get_user_limit(uid)
    if len(cards) > limit:
        await event.reply(pe(
            f"⚠️ <b>Limit Applied</b>\n"
            f"<b>{SEP}</b>\n"
            f"File contains <b>{len(cards)}</b> cards.\n"
            f"Your limit: <b>{limit}</b> — first {limit} will be checked."
        ), parse_mode='html')
        cards = cards[:limit]

    text = pe(
        f"<b>🔥 {gate_name}  —  Starting</b>\n"
        f"<b>{SEP}</b>\n"
        f"📋 <b>Total</b>      »  {len(cards)}\n"
        f"☄️ <b>Checked</b>   »  0\n"
        f"💎 <b>Charged</b>   »  0\n"
        f"✅ <b>Approved</b>  »  0\n"
        f"⚠️ <b>3DS</b>       »  0\n"
        f"<code>{make_progress_bar(0, len(cards))}</code>"
    )
    msg_id = await raw_send(uid, text, rows_stop(), reply_to=event.message.id)
    if msg_id:
        asyncio.create_task(run_mass_check(uid, cards, msg_id, gate_key, gate_name))

# ═══════════════════════════════════════════════════════
# /sh /msh — Shopify
# ═══════════════════════════════════════════════════════
@bot.on(events.NewMessage(pattern=r'^/sh\s+'))
async def single_check(event):
    uid = event.sender_id
    if not is_premium(uid):
        await event.reply(pe(f"❌ <b>Access Denied</b>\n<b>{SEP}</b>\n🔒 Use /redeem to get access."), parse_mode='html')
        return
    cards = extract_cc(event.message.text.split(' ', 1)[1].strip())
    if not cards:
        await event.reply(pe(f"❌ <b>Invalid Format</b>\n<b>{SEP}</b>\nUsage:  <code>/sh card|mm|yy|cvv</code>"), parse_mode='html')
        return
    await _run_single_gate(event, cards[0], 'shopify', 'Shopify')

def _is_txt_file(e):
    if not e.file or e.via_bot_id:
        return False
    name = e.file.name or ''
    mime = e.file.mime_type or ''
    return name.endswith('.txt') or (not name and mime == 'text/plain')

@bot.on(events.NewMessage(func=_is_txt_file))
async def txt_detected(event):
    uid = event.sender_id
    if not is_premium(uid):
        await event.reply(pe(f"❌ <b>Access Denied</b>\n<b>{SEP}</b>\n🔒 Use /redeem to get access."), parse_mode='html')
        return
    sites   = load_sites()
    proxies = get_proxies_for_user(uid) or load_proxies()
    if not sites:
        await event.reply(pe(f"❌ <b>No Sites Configured</b>"), parse_mode='html')
        return
    if not proxies:
        await event.reply(pe(f"❌ <b>No Proxy Configured</b>\n<b>{SEP}</b>\nUse <code>/setproxy</code>"), parse_mode='html')
        return

    fp = await event.message.download_media()
    if not fp:
        await event.reply(pe(f"❌ <b>File download failed.</b>"), parse_mode='html')
        return
    async with aiofiles.open(fp, 'r', encoding='utf-8', errors='ignore') as f:
        content = await f.read()
    try: os.remove(fp)
    except: pass

    cards = extract_cc(content)
    if not cards:
        await event.reply(pe(f"❌ <b>No Cards Found</b>"), parse_mode='html')
        return

    pending_checks[uid] = {'cards': cards, 'gate': 'shopify'}
    preview_lines = "\n".join([f'⭐ <tg-spoiler>{c}</tg-spoiler>' for c in cards[:3]])
    more = f"\n<i>  ...and {len(cards)-3} more cards</i>" if len(cards) > 3 else ""
    text = pe(
        f"📂 <b>File Detected  —  Shopify</b>\n"
        f"<b>{SEP}</b>\n"
        f"📋 <b>Cards found:</b> <b>{len(cards)}</b>\n"
        f"<b>{SEP}</b>\n"
        f"{preview_lines}{more}\n"
        f"<b>{SEP}</b>\n"
        f"<b>🔥 Tap below to start checking</b>"
    )
    await raw_send(
        uid, text,
        [[{"text": "💳  Start Shopify Check", "callback_data": f"start_check_{uid}"}]],
        reply_to=event.message.id,
    )

@bot.on(events.NewMessage(pattern=r'^/msh$'))
async def mass_check_cmd(event):
    uid = event.sender_id
    if not is_premium(uid):
        await event.reply(pe(f"❌ <b>Access Denied</b>"), parse_mode='html')
        return
    if not event.reply_to_msg_id:
        await event.reply(pe(f"⚡ <b>How to Mass Check</b>\n<b>{SEP}</b>\nReply to a <code>.txt</code> file with <code>/msh</code>"), parse_mode='html')
        return
    reply = await event.get_reply_message()
    if not reply.file or not reply.file.name.endswith('.txt'):
        await event.reply(pe(f"❌ <b>Invalid File</b>"), parse_mode='html')
        return
    sites   = load_sites()
    proxies = get_proxies_for_user(uid) or load_proxies()
    if not sites or not proxies:
        await event.reply(pe(f"❌ <b>No sites/proxies configured.</b>"), parse_mode='html')
        return
    fp = await reply.download_media()
    async with aiofiles.open(fp, 'r', encoding='utf-8', errors='ignore') as f:
        content = await f.read()
    cards = extract_cc(content)
    try: os.remove(fp)
    except: pass
    if not cards:
        await event.reply(pe(f"❌ <b>No Valid Cards Found</b>"), parse_mode='html')
        return
    await _run_mass_gate(event, cards, 'shopify', 'Shopify')

# ═══════════════════════════════════════════════════════
# /st1 /mst1 — Stripe $1
# ═══════════════════════════════════════════════════════
@bot.on(events.NewMessage(pattern=r'^/st1\s+'))
async def single_st1(event):
    uid = event.sender_id
    if not is_premium(uid):
        await event.reply(pe(f"❌ <b>Access Denied</b>"), parse_mode='html'); return
    cards = extract_cc(event.message.text.split(' ', 1)[1].strip())
    if not cards:
        await event.reply(pe(f"❌ <b>Invalid Format</b>\n<b>{SEP}</b>\nUsage:  <code>/st1 card|mm|yy|cvv</code>"), parse_mode='html'); return
    await _run_single_gate(event, cards[0], 'st1', 'Stripe 1$')

@bot.on(events.NewMessage(pattern=r'^/mst1(\s+[\s\S]+)?$'))
async def mass_st1(event):
    uid = event.sender_id
    if not is_premium(uid):
        await event.reply(pe(f"❌ <b>Access Denied</b>"), parse_mode='html'); return
    cards = await _gather_mass_cards(event)
    if not cards:
        await event.reply(pe(f"❌ <b>No valid cards found.</b>"), parse_mode='html'); return
    await _run_mass_gate(event, cards, 'st1', 'Stripe 1$')

# ═══════════════════════════════════════════════════════
# /st5 /mst5 — Stripe $5
# ═══════════════════════════════════════════════════════
@bot.on(events.NewMessage(pattern=r'^/st5\s+'))
async def single_st5(event):
    uid = event.sender_id
    if not is_premium(uid):
        await event.reply(pe(f"❌ <b>Access Denied</b>"), parse_mode='html'); return
    cards = extract_cc(event.message.text.split(' ', 1)[1].strip())
    if not cards:
        await event.reply(pe(f"❌ <b>Invalid Format</b>\n<b>{SEP}</b>\nUsage:  <code>/st5 card|mm|yy|cvv</code>"), parse_mode='html'); return
    await _run_single_gate(event, cards[0], 'st5', 'Stripe 5$')

@bot.on(events.NewMessage(pattern=r'^/mst5(\s+[\s\S]+)?$'))
async def mass_st5(event):
    uid = event.sender_id
    if not is_premium(uid):
        await event.reply(pe(f"❌ <b>Access Denied</b>"), parse_mode='html'); return
    cards = await _gather_mass_cards(event)
    if not cards:
        await event.reply(pe(f"❌ <b>No valid cards found.</b>"), parse_mode='html'); return
    await _run_mass_gate(event, cards, 'st5', 'Stripe 5$')

# ═══════════════════════════════════════════════════════
# /auth /mauth — Stripe Auth2 $0
# ═══════════════════════════════════════════════════════
@bot.on(events.NewMessage(pattern=r'^/auth\s+'))
async def single_auth(event):
    uid = event.sender_id
    if not is_premium(uid):
        await event.reply(pe(f"❌ <b>Access Denied</b>"), parse_mode='html'); return
    cards = extract_cc(event.message.text.split(' ', 1)[1].strip())
    if not cards:
        await event.reply(pe(f"❌ <b>Invalid Format</b>\n<b>{SEP}</b>\nUsage:  <code>/auth card|mm|yy|cvv</code>"), parse_mode='html'); return
    await _run_single_gate(event, cards[0], 'auth', 'Stripe Auth2 $0')

@bot.on(events.NewMessage(pattern=r'^/mauth(\s+[\s\S]+)?$'))
async def mass_auth(event):
    uid = event.sender_id
    if not is_premium(uid):
        await event.reply(pe(f"❌ <b>Access Denied</b>"), parse_mode='html'); return
    cards = await _gather_mass_cards(event)
    if not cards:
        await event.reply(pe(f"❌ <b>No valid cards found.</b>"), parse_mode='html'); return
    await _run_mass_gate(event, cards, 'auth', 'Stripe Auth2 $0')

# ═══════════════════════════════════════════════════════
# Mass card gatherer
# ═══════════════════════════════════════════════════════
async def _gather_mass_cards(event):
    uid = event.sender_id
    lines = []
    if event.reply_to_msg_id:
        rm = await event.get_reply_message()
        if rm and rm.file and (rm.file.name or '').endswith('.txt'):
            fp = await rm.download_media()
            if fp:
                async with aiofiles.open(fp, 'r', encoding='utf-8', errors='ignore') as f:
                    content = await f.read()
                try: os.remove(fp)
                except: pass
                lines = content.splitlines()
        elif rm and rm.text:
            lines = rm.text.splitlines()
    text = event.message.text
    parts = text.split(maxsplit=1)
    if len(parts) > 1 and parts[1].strip():
        lines.extend(parts[1].splitlines())
    if not lines:
        return []
    cards = extract_cc('\n'.join(lines))
    return cards

# ═══════════════════════════════════════════════════════
# Proxy commands
# ═══════════════════════════════════════════════════════
@bot.on(events.NewMessage(pattern=r'^/setproxy(\s+[\s\S]+)?$'))
async def setproxy_command(event):
    uid = event.sender_id
    if not is_premium(uid):
        await event.reply(pe(f"❌ <b>Access Denied.</b>"), parse_mode='html'); return
    content = event.message.text[len('/setproxy'):].strip()
    if not content:
        user_list = get_user_proxy_list(uid)
        if user_list:
            listed = "\n".join(f"  <code>{p}</code>" for p in user_list[:10])
            extra  = f"\n  <i>+{len(user_list)-10} more</i>" if len(user_list) > 10 else ""
            await event.reply(pe(
                f"🔌 <b>Your Proxies  ({len(user_list)})</b>\n"
                f"<b>{SEP}</b>\n"
                f"{listed}{extra}\n"
                f"<b>{SEP}</b>\n"
                f"Replace: <code>/setproxy ip:port</code>\n"
                f"Clear:   <code>/clearuserproxy</code>"
            ), parse_mode='html')
        else:
            await event.reply(pe(
                f"🔌 <b>Set Your Proxy</b>\n"
                f"<b>{SEP}</b>\n"
                f"<code>/setproxy ip:port</code>\n"
                f"<code>/setproxy ip:port:user:pass</code>\n"
                f"<b>{SEP}</b>\n"
                f"Multiple (one per line):\n"
                f"<code>/setproxy\nip:port\nip:port:user:pass</code>"
            ), parse_mode='html')
        return
    new_proxies = [l.strip() for l in content.split('\n') if l.strip()] if '\n' in content else [content.strip()]
    set_user_proxies(uid, new_proxies)
    await event.reply(pe(
        f"✅ <b>Proxy {'Set' if len(new_proxies)==1 else 'Updated'}</b>\n"
        f"<b>{SEP}</b>\n"
        f"📡 Active: {len(new_proxies)}\n"
        f"🔁 Rotating per card automatically"
    ), parse_mode='html')

@bot.on(events.NewMessage(pattern=r'^/clearuserproxy$'))
async def clearuserproxy_command(event):
    uid = event.sender_id
    if not is_premium(uid):
        await event.reply(pe(f"❌ <b>Access Denied.</b>"), parse_mode='html'); return
    remove_user_proxy(uid)
    await event.reply(pe(f"✅ <b>Proxy Cleared</b>"), parse_mode='html')

@bot.on(events.NewMessage(pattern=r'^/chkproxy\s+'))
async def check_single_proxy(event):
    uid = event.sender_id
    if not is_premium(uid):
        await event.reply(pe(f"❌ <b>Access Denied.</b>"), parse_mode='html'); return
    proxy = event.message.text.split(' ', 1)[1].strip()
    msg   = await event.reply(pe(f"⚡ <b>Testing Proxy...</b>\n<b>{SEP}</b>\n<code>{proxy}</code>"), parse_mode='html')
    r = await test_proxy(proxy)
    if r.get('status') == 'alive':
        ip_info = await get_proxy_ip(proxy)
        await msg.edit(pe(
            f"✅ <b>Proxy  —  Alive</b>\n"
            f"<b>{SEP}</b>\n"
            f"📡 <code>{proxy}</code>\n"
            f"🌐 Exit IP:  <code>{ip_info or 'N/A'}</code>"
        ), parse_mode='html')
    else:
        await msg.edit(pe(f"❌ <b>Proxy  —  Dead</b>\n<b>{SEP}</b>\n<code>{proxy}</code>"), parse_mode='html')

@bot.on(events.NewMessage(pattern='/site'))
async def site_command(event):
    uid = event.sender_id
    if not is_premium(uid):
        await event.reply(pe(f"❌ <b>Access Denied.</b>"), parse_mode='html'); return
    sites   = load_sites()
    proxies = get_proxies_for_user(uid) or load_proxies()
    if not sites or not proxies:
        await event.reply(pe(f"❌ <b>No sites/proxies.</b>"), parse_mode='html'); return
    smsg = await event.reply(pe(f"🔥 <b>Testing {len(sites)} sites...</b>"), parse_mode='html')
    alive, dead = [], []
    for i in range(0, len(sites), 10):
        batch   = sites[i:i+10]
        results = await asyncio.gather(*[test_site(s, random.choice(proxies)) for s in batch])
        for r in results:
            (alive if r['status'] in ('alive', 'step_error') else dead).append(r['site'])
        await smsg.edit(pe(f"🔥 <b>Testing...</b>\n✅ Alive: {len(alive)} · ❌ Dead: {len(dead)}"), parse_mode='html')
    async with aiofiles.open(SITES_FILE, 'w') as f:
        for s in alive: await f.write(f"{s}\n")
    await smsg.edit(pe(f"✅ <b>Site Check Complete</b>\n<b>{SEP}</b>\n✅ Alive: {len(alive)}\n❌ Removed: {len(dead)}"), parse_mode='html')

@bot.on(events.NewMessage(pattern=r'^/(rm|rmsite)\s+'))
async def remove_site_command(event):
    uid = event.sender_id
    if not is_admin(uid):
        await event.reply(pe(f"❌ <b>Admin only.</b>"), parse_mode='html'); return
    site = event.message.text.split(' ', 1)[1].strip()
    curr = load_sites()
    if site not in curr:
        await event.reply(pe(f"❌ <b>Site Not Found</b>"), parse_mode='html'); return
    async with aiofiles.open(SITES_FILE, 'w') as f:
        for s in curr:
            if s != site: await f.write(f"{s}\n")
    await event.reply(pe(f"✅ <b>Site Removed</b>\n<code>{site}</code>"), parse_mode='html')

@bot.on(events.NewMessage(pattern=r'^/proxy'))
async def proxy_command(event):
    uid = event.sender_id
    if not is_premium(uid):
        await event.reply(pe(f"❌ <b>Access Denied.</b>"), parse_mode='html'); return
    proxies = load_proxies()
    if not proxies:
        await event.reply(pe(f"❌ <b>Proxy Pool Empty</b>"), parse_mode='html'); return
    smsg = await event.reply(pe(f"🔥 <b>Testing {len(proxies)} proxies...</b>"), parse_mode='html')
    alive, dead = [], []
    for i in range(0, len(proxies), 50):
        results = await asyncio.gather(*[test_proxy(p) for p in proxies[i:i+50]])
        for r in results:
            (alive if r['status'] == 'alive' else dead).append(r['proxy'])
        await smsg.edit(pe(f"🔥 <b>Testing...</b>\n✅ Alive: {len(alive)} · ❌ Dead: {len(dead)}"), parse_mode='html')
    async with aiofiles.open(PROXY_FILE, 'w') as f:
        for p in alive: await f.write(f"{p}\n")
    await smsg.edit(pe(f"✅ <b>Proxy Check Complete</b>\n<b>{SEP}</b>\n✅ Alive: {len(alive)}\n❌ Removed: {len(dead)}"), parse_mode='html')

@bot.on(events.NewMessage(pattern=r'^/myplan$'))
async def myplan_command(event):
    uid = event.sender_id
    lim = get_user_limit(uid)
    if is_admin(uid):
        role, status = "Admin", "Full access"
    elif is_premium(uid):
        role, status = "Premium", "Active"
    else:
        role, status = "None", "No Access"
    await event.reply(pe(
        f"💎 <b>Your Access</b>\n"
        f"<b>{SEP}</b>\n"
        f"🔑 Role:    <b>{role}</b>\n"
        f"⚡ Status:  <b>{status}</b>\n"
        f"📋 Limit:   <b>{lim:,} cards/file</b>\n"
        f"<b>{SEP}</b>\n"
        f"{DEV_LINE}"
    ), parse_mode='html')

# ═══════════════════════════════════════════════════════
# Admin panel
# ═══════════════════════════════════════════════════════
@bot.on(events.NewMessage(pattern=r'^/admin$'))
async def admin_panel_cmd(event):
    if not is_admin(event.sender_id):
        await event.reply(pe(f"❌ <b>Admin only.</b>"), parse_mode='html'); return
    await raw_send(event.sender_id, _admin_panel_text(), rows_admin(event.sender_id))

@bot.on(events.NewMessage(pattern=r'^/setadmin(\s+.*)?$'))
async def setadmin_command(event):
    uid = event.sender_id
    if not is_admin(uid):
        await event.reply(pe(f"❌ <b>Admin only.</b>"), parse_mode='html'); return
    parts = event.message.text.strip().split()
    current_list = "\n".join(f"  • <code>{a}</code>" for a in sorted(ADMIN_IDS))
    if len(parts) < 2:
        await event.reply(pe(
            f"<b>👑 Admin Management</b>\n"
            f"<b>{SEP}</b>\n"
            f"Current:\n{current_list}\n"
            f"<b>{SEP}</b>\n"
            f"Add:    <code>/setadmin add [user_id]</code>\n"
            f"Remove: <code>/setadmin rm [user_id]</code>"
        ), parse_mode='html')
        return
    action = parts[1].lower()
    if action in ("add", "rm", "remove") and len(parts) >= 3:
        try:
            target = int(parts[2])
        except ValueError:
            await event.reply(pe(f"❌ <b>Invalid user ID.</b>"), parse_mode='html'); return
        if action == "add":
            ADMIN_IDS.add(target)
            _save_admin_ids(ADMIN_IDS)
            _register_commands()
            await event.reply(pe(f"✅ <b>Admin Added</b>\n<code>{target}</code>"), parse_mode='html')
        else:
            if target in _DEFAULT_ADMINS:
                await event.reply(pe(f"❌ <b>Cannot remove default admin.</b>"), parse_mode='html'); return
            ADMIN_IDS.discard(target)
            _save_admin_ids(ADMIN_IDS)
            _register_commands()
            await event.reply(pe(f"✅ <b>Admin Removed</b>\n<code>{target}</code>"), parse_mode='html')

@bot.on(events.NewMessage(pattern=r'^/addpremium\s+'))
async def add_premium_command(event):
    if not is_admin(event.sender_id):
        await event.reply(pe(f"❌ <b>Admin only.</b>"), parse_mode='html'); return
    new_id = event.message.text.split(' ', 1)[1].strip()
    if not new_id.isdigit():
        await event.reply(pe(f"❌ Usage: <code>/addpremium 123456789</code>"), parse_mode='html'); return
    curr = load_premium_users()
    if new_id in curr:
        await event.reply(pe(f"⚠️ <b>Already Added</b>"), parse_mode='html'); return
    async with aiofiles.open(PREMIUM_FILE, 'a') as f:
        await f.write(f"{new_id}\n")
    await event.reply(pe(f"✅ <b>User Added</b>\n<code>{new_id}</code>"), parse_mode='html')

@bot.on(events.NewMessage(pattern=r'^/rmpremium\s+'))
async def remove_premium_command(event):
    if not is_admin(event.sender_id):
        await event.reply(pe(f"❌ <b>Admin only.</b>"), parse_mode='html'); return
    rm_id = event.message.text.split(' ', 1)[1].strip()
    curr  = load_premium_users()
    if rm_id not in curr:
        await event.reply(pe(f"❌ <b>Not Found</b>"), parse_mode='html'); return
    async with aiofiles.open(PREMIUM_FILE, 'w') as f:
        for u in curr:
            if u != rm_id: await f.write(f"{u}\n")
    await event.reply(pe(f"🚫 <b>User Removed</b>\n<code>{rm_id}</code>"), parse_mode='html')

@bot.on(events.NewMessage(pattern=r'^/addsite\s+'))
async def add_site_command(event):
    if not is_admin(event.sender_id):
        await event.reply(pe(f"❌ <b>Admin only.</b>"), parse_mode='html'); return
    new_site = event.message.text.split(' ', 1)[1].strip()
    if not new_site.startswith('http'):
        await event.reply(pe(f"❌ URL must start with <code>http</code>"), parse_mode='html'); return
    curr = load_sites()
    if new_site in curr:
        await event.reply(pe(f"⚠️ <b>Site already exists.</b>"), parse_mode='html'); return
    async with aiofiles.open(SITES_FILE, 'a') as f:
        await f.write(f"{new_site}\n")
    await event.reply(pe(f"✅ <b>Site Added</b>\n<code>{new_site}</code>\n📋 Total: {len(curr)+1}"), parse_mode='html')

@bot.on(events.NewMessage(pattern=r'^/addproxy'))
async def add_proxy_command(event):
    if not is_admin(event.sender_id):
        await event.reply(pe(f"❌ <b>Admin only.</b>"), parse_mode='html'); return
    content = event.message.text[len('/addproxy'):].strip()
    if not content:
        await event.reply(pe(
            f"📡 <b>Add Proxies to Pool</b>\n"
            f"<b>{SEP}</b>\n"
            f"<code>/addproxy ip:port</code>\n"
            f"<code>/addproxy ip:port:user:pass</code>\n"
            f"Multiple (one per line):\n"
            f"<code>/addproxy\nip:port\nip:port:user:pass</code>"
        ), parse_mode='html'); return
    new   = [l.strip() for l in content.split('\n') if l.strip()] if '\n' in content else [content.strip()]
    curr  = load_proxies()
    added = [p for p in new if p not in curr]
    dups  = len(new) - len(added)
    if not added:
        await event.reply(pe(f"⚠️ <b>All proxies already in pool.</b>"), parse_mode='html'); return
    async with aiofiles.open(PROXY_FILE, 'a') as f:
        for p in added: await f.write(f"{p}\n")
    dup_note = f"\n⚠️ {dups} duplicate(s) skipped." if dups else ""
    await event.reply(pe(
        f"✅ <b>Pool Updated</b>\n"
        f"<b>{SEP}</b>\n"
        f"📡 Added: {len(added)}{dup_note}\n"
        f"📋 Total: {len(curr)+len(added)} proxies"
    ), parse_mode='html')

@bot.on(events.NewMessage(pattern=r'^/clearproxy$'))
async def clear_all_proxies(event):
    uid = event.sender_id
    if not is_admin(uid):
        await event.reply(pe(f"❌ <b>Admin only.</b>"), parse_mode='html'); return
    curr = load_proxies()
    if not curr:
        await event.reply(pe(f"⚠️ <b>Proxy pool is already empty.</b>"), parse_mode='html'); return
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    bk = f"proxy_backup_{uid}_{ts}.txt"
    async with aiofiles.open(bk, 'w') as f:
        for p in curr: await f.write(f"{p}\n")
    await event.reply(pe(f"📋 <b>Backup  ({len(curr)} proxies)</b>"), file=bk, parse_mode='html')
    try: os.remove(bk)
    except: pass
    async with aiofiles.open(PROXY_FILE, 'w') as f:
        await f.write("")
    await event.reply(pe(f"✅ <b>Proxy Pool Cleared</b>\n🗑️ Removed {len(curr)} proxies."), parse_mode='html')

@bot.on(events.NewMessage(pattern=r'^/broadcast\s+'))
async def broadcast_command(event):
    uid = event.sender_id
    if not is_admin(uid):
        await event.reply(pe(f"❌ <b>Admin only.</b>"), parse_mode='html'); return
    msg_text = event.message.text.split(' ', 1)[1].strip()
    all_targets = set()
    for u in load_premium_users():
        try: all_targets.add(int(u))
        except: pass
    for u in ADMIN_IDS:
        all_targets.add(u)
    if not all_targets:
        await event.reply(pe(f"⚠️ <b>No users to broadcast to.</b>"), parse_mode='html'); return
    status_msg = await event.reply(pe(f"📡 <b>Broadcasting... ({len(all_targets)} targets)</b>"), parse_mode='html')
    sent, failed = 0, 0
    for target in all_targets:
        try:
            await bot.send_message(target, pe(
                f"📢 <b>Announcement  —  {BOT_BRAND}</b>\n"
                f"<b>{SEP}</b>\n"
                f"{msg_text}\n"
                f"<b>{SEP}</b>\n"
                f"{DEV_LINE}"
            ), parse_mode='html')
            sent += 1
            await asyncio.sleep(0.1)
        except:
            failed += 1
    await status_msg.edit(pe(
        f"📡 <b>Broadcast Complete</b>\n"
        f"✅ Delivered: {sent}\n"
        f"❌ Failed: {failed}"
    ), parse_mode='html')

# ═══════════════════════════════════════════════════════
# Owner-only: keys / API eps / GC
# ═══════════════════════════════════════════════════════
@bot.on(events.NewMessage(pattern=r'^/genkey(\s+\d+)?$'))
async def genkey_cmd(event):
    if event.sender_id != OWNER_ID:
        await event.reply(pe(f"❌ <b>Owner only.</b>"), parse_mode='html'); return
    parts = event.message.text.strip().split()
    count = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 1
    count = min(count, 50)
    keys = [generate_key() for _ in range(count)]
    listed = "\n".join(f"  <code>{k}</code>" for k in keys)
    await event.reply(pe(
        f"✅ <b>{count} Key(s) Generated</b>\n"
        f"<b>{SEP}</b>\n"
        f"{listed}"
    ), parse_mode='html')

@bot.on(events.NewMessage(pattern=r'^/listkeys$'))
async def listkeys_cmd(event):
    if event.sender_id != OWNER_ID:
        await event.reply(pe(f"❌ <b>Owner only.</b>"), parse_mode='html'); return
    keys = list_keys(limit=100)
    if not keys:
        await event.reply(pe(f"📋 <b>No keys generated yet.</b>"), parse_mode='html'); return
    lines = []
    for k, v in keys:
        status = "❌ used" if v.get('used') else "✅ unused"
        lines.append(f"  <code>{k}</code>  {status}")
    await event.reply(pe(
        f"📋 <b>Keys ({len(keys)})</b>\n"
        f"<b>{SEP}</b>\n"
        + "\n".join(lines)
    ), parse_mode='html')

# GC setters — sent from the target GC / channel by the owner
@bot.on(events.NewMessage(pattern=r'^/setprivategc$'))
async def set_private_gc(event):
    if event.sender_id != OWNER_ID:
        return
    cfg = load_gc_config()
    cfg['private_gc'] = event.chat_id
    save_gc_config(cfg)
    await event.reply(f"✅ Private GC linked: <code>{event.chat_id}</code>", parse_mode='html')

@bot.on(events.NewMessage(pattern=r'^/setpublicgc$'))
async def set_public_gc(event):
    if event.sender_id != OWNER_ID:
        return
    cfg = load_gc_config()
    cfg['public_gc'] = event.chat_id
    save_gc_config(cfg)
    await event.reply(f"✅ Public GC linked: <code>{event.chat_id}</code>", parse_mode='html')

@bot.on(events.NewMessage(pattern=r'^/setloggc$'))
async def set_log_gc(event):
    if event.sender_id != OWNER_ID:
        return
    cfg = load_gc_config()
    cfg['log_gc'] = event.chat_id
    save_gc_config(cfg)
    await event.reply(f"✅ Log GC linked: <code>{event.chat_id}</code>", parse_mode='html')

@bot.on(events.NewMessage(pattern=r'^/setpublicchannel$'))
async def set_public_channel(event):
    if event.sender_id != OWNER_ID:
        return
    cfg = load_gc_config()
    cfg['public_channel'] = event.chat_id
    save_gc_config(cfg)
    await event.reply(f"✅ Public Channel linked: <code>{event.chat_id}</code>", parse_mode='html')

@bot.on(events.NewMessage(pattern=r'^/addreqchannel\s+'))
async def add_req_channel(event):
    if event.sender_id != OWNER_ID:
        await event.reply(pe(f"❌ <b>Owner only.</b>"), parse_mode='html'); return
    ref = event.message.text.split(' ', 1)[1].strip()
    if not ref.startswith('@'):
        await event.reply(pe(f"❌ <b>Use @username form.</b>"), parse_mode='html'); return
    cfg = load_gc_config()
    if ref in cfg['required_channels']:
        await event.reply(pe(f"⚠️ <b>Already added.</b>"), parse_mode='html'); return
    cfg['required_channels'].append(ref)
    save_gc_config(cfg)
    await event.reply(pe(f"✅ <b>Required Channel Added</b>\n<code>{ref}</code>"), parse_mode='html')

@bot.on(events.NewMessage(pattern=r'^/rmreqchannel\s+'))
async def rm_req_channel(event):
    if event.sender_id != OWNER_ID:
        await event.reply(pe(f"❌ <b>Owner only.</b>"), parse_mode='html'); return
    ref = event.message.text.split(' ', 1)[1].strip()
    cfg = load_gc_config()
    if ref not in cfg['required_channels']:
        await event.reply(pe(f"❌ <b>Not found.</b>"), parse_mode='html'); return
    cfg['required_channels'] = [c for c in cfg['required_channels'] if c != ref]
    save_gc_config(cfg)
    await event.reply(pe(f"✅ <b>Removed</b>\n<code>{ref}</code>"), parse_mode='html')

@bot.on(events.NewMessage(pattern=r'^/addapi\s+'))
async def add_api_cmd(event):
    if event.sender_id != OWNER_ID:
        await event.reply(pe(f"❌ <b>Owner only.</b>"), parse_mode='html'); return
    url = event.message.text.split(' ', 1)[1].strip().rstrip('/')
    if not url.startswith('http'):
        await event.reply(pe(f"❌ URL must start with <code>http</code>"), parse_mode='html'); return
    eps = load_api_endpoints()
    if url in eps:
        await event.reply(pe(f"⚠️ <b>Already exists.</b>"), parse_mode='html'); return
    eps.append(url)
    save_api_endpoints(eps)
    await event.reply(pe(f"✅ <b>API Endpoint Added</b>\n<code>{url}</code>\n📋 Total: {len(eps)}"), parse_mode='html')

@bot.on(events.NewMessage(pattern=r'^/rmapi\s+'))
async def rm_api_cmd(event):
    if event.sender_id != OWNER_ID:
        await event.reply(pe(f"❌ <b>Owner only.</b>"), parse_mode='html'); return
    url = event.message.text.split(' ', 1)[1].strip().rstrip('/')
    eps = load_api_endpoints()
    if url not in eps:
        await event.reply(pe(f"❌ <b>Not found.</b>"), parse_mode='html'); return
    if len(eps) == 1:
        await event.reply(pe(f"❌ <b>Cannot remove last endpoint.</b>"), parse_mode='html'); return
    eps = [e for e in eps if e != url]
    save_api_endpoints(eps)
    await event.reply(pe(f"✅ <b>Removed</b>\n<code>{url}</code>"), parse_mode='html')

# ═══════════════════════════════════════════════════════
# Callbacks
# ═══════════════════════════════════════════════════════
@bot.on(events.CallbackQuery(pattern=b"gates"))
async def cb_gates(event):
    uid = event.sender_id
    if not is_premium(uid):
        await event.answer("❌ Access required!", alert=True); return
    text = pe(
        f"<b>💳 Gates  —  {BOT_BRAND}</b>\n"
        f"<b>{SEP}</b>\n"
        f"<blockquote>"
        f"💳 <b>Shopify</b>       »  /sh · /msh\n"
        f"🔥 <b>Stripe 1$</b>     »  /st1 · /mst1\n"
        f"💎 <b>Stripe 5$</b>     »  /st5 · /mst5\n"
        f"✅ <b>Stripe Auth2</b>  »  /auth · /mauth"
        f"</blockquote>\n"
        f"<b>{SEP}</b>\n"
        f"{DEV_LINE}"
    )
    await event.answer()
    await nav_edit(event.chat_id, event.message_id, text, rows_gates())

@bot.on(events.CallbackQuery(pattern=b"gate_shopify"))
async def cb_gate_shopify(event):
    await event.answer()
    text = pe(
        f"<b>💳 Shopify Checker</b>\n"
        f"<b>{SEP}</b>\n"
        f"⚡ <b>Single:</b> <code>/sh card|mm|yy|cvv</code>\n"
        f"🔥 <b>Mass:</b> send <code>.txt</code> file\n"
        f"<b>{SEP}</b>\n"
        f"{DEV_LINE}"
    )
    await nav_edit(event.chat_id, event.message_id, text, [[{"text": "↪️ Back", "callback_data": "gates"}]])

@bot.on(events.CallbackQuery(pattern=b"gate_st1"))
async def cb_gate_st1(event):
    await event.answer()
    text = pe(
        f"<b>🔥 Stripe 1$ Charge</b>\n"
        f"<b>{SEP}</b>\n"
        f"⚡ <b>Single:</b> <code>/st1 card|mm|yy|cvv</code>\n"
        f"🔥 <b>Mass:</b> <code>/mst1</code> (reply to .txt or one-per-line)\n"
        f"<b>{SEP}</b>\n"
        f"{DEV_LINE}"
    )
    await nav_edit(event.chat_id, event.message_id, text, [[{"text": "↪️ Back", "callback_data": "gates"}]])

@bot.on(events.CallbackQuery(pattern=b"gate_st5"))
async def cb_gate_st5(event):
    await event.answer()
    text = pe(
        f"<b>💎 Stripe 5$ Charge</b>\n"
        f"<b>{SEP}</b>\n"
        f"⚡ <b>Single:</b> <code>/st5 card|mm|yy|cvv</code>\n"
        f"🔥 <b>Mass:</b> <code>/mst5</code> (reply to .txt or one-per-line)\n"
        f"<b>{SEP}</b>\n"
        f"{DEV_LINE}"
    )
    await nav_edit(event.chat_id, event.message_id, text, [[{"text": "↪️ Back", "callback_data": "gates"}]])

@bot.on(events.CallbackQuery(pattern=b"gate_auth"))
async def cb_gate_auth(event):
    await event.answer()
    text = pe(
        f"<b>✅ Stripe Auth2 $0</b>\n"
        f"<b>{SEP}</b>\n"
        f"⚡ <b>Single:</b> <code>/auth card|mm|yy|cvv</code>\n"
        f"🔥 <b>Mass:</b> <code>/mauth</code> (reply to .txt or one-per-line)\n"
        f"<b>{SEP}</b>\n"
        f"{DEV_LINE}"
    )
    await nav_edit(event.chat_id, event.message_id, text, [[{"text": "↪️ Back", "callback_data": "gates"}]])

@bot.on(events.CallbackQuery(pattern=b"redeem_info"))
async def cb_redeem_info(event):
    await event.answer()
    text = pe(
        f"🔑 <b>Redeem Key</b>\n"
        f"<b>{SEP}</b>\n"
        f"Usage: <code>/redeem OGGY-PROO-XXXX</code>"
    )
    await nav_edit(event.chat_id, event.message_id, text, [[{"text": "↪️ Back", "callback_data": "back_start"}]])

@bot.on(events.CallbackQuery(pattern=b"check_join"))
async def cb_check_join(event):
    uid = event.sender_id
    missing = await _check_force_join(uid)
    if missing:
        await event.answer("❌ Still not joined all channels.", alert=True)
        return
    await event.answer("✅ Verified!", alert=False)
    try:
        await event.delete()
    except:
        pass

@bot.on(events.CallbackQuery(pattern=b"manage_proxy"))
async def cb_manage_proxy(event):
    uid = event.sender_id
    if not is_premium(uid):
        await event.answer("❌ Access required!", alert=True); return
    user_list = get_user_proxy_list(uid)
    pool      = load_proxies()
    proxy_status = f"✅ {len(user_list)} proxy(ies) active" if user_list else "❌ No Personal Proxies Set"
    text = pe(
        f"<b>🔌 Proxy Manager</b>\n"
        f"<b>{SEP}</b>\n"
        f"👤 Personal:  {proxy_status}\n"
        f"📡 Pool:      {len(pool)} shared proxies\n"
        f"<b>{SEP}</b>\n"
        f"<code>/setproxy ip:port</code>\n"
        f"<code>/setproxy\nproxy1:port\nproxy2:port</code>\n"
        f"Clear: <code>/clearuserproxy</code>"
    )
    await event.answer()
    await nav_edit(event.chat_id, event.message_id, text, rows_proxy(uid))

@bot.on(events.CallbackQuery(pattern=b"back_start"))
async def cb_back_start(event):
    uid = event.sender_id
    try:
        sender    = await bot.get_entity(uid)
        username  = f"@{sender.username}" if sender.username else f"ID:{uid}"
        firstname = sender.first_name or "User"
    except:
        username, firstname = f"ID:{uid}", "User"
    lim = get_user_limit(uid)
    if is_admin(uid):
        status_icon, status_line = "👑", "Admin"
    elif is_premium(uid):
        status_icon, status_line = "✅", "Premium"
    else:
        status_icon, status_line = "🚫", "No Access"
    text = pe(
        f"<b>⚡ Welcome, {firstname}!</b>\n"
        f"<b>{SEP}</b>\n"
        f"<blockquote>"
        f"👤 <b>User</b>     »  {username}\n"
        f"🆔 <b>ID</b>       »  <code>{uid}</code>\n"
        f"{status_icon} <b>Status</b>  »  {status_line}\n"
        f"📋 <b>Limit</b>   »  {lim if lim else '—'} cards/file"
        f"</blockquote>\n"
        f"<b>{SEP}</b>\n"
        f"Select an option below to get started.\n"
        f"<b>{SEP}</b>\n"
        f"{DEV_LINE}"
    )
    await event.answer()
    await nav_edit(event.chat_id, event.message_id, text, rows_main())

@bot.on(events.CallbackQuery(pattern=b"close"))
async def cb_close(event):
    await event.answer()
    try:
        await bot.delete_messages(event.chat_id, event.message_id)
    except:
        pass

@bot.on(events.CallbackQuery(pattern=b"stop_mass"))
async def cb_stop_mass(event):
    uid = event.sender_id
    killed = 0
    for k in list(active_sessions.keys()):
        if k.startswith(f"{uid}_"):
            active_sessions.pop(k, None)
            killed += 1
    if killed:
        await event.answer("⛔ Mass check stopped!", alert=True)
        try:
            await raw_edit(event.chat_id, event.message_id,
                           pe(f"⛔ <b>Mass Check  —  Stopped</b>\n<b>{SEP}</b>\nCancelled by user."), [])
        except:
            pass
    else:
        await event.answer("No active session.", alert=True)

@bot.on(events.CallbackQuery(pattern=b"toggle_pool"))
async def cb_toggle_pool(event):
    uid = event.sender_id
    if not is_premium(uid):
        await event.answer("❌ Access required!", alert=True); return
    current = user_pool_enabled.get(uid, True)
    user_pool_enabled[uid] = not current
    save_user_pool()
    state = "ON ✅" if not current else "OFF ⚡"
    await event.answer(f"Proxy Pool → {state}", alert=False)
    user_list = get_user_proxy_list(uid)
    pool = load_proxies()
    proxy_status = f"✅ {len(user_list)} proxy(ies) active" if user_list else "❌ No Personal Proxies Set"
    text = pe(
        f"<b>🔌 Proxy Manager</b>\n"
        f"<b>{SEP}</b>\n"
        f"👤 Personal:  {proxy_status}\n"
        f"📡 Pool:      {len(pool)} shared proxies\n"
        f"<b>{SEP}</b>\n"
        f"<code>/setproxy ip:port</code>"
    )
    await nav_edit(event.chat_id, event.message_id, text, rows_proxy(uid))

@bot.on(events.CallbackQuery(pattern=b"test_proxy_btn"))
async def cb_test_proxy_btn(event):
    uid = event.sender_id
    if not is_premium(uid):
        await event.answer("❌ Access required!", alert=True); return
    user_list = get_user_proxy_list(uid)
    if not user_list:
        await event.answer("❌ No proxy set. Use /setproxy first.", alert=True); return
    proxy = user_list[0]
    await event.answer("⏳ Testing...", alert=False)
    r = await test_proxy(proxy)
    if r.get('status') == 'alive':
        ip_info = await get_proxy_ip(proxy)
        await event.answer(f"✅ Alive — {ip_info or 'N/A'}", alert=True)
    else:
        await event.answer("❌ Proxy Dead", alert=True)

@bot.on(events.CallbackQuery(pattern=b"remove_proxy_btn"))
async def cb_remove_proxy_btn(event):
    uid = event.sender_id
    if not is_premium(uid):
        await event.answer("❌ Access required!", alert=True); return
    remove_user_proxy(uid)
    await event.answer("✅ Proxy removed!", alert=True)
    user_list = get_user_proxy_list(uid)
    pool = load_proxies()
    proxy_status = f"✅ {len(user_list)} proxy(ies) active" if user_list else "❌ No Personal Proxies Set"
    text = pe(
        f"<b>🔌 Proxy Manager</b>\n"
        f"<b>{SEP}</b>\n"
        f"👤 Personal:  {proxy_status}\n"
        f"📡 Pool:      {len(pool)} shared proxies"
    )
    await nav_edit(event.chat_id, event.message_id, text, rows_proxy(uid))

# ═══════════════════════════════════════════════════════
# Admin panel callbacks
# ═══════════════════════════════════════════════════════
@bot.on(events.CallbackQuery(pattern=b"admin_panel"))
async def cb_admin_panel(event):
    if not is_admin(event.sender_id):
        await event.answer("❌ Admin only!", alert=True); return
    await event.answer()
    await nav_edit(event.chat_id, event.message_id, _admin_panel_text(), rows_admin(event.sender_id))

@bot.on(events.CallbackQuery(pattern=b"admin_users"))
async def cb_admin_users(event):
    if not is_admin(event.sender_id):
        await event.answer("❌ Admin only!", alert=True); return
    pcount = len(load_premium_users())
    text = pe(f"<b>👤 User Management</b>\n<b>{SEP}</b>\n✅ Access List: {pcount} users\n<b>{SEP}</b>\n{DEV_LINE}")
    await event.answer()
    await nav_edit(event.chat_id, event.message_id, text, rows_admin_users())

@bot.on(events.CallbackQuery(pattern=b"admin_sites"))
async def cb_admin_sites(event):
    if not is_admin(event.sender_id):
        await event.answer("❌ Admin only!", alert=True); return
    scount = len(load_sites())
    text = pe(
        f"<b>🌐 Site Management</b>\n"
        f"<b>{SEP}</b>\n"
        f"🌐 Active Sites: {scount}\n"
        f"<b>{SEP}</b>\n"
        f"<code>/addsite https://example.com</code>\n"
        f"<code>/rmsite https://example.com</code>"
    )
    await event.answer()
    await nav_edit(event.chat_id, event.message_id, text, rows_admin_sites())

@bot.on(events.CallbackQuery(pattern=b"admin_proxy_pool"))
async def cb_admin_proxy_pool(event):
    if not is_admin(event.sender_id):
        await event.answer("❌ Admin only!", alert=True); return
    prcount = len(load_proxies())
    text = pe(
        f"<b>📡 Proxy Pool</b>\n"
        f"<b>{SEP}</b>\n"
        f"📡 Pool Size: {prcount} proxies\n"
        f"<b>{SEP}</b>\n"
        f"<code>/addproxy ip:port</code>\n"
        f"<code>/clearproxy</code>"
    )
    await event.answer()
    await nav_edit(event.chat_id, event.message_id, text, rows_admin_proxy_pool())

@bot.on(events.CallbackQuery(pattern=b"admin_broadcast_info"))
async def cb_admin_broadcast_info(event):
    if not is_admin(event.sender_id):
        await event.answer("❌ Admin only!", alert=True); return
    total = len(load_premium_users()) + len(ADMIN_IDS)
    text = pe(f"<b>📢 Broadcast</b>\n<b>{SEP}</b>\n📋 Reach: ~{total} users\n<b>{SEP}</b>\nUsage: <code>/broadcast Message</code>")
    await event.answer()
    await nav_edit(event.chat_id, event.message_id, text, [[{"text": "↪️ Back", "callback_data": "admin_panel"}]])

@bot.on(events.CallbackQuery(pattern=b"admin_list_users"))
async def cb_admin_list_users(event):
    if not is_admin(event.sender_id):
        await event.answer("❌ Admin only!", alert=True); return
    curr = load_premium_users()
    if not curr:
        await event.answer("📋 No users on the access list yet.", alert=True); return
    lines = "\n".join([f"  {i+1}. <code>{u}</code>" for i, u in enumerate(curr[:30])])
    extra = f"\n  <i>+{len(curr)-30} more...</i>" if len(curr) > 30 else ""
    await event.answer()
    await nav_edit(event.chat_id, event.message_id, pe(f"<b>📋 Access List ({len(curr)})</b>\n<b>{SEP}</b>\n{lines}{extra}"),
                   [[{"text": "↪️ Back", "callback_data": "admin_users"}]])

@bot.on(events.CallbackQuery(pattern=b"admin_add_user_info"))
async def cb_admin_add_user_info(event):
    if not is_admin(event.sender_id):
        await event.answer("❌ Admin only!", alert=True); return
    await event.answer()
    await nav_edit(event.chat_id, event.message_id,
                   pe(f"<b>✅ Add User</b>\n<b>{SEP}</b>\nUsage: <code>/addpremium [user_id]</code>"),
                   [[{"text": "↪️ Back", "callback_data": "admin_users"}]])

@bot.on(events.CallbackQuery(pattern=b"admin_rm_user_info"))
async def cb_admin_rm_user_info(event):
    if not is_admin(event.sender_id):
        await event.answer("❌ Admin only!", alert=True); return
    await event.answer()
    await nav_edit(event.chat_id, event.message_id,
                   pe(f"<b>❌ Remove User</b>\n<b>{SEP}</b>\nUsage: <code>/rmpremium [user_id]</code>"),
                   [[{"text": "↪️ Back", "callback_data": "admin_users"}]])

@bot.on(events.CallbackQuery(pattern=b"admin_list_sites_cb"))
async def cb_admin_list_sites(event):
    if not is_admin(event.sender_id):
        await event.answer("❌ Admin only!", alert=True); return
    curr = load_sites()
    if not curr:
        await event.answer("🌐 No sites configured yet.", alert=True); return
    lines = "\n".join([f"  {i+1}. <code>{s}</code>" for i, s in enumerate(curr[:20])])
    extra = f"\n  <i>+{len(curr)-20} more...</i>" if len(curr) > 20 else ""
    await event.answer()
    await nav_edit(event.chat_id, event.message_id, pe(f"<b>🌐 Sites ({len(curr)})</b>\n<b>{SEP}</b>\n{lines}{extra}"),
                   [[{"text": "↪️ Back", "callback_data": "admin_sites"}]])

@bot.on(events.CallbackQuery(pattern=b"admin_add_site_info"))
async def cb_admin_add_site_info(event):
    if not is_admin(event.sender_id):
        await event.answer("❌ Admin only!", alert=True); return
    await event.answer()
    await nav_edit(event.chat_id, event.message_id,
                   pe(f"<b>✅ Add Site</b>\n<b>{SEP}</b>\nUsage: <code>/addsite https://example.com</code>"),
                   [[{"text": "↪️ Back", "callback_data": "admin_sites"}]])

@bot.on(events.CallbackQuery(pattern=b"admin_rm_site_info"))
async def cb_admin_rm_site_info(event):
    if not is_admin(event.sender_id):
        await event.answer("❌ Admin only!", alert=True); return
    await event.answer()
    await nav_edit(event.chat_id, event.message_id,
                   pe(f"<b>❌ Remove Site</b>\n<b>{SEP}</b>\nUsage: <code>/rmsite https://example.com</code>"),
                   [[{"text": "↪️ Back", "callback_data": "admin_sites"}]])

@bot.on(events.CallbackQuery(pattern=b"admin_list_proxy_cb"))
async def cb_admin_list_proxy(event):
    if not is_admin(event.sender_id):
        await event.answer("❌ Admin only!", alert=True); return
    curr = load_proxies()
    if not curr:
        await event.answer("📡 Proxy pool is empty.", alert=True); return
    lines = "\n".join([f"  {i+1}. <code>{p}</code>" for i, p in enumerate(curr[:20])])
    extra = f"\n  <i>+{len(curr)-20} more...</i>" if len(curr) > 20 else ""
    await event.answer()
    await nav_edit(event.chat_id, event.message_id, pe(f"<b>📡 Proxy Pool ({len(curr)})</b>\n<b>{SEP}</b>\n{lines}{extra}"),
                   [[{"text": "↪️ Back", "callback_data": "admin_proxy_pool"}]])

@bot.on(events.CallbackQuery(pattern=b"admin_add_proxy_info"))
async def cb_admin_add_proxy_info(event):
    if not is_admin(event.sender_id):
        await event.answer("❌ Admin only!", alert=True); return
    await event.answer()
    await nav_edit(event.chat_id, event.message_id,
                   pe(f"<b>✅ Add Proxies</b>\n<b>{SEP}</b>\n<code>/addproxy ip:port</code>"),
                   [[{"text": "↪️ Back", "callback_data": "admin_proxy_pool"}]])

@bot.on(events.CallbackQuery(pattern=b"admin_clear_proxy_cb"))
async def cb_admin_clear_proxy(event):
    if not is_admin(event.sender_id):
        await event.answer("❌ Admin only!", alert=True); return
    curr = load_proxies()
    if not curr:
        await event.answer("Proxy pool is already empty.", alert=True); return
    with open(PROXY_FILE, 'w') as f:
        f.write("")
    await event.answer(f"✅ Cleared {len(curr)} proxies!", alert=True)
    await nav_edit(event.chat_id, event.message_id, _admin_panel_text(), rows_admin(event.sender_id))

# ═══════════════════════════════════════════════════════
# Owner panel callbacks
# ═══════════════════════════════════════════════════════
@bot.on(events.CallbackQuery(pattern=b"owner_api_eps"))
async def cb_owner_api_eps(event):
    if event.sender_id != OWNER_ID:
        await event.answer("❌ Owner only!", alert=True); return
    eps = load_api_endpoints()
    await event.answer()
    text = pe(f"<b>🔌 API Endpoints ({len(eps)})</b>\n<b>{SEP}</b>\nUse buttons to manage.")
    await nav_edit(event.chat_id, event.message_id, text, rows_owner_api_eps())

@bot.on(events.CallbackQuery(pattern=b"owner_api_list"))
async def cb_owner_api_list(event):
    if event.sender_id != OWNER_ID:
        await event.answer("❌ Owner only!", alert=True); return
    eps = load_api_endpoints()
    lines = "\n".join(f"  {i+1}. <code>{e}</code>" for i, e in enumerate(eps))
    await event.answer()
    await nav_edit(event.chat_id, event.message_id,
                   pe(f"<b>🔌 API Endpoints ({len(eps)})</b>\n<b>{SEP}</b>\n{lines}"),
                   [[{"text": "↪️ Back", "callback_data": "owner_api_eps"}]])

@bot.on(events.CallbackQuery(pattern=b"owner_api_add_info"))
async def cb_owner_api_add_info(event):
    if event.sender_id != OWNER_ID:
        await event.answer("❌ Owner only!", alert=True); return
    await event.answer()
    await nav_edit(event.chat_id, event.message_id,
                   pe(f"<b>✅ Add Endpoint</b>\n<b>{SEP}</b>\n<code>/addapi https://check.example.com</code>"),
                   [[{"text": "↪️ Back", "callback_data": "owner_api_eps"}]])

@bot.on(events.CallbackQuery(pattern=b"owner_api_rm_info"))
async def cb_owner_api_rm_info(event):
    if event.sender_id != OWNER_ID:
        await event.answer("❌ Owner only!", alert=True); return
    await event.answer()
    await nav_edit(event.chat_id, event.message_id,
                   pe(f"<b>❌ Remove Endpoint</b>\n<b>{SEP}</b>\n<code>/rmapi https://check.example.com</code>"),
                   [[{"text": "↪️ Back", "callback_data": "owner_api_eps"}]])

@bot.on(events.CallbackQuery(pattern=b"owner_keys"))
async def cb_owner_keys(event):
    if event.sender_id != OWNER_ID:
        await event.answer("❌ Owner only!", alert=True); return
    keys = load_keys()
    total = len(keys)
    used  = sum(1 for v in keys.values() if v.get('used'))
    await event.answer()
    text = pe(f"<b>🔑 Keys</b>\n<b>{SEP}</b>\nTotal: {total}\nUsed: {used}\nUnused: {total - used}")
    await nav_edit(event.chat_id, event.message_id, text, rows_owner_keys())

@bot.on(events.CallbackQuery(pattern=b"owner_key_list"))
async def cb_owner_key_list(event):
    if event.sender_id != OWNER_ID:
        await event.answer("❌ Owner only!", alert=True); return
    keys = list_keys(limit=50)
    if not keys:
        await event.answer("📋 No keys generated yet.", alert=True); return
    lines = []
    for k, v in keys:
        status = "❌" if v.get('used') else "✅"
        lines.append(f"  {status} <code>{k}</code>")
    await event.answer()
    await nav_edit(event.chat_id, event.message_id,
                   pe(f"<b>🔑 Keys ({len(keys)})</b>\n<b>{SEP}</b>\n" + "\n".join(lines)),
                   [[{"text": "↪️ Back", "callback_data": "owner_keys"}]])

@bot.on(events.CallbackQuery(pattern=b"owner_key_gen_info"))
async def cb_owner_key_gen_info(event):
    if event.sender_id != OWNER_ID:
        await event.answer("❌ Owner only!", alert=True); return
    await event.answer()
    await nav_edit(event.chat_id, event.message_id,
                   pe(f"<b>✅ Generate Keys</b>\n<b>{SEP}</b>\n<code>/genkey 10</code>"),
                   [[{"text": "↪️ Back", "callback_data": "owner_keys"}]])

@bot.on(events.CallbackQuery(pattern=b"owner_gc"))
async def cb_owner_gc(event):
    if event.sender_id != OWNER_ID:
        await event.answer("❌ Owner only!", alert=True); return
    cfg = load_gc_config()
    await event.answer()
    text = pe(
        f"<b>🛡 GC / Channels Config</b>\n"
        f"<b>{SEP}</b>\n"
        f"🔒 Private GC:    {'✅ set' if cfg['private_gc'] else '❌ unset'}\n"
        f"🌐 Public GC:     {'✅ set' if cfg['public_gc'] else '❌ unset'}\n"
        f"📝 Log GC:        {'✅ set' if cfg['log_gc'] else '❌ unset'}\n"
        f"📢 Public Channel:{'✅ set' if cfg['public_channel'] else '❌ unset'}\n"
        f"🔗 Required:      {len(cfg['required_channels'])} channels"
    )
    await nav_edit(event.chat_id, event.message_id, text, rows_owner_gc())

@bot.on(events.CallbackQuery(pattern=b"owner_gc_private"))
async def cb_owner_gc_private(event):
    if event.sender_id != OWNER_ID:
        await event.answer("❌ Owner only!", alert=True); return
    await event.answer()
    await nav_edit(event.chat_id, event.message_id,
                   pe(f"<b>🔒 Private GC</b>\n<b>{SEP}</b>\nGo to your private GC and send:\n<code>/setprivategc</code>"),
                   [[{"text": "↪️ Back", "callback_data": "owner_gc"}]])

@bot.on(events.CallbackQuery(pattern=b"owner_gc_public"))
async def cb_owner_gc_public(event):
    if event.sender_id != OWNER_ID:
        await event.answer("❌ Owner only!", alert=True); return
    await event.answer()
    await nav_edit(event.chat_id, event.message_id,
                   pe(f"<b>🌐 Public GC</b>\n<b>{SEP}</b>\nSend in the GC:\n<code>/setpublicgc</code>"),
                   [[{"text": "↪️ Back", "callback_data": "owner_gc"}]])

@bot.on(events.CallbackQuery(pattern=b"owner_gc_log"))
async def cb_owner_gc_log(event):
    if event.sender_id != OWNER_ID:
        await event.answer("❌ Owner only!", alert=True); return
    await event.answer()
    await nav_edit(event.chat_id, event.message_id,
                   pe(f"<b>📝 Log GC</b>\n<b>{SEP}</b>\nSend in the GC:\n<code>/setloggc</code>"),
                   [[{"text": "↪️ Back", "callback_data": "owner_gc"}]])

@bot.on(events.CallbackQuery(pattern=b"owner_gc_channel"))
async def cb_owner_gc_channel(event):
    if event.sender_id != OWNER_ID:
        await event.answer("❌ Owner only!", alert=True); return
    await event.answer()
    await nav_edit(event.chat_id, event.message_id,
                   pe(f"<b>📢 Public Channel</b>\n<b>{SEP}</b>\nSend in the channel:\n<code>/setpublicchannel</code>"),
                   [[{"text": "↪️ Back", "callback_data": "owner_gc"}]])

@bot.on(events.CallbackQuery(pattern=b"owner_gc_req"))
async def cb_owner_gc_req(event):
    if event.sender_id != OWNER_ID:
        await event.answer("❌ Owner only!", alert=True); return
    cfg = load_gc_config()
    req = cfg['required_channels']
    lines = "\n".join(f"  • <code>{c}</code>" for c in req) if req else "  <i>none</i>"
    await event.answer()
    await nav_edit(event.chat_id, event.message_id,
                   pe(f"<b>🔗 Required Channels</b>\n<b>{SEP}</b>\n{lines}\n<b>{SEP}</b>\n"
                      f"<code>/addreqchannel @ch1</code>\n<code>/rmreqchannel @ch1</code>"),
                   [[{"text": "↪️ Back", "callback_data": "owner_gc"}]])

# ═══════════════════════════════════════════════════════
# File → mass check start button
# ═══════════════════════════════════════════════════════
@bot.on(events.CallbackQuery(pattern=r"^start_check_\d+$"))
async def cb_start_check(event):
    uid        = event.sender_id
    data       = event.data.decode()
    target_uid = int(data.split('_')[-1])
    if uid != target_uid:
        await event.answer("❌ Not your check!", alert=True); return
    info = pending_checks.pop(uid, None)
    if not info:
        await event.answer("⚠️ Session expired. Resend the file.", alert=True); return
    cards = info['cards']
    gate  = info.get('gate', 'shopify')
    sites   = load_sites()
    proxies = get_proxies_for_user(uid) or load_proxies()
    if gate == 'shopify' and (not sites or not proxies):
        await event.answer("❌ No sites/proxies available.", alert=True); return
    await event.answer("🔥 Starting!", alert=False)
    text = pe(
        f"<b>🔥 Mass Check  —  Starting</b>\n"
        f"<b>{SEP}</b>\n"
        f"📋 <b>Total</b>      »  {len(cards)}\n"
        f"<code>{make_progress_bar(0, len(cards))}</code>"
    )
    msg_id = await raw_send(uid, text, rows_stop())
    if msg_id:
        asyncio.create_task(run_mass_check(uid, cards, msg_id, gate, 'Shopify'))

@bot.on(events.CallbackQuery(pattern=b"noop"))
async def cb_noop(event):
    await event.answer()

# ═══════════════════════════════════════════════════════
# Command registration
# ═══════════════════════════════════════════════════════
def _register_commands():
    user_cmds = [
        {"command": "start",          "description": "🚀 Open dashboard"},
        {"command": "redeem",         "description": "🔑 Redeem a key"},
        {"command": "sh",             "description": "⚡ Shopify single: /sh cc|mm|yy|cvv"},
        {"command": "msh",            "description": "🔥 Shopify mass (reply to .txt)"},
        {"command": "st1",            "description": "🔥 Stripe $1 single"},
        {"command": "mst1",           "description": "🔥 Stripe $1 mass"},
        {"command": "st5",            "description": "💎 Stripe $5 single"},
        {"command": "mst5",           "description": "💎 Stripe $5 mass"},
        {"command": "auth",           "description": "✅ Stripe Auth2 $0 single"},
        {"command": "mauth",          "description": "✅ Stripe Auth2 $0 mass"},
        {"command": "myplan",         "description": "💎 Check your access level"},
        {"command": "setproxy",       "description": "🔌 Set proxy"},
        {"command": "clearuserproxy", "description": "🗑️ Remove your proxy"},
        {"command": "chkproxy",       "description": "✅ Test a proxy"},
    ]
    admin_cmds = user_cmds + [
        {"command": "admin",      "description": "👑 Admin panel"},
        {"command": "addpremium", "description": "✅ Add user"},
        {"command": "rmpremium",  "description": "❌ Remove user"},
        {"command": "addsite",    "description": "🌐 Add site"},
        {"command": "rmsite",     "description": "🗑️ Remove site"},
        {"command": "addproxy",   "description": "📡 Add proxy"},
        {"command": "clearproxy", "description": "🗑️ Clear proxy pool"},
        {"command": "broadcast",  "description": "📢 Broadcast"},
        {"command": "setadmin",   "description": "👑 Manage admins"},
    ]
    owner_cmds = admin_cmds + [
        {"command": "genkey",         "description": "🔑 Generate keys"},
        {"command": "listkeys",       "description": "📋 List keys"},
        {"command": "addapi",         "description": "🔌 Add API endpoint"},
        {"command": "rmapi",          "description": "❌ Remove API endpoint"},
        {"command": "addreqchannel",  "description": "🔗 Add required channel"},
        {"command": "rmreqchannel",   "description": "❌ Remove required channel"},
        {"command": "setprivategc",   "description": "🔒 Link private GC (run in GC)"},
        {"command": "setpublicgc",    "description": "🌐 Link public GC (run in GC)"},
        {"command": "setloggc",       "description": "📝 Link log GC (run in GC)"},
        {"command": "setpublicchannel","description": "📢 Link public channel (run in channel)"},
    ]
    from keyboards import _http_session
    base = f"https://api.telegram.org/bot{BOT_TOKEN}"
    try:
        _http_session.post(f"{base}/setMyCommands",
                           json={"commands": user_cmds}, timeout=5)
        _http_session.post(f"{base}/setMyCommands",
                           json={"commands": owner_cmds,
                                 "scope": {"type": "chat", "chat_id": OWNER_ID}},
                           timeout=5)
        for aid in ADMIN_IDS:
            if aid != OWNER_ID:
                _http_session.post(f"{base}/setMyCommands",
                                   json={"commands": admin_cmds,
                                         "scope": {"type": "chat", "chat_id": aid}},
                                   timeout=5)
    except:
        pass

_register_commands()
_bin_count = load_bins()
print(f"✅ {BOT_BRAND} started successfully! (BIN DB: {_bin_count:,} entries)")
bot.run_until_disconnected()
