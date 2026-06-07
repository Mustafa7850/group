# ========== حل مشكلة pyrogram ==========
import sys
import types as _types

# إنشاء وحدة pyrogram وهمية
mock_pyrogram = _types.ModuleType('pyrogram')
mock_pyrogram.Client = type('Client', (), {})
mock_pyrogram.filters = type('filters', (), {})
mock_pyrogram.types = type('types', (), {})
sys.modules['pyrogram'] = mock_pyrogram
# ======================================

import asyncio
import json
import os
import random
from datetime import datetime, timedelta
from telethon import TelegramClient, events, errors, functions
from telethon.tl.custom import Button

# ============================================
# ========== إعدادات البوت الأساسية ==========
BOT_TOKEN = "6762342423:AAEAXJr3lADwusTX9riNjfcM0BEEH8Ow1C8"
ADMIN_ID = 5667467267

# إعدادات عامة للقروبات
MESSAGE_TO_SEND = "."

# إعدادات الجدولة الافتراضية
DAILY_GROUPS_LIMIT_PER_ACCOUNT = 6
MIN_HOURS_BETWEEN_GROUPS = 3
MAX_HOURS_BETWEEN_GROUPS = 5

ACCOUNTS_FILE = "accounts.json"
DAILY_STATS_FILE = "daily_stats.json"
CONFIG_FILE = "config.json"

bot_client = None
user_clients = {}
pending_additions = {}
scheduler_task = None
scheduler_running = False

# ========== دوال الإعدادات ==========
def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    return {"daily_limit": DAILY_GROUPS_LIMIT_PER_ACCOUNT}

def save_config(config):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)

def get_daily_limit():
    cfg = load_config()
    return cfg.get("daily_limit", DAILY_GROUPS_LIMIT_PER_ACCOUNT)

def set_daily_limit(value):
    cfg = load_config()
    cfg["daily_limit"] = value
    save_config(cfg)

