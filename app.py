import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import io
from fpdf import FPDF

# ==========================================
# CALCUAMZ v4.3.1 - RESTAURACIÓN TOTAL
# ==========================================

st.set_page_config(layout="wide", page_title="CalcuAMZ v4.3.1", page_icon="📦")

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
        p_fee_pct = clean(r.get('% FEE', 4.0))
        env = clean(r.get('ENVIO', 80.0))
        t_c = clean(r.get('TIPO CAMBIO', 18.00))
        
        costo_mxn = c_usd * t_c
        
        # AUTO-CÁLCULO si Amazon es 0 (Margen 10%)
        if p_amz_orig <= 0:
            divisor = (1 - (p_fee_pct/100) - (0.105 / 1.16) - 0.10)
            p_amz = (costo_mxn + abs(env)) / divisor if divisor > 0 else 0
        else:
            p_amz = p_amz_orig

        dinero_fee = p_amz * (p_fee_pct / 100)
        base_grav = p_amz / 1.16
        ret_iva, ret_isr = base_grav * 0.08, base_grav * 0.025
        neto = p_amz - dinero_fee - abs(env) - ret_iva - ret_isr
        utilidad = neto - costo_mxn
        margen = (utilidad / neto) * 100 if neto > 0 else 0
        
        return pd.Series([p_amz, costo_mxn, dinero_fee, ret_iva, ret_isr, neto, utilidad, margen])
    except: return pd.Series([0,0,0,0,0,0,0,0])

def estilo_semaforo(row):
    estilos = [''] * len(row)
    if 'MARGEN %' in row.index:
        val = row['MARGEN %']
        idx = row.index.get_loc('MARGEN %')
        # Rojo si < 6%, Amarillo si < 9%, Verde si > 9%
        bg = '#551a1a' if val <= 6.0 else ('#5e541e' if val <= 9.0 else '#1a4d1a')
        estilos[idx] = f'background-color: {bg}; color: white; font-weight: bold;'
    return estilos

def generar_pdf(df):
    pdf = FPDF(orientation='L', unit='mm', format='A4')
    pdf.add_page()
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(0, 10, "REPORTE MAESTRO DACOCEL", ln=True, align='C')
    pdf.ln(5)
    pdf.set_font("Arial", 'B', 8)
    headers = ['SKU', 'PRODUCTO', 'COSTO USD', 'AMAZON', 'NETO', 'UTILIDAD', 'MARGEN %']
    widths = [25, 90, 25, 25, 25, 25, 25]
    for i, h in enumerate(headers): pdf.cell(widths[i], 10, h, 1, 0, 'C')
    pdf.ln()
    pdf.set_font("Arial", '', 7)
    for _, r in df.iterrows():
        pdf.cell(widths[0], 8, str(r['SKU']), 1)
        pdf.cell(widths[1], 8, str(r['PRODUCTO'])[:50], 1)
        pdf.cell(25, 8, f"${r['COSTO USD']:,.2f}", 1)
        pdf.cell(25, 8, f"${r['AMAZON']:,.2f}", 1)
        pdf.cell(25, 8, f"${r['NETO']:,.2f}", 1)
        pdf.cell(25, 8, f"${r['UTILIDAD']:,.2f}", 1)
        pdf.cell(25, 8, f"{r['MARGEN %']:.2f}%", 1)
        pdf.ln()
    return pdf.output(dest='S').encode('latin-1', 'ignore')

