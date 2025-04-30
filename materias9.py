import streamlit as st
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from datetime import datetime
import ssl
from email.utils import formatdate
import tempfile
import paramiko
import csv
import io

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
        'REMOTE_PASSWORD': st.secrets["remote_password"],
        'TIMEOUT_SECONDS': st.secrets.get("timeout_seconds", 30),
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

def get_sftp_connection():
    """Establece y devuelve una conexión SFTP segura"""
    try:
        transport = paramiko.Transport((CONFIG['REMOTE']['HOST'], CONFIG['REMOTE']['PORT']))
        transport.default_window_size = 2147483647
        transport.banner_timeout = CONFIG['TIMEOUT_SECONDS']
        transport.connect(username=CONFIG['REMOTE']['USER'], password=CONFIG['REMOTE']['PASSWORD'])
        return paramiko.SFTPClient.from_transport(transport)
    except Exception as e:
        st.error(f"🚨 Error de conexión SFTP: {str(e)}")
        return None

def obtener_alumnos(materia):
    """Obtiene la lista de alumnos directamente del servidor remoto"""
    sftp = get_sftp_connection()
    if not sftp:
        return []
    
    try:
        remote_file = os.path.join(CONFIG['REMOTE']['DIR'], CONFIG['REMOTE']['FILES'][materia])
        
        # Leer archivo remoto
        with sftp.file(remote_file, 'r') as f:
            contenido = f.read().decode('utf-8')
        
        lineas = contenido.split('\n')[2:]  # Saltar encabezado
        alumnos = []
        
        for linea in lineas:
            if linea.strip():
                partes = [p.strip() for p in linea.split('|')]
                if len(partes) >= 3:
                    alumnos.append({
                        'fecha': partes[0],
                        'nombre': partes[1],
                        'email': partes[2]
                    })
        return alumnos
        
    except FileNotFoundError:
        st.warning(f"⚠️ Archivo no encontrado en servidor: {materia}")
        return []
    except Exception as e:
        st.error(f"❌ Error al leer archivo remoto: {str(e)}")
        return []
    finally:
        sftp.close()

def registrar_alumno(nombre, email, materias):
    """Registra un alumno directamente en el servidor remoto"""
    sftp = get_sftp_connection()
    if not sftp:
        return False
    
    try:
        fecha = datetime.now().strftime('%Y-%m-%d %H:%M')
        registro_csv = []
        
        for materia in materias:
            remote_file = os.path.join(CONFIG['REMOTE']['DIR'], CONFIG['REMOTE']['FILES'][materia])
            
            # Leer o inicializar archivo
            try:
                with sftp.file(remote_file, 'r') as f:
                    contenido = f.read().decode('utf-8')
            except FileNotFoundError:
                contenido = f"Alumnos inscritos en {materia}\n\n"
            
            # Añadir nuevo registro
            nuevo_registro = f"{fecha} | {nombre} | {email}\n"
            nuevo_contenido = contenido + nuevo_registro
            
            # Escribir de vuelta al servidor
            with sftp.file(remote_file, 'w') as f:
                f.write(nuevo_contenido.encode('utf-8'))
            
            registro_csv.append(materia)
        
        # Registrar en CSV remoto
        remote_csv = os.path.join(CONFIG['REMOTE']['DIR'], CONFIG['CSV_MATERIAS'])
        try:
            with sftp.file(remote_csv, 'r') as f:
                contenido_csv = f.read().decode('utf-8')
        except FileNotFoundError:
            contenido_csv = "Fecha,Nombre,Email,Materias\n"
        
        nuevo_csv = contenido_csv + f"{fecha},{nombre},{email},{', '.join(registro_csv)}\n"
        with sftp.file(remote_csv, 'w') as f:
            f.write(nuevo_csv.encode('utf-8'))
        
        # Notificar por correo
        enviar_notificacion(nombre, email, materias, fecha)
        
        return True
        
    except Exception as e:
        st.error(f"❌ Error al registrar: {str(e)}")
        return False
    finally:
        sftp.close()

