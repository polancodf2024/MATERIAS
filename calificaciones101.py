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
import threading
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

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
            'CALIFICACIONES_FILE': st.secrets["remote_calificacionesI"]
        }
        
        # Configuración para envío de correos (usando los nombres correctos de tus secrets)
        self.EMAIL_CONFIGURED = False
        try:
            self.EMAIL = {
                'SMTP_SERVER': st.secrets["smtp_server"],
                'SMTP_PORT': st.secrets["smtp_port"],
                'SENDER_EMAIL': st.secrets["email_user"],
                'SENDER_PASSWORD': st.secrets["email_password"],
                'ADMIN_EMAIL': st.secrets["notification_email"]
            }
            self.EMAIL_CONFIGURED = True
        except KeyError as e:
            st.warning(f"⚠️ Configuración de correo incompleta: {e}. El envío de correos estará deshabilitado.")
            self.EMAIL = {}
        
        # Tiempo máximo de espera para conexión (segundos)
        self.TIMEOUT = 15
        # Número máximo de reintentos de conexión
        self.MAX_RETRIES = 2

CONFIG = Config()


# ==================
# FUNCIONES SSH/SFTP
# ==================
class SSHConnectionPool:
    """Pool de conexiones SSH para manejar múltiples usuarios simultáneos"""
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(SSHConnectionPool, cls).__new__(cls)
                cls._instance._initialize()
            return cls._instance
    
    def _initialize(self):
        self.available_connections = []
        self.in_use_connections = []
        self.max_connections = 10  # Máximo de conexiones simultáneas
        self.connection_timeout = 300  # 5 minutos para reutilizar conexión
    
    def get_connection(self):
        """Obtiene una conexión del pool"""
        with self._lock:
            current_time = time.time()
            
            # Limpiar conexiones expiradas
            self.available_connections = [
                conn for conn in self.available_connections
                if (current_time - conn['last_used']) < self.connection_timeout
            ]
            
            # Reutilizar conexión disponible
            while self.available_connections:
                conn_data = self.available_connections.pop()
                ssh = conn_data['ssh']
                
                try:
                    # Verificar si la conexión sigue activa
                    ssh.exec_command("echo 'Connection test'", timeout=5)
                    self.in_use_connections.append({
                        'ssh': ssh,
                        'last_used': current_time
                    })
                    return ssh
                except:
                    try:
                        ssh.close()
                    except:
                        pass
                    continue
            
            # Crear nueva conexión si no hay disponibles y no excedemos el límite
            if len(self.in_use_connections) < self.max_connections:
                ssh = self._create_new_connection()
                if ssh:
                    self.in_use_connections.append({
                        'ssh': ssh,
                        'last_used': current_time
                    })
                    return ssh
            
            return None
    
    def _create_new_connection(self):
        """Crea una nueva conexión SSH"""
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
                return ssh
            except Exception as e:
                if attempt == CONFIG.MAX_RETRIES - 1:
                    st.error(f"Error de conexión SSH después de {CONFIG.MAX_RETRIES} intentos: {str(e)}")
                    return None
                time.sleep(1)
    
    def return_connection(self, ssh):
        """Devuelve una conexión al pool"""
        with self._lock:
            # Encontrar y remover de in_use_connections
            self.in_use_connections = [
                conn for conn in self.in_use_connections
                if conn['ssh'] != ssh
            ]
            
            # Verificar que la conexión aún esté activa antes de devolverla al pool
            try:
                ssh.exec_command("echo 'Connection test'", timeout=5)
                self.available_connections.append({
                    'ssh': ssh,
                    'last_used': time.time()
                })
            except:
                try:
                    ssh.close()
                except:
                    pass
    
    def cleanup(self):
        """Limpia todas las conexiones"""
        with self._lock:
            for conn_data in self.available_connections + self.in_use_connections:
                try:
                    conn_data['ssh'].close()
                except:
                    pass
            self.available_connections = []
            self.in_use_connections = []


