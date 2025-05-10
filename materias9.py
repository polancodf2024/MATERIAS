# -*- coding: utf-8 -*-
import streamlit as st
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from email.utils import formatdate
import paramiko
import time
import csv
from datetime import datetime
import ssl

# ====================
# CONFIGURACIÓN INICIAL
# ====================
class Config:
    def __init__(self):
        self.SMTP_SERVER = st.secrets["smtp_server"]
        self.SMTP_PORT = st.secrets["smtp_port"]
        self.EMAIL_USER = st.secrets["email_user"]
        self.EMAIL_PASSWORD = st.secrets["email_password"]
        self.NOTIFICATION_EMAIL = st.secrets["notification_email"]
        self.CSV_MATERIAS = st.secrets["csv_materias_file"]
        self.MAX_FILE_SIZE_MB = 10
        self.TIMEOUT_SECONDS = 30
        
        self.REMOTE = {
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
                'Análisis Multivariado y Multicategórico': st.secrets["remote_categorico"],
                'Manejo e Interpretación de Datos': st.secrets["remote_manejo"],
                'Análisis de Experimentos': st.secrets["remote_diseno"]
            }
        }

CONFIG = Config()

# ===================
# DATOS DE LAS MATERIAS
# ===================
TEMARIOS = {
    'Estadística no Paramétrica': {
        'contenido': [
            "1. PRUEBA DE SIGNO PARA LA MEDIANA",
            "2. PRUEBA PARA LA TENDENCIA",
            "3. PRUEBA DE ALEATORIEDAD",
            "4. PRUEBA DE IGUALDAD DE DISTRIBUCIONES",
            "5. PRUEBA DE RANGO (Mann-Whitney)",
            "6. PRUEBA DE KRUSKAL-WALLIS"
        ],
        'evaluacion': [
            "Examen final 100%",
            "Material en PDF proporcionado",
            "Videos semanales explicativos"
        ]
    },
    'Cálculo Diferencial e Integral III': {
        'contenido': [
            "1. GEOMETRÍA DEL ESPACIO EUCLIDIANO",
            "2. DIFERENCIACIÓN",
            "3. FUNCIONES VECTORIALES",
            "4. DERIVADAS DE ORDEN SUPERIOR"
        ],
        'evaluacion': [
            "4 exámenes parciales",
            "Reposiciones disponibles",
            "Libro de texto en PDF"
        ]
    },
    # [...] (Agregar todas las demás materias con la misma estructura)
}

# ==================
# FUNCIONES SSH/SFTP
# ==================
class SSHManager:
    @staticmethod
    def get_connection():
        """Establece conexión SSH segura"""
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            ssh.connect(
                hostname=CONFIG.REMOTE['HOST'],
                port=CONFIG.REMOTE['PORT'],
                username=CONFIG.REMOTE['USER'],
                password=CONFIG.REMOTE['PASSWORD'],
                timeout=CONFIG.TIMEOUT_SECONDS
            )
            return ssh
        except Exception as e:
            st.error(f"Error de conexión SSH: {str(e)}")
            return None

    @staticmethod
    def get_remote_file(remote_path):
        """Lee archivo remoto con manejo de errores"""
        ssh = SSHManager.get_connection()
        if not ssh:
            return None
        
        try:
            sftp = ssh.open_sftp()
            with sftp.file(remote_path, 'r') as f:
                content = f.read().decode('utf-8')
            return content
        except Exception as e:
            st.error(f"Error leyendo archivo remoto: {str(e)}")
            return None
        finally:
            ssh.close()

    @staticmethod
    def write_remote_file(remote_path, content):
        """Escribe en archivo remoto con manejo de errores"""
        ssh = SSHManager.get_connection()
        if not ssh:
            return False
        
        try:
            sftp = ssh.open_sftp()
            with sftp.file(remote_path, 'w') as f:
                f.write(content.encode('utf-8'))
            return True
        except Exception as e:
            st.error(f"Error escribiendo archivo remoto: {str(e)}")
            return False
        finally:
            ssh.close()

# ====================
# FUNCIONES PRINCIPALES
# ====================
def obtener_alumnos(materia):
    """Obtiene alumnos de una materia con validación robusta"""
    remote_path = os.path.join(CONFIG.REMOTE['DIR'], CONFIG.CSV_MATERIAS)
    csv_content = SSHManager.get_remote_file(remote_path)
    
    if not csv_content:
        return []

    alumnos = []
    lines = csv_content.splitlines()
    
    # Verificar encabezados
    headers = [h.strip().lower() for h in lines[0].split(',')]
    expected_headers = ['nombre', 'email', 'materias', 'fecha']
    
    if not all(h in headers for h in expected_headers):
        st.error("El archivo CSV no tiene el formato esperado")
        return []
    
    # Procesar cada registro
    for line in lines[1:]:
        if not line.strip():
            continue
            
        try:
            row = dict(zip(headers, [x.strip() for x in line.split(',')]))
            
            if materia.lower() in [m.strip().lower() for m in row['materias'].split(',')]:
                alumnos.append({
                    'nombre': row.get('nombre', ''),
                    'email': row.get('email', ''),
                    'fecha': row.get('fecha', 'N/A')
                })
        except Exception as e:
            st.warning(f"Error procesando línea: {line}. Error: {str(e)}")
            continue
            
    return alumnos

