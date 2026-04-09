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
# NEW HF API URL — router.huggingface.co (Updated 2025)
# =========================================================
HF_API_BASE = "https://router.huggingface.co/hf-inference/models"

MODELS = {
    "1": {
        "name": "FLUX Schnell ⚡",
        "id": "black-forest-labs/FLUX.1-schnell",
        "desc": "Fast & sharp (Best)"
    },
    "2": {
        "name": "Stable Diffusion XL 🎨",
        "id": "stabilityai/stable-diffusion-xl-base-1.0",
        "desc": "Classic SDXL"
    },
    "3": {
        "name": "Dreamshaper 8 🌟",
        "id": "Lykon/dreamshaper-8",
        "desc": "Realistic & detailed"
    },
    "4": {
        "name": "Stable Diffusion 2.1 🖼️",
        "id": "stabilityai/stable-diffusion-2-1",
        "desc": "Reliable & fast"
    }
}

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
    if not HUGGINGFACE_TOKEN:
        return None, "❌ HUGGINGFACE_TOKEN set ಆಗಿಲ್ಲ. Render Environment Variables ಚೆಕ್ ಮಾಡಿ."

    headers = {
        "Authorization": f"Bearer {HUGGINGFACE_TOKEN}",
        "Content-Type": "application/json"
    }

    payload = {
        "inputs": prompt,
        "parameters": {
            "num_inference_steps": 25,
            "guidance_scale": 7.5
        }
    }

    # FLUX doesn't need guidance_scale
    if "FLUX" in model_id or "flux" in model_id.lower():
        payload = {"inputs": prompt}

    api_url = f"{HF_API_BASE}/{model_id}"
    logger.info(f"Calling: {api_url}")

    try:
        response = requests.post(api_url, headers=headers, json=payload, timeout=120)
        logger.info(f"HF Status: {response.status_code} | Model: {model_id}")

        if response.status_code == 200:
            content_type = response.headers.get('Content-Type', '')
            if 'image' in content_type or len(response.content) > 500:
                return response.content, None
            else:
                return None, "❌ Image data ಬರಲಿಲ್ಲ. ಬೇರೆ model try ಮಾಡಿ."
        elif response.status_code == 503:
            return None, "⏳ Model loading ಆಗ್ತಿದೆ. 30 sec ಕಾಯಿ ಮತ್ತೆ try ಮಾಡಿ."
        elif response.status_code == 401:
            return None, "❌ HuggingFace Token invalid! Render → Environment Variables ಚೆಕ್ ಮಾಡಿ."
        elif response.status_code == 403:
            return None, "❌ Model access ಇಲ್ಲ. /model ಬಳಸಿ ಬೇರೆ model ಆಯ್ಕೆ ಮಾಡಿ."
        elif response.status_code == 429:
            return None, "⏳ Rate limit. ಕೆಲವು seconds ಕಾಯಿ ಮತ್ತೆ try ಮಾಡಿ."
        else:
            err = response.text[:150] if response.text else "Unknown"
            logger.error(f"HF error {response.status_code}: {err}")
            return None, f"❌ Error {response.status_code}. /model ಬಳಸಿ ಬೇರೆ model try ಮಾಡಿ."

    except requests.Timeout:
        return None, "⏰ Timeout. ಮತ್ತೆ try ಮಾಡಿ."
    except Exception as e:
        logger.error(f"generate_image exception: {str(e)}")
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
# WEBHOOK
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
                        "text": f"✅ {model['name']} selected!"
                    })
                    send_message(chat_id,
                        f"✅ Model: <b>{model['name']}</b>\n\n"
                        f"💡 Now: /generate your prompt"
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
                "🤖 <b>CC Pic Bot v4 — AI Image Generator</b>\n\n"
                "📌 <b>Commands:</b>\n"
                "/generate &lt;prompt&gt; — Image generate\n"
                "/model — Model ಆಯ್ಕೆ\n"
                "/models — ಎಲ್ಲಾ models\n"
                "/help — Help\n\n"
                "🎨 <b>Example:</b>\n"
                "/generate a sunset over mountains, 4K, cinematic"
            )

        elif text.startswith('/help'):
            send_message(chat_id,
                "📖 <b>Help:</b>\n\n"
                "1️⃣ /model → Model ಆಯ್ಕೆ ಮಾಡಿ\n"
                "2️⃣ /generate your prompt → Image ತೆಗೆಯಿರಿ\n\n"
                "💡 <b>Tips:</b>\n"
                "• <i>\"a mountain lake at sunrise, photorealistic, 4K\"</i>\n"
                "• Style: <i>anime, oil painting, watercolor</i>\n"
                "• Quality: <i>detailed, sharp, HD, 8K</i>\n\n"
                "⚠️ 503 error ಬಂದರೆ → 30 sec ಕಾಯಿ ಮತ್ತೆ try ಮಾಡಿ\n"
                "⚡ FLUX Schnell — most reliable model"
            )

        elif text.startswith('/models'):
            model_list = "\n\n".join([
                f"{k}. <b>{v['name']}</b>\n   └ {v['desc']}"
                for k, v in MODELS.items()
            ])
            send_message(chat_id, f"🎨 <b>Available Models:</b>\n\n{model_list}\n\n/model ಬಳಸಿ select ಮಾಡಿ.")

        elif text.startswith('/model'):
            send_message(chat_id, "🎨 <b>Model ಆಯ್ಕೆ ಮಾಡಿ:</b>",
                reply_markup=models_keyboard())

        elif text.startswith('/generate'):
            prompt = text.replace('/generate', '', 1).strip()
            if not prompt:
                send_message(chat_id,
                    "⚠️ Prompt ಕೊಡಿ!\n\n"
                    "<b>Example:</b> /generate a beautiful mountain landscape"
                )
                return jsonify({'status': 'ok'})

            model_key = user_model_choice.get(chat_id, "1")
            model = MODELS[model_key]

            send_message(chat_id,
                f"🎨 <b>{model['name']}</b> ಜೊತೆ generate ಆಗ್ತಿದೆ...\n"
                f"📝 <i>{prompt[:100]}</i>\n\n"
                f"⏳ 20–60 sec ಕಾಯಿರಿ..."
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
                    # Fallback: send as document
                    files2 = {'document': ('image.jpg', image_data, 'image/jpeg')}
                    telegram_api("sendDocument", {"chat_id": chat_id}, files=files2)
            else:
                send_message(chat_id, error or "❌ Image generate ಆಗಲಿಲ್ಲ. ಮತ್ತೆ try ಮಾಡಿ.")

        else:
            send_message(chat_id,
                "👋 /generate &lt;prompt&gt; ಉಪಯೋಗಿಸಿ!\n/help ನೋಡಿ."
            )

        return jsonify({'status': 'ok'})

    except Exception as e:
        logger.error(f"Webhook error: {str(e)}")
        return jsonify({'status': 'error'}), 500

# =========================================================
# ROUTES
# =========================================================
@app.route('/setup')
def setup_webhook():
    webhook_url = request.url_root.rstrip('/') + '/webhook'
    result = telegram_api("setWebhook", {"url": webhook_url})
    if result and result.get('ok'):
        return f"✅ Webhook set: {webhook_url}"
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
            "hf_token_set": bool(HUGGINGFACE_TOKEN),
            "hf_api_base": HF_API_BASE
        })
    return jsonify({"error": "Failed"})

@app.route('/')
def index():
    return "🤖 CC Pic Bot v4 running! Visit /setup to configure webhook."

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
