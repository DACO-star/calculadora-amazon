import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import io
from fpdf import FPDF

# --- CalcuAMZ v2.5.4 (SKU Auto-Bulk + TC Integrado) ---
st.set_page_config(layout="wide", page_title="CalcuAMZ v2.5.4")

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
    pdf.cell(0, 10, "Reporte de Inventario - CalcuAMZ", ln=True, align='C')
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

# --- LÓGICA DE ACCESO ---
if 'auth' not in st.session_state: st.session_state.auth = False

if not st.session_state.auth:
    st.title("🔐 Acceso - CalcuAMZ")
    u = st.text_input("Usuario").lower().strip()
    p = st.text_input("Clave", type="password")
    if st.button("Ingresar"):
        if u in USUARIOS and USUARIOS[u] == p:
            st.session_state.auth = True; st.session_state.user = u; st.rerun()
        else: st.error("Acceso denegado")
else:
    try:
        ws = conectar(); df_raw = pd.DataFrame(ws.get_all_records())
        if not df_raw.empty: df_raw.columns = [str(c).strip().upper() for c in df_raw.columns]
    except: st.error("Error de conexión"); st.stop()

    es_editor = st.session_state.user in ["admin", "dav", "dax", "cesar"]

    with st.sidebar:
        st.header(f"👤 {st.session_state.user.upper()}")
        st.divider()
        if st.button("Cerrar Sesión"):
            st.session_state.auth = False; st.rerun()

    st.title("📦 Panel de Gestión y Consulta")

    if es_editor:
        t1, t2, t3 = st.tabs(["➕ Individual", "✏️ Editar / Borrar", "📂 Carga Masiva"])
        
        with t1:
            with st.form("nuevo"):
                sk = st.text_input("SKU").strip().upper()
                no = st.text_input("Nombre")
                col1, col2, col3 = st.columns(3)
                cos_u = col1.number_input("Costo USD", format="%.2f", min_value=0.0)
                tc_n = col2.number_input("Tipo de Cambio", value=18.50, step=0.01)
                fee_n = col3.number_input("% Fee Amazon", value=10.0)
                env_n = col1.number_input("Envío FBA (MXN)", value=0.0)
                
                p_sug = calcular_precio_sugerido(cos_u, fee_n, env_n, tc_n)
                pr_v = col2.number_input("Precio Venta Sugerido", value=float(p_sug))
                
                if st.form_submit_button("Guardar"):
                    sku_final = sk if sk else f"A-{len(df_raw)+1}"
                    ws.append_row([sku_final, no.upper(), cos_u, pr_v, env_n, fee_n, tc_n])
                    st.rerun()

        with t2:
            if not df_raw.empty:
                sel = st.selectbox("Elegir producto", df_raw['SKU'].astype(str) + " - " + df_raw['PRODUCTO'])
                idx = df_raw[df_raw['SKU'].astype(str) == sel.split(" - ")[0]].index[0]
                curr = df_raw.iloc[idx]
                with st.form("edit"):
                    enom = st.text_input("Nombre", value=str(curr['PRODUCTO']))
                    c_edit1, c_edit2, c_edit3 = st.columns(3)
                    ecos = c_edit1.number_input("Costo USD", value=float(curr['COSTO USD']))
                    etc = c_edit2.number_input("TC", value=float(curr.get('TIPO CAMBIO', 18.0)))
                    epre = c_edit3.number_input("Precio Amazon", value=float(curr['AMAZON']))
                    if st.form_submit_button("Actualizar"):
                        ws.update(f'A{idx+2}:G{idx+2}', [[curr['SKU'], enom.upper(), ecos, epre, curr['ENVIO'], curr['% FEE'], etc]])
                        st.rerun()
                if st.session_state.user in ["admin", "dav"] and st.button("🗑️ Eliminar"):
                    ws.delete_rows(int(idx + 2)); st.rerun()

        with t3:
            st.subheader("Importación Masiva")
            tc_bulk = st.number_input("TC para esta carga", value=18.50, step=0.01)
            buf_p = io.BytesIO()
            with pd.ExcelWriter(buf_p, engine='xlsxwriter') as wr:
                pd.DataFrame(columns=['SKU', 'PRODUCTO', 'COSTO USD', '% FEE', 'ENVIO']).to_excel(wr, index=False)
            st.download_button("📥 Plantilla", buf_p.getvalue(), "plantilla.xlsx")
            
            st.divider()
            arc = st.file_uploader("Subir Excel/CSV", type=['xlsx', 'csv'])
            if arc:
                df_b = pd.read_excel(arc) if arc.name.endswith('xlsx') else pd.read_csv(arc)
                df_b.columns = [str(c).strip().upper() for c in df_b.columns]
                
                # Anti-None SKU Logic
                for i, row in df_b.iterrows():
                    if 'SKU' not in df_b.columns or pd.isna(row.get('SKU')) or str(row.get('SKU')).strip() in ["", "None", "nan"]:
                        df_b.at[i, 'SKU'] = f"B-{len(df_raw) + i + 1}"
                
                df_b['AMAZON'] = df_b.apply(lambda r: calcular_precio_sugerido(r['COSTO USD'], r.get('% FEE', 10), r.get('ENVIO', 0), tc_bulk), axis=1)
                if st.button("🚀 Cargar Bulk"):
                    filas = [[str(f['SKU']), str(f['PRODUCTO']).upper(), f['COSTO USD'], f['AMAZON'], f.get('ENVIO', 0), f.get('% FEE', 10), tc_bulk] for _, f in df_b.iterrows()]
                    ws.append_rows(filas); st.rerun()
    else:
        st.info("💡 Modo de solo lectura.")

    st.divider()
    if not df_raw.empty:
        c_bus, c_pdf = st.columns([3, 1])
        busqueda = c_bus.text_input("🔍 Buscar SKU o Producto").strip().upper()
        res = df_raw.apply(calcular_detallado, axis=1)
        res.columns = ['COSTO MXN', 'FEE $', 'RET IVA', 'RET ISR', 'NETO RECIBIDO', 'UTILIDAD', 'MARGEN %']
        df_f = pd.concat([df_raw, res], axis=1)
        orden = ['SKU', 'PRODUCTO', 'COSTO USD', 'TIPO CAMBIO', 'COSTO MXN', 'AMAZON', 'ENVIO', '% FEE', 'FEE $', 'RET IVA', 'RET ISR', 'NETO RECIBIDO', 'UTILIDAD', 'MARGEN %']
        df_f = df_f[[c for c in orden if c in df_f.columns]]
        if busqueda: 
            df_f = df_f[df_f['SKU'].astype(str).str.contains(busqueda) | df_f['PRODUCTO'].astype(str).str.contains(busqueda)]
        with c_pdf:
            st.write("")
            if st.button("📄 Generar PDF"):
                pdf_bytes = generar_pdf(df_f)
                st.download_button("⬇️ Descargar PDF", pdf_bytes, "reporte.pdf")

        moneda = ['COSTO USD', 'TIPO CAMBIO', 'COSTO MXN', 'AMAZON', 'ENVIO', 'FEE $', 'RET IVA', 'RET ISR', 'NETO RECIBIDO', 'UTILIDAD']
        formato = {c: "${:,.2f}" for c in moneda}
        formato.update({'MARGEN %': "{:.2f}%", '% FEE': "{:.2f}%"})
        st.dataframe(df_f.style.format(formato, na_rep="-").apply(estilo_filas, axis=1), use_container_width=True, height=1200, hide_index=True)
