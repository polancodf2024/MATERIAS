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
import re

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
                'Análisis de Experimentos': st.secrets["remote_diseno"],
                'Inteligencia Artificial en Enfermería': st.secrets["remote_inteligencia_enfermeria"],
                'Inteligencia Artificial en Investigación': st.secrets["remote_inteligencia_investigacion"]
            }
        }

CONFIG = Config()

# ===================
# FUNCIONES DE VALIDACIÓN
# ===================
def validate_email(email):
    """Valida el formato de un email"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def clean_name(name):
    """Limpia y formatea nombres"""
    if not name:
        return name
    # Elimina caracteres extraños pero conserva acentos y ñ
    name = re.sub(r'[^a-zA-ZáéíóúÁÉÍÓÚñÑ\s]', '', name.strip())
    # Formato título (primera letra mayúscula)
    return ' '.join(word.capitalize() for word in name.split())

# ===================
# DATOS DE LAS MATERIAS
# ===================
TEMARIOS = {
    'Cálculo Diferencial e Integral III': {
        'contenido': [
            'Temario pendiente de subir por el departamento académico'
        ],
        'evaluacion': [
            'Sistema de evaluación pendiente de definir'
        ]
    },
    'Cálculo Diferencial e Integral IV': {
        'contenido': [
            'Temario pendiente de subir por el departamento académico'
        ],
        'evaluacion': [
            'Sistema de evaluación pendiente de definir'
        ]
    },
    'Estadística no Paramétrica': {
        'contenido': [
            'Temario pendiente de subir por el departamento académico'
        ],
        'evaluacion': [
            'Sistema de evaluación pendiente de definir'
        ]
    },
    'Bioestadística I': {
        'contenido': [
            'Temario pendiente de subir por el departamento académico'
        ],
        'evaluacion': [
            'Sistema de evaluación pendiente de definir'
        ]
    },
    'Bioestadística II': {
        'contenido': [
            'Temario pendiente de subir por el departamento académico'
        ],
        'evaluacion': [
            'Sistema de evaluación pendiente de definir'
        ]
    },
    'Análisis Multivariado y Multicategórico': {
        'contenido': [
            'Temario pendiente de subir por el departamento académico'
        ],
        'evaluacion': [
            'Sistema de evaluación pendiente de definir'
        ]
    },
    'Manejo e Interpretación de Datos': {
        'contenido': [
            'Temario pendiente de subir por el departamento académico'
        ],
        'evaluacion': [
            'Sistema de evaluación pendiente de definir'
        ]
    },
    'Análisis de Experimentos': {
        'contenido': [
            'Temario pendiente de subir por el departamento académico'
        ],
        'evaluacion': [
            'Sistema de evaluación pendiente de definir'
        ]
    },
        'Inteligencia Artificial en Enfermería': {
        'contenido': [
            'Temario pendiente de subir por el departamento académico'
        ],
        'evaluacion': [
            'Sistema de evaluación pendiente de definir'
        ]
    },
    'Inteligencia Artificial en Investigación': {
        'contenido': [
            'Temario pendiente de subir por el departamento académico'
        ],
        'evaluacion': [
            'Sistema de evaluación pendiente de definir'
        ]
    }
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

    @staticmethod
    def append_to_remote_file(remote_path, content):
        """Añade contenido a un archivo remoto existente"""
        ssh = SSHManager.get_connection()
        if not ssh:
            return False
        
        try:
            sftp = ssh.open_sftp()
            # Leer contenido existente
            try:
                existing_content = sftp.file(remote_path, 'r').read().decode('utf-8')
            except:
                existing_content = ""
            
            # Escribir contenido completo
            with sftp.file(remote_path, 'w') as f:
                f.write((existing_content + content).encode('utf-8'))
            return True
        except Exception as e:
            st.error(f"Error añadiendo a archivo remoto: {str(e)}")
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
    expected_headers = ['fecha', 'nombre', 'email', 'materias']
    
    if not all(h in headers for h in expected_headers):
        st.error("El archivo CSV no tiene el formato esperado. Se creará uno nuevo.")
        # Crear nuevo archivo con formato correcto
        new_content = "fecha,nombre,email,materias\n"
        SSHManager.write_remote_file(remote_path, new_content)
        return []
    
    # Procesar cada registro
    for line in lines[1:]:
        if not line.strip():
            continue
            
        try:
            # Manejar formato inconsistente
            parts = [p.strip() for p in line.split(',')]
            if len(parts) < 4:
                continue
                
            fecha = parts[0]
            nombre = clean_name(parts[1])
            email = parts[2].lower()
            materias = [m.strip() for m in parts[3:] if m.strip()]
            
            if not validate_email(email):
                continue
                
            if materia in materias:
                alumnos.append({
                    'nombre': nombre,
                    'email': email,
                    'fecha': fecha
                })
        except Exception as e:
            st.warning(f"Error procesando línea: {line}. Error: {str(e)}")
            continue
            
    return alumnos

def registrar_alumno(nombre, email, materias):
    """Registra nuevo alumno con validación completa"""
    # Validar entradas
    nombre = clean_name(nombre)
    email = email.strip().lower()
    
    if not nombre or len(nombre.split()) < 2:
        st.error("Por favor ingresa tu nombre completo")
        return False
        
    if not validate_email(email):
        st.error("Por favor ingresa un correo electrónico válido")
        return False
        
    if not materias:
        st.error("Debes seleccionar al menos una materia")
        return False

    remote_path = os.path.join(CONFIG.REMOTE['DIR'], CONFIG.CSV_MATERIAS)
    csv_content = SSHManager.get_remote_file(remote_path)

    # Si el archivo no existe o está mal formado, crear uno nuevo
    if not csv_content or not csv_content.startswith("fecha,nombre,email,materias"):
        csv_content = "fecha,nombre,email,materias\n"
    else:
        if not csv_content.endswith('\n'):
            csv_content += '\n'

    # Verificar si el alumno ya existe
    lines = csv_content.splitlines()
    if any(email == line.split(',')[2].strip().lower() for line in lines[1:] if len(line.split(',')) > 2):
        st.warning("Este correo electrónico ya está registrado")
        return False

    # Crear nuevo registro con formato consistente
    nuevo_registro = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')},{nombre},{email},{','.join(materias)}\n"

    # Escribir el archivo principal
    if not SSHManager.write_remote_file(remote_path, csv_content + nuevo_registro):
        return False

    # Registrar en archivos específicos de materias
    for materia in materias:
        materia_file = CONFIG.REMOTE['FILES'].get(materia)
        if materia_file:
            materia_path = os.path.join(CONFIG.REMOTE['DIR'], materia_file)
            current_content = SSHManager.get_remote_file(materia_path) or ""
            
            # Normalizar archivo de materia si es necesario
            if not current_content.startswith("fecha,nombre,email"):
                current_content = "fecha,nombre,email\n"
            elif not current_content.endswith('\n'):
                current_content += '\n'
                
            # Verificar si el alumno ya está en este archivo específico
            if email not in current_content:
                registro = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')},{nombre},{email}\n"
                if not SSHManager.write_remote_file(materia_path, current_content + registro):
                    st.warning(f"No se pudo actualizar el archivo para {materia}")
            else:
                st.info(f"El alumno ya estaba registrado en {materia}")

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
        st.warning("Información no disponible para esta materia")
        return

    st.subheader(f"Información de {materia}")

    with st.expander("📚 Contenido del curso", expanded=True):
        st.info("⏳ Temario pendiente de subir por el departamento académico")
        for item in TEMARIOS[materia]['contenido']:
            st.write(f"• {item}")

    with st.expander("📊 Sistema de evaluación", expanded=False):
        st.warning("⏳ Sistema de evaluación pendiente de definir")
        for item in TEMARIOS[materia]['evaluacion']:
            st.write(f"• {item}")

    st.info("""
    **Nota:** La información completa del curso (temario detallado y sistema de evaluación) 
    será proporcionada por el departamento académico antes del inicio de clases.
    """)

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
                    Carlos Polanco
                    """
                    if enviar_correo(email, "Confirmación de registro", mensaje):
                        st.success("¡Registro exitoso! Se ha enviado un correo de confirmación")
                        st.balloons()
                        st.snow()

    st.markdown("---")
    st.header("Información de Materias")

    materia_seleccionada = st.selectbox(
        "Selecciona una materia para ver su información",
        options=list(CONFIG.REMOTE['FILES'].keys()),
        index=0
    )

    mostrar_temario(materia_seleccionada)

