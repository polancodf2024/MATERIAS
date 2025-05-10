# -*- coding: utf-8 -*-
import streamlit as st
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from email.utils import formatdate
import tempfile
import paramiko
import time
import socket
from html import unescape
import re
from datetime import datetime
import ssl
import csv

# Función para eliminar etiquetas HTML
def strip_tags(html):
    """Elimina etiquetas HTML de un string"""
    text = unescape(html)
    clean = re.compile('<.*?>')
    return re.sub(clean, '', text)

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
        'MAX_RETRIES': st.secrets.get("max_retries", 3),
        'RETRY_DELAY': st.secrets.get("retry_delay", 5),
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
                'Análisis Multivariado y Multicategórico': st.secrets["remote_categorico"],
                'Manejo e Interpretación de Datos': st.secrets["remote_manejo"],
                'Análisis de Experimentos': st.secrets["remote_diseno"]
            }
        }
    }

# Diccionario de temarios por materia
TEMARIOS = {
    'Estadística no Paramétrica': """
    **Contenido del curso:**
    
    1. PRUEBA DE SIGNO PARA LA MEDIANA.
    - Test de signos
    
    2. PRUEBA PARA LA TENDENCIA.
    
    3. PRUEBA DE ALEATORIEDAD EN MUESTRAS.
    
    4. PRUEBA DE IGUALDAD DE FUNCIONES DE DISTRIBUCION.
    
    5. PRUEBA DE RANGO.
    - U-test de Mann-Whitney
    
    6. PRUEBA DEL RANGO PARA DOS MUESTRAS.
    - H-test de Kruskal-Wallis
    
    **Condiciones del curso:**
    - Evaluación: Calificación máxima al final, sin exámenes ni tareas.
    - Material: Libro de texto en PDF proporcionado por el profesor.
    - Clases: Video semanal con explicación del tema.
    - Enfoque: El curso requiere un rol autodidacta del alumno.    
    """,
    'Cálculo Diferencial e Integral III': """
    **Contenido del curso:**

    1. GEOMETRÍA DEL ESPACIO EUCLIDIANO.

    2. DIFERENCIACIÓN.

    3. FUNCIONES CON VALORES VECTORIALES

    4. DERIVADAS DE ORDEN SUPERIOR.

    **Condiciones del curso:**
    - Se aplican cuatro evaluaciones, y existe reposición para todas ellas.
    - El PDF del libro de texto lo proporciona el profesor.
    """,
    'Cálculo Diferencial e Integral IV': """
    **Contenido del curso:**

    1. INTEGRALES DOBLES Y TRIPLES (SIN MAPEOS).

    2. INTEGRALES DOBLES Y TRIPLES (CON MAPEOS).

    3. INTEGRAL DE LINEA Y DE SUPERFICIE.

    4. TEOREMA DE GREEN, STOKES Y GAUSS.

    **Condiciones del curso:**
    - Se aplican cuatro evaluaciones, y existe reposición para todas ellas.
    - El PDF del libro de texto lo proporciona el profesor.    
    """,
    'Bioestadística I': """
    **Contenido del curso:**

    1. ESTADÍSTICA DESCRIPTIVA EN CIENCIAS DE LA SALUD.

    2. PROBABILIDAD EN DIAGNÓSTICO CLÍNICO.

    3. INFERENCIA BÁSICA.

    4. REGRESIÓN LINEAL EN INVESTIGACIÓN CLÍNICA.
 
    **Condiciones del curso:**
    - Evaluación: Calificación máxima al final, sin exámenes ni tareas.
    - Material: Libro de texto en PDF proporcionado por el profesor.
    - Clases: Video semanal con explicación del tema.
    - Enfoque: El curso requiere un rol autodidacta del alumno.    
    """,
    'Bioestadística II': """
    **Contenido del curso:**

    1. MODELOS LINEALES GENERALIZADOS (GLM).

    2. ANÁLISIS DE SUPERVIVENCIA.

    3. DISEÑO DE ESTUDIOS.

    4. BIOESTADÍSTICA MULTIVARIANTE.
 
    **Condiciones del curso:**
    - Evaluación: Calificación máxima al final, sin exámenes ni tareas.
    - Material: Libro de texto en PDF proporcionado por el profesor.
    - Clases: Video semanal con explicación del tema.
    - Enfoque: El curso requiere un rol autodidacta del alumno.    
    """,
    'Análisis Multivariado y Multicategórico': """
    **Contenido del curso:**

    1. DIAGONALIZACIÓN (SVD).

    2. NORMAL MULTIVARIADA.

    3. CONTRASTE MEDIAS-COVARIANZAS.

    4. CORRELACIÓN CANÓNICA.

    5. REGRESIÓN MULTIVARIADA.

    6. DISCRIMINACIÓN (MINIMAX/FISHER).

    7. COMPONENTES PRINCIPALES.

    8. TABLAS DE CONTINGENCIA.

    **Condiciones del curso:**
    - Evaluación: Calificación máxima al final, sin exámenes ni tareas.
    - Material: Libro de texto en PDF proporcionado por el profesor.
    - Clases: Video semanal con explicación del tema.
    - Enfoque: El curso requiere un rol autodidacta del alumno.    
    """,
    'Manejo e Interpretación de Datos': """
    **Contenido del curso:**

    1. FUNDAMENTOS DE DATOS EN SALUD.

    2. HERRAMIENTAS COMPUTACIONALES.

    3. PROCESAMIENTO DE DATOS.

    4. ANÁLISIS EXPLORATORIO.

    5. INTERPRETACIÓN DE RESULTADOS.

    **Condiciones del curso:**
    - Evaluación: Calificación máxima al final, sin exámenes ni tareas.
    - Material: Libro de texto en PDF proporcionado por el profesor.
    - Clases: Video semanal con explicación del tema.
    - Enfoque: El curso requiere un rol autodidacta del alumno.    
    """,
    'Análisis de Experimentos': """
    **Contenido del curso:**

    1. EXPERIMENTOS DE COMPARACIÓN SIMPLE.

    2. BLOQUES ALEATORIZADOS, CUADRADOS LATINOS 
       Y DISEÑOS RELACIONADOS.

    3. DISEÑOS FACTORIALES.

    4. MÉTODOS Y DISEÑOS DE SUPERFICIE DE RESPUESTA.

    **Condiciones del curso:**
    - Evaluación: Calificación máxima al final, sin exámenes ni tareas.
    - Material: Libro de texto en PDF proporcionado por el profesor.
    - Clases: Video semanal con explicación del tema.
    - Enfoque: El curso requiere un rol autodidacta del alumno.
    """
}

