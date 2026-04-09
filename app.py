from flask import Flask, request, jsonify
import requests
import os
import logging

app = Flask(__name__)

TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
HUGGINGFACE_TOKEN = os.environ.get('HUGGINGFACE_TOKEN', '')

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# =========================================================
# AVAILABLE MODELS
# =========================================================
MODELS = {
    "1": {
        "name": "FLUX Schnell ⚡",
        "id": "black-forest-labs/FLUX.1-schnell",
        "desc": "Fast & high quality (Recommended)"
    },
    "2": {
        "name": "Stable Diffusion XL 🎨",
        "id": "stabilityai/stable-diffusion-xl-base-1.0",
        "desc": "Classic SDXL model"
    },
    "3": {
        "name": "SD 3.5 Large Turbo 🚀",
        "id": "stabilityai/stable-diffusion-3.5-large-turbo",
        "desc": "Latest SD3.5 Turbo"
    },
    "4": {
        "name": "SDXL Lightning ⚡🎨",
        "id": "ByteDance/SDXL-Lightning",
        "desc": "ByteDance super-fast SDXL"
    }
}

# Store user's selected model (in-memory)
user_model_choice = {}

# =========================================================
# HELPERS
# =========================================================
def telegram_api(method, data=None, files=None):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{method}"
    try:
        if files:
            response = requests.post(url, data=data, files=files, timeout=30)
        elif data:
            response = requests.post(url, json=data, timeout=30)
        else:
            response = requests.get(url, timeout=30)
        return response.json() if response.status_code == 200 else None
    except Exception as e:
        logger.error(f"Telegram API error: {str(e)}")
        return None

def generate_image(prompt, model_id):
    headers = {}
    if HUGGINGFACE_TOKEN:
        headers["Authorization"] = f"Bearer {HUGGINGFACE_TOKEN}"
    try:
        response = requests.post(
            f"https://api-inference.huggingface.co/models/{model_id}",
            headers=headers,
            json={"inputs": prompt},
            timeout=120
        )
        if response.status_code == 200:
            return response.content, None
        elif response.status_code == 503:
            return None, "⏳ Model is loading, please wait 30 seconds and try again."
        elif response.status_code == 401:
            return None, "❌ Invalid HuggingFace token."
        else:
            return None, f"❌ Error {response.status_code}. Try again."
    except requests.Timeout:
        return None, "⏰ Request timed out. Try again."
    except Exception as e:
        return None, f"❌ Error: {str(e)}"

def models_keyboard():
    buttons = []
    for key, model in MODELS.items():
        buttons.append([{
            "text": f"{model['name']} — {model['desc']}",
            "callback_data": f"model_{key}"
        }])
    return {"inline_keyboard": buttons}

def send_message(chat_id, text, reply_markup=None):
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML"
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    return telegram_api("sendMessage", payload)

