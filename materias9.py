import streamlit as st
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from datetime import datetime, timedelta
import ssl
from email.utils import formatdate
import tempfile
import paramiko
import csv
import time

# Cargar configuración desde secrets.toml
def load_config():
    return {
        'SMTP_SERVER': st.secrets["smtp_server"],
        'SMTP_PORT': st.secrets["smtp_port"],
        'EMAIL_USER': st.secrets["email_user"],
        'EMAIL_PASSWORD': st.secrets["email_password"],
        'NOTIFICATION_EMAIL': st.secrets["notification_email"],
        'CSV_MATERIAS': st.secrets["csv_materias_file"],
        'MAX_FILE_SIZE_MB': st.secrets.get("max_file_size_mb", 10),
        'TIMEOUT_SECONDS': st.secrets.get("timeout_seconds", 30),
        'SYNC_INTERVAL_MINUTES': st.secrets.get("sync_interval_minutes", 30),
        'REMOTE': {
            'HOST': st.secrets["remote_host"],
            'USER': st.secrets["remote_user"],
            'PASSWORD': st.secrets["remote_password"],
            'PORT': st.secrets["remote_port"],
            'DIR': st.secrets["remote_dir"],
            'FILES': {
                'Cálculo Diferencial e Integral III': st.secrets["remote_calculo3"],
                'Cálculo Diferencial e Integral IV': st.secrets["remote_calculo4"],
                'Estadística no Paramétrica': st.secrets["remote_parametrica"],
                'Bioestadística I': st.secrets["remote_bioestadistica1"],
                'Bioestadística II': st.secrets["remote_bioestadistica2"],
                'Análisis Multicategórico': st.secrets["remote_categorico"]
            }
        }
    }

CONFIG = load_config()

# Configuración de archivos locales
ARCHIVOS = {
    'Cálculo Diferencial e Integral III': 'registro_calculo3.txt',
    'Cálculo Diferencial e Integral IV': 'registro_calculo4.txt',
    'Estadística no Paramétrica': 'registro_parametrica.txt',
    'Bioestadística I': 'registro_bioestadistica1.txt',
    'Bioestadística II': 'registro_bioestadistica2.txt',
    'Análisis Multicategórico': 'registro_categorico.txt'
}

# Inicializar archivos
def init_files():
    """Crea los archivos de registro si no existen"""
    for materia, archivo in ARCHIVOS.items():
        if not os.path.exists(archivo):
            with open(archivo, 'w', encoding='utf-8') as f:
                f.write(f"Alumnos inscritos en {materia}\n\n")

init_files()

def sync_with_remote():
    """Sincroniza archivos locales con el servidor remoto"""
    try:
        transport = paramiko.Transport((CONFIG['REMOTE']['HOST'], CONFIG['REMOTE']['PORT']))
        transport.default_window_size = 2147483647
        transport.banner_timeout = CONFIG['TIMEOUT_SECONDS']
        transport.connect(username=CONFIG['REMOTE']['USER'], password=CONFIG['REMOTE']['PASSWORD'])
        sftp = paramiko.SFTPClient.from_transport(transport)
        
        for materia, local_file in ARCHIVOS.items():
            remote_file = os.path.join(CONFIG['REMOTE']['DIR'], CONFIG['REMOTE']['FILES'][materia])
            try:
                sftp.get(remote_file, local_file)
                st.toast(f"Sincronizado: {materia}", icon="✅")
            except FileNotFoundError:
                st.toast(f"Archivo remoto no encontrado: {materia}", icon="⚠️")
            except Exception as e:
                st.toast(f"Error sincronizando {materia}: {str(e)}", icon="❌")
        
        sftp.close()
        transport.close()
        return True
    except Exception as e:
        st.toast(f"Error de conexión SFTP: {str(e)}", icon="❌")
        return False

def obtener_alumnos(materia):
    """Obtiene la lista de alumnos de una materia"""
    try:
        if materia not in ARCHIVOS:
            return []
            
        with open(ARCHIVOS[materia], 'r', encoding='utf-8') as f:
            lineas = f.readlines()[2:]  # Saltar encabezado
            
        alumnos = []
        for linea in lineas:
            if linea.strip():
                partes = linea.strip().split('|')
                if len(partes) >= 3:
                    alumnos.append({
                        'fecha': partes[0].strip(),
                        'nombre': partes[1].strip(),
                        'email': partes[2].strip()
                    })
        return alumnos
        
    except Exception as e:
        st.error(f"Error al leer archivo: {str(e)}")
        return []

