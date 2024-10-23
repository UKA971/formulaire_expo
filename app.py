from flask import Flask, request, jsonify, render_template, redirect, url_for
import os
from datetime import datetime
from googleapiclient.discovery import build
from google.oauth2 import service_account
from googleapiclient.http import MediaFileUpload
from dotenv import load_dotenv
import base64
from fpdf import FPDF
import traceback
from pytz import timezone

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

def fix_base64_padding(data):
    """Fix padding issues for Base64 encoded strings."""
    return data + '=' * (-len(data) % 4)

def fix_private_key(key_str):
    """Formate correctement la clé privée avec le bon format et padding."""
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
    
    return key_str

def setup_google_credentials():
    try:
        google_private_key = os.getenv("GOOGLE_PRIVATE_KEY")
        if not google_private_key:
            raise ValueError("GOOGLE_PRIVATE_KEY environment variable is not set")

        # Correction du padding et format de la clé privée
        google_private_key = fix_base64_padding(google_private_key)
        google_private_key = fix_private_key(google_private_key)

        # Configuration des credentials
        creds = service_account.Credentials.from_service_account_info({
            "type": "service_account",
            "project_id": os.getenv("GOOGLE_PROJECT_ID"),
            "private_key_id": os.getenv("GOOGLE_PRIVATE_KEY_ID"),
            "private_key": google_private_key,
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
        raise

def validate_price(value):
    try:
        return float(value)
    except ValueError:
        raise ValueError(f"Le prix '{value}' n'est pas valide.")

def get_current_date():
    gwada_tz = timezone('America/Guadeloupe')
    return datetime.now(gwada_tz).strftime("%Y-%m-%d")

def add_data_to_sheets(form_data, works, date):
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

def generate_contract_pdf(form_data, works, date):
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
        date = get_current_date()
        email = form_data.get('email', 'Inconnu')
        form_data = form_data.copy()
        form_data['email'] = email

        creds = setup_google_credentials()
        drive_service = build('drive', 'v3', credentials=creds)
        
        artist_name = form_data.get('artistName')
        if not artist_name or not email:
            raise ValueError("Les informations de l'artiste sont manquantes.")
        
        artist_folder_id = create_drive_folder(drive_service, artist_name, parent_folder_id=PHOTOS_DRIVE_FOLDER_ID)
        
        works = []
        num_works = int(form_data.get('numWorks', 0))
        for i in range(1, num_works + 1):
            work = {
                'nom_oeuvre': form_data.get(f'nomOeuvre{i}'),
                'dimensions': form_data.get(f'dimensionsOeuvre{i}'),
                'annee': form_data.get(f'anneeOeuvre{i}'),
                'prix_artiste': validate_price(form_data.get(f'prixOeuvre{i}')),
                'prix_commission': validate_price(form_data.get(f'prixOeuvre{i}')) * 0.40,
                'prix_vente': validate_price(form_data.get(f'prixOeuvre{i}')) * 1.40,
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
                        try:
                            # Sauvegarde temporaire
                            photo.save(photo_filename)
                            # Upload sur Google Drive
                            photo_info = upload_file_to_drive(drive_service, photo_filename, work_folder_id, photo_filename)
                            # Nettoyage local du fichier photo
                            os.remove(photo_filename)
                            work['photos_urls'].append(photo_info['webViewLink'])
                            work['photos_file_ids'].append(photo_info['id'])
                        except Exception as upload_error:
                            print(f"Erreur lors du téléchargement de {photo_filename} : {str(upload_error)}")
                            raise
            
            works.append(work)
        
        add_data_to_sheets(form_data, works, date)
        contract_filename = generate_contract_pdf(form_data, works, date)
        contract_info = upload_file_to_drive(drive_service, contract_filename, CONTRACTS_DRIVE_FOLDER_ID, contract_filename)
        
        if not contract_info or 'webViewLink' not in contract_info:
            raise ValueError("Erreur lors de la récupération du lien de téléchargement du contrat.")
        
        return redirect(contract_info['webViewLink'])
        
    except Exception as e:
        print(f"Erreur lors du traitement du formulaire : {str(e)}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
