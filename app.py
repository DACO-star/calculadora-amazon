import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import io
from fpdf import FPDF

# --- CalcuAMZ v2.1 (Full Format & PDF) ---
st.set_page_config(layout="wide", page_title="CalcuAMZ v2.1")

# Configuración de Acceso y Tipo de Cambio
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
    # 1.1112 ajusta para dejar un 10% de margen real tras impuestos
    return ((costo_mx * 1.1112) + envio_fba) / divisor

def calcular_detallado(r):
    c_usd = float(r.get('COSTO USD', 0))
    p_amz = float(r.get('AMAZON', 0))
    p_fee = float(r.get('% FEE', 10.0)) # Fee por defecto 10%
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

def color_margen(val):
    return 'color: red' if isinstance(val, (int, float)) and val < 0 else 'color: white'

def generar_pdf(df):
    pdf = FPDF(orientation='L', unit='mm', format='A4')
    pdf.add_page()
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(0, 10, "Reporte de Inventario y Margenes - CalcuAMZ", ln=True, align='C')
    pdf.set_font("Arial", 'B', 8)
    headers = ['SKU', 'PRODUCTO', 'COSTO USD', 'AMAZON', 'NETO REC.', 'UTILIDAD', 'MARGEN %']
    widths = [25, 85, 25, 25, 25, 25, 20]
    for i, h in enumerate(headers):
        pdf.cell(widths[i], 10, h, 1, 0, 'C')
    pdf.ln()
    pdf.set_font("Arial", '', 7)
    for _, row in df.iterrows():
        pdf.cell(widths[0], 8, str(row['SKU']), 1)
        pdf.cell(widths[1], 8, str(row['PRODUCTO'])[:50], 1)
        pdf.cell(widths[2], 8, f"${row['COSTO USD']:,.2f}", 1)
        pdf.cell(widths[3], 8, f"${row['AMAZON']:,.2f}", 1)
        pdf.cell(widths[4], 8, f"${row['NETO RECIBIDO']:,.2f}", 1)
        pdf.cell(widths[5], 8, f"${row['UTILIDAD']:,.2f}", 1)
        pdf.cell(widths[6], 8, f"{row['MARGEN %']:.2f}%", 1)
        pdf.ln()
    return pdf.output(dest='S').encode('latin-1')

# --- Lógica de Sesión ---
if 'auth' not in st.session_state: st.session_state.auth = False

if not st.session_state.auth:
    st.title("🔐 Acceso - CalcuAMZ")
    u = st.text_input("Usuario").lower().strip()
    p = st.text_input("Clave", type="password")
    if st.button("Ingresar"):
        if u in USUARIOS and USUARIOS[u] == p:
            st.session_state.auth = True; st.session_state.user = u; st.rerun()
        else: st.error("Error de credenciales")
