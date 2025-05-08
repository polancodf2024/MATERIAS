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

# ... (las funciones get_sftp_connection, obtener_alumnos, registrar_alumno, 
# enviar_notificacion, enviar_correo y enviar_material se mantienen igual)

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
