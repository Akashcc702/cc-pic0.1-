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
# MODELS — Only HF Free Inference API compatible models
# =========================================================
MODELS = {
    "1": {
        "name": "FLUX Schnell ⚡",
        "id": "black-forest-labs/FLUX.1-schnell",
        "desc": "Fast & sharp (Best choice)"
    },
    "2": {
        "name": "Stable Diffusion XL 🎨",
        "id": "stabilityai/stable-diffusion-xl-base-1.0",
        "desc": "Classic SDXL, detailed"
    },
    "3": {
        "name": "Stable Diffusion 2.1 🖼️",
        "id": "stabilityai/stable-diffusion-2-1",
        "desc": "Reliable, fast"
    },
    "4": {
        "name": "Stable Diffusion 1.5 🌅",
        "id": "runwayml/stable-diffusion-v1-5",
        "desc": "Lightweight & quick"
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
    headers = {"Content-Type": "application/json"}
    if HUGGINGFACE_TOKEN:
        headers["Authorization"] = f"Bearer {HUGGINGFACE_TOKEN}"

    payload = {
        "inputs": prompt,
        "parameters": {
            "num_inference_steps": 25,
            "guidance_scale": 7.5
        },
        "options": {
            "wait_for_model": True,
            "use_cache": False
        }
    }

    # FLUX uses different parameters
    if "FLUX" in model_id or "flux" in model_id.lower():
        payload = {
            "inputs": prompt,
            "options": {
                "wait_for_model": True,
                "use_cache": False
            }
        }

    try:
        response = requests.post(
            f"https://api-inference.huggingface.co/models/{model_id}",
            headers=headers,
            json=payload,
            timeout=120
        )

        logger.info(f"HF response: {response.status_code} for model {model_id}")

        if response.status_code == 200:
            content_type = response.headers.get('Content-Type', '')
            if 'image' in content_type or len(response.content) > 1000:
                return response.content, None
            else:
                return None, "❌ Model returned non-image response. Try another model."

        elif response.status_code == 503:
            return None, "⏳ Model loading ಆಗ್ತಿದೆ. 30 seconds ಕಾಯಿ ಮತ್ತೆ try ಮಾಡಿ."
        elif response.status_code == 401:
            return None, "❌ HuggingFace token invalid. Check environment variable."
        elif response.status_code == 403:
            return None, "❌ Model access denied. Try another model with /model."
        elif response.status_code == 429:
            return None, "⏳ Rate limit. ಕೆಲವು seconds ಕಾಯಿ ಮತ್ತೆ try ಮಾಡಿ."
        elif response.status_code == 410:
            return None, "❌ ಈ model HF API ನಲ್ಲಿ ಇಲ್ಲ. /model ಉಪಯೋಗಿಸಿ ಬೇರೆ model ಆಯ್ಕೆ ಮಾಡಿ."
        else:
            return None, f"❌ Error {response.status_code}. /model ಬಳಸಿ ಬೇರೆ model try ಮಾಡಿ."

    except requests.Timeout:
        return None, "⏰ Timeout ಆಯ್ತು. ಮತ್ತೆ try ಮಾಡಿ."
    except Exception as e:
        logger.error(f"generate_image error: {str(e)}")
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
                        "text": f"✅ Selected: {model['name']}"
                    })
                    send_message(chat_id,
                        f"✅ Model set: <b>{model['name']}</b>\n\n"
                        f"Now use: /generate your prompt"
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
                "HuggingFace API ಬಳಸಿ AI images generate ಮಾಡಿ!\n\n"
                "📌 <b>Commands:</b>\n"
                "/generate &lt;prompt&gt; — Image generate\n"
                "/model — Model ಆಯ್ಕೆ ಮಾಡಿ\n"
                "/models — ಎಲ್ಲಾ models ಪಟ್ಟಿ\n"
                "/help — Help\n\n"
                "🎨 <b>Example:</b>\n"
                "/generate a beautiful sunset over mountains, 4K, photorealistic"
            )

        elif text.startswith('/help'):
            send_message(chat_id,
                "📖 <b>CC Pic Bot Help:</b>\n\n"
                "1️⃣ Model ಆಯ್ಕೆ: /model\n"
                "2️⃣ Image: /generate your prompt\n\n"
                "💡 <b>Good prompt tips:</b>\n"
                "• <i>\"a cat on a red sofa, cinematic lighting\"</i>\n"
                "• Style ಸೇರಿಸಿ: <i>photorealistic, anime, oil painting</i>\n"
                "• Quality: <i>4K, detailed, sharp, HD</i>\n\n"
                "⚠️ <b>Error ಬಂದರೆ:</b>\n"
                "• /model ಬಳಸಿ FLUX Schnell ಆಯ್ಕೆ ಮಾಡಿ (most reliable)\n"
                "• 503 error → 30 sec ಕಾಯಿ ಮತ್ತೆ try ಮಾಡಿ"
            )

        elif text.startswith('/models'):
            model_list = "\n\n".join([
                f"{k}. <b>{v['name']}</b>\n   └ {v['desc']}"
                for k, v in MODELS.items()
            ])
            send_message(chat_id, f"🎨 <b>Available Models:</b>\n\n{model_list}\n\nUse /model to select.")

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
                f"📝 Prompt: <i>{prompt[:100]}</i>\n\n"
                f"⏳ 20–60 seconds ಕಾಯಿರಿ..."
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
                    # Try sending as document if photo fails
                    files2 = {'document': ('image.jpg', image_data, 'image/jpeg')}
                    telegram_api("sendDocument", {"chat_id": chat_id}, files=files2)
            else:
                send_message(chat_id, error or "❌ Image generate ಆಗಲಿಲ್ಲ.")

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
# ROUTES
# =========================================================
@app.route('/setup')
def setup_webhook():
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
    return jsonify({"error": "Failed"})

@app.route('/')
def index():
    return "🤖 CC Pic Bot v3 is running! Visit /setup to configure webhook."

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
