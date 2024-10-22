from flask import Flask, request, jsonify, render_template, redirect, url_for
import os
from datetime import datetime
from googleapiclient.discovery import build
from google.oauth2.service_account import Credentials
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.platypus import Table, TableStyle
from reportlab.lib import colors
from PIL import Image
import io
from reportlab.lib.utils import ImageReader
import base64
from PyPDF2 import PdfReader, PdfWriter
import re
from urllib.parse import quote as url_quote


app = Flask(__name__)

SIGNATURE_IMAGE_PATH = 'signature_gerant.jpg'
GENERATED_CONTRACTS_FOLDER = 'generated_contracts'
if not os.path.exists(GENERATED_CONTRACTS_FOLDER):
    os.makedirs(GENERATED_CONTRACTS_FOLDER)

CONTRACTS_DRIVE_FOLDER_ID = '1RxN8sYGeECGGVOZlUF6yWwnVPU5Bp_gR'
PHOTOS_DRIVE_FOLDER_ID = '1IGERMj2fWN0uiKsg_y8RFIa3xgPPmVXN'

SPREADSHEET_ID = '16baOxeVOUcioLiEzfAwyedM5veJnOnxplKVIc2dNwtc'

creds = Credentials.from_service_account_file('credentials.json')

def create_drive_folder(drive_service, folder_name, parent_folder_id=None):
    folder_metadata = {
        'name': folder_name,
        'mimeType': 'application/vnd.google-apps.folder',
        'parents': [parent_folder_id] if parent_folder_id else []
    }
    folder = drive_service.files().create(body=folder_metadata, fields='id').execute()
    return folder.get('id')

def upload_file_to_drive(drive_service, file_path, folder_id, file_name):
    file_metadata = {
        'name': file_name,
        'parents': [folder_id]
    }
    if file_name.lower().endswith('.pdf'):
        mime_type = 'application/pdf'
    else:
        mime_type = 'image/jpeg'
    media = MediaFileUpload(file_path, mimetype=mime_type)
    uploaded_file = drive_service.files().create(body=file_metadata, media_body=media, fields='id, webViewLink').execute()
    return {'id': uploaded_file.get('id'), 'webViewLink': uploaded_file.get('webViewLink')}

def add_data_to_sheets(data, works, date):
    try:
        service = build('sheets', 'v4', credentials=creds)
        sheet = service.spreadsheets()
        artist_name = data.get('artistName', 'Inconnu')
        email = data.get('email', 'Inconnu')
        siret = data.get('siret', 'Inconnu')
        adresse = data.get('adresse', 'Inconnue')
        works_data = []
        for i, work in enumerate(works, 1):
            try:
                prix_artiste = float(work['prix_artiste']) if work['prix_artiste'] else 0.0
                prix_commission = float(work['prix_commission']) if work['prix_commission'] else 0.0
                prix_vente = float(work['prix_vente']) if work['prix_vente'] else 0.0
            except ValueError as e:
                prix_artiste = 0.0
                prix_commission = 0.0
                prix_vente = 0.0
            photo_urls = work['photos_urls']
            photo_urls += [''] * (3 - len(photo_urls))
            work_row = [
                date,
                artist_name,
                email,
                siret,
                adresse,
                work['nom_oeuvre'],
                work['dimensions'],
                work['annee'],
                f"{prix_artiste:.2f}€",
                f"{prix_commission:.2f}€",
                f"{prix_vente:.2f}€",
            ] + photo_urls
            works_data.append(work_row)
        body = {'values': works_data}
        result = sheet.values().append(
            spreadsheetId=SPREADSHEET_ID,
            range='tableau!A2',
            valueInputOption="RAW",
            body=body
        ).execute()
        return result
    except Exception as e:
        return str(e)

def download_and_validate_image(file_id, drive_service):
    try:
        request = drive_service.files().get_media(fileId=file_id)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            status, done = downloader.next_chunk()
        fh.seek(0)
        try:
            img = Image.open(fh)
            img.verify()
            fh.seek(0)
            return fh
        except (IOError, SyntaxError) as e:
            return None
    except Exception as e:
        return None

