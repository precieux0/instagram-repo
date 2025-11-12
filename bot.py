from instagrapi import Client
from instagrapi.exceptions import LoginRequired, ClientError
import logging
import time
import random
import json
from datetime import datetime, timedelta
import os
import schedule
from threading import Thread
from time import sleep

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('instagram_bot.log')
    ]
)
logger = logging.getLogger()

# Configuration via variables d'environnement (pour Render)
USERNAME = os.getenv('INSTAGRAM_USERNAME', 'votre_username')
PASSWORD = os.getenv('INSTAGRAM_PASSWORD', 'votre_password')

# CODE DE VÉRIFICATION REÇU PAR SMS
VERIFICATION_CODE = "185709"

class FollowManager:
    def __init__(self, bot):
        self.bot = bot
        self.follow_history_file = "follow_history.json"
        self.load_follow_history()
    
    def load_follow_history(self):
        """Charger l'historique des follows"""
        try:
            with open(self.follow_history_file, 'r') as f:
                self.follow_history = json.load(f)
        except FileNotFoundError:
            self.follow_history = {}
    
    def save_follow_history(self):
        """Sauvegarder l'historique des follows"""
        with open(self.follow_history_file, 'w') as f:
            json.dump(self.follow_history, f, indent=2)
    
    def record_follow(self, user_id, username):
        """Enregistrer un follow"""
        self.follow_history[user_id] = {
            'username': username,
            'follow_date': datetime.now().isoformat(),
            'unfollowed': False
        }
        self.save_follow_history()
    
    def should_unfollow(self, user_id, days_threshold=3):
        """Déterminer si on devrait unfollow"""
        if user_id not in self.follow_history:
            return True
            
        follow_data = self.follow_history[user_id]
        follow_date = datetime.fromisoformat(follow_data['follow_date'])
        days_since_follow = (datetime.now() - follow_date).days
        
        return days_since_follow >= days_threshold and not follow_data['unfollowed']
    
    def mark_unfollowed(self, user_id):
        """Marquer comme unfollowed"""
        if user_id in self.follow_history:
            self.follow_history[user_id]['unfollowed'] = True
            self.follow_history[user_id]['unfollow_date'] = datetime.now().isoformat()
            self.save_follow_history()

