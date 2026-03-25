import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import io
from fpdf import FPDF

# ==========================================
# CALCUAMZ v4.0 - PROFESSIONAL DESIGN
# ==========================================

st.set_page_config(layout="wide", page_title="CalcuAMZ v4.0", page_icon="📦")

# --- INYECCIÓN DE ESTILO PROFESIONAL ---
st.markdown("""
    <style>
    /* Fondo y contenedores */
    .stApp { background-color: #0e1117; }
    .stMetric { 
        background-color: #1e2130; 
        padding: 20px; 
        border-radius: 12px; 
        border-left: 5px solid #a65d00;
        box-shadow: 2px 2px 10px rgba(0,0,0,0.3);
    }
    /* Estilo para pestañas y formularios */
    .stTabs [data-baseweb="tab-list"] { gap: 10px; }
    .stTabs [data-baseweb="tab"] {
        background-color: #1e2130;
        border-radius: 8px 8px 0px 0px;
        padding: 10px 20px;
        color: white;
    }
    div[data-testid="stForm"] {
        background-color: #161b22;
        border: 1px solid #30363d;
        border-radius: 15px;
        padding: 25px;
    }
    /* Botones principales */
    .stButton>button {
        border-radius: 8px;
        transition: 0.3s;
        font-weight: bold;
    }
    .stButton>button:hover {
        transform: scale(1.02);
        box-shadow: 0px 0px 15px rgba(166, 93, 0, 0.4);
    }
    </style>
    """, unsafe_allow_html=True)

# --- FUNCIONES CORE ---
def conectar():
    try:
        info = st.secrets["gcp_service_account"]
        creds = Credentials.from_service_account_info(info, scopes=["https://www.googleapis.com/auth/spreadsheets"])
        return gspread.authorize(creds).open_by_key("1mF-9Ayv95PJmk4v8PrIDHf2-lRnHFZd5WOxQ__cb3Ss").sheet1
    except: return None

def calcular_detallado(r):
    try:
        c_usd, p_amz = float(r.get('COSTO USD', 0)), float(r.get('AMAZON', 0))
        p_fee, env = float(r.get('% FEE', 10.0)), float(r.get('ENVIO', 0))
        t_c = float(r.get('TIPO CAMBIO', 18.00))
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
        if val <= 6.0: bg = '#551a1a'
        elif 6.1 <= val <= 8.0: bg = '#5e541e'
        else: bg = '#1a4d1a'
        estilos[idx] = f'background-color: {bg}; color: white; font-weight: bold;'
    if 'AMAZON' in row.index:
        estilos[row.index.get_loc('AMAZON')] = 'color: #fca311; font-weight: bold;'
    return estilos

# --- LÓGICA DE USUARIO ---
USUARIOS = {"admin": "amazon123", "dav": "ventas2026", "dax": "amazon2026", "cesar": "ventas789", "consulta": "lector2026"}
if 'auth' not in st.session_state: st.session_state.auth = False

if not st.session_state.auth:
    st.title("🔐 Acceso CalcuAMZ v4.0")
    c1, c2 = st.columns(2)
    u = c1.text_input("Usuario").lower().strip()
    p = c2.text_input("Password", type="password")
    if st.button("Entrar"):
        if u in USUARIOS and USUARIOS[u] == p:
            st.session_state.auth = True; st.session_state.user = u; st.rerun()