def registrar_alumno(nombre, email, materias):
    """Registra un alumno en las materias seleccionadas"""
    try:
        fecha = datetime.now().strftime('%Y-%m-%d %H:%M')
        
        for materia in materias:
            if materia in ARCHIVOS:
                with open(ARCHIVOS[materia], 'a', encoding='utf-8') as f:
                    f.write(f"{fecha} | {nombre} | {email}\n")
        
        # Registrar en CSV de materias
        with open(CONFIG['CSV_MATERIAS'], 'a', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow([fecha, nombre, email, ', '.join(materias)])
        
        # Notificar por correo
        asunto = f"Nuevo registro: {nombre}"
        cuerpo = f"""
        <html>
            <body>
                <h2>Nuevo registro en el sistema académico</h2>
                <p><strong>Nombre:</strong> {nombre}</p>
                <p><strong>Email:</strong> {email}</p>
                <p><strong>Materias:</strong> {', '.join(materias)}</p>
                <p><strong>Fecha:</strong> {fecha}</p>
            </body>
        </html>
        """
        enviar_correo(CONFIG['NOTIFICATION_EMAIL'], asunto, cuerpo)
        
        return True
    except Exception as e:
        st.error(f"Error al registrar: {str(e)}")
        return False

def enviar_correo(destinatario, asunto, cuerpo, archivo_adjunto=None):
    """Envía un correo electrónico con manejo de errores y adjuntos"""
    try:
        if archivo_adjunto and os.path.getsize(archivo_adjunto) > CONFIG['MAX_FILE_SIZE_MB'] * 1024 * 1024:
            st.error(f"El archivo excede el tamaño máximo de {CONFIG['MAX_FILE_SIZE_MB']}MB")
            return False

        msg = MIMEMultipart()
        msg['From'] = CONFIG['EMAIL_USER']
        msg['To'] = destinatario
        msg['Subject'] = asunto
        msg['Date'] = formatdate(localtime=True)
        
        msg.attach(MIMEText(cuerpo, 'html', _charset='utf-8'))
        
        if archivo_adjunto:
            with open(archivo_adjunto, "rb") as f:
                part = MIMEApplication(f.read(), Name=os.path.basename(archivo_adjunto))
                part['Content-Disposition'] = f'attachment; filename="{os.path.basename(archivo_adjunto)}"'
                msg.attach(part)
        
        context = ssl.create_default_context()
        context.timeout = CONFIG['TIMEOUT_SECONDS']
        
        with smtplib.SMTP(CONFIG['SMTP_SERVER'], CONFIG['SMTP_PORT'], timeout=CONFIG['TIMEOUT_SECONDS']) as server:
            server.ehlo()
            server.starttls(context=context)
            server.ehlo()
            server.login(CONFIG['EMAIL_USER'], CONFIG['EMAIL_PASSWORD'])
            server.send_message(msg)
        
        return True
    except smtplib.SMTPAuthenticationError:
        st.error("Error de autenticación. Verifica usuario y contraseña.")
    except Exception as e:
        st.error(f"Error al enviar correo: {str(e)}")
    return False

def main():
    st.set_page_config(
        page_title="Sistema Académico",
        page_icon="🎓",
        layout="centered"
    )
    
    # Sincronización automática al inicio
    if 'last_sync' not in st.session_state or \
       datetime.now() - st.session_state.last_sync > timedelta(minutes=CONFIG['SYNC_INTERVAL_MINUTES']):
        with st.spinner("Sincronizando con servidor..."):
            sync_with_remote()
            st.session_state.last_sync = datetime.now()
    
    st.title("🎓 Sistema de Inscripción Académica")
    
    # Verificar y crear archivo CSV si no existe
    if not os.path.exists(CONFIG['CSV_MATERIAS']):
        with open(CONFIG['CSV_MATERIAS'], 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(['Fecha', 'Nombre', 'Email', 'Materias'])
    
    modo = st.sidebar.radio(
        "Modo de operación",
        ["Estudiante", "Profesor"],
        horizontal=True
    )
    
    if modo == "Estudiante":
        st.header("📝 Registro de Estudiante")
        
        with st.form("form_registro", border=True):
            nombre = st.text_input("Nombre completo*")
            email = st.text_input("Correo electrónico*")
            
            st.markdown("**Selecciona tus materias:**")
            cols = st.columns(2)
            materias_seleccionadas = []
            
            for i, materia in enumerate(ARCHIVOS.keys()):
                with cols[i % 2]:
                    if st.checkbox(materia, key=f"materia_{i}"):
                        materias_seleccionadas.append(materia)
            
            if st.form_submit_button("Registrarme"):
                if not nombre or not email:
                    st.warning("Por favor completa todos los campos obligatorios")
                elif not materias_seleccionadas:
                    st.warning("Selecciona al menos una materia")
                else:
                    if registrar_alumno(nombre, email, materias_seleccionadas):
                        st.success("✅ Registro exitoso!")
                        st.balloons()
    
    elif modo == "Profesor":
        st.header("📤 Envío de Material")
        
        materia = st.selectbox(
            "Selecciona una materia",
            list(ARCHIVOS.keys()),
            index=None,
            placeholder="Elige una materia..."
        )
        
        if materia:
            alumnos = obtener_alumnos(materia)
            
            if alumnos:
                st.subheader(f"Alumnos inscritos ({len(alumnos)})")
                
                with st.expander("Ver lista completa"):
                    for alumno in alumnos:
                        st.write(f"- {alumno['nombre']} ({alumno['email']})")
                
                st.divider()
                st.subheader("Enviar material")
                
                with st.form("form_envio"):
                    asunto = st.text_input("Asunto*")
                    mensaje = st.text_area("Mensaje*", height=150)
                    
                    st.markdown("**Enlaces importantes (opcional):**")
                    urls = []
                    for i in range(3):
                        url = st.text_input(f"URL {i+1}", key=f"url_{i}", placeholder="https://ejemplo.com")
                        if url:
                            urls.append(url)
                    
                    archivo_pdf = st.file_uploader(
                        f"Adjuntar PDF (opcional, máximo {CONFIG['MAX_FILE_SIZE_MB']}MB)", 
                        type="pdf"
                    )
                    
                    if st.form_submit_button("Enviar a todos"):
                        if not asunto or not mensaje:
                            st.warning("Completa los campos obligatorios")
                        else:
                            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
                                if archivo_pdf:
                                    tmp_file.write(archivo_pdf.getvalue())
                                    tmp_file_path = tmp_file.name
                                else:
                                    tmp_file_path = None
                            
                            enlaces_html = ""
                            if urls:
                                enlaces_html = "<h3>Enlaces importantes:</h3><ul>"
                                for url in urls:
                                    enlaces_html += f'<li><a href="{url}">{url}</a></li>'
                                enlaces_html += "</ul>"
                            
                            cuerpo = f"""
                            <html>
                                <body>
                                    <h2>{asunto}</h2>
                                    <div style="white-space: pre-line;">{mensaje}</div>
                                    {enlaces_html}
                                    <p>Saludos,<br>Profesor de {materia}</p>
                                </body>
                            </html>
                            """
                            
                            progreso = st.progress(0)
                            exitosos = 0
                            
                            for i, alumno in enumerate(alumnos):
                                if enviar_correo(alumno['email'], asunto, cuerpo, tmp_file_path):
                                    exitosos += 1
                                progreso.progress((i + 1) / len(alumnos))
                            
                            if tmp_file_path and os.path.exists(tmp_file_path):
                                os.unlink(tmp_file_path)
                            
                            st.success(f"📨 Enviados: {exitosos}/{len(alumnos)}")
                            if archivo_pdf:
                                st.info(f"PDF adjuntado: {archivo_pdf.name}")
                            if urls:
                                st.info(f"Enlaces incluidos: {len(urls)}")
            else:
                st.warning("No hay alumnos inscritos en esta materia")

if __name__ == "__main__":
    main()
