import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import io
from fpdf import FPDF

# ==========================================
# CALCUAMZ v4.2.1 - FULL RESTORE (SR.SICHO)
# ==========================================

st.set_page_config(layout="wide", page_title="CalcuAMZ v4.2.1", page_icon="📦")

# Nombres exactos que el código usará para identificar tus datos
COLS_MAESTRAS = ['SKU', 'PRODUCTO', 'COSTO USD', 'AMAZON', 'ENVIO', '% FEE', 'TIPO CAMBIO']

# --- ESTILO VISUAL ---
st.markdown("""
    <style>
    .stApp { background-color: #0e1117; }
    .stMetric { 
        background-color: #1e2130; 
        padding: 20px; 
        border-radius: 12px; 
        border-left: 5px solid #a65d00;
    }
    div[data-testid="stForm"] {
        background-color: #161b22;
        border: 1px solid #30363d;
        border-radius: 15px;
        padding: 25px;
    }
    .stButton>button { border-radius: 8px; font-weight: bold; }
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
        c_usd, p_amz = float(r['COSTO USD']), float(r['AMAZON'])
        p_fee, env = float(r['% FEE']), float(r['ENVIO'])
        t_c = float(r['TIPO CAMBIO'])
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

def generar_pdf(df):
    pdf = FPDF(orientation='L', unit='mm', format='A4')
    pdf.add_page()
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(0, 10, "Reporte Maestro de Inventario - Dacocel", ln=True, align='C')
    pdf.ln(5)
    pdf.set_font("Arial", 'B', 8)
    headers = ['SKU', 'PRODUCTO', 'COSTO USD', 'AMAZON', 'ENVIO', 'MARGEN %']
    widths = [30, 90, 25, 25, 25, 25]
    for i, h in enumerate(headers):
        pdf.cell(widths[i], 10, h, 1, 0, 'C')
    pdf.ln()
    pdf.set_font("Arial", '', 7)
    for _, row in df.iterrows():
        pdf.cell(widths[0], 8, str(row['SKU']), 1)
        pdf.cell(widths[1], 8, str(row['PRODUCTO'])[:50], 1)
        pdf.cell(widths[2], 8, f"${float(row['COSTO USD']):,.2f}", 1)
        pdf.cell(widths[3], 8, f"${float(row['AMAZON']):,.2f}", 1)
        pdf.cell(widths[4], 8, f"${float(row['ENVIO']):,.2f}", 1)
        pdf.cell(widths[5], 8, f"{float(row['MARGEN %']):.2f}%", 1)
        pdf.ln()
    return pdf.output(dest='S').encode('latin-1')

# --- ACCESO ---
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
    if ws is None: st.error("Error Sheets"); st.stop()
    
    # --- PARCHE DE LECTURA FORZADA ---
    data_raw = ws.get_all_values()
    if len(data_raw) <= 1:
        st.info("La base de datos está vacía. Registra tu primer producto.")
        df_raw = pd.DataFrame(columns=COLS_MAESTRAS)
    else:
        # Forzamos los nombres de columnas basados en COLS_MAESTRAS
        df_raw = pd.DataFrame(data_raw[1:], columns=COLS_MAESTRAS)
        for col in ['COSTO USD', 'AMAZON', 'ENVIO', '% FEE', 'TIPO CAMBIO']:
            df_raw[col] = pd.to_numeric(df_raw[col], errors='coerce').fillna(0.0)

    st.title("📦 Dacocel Dashboard v4.2.1")

    if not df_raw.empty:
        calc_p = df_raw.apply(calcular_detallado, axis=1)
        calc_p.columns = ['C_MX', 'F_$', 'IVA', 'ISR', 'NETO', 'UTIL', 'MARGEN']
        df_full = pd.concat([df_raw, calc_p], axis=1)
        m1, m2 = st.columns(2)
        m1.metric("Total Productos", len(df_raw))
        m2.metric("Margen Promedio", f"{df_full['MARGEN'].mean():.2f}%")

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
                if not no_in: st.error("Falta el nombre")
                else:
                    ws.append_row([sk_in if sk_in else f"M-{len(df_raw)+1}", no_in, cos, pre, env_in, fee_in, tc_in])
                    st.rerun()

    with t2:
        if not df_raw.empty:
            sel = st.selectbox("Elegir:", df_raw['SKU'].astype(str) + " - " + df_raw['PRODUCTO'])
            idx = df_raw[df_raw['SKU'].astype(str) == sel.split(" - ")[0]].index[0]
            curr = df_raw.iloc[idx]
            with st.form("f_edit"):
                enom = st.text_input("Nombre", value=str(curr['PRODUCTO']))
                ce1, ce2, ce3, ce4, ce5 = st.columns(5)
                ecos, epre, eenv, efee, etc = ce1.number_input("Costo", value=float(curr['COSTO USD'])), ce2.number_input("Precio", value=float(curr['AMAZON'])), ce3.number_input("Envío", value=float(curr['ENVIO'])), ce4.number_input("Fee", value=float(curr['% FEE'])), ce5.number_input("TC", value=float(curr['TIPO CAMBIO']))
                if st.form_submit_button("💾 Actualizar"):
                    ws.update(f'A{idx+2}:G{idx+2}', [[curr['SKU'], enom.upper(), ecos, epre, eenv, efee, etc]])
                    st.rerun()
            if st.button("🗑️ Eliminar"): ws.delete_rows(int(idx + 2)); st.rerun()

    with t3:
        f_bulk = st.file_uploader("Subir Excel", type=['xlsx', 'csv'])
        if f_bulk and st.button("🚀 Cargar"):
            df_b = pd.read_excel(f_bulk) if f_bulk.name.endswith('xlsx') else pd.read_csv(f_bulk)
            ws.append_rows(df_b.values.tolist())
            st.rerun()

    if not df_raw.empty:
        st.divider()
        busq = st.text_input("🔍 Buscar...").upper()
        if st.button("📄 Generar PDF"):
            pdf_data = generar_pdf(df_full.rename(columns={'MARGEN': 'MARGEN %'}))
            st.download_button("⬇️ Descargar", pdf_data, "reporte.pdf")
        
        df_f = df_full.copy()
        df_f.columns = ['SKU', 'PRODUCTO', 'COSTO USD', 'AMAZON', 'ENVIO', '% FEE', 'TC', 'C_MXN', 'F_$', 'IVA', 'ISR', 'NETO', 'UTILIDAD', 'MARGEN %']
        if busq: df_f = df_f[df_f['SKU'].astype(str).str.contains(busq) | df_f['PRODUCTO'].astype(str).str.contains(busq)]
        
        fmt = {c: "${:,.2f}" for c in ['COSTO USD', 'AMAZON', 'ENVIO', 'TC', 'C_MXN', 'F_$', 'IVA', 'ISR', 'NETO', 'UTILIDAD']}
        fmt.update({'MARGEN %': "{:.2f}%", '% FEE': "{:.2f}%"})
        st.dataframe(df_f.style.format(fmt).apply(estilo_filas, axis=1), use_container_width=True, height=600, hide_index=True)
