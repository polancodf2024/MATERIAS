# sistema_asistencia_carlos.py
import streamlit as st
import pandas as pd
from datetime import datetime, date
import time
from pathlib import Path

# Configuración móvil-friendly
st.set_page_config(
    page_title="Registro de Asistencia",
    page_icon="⏰",
    layout="centered"
)

# CSS para mejor experiencia
st.markdown("""
<style>
    .main > div {
        padding: 1rem;
    }
    .stButton > button {
        width: 100%;
        height: 3.5rem;
        font-size: 1.2rem;
        margin: 0.5rem 0;
    }
    .stTextInput > div > div > input {
        font-size: 1.1rem;
        height: 3rem;
    }
    .info-box {
        padding: 1.5rem;
        background-color: #e8f4fd;
        border-radius: 0.8rem;
        border: 2px solid #0078d4;
        margin: 1rem 0;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    .success-box {
        padding: 1.5rem;
        background-color: #d4edda;
        border-radius: 0.8rem;
        border: 2px solid #28a745;
        margin: 1rem 0;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    .header-text {
        color: #0078d4;
        text-align: center;
        margin-bottom: 1rem;
    }
</style>
""", unsafe_allow_html=True)

class SistemaAsistencia:
    def __init__(self):
        self.archivo_asistencia = f"asistencia_carlos_{date.today().strftime('%Y%m%d')}.csv"
        self.crear_archivo_si_no_existe()
    
    def crear_archivo_si_no_existe(self):
        """Crear archivo de asistencia si no existe"""
        if not Path(self.archivo_asistencia).exists():
            pd.DataFrame(columns=[
                'FECHA', 'HORA', 'NOMBRE_COMPLETO', 'PUESTO', 
                'TURNO', 'TIPO_REGISTRO', 'PASSWORD_USADA'
            ]).to_csv(self.archivo_asistencia, index=False)
    
    def verificar_password(self, password):
        """Verificar la contraseña única"""
        return password == "tt8plco8"
    
    def obtener_informacion_empleado(self):
        """Información fija"""
        return {
            'nombre_completo': 'Carlos Polanco',
            'puesto': 'Enfermera General',
            'turno': 'Vespertino (2:30 - 10:00)'
        }
    
    def registrar_asistencia(self, tipo_registro, password_usada):
        """Registrar la asistencia"""
        try:
            empleado = self.obtener_informacion_empleado()
            ahora = datetime.now()
            
            nuevo_registro = {
                'FECHA': ahora.strftime('%Y-%m-%d'),
                'HORA': ahora.strftime('%H:%M:%S'),
                'NOMBRE_COMPLETO': empleado['nombre_completo'],
                'PUESTO': empleado['puesto'],
                'TURNO': empleado['turno'],
                'TIPO_REGISTRO': tipo_registro,
                'PASSWORD_USADA': password_usada
            }
            
            df = pd.read_csv(self.archivo_asistencia)
            df = pd.concat([df, pd.DataFrame([nuevo_registro])], ignore_index=True)
            df.to_csv(self.archivo_asistencia, index=False)
            return True, nuevo_registro
        except Exception as e:
            return False, str(e)
    
    def obtener_tipo_registro(self):
        """Determinar si es entrada o salida basado en registros previos"""
        try:
            df = pd.read_csv(self.archivo_asistencia)
            if df.empty:
                return "ENTRADA"
            
            # Buscar registros de hoy
            hoy = date.today().strftime('%Y-%m-%d')
            registros_hoy = df[df['FECHA'] == hoy]
            
            if registros_hoy.empty:
                return "ENTRADA"
            
            # Si el último registro fue ENTRADA, ahora es SALIDA
            ultimo_registro = registros_hoy.iloc[-1]
            return "SALIDA" if ultimo_registro['TIPO_REGISTRO'] == "ENTRADA" else "ENTRADA"
            
        except:
            return "ENTRADA"
    
    def obtener_registros_hoy(self):
        """Obtener todos los registros de hoy"""
        try:
            df = pd.read_csv(self.archivo_asistencia)
            hoy = date.today().strftime('%Y-%m-%d')
            return df[df['FECHA'] == hoy]
        except:
            return pd.DataFrame()

