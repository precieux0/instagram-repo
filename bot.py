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

# Code de vérification reçu (à modifier si nécessaire)
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
        self.cl.delay_range = [1, 3]  # Réduit pour les tests
        self.last_action_time = None
        self.min_delay_minutes = 5    # Réduit pour les tests
        self.session_file = "session.json"
        self.follow_manager = FollowManager(self)
        
    def random_delay(self, min_seconds=10, max_seconds=30):
        """Délai aléatoire entre les actions pour simuler un comportement humain"""
        delay = random.randint(min_seconds, max_seconds)
        logger.info(f"⏳ Délai de {delay} secondes...")
        time.sleep(delay)
    
    def action_cooldown(self):
        """Respecte le délai minimum entre les actions principales"""
        if self.last_action_time:
            elapsed = (datetime.now() - self.last_action_time).total_seconds() / 60
            if elapsed < self.min_delay_minutes:
                wait_time = (self.min_delay_minutes - elapsed) * 60
                logger.info(f"⏰ Respect du délai de {self.min_delay_minutes}min - Attente de {wait_time:.0f}s")
                time.sleep(wait_time)
        
        self.last_action_time = datetime.now()
    
    def login_user(self):
        """Connexion à Instagram avec gestion de la vérification"""
        try:
            # Configuration pour éviter les blocages
            settings = {
                "user_agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1",
                "device_settings": {
                    "app_version": "210.0.0.0.0",
                    "android_version": 29,
                    "android_release": "10.0",
                    "dpi": "480dpi",
                    "resolution": "1080x1920",
                    "manufacturer": "Samsung",
                    "device": "SM-G973F",
                    "model": "Galaxy S10",
                    "cpu": "exynos9820",
                    "version_code": "314665256"
                }
            }
            self.cl.set_settings(settings)
            
            # Essayer de charger la session existante
            if os.path.exists(self.session_file):
                try:
                    session = self.cl.load_settings(self.session_file)
                    self.cl.set_settings(session)
                    self.cl.login(USERNAME, PASSWORD)
                    
                    # Vérifier si la session est valide
                    self.cl.get_timeline_feed()
                    logger.info("✅ Connecté via session existante")
                    return True
                except Exception as e:
                    logger.info(f"🔄 Session invalide: {e}")
            
            # CONNEXION AVEC GESTION DE LA VÉRIFICATION
            logger.info("🔐 Tentative de connexion avec gestion de vérification...")
            
            # Méthode avec code de vérification intégré
            try:
                # Essayer sans code d'abord
                self.cl.login(USERNAME, PASSWORD)
            except Exception as e:
                if "checkpoint" in str(e).lower() or "verification" in str(e).lower():
                    logger.info("📱 Instagram demande une vérification")
                    logger.info(f"🔢 Utilisation du code: {VERIFICATION_CODE}")
                    
                    try:
                        # Utiliser le code de vérification
                        self.cl.handle_2fa = True
                        self.cl.login(USERNAME, PASSWORD, verification_code=VERIFICATION_CODE)
                        logger.info("✅ Connexion réussie avec code de vérification")
                    except Exception as verify_error:
                        logger.error(f"❌ Erreur avec le code de vérification: {verify_error}")
                        return False
                else:
                    logger.error(f"❌ Erreur de connexion: {e}")
                    return False
            
            # Sauvegarder la session pour les prochaines connexions
            self.cl.dump_settings(self.session_file)
            logger.info("💾 Session sauvegardée")
            return True
            
        except Exception as e:
            logger.error(f"💥 Erreur critique de connexion: {e}")
            return False
    
    def safe_activity(self, activity_func, activity_name):
        """Exécuter une activité de manière sécurisée"""
        try:
            self.action_cooldown()
            result = activity_func()
            logger.info(f"✅ {activity_name} terminé avec succès")
            return result
        except Exception as e:
            logger.error(f"❌ Erreur pendant {activity_name}: {e}")
            return False
    
    def like_post(self, media_id):
        """Like une publication"""
        try:
            result = self.cl.media_like(media_id)
            logger.info(f"❤️ Publication likée")
            self.random_delay(5, 15)
            return result
        except Exception as e:
            logger.error(f"❌ Erreur like: {e}")
            return False
    
    def comment_post(self, media_id, comment_text):
        """Commenter une publication"""
        try:
            if len(comment_text) < 2 or len(comment_text) > 200:
                logger.warning("⚠️ Commentaire trop court ou trop long")
                return False
            
            result = self.cl.media_comment(media_id, comment_text)
            logger.info(f"💬 Commentaire ajouté")
            self.random_delay(10, 20)
            return result
        except Exception as e:
            logger.error(f"❌ Erreur commentaire: {e}")
            return False
    
    def follow_user(self, user_id):
        """Suivre un utilisateur"""
        try:
            result = self.cl.user_follow(user_id)
            logger.info(f"👤 Utilisateur suivi")
            self.follow_manager.record_follow(user_id, f"user_{user_id}")
            self.random_delay(20, 40)
            return result
        except Exception as e:
            logger.error(f"❌ Erreur follow: {e}")
            return False
    
    def unfollow_user(self, user_id):
        """Ne plus suivre un utilisateur"""
        try:
            result = self.cl.user_unfollow(user_id)
            logger.info(f"🚫 Utilisateur unfollow")
            self.follow_manager.mark_unfollowed(user_id)
            self.random_delay(20, 40)
            return result
        except Exception as e:
            logger.error(f"❌ Erreur unfollow: {e}")
            return False
    
    def get_reels(self, amount=3):
        """Récupérer des reels populaires"""
        try:
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
            logger.info("🚀 Début session d'activités")
            
            # 1. Vérifier le feed
            feed = self.cl.get_timeline_feed(amount=5)
            logger.info(f"📱 Feed chargé: {len(feed)} posts")
            
            # 2. Like 1-2 posts
            if feed:
                for post in feed[:2]:
                    self.like_post(post.id)
            
            self.random_delay(10, 20)
            
            # 3. Voir des reels
            reels = self.get_reels(2)
            for reel in reels:
                self.watch_reel(reel.id)
                if random.random() > 0.5:  # 50% chance de liker
                    self.like_post(reel.id)
            
            # 4. Follow 1-2 utilisateurs suggérés
            suggestions = self.cl.suggested_users(amount=5)
            follows = 0
            for user in suggestions.users[:2]:
                if not self.cl.user_friendship(user.pk).following:
                    self.follow_user(user.pk)
                    follows += 1
                    if follows >= 2:
                        break
            
            logger.info(f"📊 Session terminée: {follows} follows")
            return True
            
        except Exception as e:
            logger.error(f"❌ Erreur session: {e}")
            return False
    
    def simulate_human_activity(self, duration_hours=2):
        """Simule une présence humaine pendant plusieurs heures"""
        logger.info(f"🤖 Début simulation d'activité pour {duration_hours}h")
        
        start_time = datetime.now()
        end_time = start_time + timedelta(hours=duration_hours)
        session_count = 0
        
        while datetime.now() < end_time and session_count < 6:  # Max 6 sessions
            try:
                session_count += 1
                success = self.simple_activity_session()
                
                if success:
                    logger.info(f"✅ Session {session_count} réussie")
                else:
                    logger.warning(f"⚠️ Session {session_count} échouée")
                
                # Pause entre les sessions (20-40 minutes)
                pause_time = random.randint(1200, 2400)
                logger.info(f"💤 Pause de {pause_time//60} minutes")
                time.sleep(pause_time)
                
            except Exception as e:
                logger.error(f"❌ Erreur activité: {e}")
                time.sleep(300)  # Attendre 5 minutes en cas d'erreur
        
        logger.info(f"🎯 Simulation terminée: {session_count} sessions effectuées")