# --- SEGURIDAD ---
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
    registros = ws.get_all_records() if ws else []
    df_raw = pd.DataFrame(registros) if registros else pd.DataFrame()

    if not df_raw.empty:
        df_raw.columns = [str(c).upper().strip() for c in df_raw.columns]
        calc = df_raw.apply(calcular_detallado, axis=1)
        calc.columns = ['AMZ_F', 'C_MX', 'F_$', 'IVA', 'ISR', 'NETO', 'UTIL', 'MARGEN']
        df_full = pd.concat([df_raw, calc], axis=1)
        df_full['AMAZON'] = df_full.apply(lambda x: x['AMZ_F'] if clean(x['AMAZON']) <= 0 else clean(x['AMAZON']), axis=1)

    st.title("📊 Dacocel Master Dashboard v4.3.1")
    
    t1, t2, t3 = st.tabs(["➕ Nuevo Registro", "✏️ Editar / Borrar", "📂 Carga Bulk"])

    with t1:
        with st.form("f_new"):
            st.subheader("Registrar Producto")
            sk, nom = st.text_input("SKU"), st.text_input("Nombre (OBLIGATORIO)")
            c1, c2, c3, c4, c5 = st.columns(5)
            cos = c1.number_input("Costo USD", format="%.2f")
            pre = c2.number_input("Precio AMZ (0=Auto)", value=0.0)
            env = c3.number_input("Envío MXN", value=80.0)
            fee = c4.number_input("% Fee", value=4.0)
            tc = c5.number_input("T. Cambio", value=18.0)
            if st.form_submit_button("🚀 Guardar"):
                if nom:
                    ws.append_row([sk, nom.upper(), cos, pre, env, fee, tc])
                    st.rerun()

    with t2:
        if not df_raw.empty:
            opcs = (df_raw['SKU'].astype(str) + " - " + df_raw['PRODUCTO']).tolist()
            sel = st.selectbox("Selecciona para editar:", opcs)
            sku_s = str(sel).split(" - ")[0]
            idx = df_raw[df_raw['SKU'].astype(str) == sku_s].index[0]
            curr = df_raw.iloc[idx]
            with st.form("f_edit"):
                enom = st.text_input("Nombre", value=str(curr.get('PRODUCTO', '')))
                ce1, ce2, ce3, ce4, ce5 = st.columns(5)
                ecos = ce1.number_input("Costo USD", value=clean(curr.get('COSTO USD')))
                epre = ce2.number_input("Precio AMZ", value=clean(curr.get('AMAZON')))
                eenv = ce3.number_input("Envío", value=clean(curr.get('ENVIO', 80.0)))
                efee = ce4.number_input("% Fee", value=clean(curr.get('% FEE', 4.0)))
                etc = ce5.number_input("TC", value=clean(curr.get('TIPO CAMBIO', 18.0)))
                if st.form_submit_button("💾 Actualizar"):
                    ws.update(f'A{idx+2}:G{idx+2}', [[sku_s, enom.upper(), ecos, epre, eenv, efee, etc]])
                    st.rerun()
            if st.button("🗑️ Eliminar"): ws.delete_rows(int(idx + 2)); st.rerun()

    with t3:
        st.subheader("Carga Masiva")
        plantilla = pd.DataFrame(columns=['SKU', 'PRODUCTO', 'COSTO USD', 'AMAZON', 'ENVIO', '% FEE', 'TIPO CAMBIO'])
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine='xlsxwriter') as wr: plantilla.to_excel(wr, index=False)
        st.download_button("📥 Descargar Plantilla", buf.getvalue(), "plantilla.xlsx")
        archivo = st.file_uploader("Subir Excel", type=['xlsx'])
        if archivo and st.button("🚀 Procesar Carga"):
            df_b = pd.read_excel(archivo)
            ws.append_rows(df_b.values.tolist())
            st.rerun()

    st.divider()
    if not df_raw.empty:
        df_final = df_full[['SKU', 'PRODUCTO', 'COSTO USD', 'AMAZON', 'ENVIO', '% FEE', 'TC', 'C_MX', 'F_$', 'IVA', 'ISR', 'NETO', 'UTIL', 'MARGEN']].copy()
        df_final.columns = ['SKU', 'PRODUCTO', 'COSTO USD', 'AMAZON', 'ENVIO', '% FEE', 'TC', 'C_MXN', 'F_$', 'IVA', 'ISR', 'NETO', 'UTILIDAD', 'MARGEN %']
        
        c_bus, c_pdf = st.columns([3, 1])
        busq = c_bus.text_input("🔍 Filtro Maestro...").upper()
        if busq: df_final = df_final[df_final['PRODUCTO'].str.contains(busq) | df_final['SKU'].astype(str).str.contains(busq)]
        
        if c_pdf.button("📄 Generar PDF", use_container_width=True):
            st.download_button("⬇️ Descargar Reporte", generar_pdf(df_final), "reporte_dacocel.pdf")

        fmt = {c: "${:,.2f}" for c in ['COSTO USD', 'AMAZON', 'ENVIO', 'TC', 'C_MXN', 'F_$', 'IVA', 'ISR', 'NETO', 'UTILIDAD']}
        st.dataframe(df_final.style.format(fmt).format({"MARGEN %": "{:.2f}%", "% FEE": "{:.2f}%"}).apply(estilo_semaforo, axis=1), use_container_width=True, height=600, hide_index=True)