CONFIG = load_config()

def verificar_crear_archivo():
    """Verifica si el archivo existe y tiene el formato correcto, solo lo crea si no existe"""
    try:
        # Verificar si el archivo existe
        if os.path.exists(CONFIG['CSV_MATERIAS']):
            # Verificar que tenga contenido y formato válido
            if os.path.getsize(CONFIG['CSV_MATERIAS']) > 0:
                with open(CONFIG['CSV_MATERIAS'], 'r', encoding='utf-8') as f:
                    reader = csv.reader(f)
                    headers = next(reader, None)
                    if headers and all(col in headers for col in ['nombre', 'email', 'materias']):
                        return True
                    else:
                        st.error("El archivo existe pero no tiene el formato correcto")
                        return False
            return True
        else:
            # Crear archivo solo si no existe
            with open(CONFIG['CSV_MATERIAS'], 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=['nombre', 'email', 'materias', 'fecha'])
                writer.writeheader()
            return True
    except Exception as e:
        st.error(f"Error al verificar/crear archivo: {str(e)}")
        return False

def get_sftp_connection():
    """Establece conexión SFTP con el servidor remoto"""
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        ssh.connect(
            hostname=CONFIG['REMOTE']['HOST'],
            port=CONFIG['REMOTE']['PORT'],
            username=CONFIG['REMOTE']['USER'],
            password=CONFIG['REMOTE']['PASSWORD'],
            timeout=CONFIG['TIMEOUT_SECONDS']
        )
        return ssh.open_sftp()
    except Exception as e:
        st.error(f"Error de conexión SFTP: {str(e)}")
        return None