# =========================================================
# WEBHOOK HANDLER
# =========================================================
@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        data = request.get_json()

        # Inline button clicks
        if "callback_query" in data:
            callback = data["callback_query"]
            chat_id = callback["message"]["chat"]["id"]
            cb_data = callback.get("data", "")
            callback_id = callback["id"]

            if cb_data.startswith("model_"):
                key = cb_data.replace("model_", "")
                if key in MODELS:
                    user_model_choice[chat_id] = key
                    model = MODELS[key]
                    telegram_api("answerCallbackQuery", {
                        "callback_query_id": callback_id,
                        "text": f"✅ Selected: {model['name']}"
                    })
                    send_message(chat_id,
                        f"✅ Model set to: <b>{model['name']}</b>\n\n"
                        f"Now send: /generate your prompt here"
                    )
            return jsonify({'status': 'ok'})

        # Regular messages
        message = data.get('message', {})
        chat_id = message.get('chat', {}).get('id')
        text = message.get('text', '')

        if not chat_id or not text:
            return jsonify({'status': 'ok'})

        if text.startswith('/start'):
            send_message(chat_id,
                "🤖 <b>CC Pic Bot — AI Image Generator</b>\n\n"
                "Generate stunning images using top AI models!\n\n"
                "📌 <b>Commands:</b>\n"
                "/generate &lt;prompt&gt; — Generate an image\n"
                "/model — Choose AI model\n"
                "/models — List all models\n"
                "/help — Show help"
            )

        elif text.startswith('/help'):
            send_message(chat_id,
                "📖 <b>How to use CC Pic Bot:</b>\n\n"
                "1️⃣ Choose a model: /model\n"
                "2️⃣ Generate: /generate your prompt\n\n"
                "💡 <b>Good prompt tips:</b>\n"
                "• <i>\"a cat on a red sofa, sunset lighting\"</i>\n"
                "• Add style: <i>\"photorealistic\", \"anime\", \"oil painting\"</i>\n"
                "• Add quality: <i>\"4K, detailed, sharp\"</i>\n\n"
                "⚡ Default model: FLUX Schnell"
            )

        elif text.startswith('/models'):
            model_list = "\n\n".join([
                f"{k}. <b>{v['name']}</b>\n   └ {v['desc']}"
                for k, v in MODELS.items()
            ])
            send_message(chat_id, f"🎨 <b>Available Models:</b>\n\n{model_list}\n\nUse /model to select.")

        elif text.startswith('/model'):
            send_message(chat_id, "🎨 <b>Choose your AI Model:</b>",
                reply_markup=models_keyboard())

        elif text.startswith('/generate'):
            prompt = text.replace('/generate', '', 1).strip()
            if not prompt:
                send_message(chat_id,
                    "⚠️ Prompt ಬೇಕು!\n\n"
                    "<b>Usage:</b> /generate a beautiful mountain landscape"
                )
                return jsonify({'status': 'ok'})

            model_key = user_model_choice.get(chat_id, "1")
            model = MODELS[model_key]

            send_message(chat_id,
                f"🎨 Generating with <b>{model['name']}</b>...\n"
                f"📝 Prompt: <i>{prompt[:100]}</i>\n\n"
                f"⏳ Please wait (20–60 sec)..."
            )

            image_data, error = generate_image(prompt, model["id"])

            if image_data:
                files = {'photo': ('image.jpg', image_data, 'image/jpeg')}
                result = telegram_api("sendPhoto", {
                    "chat_id": chat_id,
                    "caption": f"✅ <b>{model['name']}</b>\n📝 {prompt[:200]}",
                    "parse_mode": "HTML"
                }, files=files)
                if not result or not result.get('ok'):
                    send_message(chat_id, "❌ Image send ಆಗಲಿಲ್ಲ. ಮತ್ತೆ try ಮಾಡಿ.")
            else:
                send_message(chat_id, error or "❌ Image generate ಆಗಲಿಲ್ಲ. ಮತ್ತೆ try ಮಾಡಿ.")

        else:
            send_message(chat_id,
                "👋 /generate &lt;prompt&gt; ಉಪಯೋಗಿಸಿ!\n"
                "ಅಥವಾ /help ನೋಡಿ."
            )

        return jsonify({'status': 'ok'})

    except Exception as e:
        logger.error(f"Webhook error: {str(e)}")
        return jsonify({'status': 'error'}), 500

# =========================================================
# SETUP & STATUS — RENDER_URL ಬೇಡ, auto-detect ಆಗುತ್ತದೆ
# =========================================================
@app.route('/setup')
def setup_webhook():
    # request.url_root ನಿಂದ automatically URL ತೆಗೆದುಕೊಳ್ಳುತ್ತದೆ
    webhook_url = request.url_root.rstrip('/') + '/webhook'
    result = telegram_api("setWebhook", {"url": webhook_url})
    if result and result.get('ok'):
        return f"✅ Webhook set to: {webhook_url}"
    return f"❌ Failed: {result}"

@app.route('/status')
def status():
    result = telegram_api("getWebhookInfo")
    if result and result.get('ok'):
        info = result.get('result', {})
        return jsonify({
            "webhook_url": info.get('url'),
            "pending_updates": info.get('pending_update_count'),
            "last_error": info.get('last_error_message'),
            "bot_token_set": bool(TELEGRAM_BOT_TOKEN),
            "hf_token_set": bool(HUGGINGFACE_TOKEN)
        })
    return jsonify({"error": "Failed to get webhook info"})

@app.route('/')
def index():
    return "🤖 CC Pic Bot is running! Visit /setup to configure webhook."

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
