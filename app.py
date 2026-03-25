import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import io
from fpdf import FPDF

# ==========================================
# CALCUAMZ v4.3.0 - REPORTE PDF + T3 + AUTO
# ==========================================

st.set_page_config(layout="wide", page_title="CalcuAMZ v4.3.0", page_icon="📦")

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
        p_amz_orig = clean(r.get('AMAZON', 0))
        p_fee = clean(r.get('% FEE', 4.0))
        env = clean(r.get('ENVIO', 80.0))
        t_c = clean(r.get('TIPO CAMBIO', 18.00))
        
        costo_mxn = c_usd * t_c
        fee_decimal = p_fee / 100

        if p_amz_orig <= 0:
            # Cálculo para margen del 10% neto
            divisor = (1 - fee_decimal - (0.105 / 1.16) - 0.10)
            p_amz = (costo_mxn + abs(env)) / divisor if divisor > 0 else 0
        else:
            p_amz = p_amz_orig

        dinero_fee = p_amz * fee_decimal
        base_grav = p_amz / 1.16
        ret_iva, ret_isr = base_grav * 0.08, base_grav * 0.025
        neto = p_amz - dinero_fee - abs(env) - ret_iva - ret_isr
        utilidad = neto - costo_mxn
        margen = (utilidad / neto) * 100 if neto > 0 else 0
        
        return pd.Series([p_amz, costo_mxn, dinero_fee, ret_iva, ret_isr, neto, utilidad, margen])
    except: return pd.Series([0,0,0,0,0,0,0,0])

def generar_pdf(df):
    pdf = FPDF(orientation='L', unit='mm', format='A4')
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 10, "REPORTE MAESTRO DE INVENTARIO - DACOCEL", ln=True, align='C')
    pdf.set_font("Arial", '', 10)
    pdf.cell(0, 10, f"Generado por: {st.session_state.user.upper()}", ln=True, align='C')
    pdf.ln(5)
    
    # Encabezados
    pdf.set_fill_color(30, 30, 30)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Arial", 'B', 8)
    cols = [('SKU', 25), ('PRODUCTO', 75), ('COSTO USD', 25), ('AMAZON', 25), ('NETO', 25), ('UTILIDAD', 25), ('MARGEN', 25)]
    for txt, w in cols:
        pdf.cell(w, 10, txt, 1, 0, 'C', True)
    pdf.ln()
    
    # Datos
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Arial", '', 7)
    for _, r in df.iterrows():
        pdf.cell(25, 8, str(r['SKU']), 1)
        pdf.cell(75, 8, str(r['PRODUCTO'])[:45], 1)
        pdf.cell(25, 8, f"${r['COSTO USD']:,.2f}", 1)
        pdf.cell(25, 8, f"${r['AMAZON']:,.2f}", 1)
        pdf.cell(25, 8, f"${r['NETO']:,.2f}", 1)
        pdf.cell(25, 8, f"${r['UTILIDAD']:,.2f}", 1)
        pdf.cell(25, 8, f"{r['MARGEN %']:.2f}%", 1)
        pdf.ln()
    return pdf.output(dest='S').encode('latin-1', 'ignore')

# --- LÓGICA DE INTERFAZ ---
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
        calc = df_raw.apply(calcular_detallado, axis=1)
        calc.columns = ['AMZ_F', 'C_MX', 'F_$', 'IVA', 'ISR', 'NETO', 'UTIL', 'MARGEN']
        df_full = pd.concat([df_raw, calc], axis=1)
        df_full['AMAZON'] = df_full.apply(lambda x: x['AMZ_F'] if clean(x['AMAZON']) <= 0 else clean(x['AMAZON']), axis=1)

    st.title("📊 Dacocel Master Dashboard v4.3.0")
    
    t1, t2, t3 = st.tabs(["➕ Nuevo", "✏️ Editar", "📂 Bulk"])

    with t1:
        with st.form("f_new"):
            st.subheader("Nuevo Registro")
            sk, nom = st.text_input("SKU"), st.text_input("Nombre")
            c1, c2, c3, c4, c5 = st.columns(5)
            cos = c1.number_input("Costo USD")
            pre = c2.number_input("Precio AMZ (0=Auto)", value=0.0)
            env = c3.number_input("Envío", value=80.0)
            fee = c4.number_input("% Fee", value=4.0)
            tc = c5.number_input("TC", value=18.0)
            if st.form_submit_button("Guardar"):
                ws.append_row([sk, nom.upper(), cos, pre, env, fee, tc])
                st.rerun()

    with t2:
        if not df_raw.empty:
            opcs = (df_raw['SKU'].astype(str) + " - " + df_raw['PRODUCTO']).tolist()
            sel = st.selectbox("Seleccionar:", opcs)
            sku_s = str(sel).split(" - ")[0]
            idx = df_raw[df_raw['SKU'].astype(str) == sku_s].index[0]
            with st.form("f_edit"):
                enom = st.text_input("Nombre", value=str(df_raw.iloc[idx]['PRODUCTO']))
                if st.form_submit_button("Actualizar"):
                    ws.update(f'B{idx+2}', [[enom.upper()]])
                    st.rerun()

    with t3:
        st.subheader("Carga Masiva")
        f_bulk = st.file_uploader("Subir Excel", type=['xlsx'])
        if f_bulk and st.button("🚀 Subir"):
            df_b = pd.read_excel(f_bulk)
            ws.append_rows(df_b.values.tolist())
            st.rerun()

    st.divider()
    if not df_raw.empty:
        df_final = df_full[['SKU', 'PRODUCTO', 'COSTO USD', 'AMAZON', 'NETO', 'UTIL', 'MARGEN']].copy()
        df_final.columns = ['SKU', 'PRODUCTO', 'COSTO USD', 'AMAZON', 'NETO', 'UTILIDAD', 'MARGEN %']
        
        col_btn1, col_btn2 = st.columns([3, 1])
        with col_btn2:
            if st.button("📄 Generar PDF del Inventario", use_container_width=True):
                pdf_bytes = generar_pdf(df_final)
                st.download_button("⬇️ Descargar PDF", pdf_bytes, "reporte_dacocel.pdf", "application/pdf")
        
        st.dataframe(df_final.style.format({"COSTO USD": "${:,.2f}", "AMAZON": "${:,.2f}", "NETO": "${:,.2f}", "UTILIDAD": "${:,.2f}", "MARGEN %": "{:.2f}%"}), use_container_width=True, hide_index=True)