class InstagramBot:
    def __init__(self):
        self.cl = Client()
        self.cl.delay_range = [1, 3]
        self.last_action_time = None
        self.min_delay_minutes = 5
        self.session_file = "session.json"
        self.follow_manager = FollowManager(self)
        self.is_connected = False
        
    def random_delay(self, min_seconds=10, max_seconds=30):
        """Délai aléatoire entre les actions"""
        delay = random.randint(min_seconds, max_seconds)
        logger.info(f"⏳ Délai de {delay} secondes...")
        time.sleep(delay)
    
    def action_cooldown(self):
        """Respecte le délai minimum entre les actions principales"""
        if self.last_action_time:
            elapsed = (datetime.now() - self.last_action_time).total_seconds() / 60
            if elapsed < self.min_delay_minutes:
                wait_time = (self.min_delay_minutes - elapsed) * 60
                logger.info(f"⏰ Respect du délai - Attente de {wait_time:.0f}s")
                time.sleep(wait_time)
        
        self.last_action_time = datetime.now()
    
    def login_user(self):
        """Connexion à Instagram avec gestion de la vérification"""
        try:
            logger.info("🔐 Tentative de connexion avec code de vérification...")
            
            # Réinitialiser les paramètres
            self.cl = Client()
            self.cl.delay_range = [1, 3]
            
            # Configuration minimale
            settings = {
                "user_agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1"
            }
            self.cl.set_settings(settings)
            
            # Essayer la session existante
            if os.path.exists(self.session_file):
                try:
                    self.cl.load_settings(self.session_file)
                    logger.info("📁 Session chargée")
                    
                    # Vérifier si la session est valide
                    try:
                        self.cl.get_timeline_feed()
                        logger.info("✅ Connecté via session existante")
                        self.is_connected = True
                        return True
                    except LoginRequired:
                        logger.info("🔄 Session expirée")
                except Exception as e:
                    logger.info(f"❌ Erreur chargement session: {e}")
            
            # CONNEXION AVEC CODE DE VÉRIFICATION
            logger.info(f"🔢 Utilisation du code de vérification: {VERIFICATION_CODE}")
            
            try:
                # Activer la gestion 2FA
                self.cl.handle_2fa = True
                
                # Connexion avec code de vérification
                login_result = self.cl.login(USERNAME, PASSWORD, verification_code=VERIFICATION_CODE)
                
                if login_result:
                    logger.info("✅ Connexion réussie avec code de vérification!")
                    self.cl.dump_settings(self.session_file)
                    self.is_connected = True
                    return True
                else:
                    logger.error("❌ Échec de connexion avec code")
                    return False
                    
            except Exception as login_error:
                logger.error(f"❌ Erreur lors de la connexion avec code: {login_error}")
                
                # Essayer sans code en dernier recours
                logger.info("🔄 Tentative sans code de vérification...")
                try:
                    login_result = self.cl.login(USERNAME, PASSWORD)
                    if login_result:
                        logger.info("✅ Connexion réussie sans code!")
                        self.cl.dump_settings(self.session_file)
                        self.is_connected = True
                        return True
                except Exception as final_error:
                    logger.error(f"💥 Échec final: {final_error}")
                    return False
                
        except Exception as e:
            logger.error(f"💥 Erreur critique de connexion: {e}")
            return False
    
    def get_timeline_feed_safe(self, amount=10):
        """Récupérer le feed de manière sécurisée"""
        try:
            # Méthode sans paramètre amount qui cause l'erreur
            feed = self.cl.get_timeline_feed()
            # Limiter manuellement le nombre de posts
            return feed[:amount] if feed else []
        except Exception as e:
            logger.error(f"❌ Erreur récupération feed: {e}")
            return []
    
    def like_post(self, media_id):
        """Like une publication"""
        try:
            self.action_cooldown()
            result = self.cl.media_like(media_id)
            logger.info(f"❤️ Publication likée")
            self.random_delay(5, 15)
            return result
        except Exception as e:
            logger.error(f"❌ Erreur like: {e}")
            return False
    
    def follow_user(self, user_id):
        """Suivre un utilisateur"""
        try:
            self.action_cooldown()
            result = self.cl.user_follow(user_id)
            logger.info(f"👤 Utilisateur suivi")
            self.follow_manager.record_follow(user_id, f"user_{user_id}")
            self.random_delay(20, 40)
            return result
        except Exception as e:
            logger.error(f"❌ Erreur follow: {e}")
            return False
    
    def get_reels(self, amount=3):
        """Récupérer des reels populaires"""
        try:
            self.action_cooldown()
            reels = self.cl.clips_popular(amount=amount)
            logger.info(f"🎥 {len(reels)} reels récupérés")
            return reels
        except Exception as e:
            logger.error(f"❌ Erreur récupération reels: {e}")
            return []
    
    def watch_reel(self, media_id):
        """Simuler le visionnage d'un reel"""
        try:
            logger.info(f"📺 Visionnage reel")
            watch_time = random.randint(5, 15)
            time.sleep(watch_time)
            return True
        except Exception as e:
            logger.error(f"❌ Erreur visionnage reel: {e}")
            return False
    
    def simple_activity_session(self):
        """Session d'activités simples et sécurisées"""
        try:
            if not self.is_connected:
                logger.error("❌ Non connecté à Instagram")
                return False
            
            logger.info("🚀 Début session d'activités")
            
            # 1. Vérifier le feed (méthode corrigée)
            feed = self.get_timeline_feed_safe(5)
            logger.info(f"📱 Feed chargé: {len(feed)} posts")
            
            # 2. Like 1-2 posts
            if feed:
                for post in feed[:2]:
                    self.like_post(post.id)
                    break  # Un like seulement pour tester
            
            self.random_delay(10, 20)
            
            # 3. Voir des reels
            reels = self.get_reels(2)
            for reel in reels:
                self.watch_reel(reel.id)
                if random.random() > 0.5:  # 50% chance de liker
                    self.like_post(reel.id)
                break  # Un reel seulement pour tester
            
            # 4. Follow 1 utilisateur suggéré
            try:
                suggestions = self.cl.suggested_users(amount=3)
                for user in suggestions.users[:1]:
                    if not self.cl.user_friendship(user.pk).following:
                        self.follow_user(user.pk)
                        break  # Un follow seulement
            except Exception as e:
                logger.warning(f"⚠️ Impossible de suivre: {e}")
            
            logger.info("✅ Session terminée avec succès")
            return True
            
        except Exception as e:
            logger.error(f"❌ Erreur session: {e}")
            return False
    
    def simulate_human_activity(self, duration_hours=1):
        """Simule une présence humaine"""
        logger.info(f"🤖 Début simulation pour {duration_hours}h")
        
        start_time = datetime.now()
        end_time = start_time + timedelta(hours=duration_hours)
        session_count = 0
        
        while datetime.now() < end_time and session_count < 3:
            try:
                session_count += 1
                logger.info(f"🔄 Session {session_count}")
                
                success = self.simple_activity_session()
                
                if success:
                    logger.info(f"✅ Session {session_count} réussie")
                else:
                    logger.warning(f"⚠️ Session {session_count} échouée")
                
                # Pause entre les sessions (10-20 minutes)
                if datetime.now() < end_time and session_count < 3:
                    pause_time = random.randint(600, 1200)
                    logger.info(f"💤 Pause de {pause_time//60} minutes")
                    time.sleep(pause_time)
                
            except Exception as e:
                logger.error(f"❌ Erreur activité: {e}")
                time.sleep(300)
        
        logger.info(f"🎯 Simulation terminée: {session_count} sessions")

def run_scheduled_bot():
    """Fonction planifiée pour exécuter le bot"""
    bot = InstagramBot()
    
    try:
        logger.info("🚀 Démarrage du bot Instagram")
        
        # Connexion
        if bot.login_user():
            # Session d'activités
            bot.simulate_human_activity(duration_hours=1)
            logger.info("✅ Session terminée avec succès")
        else:
            logger.error("❌ Impossible de se connecter, session annulée")
        
    except Exception as e:
        logger.error(f"❌ Erreur critique: {e}")

def schedule_bot():
    """Planification des tâches du bot"""
    # Routines quotidiennes
    schedule.every().day.at("10:00").do(run_scheduled_bot)
    schedule.every().day.at("16:00").do(run_scheduled_bot)
    schedule.every().day.at("20:00").do(run_scheduled_bot)
    
    logger.info("📅 Planificateur démarré")
    
    while True:
        schedule.run_pending()
        time.sleep(60)

def main():
    """Fonction principale"""
    if USERNAME == 'votre_username' or PASSWORD == 'votre_password':
        logger.error("❌ Configurer INSTAGRAM_USERNAME et INSTAGRAM_PASSWORD")
        exit(1)
    
    logger.info("🤖 Bot Instagram démarré")
    
    # Démarrer le planificateur
    scheduler_thread = Thread(target=schedule_bot, daemon=True)
    scheduler_thread.start()
    
    # Session immédiate
    run_scheduled_bot()
    
    # Maintenir actif
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        logger.info("👋 Arrêt du bot")

if __name__ == "__main__":
    main()
