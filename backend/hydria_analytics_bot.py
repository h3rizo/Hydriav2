#!/usr/bin/env python3
"""
Bot Telegram d'analyse des données Hydria
Analyse le planning des employés, les paiements, la consommation d'eau et les congés
"""

import asyncio
import logging
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
import psycopg2
from psycopg2.extras import RealDictCursor

# Configuration
TELEGRAM_TOKEN = "VOTRE_TOKEN_BOT_TELEGRAM"  # À configurer avec votre token
ADMIN_IDS = [123456789]  # À configurer avec votre ID Telegram

# Configuration de la base de données PostgreSQL locale
DB_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'database': 'hydria',
    'user': 'hydria',
    'password': 'hydria_password_2025'
}

# Configuration du logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def get_db_connection():
    """Créer une connexion à la base de données"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        return conn
    except Exception as e:
        logger.error(f"Erreur de connexion à la DB: {e}")
        return None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Commande /start"""
    welcome_message = """
🤖 *Bot d'analyse Hydria*

Bienvenue ! Je peux vous fournir des analyses sur :

📅 *Planning & Employés*
/planning_today - Planning aujourd'hui
/planning_week - Planning de la semaine
/employes_actifs - Liste des employés actifs
/conges - Congés en cours et à venir

💰 *Paiements*
/paiements_today - Paiements du jour
/paiements_month - Paiements du mois
/impayes - Factures impayées
/revenus - Revenus du mois

💧 *Consommation d'eau*
/conso_today - Relevés du jour
/conso_month - Consommation du mois
/top_consommateurs - Top 10 consommateurs

📊 *Statistiques*
/stats - Vue d'ensemble générale
"""
    await update.message.reply_text(welcome_message, parse_mode='Markdown')

async def planning_today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Planning des employés aujourd'hui"""
    conn = get_db_connection()
    if not conn:
        await update.message.reply_text("❌ Erreur de connexion à la base de données")
        return

    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        today = datetime.now().date()

        query = """
            SELECT e.surnom, e.nom, e.prenom, a.nom as nom_activite, p.date
            FROM plannings p
            JOIN employes e ON p.employe_uuid_id = e.id
            LEFT JOIN activites a ON p.activite_uuid_id = a.id
            WHERE DATE(p.date) = %s
            ORDER BY e.surnom
        """

        cur.execute(query, (today,))
        results = cur.fetchall()

        if not results:
            await update.message.reply_text(f"📅 Aucun planning trouvé pour aujourd'hui ({today})")
            return

        message = f"📅 *Planning du {today.strftime('%d/%m/%Y')}*\n\n"
        for row in results:
            nom_complet = f"{row['surnom'] or row['prenom']} {row['nom']}"
            activite = row['nom_activite'] or 'Non définie'
            message += f"👤 {nom_complet}\n   ➜ {activite}\n\n"

        await update.message.reply_text(message, parse_mode='Markdown')

    except Exception as e:
        logger.error(f"Erreur planning_today: {e}")
        await update.message.reply_text(f"❌ Erreur: {str(e)}")
    finally:
        conn.close()

