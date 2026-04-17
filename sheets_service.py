import gspread
from google.oauth2.service_account import Credentials
import os
import json
from datetime import datetime

class SheetsService:
    def __init__(self):
        SCOPES = ['https://www.googleapis.com/auth/spreadsheets', 
                  'https://www.googleapis.com/auth/drive']
        SPREADSHEET_ID = '1Sv7GQhBGS5UBZ0_QtG23c8SKiNBgEMI6mh60VZSLc3o'
        
        # Essayer de lire depuis variable d'environnement (Render)
        creds_json = os.environ.get('GOOGLE_CREDENTIALS')
        
        if creds_json:
            try:
                print("✅ Lecture des credentials depuis variable d'environnement")
                creds_dict = json.loads(creds_json)
                creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
                self.client = gspread.authorize(creds)
                self.sheet = self.client.open_by_key(SPREADSHEET_ID)
                print("✅ Connecté à Google Sheets")
                return
            except Exception as e:
                print(f"❌ Erreur avec variable d'environnement: {e}")
        
        # Fallback: lire depuis fichier (local)
        creds_path = os.path.join(os.path.dirname(__file__), 'credentials.json')
        
        if not os.path.exists(creds_path):
            print("⚠️ credentials.json non trouvé. Utilisation du mode démo.")
            self.client = None
            return
        
        try:
            print("✅ Lecture des credentials depuis fichier")
            creds = Credentials.from_service_account_file(creds_path, scopes=SCOPES)
            self.client = gspread.authorize(creds)
            self.sheet = self.client.open_by_key(SPREADSHEET_ID)
            print("✅ Connecté à Google Sheets")
        except Exception as e:
            print(f"❌ Erreur de connexion: {e}")
            self.client = None
    
    def get_or_create_worksheet(self, name, headers):
        if not self.client:
            return None
        try:
            return self.sheet.worksheet(name)
        except:
            worksheet = self.sheet.add_worksheet(name, rows=100, cols=len(headers))
            worksheet.update('A1', [headers])
            return worksheet
    
    def init_sheets(self):
        if not self.client:
            return {'success': False, 'error': 'Service non connecté'}
        
        try:
            self.get_or_create_worksheet("Debiteurs", 
                ['ID', 'Nom', 'Téléphone', 'Email', 'Montant total', 'Solde restant', 'Acompte', 'Date création', 'Notes'])
            
            self.get_or_create_worksheet("Historique",
                ['ID', 'ID_Debiteur', 'ID_Echeance', 'Date', 'Type', 'Montant', 'Mode', 'Commentaire', 'Date création'])
            
            self.get_or_create_worksheet("Echeances",
                ['ID', 'ID_Debiteur', 'Date', 'Montant', 'Pourcentage', 'Statut', 'Date création'])
            
            self.get_or_create_worksheet("Programmations",
                ['ID', 'ID_Debiteur', 'Date', 'Montant total', 'Solde', 'Statut', 'Date création'])
            
            config_ws = self.get_or_create_worksheet("Config",
                ['Paramètre', 'Valeur'])
            
            config_data = config_ws.get_all_values()
            mot_de_passe_existe = False
            for row in config_data:
                if len(row) > 0 and row[0] == 'mot_de_passe':
                    mot_de_passe_existe = True
                    break
            
            if not mot_de_passe_existe:
                config_ws.append_row(['mot_de_passe', 'admin123'])
            
            self.get_or_create_worksheet("Logs",
                ['Date', 'Action', 'Utilisateur', 'Détails'])
            
            print("✅ Toutes les feuilles sont initialisées")
            return {'success': True, 'message': 'Feuilles initialisées'}
        except Exception as e:
            print(f"❌ Erreur init_sheets: {e}")
            return {'success': False, 'error': str(e)}
    
    def get_debiteurs(self):
        if not self.client:
            return []
        
        try:
            ws = self.get_or_create_worksheet("Debiteurs", 
                ['ID', 'Nom', 'Téléphone', 'Email', 'Montant total', 'Solde restant', 'Acompte', 'Date création', 'Notes'])
            
            data = ws.get_all_values()
            print(f"📊 Lecture de {len(data)-1} clients")
            
            debiteurs = []
            for i in range(1, len(data)):
                row = data[i]
                if row and row[0] and str(row[0]).strip():
                    debiteurs.append({
                        'id': int(float(row[0])) if row[0] else i,
                        'nom': row[1] if len(row) > 1 and row[1] else 'Sans nom',
                        'telephone': row[2] if len(row) > 2 else '',
                        'email': row[3] if len(row) > 3 else '',
                        'montant_total': self.clean_number(row[4]),
                        'solde_restant': self.clean_number(row[5]),
                        'acompte': self.clean_number(row[6]),
                        'datecreation': row[7] if len(row) > 7 else '',
                        'notes': row[8] if len(row) > 8 else ''
                    })
            
            print(f"✅ {len(debiteurs)} clients chargés")
            return debiteurs
        except Exception as e:
            print(f"❌ Erreur get_debiteurs: {e}")
            return []
    
    def add_debiteur(self, debiteur):
        if not self.client:
            return {'success': False, 'error': 'Service non connecté'}
        
        try:
            ws = self.get_or_create_worksheet("Debiteurs",
                ['ID', 'Nom', 'Téléphone', 'Email', 'Montant total', 'Solde restant', 'Acompte', 'Date création', 'Notes'])
            
            existing = ws.get_all_values()
            new_id = len(existing)
            
            ws.append_row([
                new_id,
                debiteur.get('nom', ''),
                debiteur.get('telephone', ''),
                debiteur.get('email', ''),
                debiteur.get('montant_total', 0),
                debiteur.get('solde_restant', debiteur.get('montant_total', 0)),
                debiteur.get('acompte', 0),
                datetime.now().isoformat(),
                debiteur.get('notes', '')
            ])
            
            return {'success': True, 'id': new_id}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def update_solde(self, debiteur_id, nouveau_solde):
        if not self.client:
            return False
        
        try:
            ws = self.sheet.worksheet("Debiteurs")
            data = ws.get_all_values()
            
            for i in range(1, len(data)):
                if data[i][0] and int(float(data[i][0])) == debiteur_id:
                    ws.update_cell(i + 1, 6, nouveau_solde)
                    return True
            return False
        except:
            return False
    
    def add_paiement(self, debiteur_id, montant, mode, commentaire, type_paiement='echeance'):
        if not self.client:
            return False
        
        try:
            ws = self.get_or_create_worksheet("Historique",
                ['ID', 'ID_Debiteur', 'ID_Echeance', 'Date', 'Type', 'Montant', 'Mode', 'Commentaire', 'Date création'])
            
            existing = ws.get_all_values()
            new_id = len(existing)
            
            ws.append_row([
                new_id,
                debiteur_id,
                '',
                datetime.now().isoformat(),
                type_paiement,
                montant,
                mode,
                commentaire,
                datetime.now().isoformat()
            ])
            return True
        except:
            return False
    
    def add_paiement_avec_penalite(self, debiteur_id, echeance_id, montant, penalite, mode, commentaire):
        """Ajoute un paiement avec séparation montant principal et pénalité"""
        if not self.client:
            return False
        
        try:
            ws = self.get_or_create_worksheet("Historique",
                ['ID', 'ID_Debiteur', 'ID_Echeance', 'Date', 'Type', 'Montant', 'Mode', 'Commentaire', 'Date création'])
            
            existing = ws.get_all_values()
            new_id = len(existing)
            
            montant_principal = montant - penalite
            
            # Enregistrer le paiement principal
            ws.append_row([
                new_id,
                debiteur_id,
                echeance_id,
                datetime.now().isoformat(),
                'echeance',
                montant_principal,
                mode,
                commentaire,
                datetime.now().isoformat()
            ])
            
            # Enregistrer la pénalité séparément si > 0
            if penalite > 0:
                ws.append_row([
                    new_id + 1,
                    debiteur_id,
                    echeance_id,
                    datetime.now().isoformat(),
                    'penalite',
                    penalite,
                    mode,
                    f"Pénalité de retard - {commentaire}",
                    datetime.now().isoformat()
                ])
            
            return True
        except Exception as e:
            print(f"Erreur add_paiement_avec_penalite: {e}")
            return False
    
    def get_historique(self):
        if not self.client:
            return []
        
        try:
            ws = self.sheet.worksheet("Historique")
            data = ws.get_all_values()
            debiteurs = {d['id']: d['nom'] for d in self.get_debiteurs()}
            
            historique = []
            for i in range(1, len(data)):
                row = data[i]
                if row:
                    historique.append({
                        'date': row[3] if len(row) > 3 else '',
                        'client_nom': debiteurs.get(int(float(row[1])), 'Inconnu') if len(row) > 1 and row[1] else 'Inconnu',
                        'montant': self.clean_number(row[5]),
                        'mode': row[6] if len(row) > 6 else '-',
                        'commentaire': row[7] if len(row) > 7 else '-',
                        'type': row[4] if len(row) > 4 else 'echeance'
                    })
            return sorted(historique, key=lambda x: x['date'], reverse=True)
        except:
            return []
    
    def get_stats(self):
        debiteurs = self.get_debiteurs()
        return {
            'total_clients': len(debiteurs),
            'total_dette': sum(d['solde_restant'] for d in debiteurs),
            'clotures': sum(1 for d in debiteurs if d['solde_restant'] == 0)
        }
    
    def get_all_echeances(self):
        if not self.client:
            return []
        
        try:
            ws = self.sheet.worksheet("Echeances")
            data = ws.get_all_values()
            echeances = []
            
            for i in range(1, len(data)):
                row = data[i]
                if row and row[0]:
                    echeances.append({
                        'id': int(row[0]) if row[0].isdigit() else i,
                        'debiteur_id': int(row[1]) if len(row) > 1 and row[1] and row[1].isdigit() else 0,
                        'date': row[2] if len(row) > 2 else '',
                        'montant': self.clean_number(row[3]),
                        'statut': row[5] if len(row) > 5 else 'en_attente'
                    })
            return echeances
        except Exception as e:
            print(f"Erreur get_all_echeances: {e}")
            return []

    def get_echeances_by_debiteur(self, debiteur_id):
        """Récupère les échéances d'un client"""
        if not self.client:
            return []
        
        try:
            ws = self.sheet.worksheet("Echeances")
            data = ws.get_all_values()
            echeances = []
            
            print(f"🔍 Recherche échéances pour client {debiteur_id}")
            
            for i in range(1, len(data)):
                row = data[i]
                if len(row) > 1 and row[1] and str(row[1]).strip():
                    try:
                        id_debiteur_dans_sheet = int(float(row[1]))
                        if id_debiteur_dans_sheet == debiteur_id:
                            echeances.append({
                                'id': int(float(row[0])) if row[0] else i,
                                'date': row[2] if len(row) > 2 else '',
                                'montant': self.clean_number(row[3]),
                                'pourcentage': self.clean_number(row[4]),
                                'statut': row[5] if len(row) > 5 else 'en_attente'
                            })
                            print(f"   ✅ Échéance trouvée: {row[2]} - {row[3]} FCFA")
                    except:
                        continue
            
            print(f"📊 {len(echeances)} échéances trouvées pour client {debiteur_id}")
            return echeances
        except Exception as e:
            print(f"❌ Erreur get_echeances_by_debiteur: {e}")
            return []
    
    def save_echeances(self, debiteur_id, echeances):
        if not self.client:
            return {'success': False, 'error': 'Service non connecté'}
        
        try:
            try:
                ws = self.sheet.worksheet("Echeances")
            except:
                ws = self.sheet.add_worksheet("Echeances", rows=100, cols=7)
                ws.update('A1:G1', [['ID', 'ID_Debiteur', 'Date', 'Montant', 'Pourcentage', 'Statut', 'Date création']])
            
            existing = ws.get_all_values()
            next_id = len(existing)
            
            for i, e in enumerate(echeances):
                new_id = next_id + i + 1
                ws.append_row([
                    new_id,
                    debiteur_id,
                    e['date'],
                    e['montant'],
                    str(e['pourcentage']).replace(',', '.'),
                    'en_attente',
                    datetime.now().isoformat()
                ])
                print(f"✅ Échéance ajoutée: {e['montant']} FCFA le {e['date']}")
            
            print(f"📊 {len(echeances)} échéances enregistrées pour client {debiteur_id}")
            return {'success': True, 'message': f'{len(echeances)} échéances programmées avec succès'}
            
        except Exception as e:
            print(f"❌ Erreur save_echeances: {e}")
            return {'success': False, 'error': str(e)}
    
    def get_historique_by_client(self, debiteur_id):
        historique = self.get_historique()
        return [h for h in historique if h.get('client_id') == debiteur_id]
    
    def update_all_echeances_statut(self, debiteur_id, nouveau_statut):
        if not self.client:
            return False
        try:
            ws = self.sheet.worksheet("Echeances")
            data = ws.get_all_values()
            for i in range(1, len(data)):
                if len(data[i]) > 1 and data[i][1] and int(float(data[i][1])) == debiteur_id:
                    ws.update_cell(i + 1, 6, nouveau_statut)
            return True
        except:
            return False
    
    def update_echeance_statut(self, echeance_id, nouveau_statut):
        if not self.client:
            return False
        try:
            ws = self.sheet.worksheet("Echeances")
            data = ws.get_all_values()
            for i in range(1, len(data)):
                if data[i][0] and int(float(data[i][0])) == echeance_id:
                    ws.update_cell(i + 1, 6, nouveau_statut)
                    return True
            return False
        except:
            return False
    
    def update_echeance_partiel(self, echeance_id, montant_restant):
        if not self.client:
            return False
        
        try:
            ws = self.sheet.worksheet("Echeances")
            data = ws.get_all_values()
            
            for i in range(1, len(data)):
                if data[i][0] and int(float(data[i][0])) == echeance_id:
                    ws.update_cell(i + 1, 4, montant_restant)
                    ws.update_cell(i + 1, 6, 'partiel')
                    return True
            return False
        except Exception as e:
            print(f"Erreur update_echeance_partiel: {e}")
            return False

    def update_echeance_montant(self, echeance_id, nouveau_montant):
        if not self.client:
            return False
        
        try:
            ws = self.sheet.worksheet("Echeances")
            data = ws.get_all_values()
            
            for i in range(1, len(data)):
                if data[i][0] and int(float(data[i][0])) == echeance_id:
                    ws.update_cell(i + 1, 4, nouveau_montant)
                    return True
            return False
        except Exception as e:
            print(f"Erreur update_echeance_montant: {e}")
            return False

    def get_config(self):
        if not self.client:
            return {'mot_de_passe': 'admin123'}
        try:
            ws = self.sheet.worksheet("Config")
            data = ws.get_all_values()
            config = {}
            for row in data:
                if len(row) >= 2:
                    config[row[0]] = row[1]
            return config
        except:
            return {'mot_de_passe': 'admin123'}

    def update_mot_de_passe(self, nouveau_mot_de_passe):
        if not self.client:
            return False
        try:
            ws = self.sheet.worksheet("Config")
            data = ws.get_all_values()
            for i, row in enumerate(data):
                if len(row) > 0 and row[0] == 'mot_de_passe':
                    ws.update_cell(i + 1, 2, nouveau_mot_de_passe)
                    return True
            ws.append_row(['mot_de_passe', nouveau_mot_de_passe])
            return True
        except:
            return False
    def clean_number(self, value):
        if not value:
            return 0
        if isinstance(value, (int, float)):
            return float(value)
        return float(str(value).replace(',', '.'))