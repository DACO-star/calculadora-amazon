import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

# --- CalcuAMZ ver 1.2 (RESTAURADA) ---
st.set_page_config(layout="wide", page_title="CalcuAMZ ver 1.2")

USUARIOS = {
    "admin": "amazon123", "dav": "ventas2026",
    "dax": "amazon2026", "cesar": "ventas789"
}
TIPO_CAMBIO = 18.00

def conectar():
    info = st.secrets["gcp_service_account"]
    creds = Credentials.from_service_account_info(info, scopes=["https://www.googleapis.com/auth/spreadsheets"])
    return gspread.authorize(creds).open_by_key("1mF-9Ayv95PJmk4v8PrIDHf2-lRnHFZd5WOxQ__cb3Ss").sheet1

def calcular_detallado(r):
    c_usd = float(r.get('COSTO USD', 0))
    p_amz = float(r.get('AMAZON', 0))
    p_fee = float(r.get('% FEE', 0))
    env = float(r.get('ENVIO', 0))
    
    costo_mxn = c_usd * TIPO_CAMBIO
    dinero_fee = p_amz * (p_fee / 100)
    base_gravable = p_amz / 1.16
    ret_iva = base_gravable * 0.08
    ret_isr = base_gravable * 0.025
    
    neto = p_amz - dinero_fee - abs(env) - ret_iva - ret_isr
    utilidad = neto - costo_mxn
    
    # REGRESAMOS A: Margen sobre el NETO RECIBIDO (Tu versión favorita)
    margen = (utilidad / neto) * 100 if neto > 0 else 0
    
    return pd.Series([costo_mxn, dinero_fee, ret_iva, ret_isr, neto, utilidad, margen])

if 'auth' not in st.session_state: st.session_state.auth = False

if not st.session_state.auth:
    st.title("🔐 Acceso - CalcuAMZ")
    u = st.text_input("Usuario").lower().strip()
    p = st.text_input("Clave", type="password")
    if st.button("Ingresar"):
        if u in USUARIOS and USUARIOS[u] == p:
            st.session_state.auth = True; st.session_state.user = u
            st.rerun()
        else: st.error("Error de acceso")
else:
    with st.sidebar:
        st.write(f"👤: **{st.session_state.user.upper()}**")
        if st.button("Cerrar Sesión"): 
            st.session_state.auth = False; st.rerun()
    
    try:
        ws = conectar(); df_raw = pd.DataFrame(ws.get_all_records())
        if not df_raw.empty: df_raw.columns = [str(c).strip().upper() for c in df_raw.columns]
    except: st.error("Error de conexión"); st.stop()

    st.title("📦 Gestión de Inventario")
    t1, t2 = st.tabs(["➕ Agregar con Asistente", "✏️ Editar / Borrar"])

    with t1:
        st.subheader("Asistente de Precio Objetivo (Garantizar 10% sobre Venta)")
        with st.form("nuevo"):
            c1, c2, c3 = st.columns(3)
            sk = c1.text_input("SKU")
            no = c2.text_input("Nombre Producto")
            fe_input = c3.number_input("% Fee Amazon", value=10.0, step=0.5)
            
            c_usd_in = c1.number_input("Costo Producto (USD)", format="%.2f", step=1.0)
            env_in = c2.number_input("Envío FBA (MXN)", format="%.2f", step=5.0)
            
            p_sugerido = 0.0
            if c_usd_in > 0:
                costo_mx = c_usd_in * TIPO_CAMBIO
                tax_factor = (0.08 + 0.025) / 1.16
                divisor = 1 - (fe_input/100) - tax_factor - 0.10
                p_sugerido = (costo_mx + env_in) / divisor
            
            pr = c3.number_input("Precio Venta Final (MXN)", value=float(p_sugerido), format="%.2f")
            
            if st.form_submit_button("Guardar Producto"):
                if sk and no and pr > 0:
                    ws.append_row([sk.upper(), no.upper(), c_usd_in, pr, env_in, fe_input])
                    st.success(f"¡Guardado con éxito!")
                    st.rerun()

    with t2:
        if not df_raw.empty:
            ops = df_raw['SKU'].astype(str) + " - " + df_raw['PRODUCTO'].astype(str)
            sel = st.selectbox("Selecciona producto", ops)
            sku_sel = sel.split(" - ")[0]
            idx = df_raw[df_raw['SKU'].astype(str) == sku_sel].index[0]
            curr = df_raw.iloc[idx]
            with st.form("edit"):
                ce1, ce2 = st.columns(2)
                enom = ce1.text_input("Nombre", value=str(curr['PRODUCTO']))
                ecos = ce2.number_input("Costo USD", value=float(curr['COSTO USD']), format="%.2f")
                epre = ce1.number_input("Precio MXN", value=float(curr['AMAZON']), format="%.2f")
                efee = ce2.number_input("% Fee", value=float(curr['% FEE']), format="%.2f")
                eenv = ce1.number_input("Envío FBA", value=float(curr['ENVIO']), format="%.2f")
                if st.form_submit_button("Actualizar"):
                    ws.update(range_name=f'A{idx+2}:F{idx+2}', values=[[sku_sel, enom.upper(), ecos, epre, eenv, efee]])
                    st.rerun()
            if st.
