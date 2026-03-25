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
        pdf.cell(widths[2], 8, f"${row['COSTO USD']:,.2f}", 1)
        pdf.cell(widths[3], 8, f"${row['AMAZON']:,.2f}", 1)
        pdf.cell(widths[4], 8, f"${row['ENVIO']:,.2f}", 1)
        pdf.cell(widths[5], 8, f"{row['MARGEN %']:.2f}%", 1)
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
            st.session_state.auth = True; st.session_state.user = u; st.rerun()
else:
    ws = conectar()
    if ws is None: st.error("Error Sheets"); st.stop()
    df_raw = pd.DataFrame(ws.get_all_records())
    if not df_raw.empty: df_raw.columns = [str(c).upper().strip() for c in df_raw.columns]

    st.title("📦 Dacocel Dashboard v4.2.1")

    # --- MÉTRICAS ---
    if not df_raw.empty:
        calc_p = df_raw.apply(calcular_detallado, axis=1)
        calc_p.columns = ['C_MX', 'F_$', 'IVA', 'ISR', 'NETO', 'UTIL', 'MARGEN']
        df_full = pd.concat([df_raw, calc_p], axis=1)
        m1, m2 = st.columns(2)
        m1.metric("Total Productos", len(df_raw))
        m2.metric("Margen Promedio", f"{df_full['MARGEN'].mean():.2f}%")

    st.divider()

    # --- GESTIÓN ---
    t1, t2, t3 = st.tabs(["➕ Nuevo Registro", "✏️ Editar / Borrar", "📂 Carga Bulk"])
    
    with t1:
        with st.form("f_new"):
            st.subheader("Registrar Producto")
            sk_in = st.text_input("SKU (Auto-generar si vacío)").upper().strip()
            no_in = st.text_input("Nombre del Producto (OBLIGATORIO)").upper().strip()
            c1, c2, c3, c4, c5 = st.columns(5)
            cos = c1.number_input("Costo USD", format="%.2f")
            pre = c2.number_input("Precio AMZ", format="%.2f")
            env_in = c3.number_input("Envío (MXN)", format="%.2f")
            fee_in = c4.number_input("% Fee", value=10.0)
            tc_in = c5.number_input("TC", value=18.50)
            if st.form_submit_button("🚀 Guardar"):
                if not no_in: st.error("El nombre es obligatorio.")
                else:
                    sk_final = sk_in if sk_in else f"AUTO-{len(df_raw)+1}"
                    ws.append_row([sk_final, no_in, cos, pre, env_in, fee_in, tc_in])
                    st.rerun()

    with t2:
        if not df_raw.empty:
            sel = st.selectbox("Elegir SKU", df_raw['SKU'].astype(str) + " - " + df_raw['PRODUCTO'])
            idx = df_raw[df_raw['SKU'].astype(str) == sel.split(" - ")[0]].index[0]
            curr = df_raw.iloc[idx]
            with st.form("f_edit"):
                enom = st.text_input("Nombre", value=str(curr['PRODUCTO']))
                ce1, ce2, ce3, ce4, ce5 = st.columns(5)
                ecos = ce1.number_input("Costo USD", value=float(curr['COSTO USD']))
                epre = ce2.number_input("Precio AMZ", value=float(curr['AMAZON']))
                eenv = ce3.number_input("Envío", value=float(curr.get('ENVIO', 0.0)))
                efee = ce4.number_input("% Fee", value=float(curr.get('% FEE', 10.0)))
                etc = ce5.number_input("TC", value=float(curr.get('TIPO CAMBIO', 18.50)))
                if st.form_submit_button("💾 Actualizar"):
                    ws.update(f'A{idx+2}:G{idx+2}', [[curr['SKU'], enom.upper(), ecos, epre, eenv, efee, etc]])
                    st.rerun()
            if st.button("🗑️ Eliminar"): ws.delete_rows(int(idx + 2)); st.rerun()

    with t3:
        st.subheader("Carga Masiva")
        cb1, cb2 = st.columns(2)
        # --- DESCARGAR PLANTILLA ---
        plant_buf = io.BytesIO()
        with pd.ExcelWriter(plant_buf, engine='xlsxwriter') as wr:
            pd.DataFrame(columns=['SKU', 'PRODUCTO', 'COSTO USD', 'AMAZON', 'ENVIO', '% FEE', 'TIPO CAMBIO']).to_excel(wr, index=False)
        cb1.download_button("📥 Descargar Plantilla Excel", plant_buf.getvalue(), "plantilla_bulk.xlsx")
        # --- SUBIR ARCHIVO ---
        f_bulk = st.file_uploader("Subir Archivo", type=['xlsx', 'csv'])
        if f_bulk and st.button("🚀 Ejecutar Carga Masiva"):
            df_b = pd.read_excel(f_bulk) if f_bulk.name.endswith('xlsx') else pd.read_csv(f_bulk)
            df_b.columns = [str(c).upper().strip() for c in df_b.columns]
            ws.append_rows(df_b.values.tolist())
            st.success("¡Carga exitosa!"); st.rerun()

    st.divider()

    # --- TABLA M ---
    if not df_raw.empty:
        c_bus, c_pdf = st.columns([3, 1])
        busq = c_bus.text_input("🔍 Buscar...").upper()
        if c_pdf.button("📄 Generar Reporte PDF"):
            pdf_data = generar_pdf(df_full)
            st.download_button("⬇️ Descargar PDF", pdf_data, "reporte_dacocel.pdf")

        df_f = df_full.copy()
        df_f.columns = ['SKU', 'PRODUCTO', 'COSTO USD', 'AMAZON', 'ENVIO', '% FEE', 'TC', 'C_MXN', 'F_$', 'IVA', 'ISR', 'NETO', 'UTILIDAD', 'MARGEN %']
        if busq: df_f = df_f[df_f['SKU'].astype(str).str.contains(busq) | df_f['PRODUCTO'].astype(str).str.contains(busq)]

        fmt = {c: "${:,.2f}" for c in ['COSTO USD', 'AMAZON', 'ENVIO', 'TC', 'C_MXN', 'F_$', 'IVA', 'ISR', 'NETO', 'UTILIDAD']}
        fmt.update({'MARGEN %': "{:.2f}%", '% FEE': "{:.2f}%"})

        st.write("### M - Listado Maestro")
        st.dataframe(df_f.style.format(fmt).apply(estilo_filas, axis=1), use_container_width=True, height=1900, hide_index=True)