def run_scheduled_bot():
    """Fonction planifiée pour exécuter le bot"""
    bot = InstagramBot()
    
    try:
        logger.info("🚀 Démarrage du bot Instagram")
        
        # Connexion
        if bot.login_user():
            # Session d'activités
            bot.simulate_human_activity(duration_hours=2)
            logger.info("✅ Session planifiée terminée avec succès")
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
    
    logger.info("📅 Planificateur démarré - routines à 10h, 16h et 20h")
    
    while True:
        schedule.run_pending()
        time.sleep(60)

def main():
    """Fonction principale pour l'exécution du bot"""
    # Vérification des variables d'environnement
    if USERNAME == 'votre_username' or PASSWORD == 'votre_password':
        logger.error("❌ Veuillez configurer INSTAGRAM_USERNAME et INSTAGRAM_PASSWORD")
        exit(1)
    
    logger.info("🤖 Démarrage du Bot Instagram")
    
    # Démarrer le planificateur dans un thread séparé
    scheduler_thread = Thread(target=schedule_bot, daemon=True)
    scheduler_thread.start()
    
    # Exécuter une session immédiate
    run_scheduled_bot()
    
    # Garder le script actif
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        logger.info("👋 Arrêt du bot Instagram")

if __name__ == "__main__":
    main()
