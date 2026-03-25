import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

# ==========================================
# CALCUAMZ v4.3.8 - TARGET PRICE LOGIC
# ==========================================

st.set_page_config(layout="wide", page_title="CalcuAMZ v4.3.8", page_icon="📦")

COLS_MAESTRAS = ['SKU', 'PRODUCTO', 'COSTO USD', 'AMAZON', 'ENVIO', '% FEE', 'TIPO CAMBIO']

def conectar():
    try:
        info = st.secrets["gcp_service_account"]
        creds = Credentials.from_service_account_info(info, scopes=["https://www.googleapis.com/auth/spreadsheets"])
        return gspread.authorize(creds).open_by_key("1mF-9Ayv95PJmk4v8PrIDHf2-lRnHFZd5WOxQ__cb3Ss").sheet1
    except: return None

def calcular_detallado(r):
    try:
        c_usd = pd.to_numeric(r.get('COSTO USD', 0), errors='coerce') or 0.0
        p_amz = pd.to_numeric(r.get('AMAZON', 0), errors='coerce') or 0.0
        p_fee = pd.to_numeric(r.get('% FEE', 10.0), errors='coerce') or 10.0
        env = pd.to_numeric(r.get('ENVIO', 0), errors='coerce') or 0.0
        t_c = pd.to_numeric(r.get('TIPO CAMBIO', 18.50), errors='coerce') or 18.50
        
        costo_mxn = float(c_usd) * float(t_c)
        fee_decimal = float(p_fee) / 100
        
        # --- CÁLCULO ACTUAL ---
        dinero_fee = p_amz * fee_decimal
        base_grav = p_amz / 1.16
        ret_iva, ret_isr = base_grav * 0.08, base_grav * 0.025
        neto = p_amz - dinero_fee - abs(float(env)) - ret_iva - ret_isr
        utilidad = neto - costo_mxn
        margen = (utilidad / neto) * 100 if neto > 0 else 0

        # --- CÁLCULO PRECIO OBJETIVO (MARGEN 10%) ---
        # Fórmula despejada considerando Retenciones (10.5%) y Fee
        # Precio = (Costo_MXN + Envío) / (1 - Fee - 0.105/1.16 - Margen_Deseado)
        target_m = 0.10 
        divisor = (1 - fee_decimal - (0.105 / 1.16) - target_m)
        precio_10 = (costo_mxn + abs(float(env))) / divisor if divisor > 0 else 0
        
        return pd.Series([costo_mxn, dinero_fee, ret_iva, ret_isr, neto, utilidad, margen, precio_10])
    except: return pd.Series([0,0,0,0,0,0,0,0])

# --- LÓGICA DE INTERFAZ (RESUMIDA PARA BREVEDAD) ---
# ... (Mantener bloques de Seguridad y Conexión de la v4.3.5) ...

ws = conectar()
if ws:
    raw_data = ws.get_all_values()
    if raw_data and raw_data[0][0].upper() == 'SKU':
        df_raw = pd.DataFrame(raw_data[1:], columns=raw_data[0])
        for col in ['COSTO USD', 'AMAZON', 'ENVIO', '% FEE', 'TIPO CAMBIO']:
            df_raw[col] = pd.to_numeric(df_raw[col], errors='coerce').fillna(0.0)

        if not df_raw.empty:
            calc_res = df_raw.apply(calcular_detallado, axis=1)
            calc_res.columns = ['C_MX', 'F_$', 'IVA', 'ISR', 'NETO', 'UTIL', 'MARGEN', 'PRECIO_10']
            df_full = pd.concat([df_raw, calc_res], axis=1)
            
            st.title("📊 Master Dashboard v4.3.8")
            
            # --- TABLA CON PRECIO SUGERIDO ---
            st.subheader("Análisis de Precios e Ideal 10%")
            df_viz = df_full.copy()
            df_viz = df_viz[['SKU', 'PRODUCTO', 'AMAZON', 'MARGEN', 'PRECIO_10', 'UTIL']]
            
            # Formateo
            df_viz.columns = ['SKU', 'PRODUCTO', 'PRECIO ACTUAL', 'MARGEN %', 'PRECIO IDEAL (10%)', 'GANANCIA $']
            st.dataframe(df_viz.style.format({
                'PRECIO ACTUAL': "${:,.2f}",
                'PRECIO IDEAL (10%)': "${:,.2f}",
                'GANANCIA $': "${:,.2f}",
                'MARGEN %': "{:.2f}%"
            }), use_container_width=True)

# ... (Mantener resto de pestañas de Nuevo/Editar/Bulk de la v4.3.5) ...
