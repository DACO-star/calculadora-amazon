import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import io
from fpdf import FPDF

# ==========================================
# CALCUAMZ v4.2.6 - ANTI-EMPTY CELL SHIELD
# ==========================================

st.set_page_config(layout="wide", page_title="CalcuAMZ v4.2.6", page_icon="📦")

st.markdown("""
    <style>
    .stApp { background-color: #0e1117; }
    .stMetric { background-color: #1e2130; padding: 20px; border-radius: 12px; border-left: 5px solid #a65d00; }
    div[data-testid="stForm"] { background-color: #161b22; border: 1px solid #30363d; border-radius: 15px; padding: 25px; }
    </style>
    """, unsafe_allow_html=True)

def conectar():
    try:
        info = st.secrets["gcp_service_account"]
        creds = Credentials.from_service_account_info(info, scopes=["https://www.googleapis.com/auth/spreadsheets"])
        return gspread.authorize(creds).open_by_key("1mF-9Ayv95PJmk4v8PrIDHf2-lRnHFZd5WOxQ__cb3Ss").sheet1
    except: return None

def calcular_detallado(r):
    try:
        # Convertimos a float y si falla o es NaN, usamos 0.0
        def to_f(val):
            try: return float(val) if str(val).strip() != "" else 0.0
            except: return 0.0

        c_usd = to_f(r.get('COSTO USD', 0))
        p_amz = to_f(r.get('AMAZON', 0))
        p_fee = to_f(r.get('% FEE', 10.0))
        env = to_f(r.get('ENVIO', 0))
        t_c = to_f(r.get('TIPO CAMBIO', 18.00))
        
        costo_mxn = c_usd * t_c
        dinero_fee = p_amz * (p_fee / 100)
        base_grav = p_amz / 1.16
        ret_iva, ret_isr = base_grav * 0.08, base_grav * 0.025
        neto = p_amz - dinero_fee - abs(env) - ret_iva - ret_isr
        utilidad = neto - costo_mxn
        margen = (utilidad / neto) * 100 if neto > 0 else 0
        return pd.Series([costo_mxn, dinero_fee, ret_iva, ret_isr, neto, utilidad, margen])
    except: return pd.Series([0,0,0,0,0,0,0])

def estilo_filas(row):
    estilos = [''] * len(row)
    if 'MARGEN %' in row.index:
        val = row['MARGEN %']
        idx = row.index.get_loc('MARGEN %')
        bg = '#551a1a' if val <= 6.0 else ('#5e541e' if val <= 8.0 else '#1a4d1a')
        estilos[idx] = f'background-color: {bg}; color: white; font-weight: bold;'
    return estilos

# --- SEGURIDAD ---
USUARIOS = {"admin": "amazon123", "dav": "ventas2026", "dax": "amazon2026", "cesar": "ventas789"}
if 'auth' not in st.session_state: st.session_state.auth = False

if not st.session_state.auth:
    st.title("🔐 Acceso CalcuAMZ")
    c1, c2 = st.columns(2)
    u = c1.text_input("Usuario").lower().strip()
    p = c2.text_input("Password", type="password")
    if st.button("Entrar"):
        if u in USUARIOS and USUARIOS[u] == p:
            st.session_state.auth = True; st.session_state.user = u; st.rerun()
