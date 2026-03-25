import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import io
from fpdf import FPDF

# ==========================================
# CALCUAMZ v3.0 - MASTER EDITION (SR.SICHO)
# ==========================================

st.set_page_config(layout="wide", page_title="CalcuAMZ v3.0", page_icon="📦")

# Configuración de Usuarios
USUARIOS = {
    "admin": "amazon123", "dav": "ventas2026",
    "dax": "amazon2026", "cesar": "ventas789",
    "consulta": "lector2026"
}

def conectar():
    info = st.secrets["gcp_service_account"]
    creds = Credentials.from_service_account_info(info, scopes=["https://www.googleapis.com/auth/spreadsheets"])
    return gspread.authorize(creds).open_by_key("1mF-9Ayv95PJmk4v8PrIDHf2-lRnHFZd5WOxQ__cb3Ss").sheet1

def calcular_precio_sugerido(costo_usd, fee_pct, envio_fba, t_cambio):
    if costo_usd <= 0: return 0.0
    costo_mx = costo_usd * t_cambio
    tax_factor = (0.08 + 0.025) / 1.16
    divisor = 1 - (fee_pct/100) - tax_factor
    return ((costo_mx * 1.1112) + envio_fba) / divisor

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
    except:
        return pd.Series([0,0,0,0,0,0,0])

def estilo_filas(row):
    estilos = [''] * len(row)
    if 'AMAZON' in row.index:
        idx_amz = row.index.get_loc('AMAZON')
        estilos[idx_amz] = 'background-color: #a65d00; color: white; font-weight: bold;'
    if 'MARGEN %' in row.index:
        val = row['MARGEN %']
        idx_margen = row.index.get_loc('MARGEN %')
        color_letra = 'color: #ff4b4b;' if val < 0 else 'color: white;'
        if val <= 6.0: bg = 'background-color: #551a1a;'
        elif 6.1 <= val <= 8.0: bg = 'background-color: #5e541e;'
        else: bg = 'background-color: #1a4d1a;'
        estilos[idx_margen] = f'{color_letra} {bg}'
    return estilos

def generar_pdf(df):
    pdf = FPDF(orientation='L', unit='mm', format='A4')
    pdf.add_page()
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(0, 10, "Reporte de Inventario y Margenes - CalcuAMZ v3.0", ln=True, align='C')
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

# --- LÓGICA DE SESIÓN ---
if 'auth' not in st.session_state: st.session_state.auth = False

if not st.session_state.auth:
    st.title("🔐 Acceso CalcuAMZ v3.0")
    col_l1, col_l2 = st.columns(2)
    u = col_l1.text_input("Usuario").lower().strip()
    p = col_l2.text_input("Contraseña", type="password")
    if st.button("Ingresar al Panel"):
        if u in USUARIOS and USUARIOS[u] == p:
            st.session_state.auth = True; st.session_state.user = u; st.rerun()
        else: st.error("Credenciales incorrectas")
else:
    try:
        ws = conectar(); df_raw = pd.DataFrame(ws.get_all_records())
        if not df_raw.empty: df_raw.columns = [str(c).strip().upper() for c in df_raw.columns]
    except: st.error("Error de conexión con la base de datos"); st.stop()

    es_editor = st.session_state.user in ["admin", "dav", "dax", "cesar"]

    with st.sidebar:
        st.title("🛠️ Opciones")
        st.write(f"Conectado como: **{st.session_state.user.upper()}**")
        st.divider()
        if st.button("Cerrar Sesión"):
            st.session_state.auth = False; st.rerun()

    st.title("📦 Panel de Control v3.0")

    if es_editor:
        t1, t2, t3 = st.tabs(["➕ Registro Individual", "✏️ Editar / Borrar", "📂 Carga Masiva"])
        
        with t1:
            with st.form("nuevo_p"):
                sk = st.text_input("SKU").strip().upper()
                no = st.text_input("Nombre del Producto")
                c1, c2, c3 = st.columns(3)
                cos_u = c1.number_input("Costo USD", min_value=0.0, format="%.2f")
                tc_n = c2.number_input("Tipo de Cambio", value=18.50, step=0.01)
                fee_n = c3.number_input("% Fee Amazon", value=10.0)
                env_n = c1.number_input("Envío FBA (MXN)", value=0.0)
                
                p_sug = calcular_precio_sugerido(cos_u, fee_n, env_n, tc_n)
                pr_v = c2.number_input("Precio Final de Venta", value=float(p_sug))
                
                if st.form_submit_button("Guardar Producto"):
                    sku_f = sk if sk else f"A-{len(df_raw)+1}"
                    ws.append_row([sku_f, no.upper(), cos_u, pr_v, env_n, fee_n, tc_n])
                    st.rerun()

        with t2:
            if not df_raw.empty:
                sel = st.selectbox("Seleccionar para editar", df_raw['SKU'].astype(str) + " - " + df_raw['PRODUCTO'])
                idx = df_raw[df_raw['SKU'].astype(str) == sel.split(" - ")[0]].index[0]
                curr = df_raw.iloc[idx]
                with st.form("edit_p"):
                    enom = st.text_input("Nombre", value=str(curr['PRODUCTO']))
                    ce1, ce2, ce3, ce4 = st.columns(4) # Añadimos columna para el Fee
                    ecos = ce1.number_input("Costo USD", value=float(curr['COSTO USD']))
                    etc = ce2.number_input("TC", value=float(curr.get('TIPO CAMBIO', 18.0)))
                    epre = ce3.number_input("Precio Amazon", value=float(curr['AMAZON']))
                    efee = ce4.number_input("% Fee", value=float(curr.get('% FEE', 10.0))) # Nuevo campo editable