class SSHManager:
    _connection_pool = SSHConnectionPool()
    _file_lock_timeout = 30  # 30 segundos máximo para esperar un lock

    @staticmethod
    def get_connection():
        """Obtiene una conexión del pool"""
        return SSHManager._connection_pool.get_connection()

    @staticmethod
    def return_connection(ssh):
        """Devuelve una conexión al pool"""
        SSHManager._connection_pool.return_connection(ssh)

    @staticmethod
    def cleanup():
        """Limpia todas las conexiones del pool"""
        SSHManager._connection_pool.cleanup()

    @staticmethod
    def _acquire_file_lock(remote_path: str, sftp) -> bool:
        """Adquiere un lock para el archivo usando archivo .lock"""
        lock_path = remote_path + '.lock'
        max_attempts = 10
        attempt = 0
        
        while attempt < max_attempts:
            try:
                # Intentar crear el archivo lock
                try:
                    sftp.stat(lock_path)
                    # Lock existe, esperar
                    time.sleep(0.5)
                    attempt += 1
                    continue
                except FileNotFoundError:
                    # Lock no existe, crearlo
                    try:
                        with sftp.file(lock_path, 'w') as f:
                            f.write(f"locked_{datetime.now().isoformat()}")
                        # Verificar que somos los dueños del lock
                        time.sleep(0.1)
                        try:
                            sftp.stat(lock_path)
                            return True
                        except FileNotFoundError:
                            # Alguien más creó el lock
                            continue
                    except:
                        continue
            except Exception:
                attempt += 1
                time.sleep(0.5)
        
        return False

    @staticmethod
    def _release_file_lock(remote_path: str, sftp):
        """Libera el lock del archivo"""
        lock_path = remote_path + '.lock'
        try:
            sftp.remove(lock_path)
        except:
            pass  # Ignorar errores al liberar lock

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
                
                # Adquirir lock antes de leer
                if not SSHManager._acquire_file_lock(remote_path, sftp):
                    st.warning("Esperando acceso al archivo...")
                    if attempt == CONFIG.MAX_RETRIES - 1:
                        SSHManager.return_connection(ssh)
                        return None
                    continue
                
                try:
                    with sftp.file(remote_path, 'r') as f:
                        content = f.read().decode('utf-8')
                    return content
                finally:
                    # Liberar lock después de leer
                    SSHManager._release_file_lock(remote_path, sftp)
                    
            except FileNotFoundError:
                SSHManager._release_file_lock(remote_path, sftp)
                return ""  # Archivo no existe, retornar vacío
            except Exception as e:
                SSHManager._release_file_lock(remote_path, sftp)
                if attempt == CONFIG.MAX_RETRIES - 1:
                    st.error(f"Error leyendo archivo remoto: {str(e)}")
                    return None
                # En caso de error, reintentar
            finally:
                SSHManager.return_connection(ssh)
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
                
                # Adquirir lock antes de escribir
                if not SSHManager._acquire_file_lock(remote_path, sftp):
                    st.warning("Esperando acceso al archivo...")
                    if attempt == CONFIG.MAX_RETRIES - 1:
                        SSHManager.return_connection(ssh)
                        return False
                    continue
                
                try:
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
                finally:
                    # Liberar lock después de escribir
                    SSHManager._release_file_lock(remote_path, sftp)
                    
            except Exception as e:
                SSHManager._release_file_lock(remote_path, sftp)
                if attempt == CONFIG.MAX_RETRIES - 1:
                    st.error(f"Error escribiendo archivo remoto: {str(e)}")
                    return False
            finally:
                SSHManager.return_connection(ssh)
        return False

