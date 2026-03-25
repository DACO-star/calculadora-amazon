import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import io
from fpdf import FPDF

# ==========================================
# CALCUAMZ v4.1 - MASTER EDITION (SR.SICHO)
# ==========================================

st.set_page_config(layout="wide", page_title="CalcuAMZ v4.1", page_icon="📦")

# --- INYECCIÓN DE ESTILO PROFESIONAL (CSS) ---
st.markdown("""
    <style>
    .stApp { background-color: #0e1117; }
    .stMetric { 
        background-color: #1e2130; 
        padding: 20px; 
        border-radius: 12px; 
        border-left: 5px solid #a65d00;
        box-shadow: 2px 2px 10px rgba(0,0,0,0.3);
    }
    div[data-testid="stForm"] {
        background-color: #161b22;
        border: 1px solid #30363d;
        border-radius: 15px;
        padding: 25px;
    }
    .stButton>button {
        border-radius: 8px;
        transition: 0.3s;
        font-weight: bold;
    }
    .stButton>button:hover {
        transform: scale(1.02);
        box-shadow: 0px 0px 15px rgba(166, 93, 0, 0.4);
    }
    /* Estilo para la tabla */
    [data-testid="stDataFrame"] {
        border: 1px solid #30363d;
        border-radius: 10px;
    }
    </style>
    """, unsafe_allow_html=True)

# --- FUNCIONES DE CONEXIÓN Y CÁLCULO ---
def conectar():
    try:
        info = st.secrets["gcp_service_account"]
        creds = Credentials.from_service_account_info(info, scopes=["https://www.googleapis.com/auth/spreadsheets"])
        return gspread.authorize(creds).open_by_key("1mF-9Ayv95PJmk4v8PrIDHf2-lRnHFZd5WOxQ__cb3Ss").sheet1
    except: return None

def calcular_detallado(r):
    try:
        c_usd = float(r.get('COSTO USD', 0))
        p_amz = float(r.get('AMAZON', 0))
        p_fee = float(r.get('% FEE', 10.0))
        env = float(r.get('ENVIO', 0))
        t_c = float(r.get('TIPO CAMBIO', 18.00))
        
        costo_mxn = c_usd * t_c
        dinero_fee = p_amz * (p_fee / 100)
        base_gravable = p_amz / 1.16
        ret_iva = base_gravable * 0.08
        ret_isr = base_gravable * 0.025
        
        neto = p_amz - dinero_fee - abs(env) - ret_iva - ret_isr
        utilidad = neto - costo_mxn
        margen = (utilidad / neto) * 100 if neto > 0 else 0
        
        return pd.Series([costo_mxn, dinero_fee, ret_iva, ret_isr, neto, utilidad, margen])
    except: return pd.Series([0,0,0,0,0,0,0])

def estilo_filas(row):
    estilos = [''] * len(row)
    if 'MARGEN %' in row.index:
        val = row['MARGEN %']
        idx_margen = row.index.get_loc('MARGEN %')
        if val <= 6.0: bg = '#551a1a'
        elif 6.1 <= val <= 8.0: bg = '#5e541e'
        else: bg = '#1a4d1a'
        estilos[idx_margen] = f'background-color: {bg}; color: white; font-weight: bold;'
    if 'AMAZON' in row.index:
        estilos[row.index.get_loc('AMAZON')] = 'color: #fca311; font-weight: bold;'
    return estilos

def generar_pdf(df):
    pdf = FPDF(orientation='L', unit='mm', format='A4')
    pdf.add_page()
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(0, 10, "Reporte de Inventario - CalcuAMZ v4.1", ln=True, align='C')
    pdf.ln(5)
    pdf.set_font("Arial", 'B', 8)
    headers = ['SKU', 'PRODUCTO', 'COSTO USD', 'AMAZON', 'UTILIDAD', 'MARGEN %']
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
        pdf.cell(widths[4], 8, f"${row['UTILIDAD']:,.2f}", 1)
        pdf.cell(widths[5], 8, f"{row['MARGEN %']:.2f}%", 1)
        pdf.ln()
    return pdf.output(dest='S').encode('latin-1')

# --- AUTENTICACIÓN ---
USUARIOS = {"admin": "amazon123", "dav": "ventas2026", "dax": "amazon2026", "cesar": "ventas789", "consulta": "lector2026"}
if 'auth' not in st.session_state: st.session_state.auth = False

if not st.session_state.auth:
    st.title("🔐 Acceso CalcuAMZ v4.1")
    c1, c2 = st.columns(2)
    u = c1.text_input("Usuario").lower().strip()
    p = c2.text_input("Password", type="password")
    if st.button("Entrar al Panel"):
        if u in USUARIOS and USUARIOS[u] == p:
            st.session_state.auth = True; st.session_state.user = u; st.rerun()
        else: st.error("Credenciales incorrectas")
