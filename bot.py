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
        self.cl.delay_range = [5, 10]
        self.last_action_time = None
        self.min_delay_minutes = 8
        self.session_file = "session.json"
        self.follow_manager = FollowManager(self)
        
    def random_delay(self, min_seconds=30, max_seconds=120):
        """Délai aléatoire entre les actions pour simuler un comportement humain"""
        delay = random.randint(min_seconds, max_seconds)
        logger.info(f"⏳ Délai de {delay} secondes...")
        time.sleep(delay)
    
    def action_cooldown(self):
        """Respecte le délai minimum de 8 minutes entre les actions principales"""
        if self.last_action_time:
            elapsed = (datetime.now() - self.last_action_time).total_seconds() / 60
            if elapsed < self.min_delay_minutes:
                wait_time = (self.min_delay_minutes - elapsed) * 60
                logger.info(f"⏰ Respect du délai de {self.min_delay_minutes}min - Attente de {wait_time:.0f}s")
                time.sleep(wait_time)
        
        self.last_action_time = datetime.now()
    
    def login_user(self):
        """Connexion à Instagram avec gestion de session"""
        session = self.cl.load_settings(self.session_file)
        
        login_via_session = False
        login_via_pw = False

        if session:
            try:
                self.cl.set_settings(session)
                self.cl.login(USERNAME, PASSWORD)

                # Vérification de la validité de la session
                try:
                    self.cl.get_timeline_feed()
                    login_via_session = True
                    logger.info("✅ Connecté via session existante")
                except LoginRequired:
                    logger.info("❌ Session invalide, reconnexion nécessaire")
                    old_session = self.cl.get_settings()
                    self.cl.set_settings({})
                    self.cl.set_uuids(old_session["uuids"])
                    self.cl.login(USERNAME, PASSWORD)
                    login_via_session = True
            except Exception as e:
                logger.info(f"❌ Échec connexion par session: {e}")

        if not login_via_session:
            try:
                logger.info(f"🔐 Tentative de connexion avec: {USERNAME}")
                if self.cl.login(USERNAME, PASSWORD):
                    login_via_pw = True
                    logger.info("✅ Connecté via mot de passe")
                    self.cl.dump_settings(self.session_file)
            except Exception as e:
                logger.info(f"❌ Échec connexion par mot de passe: {e}")

        if not login_via_pw and not login_via_session:
            raise Exception("❌ Impossible de se connecter")
    
    def like_post(self, media_id):
        """Like une publication"""
        try:
            self.action_cooldown()
            result = self.cl.media_like(media_id)
            logger.info(f"❤️ Publication likée: {media_id}")
            self.random_delay(10, 30)
            return result
        except Exception as e:
            logger.error(f"❌ Erreur like: {e}")
            return False
    
    def comment_post(self, media_id, comment_text):
        """Commenter une publication"""
        try:
            self.action_cooldown()
            if len(comment_text) < 2 or len(comment_text) > 200:
                logger.warning("⚠️ Commentaire trop court ou trop long")
                return False
            
            result = self.cl.media_comment(media_id, comment_text)
            logger.info(f"💬 Commentaire ajouté: {comment_text}")
            self.random_delay(15, 45)
            return result
        except Exception as e:
            logger.error(f"❌ Erreur commentaire: {e}")
            return False
    
    def follow_user(self, user_id):
        """Suivre un utilisateur"""
        try:
            self.action_cooldown()
            result = self.cl.user_follow(user_id)
            logger.info(f"👤 Utilisateur suivi: {user_id}")
            self.follow_manager.record_follow(user_id, f"user_{user_id}")
            self.random_delay(30, 60)
            return result
        except Exception as e:
            logger.error(f"❌ Erreur follow: {e}")
            return False
    
    def unfollow_user(self, user_id):
        """Ne plus suivre un utilisateur"""
        try:
            self.action_cooldown()
            result = self.cl.user_unfollow(user_id)
            logger.info(f"🚫 Utilisateur unfollow: {user_id}")
            self.follow_manager.mark_unfollowed(user_id)
            self.random_delay(30, 90)
            return result
        except Exception as e:
            logger.error(f"❌ Erreur unfollow: {e}")
            return False
    
    def unfollow_non_followers(self, max_unfollows=10):
        """Unfollow les utilisateurs qui ne vous suivent pas en retour"""
        try:
            self.action_cooldown()
            
            my_user_id = self.cl.user_id_from_username(USERNAME)
            following = self.cl.user_following(my_user_id)
            followers = self.cl.user_followers(my_user_id)
            
            followers_ids = set(followers.keys())
            unfollow_count = 0
            
            for user_id, user_info in following.items():
                if unfollow_count >= max_unfollows:
                    break
                    
                if user_id not in followers_ids:
                    if self.follow_manager.should_unfollow(user_id, days_threshold=3):
                        self.unfollow_user(user_id)
                        unfollow_count += 1
                        logger.info(f"🚫 Unfollow non-réciproque: {user_info.username}")
                        
            logger.info(f"✅ {unfollow_count} unfollows non-réciproques effectués")
            return unfollow_count
            
        except Exception as e:
            logger.error(f"❌ Erreur unfollow non-followers: {e}")
            return 0
    
    def get_reels(self, amount=5):
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
            logger.info(f"📺 Visionnage reel: {media_id}")
            watch_time = random.randint(10, 30)
            time.sleep(watch_time)
            return True
        except Exception as e:
            logger.error(f"❌ Erreur visionnage reel: {e}")
            return False
    
    def interact_with_reel(self, media_id):
        """Interagir avec un reel (like + commentaire possible)"""
        try:
            if random.random() > 0.3:
                self.like_post(media_id)
            
            if random.random() > 0.8:
                comments = [
                    "Super content! 👍",
                    "Très intéressant!",
                    "J'adore 😍",
                    "Top qualité!",
                    "Merci pour le partage!",
                    "Incroyable! 👏",
                    "Bravo pour ce contenu!",
                    "Très utile, merci!"
                ]
                comment = random.choice(comments)
                self.comment_post(media_id, comment)
            
            return True
        except Exception as e:
            logger.error(f"❌ Erreur interaction reel: {e}")
            return False
    
    def follow_suggested_users(self, max_follows=15):
        """Follow des utilisateurs suggérés avec limite"""
        try:
            self.action_cooldown()
            suggestions = self.cl.suggested_users(amount=20)
            follow_count = 0
            
            for user in suggestions.users:
                if follow_count >= max_follows:
                    break
                    
                if not self.cl.user_friendship(user.pk).following:
                    self.follow_user(user.pk)
                    follow_count += 1
                    
            return follow_count
            
        except Exception as e:
            logger.error(f"❌ Erreur follow suggérés: {e}")
            return 0
    
    def daily_follow_unfollow_routine(self, max_follows=15, max_unfollows=10):
        """Routine quotidienne de gestion follow/unfollow"""
        logger.info("🔄 Début routine follow/unfollow quotidienne")
        
        unfollowed_count = self.unfollow_non_followers(max_unfollows=max_unfollows)
        
        self.random_delay(300, 600)
        
        followed_count = self.follow_suggested_users(max_follows=max_follows)
        
        logger.info(f"📊 Routine terminée: {unfollowed_count} unfollows, {followed_count} follows")
        return unfollowed_count, followed_count
    
    def scroll_timeline(self):
        """Simule le scroll du feed"""
        logger.info("📱 Scroll du feed...")
        feed = self.cl.get_timeline_feed(amount=10)
        for item in feed[:5]:
            time.sleep(random.randint(5, 15))
    
    def watch_reels_session(self):
        """Session de visionnage de reels"""
        logger.info("🎥 Session reels...")
        reels = self.get_reels(3)
        for reel in reels:
            self.watch_reel(reel.id)
            if random.random() > 0.5:
                self.interact_with_reel(reel.id)
    
    def like_random_posts(self):
        """Like des posts aléatoires"""
        logger.info("❤️ Session de likes...")
        feed = self.cl.get_timeline_feed(amount=10)
        for post in random.sample(feed, min(3, len(feed))):
            self.like_post(post.id)
    
    def comment_random_posts(self):
        """Commenter des posts aléatoires"""
        logger.info("💬 Session commentaires...")
        feed = self.cl.get_timeline_feed(amount=10)
        for post in random.sample(feed, min(2, len(feed))):
            comments = ["Super!", "J'aime!", "👍", "Intéressant!"]
            self.comment_post(post.id, random.choice(comments))
    
    def simulate_human_activity(self, duration_hours=2):
        """Simule une présence humaine pendant plusieurs heures"""
        logger.info(f"🤖 Début simulation d'activité pour {duration_hours}h")
        
        start_time = datetime.now()
        end_time = start_time + timedelta(hours=duration_hours)
        
        while datetime.now() < end_time:
            try:
                action = random.choices(
                    ['scroll_feed', 'watch_reels', 'like_posts', 'follow_users', 'comment'],
                    weights=[0.3, 0.3, 0.2, 0.1, 0.1]
                )[0]
                
                if action == 'scroll_feed':
                    self.scroll_timeline()
                elif action == 'watch_reels':
                    self.watch_reels_session()
                elif action == 'like_posts':
                    self.like_random_posts()
                elif action == 'follow_users':
                    self.follow_suggested_users(5)
                elif action == 'comment':
                    self.comment_random_posts()
                
                long_break = random.randint(600, 1800)
                logger.info(f"💤 Pause longue de {long_break//60}min")
                time.sleep(long_break)
                
            except Exception as e:
                logger.error(f"❌ Erreur activité: {e}")
                time.sleep(300)

