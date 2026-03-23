import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

# --- 1. CONFIGURACIÓN ---
USUARIOS = {
    "admin": "amazon123", 
    "cesar": "ventas2026",
    "fidel": "amazon2026",  # Usuario extra 1
}
TIPO_CAMBIO = 18.00

def conectar():
    info = st.secrets["gcp_service_account"]
    scope = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials.from_service_account_info(info, scopes=scope)
    return gspread.authorize(creds).open_by_key("1mF-9Ayv95PJmk4v8PrIDHf2-lRnHFZd5WOxQ__cb3Ss").sheet1

def calcular_detallado(r):
    # Recuperamos todos los datos del Excel
    c_usd = float(r.get('COSTO USD', 0))
    p_amz = float(r.get('AMAZON', 0))
    p_fee = float(r.get('% FEE', 0))
    env = float(r.get('ENVIO', 0))

    # Cálculos detallados (Funcionalidad recuperada)
    costo_mxn = c_usd * TIPO_CAMBIO
    dinero_fee = p_amz * (p_fee / 100)
    base_gravable = p_amz / 1.16
    ret_iva = base_gravable * 0.08
    ret_isr = base_gravable * 0.025
    
    neto = p_amz - dinero_fee - abs(env) - ret_iva - ret_isr
    utilidad = neto - costo_mxn
    margen = (utilidad / neto) * 100 if neto > 0 else 0
    
    return pd.Series([costo_mxn, dinero_fee, ret_iva, ret_isr, neto, utilidad, margen])

# --- 2. LOGIN ---
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
    # --- 3. DATOS ---
    try:
        ws = conectar()
        df_raw = pd.DataFrame(ws.get_all_records())
        if not df_raw.empty:
            df_raw.columns = [str(c).strip().upper() for c in df_raw.columns]
    except Exception as e:
        st.error(f"Error de conexión: {e}")
        st.stop()

    st.title("📦 Calculadora Amazon Pro")
    t1, t2 = st.tabs(["➕ Agregar", "✏️ Editar / Borrar"])

    with t1:
        with st.form("nuevo"):
            c1, c2 = st.columns(2)
            sk = c1.text_input("SKU")
            no = c2.text_input("Producto")
            co = c1.number_input("Costo USD", format="%.2f", step=1.0)
            pr = c2.number_input("Precio Amazon MXN", format="%.2f", step=10.0)
            fe = c1.number_input("% Fee", value=10.0, step=0.5)
            en = c2.number_input("Envío FBA MXN", format="%.2f", step=5.0)
            if st.form_submit_button("Guardar Producto"):
                if sk and no:
                    ws.append_row([sk.upper(), no.upper(), co, pr, en, fe])
                    st.success("¡Guardado!")
                    st.rerun()

    with t2:
        if not df_raw.empty:
            ops = df_raw['SKU'].astype(str) + " - " + df_raw['PRODUCTO'].astype(str)
            sel = st.selectbox("Selecciona Producto", ops)
            idx = df_raw[df_raw['SKU'].astype(str) == sel.split(" - ")[0]].index[0]
            curr = df_raw.iloc[idx]

            with st.form("edit"):
                # Recuperamos los campos de edición
                enom = st.text_input("Nombre", value=str(curr['PRODUCTO']))
                ecos = st.number_input("Costo USD", value=float(curr['COSTO USD']), format="%.2f")
                epre = st.number_input("Precio MXN", value=float(curr['AMAZON']), format="%.2f")
                efee = st.number_input("% Fee", value=float(curr['% FEE']), step=0.5)
                eenv = st.number_input("Envío FBA", value=float(curr['ENVIO']), format="%.2f")
                
                if st.form_submit_button("Actualizar"):
                    ws.update(range_name=f'A{idx+2}:F{idx+2}', 
                             values=[[curr['SKU'], enom.upper(), ecos, epre, eenv, efee]])
                    st.success("Actualizado")
                    st.rerun()
            
            if st.button("🗑️ Eliminar Producto"):
                ws.delete_rows(int(idx + 2))
                st.rerun()

    # --- 4. TABLA DE RENTABILIDAD COMPLETA ---
    st.divider()
    st.subheader("📊 Análisis de Rentabilidad")
    if not df_raw.empty:
        res = df_raw.apply(calcular_detallado, axis=1)
        res.columns = ['COSTO MXN', 'FEE $', 'RET IVA', 'RET ISR', 'NETO', 'UTILIDAD', 'MARGEN %']
        df_final = pd.concat([df_raw, res], axis=1)
        
        # Formato de dinero
        money = ['COSTO USD','AMAZON','ENVIO','COSTO MXN','FEE $','RET IVA','RET ISR','NETO','UTILIDAD']
        st.dataframe(df_final.style.format({c: "${:,.2f}" for c in money} | {"MARGEN %": "{:.2f}%"}), use_container_width=True)
