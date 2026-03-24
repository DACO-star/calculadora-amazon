import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import io
from fpdf import FPDF

# --- CalcuAMZ v2.0 ---
st.set_page_config(layout="wide", page_title="CalcuAMZ v2.0")

USUARIOS = {
    "admin": "amazon123", "dav": "ventas2026",
    "dax": "amazon2026", "cesar": "ventas789"
}
TIPO_CAMBIO = 18.00

def conectar():
    info = st.secrets["gcp_service_account"]
    creds = Credentials.from_service_account_info(info, scopes=["https://www.googleapis.com/auth/spreadsheets"])
    return gspread.authorize(creds).open_by_key("1mF-9Ayv95PJmk4v8PrIDHf2-lRnHFZd5WOxQ__cb3Ss").sheet1

def calcular_precio_sugerido(costo_usd, fee_pct, envio_fba):
    if costo_usd <= 0: return 0.0
    costo_mx = costo_usd * TIPO_CAMBIO
    tax_factor = (0.08 + 0.025) / 1.16
    divisor = 1 - (fee_pct/100) - tax_factor
    return ((costo_mx * 1.1112) + envio_fba) / divisor

def calcular_detallado(r):
    c_usd = float(r.get('COSTO USD', 0))
    p_amz = float(r.get('AMAZON', 0))
    p_fee = float(r.get('% FEE', 15.0))
    env = float(r.get('ENVIO', 0))
    costo_mxn = c_usd * TIPO_CAMBIO
    dinero_fee = p_amz * (p_fee / 100)
    base_gravable = p_amz / 1.16
    ret_iva = base_gravable * 0.08
    ret_isr = base_gravable * 0.025
    neto = p_amz - dinero_fee - abs(env) - ret_iva - ret_isr
    utilidad = neto - costo_mxn
    margen = (utilidad / neto) * 100 if neto > 0 else 0
    return pd.Series([costo_mxn, dinero_fee, ret_iva, ret_isr, neto, utilidad, margen])

