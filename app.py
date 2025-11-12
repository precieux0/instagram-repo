from flask import Flask
import threading
import os
import time

app = Flask(__name__)

# Variable pour suivre l'état du bot
bot_status = "🟢 En cours de démarrage"
bot_thread = None

def run_bot():
    """Fonction pour exécuter le bot en arrière-plan"""
    global bot_status
    try:
        # Importer et exécuter le bot
        from bot import main
        bot_status = "🤖 Bot en cours d'exécution"
        main()
    except Exception as e:
        bot_status = f"🔴 Erreur: {str(e)}"
        # Relancer le bot après une pause en cas d'erreur
        time.sleep(60)
        run_bot()

def start_bot():
    """Démarrer le bot dans un thread"""
    global bot_thread
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()

@app.route('/')
def home():
    return f"""
    <html>
        <head>
            <title>Instagram Bot</title>
            <meta charset="utf-8">
            <style>
                body {{ font-family: Arial, sans-serif; margin: 40px; }}
                .status {{ padding: 10px; border-radius: 5px; background: #f0f0f0; }}
            </style>
        </head>
        <body>
            <h1>🤖 Instagram Bot</h1>
            <div class="status">
                <strong>Statut:</strong> {bot_status}
            </div>
            <p>Le bot Instagram fonctionne en arrière-plan.</p>
            <p><a href="/health">Health Check</a> | <a href="/status">Status API</a></p>
        </body>
    </html>
    """

@app.route('/health')
def health():
    return "OK"

@app.route('/status')
def status():
    return {
        "status": "running", 
        "bot_status": bot_status,
        "service": "instagram-bot",
        "timestamp": time.time()
    }

# Démarrer le bot au lancement de l'app
if __name__ == '__main__':
    start_bot()
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