def registrar_alumno(nombre, email, materias):
    """Registra nuevo alumno con validación completa"""
    if not nombre or not email or not materias:
        st.error("Datos incompletos para el registro")
        return False
    
    remote_path = os.path.join(CONFIG.REMOTE['DIR'], CONFIG.CSV_MATERIAS)
    csv_content = SSHManager.get_remote_file(remote_path) or "nombre,email,materias,fecha\n"
    
    # Verificar si el alumno ya existe
    if email.lower() in [line.split(',')[1].strip().lower() for line in csv_content.splitlines()[1:] if len(line.split(',')) > 1]:
        st.warning("Este correo electrónico ya está registrado")
        return False
    
    # Añadir nuevo registro
    nuevo_registro = f"{nombre},{email},{','.join(materias)},{datetime.now()}\n"
    
    if not SSHManager.write_remote_file(remote_path, csv_content + nuevo_registro):
        return False
    
    # Registrar en archivos específicos de materias
    for materia in materias:
        materia_file = CONFIG.REMOTE['FILES'].get(materia)
        if materia_file:
            materia_path = os.path.join(CONFIG.REMOTE['DIR'], materia_file)
            registro = f"{nombre},{email},{datetime.now()}\n"
            current_content = SSHManager.get_remote_file(materia_path) or ""
            SSHManager.write_remote_file(materia_path, current_content + registro)
    
    return True

def enviar_correo(destinatario, asunto, mensaje, adjunto=None):
    """Envía correo electrónico con manejo robusto"""
    if not destinatario or not asunto or not mensaje:
        st.error("Faltan datos requeridos para enviar el correo")
        return False
    
    try:
        msg = MIMEMultipart()
        msg['From'] = CONFIG.EMAIL_USER
        msg['To'] = destinatario
        msg['Subject'] = asunto
        msg.attach(MIMEText(mensaje, 'plain'))
        
        if adjunto:
            if adjunto.size > CONFIG.MAX_FILE_SIZE_MB * 1024 * 1024:
                st.error(f"El archivo excede el tamaño máximo de {CONFIG.MAX_FILE_SIZE_MB}MB")
                return False
                
            part = MIMEBase('application', 'octet-stream')
            part.set_payload(adjunto.read())
            encoders.encode_base64(part)
            part.add_header('Content-Disposition', f'attachment; filename="{adjunto.name}"')
            msg.attach(part)
        
        context = ssl.create_default_context()
        
        with smtplib.SMTP(CONFIG.SMTP_SERVER, CONFIG.SMTP_PORT) as server:
            server.starttls(context=context)
            server.login(CONFIG.EMAIL_USER, CONFIG.EMAIL_PASSWORD)
            server.send_message(msg)
        
        return True
    except Exception as e:
        st.error(f"Error enviando correo: {str(e)}")
        return False

# =============
# INTERFAZ GUI
# =============
def mostrar_temario(materia):
    """Muestra el temario de una materia con formato"""
    if materia not in TEMARIOS:
        st.warning("Temario no disponible para esta materia")
        return
    
    st.subheader(f"Temario de {materia}")
    
    with st.expander("Contenido del curso", expanded=True):
        for item in TEMARIOS[materia]['contenido']:
            st.write(f"- {item}")
    
    with st.expander("Sistema de evaluación", expanded=False):
        for item in TEMARIOS[materia]['evaluacion']:
            st.write(f"- {item}")

def modo_estudiante():
    """Interfaz para el modo estudiante"""
    st.header("Registro de Estudiantes")
    
    with st.form("form_registro", border=True):
        nombre = st.text_input("Nombre completo*", placeholder="Ej. María González López")
        email = st.text_input("Correo electrónico*", placeholder="tu@correo.unam.mx")
        
        st.markdown("**Selecciona tus materias:**")
        cols = st.columns(2)
        materias_seleccionadas = []
        
        for i, materia in enumerate(CONFIG.REMOTE['FILES'].keys()):
            with cols[i % 2]:
                if st.checkbox(materia, key=f"mat_{i}"):
                    materias_seleccionadas.append(materia)
        
        if st.form_submit_button("Registrarme", type="primary"):
            if not nombre or not email:
                st.error("Por favor completa todos los campos obligatorios")
            elif not materias_seleccionadas:
                st.error("Debes seleccionar al menos una materia")
            else:
                if registrar_alumno(nombre, email, materias_seleccionadas):
                    mensaje = f"""
                    Hola {nombre},
                    
                    Tu registro en las siguientes materias ha sido exitoso:
                    {', '.join(materias_seleccionadas)}
                    
                    Recibirás material y notificaciones en este correo.
                    
                    Saludos,
                    Departamento Académico
                    """
                    if enviar_correo(email, "Confirmación de registro", mensaje):
                        st.success("¡Registro exitoso! Se ha enviado un correo de confirmación")
                        st.balloons()

    st.markdown("---")
    st.header("Información de Materias")
    
    materia_seleccionada = st.selectbox(
        "Selecciona una materia para ver su temario",
        options=list(CONFIG.REMOTE['FILES'].keys()),
        index=0
    )
    
    mostrar_temario(materia_seleccionada)

