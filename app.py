import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import io

# ==========================================
# CALCUAMZ v4.3.8 - FIXED AUTO-PRICE 10.00%
# ==========================================

st.set_page_config(layout="wide", page_title="CalcuAMZ v4.3.8", page_icon="📦")

def conectar():
    try:
        info = st.secrets["gcp_service_account"]
        creds = Credentials.from_service_account_info(info, scopes=["https://www.googleapis.com/auth/spreadsheets"])
        return gspread.authorize(creds).open_by_key("1mF-9Ayv95PJmk4v8PrIDHf2-lRnHFZd5WOxQ__cb3Ss").sheet1
    except: return None

def clean(val, def_val=0.0):
    try:
        if pd.isna(val) or str(val).strip() == "": return def_val
        v = str(val).replace('$', '').replace(',', '').strip()
        return float(v)
    except: return def_val

def calcular_detallado(r):
    try:
        c_usd = clean(r.get('COSTO USD', 0))
        p_amz_input = clean(r.get('AMAZON', 0))
        p_fee_pct = clean(r.get('% FEE', 4.0))
        env = clean(r.get('ENVIO', 80.0))
        t_c = clean(r.get('TIPO CAMBIO', 18.00))
        
        costo_mxn = c_usd * t_c
        fee_dec = p_fee_pct / 100
        const_ret = 0.09051724  # (0.08 + 0.025) / 1.16
        
        # --- LÓGICA DE AUTO-PRECIO PARA MARGEN 10.00% NETO ---
        # Si el margen es 10% sobre el Neto, entonces Costo = 90% del Neto.
        # Neto Objetivo = Costo / 0.90
        # Precio = (Neto Objetivo + Envio) / (1 - Fee - Retenciones)
        if p_amz_input <= 0:
            neto_objetivo = costo_mxn / 0.90
            p_amz = (neto_objetivo + env) / (1 - fee_dec - const_ret)
        else:
            p_amz = p_amz_input

        # Cálculos de salida
        dinero_fee = p_amz * fee_dec
        base_grav = p_amz / 1.16
        ret_iva, ret_isr = base_grav * 0.08, base_grav * 0.025
        neto_recibido = p_amz - dinero_fee - env - ret_iva - ret_isr
        utilidad = neto_recibido - costo_mxn
        
        # Margen real sobre lo que entra a la cuenta (Neto)
        margen = (utilidad / neto_recibido) * 100 if neto_recibido > 0 else 0
        
        return pd.Series([p_amz, costo_mxn, dinero_fee, ret_iva, ret_isr, neto_recibido, utilidad, margen])
    except: return pd.Series([0.0]*8)

def estilo_semaforo(row):
    estilos = [''] * len(row)
    if 'MARGEN %' in row.index:
        val = row['MARGEN %']
        idx = row.index.get_loc('MARGEN %')
        # Verde solo si estamos en el 10% o más
        bg = '#551a1a' if val < 7.0 else ('#5e541e' if val < 9.9 else '#1a4d1a')
        estilos[idx] = f'background-color: {bg}; color: white; font-weight: bold;'
    return estilos

# --- LOGIN ---
USUARIOS = {"admin": "amazon123", "dav": "ventas2026", "dax": "amazon2026", "cesar": "ventas789"}
if 'auth' not in st.session_state: st.session_state.auth = False

if not st.session_state.auth:
    st.title("🔐 Acceso CalcuAMZ")
    u = st.text_input("Usuario").lower().strip()
    p = st.text_input("Password", type="password")
    if st.button("Entrar"):
        if u in USUARIOS and USUARIOS[u] == p:
            st.session_state.auth, st.session_state.user = True, u; st.rerun()
else:
    ws = conectar()
    data = ws.get_all_records() if ws else []
    df_raw = pd.DataFrame(data) if data else pd.DataFrame()

    if not df_raw.empty:
        df_raw.columns = [str(c).upper().strip() for c in df_raw.columns]
        
        # PROCESAMIENTO DE CÁLCULOS
        calc = df_raw.apply(calcular_detallado, axis=1)
        calc.columns = ['AMZ_P', 'C_MXN_V', 'FEE_V', 'IVA_V', 'ISR_V', 'NETO_V', 'UTIL_V', 'MARG_V']
        df_full = pd.concat([df_raw, calc], axis=1)

    st.title("📊 Dacocel Master Dashboard v4.3.8")
    
    t1, t2, t3 = st.tabs(["➕ Nuevo", "✏️ Editar", "📂 Bulk"])

    # ... [Pestañas Nuevo y Editar sin cambios] ...

    with t3:
        st.subheader("Configuración de Plantilla")
        tc_p = st.number_input("Tipo de Cambio para la descarga:", value=18.0, step=0.01)
        plantilla = pd.DataFrame({'SKU':['M-X'],'PRODUCTO':['NOM'],'COSTO USD':[0.0],'AMAZON':[0.0],'ENVIO':[80.0],'% FEE':[4.0],'TIPO CAMBIO':[tc_p]})
        buf = io.BytesIO()
        with pd.ExcelWriter(buf) as wr: plantilla.to_excel(wr, index=False)
        st.download_button(f"📥 Bajar Plantilla TC {tc_p}", buf.getvalue(), "plantilla.xlsx")
        archivo = st.file_uploader("Subir Excel", type=['xlsx'])
        if archivo and st.button("🚀 Procesar"):
            ws.append_rows(pd.read_excel(archivo).values.tolist()); st.rerun()

    st.divider()
    if not df_raw.empty:
        # CONSTRUCCIÓN DE LA TABLA FINAL CON NOMBRES CORRECTOS
        df_final = df_full[['SKU', 'PRODUCTO', 'COSTO USD', 'AMZ_P', 'ENVIO', '% FEE', 'TIPO CAMBIO', 'C_MXN_V', 'FEE_V', 'IVA_V', 'ISR_V', 'NETO_V', 'UTIL_V', 'MARG_V']].copy()
        df_final.columns = ['SKU', 'PRODUCTO', 'COSTO USD', 'AMAZON', 'ENVIO', '% FEE', 'TC', 'C_MXN', 'F_$', 'IVA', 'ISR', 'NETO', 'UTILIDAD', 'MARGEN %']
        
        formateo = {
            "COSTO USD": "${:,.2f}", "AMAZON": "${:,.2f}", "ENVIO": "${:,.2f}", "TC": "${:,.2f}", 
            "C_MXN": "${:,.2f}", "F_$": "${:,.2f}", "IVA": "${:,.2f}", "ISR": "${:,.2f}", 
            "NETO": "${:,.2f}", "UTILIDAD": "${:,.2f}", "MARGEN %": "{:.2f}%", "% FEE": "{:.2f}%"
        }
        st.dataframe(df_final.style.format(formateo).apply(estilo_semaforo, axis=1), use_container_width=True, height=600, hide_index=True)
