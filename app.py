from flask import Flask, request, jsonify, render_template, redirect, url_for
import os
from datetime import datetime
from googleapiclient.discovery import build
from google.oauth2.service_account import Credentials
from googleapiclient.http import MediaFileUpload
from dotenv import load_dotenv
import base64
from fpdf import FPDF

load_dotenv()

app = Flask(__name__)

SIGNATURE_IMAGE_PATH = 'signature_gerant.jpg'
GENERATED_CONTRACTS_FOLDER = 'generated_contracts'
if not os.path.exists(GENERATED_CONTRACTS_FOLDER):
    os.makedirs(GENERATED_CONTRACTS_FOLDER)

# Configurations Google
CONTRACTS_DRIVE_FOLDER_ID = os.getenv('CONTRACTS_DRIVE_FOLDER_ID')
PHOTOS_DRIVE_FOLDER_ID = os.getenv('PHOTOS_DRIVE_FOLDER_ID')
SPREADSHEET_ID = os.getenv('SPREADSHEET_ID')

def fix_private_key(key_str):
    """Formate correctement la clé privée avec le bon format et padding"""
    if not key_str:
        raise ValueError("Private key is empty")
    
    # Supprime tous les espaces en début et fin
    key_str = key_str.strip()
    
    # Supprime les guillemets si présents
    key_str = key_str.strip('"\'')
    
    # Remplace les \\n par \n
    key_str = key_str.replace('\\n', '\n')
    
    # Vérifie et ajoute les en-têtes si nécessaire
    if '-----BEGIN PRIVATE KEY-----' not in key_str:
        key_str = '-----BEGIN PRIVATE KEY-----\n' + key_str
    if '-----END PRIVATE KEY-----' not in key_str:
        key_str = key_str + '\n-----END PRIVATE KEY-----'
    
    # Assure-toi que chaque ligne a la bonne longueur
    parts = key_str.split('\n')
    formatted_parts = []
    for part in parts:
        if part.strip() and not part.startswith('-----') and not part.endswith('-----'):
            # Ajoute le padding si nécessaire
            padding = len(part) % 4
            if padding:
                part += '=' * (4 - padding)
        formatted_parts.append(part)
    
    return '\n'.join(formatted_parts)

def setup_google_credentials():
    """Configure les credentials Google avec gestion améliorée des erreurs"""
    try:
        google_private_key = os.getenv("GOOGLE_PRIVATE_KEY")
        if not google_private_key:
            raise ValueError("GOOGLE_PRIVATE_KEY environment variable is not set")
        
        fixed_private_key = fix_private_key(google_private_key)
        
        # Debug logging
        print("Formatted key start:", fixed_private_key[:50])
        print("Formatted key end:", fixed_private_key[-50:])
        
        creds = Credentials.from_service_account_info({
            "type": os.getenv("GOOGLE_SERVICE_ACCOUNT_TYPE"),
            "project_id": os.getenv("GOOGLE_PROJECT_ID"),
            "private_key_id": os.getenv("GOOGLE_PRIVATE_KEY_ID"),
            "private_key": fixed_private_key,
            "client_email": os.getenv("GOOGLE_CLIENT_EMAIL"),
            "client_id": os.getenv("GOOGLE_CLIENT_ID"),
            "auth_uri": os.getenv("GOOGLE_AUTH_URI"),
            "token_uri": os.getenv("GOOGLE_TOKEN_URI"),
            "auth_provider_x509_cert_url": os.getenv("GOOGLE_AUTH_PROVIDER_CERT_URL"),
            "client_x509_cert_url": os.getenv("GOOGLE_CLIENT_CERT_URL"),
        })
        return creds
    except Exception as e:
        print(f"Error initializing credentials: {str(e)}")
        # Debug logging des variables d'environnement (sauf la clé privée)
        for key, value in os.environ.items():
            if 'PRIVATE' not in key.upper():
                print(f"{key}: {value[:20]}..." if value else f"{key}: None")
        raise

def add_data_to_sheets(form_data, works, date):
    """Ajoute les données du contrat dans Google Sheets"""
    try:
        creds = setup_google_credentials()
        service = build('sheets', 'v4', credentials=creds)
        
        for work in works:
            row_data = [
                date,
                form_data.get('artistName'),
                form_data.get('email'),
                work['nom_oeuvre'],
                work['dimensions'],
                work['annee'],
                work['prix_artiste'],
                work['prix_commission'],
                work['prix_vente'],
                ', '.join(work['photos_urls'])
            ]
            
            body = {
                'values': [row_data]
            }
            
            service.spreadsheets().values().append(
                spreadsheetId=SPREADSHEET_ID,
                range='Feuille1!A:J',
                valueInputOption='USER_ENTERED',
                body=body
            ).execute()
            
    except Exception as e:
        print(f"Erreur lors de l'ajout des données dans Sheets: {str(e)}")
        raise