def get_image(image_data, max_width, max_height):
    img = Image.open(image_data)
    iw, ih = img.size
    aspect = ih / float(iw)
    if iw > ih:
        width = min(iw, max_width)
        height = width * aspect
    else:
        height = min(ih, max_height)
        width = height / aspect
    if width > max_width:
        width = max_width
        height = width * aspect
    if height > max_height:
        height = max_height
        width = height / aspect
    return width, height

def generate_contract_pdf(data, works, date, drive_service):
    contract_filename = f"{data['artistName']}_contract_{date}.pdf"
    contract_filepath = os.path.join(GENERATED_CONTRACTS_FOLDER, contract_filename)
    c = canvas.Canvas(contract_filepath, pagesize=A4)
    width, height = A4
    text = c.beginText(40, height - 50)
    text.setFont("Helvetica-Bold", 14)
    text.setTextOrigin(width / 2 - 180, height - 50)
    text.textLine("Contrat de commission portant dépôt d'Œuvres d'art")
    text.textLine("à la galerie UKA en vue de leur vente")
    text.setTextOrigin(40, height - 100)
    text.setFont("Helvetica", 12)
    text.textLine("")
    text.setFont("Helvetica", 12)
    text.textLine("LE PRESENT CONTRAT EST PASSE ENTRE :")
    text.textLine("")
    text.setFont("Helvetica-Bold", 12)
    text.textLine("L’ARTISTE :")
    text.setFont("Helvetica", 12)
    text.textLine(f"SIRET : {data['siret']}")
    text.textLine(f"NOM : {data['artistName']}")
    text.textLine(f"EMAIL : {data['email']}")
    text.textLine(f"ADRESSE : {data['adresse']}")
    text.textLine("")
    text.textLine("ET")
    text.textLine("")
    text.setFont("Helvetica-Bold", 12)
    text.textLine(f"LA GALERIE D’ART/ BOUTIK UKA")
    text.setFont("Helvetica", 12)
    text.textLine(f"ADRESSE : 6-7 LES POIRIERS, LA MARINA, 97110 POINTE A PITRE")
    text.textLine(f"SIREN : 829 320 670 000 13")
    text.textLine("")
    text.setFont("Helvetica-Bold", 12)
    text.textLine("PREAMBULE :")
    text.setFont("Helvetica", 12)
    text.textLine("La Galerie d'art entend vendre les œuvres d'art de l'artiste ;")
    text.textLine("En fait de quoi, les parties s'entendent sur ce qui suit :")
    text.textLine("")
    text.setFont("Helvetica-Bold", 12)
    text.textLine("Article 1 - La durée du contrat de dépôt")
    text.setFont("Helvetica", 12)
    text.textLine("1.1 La période de ce contrat de dépôt d'œuvres d'art en galerie est prévue pour un minimum")
    text.textLine("de six (6) semaines à partir de la date du présent contrat.")
    text.textLine("1.2 À l'échéance du contrat toutes les œuvres d'art non vendues seront susceptibles soit")
    text.textLine("d'être maintenues en dépôt, soit retournées à l'Artiste.")
    text.textLine("")
    text.setFont("Helvetica-Bold", 12)
    text.textLine("Article 2 - Structure des prix")
    text.setFont("Helvetica", 12)
    text.textLine("2.1 Le prix des œuvres d'art")
    text.textLine("2.1.1 Le prix coûtant de l'œuvre est déterminé par l'Artiste en consultation avec la Galerie.")
    text.textLine("2.1.2 La commission de la Galerie d'art est de 30% + 10% incluant la TVA et les frais de TPE.")
    text.textLine("Le prix coûtant plus la commission de 40% de la Galerie d'art constitue le prix de vente")
    text.textLine("offert au public. La Galerie d'art ne saurait modifier le prix de vente recommandé sans")
    text.textLine("un accord écrit de la part de l'Artiste.")
    text.textLine("")
    text.setFont("Helvetica-Bold", 12)
    text.textLine("Article 3 – Engagement de la galerie d’art Uka")
    text.setFont("Helvetica", 12)
    text.textLine("3.1 Ouverture de la galerie : La galerie est ouverte du lundi au samedi de 10h30 à 19h30.")
    text.textLine("3.2 Prise en charge du vernissage de l’exposition et communication.")
    text.textLine("3.3 Impression des cartels et biographies des artistes, matériel fourni.")
    text.textLine("3.4 Assurance des œuvres pendant la durée de l'exposition.")
    text.textLine("")
    c.drawText(text)
    c.showPage()
    text = c.beginText(40, height - 50)
    text.setFont("Helvetica", 12)
    text.setFont("Helvetica-Bold", 12)
    text.textLine("Article 4 – Engagement des artistes exposants")
    text.setFont("Helvetica", 12)
    text.textLine("4.1 Les Œuvres")
    text.textLine("Les œuvres exposées doivent être fournies avec un système d’accrochage prêt et adéquat")
    text.textLine("aux cimaises de la galerie.")
    text.textLine("L’impression et l’encadrement sont à la charge de l’artiste.")
    text.textLine("")
    text.textLine("4.2 Cartels et biographie")
    text.textLine("L’artiste doit fournir les éléments demandés par la galerie pour la réalisation des cartels.")
    text.textLine("")
    text.textLine("4.3 Présence des artistes")
    text.textLine("Il peut être demandé aux artistes de venir à la rencontre du public le samedi après-midi")
    text.textLine("selon des créneaux horaires à définir.")
    text.textLine("")
    text.setFont("Helvetica-Bold", 12)
    text.textLine("Article 5 – Cession des droits d’auteurs sur les œuvres")
    text.setFont("Helvetica", 12)
    text.textLine("Par la signature de ce contrat l’artiste cède ces droits d’auteurs sur les œuvres exposées")
    text.textLine("pendant la durée de l’exposition, pour la promotion de celle-ci sur les réseaux sociaux ou")
    text.textLine("dans la presse.")
    text.textLine("")
    c.drawText(text)
    table_data = []
    table_data.append(["NOM DE L’ŒUVRE", "FORMAT", "ANNÉE", "PRIX ARTISTE", "COMMISSION", "PRIX DE VENTE"])
    for work in works:
        row = [
            work['nom_oeuvre'],
            work['dimensions'],
            work['annee'],
            f"{float(work['prix_artiste']):.2f}€",
            f"{float(work['prix_commission']):.2f}€",
            f"{float(work['prix_vente']):.2f}€"
        ]
        table_data.append(row)
    table = Table(table_data, colWidths=[120, 50, 50, 80, 80, 80])
    style = TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#d3d3d3')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('ALIGN', (0, 1), (-1, -1), 'CENTER'),
        ('ALIGN', (3, 1), (-1, -1), 'RIGHT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 9),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ])
    table.setStyle(style)
    table_width, table_height = table.wrapOn(c, width, height)
    x = 40
    y = height - 300
    table.drawOn(c, x, y - table_height)
    signature_y_position = 50
    c.drawImage(SIGNATURE_IMAGE_PATH, width - 200, signature_y_position, width=150, preserveAspectRatio=True, mask='auto')
    c.drawString(40, signature_y_position - 20, f"Fait le {date} à Pointe-à-Pitre.")
    c.drawString(40, signature_y_position - 40, "L'Artiste")
    c.drawString(width - 200, signature_y_position - 40, "La Galerie d'art (signature)")
    c.showPage()
    y_position = height - 100
    image_padding = 20
    max_image_height = height / 2 - 60
    max_image_width = width - 2 * 60
    for work in works:
        photos_file_ids = work.get('photos_file_ids', [])
        for file_id in photos_file_ids:
            img_data = download_and_validate_image(file_id, drive_service)
            if img_data:
                try:
                    img_width, img_height = get_image(img_data, max_image_width, max_image_height)
                    img_reader = ImageReader(img_data)
                    x_position = (width - img_width) / 2
                    c.drawImage(img_reader, x_position, y_position - img_height, width=img_width, height=img_height)
                    c.setFont("Helvetica-Bold", 12)
                    c.drawCentredString(width / 2, y_position - img_height - 20, work['nom_oeuvre'])
                    y_position -= img_height + image_padding + 40
                except Exception as e:
                    pass
            else:
                pass
            if y_position - max_image_height < 60:
                c.showPage()
                y_position = height - 100
    c.save()
    return contract_filepath

def extract_file_id_from_url(url):
    match = re.search(r'/d/([a-zA-Z0-9_-]+)', url)
    if match:
        return match.group(1)
    else:
        raise ValueError("Impossible d'extraire l'ID du fichier à partir de l'URL.")

def download_file_from_drive(file_id, drive_service):
    try:
        request = drive_service.files().get_media(fileId=file_id)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            status, done = downloader.next_chunk()
        fh.seek(0)
        return fh
    except Exception as e:
        return None

def integrate_signature_into_pdf(contract_pdf_data, signature_data, artist_name):
    contract_pdf_data.seek(0)
    existing_pdf = PdfReader(contract_pdf_data)
    num_pages = len(existing_pdf.pages)

    packet = io.BytesIO()
    can = canvas.Canvas(packet, pagesize=A4)
    width, height = A4

    signature_image = Image.open(io.BytesIO(signature_data))

    if signature_image.mode in ('RGBA', 'LA'):
        background = Image.new('RGB', signature_image.size, (255, 255, 255))
        alpha_channel = signature_image.split()[-1]
        background.paste(signature_image, mask=alpha_channel)
        signature_image = background
    else:
        signature_image = signature_image.convert('RGB')

    signature_width = 200
    aspect = signature_image.height / signature_image.width
    signature_height = signature_width * aspect

    x_position = 100
    y_position = 50

    signature_reader = ImageReader(signature_image)
    can.drawImage(signature_reader, x_position, y_position, width=signature_width, height=signature_height)
    can.save()

    packet.seek(0)
    new_pdf = PdfReader(packet)
    output = PdfWriter()

    for page_num in range(num_pages):
        page = existing_pdf.pages[page_num]
        if page_num == num_pages - 1:
            page.merge_page(new_pdf.pages[0])
        output.add_page(page)

    signed_contract_filepath = os.path.join(GENERATED_CONTRACTS_FOLDER, f"{artist_name}_contract_signé_{datetime.now().strftime('%Y-%m-%d')}.pdf")
    with open(signed_contract_filepath, 'wb') as out_file:
        output.write(out_file)

    return signed_contract_filepath


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
        num_works = int(form_data.get('numWorks'))
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
        artist_name = data['artist_name']
        contract_url = data['contract_url']
        drive_service = build('drive', 'v3', credentials=creds)
        header, encoded = signature_data_url.split(",", 1)
        signature_data = base64.b64decode(encoded)
        contract_file_id = extract_file_id_from_url(contract_url)
        contract_pdf_data = download_file_from_drive(contract_file_id, drive_service)
        signed_contract_filepath = integrate_signature_into_pdf(contract_pdf_data, signature_data, artist_name)
        signed_contract_filename = f"{artist_name}_contract_signé_{datetime.now().strftime('%Y-%m-%d')}.pdf"
        signed_contract_info = upload_file_to_drive(drive_service, signed_contract_filepath, CONTRACTS_DRIVE_FOLDER_ID, signed_contract_filename)
        signed_contract_url = signed_contract_info['webViewLink']
        return jsonify({"status": "success", "signed_contract_url": signed_contract_url})
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return jsonify({"status": "error", "message": str(e)})

if __name__ == '__main__':
    app.run(debug=True)
