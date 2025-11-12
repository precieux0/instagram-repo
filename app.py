from flask import Flask
import threading
import os
import time
from datetime import datetime

app = Flask(__name__)

# Variable pour suivre l'état du bot
bot_status = "🟢 En cours de démarrage"
bot_thread = None

def run_bot():
    """Fonction pour exécuter le bot en arrière-plan"""
    global bot_status
    try:
        # Importer et exécuter le bot
        from bot import InstagramBot
        bot_status = "🤖 Bot en cours d'exécution"
        
        # Créer une instance et démarrer
        bot = InstagramBot()
        
        # Vérifier les variables d'environnement
        username = os.getenv('INSTAGRAM_USERNAME')
        password = os.getenv('INSTAGRAM_PASSWORD')
        
        if not username or not password:
            bot_status = "🔴 Variables d'environnement manquantes"
            return
        
        # Connexion
        bot.login_user()
        bot_status = "✅ Connecté à Instagram - Activités en cours"
        
        # Démarrer les activités (version sécurisée)
        start_time = datetime.now()
        activity_count = 0
        
        while True:
            try:
                # Exécuter une activité
                activity_count += 1
                bot.simulate_human_activity(duration_hours=1)  # 1 heure d'activité
                
                bot_status = f"✅ Activité {activity_count} terminée - Prochaine dans 1h"
                
                # Attendre 1 heure entre les sessions
                time.sleep(3600)
                
            except Exception as e:
                bot_status = f"🔴 Erreur activité: {str(e)}"
                time.sleep(300)  # Attendre 5 minutes avant de réessayer
                
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
            <meta http-equiv="refresh" content="60">  <!-- Auto-refresh chaque minute -->
            <style>
                body {{ font-family: Arial, sans-serif; margin: 40px; }}
                .status {{ padding: 10px; border-radius: 5px; background: #f0f0f0; }}
                .online {{ color: green; }}
                .error {{ color: red; }}
                .timestamp {{ color: #666; font-size: 12px; }}
            </style>
        </head>
        <body>
            <h1>🤖 Instagram Bot</h1>
            <div class="status">
                <strong>Statut:</strong> <span class="{'online' if '✅' in bot_status or '🤖' in bot_status else 'error'}">{bot_status}</span>
            </div>
            <p>Le bot Instagram fonctionne en arrière-plan.</p>
            <p class="timestamp">Dernière mise à jour: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
            <p>
                <a href="/health">Health Check</a> | 
                <a href="/status">Status API</a> |
                <a href="/ping">Ping</a>
            </p>
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
        "timestamp": datetime.now().isoformat()
    }

@app.route('/ping')
def ping():
    """Route ULTRA-LÉGÈRE pour UptimeRobot"""
    return "pong"

# Démarrer le bot au lancement de l'app
if __name__ == '__main__':
    start_bot()
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