def obtener_alumnos(materia):
    """Obtiene la lista de alumnos inscritos en una materia específica"""
    if not verificar_crear_archivo():
        return []
    
    try:
        with open(CONFIG['CSV_MATERIAS'], 'r', encoding='utf-8') as f:
            alumnos = []
            reader = csv.DictReader(f)
            
            # Verificar nuevamente las columnas por seguridad
            if not all(col in reader.fieldnames for col in ['nombre', 'email', 'materias']):
                st.error("El archivo no tiene las columnas requeridas")
                return []
            
            for row in reader:
                try:
                    if materia.lower() in [m.strip().lower() for m in row['materias'].split(',')]:
                        alumnos.append({
                            'nombre': row.get('nombre', ''),
                            'email': row.get('email', ''),
                            'fecha': row.get('fecha', 'Fecha no disponible')
                        })
                except (KeyError, AttributeError):
                    continue
            return alumnos
    except Exception as e:
        st.error(f"Error al leer el archivo: {str(e)}")
        return []

def registrar_alumno(nombre, email, materias_seleccionadas):
    """Registra un nuevo alumno en el sistema"""
    if not verificar_crear_archivo():
        return False
    
    try:
        with open(CONFIG['CSV_MATERIAS'], 'a', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=['nombre', 'email', 'materias', 'fecha'])
            
            writer.writerow({
                'nombre': nombre.strip(),
                'email': email.strip(),
                'materias': ', '.join(m.strip() for m in materias_seleccionadas),
                'fecha': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })
        
        # Enviar correo de confirmación
        asunto = "Confirmación de registro en materias académicas"
        mensaje = f"""
        Hola {nombre},
        
        Gracias por registrarte en las siguientes materias:
        {', '.join(materias_seleccionadas)}
        
        Recibirás materiales y notificaciones importantes en este correo electrónico.
        
        Saludos,
        Equipo Académico
        """
        enviar_correo(email, asunto, mensaje)
        
        return True
    except Exception as e:
        st.error(f"Error al registrar al alumno: {str(e)}")
        return False

def enviar_notificacion(asunto, mensaje):
    """Envía una notificación al administrador"""
    try:
        enviar_correo(CONFIG['NOTIFICATION_EMAIL'], asunto, mensaje)
        return True
    except Exception as e:
        st.error(f"Error al enviar notificación: {str(e)}")
        return False

def enviar_correo(destinatario, asunto, mensaje, adjunto=None):
    """Envía un correo electrónico con opción a adjunto"""
    try:
        # Configurar el mensaje
        msg = MIMEMultipart()
        msg['From'] = CONFIG['EMAIL_USER']
        msg['To'] = destinatario
        msg['Date'] = formatdate(localtime=True)
        msg['Subject'] = asunto
        
        # Adjuntar el cuerpo del mensaje
        msg.attach(MIMEText(mensaje, 'plain'))
        
        # Adjuntar archivo si se proporciona
        if adjunto:
            part = MIMEBase('application', 'octet-stream')
            part.set_payload(adjunto.read())
            encoders.encode_base64(part)
            part.add_header(
                'Content-Disposition',
                f'attachment; filename="{adjunto.name}"'
            )
            msg.attach(part)
        
        # Configurar conexión segura con el servidor SMTP
        context = ssl.create_default_context()
        
        with smtplib.SMTP_SSL(
            CONFIG['SMTP_SERVER'],
            CONFIG['SMTP_PORT'],
            context=context
        ) as server:
            server.login(CONFIG['EMAIL_USER'], CONFIG['EMAIL_PASSWORD'])
            server.sendmail(CONFIG['EMAIL_USER'], destinatario, msg.as_string())
        
        return True
    except Exception as e:
        st.error(f"Error al enviar correo: {str(e)}")
        return False

