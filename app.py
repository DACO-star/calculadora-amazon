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

USUARIOS = {
    "admin": "amazon123", "dav": "ventas2026",
    "dax": "amazon2026", "cesar": "ventas789",
    "consulta": "lector2026"
}

def conectar():
    try:
        info = st.secrets["gcp_service_account"]
        creds = Credentials.from_service_account_info(info, scopes=["https://www.googleapis.com/auth/spreadsheets"])
        return gspread.authorize(creds).open_by_key("1mF-9Ayv95PJmk4v8PrIDHf2-lRnHFZd5WOxQ__cb3Ss").sheet1
    except:
        return None

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
    c1, c2 = st.columns(2)
    u = c1.text_input("Usuario").lower().strip()
    p = c2.text_input("Contraseña", type="password")
    if st.button("Ingresar"):
        if u in USUARIOS and USUARIOS[u] == p:
            st.session_state.auth = True; st.session_state.user = u; st.rerun()
else:
    ws = conectar()
    if ws is None: st.error("Error de conexión"); st.stop()
    
    df_raw = pd.DataFrame(ws.get_all_records())
    if not df_raw.empty:
        df_raw.columns = [str(c).strip().upper() for c in df_raw.columns]

    es_editor = st.session_state.user in ["admin", "dav", "dax", "cesar"]

    with st.sidebar:
        st.title("🛠️ Opciones")
        st.write(f"Conectado: **{st.session_state.user.upper()}**")
        if st.button("Cerrar Sesión"):
            st.session_state.auth = False; st.rerun()

    st.title("📦 Panel de Control v3.0")

    if es_editor:
        t1, t2, t3 = st.tabs(["➕ Nuevo", "✏️ Editar / Borrar", "📂 Carga Bulk"])
        
        with t1:
            with st.form("f_nuevo"):
                sk = st.text_input("SKU").upper()
                no = st.text_input("Nombre Producto")
                c1, c2, c3 = st.columns(3)
                cos = c1.number_input("Costo USD", format="%.2f")
                pre = c2.number_input("Precio Amazon", format="%.2f")
                tc = c3.number_input("TC", value=18.50)
                if st.form_submit_button("Guardar"):
                    ws.append_row([sk, no.upper(), cos, pre, 0, 10, tc])
                    st.rerun()

        with t2:
            if not df_raw.empty:
                sel = st.selectbox("Elegir producto", df_raw['SKU'].astype(str) + " - " + df_raw['PRODUCTO'])
                idx = df_raw[df_raw['SKU'].astype(str) == sel.split(" - ")[0]].index[0]
                curr = df_raw.iloc[idx]
                with st.form("f_editar"):
                    enom = st.text_input("Nombre", value=str(curr['PRODUCTO']))
                    ce1, ce2, ce3, ce4 = st.columns(4)
                    ecos = ce1.number_input("Costo USD", value=float(curr['COSTO USD']))
                    epre = ce2.number_input("Precio Amazon", value=float(curr['AMAZON']))
                    efee = ce3.number_input("% Fee", value=float(curr.get('% FEE', 10.0)))
                    etc = ce4.number_input("TC", value=float(curr.get('TIPO CAMBIO', 18.0)))
                    if st.form_submit_button("Actualizar Datos"):
                        ws.update(f'A{idx+2}:G{idx+2}', [[curr['SKU'], enom.upper(), ecos, epre, curr['ENVIO'], efee, etc]])
                        st.rerun()
                if st.button("🗑️ Eliminar Producto"):
                    ws.delete_rows(int(idx + 2)); st.rerun()

        with t3:
            st.subheader("Carga Masiva")
            col_b1, col_b2 = st.columns(2)
            
            # --- DESCARGAR PLANTILLA ---
            plant_buf = io.BytesIO()
            with pd.ExcelWriter(plant_buf, engine='xlsxwriter') as wr:
                pd.DataFrame(columns=['SKU', 'PRODUCTO', 'COSTO USD', '% FEE', 'ENVIO']).to_excel(wr, index=False)
            col_b1.download_button("📥 Descargar Plantilla Excel", plant_buf.getvalue(), "plantilla_bulk.xlsx")
            
            tc_bulk = col_b2.number_input("TC para carga", value=18.50)
            
            # --- SUBIR ARCHIVO ---
            f_bulk = st.file_uploader("Subir Archivo (XLSX o CSV)", type=['xlsx', 'csv'])
            if f_bulk:
                df_b = pd.read_excel(f_bulk) if f_bulk.name.endswith('xlsx') else pd.read_csv(f_bulk)
                df_b.columns = [str(c).strip().upper() for c in df_b.columns]
                
                if st.button("🚀 Ejecutar Carga en Google Sheets"):
                    filas = []
                    for i, r in df_b.iterrows():
                        p_sug = calcular_precio_sugerido(r['COSTO USD'], r.get('% FEE', 10), r.get('ENVIO', 0), tc_bulk)
                        filas.append([str(r['SKU']), str(r['PRODUCTO']).upper(), r['COSTO USD'], p_sug, r.get('ENVIO', 0), r.get('% FEE', 10), tc_bulk])
                    ws.append_rows(filas)
                    st.success("¡Carga masiva completada!"); st.rerun()

    st.divider()

    # --- TABLA Y PDF ---
    if not df_raw.empty:
        c_bus, c_pdf = st.columns([3, 1])
        busq = c_bus.text_input("🔍 Buscar SKU o Producto...").upper()
        
        calc = df_raw.apply(calcular_detallado, axis=1)
        calc.columns = ['COSTO MXN', 'FEE $', 'RET IVA', 'RET ISR', 'NETO', 'UTILIDAD', 'MARGEN %']
        df_f = pd.concat([df_raw, calc], axis=1)
        
        if busq:
            df_f = df_f[df_f['SKU'].astype(str).str.contains(busq) | df_f['PRODUCTO'].astype(str).str.contains(busq)]

        # --- BOTÓN PDF ---
        if c_pdf.button("📄 Generar Reporte PDF"):
            pdf_data = generar_pdf(df_f)
            st.download_button("⬇️ Descargar PDF", pdf_data, "reporte_dacocel.pdf")

        # Formato visual
        mon_cols = ['COSTO USD', 'TIPO CAMBIO', 'COSTO MXN', 'AMAZON', 'ENVIO', 'FEE $', 'RET IVA', 'RET ISR', 'NETO', 'UTILIDAD']
        fmt = {c: "${:,.2f}" for c in mon_cols}
        fmt.update({'MARGEN %': "{:.2f}%", '% FEE': "{:.2f}%"})

        st.dataframe(
            df_f.style.format(fmt, na_rep="-").apply(estilo_filas, axis=1),
            use_container_width=True, height=800, hide_index=True
        )