def enviar_notificacion(nombre, email, materias, fecha):
    """Envía notificación por correo electrónico"""
    try:
        asunto = f"📝 Nuevo registro: {nombre}"
        cuerpo = f"""
        <html>
            <body style="font-family: Arial, sans-serif;">
                <h2 style="color: #2e6c80;">Nuevo registro en el sistema académico</h2>
                <table style="border-collapse: collapse; width: 100%;">
                    <tr style="background-color: #f2f2f2;">
                        <td style="padding: 8px; border: 1px solid #ddd; width: 30%;"><strong>Nombre:</strong></td>
                        <td style="padding: 8px; border: 1px solid #ddd;">{nombre}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px; border: 1px solid #ddd;"><strong>Email:</strong></td>
                        <td style="padding: 8px; border: 1px solid #ddd;">{email}</td>
                    </tr>
                    <tr style="background-color: #f2f2f2;">
                        <td style="padding: 8px; border: 1px solid #ddd;"><strong>Materias:</strong></td>
                        <td style="padding: 8px; border: 1px solid #ddd;">{', '.join(materias)}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px; border: 1px solid #ddd;"><strong>Fecha:</strong></td>
                        <td style="padding: 8px; border: 1px solid #ddd;">{fecha}</td>
                    </tr>
                </table>
            </body>
        </html>
        """
        
        enviar_correo(CONFIG['NOTIFICATION_EMAIL'], asunto, cuerpo)
        
    except Exception as e:
        st.error(f"⚠️ Error al enviar notificación: {str(e)}")

def enviar_correo(destinatario, asunto, cuerpo, archivo_adjunto=None):
    """Envía correos electrónicos con manejo robusto de errores"""
    try:
        if archivo_adjunto and os.path.getsize(archivo_adjunto) > CONFIG['MAX_FILE_SIZE_MB'] * 1024 * 1024:
            st.error(f"📦 El archivo excede el tamaño máximo de {CONFIG['MAX_FILE_SIZE_MB']}MB")
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
        st.error("🔒 Error de autenticación. Verifica usuario y contraseña SMTP.")
    except Exception as e:
        st.error(f"❌ Error al enviar correo: {str(e)}")
    return False