def modo_profesor():
    """Interfaz para el modo profesor con visualización limpia de alumnos"""
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

    # Obtener alumnos (limpia la caché de streamlit para esta consulta)
    @st.cache_data(ttl=10)  # Cache por 10 segundos para evitar múltiples lecturas
    def _obtener_alumnos(materia):
        return obtener_alumnos(materia)

    alumnos = _obtener_alumnos(materia)

    if not alumnos:
        st.warning("No hay alumnos inscritos en esta materia")
        return

    # Mostrar alumnos (usando un contenedor que se limpia automáticamente)
    with st.container():
        st.subheader(f"Alumnos inscritos: {len(alumnos)}")

        # Usar un expander que se reinicia cada vez
        with st.expander("Ver lista completa", expanded=False):
            # Limpiar cualquier contenido previo
            st.empty()

            # Mostrar la lista actualizada
            for alumno in alumnos:
                st.write(f"- **{alumno['nombre']}** ({alumno['email']}) - {alumno['fecha']}")

    # Envío de material
    st.markdown("---")
    st.subheader("Envío de material académico")

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
            accept_multiple_files=False,
            key="file_uploader"  # Key única para este uploader
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
                success_count = 0
                total_alumnos = len(alumnos)

                # Envío en grupos con pausas para evitar bloqueos de Gmail
                grupo_size = 5  # Enviar 5 correos por lote
                pausa_entre_grupos = 10  # 10 segundos entre lotes
                pausa_entre_correos = 2  # 2 segundos entre correos individuales

                for i, alumno in enumerate(alumnos):
                    status_text.text(f"Enviando a {alumno['nombre']} ({i+1}/{total_alumnos})...")

                    # Reiniciar el puntero del archivo para cada envío
                    if archivo:
                        archivo.seek(0)

                    if enviar_correo(
                        alumno['email'],
                        asunto,
                        f"Estimado(a) {alumno['nombre']}:\n\n{mensaje_completo}",
                        archivo
                    ):
                        success_count += 1

                    progress_bar.progress((i + 1) / total_alumnos)
                    
                    # Pausa entre correos individuales
                    time.sleep(pausa_entre_correos)
                    
                    # Pausa más larga entre grupos
                    if (i + 1) % grupo_size == 0 and (i + 1) < total_alumnos:
                        status_text.text(f"Pausa de {pausa_entre_grupos} segundos para evitar bloqueos...")
                        time.sleep(pausa_entre_grupos)

                if success_count == total_alumnos:
                    status_text.success(f"¡Material enviado con éxito a todos los {success_count} alumnos!")
                else:
                    status_text.warning(f"Se enviaron {success_count} de {total_alumnos} correos. Algunos pueden no haberse enviado correctamente.")
                
                st.balloons()
                st.snow()

                # Esperar unos segundos para que se vean las animaciones
                time.sleep(3)

                # Forzar limpieza del formulario después del envío
                st.rerun()


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
