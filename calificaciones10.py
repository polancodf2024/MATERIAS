# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import csv
import os
from datetime import datetime
import paramiko
import time

# Configuración de la página
st.set_page_config(
    page_title="Sistema Académico - Evaluación",
    page_icon="📚",
    layout="centered"
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
            'CALIFICACIONES_FILE': 'calificaciones.csv'
        }

CONFIG = Config()

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
                timeout=30
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
            # Si el archivo no existe, retornar contenido vacío
            if "No such file" in str(e):
                return ""
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
            # Crear directorio si no existe
            try:
                sftp.stat(os.path.dirname(remote_path))
            except:
                sftp.mkdir(os.path.dirname(remote_path))
                
            with sftp.file(remote_path, 'w') as f:
                f.write(content.encode('utf-8'))
            return True
        except Exception as e:
            st.error(f"Error escribiendo archivo remoto: {str(e)}")
            return False
        finally:
            ssh.close()

# ====================
# FUNCIONES DE CALIFICACIONES
# ====================
def inicializar_archivo_calificaciones():
    """Inicializa el archivo CSV si no existe"""
    remote_path = os.path.join(CONFIG.REMOTE['DIR'], CONFIG.REMOTE['CALIFICACIONES_FILE'])
    csv_content = SSHManager.get_remote_file(remote_path)
    
    if csv_content == "" or not csv_content.startswith("Fecha,Número Económico,Nombre Completo,Email,Calificación"):
        # Crear nuevo archivo con encabezados
        nuevo_contenido = "Fecha,Número Económico,Nombre Completo,Email,Calificación\n"
        return SSHManager.write_remote_file(remote_path, nuevo_contenido)
    return True

def guardar_calificacion(numero_economico, nombre, email, calificacion):
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
def validate_email(email):
    """Valida el formato de un email"""
    import re
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def clean_name(name):
    """Limpia y formatea nombres"""
    if not name:
        return name
    # Elimina caracteres extraños pero conserva acentos y ñ
    import re
    name = re.sub(r'[^a-zA-ZáéíóúÁÉÍÓÚñÑ\s]', '', name.strip())
    # Formato título (primera letra mayúscula)
    return ' '.join(word.capitalize() for word in name.split())

# ====================
# INTERFAZ PRINCIPAL
# ====================
def main():
    st.title("🤖 Evaluación de  la  Semana 1")
#    st.write("Este examen evalúa tu comprensión sobre el tema estudiado y te dará cómo formular preguntas efectivas para obtener mejores respuestas de DeepSeek.")
    
    # Inicializar el archivo de calificaciones
    if not inicializar_archivo_calificaciones():
        st.error("No se pudo inicializar el archivo de calificaciones. Contacta al administrador: polanco@unam.mx.")
        return
    
    # Inicializar variables de sesión si no existen
    if 'examen_iniciado' not in st.session_state:
        st.session_state.examen_iniciado = False
    if 'respuestas' not in st.session_state:
        st.session_state.respuestas = [None] * len(preguntas)
    
    # Sección de información del estudiante
    with st.form("info_estudiante"):
        st.header("Información del Estudiante")
        numero_economico = st.text_input("Número Económico:")
        nombre_completo = st.text_input("Nombre Completo:")
        email = st.text_input("Email:")
        
        submitted_info = st.form_submit_button("Comenzar Examen")
    
    # Si se ha enviado la información del estudiante, mostrar el examen
    if submitted_info:
        if not numero_economico or not nombre_completo or not email:
            st.error("Por favor, completa todos los campos.")
        else:
            # Validar email
            if not validate_email(email):
                st.error("Por favor ingresa un correo electrónico válido")
            else:
                # Guardar información del estudiante en sesión
                st.session_state.numero_economico = numero_economico
                st.session_state.nombre_completo = clean_name(nombre_completo)
                st.session_state.email = email
                st.session_state.examen_iniciado = True
                st.session_state.respuestas = [None] * len(preguntas)
                st.rerun()
    
    # Mostrar el examen si ha sido iniciado
    if st.session_state.get('examen_iniciado', False):
        st.header("Examen: Cómo Formular Preguntas a DeepSeek")
        st.write("Responde las siguientes 5 preguntas seleccionando la opción correcta:")
        
        # Mostrar preguntas
        for i, pregunta_data in enumerate(preguntas):
            st.subheader(pregunta_data["pregunta"])
            opcion_seleccionada = st.radio(
                f"Selecciona una opción para la pregunta {i+1}:",
                pregunta_data["opciones"],
                key=f"pregunta_{i}",
                index=None
            )
            st.session_state.respuestas[i] = opcion_seleccionada
            st.write("---")
        
        # Botón para enviar respuestas
        if st.button("Enviar Examen", type="primary"):
            # Verificar que todas las preguntas han sido respondidas
            if None in st.session_state.respuestas:
                st.error("Por favor, responde todas las preguntas antes de enviar el examen.")
            else:
                # Calificar examen
                calificacion = 0
                respuestas_correctas = []
                resultados_detallados = []
                
                for i, pregunta_data in enumerate(preguntas):
                    if st.session_state.respuestas[i] == pregunta_data["respuesta_correcta"]:
                        calificacion += 1
                        resultados_detallados.append("✓ Correcta")
                    else:
                        resultados_detallados.append("✗ Incorrecta")
                    respuestas_correctas.append(pregunta_data["respuesta_correcta"])
                
                # Guardar calificación
                if guardar_calificacion(
                    st.session_state.numero_economico,
                    st.session_state.nombre_completo,
                    st.session_state.email,
                    calificacion
                ):
                    # Mostrar resultados
                    st.success(f"✅ Examen completado. Tu calificación es: {calificacion}/5")
                    
                    # Mostrar animaciones
                    st.balloons()
                    st.snow()
                    
                    # Mostrar respuestas correctas y resultados detallados
                    st.subheader("Detalle de tus respuestas:")
                    for i, (correcta, resultado) in enumerate(zip(respuestas_correctas, resultados_detallados)):
                        st.write(f"**Pregunta {i+1}**: {resultado}")
                        st.write(f"**Tu respuesta**: {st.session_state.respuestas[i]}")
                        st.write(f"**Respuesta correcta**: {correcta}")
                        st.write("---")
                    
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
                        label="📥 Descargar preguntas y evaluación",
                        data=csv_data,
                        file_name=f"evaluacion_deepseek_{st.session_state.numero_economico}.csv",
                        mime="text/csv"
                    )
                else:
                    st.error("Error al guardar la calificación. Contacta al administrador: polanco@unam.mx.")

if __name__ == "__main__":
    main()
