from flask import Flask, request, jsonify, render_template, redirect, url_for
import os
from datetime import datetime
from googleapiclient.discovery import build
from google.oauth2.service_account import Credentials
from googleapiclient.http import MediaFileUpload
from dotenv import load_dotenv  # Importation de dotenv
import base64

load_dotenv()  # Chargement des variables d'environnement

app = Flask(__name__)

SIGNATURE_IMAGE_PATH = 'signature_gerant.jpg'
GENERATED_CONTRACTS_FOLDER = 'generated_contracts'
if not os.path.exists(GENERATED_CONTRACTS_FOLDER):
    os.makedirs(GENERATED_CONTRACTS_FOLDER)

# Chargement des identifiants depuis les variables d'environnement
CONTRACTS_DRIVE_FOLDER_ID = os.getenv('CONTRACTS_DRIVE_FOLDER_ID')
PHOTOS_DRIVE_FOLDER_ID = os.getenv('PHOTOS_DRIVE_FOLDER_ID')
SPREADSHEET_ID = os.getenv('SPREADSHEET_ID')

# Vérification des variables d'environnement pour Google
google_private_key = os.getenv("GOOGLE_PRIVATE_KEY")
if google_private_key is None:
    raise ValueError("La variable d'environnement GOOGLE_PRIVATE_KEY n'est pas définie.")

# Remplacer les caractères de nouvelle ligne
google_private_key = google_private_key.replace('\\n', '\n')

# Charger les identifiants Google
creds = Credentials.from_service_account_info(
    {
        "type": os.getenv("GOOGLE_SERVICE_ACCOUNT_TYPE"),
        "project_id": os.getenv("GOOGLE_PROJECT_ID"),
        "private_key_id": os.getenv("GOOGLE_PRIVATE_KEY_ID"),
        "private_key": google_private_key,
        "client_email": os.getenv("GOOGLE_CLIENT_EMAIL"),
        "client_id": os.getenv("GOOGLE_CLIENT_ID"),
        "auth_uri": os.getenv("GOOGLE_AUTH_URI"),
        "token_uri": os.getenv("GOOGLE_TOKEN_URI"),
        "auth_provider_x509_cert_url": os.getenv("GOOGLE_AUTH_PROVIDER_CERT_URL"),
        "client_x509_cert_url": os.getenv("GOOGLE_CLIENT_CERT_URL"),
    }
)

def create_drive_folder(drive_service, folder_name, parent_folder_id=None):
    folder_metadata = {
        'name': folder_name,
        'mimeType': 'application/vnd.google-apps.folder',
        'parents': [parent_folder_id] if parent_folder_id else []
    }
    folder = drive_service.files().create(body=folder_metadata, fields='id').execute()
    return folder.get('id')

def upload_file_to_drive(drive_service, file_path, parent_folder_id, file_name):
    file_metadata = {
        'name': file_name,
        'parents': [parent_folder_id]
    }
    media = MediaFileUpload(file_path)
    file = drive_service.files().create(body=file_metadata, media_body=media, fields='id, webViewLink').execute()
    return file

def add_data_to_sheets(form_data, works, date):
    # Cette fonction doit être implémentée pour ajouter des données dans Google Sheets
    pass

def generate_contract_pdf(form_data, works, date, drive_service):
    # Cette fonction doit être implémentée pour générer un PDF du contrat
    return "path/to/generated_contract.pdf"

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
        redirect_url = url_for('sign_contract', contract_url=contract_url, artist_name=artist_name)
        return jsonify({"status": "success", "redirect_url": redirect_url})
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

        # Code pour sauvegarder la signature ici...

    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return jsonify({"status": "error", "message": str(e)})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000)))  # 5000 est le port par défaut
