import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

# CONFIGURACIÓN
USUARIOS = {"admin": "amazon123", "socio": "ventas2026"}

def conectar():
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], 
                                                 scopes=["https://www.googleapis.com/auth/spreadsheets"])
    return gspread.authorize(creds).open_by_key("1mF-9Ayv95PJmk4v8PrIDHf2-lRnHFZd5WOxQ__cb3Ss").sheet1

def calcular(r):
    c_usd = float(r.get('COSTO USD', 0))
    p_amz = float(r.get('AMAZON', 0))
    p_fee = float(r.get('% FEE', 0))
    env = float(r.get('ENVIO', 0))
    costo_mxn = c_usd * 18.0
    quedan = p_amz - (p_amz * p_fee/100) - abs(env) - (p_amz/1.16 * 0.105)
    return pd.Series([costo_mxn, quedan - costo_mxn])

# LOGIN
if 'auth' not in st.session_state: st.session_state.auth = False

if not st.session_state.auth:
    st.title("🔐 Acceso")
    u = st.text_input("Usuario")
    p = st.text_input("Clave", type="password")
    if st.button("Entrar"):
        if u in USUARIOS and USUARIOS[u] == p:
            st.session_state.auth = True
            st.rerun()
else:
    # CARGA DE DATOS
    try:
        ws = conectar()
        df = pd.DataFrame(ws.get_all_records())
        if not df.empty:
            df.columns = [str(c).strip().upper() for c in df.columns]
    except:
        st.error("Error conectando a la base de datos.")
        st.stop()

    st.title("📦 Gestión Inventario")
    
    t1, t2 = st.tabs(["➕ Añadir", "✏️ Editar"])
    
    with t1:
        with st.form("add"):
            sku = st.text_input("SKU")
            nom = st.text_input("Nombre")
            c_u = st.number_input("Costo USD", format="%.2f")
            p_a = st.number_input("Precio MXN", format="%.2f")
            if st.form_submit_button("Guardar"):
                ws.append_row([sku.upper(), nom.upper(), c_u, p_a, 0, 10])
                st.rerun()

    with t2:
        if not df.empty:
            ops = df['SKU'].astype(str) + " - " + df['PRODUCTO'].astype(str)
            sel = st.selectbox("Producto", ops)
            idx = df[df['SKU'].astype(str) == sel.split(" - ")[0]].index[0]
            if st.button("Eliminar Producto"):
                ws.delete_rows(int(idx + 2))
                st.rerun()

    st.divider()
    if not df.empty:
        res = df.apply(calcular, axis=1)
        res.columns = ['COSTO MXN', 'UTILIDAD']
        st.dataframe(pd.concat([df, res], axis=1), use_container_width=True)
