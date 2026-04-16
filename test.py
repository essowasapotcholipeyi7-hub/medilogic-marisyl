import os
import gspread
from google.oauth2.service_account import Credentials

print("1️⃣ Vérification du fichier credentials.json...")

creds_path = 'credentials.json'
if os.path.exists(creds_path):
    print("✅ credentials.json trouvé")
else:
    print("❌ credentials.json NON trouvé")
    print(f"📁 Chemin actuel: {os.getcwd()}")
    print("📁 Fichiers dans le dossier:")
    for f in os.listdir('.'):
        print(f"   - {f}")

print("\n2️⃣ Tentative de connexion à Google Sheets...")

try:
    SCOPES = ['https://www.googleapis.com/auth/spreadsheets', 
              'https://www.googleapis.com/auth/drive']
    SPREADSHEET_ID = '1Sv7GQhBGS5UBZ0_QtG23c8SKiNBgEMI6mh60VZSLc3o'
    
    creds = Credentials.from_service_account_file(creds_path, scopes=SCOPES)
    client = gspread.authorize(creds)
    sheet = client.open_by_key(SPREADSHEET_ID)
    
    print("✅ Connexion réussie !")
    print(f"📊 Titre du classeur: {sheet.title}")
    
except Exception as e:
    print(f"❌ Erreur: {e}")