# ========== دوال الإحصائيات ==========
def load_stats():
    if os.path.exists(DAILY_STATS_FILE):
        with open(DAILY_STATS_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_stats(stats):
    with open(DAILY_STATS_FILE, 'w') as f:
        json.dump(stats, f, indent=2)

def get_today_key(phone):
    return f"{phone}_{datetime.now().strftime('%Y-%m-%d')}"

def can_create(phone):
    stats = load_stats()
    key = get_today_key(phone)
    current = stats.get(key, 0)
    limit = get_daily_limit()
    return current < limit, current, limit

def increment_daily(phone):
    stats = load_stats()
    key = get_today_key(phone)
    stats[key] = stats.get(key, 0) + 1
    save_stats(stats)

# ========== إدارة الحسابات ==========
def load_accounts():
    if os.path.exists(ACCOUNTS_FILE):
        with open(ACCOUNTS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def save_accounts(accounts):
    with open(ACCOUNTS_FILE, 'w', encoding='utf-8') as f:
        json.dump(accounts, f, indent=2, ensure_ascii=False)

def remove_account(phone):
    accounts = load_accounts()
    accounts = [a for a in accounts if a.get('phone') != phone]
    save_accounts(accounts)
    session_file = f"{phone}.session"
    if os.path.exists(session_file):
        os.remove(session_file)
    if phone in user_clients:
        asyncio.create_task(user_clients[phone].disconnect())
        del user_clients[phone]

def get_group_name(seq):
    return f"{datetime.now().strftime('%d-%m-%Y')}-{seq}"

# ========== دوال القروبات ==========
async def create_single_group(phone, chat_id):
    can, current, limit = can_create(phone)
    if not can:
        await bot_client.send_message(chat_id, f"⏸️ {phone}: الحد اليومي ({limit}) اكتمل")
        return False
    client = user_clients.get(phone)
    if not client or not client.is_connected():
        await bot_client.send_message(chat_id, f"❌ {phone} غير متصل")
        return False

    name = get_group_name(current + 1)
    try:
        res = await client(functions.channels.CreateChannelRequest(title=name, about="", megagroup=True))
        entity = res.chats[0]
        await client.send_message(entity, MESSAGE_TO_SEND)
        increment_daily(phone)
        await bot_client.send_message(chat_id, f"✅ [{phone}] تم: {name} ({current+1}/{limit})")
        return True
    except errors.FloodWaitError as e:
        await bot_client.send_message(ADMIN_ID, f"⚠️ Flood {phone}: انتظر {e.seconds} ثانية")
        await asyncio.sleep(e.seconds)
        return False
    except Exception as e:
        await bot_client.send_message(ADMIN_ID, f"❌ خطأ {phone}: {str(e)[:100]}")
        return False

async def check_spambot():
    try:
        async for msg in bot_client.iter_messages('@SpamBot', limit=3):
            if msg.text and any(k in msg.text.lower() for k in ['restricted', 'limited', 'spam']):
                await bot_client.send_message(ADMIN_ID, f"🚨 تحذير من SpamBot! توقف الجدولة.\n{msg.text[:200]}")
                return False
        return True
    except:
        return True

async def scheduler_loop():
    global scheduler_running
    await bot_client.send_message(ADMIN_ID, f"🔄 تشغيل الجدولة الآمنة\n📅 الحد اليومي: {get_daily_limit()}\n⏱️ الفاصل: {MIN_HOURS_BETWEEN_GROUPS}-{MAX_HOURS_BETWEEN_GROUPS} ساعات")
    while scheduler_running:
        if not await check_spambot():
            scheduler_running = False
            break
        available = [p for p, c in user_clients.items() if c and c.is_connected() and can_create(p)[0]]
        if available:
            phone = random.choice(available)
            await create_single_group(phone, ADMIN_ID)
            delay = random.randint(MIN_HOURS_BETWEEN_GROUPS * 3600, MAX_HOURS_BETWEEN_GROUPS * 3600)
            hours = delay // 3600
            await bot_client.send_message(ADMIN_ID, f"💤 انتظار {hours} ساعات قبل القروب التالي...")
            await asyncio.sleep(delay)
        else:
            midnight = (datetime.now() + timedelta(days=1)).replace(hour=0, minute=0, second=0)
            wait = (midnight - datetime.now()).total_seconds()
            await bot_client.send_message(ADMIN_ID, f"🌙 جميع الحسابات وصلت للحد اليومي. انتظار {wait/3600:.1f} ساعات")
            await asyncio.sleep(wait)
    scheduler_running = False

def start_scheduler():
    global scheduler_task, scheduler_running
    if scheduler_running:
        return False
    scheduler_running = True
    scheduler_task = asyncio.create_task(scheduler_loop())
    return True

def stop_scheduler():
    global scheduler_running
    scheduler_running = False
    return True

# ========== دوال تسجيل الدخول ==========
async def start_login(chat_id, phone, api_id, api_hash):
    client = TelegramClient(f"{phone}.session", api_id, api_hash)
    await client.connect()
    if not await client.is_user_authorized():
        await client.send_code_request(phone)
        pending_additions[chat_id] = {'client': client, 'phone': phone, 'api_id': api_id, 'api_hash': api_hash, 'step': 'code'}
        return True, "📲 تم إرسال رمز التحقق. أرسله هنا:"
    else:
        user_clients[phone] = client
        accounts = load_accounts()
        accounts = [a for a in accounts if a.get('phone') != phone] + [{'phone': phone, 'api_id': api_id, 'api_hash': api_hash, 'session_file': f"{phone}.session"}]
        save_accounts(accounts)
        return True, f"✅ تم تسجيل الحساب {phone}"

async def complete_code(chat_id, code):
    if chat_id not in pending_additions:
        return False, "لا توجد عملية نشطة"
    data = pending_additions[chat_id]
    try:
        await data['client'].sign_in(data['phone'], code)
        if await data['client'].is_user_authorized():
            user_clients[data['phone']] = data['client']
            accounts = load_accounts()
            accounts = [a for a in accounts if a.get('phone') != data['phone']] + [{'phone': data['phone'], 'api_id': data['api_id'], 'api_hash': data['api_hash'], 'session_file': f"{data['phone']}.session"}]
            save_accounts(accounts)
            del pending_additions[chat_id]
            return True, f"✅ تم إضافة الحساب {data['phone']}"
    except errors.SessionPasswordNeededError:
        pending_additions[chat_id]['step'] = 'password'
        return False, "PASSWORD_NEEDED"
    except errors.PhoneCodeInvalidError:
        return False, "❌ الرمز غير صحيح"
    except errors.PhoneCodeExpiredError:
        del pending_additions[chat_id]
        return False, "❌ انتهت صلاحية الرمز"
    except Exception as e:
        del pending_additions[chat_id]
        return False, f"❌ {str(e)[:100]}"
    return False, "خطأ"

async def complete_password(chat_id, pwd):
    if chat_id not in pending_additions:
        return False, "لا توجد عملية"
    data = pending_additions[chat_id]
    try:
        await data['client'].sign_in(password=pwd)
        if await data['client'].is_user_authorized():
            user_clients[data['phone']] = data['client']
            accounts = load_accounts()
            accounts = [a for a in accounts if a.get('phone') != data['phone']] + [{'phone': data['phone'], 'api_id': data['api_id'], 'api_hash': data['api_hash'], 'session_file': f"{data['phone']}.session"}]
            save_accounts(accounts)
            del pending_additions[chat_id]
            return True, f"✅ تم إضافة الحساب {data['phone']}"
    except errors.PasswordHashInvalidError:
        return False, "❌ كلمة المرور غير صحيحة"
    except Exception as e:
        del pending_additions[chat_id]
        return False, f"❌ {str(e)[:100]}"
    return False, "خطأ"

async def load_saved_accounts():
    for acc in load_accounts():
        phone = acc['phone']
        session_file = acc.get('session_file', f"{phone}.session")
        api_id = acc['api_id']
        api_hash = acc['api_hash']
        client = TelegramClient(session_file, api_id, api_hash)
        try:
            await client.start()
            if await client.is_user_authorized():
                user_clients[phone] = client
        except Exception as e:
            print(f"فشل تحميل {phone}: {e}")

# ========== أزرار القائمة ==========
def main_buttons():
    return [
        [Button.inline("➕ إضافة حساب جديد", b"add_acc")],
        [Button.inline("📋 قائمة الحسابات", b"list_acc")],
        [Button.inline("▶️ بدء الجدولة الآمنة", b"start_sched")],
        [Button.inline("⏹️ إيقاف الجدولة", b"stop_sched")],
        [Button.inline("🎯 إنشاء يدوي (جميع)", b"manual_all")],
        [Button.inline("🎯 إنشاء يدوي (حساب محدد)", b"manual_one")],
        [Button.inline("⚙️ ضبط الحد اليومي", b"set_limit")],
        [Button.inline("📊 التقرير اليومي", b"daily_report")],
        [Button.inline("❓ تعليمات", b"help")]
    ]

# ========== تشغيل البوت ==========
async def main():
    global bot_client
    bot_client = TelegramClient("bot_session", 22687194, "b36ad6db6121e384764180ee534a2b30")
    await bot_client.start(bot_token=BOT_TOKEN)
    me = await bot_client.get_me()
    print(f"🤖 البوت شغال: @{me.username}")
    await load_saved_accounts()

    @bot_client.on(events.NewMessage(func=lambda e: e.sender_id == ADMIN_ID))
    async def text_handler(event):
        cid = event.chat_id
        if cid in pending_additions:
            step = pending_additions[cid].get('step')
            if step == 'code':
                res, msg = await complete_code(cid, event.text.strip())
                await event.reply(msg)
                if msg.startswith("PASSWORD_NEEDED"):
                    await event.reply("🔒 أرسل كلمة المرور:")
                elif "✅" in msg and cid in pending_additions:
                    del pending_additions[cid]
            elif step == 'password':
                res, msg = await complete_password(cid, event.text.strip())
                await event.reply(msg)
                if cid in pending_additions:
                    del pending_additions[cid]

    @bot_client.on(events.NewMessage(pattern='/start'))
    async def start_cmd(event):
        if event.sender_id != ADMIN_ID:
            await event.reply("⛔ هذا البوت خاص بصاحبه.")
            return
        await event.reply("📱 **لوحة التحكم**\nاختر أحد الأزرار:", buttons=main_buttons(), parse_mode='markdown')

    @bot_client.on(events.CallbackQuery)
    async def callback(event):
        global scheduler_running
        if event.sender_id != ADMIN_ID:
            await event.answer("غير مسموح", alert=True)
            return
        data = event.data.decode()
        if data == "help":
            await event.edit("**التعليمات**\n• الحد اليومي 6 قروبات لكل حساب\n• فاصل 3-5 ساعات عشوائي\n• دوران عشوائي بين الحسابات", buttons=[[Button.inline("🔙 رجوع", b"back")]])
            return
        if data == "back":
            await event.edit("📱 **لوحة التحكم**", buttons=main_buttons())
            return
        if data == "start_sched":
            if scheduler_running:
                await event.answer("الجدولة تعمل بالفعل", alert=True)
            else:
                start_scheduler()
                await event.edit("✅ تم تشغيل الجدولة الآمنة")
            return
        if data == "stop_sched":
            if not scheduler_running:
                await event.answer("الجدولة غير مفعلة", alert=True)
            else:
                stop_scheduler()
                await event.edit("⏹️ تم إيقاف الجدولة")
            return
        if data == "add_acc":
            await event.edit("📞 أرسل رقم الهاتف (مثال: +9647827123666)")
            return
        if data == "list_acc":
            if not user_clients:
                await event.edit("📭 لا توجد حسابات", buttons=[[Button.inline("🔙 رجوع", b"back")]])
                return
            text = "**📱 الحسابات:**\n"
            for p, cl in user_clients.items():
                status = "✅ متصل" if cl.is_connected() else "❌"
                can, cur, lim = can_create(p)
                text += f"• `{p}` {status} | اليوم: {cur}/{lim}\n"
            btns = [[Button.inline(f"🗑️ حذف {p}", f"del_{p}".encode())] for p in user_clients.keys()]
            btns.append([Button.inline("🔙 رجوع", b"back")])
            await event.edit(text, buttons=btns, parse_mode='markdown')
            return
        if data.startswith("del_"):
            phone = data[4:]
            if phone in user_clients:
                remove_account(phone)
                await event.edit(f"✅ تم حذف {phone}", buttons=[[Button.inline("🔙 رجوع", b"back")]])
            return
        if data == "manual_all":
            if not user_clients:
                await event.edit("لا توجد حسابات", buttons=[[Button.inline("🔙 رجوع", b"back")]])
                return
            await event.edit("أرسل عدد القروبات لكل حساب (1-10):")
            @bot_client.on(events.NewMessage(func=lambda m: m.sender_id == ADMIN_ID and m.chat_id == event.chat_id))
            async def manual_num(msg):
                bot_client.remove_event_handler(manual_num)
                try:
                    num = int(msg.text.strip())
                    if num < 1 or num > 10:
                        raise ValueError
                except:
                    await msg.reply("❌ عدد غير صالح")
                    return
                await msg.reply(f"🚀 جاري إنشاء {num} قروب لكل حساب...")
                for phone in user_clients:
                    for _ in range(num):
                        await create_single_group(phone, msg.chat_id)
                        await asyncio.sleep(random.randint(60, 180))
                await msg.reply("✅ انتهى")
            return
        if data == "manual_one":
            if not user_clients:
                await event.edit("لا توجد حسابات", buttons=[[Button.inline("🔙 رجوع", b"back")]])
                return
            btns = [[Button.inline(phone, f"choose_{phone}".encode())] for phone in user_clients.keys()]
            btns.append([Button.inline("🔙 رجوع", b"back")])
            await event.edit("🎯 اختر الحساب:", buttons=btns)
            return
        if data.startswith("choose_"):
            phone = data[7:]
            if phone not in user_clients:
                await event.edit("حساب غير موجود", buttons=[[Button.inline("🔙 رجوع", b"back")]])
                return
            await event.edit(f"أرسل عدد القروبات للحساب {phone} (1-10):")
            @bot_client.on(events.NewMessage(func=lambda m: m.sender_id == ADMIN_ID and m.chat_id == event.chat_id))
            async def manual_one_num(msg):
                bot_client.remove_event_handler(manual_one_num)
                try:
                    num = int(msg.text.strip())
                    if num < 1 or num > 10:
                        raise ValueError
                except:
                    await msg.reply("❌ عدد غير صالح")
                    return
                await msg.reply(f"🚀 جاري إنشاء {num} قروب...")
                for _ in range(num):
                    await create_single_group(phone, msg.chat_id)
                    await asyncio.sleep(random.randint(60, 180))
                await msg.reply("✅ انتهى")
            return
        if data == "set_limit":
            current = get_daily_limit()
            await event.edit(f"⚙️ **الحد اليومي الحالي:** {current}\nأرسل الرقم الجديد (3-15):")
            @bot_client.on(events.NewMessage(func=lambda m: m.sender_id == ADMIN_ID and m.chat_id == event.chat_id))
            async def new_limit(msg):
                bot_client.remove_event_handler(new_limit)
                try:
                    new = int(msg.text.strip())
                    if new < 3 or new > 15:
                        raise ValueError
                    set_daily_limit(new)
                    await msg.reply(f"✅ تم ضبط الحد اليومي إلى {new}")
                except:
                    await msg.reply("❌ قيمة غير صالحة (3-15)")
            return
        if data == "daily_report":
            if not user_clients:
                await event.edit("لا توجد حسابات", buttons=[[Button.inline("🔙 رجوع", b"back")]])
                return
            limit = get_daily_limit()
            text = f"**📊 تقرير يوم {datetime.now().strftime('%Y-%m-%d')}**\nحد اليوم: {limit}\n\n"
            for phone in user_clients:
                can, cur, _ = can_create(phone)
                text += f"• `{phone}`: {cur}/{limit}\n"
            await event.edit(text, buttons=[[Button.inline("🔙 رجوع", b"back")]], parse_mode='markdown')
            return

    await bot_client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
