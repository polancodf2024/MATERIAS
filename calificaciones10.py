# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import csv
import os
from datetime import datetime
import paramiko
import time
import re
from typing import Optional, List, Dict, Any

# Configuración de la página
st.set_page_config(
    page_title="Sistema Académico - Evaluación",
    page_icon="📚",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# ====================
# CONFIGURACIÓN INICIAL
# ====================
class Config:
    def __init__(self):
        # Configuración para conexión remota
        self.REMOTE = {
            'HOST': st.secrets["remote_host"],
            'USER': st.secrets["remote_user"],
            'PASSWORD': st.secrets["remote_password"],
            'PORT': st.secrets["remote_port"],
            'DIR': st.secrets["remote_dir"],
            'CALIFICACIONES_FILE': st.secrets["remote_calificaciones"]  # Cambiado aquí
        }
        # Tiempo máximo de espera para conexión (segundos)
        self.TIMEOUT = 15
        # Número máximo de reintentos de conexión
        self.MAX_RETRIES = 2

CONFIG = Config()


# ==================
# FUNCIONES SSH/SFTP
# ==================
class SSHManager:
    _connection_cache = None
    _last_connection_time = 0
    _connection_timeout = 300  # 5 minutos para reutilizar conexión

    @staticmethod
    def get_connection():
        """Establece conexión SSH segura con caché y reintentos"""
        current_time = time.time()
        
        # Reutilizar conexión si está activa y no ha expirado
        if (SSHManager._connection_cache and 
            (current_time - SSHManager._last_connection_time) < SSHManager._connection_timeout):
            try:
                # Verificar si la conexión sigue activa
                SSHManager._connection_cache.exec_command("echo 'Connection test'", timeout=5)
                return SSHManager._connection_cache
            except:
                # Si falla la verificación, cerrar y crear nueva conexión
                try:
                    SSHManager._connection_cache.close()
                except:
                    pass
                SSHManager._connection_cache = None
        
        # Crear nueva conexión
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        
        for attempt in range(CONFIG.MAX_RETRIES):
            try:
                ssh.connect(
                    hostname=CONFIG.REMOTE['HOST'],
                    port=CONFIG.REMOTE['PORT'],
                    username=CONFIG.REMOTE['USER'],
                    password=CONFIG.REMOTE['PASSWORD'],
                    timeout=CONFIG.TIMEOUT,
                    banner_timeout=30
                )
                SSHManager._connection_cache = ssh
                SSHManager._last_connection_time = current_time
                return ssh
            except Exception as e:
                if attempt == CONFIG.MAX_RETRIES - 1:
                    st.error(f"Error de conexión SSH después de {CONFIG.MAX_RETRIES} intentos: {str(e)}")
                    return None
                time.sleep(1)  # Esperar antes de reintentar

    @staticmethod
    def cleanup():
        """Limpia la conexión caché si existe"""
        if SSHManager._connection_cache:
            try:
                SSHManager._connection_cache.close()
            except:
                pass
            SSHManager._connection_cache = None

    @staticmethod
    def get_remote_file(remote_path: str) -> Optional[str]:
        """Lee archivo remoto con manejo de errores y reintentos"""
        for attempt in range(CONFIG.MAX_RETRIES):
            ssh = SSHManager.get_connection()
            if not ssh:
                if attempt == CONFIG.MAX_RETRIES - 1:
                    return None
                continue
            
            try:
                sftp = ssh.open_sftp()
                with sftp.file(remote_path, 'r') as f:
                    content = f.read().decode('utf-8')
                return content
            except FileNotFoundError:
                return ""  # Archivo no existe, retornar vacío
            except Exception as e:
                if attempt == CONFIG.MAX_RETRIES - 1:
                    st.error(f"Error leyendo archivo remoto: {str(e)}")
                    return None
                # En caso de error, limpiar conexión y reintentar
                SSHManager.cleanup()
        return None

    @staticmethod
    def write_remote_file(remote_path: str, content: str) -> bool:
        """Escribe en archivo remoto con manejo de errores y reintentos"""
        for attempt in range(CONFIG.MAX_RETRIES):
            ssh = SSHManager.get_connection()
            if not ssh:
                if attempt == CONFIG.MAX_RETRIES - 1:
                    return False
                continue
            
            try:
                sftp = ssh.open_sftp()
                
                # Crear directorio si no existe
                dir_path = os.path.dirname(remote_path)
                try:
                    sftp.stat(dir_path)
                except FileNotFoundError:
                    # Crear directorio recursivamente
                    parts = dir_path.split('/')
                    current_path = ""
                    for part in parts:
                        if part:
                            current_path += '/' + part
                            try:
                                sftp.stat(current_path)
                            except FileNotFoundError:
                                sftp.mkdir(current_path)
                
                # Escribir contenido temporal primero
                temp_path = remote_path + '.tmp'
                with sftp.file(temp_path, 'w') as f:
                    f.write(content.encode('utf-8'))
                
                # Reemplazar archivo original
                try:
                    sftp.rename(temp_path, remote_path)
                except:
                    # Si falla el rename, intentar escribir directamente
                    with sftp.file(remote_path, 'w') as f:
                        f.write(content.encode('utf-8'))
                
                return True
            except Exception as e:
                if attempt == CONFIG.MAX_RETRIES - 1:
                    st.error(f"Error escribiendo archivo remoto: {str(e)}")
                    return False
                # En caso de error, limpiar conexión y reintentar
                SSHManager.cleanup()
        return False

# ====================
# FUNCIONES DE CALIFICACIONES
# ====================
def inicializar_archivo_calificaciones() -> bool:
    """Inicializa el archivo CSV si no existe"""
    remote_path = os.path.join(CONFIG.REMOTE['DIR'], CONFIG.REMOTE['CALIFICACIONES_FILE'])
    csv_content = SSHManager.get_remote_file(remote_path)

    if csv_content is None:
        return False  # Error de conexión

    if csv_content == "" or not csv_content.startswith("Fecha,Número Económico,Nombre Completo,Email,Calificación"):
        # Crear nuevo archivo con encabezados
        nuevo_contenido = "Fecha,Número Económico,Nombre Completo,Email,Calificación\n"
        return SSHManager.write_remote_file(remote_path, nuevo_contenido)
    return True

def guardar_calificacion(numero_economico: str, nombre: str, email: str, calificacion: int) -> bool:
    """Guarda la calificación en el archivo CSV remoto"""
    fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    nuevo_registro = f"{fecha},{numero_economico},{nombre},{email},{calificacion}\n"

    remote_path = os.path.join(CONFIG.REMOTE['DIR'], CONFIG.REMOTE['CALIFICACIONES_FILE'])
    csv_content = SSHManager.get_remote_file(remote_path)

    if csv_content is None:
        return False

    # Asegurar que el contenido termina con nueva línea
    if csv_content and not csv_content.endswith('\n'):
        csv_content += '\n'

    nuevo_contenido = csv_content + nuevo_registro
    return SSHManager.write_remote_file(remote_path, nuevo_contenido)



# ====================
# PREGUNTAS DEL EXAMEN
# ====================
preguntas = [
    {
        "pregunta": "1. ¿Cuál es la característica más importante al formular preguntas a DeepSeek para obtener respuestas precisas?",
        "opciones": [
            "Usar lenguaje técnico complejo",
            "Ser específico y claro en la solicitud",
            "Incluir múltiples preguntas en una sola consulta",
            "Escribir en inglés siempre"
        ],
        "respuesta_correcta": "Ser específico y claro en la solicitud"
    },
    {
        "pregunta": "2. Al pedir código a DeepSeek, ¿qué práctica mejora significativamente los resultados?",
        "opciones": [
            "Solicitar código sin contexto alguno",
            "Especificar el lenguaje de programación y el objetivo del código",
            "Pedir que adivine qué lenguaje quieres usar",
            "Solicitar código completo sin ejemplos"
        ],
        "respuesta_correcta": "Especificar el lenguaje de programación y el objetivo del código"
    },
    {
        "pregunta": "3. Si DeepSeek no entiende tu pregunta, ¿cuál es la mejor estrategia?",
        "opciones": [
            "Repetir exactamente la misma pregunta más fuerte",
            "Reformular la pregunta con diferentes palabras o ejemplos",
            "Culpar al modelo por no entender",
            "Abandonar la consulta completamente"
        ],
        "respuesta_correcta": "Reformular la pregunta con diferentes palabras o ejemplos"
    },
    {
        "pregunta": "4. Para obtener explicaciones detalladas sobre un concepto, ¿qué enfoque es más efectivo?",
        "opciones": [
            "Pedir simplemente 'explícame X concepto'",
            "Solicitar 'explica X concepto como si fuera para un principiante'",
            "Asumir que el modelo sabe tu nivel de conocimiento",
            "Pedir la explicación más técnica posible"
        ],
        "respuesta_correcta": "Solicitar 'explica X concepto como si fuera para un principiante'"
    },
    {
        "pregunta": "5. Al solicitar comparaciones entre tecnologías, ¿qué información adicional es crucial para obtener una respuesta útil?",
        "opciones": [
            "El color favorito del programador",
            "El contexto de uso o caso específico donde se aplicará",
            "La fecha de creación de cada tecnología",
            "El número de líneas de código de cada opción"
        ],
        "respuesta_correcta": "El contexto de uso o caso específico donde se aplicará"
    }
]

# ====================
# FUNCIONES DE VALIDACIÓN
# ====================
def validate_email(email: str) -> bool:
    """Valida el formato de un email"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def clean_name(name: str) -> str:
    """Limpia y formatea nombres"""
    if not name:
        return name
    # Elimina caracteres extraños pero conserva acentos y ñ
    name = re.sub(r'[^a-zA-ZáéíóúÁÉÍÓÚñÑ\s]', '', name.strip())
    # Formato título (primera letra mayúscula)
    return ' '.join(word.capitalize() for word in name.split())

def validate_student_id(student_id: str) -> bool:
    """Valida que el número económico tenga un formato básico"""
    if not student_id:
        return False
    # Permite números y letras, mínimo 5 caracteres
    return bool(re.match(r'^[a-zA-Z0-9]{5,}$', student_id.strip()))

# ====================
# COMPONENTES DE INTERFAZ
# ====================
def show_student_info_form():
    """Muestra el formulario de información del estudiante"""
    with st.form("info_estudiante"):
        st.header("Información del Estudiante")
        
        col1, col2 = st.columns(2)
        
        with col1:
            numero_economico = st.text_input("Número Económico:", 
                                           help="Ingresa tu número de cuenta o identificador estudiantil")
        with col2:
            email = st.text_input("Email:", 
                                help="Ingresa tu correo electrónico institucional")
        
        nombre_completo = st.text_input("Nombre Completo:", 
                                      help="Ingresa tu nombre completo como aparece en registros oficiales")
        
        submitted_info = st.form_submit_button("Comenzar Examen", use_container_width=True)
        
        if submitted_info:
            errors = []
            
            if not numero_economico:
                errors.append("El número económico es obligatorio")
            elif not validate_student_id(numero_economico):
                errors.append("El número económico no tiene un formato válido")
                
            if not nombre_completo:
                errors.append("El nombre completo es obligatorio")
            elif len(clean_name(nombre_completo).split()) < 2:
                errors.append("Ingresa al menos nombre y apellido")
                
            if not email:
                errors.append("El email es obligatorio")
            elif not validate_email(email):
                errors.append("El formato del email no es válido")
            
            if errors:
                for error in errors:
                    st.error(error)
                return None, None, None, False
            else:
                return numero_economico, clean_name(nombre_completo), email, True
        
        return None, None, None, False

def show_exam_interface():
    """Muestra la interfaz del examen"""
    st.header("Examen: Cómo Formular Preguntas a DeepSeek")
    st.write("Responde las siguientes 5 preguntas seleccionando la opción correcta:")
    
    # Usar tabs para organizar las preguntas
    tabs = st.tabs([f"Pregunta {i+1}" for i in range(len(preguntas))])
    
    all_answered = True
    for i, (tab, pregunta_data) in enumerate(zip(tabs, preguntas)):
        with tab:
            st.subheader(pregunta_data["pregunta"])
            
            # Obtener el índice de la opción seleccionada previamente
            selected_index = None
            if st.session_state.respuestas[i] is not None:
                try:
                    selected_index = pregunta_data["opciones"].index(st.session_state.respuestas[i])
                except ValueError:
                    selected_index = None
            
            opcion_seleccionada = st.radio(
                f"Selecciona una opción:",
                pregunta_data["opciones"],
                key=f"pregunta_{i}",
                index=selected_index
            )
            st.session_state.respuestas[i] = opcion_seleccionada
            
            if opcion_seleccionada is None:
                all_answered = False
                st.warning("⚠️ Esta pregunta aún no ha sido respondida")
    
    return all_answered

def show_results(calificacion: int, respuestas_correctas: List[str]):
    """Muestra los resultados del examen"""
    st.success(f"✅ Examen completado. Tu calificación es: {calificacion}/5")

    # Mostrar animaciones
    if calificacion >= 4:
        st.balloons()
    st.snow()

    # Mostrar respuestas correctas y resultados detallados
    st.subheader("Detalle de tus respuestas:")

    resultados_detallados = []
    for i, pregunta_data in enumerate(preguntas):
        es_correcta = st.session_state.respuestas[i] == pregunta_data["respuesta_correcta"]
        resultado = "✓ Correcta" if es_correcta else "✗ Incorrecta"
        resultados_detallados.append(resultado)

        with st.expander(f"Pregunta {i+1}: {resultado}"):
            st.write(f"**Tu respuesta**: {st.session_state.respuestas[i] or 'No respondida'}")
            st.write(f"**Respuesta correcta**: {pregunta_data['respuesta_correcta']}")

    # Preparar datos para descarga
    resultados = {
        "Pregunta": [pregunta["pregunta"] for pregunta in preguntas],
        "Tu respuesta": st.session_state.respuestas,
        "Respuesta correcta": respuestas_correctas,
        "Resultado": resultados_detallados
    }

    df_resultados = pd.DataFrame(resultados)

    # Opciones de descarga
    st.subheader("Descargar Resultados")
    csv_data = df_resultados.to_csv(index=False)

    st.download_button(
        label="📥 Descargar evaluación completa",
        data=csv_data,
        file_name=f"evaluacion_deepseek_{st.session_state.numero_economico}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
        mime="text/csv",
        use_container_width=True
    )

def reset_exam():
    """Reinicia el examen para permitir otro intento"""
    for key in ['examen_iniciado', 'numero_economico', 'nombre_completo', 'email', 'respuestas']:
        if key in st.session_state:
            del st.session_state[key]
    st.rerun()

def calculate_grade() -> tuple:
    """Calcula la calificación y prepara los resultados"""
    calificacion = 0
    respuestas_correctas = []
    
    for i, pregunta_data in enumerate(preguntas):
        respuestas_correctas.append(pregunta_data["respuesta_correcta"])
        if st.session_state.respuestas[i] == pregunta_data["respuesta_correcta"]:
            calificacion += 1
    
    return calificacion, respuestas_correctas

# ====================
# INTERFAZ PRINCIPAL
# ====================
def main():
    st.title("🤖 Evaluación de la Semana 1")
    
    # Inicializar el archivo de calificaciones
    if not inicializar_archivo_calificaciones():
        st.error("No se pudo inicializar el archivo de calificaciones. Contacta al administrador: polanco@unam.mx.")
        return
    
    # Inicializar variables de sesión si no existen
    if 'examen_iniciado' not in st.session_state:
        st.session_state.examen_iniciado = False
    if 'respuestas' not in st.session_state:
        st.session_state.respuestas = [None] * len(preguntas)
    
    # Mostrar estado de conexión
    with st.sidebar:
        st.header("Estado del Sistema")
        if SSHManager.get_connection():
            st.success("✅ Conectado al servidor")
        else:
            st.error("❌ Error de conexión")
        
        st.info(f"Preguntas: {len(preguntas)}")
        if st.session_state.examen_iniciado:
            respuestas_contestadas = sum(1 for r in st.session_state.respuestas if r is not None)
            st.info(f"Progreso: {respuestas_contestadas}/{len(preguntas)}")
    
    # Flujo principal de la aplicación
    if not st.session_state.examen_iniciado:
        # Sección de información del estudiante
        numero_economico, nombre_completo, email, info_valida = show_student_info_form()
        
        if info_valida:
            # Guardar información del estudiante en sesión
            st.session_state.numero_economico = numero_economico
            st.session_state.nombre_completo = nombre_completo
            st.session_state.email = email
            st.session_state.examen_iniciado = True
            st.session_state.respuestas = [None] * len(preguntas)
            st.rerun()
    else:
        # Mostrar información del estudiante actual
        st.sidebar.write("---")
        st.sidebar.subheader("Estudiante:")
        st.sidebar.write(f"**Nombre**: {st.session_state.nombre_completo}")
        st.sidebar.write(f"**Número Económico**: {st.session_state.numero_economico}")
        st.sidebar.write(f"**Email**: {st.session_state.email}")
        
        # Mostrar el examen
        all_answered = show_exam_interface()
        
        # Botón para enviar respuestas
        col1, col2 = st.columns([1, 2])
        
        with col1:
            if st.button("Reiniciar Examen", type="secondary"):
                reset_exam()
                return
        
        with col2:
            if st.button("Enviar Examen", type="primary", disabled=not all_answered):
                # Calificar examen
                calificacion, respuestas_correctas = calculate_grade()
                
                # Guardar calificación
                if guardar_calificacion(
                    st.session_state.numero_economico,
                    st.session_state.nombre_completo,
                    st.session_state.email,
                    calificacion
                ):
                    show_results(calificacion, respuestas_correctas)
                else:
                    st.error("Error al guardar la calificación. Contacta al administrador: polanco@unam.mx.")

# Manejo de limpieza al finalizar
try:
    if __name__ == "__main__":
        main()
finally:
    # Limpiar conexiones SSH al finalizar
    SSHManager.cleanup()
