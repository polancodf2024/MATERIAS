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
            'PORT': int(st.secrets.get("remote_port")),
            'DIR': st.secrets["remote_dir"],
            'CALIFICACIONES_FILE': st.secrets["remote_calificaciones"]
        }
        
        # Configuración para envío de correos
        self.EMAIL_CONFIGURED = False
        try:
            self.EMAIL = {
                'SMTP_SERVER': st.secrets["smtp_server"],
                'SMTP_PORT': int(st.secrets.get("smtp_port")),
                'SENDER_EMAIL': st.secrets["email_user"],
                'SENDER_PASSWORD': st.secrets["email_password"]
            }
            self.EMAIL_CONFIGURED = True
        except KeyError as e:
            st.warning(f"⚠️ Configuración de correo incompleta: {e}. El envío de correos estará deshabilitado.")
            self.EMAIL = {}
        
        # Tiempo máximo de espera para conexión (segundos)
        self.TIMEOUT = 15
        # Número máximo de reintentos de conexión
        self.MAX_RETRIES = 3

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
        self.max_connections = 5
        self.connection_timeout = 300
    
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
                    transport = ssh.get_transport()
                    if transport and transport.is_active():
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
            
            # Crear nueva conexión si no hay disponibles
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
                    banner_timeout=30,
                    allow_agent=False,
                    look_for_keys=False
                )
                return ssh
            except Exception as e:
                if attempt == CONFIG.MAX_RETRIES - 1:
                    st.error(f"Error de conexión SSH después de {CONFIG.MAX_RETRIES} intentos: {str(e)}")
                    return None
                time.sleep(2)
    
    def return_connection(self, ssh):
        """Devuelve una conexión al pool"""
        with self._lock:
            self.in_use_connections = [
                conn for conn in self.in_use_connections
                if conn['ssh'] != ssh
            ]
            
            try:
                transport = ssh.get_transport()
                if transport and transport.is_active():
                    self.available_connections.append({
                        'ssh': ssh,
                        'last_used': time.time()
                    })
                else:
                    try:
                        ssh.close()
                    except:
                        pass
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
    _file_lock_timeout = 30

    @staticmethod
    def get_connection():
        return SSHManager._connection_pool.get_connection()

    @staticmethod
    def return_connection(ssh):
        SSHManager._connection_pool.return_connection(ssh)

    @staticmethod
    def cleanup():
        SSHManager._connection_pool.cleanup()

    @staticmethod
    def _acquire_file_lock(remote_path: str, sftp) -> bool:
        lock_path = remote_path + '.lock'
        max_attempts = 10
        attempt = 0
        
        while attempt < max_attempts:
            try:
                try:
                    sftp.stat(lock_path)
                    time.sleep(0.5)
                    attempt += 1
                    continue
                except FileNotFoundError:
                    try:
                        with sftp.file(lock_path, 'w') as f:
                            f.write(f"locked_{datetime.now().isoformat()}")
                        time.sleep(0.1)
                        try:
                            sftp.stat(lock_path)
                            return True
                        except FileNotFoundError:
                            continue
                    except:
                        continue
            except Exception:
                attempt += 1
                time.sleep(0.5)
        
        return False

    @staticmethod
    def _release_file_lock(remote_path: str, sftp):
        lock_path = remote_path + '.lock'
        try:
            sftp.remove(lock_path)
        except:
            pass

    @staticmethod
    def get_remote_file(remote_path: str) -> Optional[str]:
        for attempt in range(CONFIG.MAX_RETRIES):
            ssh = SSHManager.get_connection()
            if not ssh:
                if attempt == CONFIG.MAX_RETRIES - 1:
                    st.error("No se pudo obtener conexión SSH")
                    return None
                continue
            
            try:
                sftp = ssh.open_sftp()
                
                if not SSHManager._acquire_file_lock(remote_path, sftp):
                    if attempt == CONFIG.MAX_RETRIES - 1:
                        SSHManager.return_connection(ssh)
                        return None
                    continue
                
                try:
                    with sftp.file(remote_path, 'r') as f:
                        content = f.read().decode('utf-8')
                    return content
                finally:
                    SSHManager._release_file_lock(remote_path, sftp)
                    
            except FileNotFoundError:
                SSHManager._release_file_lock(remote_path, sftp)
                return ""
            except Exception as e:
                SSHManager._release_file_lock(remote_path, sftp)
                if attempt == CONFIG.MAX_RETRIES - 1:
                    st.error(f"Error leyendo archivo remoto: {str(e)}")
                    return None
            finally:
                SSHManager.return_connection(ssh)
        return None

    @staticmethod
    def write_remote_file(remote_path: str, content: str) -> bool:
        for attempt in range(CONFIG.MAX_RETRIES):
            ssh = SSHManager.get_connection()
            if not ssh:
                if attempt == CONFIG.MAX_RETRIES - 1:
                    st.error("No se pudo obtener conexión SSH para escritura")
                    return False
                continue
            
            try:
                sftp = ssh.open_sftp()
                
                if not SSHManager._acquire_file_lock(remote_path, sftp):
                    if attempt == CONFIG.MAX_RETRIES - 1:
                        SSHManager.return_connection(ssh)
                        return False
                    continue
                
                try:
                    dir_path = os.path.dirname(remote_path)
                    try:
                        sftp.stat(dir_path)
                    except FileNotFoundError:
                        parts = dir_path.split('/')
                        current_path = ""
                        for part in parts:
                            if part:
                                current_path += '/' + part
                                try:
                                    sftp.stat(current_path)
                                except FileNotFoundError:
                                    sftp.mkdir(current_path)
                    
                    temp_path = remote_path + '.tmp'
                    with sftp.file(temp_path, 'w') as f:
                        f.write(content.encode('utf-8'))
                    
                    try:
                        sftp.rename(temp_path, remote_path)
                    except:
                        with sftp.file(remote_path, 'w') as f:
                            f.write(content.encode('utf-8'))
                    
                    return True
                finally:
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
            mensaje = MIMEMultipart()
            mensaje['From'] = CONFIG.EMAIL['SENDER_EMAIL']
            mensaje['To'] = destinatario
            mensaje['Subject'] = f"📊 Resultados de Evaluación - Semana 2 - {nombre_estudiante}"
            
            cuerpo = f"""
            <html>
            <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                <div style="max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #ddd; border-radius: 10px;">
                    <h2 style="color: #2c3e50; text-align: center;">📚 Evaluación de la Semana 2</h2>
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
                            <th style="padding: 10px; text-align: center;">Tu Respuesta</th>
                            <th style="padding: 10px; text-align: center;">Respuesta Correcta</th>
                            <th style="padding: 10px; text-align: center;">Resultado</th>
                        </tr>
            """
            
            for i, resultado in enumerate(respuestas_detalladas, 1):
                color = "#27ae60" if resultado['correcta'] else "#e74c3c"
                icono = "✅" if resultado['correcta'] else "❌"
                
                respuesta_usuario = str(resultado['respuesta_usuario']).replace('<', '&lt;').replace('>', '&gt;')
                respuesta_correcta = str(resultado['respuesta_correcta']).replace('<', '&lt;').replace('>', '&gt;')
                
                cuerpo += f"""
                        <tr style="border-bottom: 1px solid #ddd;">
                            <td style="padding: 10px;">Pregunta {i}</td>
                            <td style="padding: 10px; text-align: center;">{respuesta_usuario}</td>
                            <td style="padding: 10px; text-align: center;">{respuesta_correcta}</td>
                            <td style="padding: 10px; text-align: center; color: {color};">
                                {icono} {resultado['resultado']}
                            </td>
                        </tr>
                """
            
            cuerpo += f"""
                    </table>
                    
                    <div style="margin-top: 20px; padding: 15px; background-color: #e8f4fd; border-radius: 5px;">
                        <p><strong>Información importante:</strong></p>
                        <ul>
                            <li>Este correo es una confirmación de que tu evaluación ha sido registrada en el sistema.</li>
                            <li>Guarda este correo como comprobante de tu participación.</li>
                            <li>Para cualquier duda o aclaración, contacta a tu instructor.</li>
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
            
            mensaje.attach(MIMEText(cuerpo, 'html'))
            
            server = smtplib.SMTP(CONFIG.EMAIL['SMTP_SERVER'], CONFIG.EMAIL['SMTP_PORT'])
            server.starttls()
            server.login(CONFIG.EMAIL['SENDER_EMAIL'], CONFIG.EMAIL['SENDER_PASSWORD'])
            server.send_message(mensaje)
            server.quit()
            
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
    
    with st.spinner("Conectando al servidor..."):
        csv_content = SSHManager.get_remote_file(remote_path)

    if csv_content is None:
        st.error("❌ No se pudo conectar al servidor remoto")
        return False

    if csv_content == "" or not csv_content.startswith("Fecha,Número Económico,Nombre Completo,Email,Calificación"):
        nuevo_contenido = "Fecha,Número Económico,Nombre Completo,Email,Calificación\n"
        with st.spinner("Creando archivo de calificaciones..."):
            success = SSHManager.write_remote_file(remote_path, nuevo_contenido)
        if success:
            st.success("✅ Archivo de calificaciones inicializado correctamente")
        else:
            st.error("❌ Error al inicializar el archivo de calificaciones")
        return success
    
    return True

def guardar_calificacion(numero_economico: str, nombre: str, email: str, calificacion: int) -> bool:
    """Guarda la calificación en el archivo CSV remoto con lock"""
    fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    nombre_limpio = nombre.replace(',', ';')
    nuevo_registro = f'"{fecha}","{numero_economico}","{nombre_limpio}","{email}","{calificacion}"\n'

    remote_path = os.path.join(CONFIG.REMOTE['DIR'], CONFIG.REMOTE['CALIFICACIONES_FILE'])
    
    with st.spinner("Guardando calificación..."):
        csv_content = SSHManager.get_remote_file(remote_path)

    if csv_content is None:
        st.error("❌ Error al leer el archivo de calificaciones existente")
        return False

    if csv_content and not csv_content.endswith('\n'):
        csv_content += '\n'

    nuevo_contenido = csv_content + nuevo_registro
    
    with st.spinner("Escribiendo en archivo remoto..."):
        success = SSHManager.write_remote_file(remote_path, nuevo_contenido)
    
    if success:
        st.success("✅ Calificación guardada correctamente en el archivo remoto")
    else:
        st.error("❌ Error al guardar la calificación en el archivo remoto")
    
    return success

# ====================
# PREGUNTAS DEL EXAMEN
# ====================
preguntas = [
    {
        "pregunta": "1. Un usuario necesita redactar un oficio dirigido a la Dirección General. ¿Cuál de las siguientes opciones es la más específica y efectiva para obtener un resultado útil con DeepSeek?",
        "opciones": [
            "Haz un oficio.",
            "Redacta un oficio formal dirigido a la Dirección General solicitando autorización para el uso del auditorio el próximo 15 de noviembre para una sesión académica, con una asistencia estimada de 50 personas.",
            "Necesito un documento para pedir permiso.",
            "Escribe algo para el auditorio."
        ],
        "respuesta_correcta": "Redacta un oficio formal dirigido a la Dirección General solicitando autorización para el uso del auditorio el próximo 15 de noviembre para una sesión académica, con una asistencia estimada de 50 personas."
    },
    {
        "pregunta": "2. Si un usuario desea traducir un protocolo de investigación del inglés al español manteniendo la terminología médica especializada, ¿cuál es la forma más adecuada de pedirlo?",
        "opciones": [
            "Traduce esto.",
            "Traduce este texto al español.",
            "Traduce este protocolo de investigación del inglés al español manteniendo la terminología cardiológica específica y el formato técnico.",
            "Pon esto en español."
        ],
        "respuesta_correcta": "Traduce este protocolo de investigación del inglés al español manteniendo la terminología cardiológica específica y el formato técnico."
    },
    {
        "pregunta": "3. Para organizar y resumir un acta de reunión, ¿cuál de las siguientes solicitudes permitirá obtener un resultado más estructurado y útil?",
        "opciones": [
            "Lee esto y dime qué dice.",
            "Resume esta acta de reunión.",
            "Toma esta transcripción de reunión y genera un acta formal con los siguientes apartados: puntos tratados, acuerdos alcanzados, acciones pendientes con responsables, y temas para la próxima reunión.",
            "Saca lo importante de esta reunión."
        ],
        "respuesta_correcta": "Toma esta transcripción de reunión y genera un acta formal con los siguientes apartados: puntos tratados, acuerdos alcanzados, acciones pendientes con responsables, y temas para la próxima reunión."
    },
    {
        "pregunta": "4. Si un usuario quiere crear una plantilla para informes mensuales de actividades, ¿cuál es la mejor manera de solicitarlo?",
        "opciones": [
            "Haz un formato.",
            "Crea una plantilla para informes mensuales de actividades que incluya: título del proyecto, investigadores responsables, período reportado, actividades realizadas, resultados obtenidos, dificultades enfrentadas y próximos pasos.",
            "Necesito un modelo para informes.",
            "Diseña algo para reportar avances."
        ],
        "respuesta_correcta": "Crea una plantilla para informes mensuales de actividades que incluya: título del proyecto, investigadores responsables, período reportado, actividades realizadas, resultados obtenidos, dificultades enfrentadas y próximos pasos."
    },
    {
        "pregunta": "5. Al clasificar documentos automáticamente, ¿cuál de estas instrucciones será más efectiva para DeepSeek?",
        "opciones": [
            "Ordena estos documentos.",
            "Clasifica estos 20 documentos en las categorías: Investigación, Administrativo, Pacientes, Proveedores. Para cada uno, indica el tipo de documento y su nivel de prioridad.",
            "Separa estos papeles.",
            "Agrupa estos archivos."
        ],
        "respuesta_correcta": "Clasifica estos 20 documentos en las categorías: Investigación, Administrativo, Pacientes, Proveedores. Para cada uno, indica el tipo de documento y su nivel de prioridad."
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
    name = re.sub(r'[^a-zA-ZáéíóúÁÉÍÓÚñÑ\s]', '', name.strip())
    return ' '.join(word.capitalize() for word in name.split())

def validate_student_id(student_id: str) -> bool:
    """Valida que el número económico tenga un formato básico"""
    if not student_id:
        return False
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
                return numero_economico.strip(), clean_name(nombre_completo), email.strip(), True
        
        return None, None, None, False

def show_exam_interface():
    """Muestra la interfaz del examen"""
    st.header("Examen: Cómo Formular Preguntas a DeepSeek")
    st.write("Responde las siguientes 5 preguntas seleccionando la opción correcta:")
    
    tabs = st.tabs([f"Pregunta {i+1}" for i in range(len(preguntas))])
    
    all_answered = True
    for i, (tab, pregunta_data) in enumerate(zip(tabs, preguntas)):
        with tab:
            st.subheader(pregunta_data["pregunta"])
            
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
    
    return all_answered

def show_results(calificacion: int, respuestas_correctas: List[str]):
    """Muestra los resultados del examen"""
    st.success(f"✅ Examen completado. Tu calificación es: {calificacion}/5")

    if calificacion >= 4:
        st.balloons()
    else:
        st.snow()

    st.subheader("Detalle de tus respuestas:")

    resultados_detallados = []
    respuestas_para_correo = []
    
    for i, pregunta_data in enumerate(preguntas):
        es_correcta = st.session_state.respuestas[i] == pregunta_data["respuesta_correcta"]
        resultado = "✓ Correcta" if es_correcta else "✗ Incorrecta"
        resultados_detallados.append(resultado)
        
        respuestas_para_correo.append({
            'correcta': es_correcta,
            'resultado': resultado,
            'respuesta_usuario': st.session_state.respuestas[i] or 'No respondida',
            'respuesta_correcta': pregunta_data["respuesta_correcta"]
        })

        with st.expander(f"Pregunta {i+1}: {resultado}"):
            st.write(f"**Tu respuesta**: {st.session_state.respuestas[i] or 'No respondida'}")
            st.write(f"**Respuesta correcta**: {pregunta_data['respuesta_correcta']}")

    # SOLO ENVÍO DE CORREO AL ESTUDIANTE - SIN NOTIFICACIÓN AL ADMINISTRADOR
    if CONFIG.EMAIL_CONFIGURED:
        with st.spinner("Enviando resultados por correo..."):
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

    resultados = {
        "Pregunta": [pregunta["pregunta"] for pregunta in preguntas],
        "Tu respuesta": st.session_state.respuestas,
        "Respuesta correcta": respuestas_correctas,
        "Resultado": resultados_detallados
    }

    df_resultados = pd.DataFrame(resultados)

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
    st.title("🤖 Evaluación de la Semana 2")
    
    if not CONFIG.EMAIL_CONFIGURED:
        st.warning("⚠️ La funcionalidad de correo no está configurada. Los resultados se guardarán pero no se enviarán por correo.")
    
    if 'examen_iniciado' not in st.session_state:
        st.session_state.examen_iniciado = False
    if 'respuestas' not in st.session_state:
        st.session_state.respuestas = [None] * len(preguntas)
    
    with st.sidebar:
        st.header("Estado del Sistema")
        
        with st.spinner("Probando conexión..."):
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
    
    if 'archivo_inicializado' not in st.session_state:
        with st.spinner("Inicializando sistema..."):
            if inicializar_archivo_calificaciones():
                st.session_state.archivo_inicializado = True
            else:
                st.error("No se pudo inicializar el sistema. Contacta al administrador.")
                return
    
    if not st.session_state.examen_iniciado:
        numero_economico, nombre_completo, email, info_valida = show_student_info_form()
        
        if info_valida:
            st.session_state.numero_economico = numero_economico
            st.session_state.nombre_completo = nombre_completo
            st.session_state.email = email
            st.session_state.examen_iniciado = True
            st.session_state.respuestas = [None] * len(preguntas)
            st.rerun()
    else:
        st.sidebar.write("---")
        st.sidebar.subheader("Estudiante:")
        st.sidebar.write(f"**Nombre**: {st.session_state.nombre_completo}")
        st.sidebar.write(f"**Número Económico**: {st.session_state.numero_economico}")
        st.sidebar.write(f"**Email**: {st.session_state.email}")
        
        all_answered = show_exam_interface()
        
        col1, col2 = st.columns([1, 2])
        
        with col1:
            if st.button("Reiniciar Examen", type="secondary", use_container_width=True):
                reset_exam()
                return
        
        with col2:
            if st.button("Enviar Examen", type="primary", disabled=not all_answered, use_container_width=True):
                if not all_answered:
                    st.error("Por favor, responde todas las preguntas antes de enviar el examen.")
                    return
                    
                calificacion, respuestas_correctas = calculate_grade()
                
                with st.spinner("Procesando resultados..."):
                    if guardar_calificacion(
                        st.session_state.numero_economico,
                        st.session_state.nombre_completo,
                        st.session_state.email,
                        calificacion
                    ):
                        show_results(calificacion, respuestas_correctas)
                    else:
                        st.error("Error al guardar la calificación. Contacta al administrador.")

try:
    if __name__ == "__main__":
        main()
except Exception as e:
    st.error(f"Error crítico en la aplicación: {str(e)}")
finally:
    SSHManager.cleanup()
