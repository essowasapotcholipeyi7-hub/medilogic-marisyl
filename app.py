from flask import Flask, render_template, request, jsonify, session
from sheets_service import SheetsService
from datetime import datetime, timedelta
import os
import json

app = Flask(__name__)
app.secret_key = 'marisyl-secret-key-2024'

# Initialiser le service Sheets
sheets = SheetsService()

# ========== DONNÉES DE DÉMONSTRATION ==========
DEMO_DEBITEURS = []

DEMO_HISTORIQUE = []

# ========== ROUTES PRINCIPALES ==========
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    password = data.get('password', '')
    
    if password == 'admin123':
        session['logged_in'] = True
        return jsonify({'success': True})
    return jsonify({'success': False, 'message': 'Mot de passe incorrect'})

@app.route('/api/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'success': True})

@app.route('/api/check_auth')
def check_auth():
    return jsonify({'logged_in': session.get('logged_in', False)})

# ========== VENTE DIRECTE (avec acompte 60%) ==========
@app.route('/api/vente-directe', methods=['POST'])
def vente_directe():
    data = request.json
    nom = data.get('nom')
    telephone = data.get('telephone')
    email = data.get('email')
    montant_total = data.get('montant_total', 0)
    
    acompte = montant_total * 0.6
    solde = montant_total * 0.4
    
    debiteur = {
        'nom': nom,
        'telephone': telephone,
        'email': email,
        'montant_total': montant_total,
        'acompte': acompte,
        'solde_restant': solde,
        'notes': f"Vente directe - Acompte 60% : {acompte} FCFA"
    }
    
    result = sheets.add_debiteur(debiteur)
    
    if result.get('success'):
        sheets.add_paiement(result['id'], acompte, 'Espèces', f"Acompte 60% - Vente directe")
        return jsonify({'success': True, 'id': result['id'], 'acompte': acompte, 'solde': solde})
    
    return jsonify({'success': False, 'error': result.get('error')})

# ========== SAISIE MANUELLE ==========
@app.route('/api/saisie-manuelle', methods=['POST'])
def saisie_manuelle():
    data = request.json
    nom = data.get('nom')
    telephone = data.get('telephone')
    email = data.get('email')
    montant_total = data.get('montant_total', 0)
    
    debiteur = {
        'nom': nom,
        'telephone': telephone,
        'email': email,
        'montant_total': montant_total,
        'acompte': 0,
        'solde_restant': montant_total,
        'notes': "Saisie manuelle - Crédit existant"
    }
    
    result = sheets.add_debiteur(debiteur)
    
    if result.get('success'):
        return jsonify({'success': True, 'id': result['id']})
    
    return jsonify({'success': False, 'error': result.get('error')})

# ========== API CLIENTS ==========
@app.route('/api/debiteurs')
def get_debiteurs():
    debiteurs = sheets.get_debiteurs()
    if debiteurs:
        return jsonify(debiteurs)
    return jsonify(DEMO_DEBITEURS)

@app.route('/api/debiteurs/<int:debiteur_id>')
def get_debiteur(debiteur_id):
    debiteurs = sheets.get_debiteurs()
    debiteur = next((d for d in debiteurs if d['id'] == debiteur_id), None)
    if debiteur:
        return jsonify(debiteur)
    return jsonify({'error': 'Client non trouvé'}), 404

@app.route('/api/debiteurs', methods=['POST'])
def add_debiteur():
    data = request.json
    result = sheets.add_debiteur(data)
    return jsonify(result)

# ========== API STATISTIQUES ==========
@app.route('/api/stats')
def get_stats():
    stats = sheets.get_stats()
    if stats['total_clients'] > 0:
        echeances = sheets.get_all_echeances()
        aujourdhui = datetime.now().date()
        en_retard = 0
        for e in echeances:
            if e.get('statut') == 'en_attente':
                try:
                    date_echeance = datetime.fromisoformat(e['date']).date()
                    if date_echeance < aujourdhui:
                        en_retard += 1
                except:
                    pass
        stats['en_retard'] = en_retard
        return jsonify(stats)
    
    return jsonify({
        'total_clients': len(DEMO_DEBITEURS),
        'total_dette': sum(d['solde_restant'] for d in DEMO_DEBITEURS),
        'en_retard': 0,
        'clotures': sum(1 for d in DEMO_DEBITEURS if d['solde_restant'] == 0)
    })

# ========== API HISTORIQUE ==========
@app.route('/api/historique')
def get_historique():
    historique = sheets.get_historique()
    if historique:
        return jsonify(historique)
    return jsonify(DEMO_HISTORIQUE)

@app.route('/api/historique/client/<int:debiteur_id>')
def get_historique_client(debiteur_id):
    historique = sheets.get_historique_by_client(debiteur_id)
    return jsonify(historique)

# ========== API PAIEMENTS ==========
@app.route('/api/paiements', methods=['POST'])
def add_paiement():
    data = request.json
    debiteur_id = data.get('debiteur_id')
    montant = data.get('montant', 0)
    mode = data.get('mode', 'espèces')
    commentaire = data.get('commentaire', '')
    type_paiement = data.get('type', 'echeance')
    
    debiteurs = sheets.get_debiteurs()
    debiteur = next((d for d in debiteurs if d['id'] == debiteur_id), None)
    
    if not debiteur:
        return jsonify({'success': False, 'error': 'Client non trouvé'})
    
    if montant > debiteur['solde_restant']:
        return jsonify({'success': False, 'error': 'Le montant dépasse le solde restant'})
    
    result = sheets.add_paiement(debiteur_id, montant, mode, commentaire, type_paiement)
    
    if result:
        nouveau_solde = debiteur['solde_restant'] - montant
        sheets.update_solde(debiteur_id, nouveau_solde)
        
        if nouveau_solde == 0:
            sheets.update_all_echeances_statut(debiteur_id, 'paye')
        
        whatsapp_url = generer_lien_whatsapp(debiteur['telephone'], debiteur['nom'], montant, nouveau_solde)
        
        return jsonify({'success': True, 'nouveau_solde': nouveau_solde, 'whatsapp_url': whatsapp_url})
    
    return jsonify({'success': False, 'error': 'Erreur lors de l\'enregistrement'})


# ========== API PAIEMENTS ÉCHÉANCES ==========
@app.route('/api/paiements/echeance', methods=['POST'])
def payer_echeance_route():
    try:
        data = request.json
        echeance_id = data.get('echeanceId')
        client_id = data.get('clientId')
        montant = data.get('montant', 0)
        mode = data.get('mode', 'Espèces')
        commentaire = data.get('commentaire', '')
        penalite = data.get('penalite', 0)
        
        if not echeance_id or not client_id:
            return jsonify({'success': False, 'error': 'Données incomplètes'})
        
        montant_total = montant + penalite
        
        # Utiliser la nouvelle méthode avec séparation
        result = sheets.add_paiement_avec_penalite(client_id, echeance_id, montant_total, penalite, mode, commentaire)
        
        if result:
            debiteurs = sheets.get_debiteurs()
            client = next((d for d in debiteurs if d['id'] == client_id), None)
            if client:
                nouveau_solde = client['solde_restant'] - montant_total
                sheets.update_solde(client_id, nouveau_solde)
            
            sheets.update_echeance_statut(echeance_id, 'paye')
            
            return jsonify({'success': True, 'message': f'Paiement effectué', 'client_id': client_id})
        
        return jsonify({'success': False, 'error': 'Erreur lors de l\'enregistrement'})
        
    except Exception as e:
        print(f"❌ Erreur: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/paiements/total', methods=['POST'])
def payer_total_route():
    try:
        data = request.json
        client_id = data.get('clientId')
        montant = data.get('montant', 0)
        mode = data.get('mode', 'Espèces')
        commentaire = data.get('commentaire', 'Paiement total du solde')
        
        if not client_id:
            return jsonify({'success': False, 'error': 'Client non spécifié'})
        
        result = sheets.add_paiement(client_id, montant, mode, commentaire, 'total')
        
        if result:
            sheets.update_solde(client_id, 0)
            echeances = sheets.get_echeances_by_debiteur(client_id)
            for e in echeances:
                if e['statut'] == 'en_attente':
                    sheets.update_echeance_statut(e['id'], 'anticipe')
            
            return jsonify({'success': True, 'message': 'Solde total payé avec succès'})
        
        return jsonify({'success': False, 'error': 'Erreur lors du paiement'})
        
    except Exception as e:
        print(f"❌ Erreur: {e}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/paiements/personnalise', methods=['POST'])
def paiement_personnalise():
    try:
        data = request.json
        client_id = data.get('client_id')
        montant_total = data.get('montant_total', 0)
        mode = data.get('mode', 'Espèces')
        commentaire = data.get('commentaire', '')
        paiements = data.get('paiements', [])
        
        if not client_id:
            return jsonify({'success': False, 'error': 'Client non spécifié'})
        
        # Récupérer le client
        debiteurs = sheets.get_debiteurs()
        client = next((d for d in debiteurs if d['id'] == client_id), None)
        
        if not client:
            return jsonify({'success': False, 'error': 'Client non trouvé'})
        
        montant_total_paye = 0
        trop_percu = 0
        
        # Traiter chaque paiement d'échéance
        for p in paiements:
            montant_total_paye += p['montant']
            
            if p['type'] == 'complet':
                # Paiement complet de l'échéance
                sheets.update_echeance_statut(p['echeance_id'], 'paye')
                sheets.add_paiement(client_id, p['montant'], mode, f"Paiement échéance - {commentaire}", 'echeance')
                
            elif p['type'] == 'partiel':
                # Paiement partiel - mettre à jour le montant restant
                sheets.update_echeance_partiel(p['echeance_id'], p['montant_restant'])
                sheets.add_paiement(client_id, p['montant'], mode, f"Paiement partiel - {commentaire}", 'partiel')
        
        # Vérifier le trop-perçu
        if montant_total_paye > montant_total:
            trop_percu = montant_total_paye - montant_total
        
        # Mettre à jour le solde du client
        nouveau_solde = client['solde_restant'] - montant_total
        sheets.update_solde(client_id, max(0, nouveau_solde))
        
        # Enregistrer le paiement principal
        sheets.add_paiement(client_id, montant_total, mode, commentaire, 'personnalise')
        
        # Gérer le trop-perçu (déduire de la prochaine échéance)
        if trop_percu > 0:
            # Récupérer la prochaine échéance
            echeances = sheets.get_echeances_by_debiteur(client_id)
            prochaine = next((e for e in echeances if e['statut'] == 'en_attente'), None)
            
            if prochaine:
                nouveau_montant = prochaine['montant'] - trop_percu
                if nouveau_montant <= 0:
                    sheets.update_echeance_statut(prochaine['id'], 'paye')
                    if nouveau_montant < 0:
                        trop_percu_suivant = abs(nouveau_montant)
                        # Reporter sur l'échéance suivante...
                else:
                    sheets.update_echeance_montant(prochaine['id'], nouveau_montant)
        
        return jsonify({
            'success': True,
            'message': f'Paiement de {montant_total:,.0f} FCFA effectué',
            'nouveau_solde': max(0, nouveau_solde),
            'trop_percu': trop_percu if trop_percu > 0 else None
        })
        
    except Exception as e:
        print(f"❌ Erreur: {e}")
        return jsonify({'success': False, 'error': str(e)})

# ========== API ÉCHÉANCES ==========
@app.route('/api/echeances/<int:debiteur_id>')
def get_echeances(debiteur_id):
    echeances = sheets.get_echeances_by_debiteur(debiteur_id)
    return jsonify(echeances)

@app.route('/api/echeances/enregistrer', methods=['POST'])
def enregistrer_echeances():
    try:
        data = request.json
        debiteur_id = data.get('debiteur_id')
        echeances = data.get('echeances', [])
        
        if not debiteur_id or not echeances:
            return jsonify({'success': False, 'error': 'Données incomplètes'})
        
        result = sheets.save_echeances(debiteur_id, echeances)
        return jsonify(result)
        
    except Exception as e:
        print(f"❌ Erreur: {e}")
        return jsonify({'success': False, 'error': str(e)})

# ========== API PROGRAMMATION ==========
@app.route('/api/programmations/calculer', methods=['POST'])
def calculer_programmation():
    try:
        data = request.json
        montant_total = data.get('montant_total', 0)
        nb_tranches = data.get('nb_tranches', 3)
        periode = data.get('periode', 'mensuel')
        
        if montant_total <= 0:
            return jsonify({'success': False, 'error': 'Montant invalide'})
        
        montant_tranche = montant_total / nb_tranches
        echeances = []
        date_debut = datetime.now()
        
        for i in range(nb_tranches):
            if periode == 'hebdomadaire':
                date_echeance = date_debut + timedelta(weeks=i+1)
            else:
                date_echeance = date_debut + timedelta(days=30*(i+1))
            
            echeances.append({
                'date': date_echeance.isoformat(),
                'montant': round(montant_tranche if i < nb_tranches - 1 else montant_total - (montant_tranche * (nb_tranches - 1)), 0),
                'pourcentage': round((montant_tranche / montant_total) * 100, 1)
            })
        
        return jsonify({'success': True, 'echeances': echeances})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# ========== API ALERTES ==========
@app.route('/api/alertes')
def get_alertes():
    try:
        debiteurs = sheets.get_debiteurs()
        echeances = sheets.get_all_echeances()
        
        aujourdhui = datetime.now().date()
        fin_semaine = aujourdhui + timedelta(days=7)
        alerte_aujourdhui = []
        alerte_retard = []
        alerte_cette_semaine = []
        
        for e in echeances:
            if e.get('statut') == 'en_attente':
                try:
                    date_echeance = datetime.fromisoformat(e['date']).date()
                    debiteur = next((d for d in debiteurs if d['id'] == e['debiteur_id']), None)
                    
                    if date_echeance == aujourdhui:
                        alerte_aujourdhui.append({
                            'client_nom': debiteur['nom'] if debiteur else 'Inconnu',
                            'montant': e['montant'],
                            'echeance_id': e['id'],
                            'debiteur_id': e['debiteur_id'],
                            'date_echeance': e['date']
                        })
                    elif date_echeance < aujourdhui:
                        jours_retard = (aujourdhui - date_echeance).days + 1
                        penalite = e['montant'] * 0.01 * (jours_retard - 14) if jours_retard > 14 else 0
                        
                        alerte_retard.append({
                            'client_nom': debiteur['nom'] if debiteur else 'Inconnu',
                            'montant': e['montant'],
                            'jours_retard': jours_retard,
                            'penalite': penalite,
                            'echeance_id': e['id'],
                            'debiteur_id': e['debiteur_id'],
                            'date_echeance': e['date']
                        })
                    elif date_echeance <= fin_semaine:
                        jours_restant = (date_echeance - aujourdhui).days
                        alerte_cette_semaine.append({
                            'client_nom': debiteur['nom'] if debiteur else 'Inconnu',
                            'montant': e['montant'],
                            'jours_restant': jours_restant,
                            'echeance_id': e['id'],
                            'debiteur_id': e['debiteur_id'],
                            'date_echeance': e['date']
                        })
                except Exception as ex:
                    print(f"Erreur traitement échéance: {ex}")
                    continue
        
        return jsonify({
            'aujourdhui': alerte_aujourdhui,
            'retard': alerte_retard,
            'cette_semaine': alerte_cette_semaine
        })
        
    except Exception as e:
        print(f"❌ Erreur get_alertes: {e}")
        return jsonify({'aujourdhui': [], 'retard': [], 'cette_semaine': []})

@app.route('/api/whatsapp/rappel/<int:debiteur_id>')
def get_whatsapp_rappel(debiteur_id):
    debiteurs = sheets.get_debiteurs()
    debiteur = next((d for d in debiteurs if d['id'] == debiteur_id), None)
    
    if not debiteur or not debiteur.get('telephone'):
        return jsonify({'success': False, 'error': 'Numéro non disponible'})
    
    # Récupérer la prochaine échéance
    echeances = sheets.get_echeances_by_debiteur(debiteur_id)
    prochaine_echeance = next((e for e in echeances if e['statut'] == 'en_attente'), None)
    
    numero = debiteur['telephone'].replace(' ', '').replace('+', '')
    if not numero.startswith('228'):
        numero = '228' + numero
    
    if prochaine_echeance:
        date_echeance = datetime.fromisoformat(prochaine_echeance['date'])
        aujourdhui = datetime.now()
        jours_restant = (date_echeance - aujourdhui).days
        montant = prochaine_echeance['montant']
        
        if jours_restant < 0:
            # Déjà en retard
            jours_retard = abs(jours_restant)
            if jours_retard > 14:
                penalite = montant * 0.01 * (jours_retard - 14)
                message = f"""🚨 URGENT - RETARD DE PAIEMENT 🚨

Bonjour {debiteur['nom']},

⚠️ Votre paiement est en retard de {jours_retard} jours !

💰 Montant dû : {montant:,.0f} FCFA
⚠️ Pénalité : {penalite:,.0f} FCFA
💵 Total à payer : {montant + penalite:,.0f} FCFA

📅 Échéance initiale : {date_echeance.strftime('%d/%m/%Y')}

Merci de régulariser votre situation.

Cordialement,
L'équipe MARISYL"""
            else:
                message = f"""🔔 RAPPEL DE PAIEMENT - RETARD

Bonjour {debiteur['nom']},

⚠️ Votre paiement est en retard de {jours_retard} jours.

💰 Montant à payer : {montant:,.0f} FCFA

📅 Échéance initiale : {date_echeance.strftime('%d/%m/%Y')}

Veuillez effectuer le paiement sans plus tarder.

Cordialement,
L'équipe MARISYL"""
        elif jours_restant == 0:
            message = f"""⚠️ RAPPEL - PAIEMENT AUJOURD'HUI ⚠️

Bonjour {debiteur['nom']},

📅 Votre échéance arrive à échéance AUJOURD'HUI !

💰 Montant à payer : {montant:,.0f} FCFA

Merci de procéder au paiement dès aujourd'hui.

Cordialement,
L'équipe MARISYL"""
        else:
            message = f"""🔔 RAPPEL DE PAIEMENT

Bonjour {debiteur['nom']},

📅 Votre prochaine échéance est dans {jours_restant} jours.

💰 Montant à payer : {montant:,.0f} FCFA

⚠️ Attention : Passé 14 jours de retard, une pénalité de 1% par jour sera appliquée.

Merci de votre ponctualité.

Cordialement,
L'équipe MARISYL"""
    else:
        # Pas d'échéance programmée, rappel du solde
        message = f"""🔔 RAPPEL DE SOLDE

Bonjour {debiteur['nom']},

💰 Votre solde restant est de {debiteur['solde_restant']:,.0f} FCFA.

Merci de régulariser votre situation.

Cordialement,
L'équipe MARISYL"""
    
    url = f"https://wa.me/{numero}?text={message}"
    return jsonify({'success': True, 'url': url})

# ========== API ADMINISTRATION ==========
@app.route('/api/admin/changer-mot-de-passe', methods=['POST'])
def admin_changer_mot_de_passe():
    data = request.json
    ancien = data.get('ancien')
    nouveau = data.get('nouveau')
    
    # Vérifier l'ancien mot de passe
    if ancien != 'admin123':
        return jsonify({'success': False, 'message': 'Ancien mot de passe incorrect'})
    
    # Ici, vous devriez sauvegarder dans Google Sheets
    # Pour l'instant, simulation
    return jsonify({'success': True, 'message': 'Mot de passe changé avec succès'})

@app.route('/api/admin/question-secrete', methods=['POST'])
def admin_question_secrete():
    data = request.json
    question = data.get('question')
    reponse = data.get('reponse')
    
    # Sauvegarder dans Google Sheets
    return jsonify({'success': True, 'message': 'Question secrète sauvegardée'})

@app.route('/api/admin/email-secours', methods=['POST'])
def admin_email_secours():
    data = request.json
    email = data.get('email')
    
    # Sauvegarder dans Google Sheets
    return jsonify({'success': True, 'message': 'Email de secours sauvegardé'})

@app.route('/api/admin/config')
def admin_config():
    # Lire depuis Google Sheets
    return jsonify({
        'question': 'Quel est le nom de votre premier animal ?',
        'reponse': '',
        'email': ''
    })

# ========== FONCTIONS WHATSAPP ==========
def generer_lien_whatsapp(telephone, nom, montant, nouveau_solde):
    if not telephone:
        return None
    
    numero = telephone.replace(' ', '').replace('+', '')
    if not numero.startswith('228'):
        numero = '228' + numero
    
    message = f"✅ CONFIRMATION PAIEMENT MARISYL\n\nBonjour {nom},\n\nNous confirmons votre paiement de {montant:,.0f} FCFA.\n\n💰 Nouveau solde : {nouveau_solde:,.0f} FCFA\n\nMerci pour votre confiance !"
    
    return f"https://wa.me/{numero}?text={message}"

@app.route('/api/whatsapp/<int:debiteur_id>')
def get_whatsapp_link(debiteur_id):
    debiteurs = sheets.get_debiteurs()
    debiteur = next((d for d in debiteurs if d['id'] == debiteur_id), None)
    
    if not debiteur or not debiteur.get('telephone'):
        return jsonify({'success': False, 'error': 'Numéro non disponible'})
    
    numero = debiteur['telephone'].replace(' ', '').replace('+', '')
    if not numero.startswith('228'):
        numero = '228' + numero
    
    # Vérifier si le solde est à zéro
    if debiteur.get('solde_restant', 0) <= 0:
        # Message de remerciement
        message = f"""🎉 MERCI POUR VOTRE CONFIANCE - MARISYL 🎉

Bonjour {debiteur['nom']},

✅ Votre dette est entièrement remboursée !
💰 Montant total remboursé : {debiteur['montant_total']:,.0f} FCFA

Nous vous remercions pour votre ponctualité et votre confiance.

📞 N'hésitez pas à nous contacter pour tout besoin futur.

Cordialement,
L'équipe MARISYL"""
        
        url = f"https://wa.me/{numero}?text={message}"
        return jsonify({'success': True, 'url': url, 'solde_restant': 0, 'type': 'remerciement'})
    
    # Message de rappel (solde > 0)
    message = f"""🔔 RAPPEL MARISYL

Bonjour {debiteur['nom']},

📊 Votre solde restant est de {debiteur['solde_restant']:,.0f} FCFA.

Merci de régulariser votre situation.

Cordialement,
L'équipe MARISYL"""
    
    url = f"https://wa.me/{numero}?text={message}"
    return jsonify({'success': True, 'url': url, 'solde_restant': debiteur['solde_restant'], 'type': 'rappel'})

# ========== FONCTION GÉNÉRATRICE DU CERTIFICAT ==========
def generer_html_certificat(debiteur):
    today = datetime.now()
    
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>Certificat de solde - MARISYL</title>
        <style>
            * {{
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }}
            body {{
                font-family: 'Times New Roman', 'Segoe UI', Arial, sans-serif;
                background: #e8e8e8;
                display: flex;
                justify-content: center;
                align-items: center;
                min-height: 100vh;
                padding: 40px;
            }}
            .certificat {{
                max-width: 800px;
                width: 100%;
                background: white;
                border-radius: 20px;
                box-shadow: 0 20px 40px rgba(0,0,0,0.15);
                overflow: hidden;
            }}
            .border-deco {{
                height: 8px;
                background: linear-gradient(90deg, #1E3A8A, #4169E1, #10B981, #4169E1, #1E3A8A);
            }}
            .header {{
                text-align: center;
                padding: 30px;
                background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
                border-bottom: 2px solid #4169E1;
            }}
            .logo {{
                width: 70px;
                height: 70px;
                background: linear-gradient(135deg, #1E3A8A, #4169E1);
                border-radius: 50%;
                display: flex;
                align-items: center;
                justify-content: center;
                margin: 0 auto 15px;
            }}
            .logo span {{
                color: white;
                font-size: 32px;
                font-weight: bold;
            }}
            .header h1 {{
                font-size: 28px;
                color: #1E3A8A;
                margin-bottom: 5px;
            }}
            .header p {{
                color: #6c757d;
                font-size: 12px;
            }}
            .badge {{
                display: inline-block;
                background: #10B981;
                color: white;
                padding: 5px 20px;
                border-radius: 30px;
                font-size: 12px;
                margin-top: 10px;
            }}
            .content {{
                padding: 40px;
            }}
            .title {{
                text-align: center;
                margin-bottom: 30px;
            }}
            .title h2 {{
                font-size: 22px;
                color: #2c3e50;
                border-bottom: 2px solid #10B981;
                display: inline-block;
                padding-bottom: 10px;
            }}
            .attestation {{
                text-align: center;
                margin: 30px 0;
                font-size: 16px;
                line-height: 1.8;
            }}
            .client-name {{
                font-size: 28px;
                font-weight: bold;
                color: #1E3A8A;
                margin: 20px 0;
            }}
            .info-box {{
                background: #f8f9fa;
                border-radius: 15px;
                padding: 20px;
                margin: 25px 0;
                border-left: 4px solid #10B981;
            }}
            .info-row {{
                display: flex;
                justify-content: space-between;
                padding: 12px 0;
                border-bottom: 1px dashed #dee2e6;
            }}
            .info-row:last-child {{
                border-bottom: none;
            }}
            .info-label {{
                font-weight: bold;
                color: #495057;
            }}
            .montant {{
                font-size: 32px;
                font-weight: bold;
                color: #10B981;
            }}
            .message {{
                text-align: center;
                margin: 30px 0;
                padding: 20px;
                background: #f0fdf4;
                border-radius: 10px;
            }}
            .signatures {{
                display: flex;
                justify-content: space-between;
                margin: 40px 0 20px;
                gap: 40px;
            }}
            .signature-box {{
                flex: 1;
                text-align: center;
            }}
            .signature-line {{
                margin-top: 50px;
                border-top: 1px solid #333;
                padding-top: 10px;
            }}
            .stamp {{
                text-align: center;
                margin: 20px 0;
            }}
            .stamp-circle {{
                width: 100px;
                height: 100px;
                border: 2px solid #dc2626;
                border-radius: 50%;
                display: inline-flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                margin: 0 auto;
            }}
            .stamp-circle span {{
                color: #dc2626;
                font-size: 10px;
                font-weight: bold;
            }}
            .footer {{
                background: #f8f9fa;
                padding: 20px;
                text-align: center;
                border-top: 1px solid #e9ecef;
                font-size: 11px;
                color: #6c757d;
            }}
            @media print {{
                body {{
                    background: white;
                    padding: 0;
                }}
                .certificat {{
                    box-shadow: none;
                }}
                .header, .border-deco, .badge {{
                    -webkit-print-color-adjust: exact;
                    print-color-adjust: exact;
                }}
            }}
        </style>
    </head>
    <body>
        <div class="certificat">
            <div class="border-deco"></div>
            <div class="header">
                <div class="logo"><span>M</span></div>
                <h1>MARISYL</h1>
                <p>Gestion de crédit pour boutiques | MediLogic</p>
                <div class="badge">✅ CERTIFICAT DE SOLDE ✅</div>
            </div>
            
            <div class="content">
                <div class="title">
                    <h2>ATTESTATION DE REMBOURSEMENT</h2>
                </div>
                
                <div class="attestation">
                    <p>Nous soussignés, <strong>MARISYL / MediLogic</strong>, attestons que</p>
                    <div class="client-name">{debiteur['nom']}</div>
                    <p>a remboursé <strong>intégralement et sans aucune réserve</strong> sa dette contractée auprès de notre établissement.</p>
                </div>
                
                <div class="info-box">
                    <div class="info-row">
                        <span class="info-label">📄 Numéro de dossier</span>
                        <span>MARISYL-{today.strftime('%Y')}-{str(debiteur['id']).zfill(4)}</span>
                    </div>
                    <div class="info-row">
                        <span class="info-label">💰 Montant total remboursé</span>
                        <span class="montant">{debiteur['montant_total']:,.0f} FCFA</span>
                    </div>
                    <div class="info-row">
                        <span class="info-label">📅 Date de clôture</span>
                        <span>{today.strftime('%d/%m/%Y')}</span>
                    </div>
                    <div class="info-row">
                        <span class="info-label">👤 Client</span>
                        <span>{debiteur['nom']}</span>
                    </div>
                    <div class="info-row">
                        <span class="info-label">📞 Contact</span>
                        <span>{debiteur['telephone']}</span>
                    </div>
                </div>
                
                <div class="message">
                    <p>🎉 <strong>Félicitations !</strong> Votre dossier est désormais clôturé. 🎉</p>
                </div>
                
                <div class="signatures">
                    <div class="signature-box">
                        <div class="signature-line"></div>
                        <div>Signature du client</div>
                    </div>
                    <div class="signature-box">
                        <div class="signature-line"></div>
                        <div>Signature du responsable</div>
                    </div>
                </div>
                
                <div class="stamp">
                    <div class="stamp-circle">
                        <span>VALIDÉ</span>
                        <span>LE {today.strftime('%d/%m/%Y')}</span>
                    </div>
                </div>
            </div>
            
            <div class="footer">
                <p>Document généré le {today.strftime('%d/%m/%Y à %H:%M')}</p>
                <p>MARISYL - MediLogic | Tous droits réservés</p>
            </div>
        </div>
        <script>window.print(); window.close();</script>
    </body>
    </html>
    """


# ========== EXPORT PDF ==========
@app.route('/api/pdf/clients')
def export_clients_pdf():
    debiteurs = sheets.get_debiteurs()
    if not debiteurs:
        debiteurs = []
    
    rows = ''
    for d in debiteurs:
        rows += f"<tr><td>{d['id']}</td><td>{d['nom']}</td><td>{d['telephone']}</td><td style='text-align:right'>{d['montant_total']:,.0f} FCFA</td><td style='text-align:right'>{d['solde_restant']:,.0f} FCFA</td></tr>"
    
    html = f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="UTF-8"><title>Liste des clients</title>
    <style>
        body{{font-family:Arial;margin:40px}}
        table{{width:100%;border-collapse:collapse}}
        th,td{{border:1px solid #ddd;padding:8px}}
        th{{background:#4F46E5;color:white}}
    </style>
    </head>
    <body>
        <h1>Liste des clients</h1>
        <table>
            <thead><tr><th>ID</th><th>Nom</th><th>Téléphone</th><th>Total</th><th>Solde</th></tr></thead>
            <tbody>{rows}</tbody>
        </table>
        <script>window.print();</script>
    </body>
    </html>
    """
    return html


@app.route('/api/pdf/certificat/<int:debiteur_id>')
def certificat_solde_pdf(debiteur_id):
    debiteurs = sheets.get_debiteurs()
    debiteur = next((d for d in debiteurs if d['id'] == debiteur_id), None)
    
    if not debiteur:
        return "<h1>Client non trouvé</h1>"
    
    if debiteur['solde_restant'] != 0:
        return "<h1>Certificat non disponible - Solde non nul</h1>"
    
    today = datetime.now()
    
    # Retourner directement le HTML sans script window.close() qui ferme trop tôt
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>Certificat de solde - MARISYL</title>
        <style>
            body {{ font-family: Arial; padding: 50px; }}
            .certificat {{ max-width: 600px; margin: 0 auto; border: 2px solid #4169E1; padding: 30px; border-radius: 15px; text-align: center; }}
            h1 {{ color: #1E3A8A; }}
            .badge {{ background: #10B981; color: white; padding: 5px 20px; border-radius: 20px; display: inline-block; }}
            .client {{ font-size: 24px; font-weight: bold; margin: 20px 0; }}
            .montant {{ font-size: 28px; color: #10B981; font-weight: bold; }}
            .signatures {{ display: flex; justify-content: space-between; margin-top: 50px; }}
            .signature {{ text-align: center; width: 45%; }}
            .line {{ border-top: 1px solid black; margin-top: 40px; padding-top: 10px; }}
            button {{ margin-top: 30px; padding: 10px 20px; background: #4169E1; color: white; border: none; border-radius: 5px; cursor: pointer; }}
            button:hover {{ opacity: 0.8; }}
        </style>
    </head>
    <body>
        <div class="certificat">
            <h1>MARISYL</h1>
            <p>MediLogic - Gestion de crédit</p>
            <div class="badge">✅ CERTIFICAT DE SOLDE ✅</div>
            
            <h2>Attestation de remboursement</h2>
            
            <p>Nous attestons que</p>
            <div class="client">{debiteur['nom']}</div>
            <p>a remboursé intégralement sa dette de</p>
            <div class="montant">{debiteur['montant_total']:,.0f} FCFA</div>
            
            <p>Date de clôture : <strong>{today.strftime('%d/%m/%Y')}</strong></p>
            
            <div class="signatures">
                <div class="signature">
                    <div class="line"></div>
                    Signature du client
                </div>
                <div class="signature">
                    <div class="line"></div>
                    Signature du responsable
                </div>
            </div>
            
            <p style="margin-top: 30px; font-size: 12px; color: #666;">
                Document généré le {today.strftime('%d/%m/%Y à %H:%M')}
            </p>
            
            <button onclick="window.print()">🖨️ Imprimer</button>
            <button onclick="window.close()">❌ Fermer</button>
        </div>
    </body>
    </html>
    """
    return html

@app.route('/api/pdf/contrat/<int:debiteur_id>')
def contrat_pdf(debiteur_id):
    debiteurs = sheets.get_debiteurs()
    debiteur = next((d for d in debiteurs if d['id'] == debiteur_id), None)
    echeances = sheets.get_echeances_by_debiteur(debiteur_id)
    
    if not debiteur:
        return "<h1>Client non trouvé</h1>"
    
    echeances_rows = ''
    for i, e in enumerate(echeances):
        echeances_rows += f"""
        <tr>
            <td style="padding: 8px;">{i+1}</td>
            <td style="padding: 8px;">{datetime.fromisoformat(e['date']).strftime('%d/%m/%Y')}</td>
            <td style="padding: 8px; text-align: right;">{e['montant']:,.0f} FCFA</td>
            <td style="padding: 8px; text-align: center;">{e['pourcentage']}%</td>
            <td style="padding: 8px; text-align: center;">⏳ En attente</td>
        </tr>
        """
    
    html = f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="UTF-8"><title>Contrat MARISYL</title>
    <style>
        body {{ font-family: Arial; margin: 40px; }}
        .header {{ text-align: center; background: #4F46E5; color: white; padding: 20px; border-radius: 10px; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
        th {{ background: #4F46E5; color: white; padding: 10px; }}
        td {{ padding: 8px; border-bottom: 1px solid #ddd; }}
        .signature {{ margin-top: 50px; display: flex; justify-content: space-between; }}
    </style>
    </head>
    <body>
        <div class="header"><h1>MARISYL</h1><p>Contrat de paiement échelonné</p></div>
        <h2>Client : {debiteur['nom']}</h2>
        <p>Téléphone : {debiteur['telephone']}</p>
        <p>Email : {debiteur.get('email', '-')}</p>
        <p>Montant total : <strong>{debiteur['montant_total']:,.0f} FCFA</strong></p>
        <p>Acompte versé : <strong>{(debiteur['montant_total'] - debiteur['solde_restant']):,.0f} FCFA</strong></p>
        <p>Solde restant : <strong>{debiteur['solde_restant']:,.0f} FCFA</strong></p>
        <h3>📅 Échéancier des paiements</h3>
        <table><thead><tr><th>#</th><th>Date</th><th>Montant</th><th>%</th><th>Statut</th></tr></thead>
        <tbody>{echeances_rows if echeances_rows else '<tr><td colspan="5" style="text-align: center;">Aucune échéance programmée</td></tr>'}</tbody>
        </table>
        <div class="signature"><div>Signature client : ___________</div><div>Signature commerçant : ___________</div></div>
        <div class="footer"><p>Généré le {datetime.now().strftime('%d/%m/%Y à %H:%M')}</p><p>MARISYL - MediLogic</p></div>
        <script>window.print();</script>
    </body>
    </html>
    """
    return html

# ========== INITIALISATION ==========
@app.route('/api/init')
def init_sheets():
    result = sheets.init_sheets()
    return jsonify(result)

if __name__ == '__main__':
    print("=" * 50)
    print("🚀 MediLogic - MARISYL")
    print("=" * 50)
    print("📍 Application démarrée sur: http://localhost:5000")
    print("🔐 Mot de passe: admin123")
    print("=" * 50)
    
    app.run(debug=True, port=5000)