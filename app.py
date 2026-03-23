import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

# --- 1. CONFIGURACIÓN DE SEGURIDAD ---
USUARIOS_VALIDOS = {"admin": "amazon123", "socio": "ventas2026"}

# --- 2. CONEXIÓN A GOOGLE SHEETS ---
def conectar_google_sheets():
    # Usamos st.secrets para mayor seguridad en la nube
    info_claves = st.secrets["gcp_service_account"]
    scope = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials.from_service_account_info(info_claves, scopes=scope)
    cliente = gspread.authorize(creds)
    # ID de tu hoja de cálculo
    sheet_id = "1mF-9Ayv95PJmk4v8PrIDHf2-lRnHFZd5WOxQ__cb3Ss"
    sheet = cliente.open_by_key(sheet_id).sheet1
    return sheet

# --- 3. LÓGICA DE CÁLCULO DE RENTABILIDAD ---
TIPO_CAMBIO = 18.00

def calcular_valores(r):
    # .get ayuda a evitar errores si una columna falta temporalmente
    c_usd = float(r.get('COSTO USD', 0))
    p_amz = float(r.get('AMAZON', 0))
    p_fee = float(r.get('% FEE', 0))
    env = float(r.get('ENVIO', 0))

    costo_mxn = c_usd * TIPO_CAMBIO
    dinero_fee = p_amz * (p_fee / 100)
    base_gravable = p_amz / 1.16
    ret_iva = base_gravable * 0.08
    ret_isr = base_gravable * 0.025
    quedan = p_amz - dinero_fee - abs(env) - ret_iva - ret_isr
    utilidad = quedan - costo_mxn
    margen = (utilidad / quedan) * 100 if quedan > 0 else 0
    
    return pd.Series([costo_mxn, dinero_fee, base_gravable, ret_iva, ret_isr, quedan, utilidad, margen])

# --- 4. SISTEMA DE LOGIN ---
if 'autenticado' not in st.session_state:
    st.session_state.autenticado = False

if not st.session_state.autenticado:
    st.title("🔐 Acceso al Sistema")
    u = st.text_input("Usuario")
    p = st.text_input("Contraseña", type="password")
    if st.button("Ingresar"):
        if u in USUARIOS_VALIDOS and USUARIOS_VALIDOS[u] == p:
            st.session_state.autenticado = True
            st.rerun()
        else:
            st.error("Credenciales incorrectas")
else:
    # --- 5. CARGA Y LIMPIEZA DE DATOS ---
    try:
        gsheet = conectar_google_sheets()
        df_base = pd.DataFrame(gsheet.get_all_records())
        
        if not df_base.empty:
            # LIMPIEZA: Quitamos espacios vacíos y forzamos mayúsculas en títulos
            df_base.columns = [str(c).strip().upper() for c in df_base.columns]
    except Exception as e:
        st.error(f"Error de conexión con Google Sheets: {e}")
        st.stop()

    st.title("📦 Gestión de Inventario Amazon")

    tab1, tab2 = st.tabs(["➕ Agregar Producto", "✏️ Editar / Borrar"])

    #