# ====================
# FUNCIONES DE CORREO
# ====================
class EmailManager:
    @staticmethod
    def enviar_correo_resultados(destinatario: str, nombre_estudiante: str, numero_economico: str, 
                               calificacion: int, respuestas_detalladas: List[Dict]) -> bool:
        """
        Envía un correo con los resultados de la evaluación al estudiante
        """
        if not CONFIG.EMAIL_CONFIGURED:
            return False
            
        try:
            # Configurar el mensaje
            mensaje = MIMEMultipart()
            mensaje['From'] = CONFIG.EMAIL['SENDER_EMAIL']
            mensaje['To'] = destinatario
            mensaje['Subject'] = f"📊 Resultados de Evaluación - Semana 1 - {nombre_estudiante}"
            
            # Crear contenido del correo
            cuerpo = f"""
            <html>
            <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                <div style="max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #ddd; border-radius: 10px;">
                    <h2 style="color: #2c3e50; text-align: center;">📚 Evaluación de la Semana 1</h2>
                    <h3 style="color: #34495e;">Resultados de tu evaluación</h3>
                    
                    <div style="background-color: #f8f9fa; padding: 15px; border-radius: 5px; margin: 15px 0;">
                        <p><strong>Estudiante:</strong> {nombre_estudiante}</p>
                        <p><strong>Número Económico:</strong> {numero_economico}</p>
                        <p><strong>Email:</strong> {destinatario}</p>
                        <p><strong>Fecha de Evaluación:</strong> {datetime.now().strftime('%d/%m/%Y %H:%M')}</p>
                    </div>
                    
                    <div style="text-align: center; margin: 20px 0;">
                        <h2 style="color: {'#27ae60' if calificacion >= 4 else '#e74c3c'};">
                            Calificación Final: {calificacion}/5
                        </h2>
                        <p style="font-size: 18px;">
                            {'✅ ¡Felicidades! Has aprobado la evaluación.' if calificacion >= 4 else '📝 Sigue practicando para mejorar.'}
                        </p>
                    </div>
                    
                    <h4 style="color: #34495e;">Detalle de tus respuestas:</h4>
                    <table style="width: 100%; border-collapse: collapse; margin: 15px 0;">
                        <tr style="background-color: #34495e; color: white;">
                            <th style="padding: 10px; text-align: left;">Pregunta</th>
                            <th style="padding: 10px; text-align: center;">Resultado</th>
                        </tr>
            """
            
            # Agregar detalles de cada pregunta
            for i, resultado in enumerate(respuestas_detalladas, 1):
                color = "#27ae60" if resultado['correcta'] else "#e74c3c"
                icono = "✅" if resultado['correcta'] else "❌"
                
                cuerpo += f"""
                        <tr style="border-bottom: 1px solid #ddd;">
                            <td style="padding: 10px;">Pregunta {i}</td>
                            <td style="padding: 10px; text-align: center; color: {color};">
                                {icono} {resultado['resultado']}
                            </td>
                        </tr>
                """
            
            # Cierre del correo
            cuerpo += f"""
                    </table>
                    
                    <div style="margin-top: 20px; padding: 15px; background-color: #e8f4fd; border-radius: 5px;">
                        <p><strong>Información importante:</strong></p>
                        <ul>
                            <li>Este correo es una confirmación de que tu evaluación ha sido registrada en el sistema.</li>
                            <li>Guarda este correo como comprobante de tu participación.</li>
                            <li>Para cualquier duda o aclaración, contacta al administrador: {CONFIG.EMAIL['ADMIN_EMAIL']}</li>
                        </ul>
                    </div>
                    
                    <div style="margin-top: 20px; text-align: center; color: #7f8c8d; font-size: 12px;">
                        <p>Sistema Académico de Evaluación<br>
                        Instituto Nacional de Cardiología Ignacio Chávez</p>
                    </div>
                </div>
            </body>
            </html>
            """
            
            # Adjuntar el cuerpo del mensaje
            mensaje.attach(MIMEText(cuerpo, 'html'))
            
            # Conectar al servidor SMTP y enviar
            with smtplib.SMTP(CONFIG.EMAIL['SMTP_SERVER'], CONFIG.EMAIL['SMTP_PORT']) as server:
                server.starttls()  # Seguridad TLS
                server.login(CONFIG.EMAIL['SENDER_EMAIL'], CONFIG.EMAIL['SENDER_PASSWORD'])
                server.send_message(mensaje)
            
            return True
            
        except Exception as e:
            st.error(f"Error al enviar correo: {str(e)}")
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
    """Guarda la calificación en el archivo CSV remoto con lock"""
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
    return bool(re.match(r'^[a-zA-Z0-9]{4,}$', student_id.strip()))

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
    respuestas_para_correo = []
    
    for i, pregunta_data in enumerate(preguntas):
        es_correcta = st.session_state.respuestas[i] == pregunta_data["respuesta_correcta"]
        resultado = "✓ Correcta" if es_correcta else "✗ Incorrecta"
        resultados_detallados.append(resultado)
        
        # Preparar datos para el correo
        respuestas_para_correo.append({
            'correcta': es_correcta,
            'resultado': resultado,
            'respuesta_usuario': st.session_state.respuestas[i] or 'No respondida',
            'respuesta_correcta': pregunta_data["respuesta_correcta"]
        })

        with st.expander(f"Pregunta {i+1}: {resultado}"):
            st.write(f"**Tu respuesta**: {st.session_state.respuestas[i] or 'No respondida'}")
            st.write(f"**Respuesta correcta**: {pregunta_data['respuesta_correcta']}")

    # Envío de correos (solo si está configurado)
    if CONFIG.EMAIL_CONFIGURED:
        with st.spinner("Enviando resultados por correo..."):
            # Enviar correo al estudiante
            correo_enviado = EmailManager.enviar_correo_resultados(
                destinatario=st.session_state.email,
                nombre_estudiante=st.session_state.nombre_completo,
                numero_economico=st.session_state.numero_economico,
                calificacion=calificacion,
                respuestas_detalladas=respuestas_para_correo
            )
            
            if correo_enviado:
                st.success(f"📧 Se ha enviado un correo con tus resultados a: {st.session_state.email}")
            else:
                st.warning("⚠️ No se pudo enviar el correo con los resultados, pero tu evaluación ha sido guardada.")
    else:
        st.info("ℹ️ La funcionalidad de correo no está configurada. Tu evaluación ha sido guardada correctamente.")

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
    
    # Mostrar estado de configuración de correo
    if not CONFIG.EMAIL_CONFIGURED:
        st.warning("⚠️ La funcionalidad de correo no está configurada. Los resultados se guardarán pero no se enviarán por correo.")
    
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
        ssh = SSHManager.get_connection()
        if ssh:
            st.success("✅ Conectado al servidor")
            SSHManager.return_connection(ssh)
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