def main():
    st.markdown('<h1 class="header-text">⏰ Sistema de Asistencia Personal</h1>', unsafe_allow_html=True)
    st.markdown("---")
    
    sistema = SistemaAsistencia()
    
    # Estado de la sesión
    if 'autenticado' not in st.session_state:
        st.session_state.autenticado = False
    
    if not st.session_state.autenticado:
        # PANTALLA DE ACCESO
        st.subheader("🔐 Acceso al Sistema")
        
        with st.form("acceso_form"):
            password = st.text_input(
                "**Contraseña de acceso:**", 
                type="password",
                placeholder="Ingresa tu contraseña única",
                help="Usa la contraseña asignada para registrar tu asistencia"
            )
            
            if st.form_submit_button("🎯 Verificar y Acceder", use_container_width=True):
                if password:
                    with st.spinner("Verificando acceso..."):
                        time.sleep(1)
                        if sistema.verificar_password(password):
                            st.session_state.autenticado = True
                            st.rerun()
                        else:
                            st.error("❌ Contraseña incorrecta. Intenta nuevamente.")
                else:
                    st.warning("📝 Ingresa tu contraseña para continuar")
    
    else:
        # PANTALLA PRINCIPAL - USUARIO AUTENTICADO
        empleado_info = sistema.obtener_informacion_empleado()
        tipo_registro = sistema.obtener_tipo_registro()
        
        # Mostrar información del empleado
        st.markdown(f"""
        <div class="info-box">
        <h3>👤 Información Personal</h3>
        <p><strong>Nombre completo:</strong> {empleado_info['nombre_completo']}</p>
        <p><strong>Puesto:</strong> {empleado_info['puesto']}</p>
        <p><strong>Turno asignado:</strong> {empleado_info['turno']}</p>
        <p><strong>Próximo registro:</strong> <span style='color: {"green" if tipo_registro == "ENTRADA" else "red"}; font-weight: bold;'>{tipo_registro}</span></p>
        </div>
        """, unsafe_allow_html=True)
        
        # Botón de registro
        col1, col2 = st.columns([3, 1])
        
        with col1:
            if st.button(
                f"✅ Registrar {tipo_registro}", 
                use_container_width=True,
                type="primary",
                help=f"Haz click para registrar tu {tipo_registro.lower()}"
            ):
                with st.spinner("Procesando registro..."):
                    time.sleep(1.5)
                    exito, resultado = sistema.registrar_asistencia(tipo_registro, "tt8plco8")
                    
                    if exito:
                        st.balloons()
                        st.markdown(f"""
                        <div class="success-box">
                        <h3>🎉 ¡Registro Exitoso!</h3>
                        <p><strong>Nombre:</strong> {resultado['NOMBRE_COMPLETO']}</p>
                        <p><strong>Puesto:</strong> {resultado['PUESTO']}</p>
                        <p><strong>Turno:</strong> {resultado['TURNO']}</p>
                        <p><strong>Tipo de registro:</strong> {resultado['TIPO_REGISTRO']}</p>
                        <p><strong>Fecha:</strong> {resultado['FECHA']}</p>
                        <p><strong>Hora exacta:</strong> {resultado['HORA']}</p>
                        <p><strong>Método:</strong> 📱 Sistema Web</p>
                        </div>
                        """, unsafe_allow_html=True)
                    else:
                        st.error(f"❌ Error al registrar: {resultado}")
        
        with col2:
            if st.button("🔄 Actualizar", use_container_width=True):
                st.rerun()
            
            if st.button("🚪 Salir", use_container_width=True):
                st.session_state.autenticado = False
                st.rerun()
        
        # Mostrar historial de registros de hoy
        st.markdown("---")
        st.subheader("📊 Mis Registros de Hoy")
        
        registros_hoy = sistema.obtener_registros_hoy()
        
        if not registros_hoy.empty:
            for _, registro in registros_hoy.iterrows():
                emoji = "🟢" if registro['TIPO_REGISTRO'] == "ENTRADA" else "🔴"
                st.write(f"{emoji} **{registro['HORA']}** - {registro['TIPO_REGISTRO']}")
            
            st.info(f"**Total de registros hoy:** {len(registros_hoy)}")
        else:
            st.write("ℹ️ Aún no tienes registros para hoy")
        
        # Información del sistema
        st.markdown("---")
        st.caption(f"🖥️ Sistema de Asistencia Personal • Última actualización: {datetime.now().strftime('%H:%M:%S')}")

if __name__ == "__main__":
    main()