else:
    try:
        ws = conectar(); df_raw = pd.DataFrame(ws.get_all_records())
        if not df_raw.empty: df_raw.columns = [str(c).strip().upper() for c in df_raw.columns]
    except: st.error("Error al conectar con Google Sheets"); st.stop()

    st.title("📦 Panel de Gestión de Inventario")
    t1, t2, t3 = st.tabs(["➕ Individual", "✏️ Editar / Borrar", "📂 Carga Masiva"])

    with t1:
        st.subheader("Registro Manual")
        sk_in = st.text_input("SKU").strip().upper()
        with st.form("nuevo_p"):
            no = st.text_input("Nombre del Producto")
            c1, c2 = st.columns(2)
            cos = c1.number_input("Costo USD", format="%.2f", step=0.1)
            fee = c2.number_input("% Fee Amazon", value=10.0)
            env = c1.number_input("Envío FBA (MXN)", value=0.0)
            
            p_sug = calcular_precio_sugerido(cos, fee, env)
            pr = c2.number_input("Precio Sugerido (10% Margen)", value=float(p_sug))
            
            if st.form_submit_button("Guardar Producto"):
                if no:
                    final_sku = sk_in if sk_in else f"AUTO-{len(df_raw)+1:03d}"
                    ws.append_row([final_sku, no.upper(), cos, pr, env, fee])
                    st.success(f"Guardado: {final_sku}"); st.rerun()

    with t2:
        if not df_raw.empty:
            st.subheader("Modificar Existente")
            sel = st.selectbox("Selecciona para editar", df_raw['SKU'].astype(str) + " - " + df_raw['PRODUCTO'])
            sku_sel = sel.split(" - ")[0]
            idx = df_raw[df_raw['SKU'].astype(str) == sku_sel].index[0]
            curr = df_raw.iloc[idx]
            with st.form("edicion"):
                enom = st.text_input("Nombre", value=str(curr['PRODUCTO']))
                ecos = st.number_input("Costo USD", value=float(curr['COSTO USD']))
                epre = st.number_input("Precio MXN", value=float(curr['AMAZON']))
                efee = st.number_input("% Fee", value=float(curr.get('% FEE', 10.0)))
                eenv = st.number_input("Envío", value=float(curr.get('ENVIO', 0.0)))
                if st.form_submit_button("Actualizar"):
                    ws.update(range_name=f'A{idx+2}:F{idx+2}', values=[[sku_sel, enom.upper(), ecos, epre, eenv, efee]])
                    st.rerun()
            if st.session_state.user in ["admin", "dav"] and st.button("🗑️ Eliminar Producto"):
                ws.delete_rows(int(idx + 2)); st.rerun()

    with t3:
        st.subheader("Procesador de Listas")
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
            pd.DataFrame(columns=['SKU', 'PRODUCTO', 'COSTO USD', '% FEE', 'ENVIO']).to_excel(writer, index=False)
        st.download_button("📥 Descargar Plantilla", buffer.getvalue(), "plantilla_amz.xlsx")
        
        st.divider()
        archivo = st.file_uploader("Subir Excel del Proveedor", type=['xlsx', 'csv'])
        if archivo:
            try:
                df_b = pd.read_excel(archivo) if archivo.name.endswith('xlsx') else pd.read_csv(archivo)
                df_b.columns = [str(c).strip().upper() for c in df_b.columns]
                if all(c in df_b.columns for c in ['PRODUCTO', 'COSTO USD']):
                    if 'SKU' not in df_b.columns: df_b['SKU'] = [f"B-{i+len(df_raw)+1:03d}" for i in range(len(df_b))]
                    if 'ENVIO' not in df_b.columns: df_b['ENVIO'] = 0.0
                    if '% FEE' not in df_b.columns: df_b['% FEE'] = 10.0
                    
                    df_b['AMAZON'] = df_b.apply(lambda r: calcular_precio_sugerido(r['COSTO USD'], r['% FEE'], r['ENVIO']), axis=1)
                    st.write("Vista previa con precios calculados:")
                    st.dataframe(df_b.head())
                    if st.button("🚀 Confirmar y Subir todo"):
                        ws.append_rows(df_b[['SKU', 'PRODUCTO', 'COSTO USD', 'AMAZON', 'ENVIO', '% FEE']].values.tolist())
                        st.success("¡Carga lista!"); st.rerun()
            except Exception as e: st.error(f"Error: {e}")

    st.divider()
    if not df_raw.empty:
        busqueda = st.text_input("🔍 Buscar por SKU o Nombre").strip().upper()
        res = df_raw.apply(calcular_detallado, axis=1)
        res.columns = ['COSTO MXN', 'FEE $', 'RET IVA', 'RET ISR', 'NETO RECIBIDO', 'UTILIDAD', 'MARGEN %']
        df_final = pd.concat([df_raw, res], axis=1)
        
        if busqueda:
            df_final = df_final[df_final['SKU'].astype(str).str.contains(busqueda) | df_final['PRODUCTO'].astype(str).str.contains(busqueda)]
        
        c1, c2, c3 = st.columns([1,1,1])
        c1.metric("Total Items", len(df_final))
        c2.metric("Margen Promedio", f"{df_final['MARGEN %'].mean():.2f}%")
        with c3:
            if st.button("📄 Generar Reporte PDF"):
                try:
                    pdf_out = generar_pdf(df_final)
                    st.download_button("⬇️ Descargar Reporte", pdf_out, "reporte_amazon.pdf", "application/pdf")
                except: st.error("Error al generar PDF. Revisa caracteres especiales.")

        # --- Formato Visual con Signos ---
        moneda = ['COSTO USD','AMAZON','ENVIO','COSTO MXN','FEE $','RET IVA','RET ISR','NETO RECIBIDO','UTILIDAD']
        formato = {c: "${:,.2f}" for c in moneda}
        formato.update({'MARGEN %': "{:.2f}%", '% FEE': "{:.2f}%"})
        
        st.dataframe(
            df_final.style.format(formato, na_rep="-").applymap(color_margen, subset=['MARGEN %']), 
            use_container_width=True, height=600,
            hide_index=True
        )