else:
    ws = conectar()
    if ws is None: st.error("Fallo de conexión"); st.stop()
    df_raw = pd.DataFrame(ws.get_all_records())
    if not df_raw.empty: df_raw.columns = [str(c).upper().strip() for c in df_raw.columns]

    es_editor = st.session_state.user in ["admin", "dav", "dax", "cesar"]

    st.title("📦 Dacocel Dashboard v4.0")

    # --- MÉTRICAS DE CABECERA ---
    if not df_raw.empty:
        calc_pre = df_raw.apply(calcular_detallado, axis=1)
        calc_pre.columns = ['C_MX', 'FEE_$', 'IVA', 'ISR', 'NETO', 'UTIL', 'MARGEN']
        df_full_pre = pd.concat([df_raw, calc_pre], axis=1)
        
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total Productos", len(df_raw))
        m2.metric("Margen Promedio", f"{df_full_pre['MARGEN'].mean():.2f}%")
        m3.metric("Más Rentable", f"{df_full_pre['MARGEN'].max():.1f}%")
        en_riesgo = len(df_full_pre[df_full_pre['MARGEN'] < 6])
        m4.metric("Alerta Margen Bajo", en_riesgo, delta="- Riesgo" if en_riesgo > 0 else "OK", delta_color="inverse")

    st.divider()

    # --- GESTIÓN ---
    if es_editor:
        t1, t2, t3 = st.tabs(["➕ Registro Individual", "✏️ Editor Maestro", "📂 Carga Bulk"])
        
        with t1:
            with st.form("f_new"):
                st.subheader("Añadir Nuevo SKU")
                sk = st.text_input("SKU").upper()
                no = st.text_input("Nombre Modelo")
                c1, c2, c3, c4 = st.columns(4)
                cos = c1.number_input("Costo USD", format="%.2f")
                pre = c2.number_input("Venta Amazon", format="%.2f")
                fee = c3.number_input("% Fee", value=10.0)
                tc = c4.number_input("TC", value=18.50)
                if st.form_submit_button("🚀 Registrar en Base de Datos"):
                    ws.append_row([sk, no.upper(), cos, pre, 0, fee, tc])
                    st.rerun()

        with t2:
            if not df_raw.empty:
                opciones = df_raw['SKU'].astype(str) + " - " + df_raw['PRODUCTO']
                sel = st.selectbox("Buscar Producto para modificar", opciones)
                idx = df_raw[df_raw['SKU'].astype(str) == sel.split(" - ")[0]].index[0]
                curr = df_raw.iloc[idx]
                with st.form("f_edit"):
                    enom = st.text_input("Nombre", value=str(curr['PRODUCTO']))
                    e1, e2, e3, e4 = st.columns(4)
                    ecos = e1.number_input("Costo USD", value=float(curr['COSTO USD']))
                    epre = e2.number_input("Precio", value=float(curr['AMAZON']))
                    efee = e3.number_input("% Fee", value=float(curr.get('% FEE', 10.0)))
                    etc = e4.number_input("TC", value=float(curr.get('TIPO CAMBIO', 18.0)))
                    if st.form_submit_button("💾 Guardar Cambios"):
                        ws.update(f'A{idx+2}:G{idx+2}', [[curr['SKU'], enom.upper(), ecos, epre, curr['ENVIO'], efee, etc]])
                        st.rerun()
                if st.button("🗑️ Eliminar Producto", type="primary"):
                    ws.delete_rows(int(idx + 2)); st.rerun()

    st.divider()

    # --- VISTA DE DATOS ---
    if not df_raw.empty:
        c_bus, c_pdf = st.columns([3, 1])
        busq = c_bus.text_input("🔍 Filtro rápido (SKU o Nombre)").upper()
        
        df_f = df_full_pre.copy()
        df_f.columns = ['SKU', 'PRODUCTO', 'COSTO USD', 'AMAZON', 'ENVIO', '% FEE', 'TIPO CAMBIO', 'COSTO MXN', 'FEE $', 'RET IVA', 'RET ISR', 'NETO RECIBIDO', 'UTILIDAD', 'MARGEN %']
        
        if busq:
            df_f = df_f[df_f['SKU'].astype(str).str.contains(busq) | df_f['PRODUCTO'].astype(str).str.contains(busq)]

        if c_pdf.button("📄 Exportar PDF"):
            st.info("Generando reporte...") # Aquí podrías llamar a la función generar_pdf definida arriba

        fmt = {c: "${:,.2f}" for c in ['COSTO USD', 'AMAZON', 'COSTO MXN', 'FEE $', 'RET IVA', 'RET ISR', 'NETO RECIBIDO', 'UTILIDAD']}
        fmt.update({'MARGEN %': "{:.2f}%", '% FEE': "{:.2f}%"})

        st.dataframe(
            df_f.style.format(fmt, na_rep="-").apply(estilo_filas, axis=1),
            use_container_width=True, height=600, hide_index=True
        )