def generate_contract_pdf(form_data, works, date, drive_service):
    """Génère le PDF du contrat"""
    try:
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font('Arial', 'B', 16)
        
        # En-tête
        pdf.cell(0, 10, 'CONTRAT DE DEPOT', 0, 1, 'C')
        pdf.ln(10)
        
        # Informations de l'artiste
        pdf.set_font('Arial', '', 12)
        pdf.cell(0, 10, f"Date: {date}", 0, 1)
        pdf.cell(0, 10, f"Artiste: {form_data.get('artistName')}", 0, 1)
        pdf.cell(0, 10, f"Email: {form_data.get('email')}", 0, 1)
        pdf.ln(10)
        
        # Liste des œuvres
        pdf.set_font('Arial', 'B', 14)
        pdf.cell(0, 10, 'Œuvres déposées:', 0, 1)
        pdf.ln(5)
        
        pdf.set_font('Arial', '', 12)
        for work in works:
            pdf.cell(0, 10, f"Titre: {work['nom_oeuvre']}", 0, 1)
            pdf.cell(0, 10, f"Dimensions: {work['dimensions']}", 0, 1)
            pdf.cell(0, 10, f"Année: {work['annee']}", 0, 1)
            pdf.cell(0, 10, f"Prix artiste: {work['prix_artiste']}€", 0, 1)
            pdf.cell(0, 10, f"Prix de vente: {work['prix_vente']}€", 0, 1)
            pdf.ln(5)
        
        # Signature
        pdf.ln(20)
        pdf.cell(0, 10, 'Signatures:', 0, 1)
        pdf.ln(30)
        pdf.cell(90, 10, 'Le gérant:', 0, 0)
        pdf.cell(90, 10, "L'artiste:", 0, 1)
        
        # Sauvegarde du PDF
        filename = f"{GENERATED_CONTRACTS_FOLDER}/contrat_{form_data.get('artistName')}_{date}.pdf"
        pdf.output(filename)
        
        return filename
        
    except Exception as e:
        print(f"Erreur lors de la génération du PDF: {str(e)}")
        raise

@app.route('/')
def form():
    return render_template('form.html')

@app.route('/submit', methods=['POST'])
def submit():
    try:
        form_data = request.form
        files = request.files
        date = datetime.now().strftime("%Y-%m-%d")
        email = form_data.get('email', 'Inconnu')
        form_data = form_data.copy()
        form_data['email'] = email

        # Initialisation du service Drive avec les credentials améliorés
        creds = setup_google_credentials()
        drive_service = build('drive', 'v3', credentials=creds)
        
        artist_name = form_data.get('artistName')
        artist_folder_id = create_drive_folder(drive_service, artist_name, parent_folder_id=PHOTOS_DRIVE_FOLDER_ID)
        
        works = []
        num_works = int(form_data.get('numWorks', 0))
        for i in range(1, num_works + 1):
            work = {
                'nom_oeuvre': form_data.get(f'nomOeuvre{i}'),
                'dimensions': form_data.get(f'dimensionsOeuvre{i}'),
                'annee': form_data.get(f'anneeOeuvre{i}'),
                'prix_artiste': form_data.get(f'prixOeuvre{i}'),
                'prix_commission': float(form_data.get(f'prixOeuvre{i}')) * 0.40,
                'prix_vente': float(form_data.get(f'prixOeuvre{i}')) * 1.40,
                'photos_urls': [],
                'photos_file_ids': []
            }
            
            work_folder_id = create_drive_folder(drive_service, work['nom_oeuvre'], parent_folder_id=artist_folder_id)
            
            for j in range(1, 4):
                photo_field = f'photoOeuvre{i}_{j}'
                if photo_field in files:
                    photo = files[photo_field]
                    if photo.filename != '':
                        photo_filename = photo.filename
                        photo.save(photo_filename)
                        photo_info = upload_file_to_drive(drive_service, photo_filename, work_folder_id, photo_filename)
                        os.remove(photo_filename)
                        work['photos_urls'].append(photo_info['webViewLink'])
                        work['photos_file_ids'].append(photo_info['id'])
            
            works.append(work)
            
        add_data_to_sheets(form_data, works, date)
        contract_filepath = generate_contract_pdf(form_data, works, date, drive_service)
        contract_info = upload_file_to_drive(drive_service, contract_filepath, CONTRACTS_DRIVE_FOLDER_ID, os.path.basename(contract_filepath))
        contract_url = contract_info['webViewLink']
        
        return jsonify({
            "status": "success",
            "redirect_url": url_for('sign_contract', contract_url=contract_url, artist_name=artist_name)
        })
        
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return jsonify({"status": "error", "message": str(e)})

@app.route('/sign_contract')
def sign_contract():
    contract_url = request.args.get('contract_url')
    artist_name = request.args.get('artist_name')
    return render_template('sign_contract.html', contract_url=contract_url, artist_name=artist_name)

@app.route('/save_signed_contract', methods=['POST'])
def save_signed_contract():
    try:
        data = request.get_json()
        signature_data_url = data['signature']
        
        # Vérification et ajout du padding
        padding = len(signature_data_url) % 4
        if padding != 0:
            signature_data_url += '=' * (4 - padding)

        # Extraire le contenu de la signature
        header, encoded = signature_data_url.split(",", 1)
        signature_data = base64.b64decode(encoded)
        
        # Code pour sauvegarder la signature...
        # À implémenter selon vos besoins
        
        return jsonify({"status": "success"})
        
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return jsonify({"status": "error", "message": str(e)})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000)))