else:
    ws = conectar()
    if ws is None: st.error("Error de conexión con Google Sheets"); st.stop()
    
    df_raw = pd.DataFrame(ws.get_all_records())
    if not df_raw.empty:
        df_raw.columns = [str(c).upper().strip() for c in df_raw.columns]

    es_editor = st.session_state.user in ["admin", "dav", "dax", "cesar"]

    with st.sidebar:
        st.title("🛠️ Configuración")
        st.write(f"Conectado: **{st.session_state.user.upper()}**")
        if st.button("Cerrar Sesión"):
            st.session_state.auth = False; st.rerun()

    st.title("📦 Dacocel Dashboard v4.1")

    # --- MÉTRICAS DE CABECERA (KPIs) ---
    if not df_raw.empty:
        calc_pre = df_raw.apply(calcular_detallado, axis=1)
        calc_pre.columns = ['C_MX', 'FEE_$', 'IVA', 'ISR', 'NETO', 'UTIL', 'MARGEN']
        df_full_pre = pd.concat([df_raw, calc_pre], axis=1)
        
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total Productos", len(df_raw))
        m2.metric("Margen Promedio", f"{df_full_pre['MARGEN'].mean():.2f}%")
        m3.metric("Utilidad Total Est.", f"${df_full_pre['UTIL'].sum():,.2f}")
        en_riesgo = len(df_full_pre[df_full_pre['MARGEN'] < 6])
        m4.metric("Riesgo (Bajo 6%)", en_riesgo, delta="- Alerta" if en_riesgo > 0 else "OK", delta_color="inverse")

    st.divider()

    # --- PESTAÑAS DE GESTIÓN ---
    if es_editor:
        t1, t2, t3 = st.tabs(["➕ Nuevo Registro", "✏️ Editar / Borrar", "📂 Carga Bulk"])
        
        with t1:
            with st.form("f_new"):
                st.subheader("Registrar Nuevo Producto")
                sk = st.text_input("SKU").upper()
                no = st.text_input("Nombre del Producto")
                c1, c2, c3, c4 = st.columns(4)
                cos = c1.number_input("Costo USD", format="%.2f")
                pre = c2.number_input("Precio Amazon", format="%.2f")
                fee = c3.number_input("% Fee Amazon", value=10.0)
                tc = c4.number_input("T. Cambio", value=18.50)
                if st.form_submit_button("🚀 Guardar en Base de Datos"):
                    ws.append_row([sk, no.upper(), cos, pre, 0, fee, tc])
                    st.success("Guardado exitosamente"); st.rerun()

        with t2:
            if not df_raw.empty:
                sel = st.selectbox("Seleccionar SKU", df_raw['SKU'].astype(str) + " - " + df_raw['PRODUCTO'])
                idx = df_raw[df_raw['SKU'].astype(str) == sel.split(" - ")[0]].index[0]
                curr = df_raw.iloc[idx]
                with st.form("f_edit"):
                    enom = st.text_input("Nombre", value=str(curr['PRODUCTO']))
                    e1, e2, e3, e4 = st.columns(4)
                    ecos = e1.number_input("Costo USD", value=float(curr['COSTO USD']))
                    epre = e2.number_input("Precio Amazon", value=float(curr['AMAZON']))
                    efee = e3.number_input("% Fee", value=float(curr.get('% FEE', 10.0)))
                    etc = e4.number_input("TC", value=float(curr.get('TIPO CAMBIO', 18.0)))
                    if st.form_submit_button("💾 Actualizar"):
                        ws.update(f'A{idx+2}:G{idx+2}', [[curr['SKU'], enom.upper(), ecos, epre, curr['ENVIO'], efee, etc]])
                        st.rerun()
                if st.button("🗑️ Eliminar permanentemente", type="primary"):
                    ws.delete_rows(int(idx + 2)); st.rerun()

        with t3:
            st.subheader("Procesamiento Bulk")
            cb1, cb2 = st.columns(2)
            plant_buf = io.BytesIO()
            with pd.ExcelWriter(plant_buf, engine='xlsxwriter') as wr:
                pd.DataFrame(columns=['SKU', 'PRODUCTO', 'COSTO USD', '% FEE', 'ENVIO']).to_excel(wr, index=False)
            cb1.download_button("📥 Descargar Plantilla", plant_buf.getvalue(), "plantilla_dacocel.xlsx")
            tc_bulk = cb2.number_input("TC para Bulk", value=18.50)
            f_bulk = st.file_uploader("Subir Excel", type=['xlsx', 'csv'])
            if f_bulk and st.button("🚀 Iniciar Carga"):
                df_b = pd.read_excel(f_bulk) if f_bulk.name.endswith('xlsx') else pd.read_csv(f_bulk)
                st.info("Cargando datos a Google Sheets...") # Lógica simplificada

    st.divider()

    # --- TABLA DE RESULTADOS (VISTA FINAL) ---
    if not df_raw.empty:
        c_bus, c_pdf = st.columns([3, 1])
        busq = c_bus.text_input("🔍 Buscar por SKU o Nombre...").upper()
        
        df_f = df_full_pre.copy()
        df_f.columns = ['SKU', 'PRODUCTO', 'COSTO USD', 'AMAZON', 'ENVIO', '% FEE', 'TIPO CAMBIO', 'COSTO MXN', 'FEE $', 'RET IVA', 'RET ISR', 'NETO RECIBIDO', 'UTILIDAD', 'MARGEN %']
        
        if busq:
            df_f = df_f[df_f['SKU'].astype(str).str.contains(busq) | df_f['PRODUCTO'].astype(str).str.contains(busq)]

        if c_pdf.button("📄 Generar Reporte PDF"):
            pdf_data = generar_pdf(df_f)
            st.download_button("⬇️ Descargar Reporte", pdf_data, "reporte_sicho.pdf")

        # --- FORMATO DE MONEDA CORREGIDO ---
        mon_cols = [
            'COSTO USD', 'AMAZON', 'ENVIO', 'TIPO CAMBIO', 
            'COSTO MXN', 'FEE $', 'RET IVA', 'RET ISR', 
            'NETO RECIBIDO', 'UTILIDAD'
        ]
        
        fmt = {c: "${:,.2f}" for c in mon_cols if c in df_f.columns}
        fmt.update({'MARGEN %': "{:.2f}%", '% FEE': "{:.2f}%"})

        st.dataframe(
            df_f.style.format(fmt, na_rep="-").apply(estilo_filas, axis=1),
            use_container_width=True, height=1900, hide_index=True
        )