def enviar_material(materia, asunto, mensaje, urls, archivo_pdf):
    """Envía material a todos los alumnos de una materia"""
    try:
        alumnos = obtener_alumnos(materia)
        if not alumnos:
            st.warning("No hay alumnos inscritos en esta materia")
            return False
        
        # Preparar mensaje con URLs si existen
        if urls:
            mensaje += "\n\nEnlaces adicionales:\n"
            for i, url in enumerate(urls, 1):
                mensaje += f"{i}. {url}\n"
        
        # Verificar tamaño del archivo adjunto
        if archivo_pdf:
            max_size = CONFIG['MAX_FILE_SIZE_MB'] * 1024 * 1024
            if archivo_pdf.size > max_size:
                st.error(f"El archivo excede el tamaño máximo permitido ({CONFIG['MAX_FILE_SIZE_MB']}MB)")
                return False
        
        # Enviar a cada alumno
        total = len(alumnos)
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        for i, alumno in enumerate(alumnos, 1):
            status_text.text(f"Enviando a {alumno['nombre']} ({i}/{total})...")
            enviar_correo(
                alumno['email'],
                asunto,
                f"Hola {alumno['nombre']},\n\n{mensaje}",
                archivo_pdf
            )
            progress_bar.progress(i / total)
            time.sleep(1)  # Pequeña pausa para evitar bloqueos
        
        status_text.text("")
        st.success(f"Material enviado correctamente a {total} alumnos")
        return True
    except Exception as e:
        st.error(f"Error al enviar material: {str(e)}")
        return False