async def planning_week(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Planning de la semaine"""
    conn = get_db_connection()
    if not conn:
        await update.message.reply_text("❌ Erreur de connexion à la base de données")
        return

    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        today = datetime.now().date()
        week_end = today + timedelta(days=7)

        query = """
            SELECT e.surnom, e.nom, a.nom as nom_activite, p.date
            FROM plannings p
            JOIN employes e ON p.employe_uuid_id = e.id
            LEFT JOIN activites a ON p.activite_uuid_id = a.id
            WHERE DATE(p.date) BETWEEN %s AND %s
            ORDER BY p.date, e.surnom
        """

        cur.execute(query, (today, week_end))
        results = cur.fetchall()

        if not results:
            await update.message.reply_text("📅 Aucun planning trouvé pour les 7 prochains jours")
            return

        message = f"📅 *Planning du {today.strftime('%d/%m')} au {week_end.strftime('%d/%m/%Y')}*\n\n"

        current_date = None
        for row in results:
            date = row['date'].date() if hasattr(row['date'], 'date') else row['date']
            if current_date != date:
                current_date = date
                message += f"\n📆 *{date.strftime('%d/%m/%Y')}*\n"

            nom = row['surnom'] or row['nom']
            activite = row['nom_activite'] or 'Non définie'
            message += f"  • {nom}: {activite}\n"

        await update.message.reply_text(message, parse_mode='Markdown')

    except Exception as e:
        logger.error(f"Erreur planning_week: {e}")
        await update.message.reply_text(f"❌ Erreur: {str(e)}")
    finally:
        conn.close()

async def employes_actifs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Liste des employés actifs"""
    conn = get_db_connection()
    if not conn:
        await update.message.reply_text("❌ Erreur de connexion à la base de données")
        return

    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)

        query = """
            SELECT surnom, nom, prenom, poste_id
            FROM employes
            WHERE date_debauchage IS NULL
            ORDER BY surnom
        """

        cur.execute(query)
        results = cur.fetchall()

        message = f"👥 *Employés actifs* ({len(results)})\n\n"
        for row in results:
            nom_complet = f"{row['surnom'] or row['prenom']} {row['nom']}"
            message += f"• {nom_complet}\n"

        await update.message.reply_text(message, parse_mode='Markdown')

    except Exception as e:
        logger.error(f"Erreur employes_actifs: {e}")
        await update.message.reply_text(f"❌ Erreur: {str(e)}")
    finally:
        conn.close()