def modo_profesor():
    """Interfaz para el modo profesor"""
    st.header("Acceso Docente")
    
    # Autenticación
    if 'profesor_autenticado' not in st.session_state:
        st.session_state.profesor_autenticado = False
    
    if not st.session_state.profesor_autenticado:
        password = st.text_input("Contraseña de acceso", type="password")
        
        if st.button("Ingresar"):
            if password == CONFIG.REMOTE['PASSWORD']:
                st.session_state.profesor_autenticado = True
                st.rerun()
            else:
                st.error("Contraseña incorrecta")
        return
    
    st.success("Acceso autorizado")
    
    # Verificar conexión remota
    with st.expander("Estado del sistema", expanded=False):
        with st.spinner("Verificando conexión con servidor..."):
            ssh = SSHManager.get_connection()
            if ssh:
                st.success("Conexión SSH establecida correctamente")
                ssh.close()
            else:
                st.error("No se pudo conectar al servidor remoto")
                return
    
    st.header("Gestión Académica")
    
    # Selección de materia
    materia = st.selectbox(
        "Selecciona una materia",
        options=list(CONFIG.REMOTE['FILES'].keys()),
        index=0
    )
    
    # Obtener alumnos
    alumnos = obtener_alumnos(materia)
    
    if not alumnos:
        st.warning("No hay alumnos inscritos en esta materia")
        return
    
    st.subheader(f"Alumnos inscritos: {len(alumnos)}")
    
    with st.expander("Ver lista completa", expanded=False):
        for alumno in alumnos:
            st.write(f"- **{alumno['nombre']}** ({alumno['email']}) - {alumno['fecha']}")
    
    # Envío de material
    st.markdown("---")
    st.subheader("Enviar material académico")
    
    with st.form("form_envio_material", border=True):
        asunto = st.text_input("Asunto*", placeholder="Ej: Material para el parcial 1")
        mensaje = st.text_area("Mensaje*", height=150, 
                             placeholder="Escribe aquí el contenido del mensaje...")
        
        st.markdown("**Enlaces adicionales (opcional):**")
        enlaces = []
        for i in range(3):
            url = st.text_input(f"Enlace {i+1}", key=f"url_{i}", 
                              placeholder="https://ejemplo.com/recurso")
            if url:
                enlaces.append(url)
        
        archivo = st.file_uploader(
            f"Adjuntar archivo (PDF/ZIP, máx. {CONFIG.MAX_FILE_SIZE_MB}MB)",
            type=['pdf', 'zip'],
            accept_multiple_files=False
        )
        
        if st.form_submit_button("Enviar a todos los alumnos", type="primary"):
            if not asunto or not mensaje:
                st.error("Completa los campos obligatorios")
            else:
                # Construir mensaje completo
                mensaje_completo = f"{mensaje}\n\n"
                
                if enlaces:
                    mensaje_completo += "**Recursos adicionales:**\n"
                    for i, url in enumerate(enlaces, 1):
                        mensaje_completo += f"{i}. {url}\n"
                
                # Progreso del envío
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                for i, alumno in enumerate(alumnos):
                    status_text.text(f"Enviando a {alumno['nombre']} ({i+1}/{len(alumnos)})...")
                    
                    # Reiniciar el puntero del archivo para cada envío
                    if archivo:
                        archivo.seek(0)
                    
                    enviar_correo(
                        alumno['email'],
                        asunto,
                        f"Estimado(a) {alumno['nombre']}:\n\n{mensaje_completo}",
                        archivo
                    )
                    
                    progress_bar.progress((i + 1) / len(alumnos))
                    time.sleep(0.5)  # Pausa para evitar bloqueos
                
                status_text.success("¡Material enviado con éxito!")
                st.balloons()

# =============
# APLICACIÓN
# =============
def main():
    st.set_page_config(
        page_title="Sistema Académico UNAM",
        page_icon="🎓",
        layout="centered",
        initial_sidebar_state="expanded"
    )
    
    # Logo y barra lateral
    st.sidebar.image("unam.svg", width=150)
    st.sidebar.title("Menú Principal")
    
    modo = st.sidebar.radio(
        "Modo de operación",
        ["👨‍🎓 Estudiante", "👨‍🏫 Profesor"],
        index=0
    )
    
    st.title("Sistema de Gestión Académica")
    
    if "Estudiante" in modo:
        modo_estudiante()
    else:
        modo_profesor()

if __name__ == "__main__":
    main()
