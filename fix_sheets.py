from sheets_service import SheetsService
from datetime import datetime

sheets = SheetsService()

if not sheets.client:
    print("❌ Non connecté")
    exit()

# Récupérer la feuille
ws = sheets.sheet.worksheet("Debiteurs")

# Supprimer toutes les lignes après l'en-tête
ws.batch_clear(["A2:I1000"])
print("✅ Lignes supprimées")

# Ajouter les bons en-têtes
headers = ["ID", "Nom", "Téléphone", "Email", "Montant total", "Solde restant", "Acompte", "Date création", "Notes"]
ws.update('A1:I1', [headers])
print("✅ En-têtes corrigés")

# Ajouter des clients de test
clients = [
    [1, "Jean Dupont", "90123456", "jean@email.com", 100000, 40000, 60000, datetime.now().isoformat(), ""],
    [2, "Marie Koné", "90234567", "marie@email.com", 250000, 150000, 100000, datetime.now().isoformat(), ""],
    [3, "Ali Touré", "90345678", "ali@email.com", 75000, 75000, 0, datetime.now().isoformat(), ""],
]

for c in clients:
    ws.append_row(c)
    print(f"✅ Client {c[0]} ajouté: {c[1]}")

print("\n🎉 Terminé !")