def run_scheduled_bot():
    """Fonction planifiée pour exécuter le bot"""
    bot = InstagramBot()
    
    try:
        logger.info("🚀 Démarrage du bot Instagram planifié")
        bot.login_user()
        
        # Routine quotidienne follow/unfollow
        bot.daily_follow_unfollow_routine(max_follows=15, max_unfollows=10)
        
        # Simulation d'activité humaine
        bot.simulate_human_activity(duration_hours=2)
        
        logger.info("✅ Session planifiée terminée avec succès")
        
    except Exception as e:
        logger.error(f"❌ Erreur critique dans la session planifiée: {e}")

def schedule_bot():
    """Planification des tâches du bot"""
    # Routine quotidienne à 10h
    schedule.every().day.at("10:00").do(run_scheduled_bot)
    
    # Routine supplémentaire à 16h
    schedule.every().day.at("16:00").do(run_scheduled_bot)
    
    logger.info("📅 Planificateur démarré - routines à 10h et 16h")
    
    while True:
        schedule.run_pending()
        time.sleep(60)  # Vérifier toutes les minutes

if __name__ == "__main__":
    # Vérification des variables d'environnement
    if USERNAME == 'votre_username' or PASSWORD == 'votre_password':
        logger.error("❌ Veuillez configurer INSTAGRAM_USERNAME et INSTAGRAM_PASSWORD")
        exit(1)
    
    logger.info("🤖 Démarrage du Bot Instagram")
    
    # Démarrer le planificateur dans un thread séparé
    scheduler_thread = Thread(target=schedule_bot, daemon=True)
    scheduler_thread.start()
    
    # Garder le script actif
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        logger.info("👋 Arrêt du bot Instagram")