else:
    with st.sidebar:
        try: st.image("500x500LOGODACO.png", width=150)
        except: st.subheader("📦 DACOCEL")
        st.divider()
        st.write(f"Usuario: **{st.session_state.user.upper()}**")
        if st.button("Cerrar Sesión"): st.session_state.auth = False; st.rerun()

    ws = conectar()
    if ws is None: st.error("Error Sheets"); st.stop()
    
    # Leemos todos los valores y forzamos limpieza de columnas
    data = ws.get_all_records()
    if not data:
        st.info("Base de datos vacía.")
        df_raw = pd.DataFrame()
    else:
        df_raw = pd.DataFrame(data)
        df_raw.columns = [str(c).upper().strip() for c in df_raw.columns]
        
        # Limpieza global de valores no numéricos
        for col in ['COSTO USD', 'AMAZON', 'ENVIO', '% FEE', 'TIPO CAMBIO']:
            if col in df_raw.columns:
                df_raw[col] = pd.to_numeric(df_raw[col], errors='coerce').fillna(0.0)

        calc_p = df_raw.apply(calcular_detallado, axis=1)
        calc_p.columns = ['C_MX', 'F_$', 'IVA', 'ISR', 'NETO', 'UTIL', 'MARGEN']
        df_full = pd.concat([df_raw, calc_p], axis=1)

        st.title("📊 Master Dashboard v4.2.6")
        st.divider()

        t1, t2, t3 = st.tabs(["➕ Nuevo", "✏️ Editar", "📂 Bulk"])
        
        with t1:
            with st.form("f_new"):
                st.subheader("Registrar Producto")
                sk_in = st.text_input("SKU").upper().strip()
                no_in = st.text_input("Nombre (OBLIGATORIO)").upper().strip()
                c1, c2, c3, c4, c5 = st.columns(5)
                cos, pre, env_in, fee_in, tc_in = c1.number_input("Costo USD"), c2.number_input("Precio AMZ"), c3.number_input("Envío"), c4.number_input("% Fee", 10.0), c5.number_input("TC", 18.50)
                if st.form_submit_button("🚀 Guardar"):
                    if no_in:
                        ws.append_row([sk_in if sk_in else f"M-{len(df_raw)+1}", no_in, cos, pre, env_in, fee_in, tc_in])
                        st.rerun()

        with t2:
            opciones = (df_raw['SKU'].astype(str) + " - " + df_raw['PRODUCTO']).tolist()
            sel = st.selectbox("Selecciona para editar:", opciones)
            sku_sel = str(sel).split(" - ")[0]
            idx = df_raw[df_raw['SKU'].astype(str) == sku_sel].index[0]
            curr = df_raw.iloc[idx]
            
            with st.form("f_edit"):
                enom = st.text_input("Nombre", value=str(curr.get('PRODUCTO', '')))
                ce1, ce2, ce3, ce4, ce5 = st.columns(5)
                # El truco: si curr['AMAZON'] es NaN o vacío, float() no fallará gracias a to_numeric arriba
                ecos = ce1.number_input("Costo USD", value=float(curr.get('COSTO USD', 0.0)))
                epre = ce2.number_input("Precio AMZ", value=float(curr.get('AMAZON', 0.0)))
                eenv = ce3.number_input("Envío", value=float(curr.get('ENVIO', 0.0)))
                efee = ce4.number_input("% Fee", value=float(curr.get('% FEE', 10.0)))
                etc = ce5.number_input("TC", value=float(curr.get('TIPO CAMBIO', 18.50)))
                if st.form_submit_button("💾 Actualizar"):
                    ws.update(f'A{idx+2}:G{idx+2}', [[sku_sel, enom.upper(), ecos, epre, eenv, efee, etc]])
                    st.rerun()
            if st.button("🗑️ Eliminar"): ws.delete_rows(int(idx + 2)); st.rerun()

        with t3:
            f_bulk = st.file_uploader("Subir Excel", type=['xlsx', 'csv'])
            if f_bulk and st.button("🚀 Cargar"):
                df_b = pd.read_excel(f_bulk) if f_bulk.name.endswith('xlsx') else pd.read_csv(f_bulk)
                ws.append_rows(df_b.values.tolist())
                st.rerun()

        st.divider()
        df_final = df_full.copy()
        df_final.columns = ['SKU', 'PRODUCTO', 'COSTO USD', 'AMAZON', 'ENVIO', '% FEE', 'TC', 'C_MXN', 'F_$', 'IVA', 'ISR', 'NETO', 'UTILIDAD', 'MARGEN %']
        fmt = {c: "${:,.2f}" for c in ['COSTO USD', 'AMAZON', 'ENVIO', 'TC', 'C_MXN', 'F_$', 'IVA', 'ISR', 'NETO', 'UTILIDAD']}
        fmt.update({'MARGEN %': "{:.2f}%", '% FEE': "{:.2f}%"})
        st.write("### M - Listado Maestro")
        st.dataframe(df_final.style.format(fmt).apply(estilo_filas, axis=1), use_container_width=True, height=600, hide_index=True)