def main():
    st.set_page_config(
        page_title="Sistema Académico",
        page_icon="🎓",
        layout="centered"
    )
    
    # Mostrar logo UNAM en la barra lateral
    st.sidebar.image("unam.svg", width=150)
    
    st.title("Notificaciones Académicas")
    
    modo = st.sidebar.radio(
        "Modo de operación",
        ["Estudiante", "Profesor"],
        horizontal=True,
        index=0
    )
    
    if modo == "Estudiante":
        st.header("Registro del Estudiante")
        st.error("Consulte abajo los temarios de cada materia")
        
        # Inicializar el estado para el temario activo
        if 'temario_activo' not in st.session_state:
            st.session_state.temario_activo = None
        
        # Mostrar el temario si hay uno activo
        if st.session_state.temario_activo:
            materia = st.session_state.temario_activo
            with st.expander(f"📖 Temario de {materia}", expanded=True):
                st.markdown(TEMARIOS.get(materia, "**Temario no disponible actualmente**"))
        
        with st.form("form_registro", border=True):
            nombre = st.text_input("Nombre completo*", placeholder="Ej: Juan Pérez López")
            email = st.text_input("Correo electrónico*", placeholder="Ej: juan.perez@correo.unam.mx")
            
            st.markdown("**Selecciona tus materias:**")
            cols = st.columns(2)
            materias_seleccionadas = []
            
            for i, materia in enumerate(CONFIG['REMOTE']['FILES'].keys()):
                with cols[i % 2]:
                    if st.checkbox(materia, key=f"materia_{i}"):
                        materias_seleccionadas.append(materia)
            
            if st.form_submit_button("Registrarme", type="primary"):
                if not nombre or not email:
                    st.warning("Por favor completa todos los campos obligatorios")
                elif not materias_seleccionadas:
                    st.warning("Debes seleccionar al menos una materia")
                elif registrar_alumno(nombre, email, materias_seleccionadas):
                    st.success("""¡Registro completado exitosamente!
                    
                    **Importante:** Hemos enviado un correo de confirmación a tu dirección. Si no lo ves en tu bandeja de entrada:
                    
                    1. Revisa tu carpeta de **Spam** o **Correo no deseado**
                    2. Agrega nuestra dirección ({}) a tus contactos
                    3. Espera 5-10 minutos y vuelve a revisar
                    
                    Si después de 15 minutos no has recibido el correo, por favor contacta al administrador del sistema con tu nombre y correo electrónico.
                    """.format(CONFIG['EMAIL_USER']))
                    st.balloons()
        
        # Botones de temario en pestañas
        st.markdown("---")
        st.subheader("Consultar Temarios")
        
        # Crear pestañas para cada materia
        tabs = st.tabs([f"📚 {materia}" for materia in CONFIG['REMOTE']['FILES'].keys()])
        
        for i, tab in enumerate(tabs):
            with tab:
                materia = list(CONFIG['REMOTE']['FILES'].keys())[i]
                st.markdown(TEMARIOS.get(materia, "**Temario no disponible actualmente**"))

    elif modo == "Profesor":
        st.header("Acceso para Profesores")
        
        # Verificación de contraseña
        password = st.text_input("Contraseña de acceso", type="password", help="Ingresa la contraseña proporcionada por el administrador")
        
        if password == CONFIG['REMOTE_PASSWORD']:
            st.session_state.profesor_autenticado = True
        
        if st.session_state.get('profesor_autenticado', False):
            st.success("Acceso autorizado")
            st.header("Envío de Material Académico")
            
            # Diagnóstico del archivo
            with st.expander("🔍 Diagnóstico del archivo de registros", expanded=False):
                if os.path.exists(CONFIG['CSV_MATERIAS']):
                    st.success(f"Archivo encontrado: {CONFIG['CSV_MATERIAS']}")
                    try:
                        with open(CONFIG['CSV_MATERIAS'], 'r', encoding='utf-8') as f:
                            reader = csv.DictReader(f)
                            if reader.fieldnames and all(col in reader.fieldnames for col in ['nombre', 'email', 'materias']):
                                st.success("Formato del archivo válido")
                                num_alumnos = sum(1 for _ in reader)
                                st.info(f"Total de registros: {num_alumnos}")
                            else:
                                st.error("El archivo no tiene el formato correcto")
                    except Exception as e:
                        st.error(f"Error al leer el archivo: {str(e)}")
                else:
                    st.warning("El archivo de registros no existe aún")
            
            materia = st.selectbox(
                "Selecciona una materia",
                list(CONFIG['REMOTE']['FILES'].keys()),
                index=None,
                placeholder="Selecciona una materia de la lista..."
            )
            
            if materia:
                alumnos = obtener_alumnos(materia)
                
                if alumnos:
                    st.subheader(f"Alumnos inscritos: {len(alumnos)}")
                    
                    with st.expander("Ver lista completa de alumnos", expanded=False):
                        for alumno in alumnos:
                            st.write(f"- **{alumno['nombre']}** ({alumno['email']}) - Registrado el {alumno['fecha']}")
                    
                    st.divider()
                    st.subheader("Componer mensaje")
                    
                    with st.form("form_envio", border=True):
                        asunto = st.text_input("Asunto*", placeholder="Ej: Material de estudio para el examen parcial")
                        mensaje = st.text_area("Mensaje*", height=150, placeholder="Escribe aquí el contenido que recibirán los estudiantes...")
                        
                        st.markdown("**Enlaces adicionales (opcional):**")
                        urls = []
                        for i in range(3):
                            url = st.text_input(f"Enlace {i+1}", key=f"url_{i}", placeholder="https://ejemplo.com/recurso")
                            if url:
                                urls.append(url)
                        
                        archivo_pdf = st.file_uploader(
                            f"Adjuntar archivo PDF (opcional, máximo {CONFIG['MAX_FILE_SIZE_MB']}MB)", 
                            type="pdf",
                            help="Sube un archivo PDF que se enviará adjunto a todos los estudiantes"
                        )
                        
                        if st.form_submit_button("Enviar a todos los alumnos", type="primary"):
                            if not asunto or not mensaje:
                                st.warning("Debes completar todos los campos obligatorios")
                            else:
                                enviar_material(materia, asunto, mensaje, urls, archivo_pdf)
                else:
                    st.warning("Actualmente no hay alumnos inscritos en esta materia")
        elif password and password != CONFIG['REMOTE_PASSWORD']:
            st.error("Contraseña incorrecta. Por favor inténtalo nuevamente.")

if __name__ == "__main__":
    main()