def generar_pdf(df):
    pdf = FPDF(orientation='L', unit='mm', format='A4')
    pdf.add_page()
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(0, 10, "Reporte de Inventario y Margenes - CalcuAMZ", ln=True, align='C')
    pdf.set_font("Arial", 'B', 8)
    # Encabezados reducidos para que quepan
    headers = ['SKU', 'PRODUCTO', 'COSTO USD', 'AMAZON', 'UTILIDAD', 'MARGEN %']
    widths = [30, 80, 25, 25, 25, 25]
    for i, h in enumerate(headers):
        pdf.cell(widths[i], 10, h, 1, 0, 'C')
    pdf.ln()
    pdf.set_font("Arial", '', 7)
    for _, row in df.iterrows():
        pdf.cell(widths[0], 8, str(row['SKU']), 1)
        pdf.cell(widths[1], 8, str(row['PRODUCTO'])[:45], 1)
        pdf.cell(widths[2], 8, f"${row['COSTO USD']:.2f}", 1)
        pdf.cell(widths[3], 8, f"${row['AMAZON']:.2f}", 1)
        pdf.cell(widths[4], 8, f"${row['UTILIDAD']:.2f}", 1)
        pdf.cell(widths[5], 8, f"{row['MARGEN %']:.2f}%", 1)
        pdf.ln()
    return pdf.output(dest='S').encode('latin-1')

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

    st.title("📦 Gestión de Inventario v2.0")
    t1, t2, t3 = st.tabs(["➕ Individual", "✏️ Editar / Borrar", "📂 Carga Masiva"])

    with t1:
        st.subheader("Nuevo Producto")
        sk_in = st.text_input("SKU (Opcional)").strip().upper()
        with st.form("f1"):
            no = st.text_input("Nombre")
            c1, c2 = st.columns(2)
            cos = c1.number_input("Costo USD", format="%.2f")
            fee = c2.number_input("% Fee", value=15.0)
            env = c1.number_input("Envío FBA", value=0.0)
            pr = c2.number_input("Precio Final", value=float(calcular_precio_sugerido(cos, fee, env)))
            if st.form_submit_button("Guardar"):
                sku = sk_in if sk_in else f"AUTO-{len(df_raw)+1:03d}"
                ws.append_row([sku, no.upper(), cos, pr, env, fee]); st.rerun()

    with t2:
        if not df_raw.empty:
            sel = st.selectbox("Producto", df_raw['SKU'].astype(str) + " - " + df_raw['PRODUCTO'])
            idx = df_raw[df_raw['SKU'].astype(str) == sel.split(" - ")[0]].index[0]
            curr = df_raw.iloc[idx]
            with st.form("f2"):
                enom = st.text_input("Nombre", value=str(curr['PRODUCTO']))
                ecos = st.number_input("Costo USD", value=float(curr['COSTO USD']))
                epre = st.number_input("Precio MXN", value=float(curr['AMAZON']))
                if st.form_submit_button("Actualizar"):
                    ws.update(range_name=f'A{idx+2}:F{idx+2}', values=[[curr['SKU'], enom.upper(), ecos, epre, curr['ENVIO'], curr['% FEE']]])
                    st.rerun()
            if st.session_state.user in ["admin", "dav"] and st.button("🗑️ Eliminar"):
                ws.delete_rows(int(idx + 2)); st.rerun()

    with t3:
        st.subheader("Bulk Upload")
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine='xlsxwriter') as wr:
            pd.DataFrame(columns=['SKU', 'PRODUCTO', 'COSTO USD', '% FEE', 'ENVIO']).to_excel(wr, index=False)
        st.download_button("📥 Bajar Plantilla", buf.getvalue(), "plantilla.xlsx")
        st.divider()
        arc = st.file_uploader("Subir archivo", type=['xlsx', 'csv'])
        if arc:
            df_b = pd.read_excel(arc) if arc.name.endswith('xlsx') else pd.read_csv(arc)
            df_b.columns = [str(c).strip().upper() for c in df_b.columns]
            df_b['AMAZON'] = df_b.apply(lambda r: calcular_precio_sugerido(r['COSTO USD'], r.get('% FEE', 15), r.get('ENVIO', 0)), axis=1)
            st.dataframe(df_b.head())
            if st.button("🚀 Procesar"):
                ws.append_rows(df_b[['SKU', 'PRODUCTO', 'COSTO USD', 'AMAZON', 'ENVIO', '% FEE']].values.tolist())
                st.rerun()

    st.divider()
    if not df_raw.empty:
        bus = st.text_input("🔍 Filtro").strip().upper()
        res = df_raw.apply(calcular_detallado, axis=1)
        res.columns = ['COSTO MXN', 'FEE $', 'RET IVA', 'RET ISR', 'NETO RECIBIDO', 'UTILIDAD', 'MARGEN %']
        df_f = pd.concat([df_raw, res], axis=1)
        if bus: df_f = df_f[df_f['SKU'].astype(str).str.contains(bus) | df_f['PRODUCTO'].astype(str).str.contains(bus)]
        
        c1, c2, c3 = st.columns([1,1,1])
        c1.metric("Items", len(df_f))
        c2.metric("Margen Promedio", f"{df_f['MARGEN %'].mean():.2f}%")
        
        # BOTÓN PDF
        with c3:
            if st.button("📄 Generar Reporte PDF"):
                pdf_bytes = generar_pdf(df_f)
                st.download_button("⬇️ Descargar PDF", pdf_bytes, "reporte_margenes.pdf", "application/pdf")
        
        formato = {c: "${:,.2f}" for c in ['COSTO USD','AMAZON','COSTO MXN','UTILIDAD']}
        formato.update({'MARGEN %': "{:.2f}%", '% FEE': "{:.2f}%"})
        st.dataframe(df_f.style.format(formato, na_rep="-"), use_container_width=True)
