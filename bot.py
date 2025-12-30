import logging
import sqlite3
from datetime import timedelta

from telegram import (
    Update,
    ChatPermissions,
)
from telegram.constants import ChatMemberStatus
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
)

# ================= CONFIG =================
BOT_TOKEN = "PUT_YOUR_BOT_TOKEN_HERE"
DEFAULT_WARN_LIMIT = 3

logging.basicConfig(level=logging.INFO)

# ================= DATABASE =================
db = sqlite3.connect("bot.db", check_same_thread=False)
cur = db.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS groups (
    chat_id INTEGER PRIMARY KEY,
    warn_limit INTEGER DEFAULT 3
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS warns (
    chat_id INTEGER,
    user_id INTEGER,
    count INTEGER DEFAULT 0,
    PRIMARY KEY (chat_id, user_id)
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS messages (
    chat_id INTEGER,
    user_id INTEGER,
    message_id INTEGER
)
""")

db.commit()

# ================= HELPERS =================
async def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    member = await context.bot.get_chat_member(
        update.effective_chat.id,
        update.effective_user.id
    )
    return member.status in [
        ChatMemberStatus.ADMINISTRATOR,
        ChatMemberStatus.OWNER,
    ]


def get_warn_limit(chat_id: int):
    cur.execute("SELECT warn_limit FROM groups WHERE chat_id=?", (chat_id,))
    row = cur.fetchone()
    if row:
        return row[0]
    cur.execute(
        "INSERT OR IGNORE INTO groups(chat_id, warn_limit) VALUES (?,?)",
        (chat_id, DEFAULT_WARN_LIMIT)
    )
    db.commit()
    return DEFAULT_WARN_LIMIT


def add_warn(chat_id: int, user_id: int):
    cur.execute(
        "INSERT OR IGNORE INTO warns(chat_id, user_id, count) VALUES (?,?,0)",
        (chat_id, user_id)
    )
    cur.execute(
        "UPDATE warns SET count = count + 1 WHERE chat_id=? AND user_id=?",
        (chat_id, user_id)
    )
    db.commit()
    cur.execute(
        "SELECT count FROM warns WHERE chat_id=? AND user_id=?",
        (chat_id, user_id)
    )
    return cur.fetchone()[0]


def reset_warn(chat_id: int, user_id: int):
    cur.execute(
        "DELETE FROM warns WHERE chat_id=? AND user_id=?",
        (chat_id, user_id)
    )
    db.commit()

# ================= MESSAGE LOGGER =================
async def log_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or not msg.from_user:
        return
    cur.execute(
        "INSERT INTO messages(chat_id, user_id, message_id) VALUES (?,?,?)",
        (msg.chat.id, msg.from_user.id, msg.message_id)
    )
    db.commit()

# ================= COMMANDS =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("ربات مدیریت گروه فعال است.")

# ---- USER MANAGEMENT ----
async def ban(update, context):
    if not await is_admin(update, context): return
    if not update.message.reply_to_message: return
    await context.bot.ban_chat_member(
        update.effective_chat.id,
        update.message.reply_to_message.from_user.id
    )
    await update.message.reply_text("کاربر بن شد.")

async def unban(update, context):
    if not await is_admin(update, context): return
    if not update.message.reply_to_message: return
    await context.bot.unban_chat_member(
        update.effective_chat.id,
        update.message.reply_to_message.from_user.id
    )
    await update.message.reply_text("کاربر آنبن شد.")

async def kick(update, context):
    if not await is_admin(update, context): return
    if not update.message.reply_to_message: return
    uid = update.message.reply_to_message.from_user.id
    cid = update.effective_chat.id
    await context.bot.ban_chat_member(cid, uid)
    await context.bot.unban_chat_member(cid, uid)
    await update.message.reply_text("کاربر کیک شد.")

async def mute(update, context):
    if not await is_admin(update, context): return
    if not update.message.reply_to_message: return
    await context.bot.restrict_chat_member(
        update.effective_chat.id,
        update.message.reply_to_message.from_user.id,
        ChatPermissions(can_send_messages=False)
    )
    await update.message.reply_text("کاربر میوت شد.")

async def unmute(update, context):
    if not await is_admin(update, context): return
    if not update.message.reply_to_message: return
    await context.bot.restrict_chat_member(
        update.effective_chat.id,
        update.message.reply_to_message.from_user.id,
        ChatPermissions(can_send_messages=True)
    )
    await update.message.reply_text("کاربر آن‌میوت شد.")

async def tmute(update, context):
    if not await is_admin(update, context): return
    if not update.message.reply_to_message or not context.args: return
    minutes = int(context.args[0])
    await context.bot.restrict_chat_member(
        update.effective_chat.id,
        update.message.reply_to_message.from_user.id,
        ChatPermissions(can_send_messages=False),
        until_date=timedelta(minutes=minutes)
    )
    await update.message.reply_text(f"کاربر {minutes} دقیقه میوت شد.")

# ---- WARN SYSTEM ----
async def warn(update, context):
    if not await is_admin(update, context): return
    if not update.message.reply_to_message: return
    uid = update.message.reply_to_message.from_user.id
    cid = update.effective_chat.id
    count = add_warn(cid, uid)
    limit = get_warn_limit(cid)
    if count >= limit:
        await context.bot.ban_chat_member(cid, uid)
        reset_warn(cid, uid)
        await update.message.reply_text("کاربر به‌دلیل رسیدن به حد اخطار بن شد.")
    else:
        await update.message.reply_text(f"اخطار {count}/{limit}")

async def unwarn(update, context):
    if not await is_admin(update, context): return
    if not update.message.reply_to_message: return
    reset_warn(update.effective_chat.id,
               update.message.reply_to_message.from_user.id)
    await update.message.reply_text("اخطارها پاک شد.")

async def setwarn(update, context):
    if not await is_admin(update, context): return
    if not context.args: return
    limit = int(context.args[0])
    cur.execute(
        "INSERT OR REPLACE INTO groups(chat_id, warn_limit) VALUES (?,?)",
        (update.effective_chat.id, limit)
    )
    db.commit()
    await update.message.reply_text(f"حد اخطار روی {limit} تنظیم شد.")

# ---- MESSAGE CLEANING ----
async def purge(update, context):
    if not await is_admin(update, context): return
    if not update.message.reply_to_message: return
    start = update.message.reply_to_message.message_id
    end = update.message.message_id
    for mid in range(start, end + 1):
        try:
            await context.bot.delete_message(update.effective_chat.id, mid)
        except:
            pass

async def delall(update, context):
    if not await is_admin(update, context): return
    if not update.message.reply_to_message: return
    uid = update.message.reply_to_message.from_user.id
    cid = update.effective_chat.id
    cur.execute(
        "SELECT message_id FROM messages WHERE chat_id=? AND user_id=?",
        (cid, uid)
    )
    rows = cur.fetchall()
    for (mid,) in rows:
        try:
            await context.bot.delete_message(cid, mid)
        except:
            pass
    cur.execute(
        "DELETE FROM messages WHERE chat_id=? AND user_id=?",
        (cid, uid)
    )
    db.commit()
    await update.message.reply_text("پیام‌های ثبت‌شده کاربر پاک شد.")

# ---- ADMIN TOOLS ----
async def pin(update, context):
    if not await is_admin(update, context): return
    if not update.message.reply_to_message: return
    await context.bot.pin_chat_message(
        update.effective_chat.id,
        update.message.reply_to_message.message_id
    )

async def unpin(update, context):
    if not await is_admin(update, context): return
    await context.bot.unpin_all_chat_messages(update.effective_chat.id)

async def admins(update, context):
    admins = await context.bot.get_chat_administrators(update.effective_chat.id)
    text = "ادمین‌ها:\n"
    for a in admins:
        if a.user.username:
            text += f"@{a.user.username}\n"
        else:
            text += f"{a.user.first_name}\n"
    await update.message.reply_text(text)

async def tagall(update, context):
    if not await is_admin(update, context): return
    cur.execute(
        "SELECT DISTINCT user_id FROM messages WHERE chat_id=?",
        (update.effective_chat.id,)
    )
    users = cur.fetchall()
    text = ""
    for (uid,) in users[:30]:
        text += f"<a href='tg://user?id={uid}'>•</a>"
    await update.message.reply_text(text, parse_mode="HTML")

async def info(update, context):
    if not update.message.reply_to_message: return
    u = update.message.reply_to_message.from_user
    await update.message.reply_text(
        f"ID: {u.id}\n"
        f"Username: @{u.username}\n"
        f"Name: {u.first_name}"
    )

async def stats(update, context):
    cid = update.effective_chat.id
    cur.execute("SELECT COUNT(*) FROM warns WHERE chat_id=?", (cid,))
    warns = cur.fetchone()[0]
    cur.execute("SELECT COUNT(DISTINCT user_id) FROM messages WHERE chat_id=?", (cid,))
    users = cur.fetchone()[0]
    await update.message.reply_text(
        f"کاربران ثبت‌شده: {users}\n"
        f"کاربران دارای اخطار: {warns}"
    )

# ================= MAIN =================
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ban", ban))
    app.add_handler(CommandHandler("unban", unban))
    app.add_handler(CommandHandler("kick", kick))
    app.add_handler(CommandHandler("mute", mute))
    app.add_handler(CommandHandler("unmute", unmute))
    app.add_handler(CommandHandler("tmute", tmute))
    app.add_handler(CommandHandler("warn", warn))
    app.add_handler(CommandHandler("unwarn", unwarn))
    app.add_handler(CommandHandler("setwarn", setwarn))
    app.add_handler(CommandHandler("purge", purge))
    app.add_handler(CommandHandler("delall", delall))
    app.add_handler(CommandHandler("pin", pin))
    app.add_handler(CommandHandler("unpin", unpin))
    app.add_handler(CommandHandler("admins", admins))
    app.add_handler(CommandHandler("tagall", tagall))
    app.add_handler(CommandHandler("info", info))
    app.add_handler(CommandHandler("stats", stats))

    app.add_handler(CommandHandler("log", log_message))
    app.add_handler(CommandHandler("message", log_message))

    app.run_polling()

if __name__ == "__main__":
    main()