def enviar_material(materia, asunto, mensaje, urls=None, archivo_pdf=None):
    """Envía material a todos los alumnos de una materia"""
    alumnos = obtener_alumnos(materia)
    if not alumnos:
        st.warning("No hay alumnos inscritos en esta materia")
        return
    
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
            if archivo_pdf:
                tmp_file.write(archivo_pdf.getvalue())
                tmp_file_path = tmp_file.name
            else:
                tmp_file_path = None
            
            enlaces_html = ""
            if urls:
                enlaces_html = "<h3>📌 Enlaces importantes:</h3><ul>"
                for url in urls:
                    enlaces_html += f'<li><a href="{url}">{url}</a></li>'
                enlaces_html += "</ul>"
            
            cuerpo = f"""
            <html>
                <body style="font-family: Arial, sans-serif;">
                    <h2 style="color: #2e6c80;">{asunto}</h2>
                    <div style="white-space: pre-line; margin-bottom: 20px;">{mensaje}</div>
                    {enlaces_html}
                    <p style="margin-top: 30px;">Saludos,<br>Profesor de {materia}</p>
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
            
            st.success(f"✉️ Enviados: {exitosos}/{len(alumnos)}")
            if archivo_pdf:
                st.info(f"📄 PDF adjuntado: {archivo_pdf.name}")
            if urls:
                st.info(f"🔗 Enlaces incluidos: {len(urls)}")
    
    except Exception as e:
        st.error(f"❌ Error al enviar material: {str(e)}")

def main():
    st.set_page_config(
        page_title="Sistema Académico",
        page_icon="🎓",
        layout="centered"
    )
    
    # Mostrar logo UNAM en la barra lateral
    st.sidebar.image("unam.svg", width=150)
    
    st.title("🎓 Sistema de Inscripción Académica")
    
    modo = st.sidebar.radio(
        "Modo de operación",
        ["Estudiante", "Profesor"],
        horizontal=True,
        index=0
    )
    
    if modo == "Estudiante":
        st.header("📝 Registro de Estudiante")
        
        with st.form("form_registro", border=True):
            nombre = st.text_input("Nombre completo*", placeholder="Ej: Juan Pérez")
            email = st.text_input("Correo electrónico*", placeholder="Ej: juan@ejemplo.com")
            
            st.markdown("**Selecciona tus materias:**")
            cols = st.columns(2)
            materias_seleccionadas = []
            
            for i, materia in enumerate(CONFIG['REMOTE']['FILES'].keys()):
                with cols[i % 2]:
                    if st.checkbox(materia, key=f"materia_{i}"):
                        materias_seleccionadas.append(materia)
            
            if st.form_submit_button("Registrarme", type="primary"):
                if not nombre or not email:
                    st.warning("⚠️ Por favor completa todos los campos obligatorios")
                elif not materias_seleccionadas:
                    st.warning("⚠️ Selecciona al menos una materia")
                elif registrar_alumno(nombre, email, materias_seleccionadas):
                    st.success("✅ Registro exitoso!")
                    st.balloons()
    
    elif modo == "Profesor":
        st.header("🔒 Acceso de Profesor")
        
        # Verificación de contraseña
        password = st.text_input("Contraseña de acceso", type="password")
        
        if password == CONFIG['REMOTE_PASSWORD']:
            st.session_state.profesor_autenticado = True
        
        if st.session_state.get('profesor_autenticado', False):
            st.header("📤 Envío de Material")
            
            materia = st.selectbox(
                "Selecciona una materia",
                list(CONFIG['REMOTE']['FILES'].keys()),
                index=None,
                placeholder="Elige una materia..."
            )
            
            if materia:
                alumnos = obtener_alumnos(materia)
                
                if alumnos:
                    st.subheader(f"👥 Alumnos inscritos ({len(alumnos)})")
                    
                    with st.expander("Ver lista completa", expanded=False):
                        for alumno in alumnos:
                            st.write(f"- **{alumno['nombre']}** ({alumno['email']}) - Registrado el {alumno['fecha']}")
                    
                    st.divider()
                    st.subheader("📨 Enviar material")
                    
                    with st.form("form_envio", border=True):
                        asunto = st.text_input("Asunto*", placeholder="Ej: Material para la próxima clase")
                        mensaje = st.text_area("Mensaje*", height=150, placeholder="Escribe aquí el contenido del mensaje...")
                        
                        st.markdown("**🔗 Enlaces importantes (opcional):**")
                        urls = []
                        for i in range(3):
                            url = st.text_input(f"URL {i+1}", key=f"url_{i}", placeholder="https://ejemplo.com")
                            if url:
                                urls.append(url)
                        
                        archivo_pdf = st.file_uploader(
                            f"📄 Adjuntar PDF (opcional, máximo {CONFIG['MAX_FILE_SIZE_MB']}MB)", 
                            type="pdf"
                        )
                        
                        if st.form_submit_button("Enviar a todos", type="primary"):
                            if not asunto or not mensaje:
                                st.warning("⚠️ Completa los campos obligatorios")
                            else:
                                enviar_material(materia, asunto, mensaje, urls, archivo_pdf)
                else:
                    st.warning("ℹ️ No hay alumnos inscritos en esta materia")
        elif password and password != CONFIG['REMOTE_PASSWORD']:
            st.error("❌ Contraseña incorrecta. Inténtalo de nuevo.")

if __name__ == "__main__":
    main()