async def conges(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Congés en cours et à venir"""
    conn = get_db_connection()
    if not conn:
        await update.message.reply_text("❌ Erreur de connexion à la base de données")
        return

    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        today = datetime.now().date()

        query = """
            SELECT e.surnom, e.nom, dc.date_debut, dc.date_fin, dc.type_demande, dc.statut
            FROM demandes_conges dc
            JOIN employes e ON dc.employe_id = e.id
            WHERE dc.date_fin >= %s
            AND dc.statut IN ('validee_chef', 'validee_directeur')
            ORDER BY dc.date_debut
        """

        cur.execute(query, (today,))
        results = cur.fetchall()

        if not results:
            await update.message.reply_text("🏖️ Aucun congé en cours ou à venir")
            return

        message = f"🏖️ *Congés en cours et à venir*\n\n"
        for row in results:
            nom = row['surnom'] or row['nom']
            debut = row['date_debut'].strftime('%d/%m/%Y')
            fin = row['date_fin'].strftime('%d/%m/%Y')
            type_conge = row['type_demande']
            message += f"• {nom}\n  {debut} → {fin}\n  Type: {type_conge}\n\n"

        await update.message.reply_text(message, parse_mode='Markdown')

    except Exception as e:
        logger.error(f"Erreur conges: {e}")
        await update.message.reply_text(f"❌ Erreur: {str(e)}")
    finally:
        conn.close()

async def paiements_today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Paiements du jour"""
    conn = get_db_connection()
    if not conn:
        await update.message.reply_text("❌ Erreur de connexion à la base de données")
        return

    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        today = datetime.now().date()

        # Paiements forfaitaires
        query1 = """
            SELECT COUNT(*) as count, COALESCE(SUM(montant), 0) as total
            FROM paiements_forfaitaires
            WHERE DATE(date_paiement) = %s
        """
        cur.execute(query1, (today,))
        forfait = cur.fetchone()

        # Paiements volumétriques (relevés avec numeroDiameX du jour)
        query2 = """
            SELECT COUNT(*) as count, COALESCE(SUM(montant), 0) as total
            FROM releves
            WHERE "numeroDiameX" IS NOT NULL
            AND DATE(datepaiement) = %s
        """
        cur.execute(query2, (today,))
        volume = cur.fetchone()

        total_count = forfait['count'] + volume['count']
        total_montant = float(forfait['total']) + float(volume['total'])

        message = f"💰 *Paiements du {today.strftime('%d/%m/%Y')}*\n\n"
        message += f"Forfaitaire: {forfait['count']} ({forfait['total']:,.0f} Ar)\n"
        message += f"Volumétrique: {volume['count']} ({volume['total']:,.0f} Ar)\n\n"
        message += f"*Total: {total_count} ({total_montant:,.0f} Ar)*"

        await update.message.reply_text(message, parse_mode='Markdown')

    except Exception as e:
        logger.error(f"Erreur paiements_today: {e}")
        await update.message.reply_text(f"❌ Erreur: {str(e)}")
    finally:
        conn.close()

async def paiements_month(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Paiements du mois"""
    conn = get_db_connection()
    if not conn:
        await update.message.reply_text("❌ Erreur de connexion à la base de données")
        return

    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        now = datetime.now()

        # Paiements forfaitaires du mois
        query1 = """
            SELECT COUNT(*) as count, COALESCE(SUM(montant), 0) as total
            FROM paiements_forfaitaires
            WHERE EXTRACT(MONTH FROM date_paiement) = %s
            AND EXTRACT(YEAR FROM date_paiement) = %s
        """
        cur.execute(query1, (now.month, now.year))
        forfait = cur.fetchone()

        # Paiements volumétriques du mois
        query2 = """
            SELECT COUNT(*) as count, COALESCE(SUM(montant), 0) as total
            FROM releves
            WHERE "numeroDiameX" IS NOT NULL
            AND EXTRACT(MONTH FROM datepaiement) = %s
            AND EXTRACT(YEAR FROM datepaiement) = %s
        """
        cur.execute(query2, (now.month, now.year))
        volume = cur.fetchone()

        total_count = forfait['count'] + volume['count']
        total_montant = float(forfait['total']) + float(volume['total'])

        message = f"💰 *Paiements de {now.strftime('%B %Y')}*\n\n"
        message += f"Forfaitaire: {forfait['count']} ({forfait['total']:,.0f} Ar)\n"
        message += f"Volumétrique: {volume['count']} ({volume['total']:,.0f} Ar)\n\n"
        message += f"*Total: {total_count} ({total_montant:,.0f} Ar)*"

        await update.message.reply_text(message, parse_mode='Markdown')

    except Exception as e:
        logger.error(f"Erreur paiements_month: {e}")
        await update.message.reply_text(f"❌ Erreur: {str(e)}")
    finally:
        conn.close()

async def impayes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Factures impayées"""
    conn = get_db_connection()
    if not conn:
        await update.message.reply_text("❌ Erreur de connexion à la base de données")
        return

    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)

        query = """
            SELECT COUNT(*) as count, COALESCE(SUM(montant), 0) as total
            FROM releves
            WHERE montant IS NOT NULL
            AND montant > 0
            AND "numeroDiameX" IS NULL
        """
        cur.execute(query)
        result = cur.fetchone()

        message = f"⚠️ *Factures impayées*\n\n"
        message += f"Nombre: {result['count']}\n"
        message += f"Montant total: {result['total']:,.0f} Ar"

        await update.message.reply_text(message, parse_mode='Markdown')

    except Exception as e:
        logger.error(f"Erreur impayes: {e}")
        await update.message.reply_text(f"❌ Erreur: {str(e)}")
    finally:
        conn.close()

async def revenus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Revenus du mois"""
    conn = get_db_connection()
    if not conn:
        await update.message.reply_text("❌ Erreur de connexion à la base de données")
        return

    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        now = datetime.now()

        # Paiements forfaitaires
        query1 = """
            SELECT COALESCE(SUM(montant), 0) as total
            FROM paiements_forfaitaires
            WHERE EXTRACT(MONTH FROM date_paiement) = %s
            AND EXTRACT(YEAR FROM date_paiement) = %s
        """
        cur.execute(query1, (now.month, now.year))
        forfait = cur.fetchone()['total']

        # Paiements volumétriques
        query2 = """
            SELECT COALESCE(SUM(montant), 0) as total
            FROM releves
            WHERE "numeroDiameX" IS NOT NULL
            AND EXTRACT(MONTH FROM datepaiement) = %s
            AND EXTRACT(YEAR FROM datepaiement) = %s
        """
        cur.execute(query2, (now.month, now.year))
        volume = cur.fetchone()['total']

        total = float(forfait) + float(volume)

        message = f"💵 *Revenus de {now.strftime('%B %Y')}*\n\n"
        message += f"Paiements forfaitaires:\n{forfait:,.0f} Ar\n\n"
        message += f"Paiements volumétriques:\n{volume:,.0f} Ar\n\n"
        message += f"━━━━━━━━━━━━━━━━━\n"
        message += f"*TOTAL: {total:,.0f} Ar*"

        await update.message.reply_text(message, parse_mode='Markdown')

    except Exception as e:
        logger.error(f"Erreur revenus: {e}")
        await update.message.reply_text(f"❌ Erreur: {str(e)}")
    finally:
        conn.close()

async def conso_today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Relevés de consommation d'eau du jour"""
    conn = get_db_connection()
    if not conn:
        await update.message.reply_text("❌ Erreur de connexion à la base de données")
        return

    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        today = datetime.now().date()

        query = """
            SELECT COUNT(*) as count, COALESCE(SUM(consommation), 0) as total
            FROM releves
            WHERE DATE(datereleve) = %s
        """
        cur.execute(query, (today,))
        result = cur.fetchone()

        message = f"💧 *Relevés du {today.strftime('%d/%m/%Y')}*\n\n"
        message += f"Nombre de relevés: {result['count']}\n"
        message += f"Consommation totale: {result['total']:,.2f} m³"

        await update.message.reply_text(message, parse_mode='Markdown')

    except Exception as e:
        logger.error(f"Erreur conso_today: {e}")
        await update.message.reply_text(f"❌ Erreur: {str(e)}")
    finally:
        conn.close()

async def conso_month(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Consommation d'eau du mois"""
    conn = get_db_connection()
    if not conn:
        await update.message.reply_text("❌ Erreur de connexion à la base de données")
        return

    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        now = datetime.now()

        query = """
            SELECT COUNT(*) as count,
                   COALESCE(SUM(consommation), 0) as total,
                   COALESCE(AVG(consommation), 0) as moyenne
            FROM releves
            WHERE EXTRACT(MONTH FROM datereleve) = %s
            AND EXTRACT(YEAR FROM datereleve) = %s
        """
        cur.execute(query, (now.month, now.year))
        result = cur.fetchone()

        message = f"💧 *Consommation de {now.strftime('%B %Y')}*\n\n"
        message += f"Nombre de relevés: {result['count']}\n"
        message += f"Consommation totale: {result['total']:,.2f} m³\n"
        message += f"Consommation moyenne: {result['moyenne']:,.2f} m³"

        await update.message.reply_text(message, parse_mode='Markdown')

    except Exception as e:
        logger.error(f"Erreur conso_month: {e}")
        await update.message.reply_text(f"❌ Erreur: {str(e)}")
    finally:
        conn.close()

async def top_consommateurs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Top 10 des plus gros consommateurs du mois"""
    conn = get_db_connection()
    if not conn:
        await update.message.reply_text("❌ Erreur de connexion à la base de données")
        return

    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        now = datetime.now()

        query = """
            SELECT pe.nomabonne, pe.idxls, SUM(r.consommation) as total
            FROM releves r
            JOIN pointseaus pe ON r.point_eau_id = pe.id
            WHERE EXTRACT(MONTH FROM r.datereleve) = %s
            AND EXTRACT(YEAR FROM r.datereleve) = %s
            GROUP BY pe.id, pe.nomabonne, pe.idxls
            ORDER BY total DESC
            LIMIT 10
        """
        cur.execute(query, (now.month, now.year))
        results = cur.fetchall()

        if not results:
            await update.message.reply_text(f"💧 Aucun relevé trouvé pour {now.strftime('%B %Y')}")
            return

        message = f"💧 *Top 10 consommateurs - {now.strftime('%B %Y')}*\n\n"
        for i, row in enumerate(results, 1):
            nom = row['nomabonne'] or f"PE-{row['idxls']}"
            message += f"{i}. {nom}\n   {row['total']:,.2f} m³\n\n"

        await update.message.reply_text(message, parse_mode='Markdown')

    except Exception as e:
        logger.error(f"Erreur top_consommateurs: {e}")
        await update.message.reply_text(f"❌ Erreur: {str(e)}")
    finally:
        conn.close()

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Statistiques générales"""
    conn = get_db_connection()
    if not conn:
        await update.message.reply_text("❌ Erreur de connexion à la base de données")
        return

    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # Points d'eau
        cur.execute("SELECT COUNT(*) as count FROM pointseaus")
        points_eau = cur.fetchone()['count']

        # Employés actifs
        cur.execute("SELECT COUNT(*) as count FROM employes WHERE date_debauchage IS NULL")
        employes = cur.fetchone()['count']

        # Paiements du mois
        now = datetime.now()
        cur.execute("""
            SELECT COUNT(*) as count FROM paiements_forfaitaires
            WHERE EXTRACT(MONTH FROM date_paiement) = %s
            AND EXTRACT(YEAR FROM date_paiement) = %s
        """, (now.month, now.year))
        paiements = cur.fetchone()['count']

        # Relevés du mois
        cur.execute("""
            SELECT COUNT(*) as count FROM releves
            WHERE EXTRACT(MONTH FROM datereleve) = %s
            AND EXTRACT(YEAR FROM datereleve) = %s
        """, (now.month, now.year))
        releves = cur.fetchone()['count']

        message = f"📊 *Statistiques générales*\n\n"
        message += f"Points d'eau: {points_eau}\n"
        message += f"Employés actifs: {employes}\n\n"
        message += f"*{now.strftime('%B %Y')}*\n"
        message += f"Paiements: {paiements}\n"
        message += f"Relevés: {releves}"

        await update.message.reply_text(message, parse_mode='Markdown')

    except Exception as e:
        logger.error(f"Erreur stats: {e}")
        await update.message.reply_text(f"❌ Erreur: {str(e)}")
    finally:
        conn.close()

def main():
    """Démarrer le bot"""
    # Créer l'application
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # Ajouter les gestionnaires de commandes
    application.add_handler(CommandHandler("start", start))

    # Planning & Employés
    application.add_handler(CommandHandler("planning_today", planning_today))
    application.add_handler(CommandHandler("planning_week", planning_week))
    application.add_handler(CommandHandler("employes_actifs", employes_actifs))
    application.add_handler(CommandHandler("conges", conges))

    # Paiements
    application.add_handler(CommandHandler("paiements_today", paiements_today))
    application.add_handler(CommandHandler("paiements_month", paiements_month))
    application.add_handler(CommandHandler("impayes", impayes))
    application.add_handler(CommandHandler("revenus", revenus))

    # Consommation d'eau
    application.add_handler(CommandHandler("conso_today", conso_today))
    application.add_handler(CommandHandler("conso_month", conso_month))
    application.add_handler(CommandHandler("top_consommateurs", top_consommateurs))

    # Statistiques
    application.add_handler(CommandHandler("stats", stats))

    # Démarrer le bot
    logger.info("Bot d'analyse Hydria démarré")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()