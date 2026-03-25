import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import io
from fpdf import FPDF
from datetime import datetime
import numpy as np

# =================================================================
# CALCUAMZ v5.2 - FULL RESTORATION + JSON BULK FIX
# =================================================================
# Empresa: Dacocel | Usuario: sr.sicho
# Estado: Versión completa con Plantillas, PDF y Motor Fiscal.
# =================================================================

st.set_page_config(
    layout="wide", 
    page_title="CalcuAMZ v5.2 | Dacocel Master", 
    page_icon="📦"
)

# --- 1. CONEXIÓN A GOOGLE SHEETS ---
def conectar_base_datos():
    """Establece conexión segura con la hoja de cálculo central."""
    try:
        info_gcp = st.secrets["gcp_service_account"]
        alcances = ["https://www.googleapis.com/auth/spreadsheets"]
        credenciales = Credentials.from_service_account_info(info_gcp, scopes=alcances)
        cliente = gspread.authorize(credenciales)
        # ID único de la base de datos de Dacocel
        id_hoja = "1mF-9Ayv95PJmk4v8PrIDHf2-lRnHFZd5WOxQ__cb3Ss"
        return cliente.open_by_key(id_hoja).sheet1
    except Exception as e:
        st.error(f"❌ Error de enlace con la nube: {e}")
        return None

# --- 2. MOTOR DE CÁLCULO FINANCIERO (OBJETIVO 10% NETO) ---
def limpiar_moneda(valor, por_defecto=0.0):
    """Limpia formatos de moneda para cálculos."""
    try:
        if pd.isna(valor) or str(valor).strip() == "":
            return por_defecto
        limpio = str(valor).replace('$', '').replace(',', '').replace('%', '').strip()
        return float(limpio)
    except:
        return por_defecto

def motor_fiscal_dacocel(fila):
    """Calcula el precio para 10.00% neto considerando retenciones e-commerce en México."""
    try:
        c_usd = limpiar_moneda(fila.get('COSTO USD', 0))
        p_amz_in = limpiar_moneda(fila.get('AMAZON', 0))
        fee_pct = limpiar_moneda(fila.get('% FEE', 4.0))
        envio_mxn = limpiar_moneda(fila.get('ENVIO', 80.0))
        tc_v = limpiar_moneda(fila.get('TIPO CAMBIO', 18.00))
        
        costo_mxn = c_usd * tc_v
        fee_dec = fee_pct / 100
        # Retención combinada IVA/ISR (8% + 2.5%) / 1.16
        tasa_ret = 0.09051724 
        
        if p_amz_in <= 0:
            neto_obj = costo_mxn / 0.90
            p_amz = (neto_obj + envio_mxn) / (1 - fee_dec - tasa_ret)
        else:
            p_amz = p_amz_in

        m_fee = p_amz * fee_dec
        base_iva = p_amz / 1.16
        r_iva, r_isr = base_iva * 0.08, base_iva * 0.025
        neto = p_amz - m_fee - envio_mxn - r_iva - r_isr
        util = neto - costo_mxn
        margen = (util / neto) * 100 if neto > 0 else 0
        
        return pd.Series([p_amz, costo_mxn, m_fee, r_iva, r_isr, neto, util, margen])
    except:
        return pd.Series([0.0] * 8)

# --- 3. GENERADOR DE REPORTES PDF ---
def crear_reporte_pdf(df_final):
    """Genera documento PDF profesional con la lista de precios."""
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 15)
    pdf.cell(190, 10, "DACOCEL - REPORTE MAESTRO DE PRECIOS", ln=True, align='C')
    pdf.set_font("Arial", 'I', 9)
    pdf.cell(190, 7, f"Generado: {datetime.now().strftime('%d/%m/%Y %H:%M')}", ln=True, align='C')
    pdf.ln(10)
    
    # Encabezado de tabla
    pdf.set_fill_color(30, 30, 30); pdf.set_text_color(255, 255, 255)
    pdf.cell(30, 8, " SKU", 1, 0, 'L', True)
    pdf.cell(90, 8, " PRODUCTO", 1, 0, 'L', True)
    pdf.cell(35, 8, " PRECIO AMZ", 1, 0, 'C', True)
    pdf.cell(35, 8, " MARGEN %", 1, 1, 'C', True)
    
    # Datos
    pdf.set_text_color(0, 0, 0); pdf.set_font("Arial", '', 8)
    for _, fila in df_final.iterrows():
        pdf.cell(30, 7, str(fila['SKU']), 1)
        pdf.cell(90, 7, str(fila['PRODUCTO'])[:50], 1)
        pdf.cell(35, 7, f"${fila['AMAZON']:,.2f}", 1, 0, 'R')
        pdf.cell(35, 7, f"{fila['MARGEN %']:.2f}%", 1, 1, 'R')
    
    return pdf.output(dest='S').encode('latin-1')

# --- 4. SISTEMA DE ACCESO ---
ACCESOS = {"admin": "amazon123", "dav": "ventas2026", "dax": "amazon2026", "cesar": "ventas789"}

if 'auth_active' not in st.session_state:
    st.session_state.auth_active = False

if not st.session_state.auth_active:
    st.title("🔐 Acceso CalcuAMZ v5.2")
    u_log = st.text_input("Usuario")
    p_log = st.text_input("Contraseña", type="password")
    if st.button("Entrar"):
        if u_log.lower() in ACCESOS and ACCESOS[u_log.lower()] == p_log:
            st.session_state.auth_active = True
            st.session_state.user_now = u_log
            st.rerun()
else:
    # --- APP PRINCIPAL ---
    hoja = conectar_base_datos()
    raw = hoja.get_all_records() if hoja else []
    df_db = pd.DataFrame(raw) if raw else pd.DataFrame()

    if not df_db.empty:
        df_db.columns = [str(c).upper().strip() for c in df_db.columns]
        res = df_db.apply(motor_fiscal_dacocel, axis=1)
        res.columns = ['AMZ_P', 'C_MXN', 'FEE_$', 'IVA_R', 'ISR_R', 'NETO_R', 'UTIL_$', 'MARG_P']
        df_full = pd.concat([df_db, res], axis=1)
        df_full['AMAZON'] = df_full.apply(lambda x: x['AMZ_P'] if limpiar_moneda(x['AMAZON']) <= 0 else x['AMAZON'], axis=1)

    st.title("📊 Dacocel Master Dashboard v5.2")
    
    t_add, t_edit, t_bulk = st.tabs(["➕ Nuevo Producto", "✏️ Editar / Buscar", "📂 Carga Masiva"])

    # --- TAB: AGREGAR ---
    with t_add:
        with st.form("form_alta"):
            st.subheader("Alta Manual")
            l1, l2 = st.columns(2)
            n_sku, n_nom = l1.text_input("SKU").strip(), l2.text_input("Nombre").upper().strip()
            c1, c2, c3, c4, c5 = st.columns(5)
            n_cos, n_pre, n_env, n_fee, n_tc = c1.number_input("Costo USD"), c2.number_input("Precio AMZ"), c3.number_input("Envío", 80.0), c4.number_input("% Fee", 4.0), c5.number_input("TC", 18.0)
            if st.form_submit_button("🚀 Guardar"):
                if not n_sku or not n_nom: st.error("SKU y Nombre obligatorios.")
                else:
                    hoja.append_row([n_sku, n_nom, n_cos, n_pre, n_env, n_fee, n_tc])
                    st.success("Guardado."); st.rerun()

    # --- TAB: EDITAR CON BUSCADOR ---
    with t_edit:
        if not df_db.empty:
            st.subheader("Gestión de Inventario")
            q_edit = st.text_input("🔍 Buscar SKU o Nombre para editar:").upper()
            opts = (df_full['SKU'].astype(str) + " - " + df_full['PRODUCTO']).tolist()
            opts_f = [o for o in opts if q_edit in o] if q_edit else opts
            if opts_f:
                sel = st.selectbox("Seleccione producto:", opts_f)
                t_sku = str(sel).split(" - ")[0]
                idx = df_full[df_full['SKU'].astype(str) == t_sku].index[0]
                curr = df_full.iloc[idx]
                with st.form("form_ed"):
                    e_nom = st.text_input("Nombre", value=str(curr['PRODUCTO']))
                    ce1, ce2, ce3, ce4, ce5 = st.columns(5)
                    e_cos, e_pre, e_env, e_fee, e_tc = ce1.number_input("Costo USD", value=limpiar_moneda(curr['COSTO USD'])), ce2.number_input("Precio AMZ", value=limpiar_moneda(curr['AMAZON'])), ce3.number_input("Envío", value=limpiar_moneda(curr['ENVIO'])), ce4.number_input("% Fee", value=limpiar_moneda(curr['% FEE'])), ce5.number_input("TC", value=limpiar_moneda(curr['TIPO CAMBIO']))
                    if st.form_submit_button("✅ Actualizar"):
                        hoja.update(f'A{idx+2}:G{idx+2}', [[t_sku, e_nom.upper(), e_cos, e_pre, e_env, e_fee, e_tc]])
                        st.rerun()
                if st.button("🗑️ Borrar"): hoja.delete_rows(int(idx + 2)); st.rerun()

    # --- TAB: BULK (RESTAURADO COMPLETO) ---
    with t_bulk:
        st.subheader("Operaciones por Lotes")
        
        # 1. DESCARGAR PLANTILLA CON TC VARIABLE
        tc_plantilla = st.number_input("Tipo de Cambio para la plantilla:", value=18.0)
        df_p = pd.DataFrame({
            'SKU':['M-001'], 'PRODUCTO':['NOMBRE DEL MODELO'], 'COSTO USD':[0.0], 
            'AMAZON':[0.0], 'ENVIO':[80.0], '% FEE':[4.0], 'TIPO CAMBIO':[tc_plantilla]
        })
        buffer_p = io.BytesIO()
        with pd.ExcelWriter(buffer_p, engine='xlsxwriter') as writer:
            df_p.to_excel(writer, index=False)
        st.download_button(f"📥 Bajar Plantilla (TC {tc_plantilla})", buffer_p.getvalue(), "plantilla_dacocel.xlsx")
        
        st.divider()
        
        # 2. CARGA MASIVA CON FIX DE JSON
        u_file = st.file_uploader("Subir Excel:", type=['xlsx'])
        if u_file and st.button("🚀 Iniciar Carga Masiva"):
            try:
                df_up = pd.read_excel(u_file)
                # Limpieza técnica para evitar InvalidJSONError
                df_up = df_up.replace({np.nan: '', None: ''})
                for c in ['COSTO USD', 'AMAZON', 'ENVIO', '% FEE', 'TIPO CAMBIO']:
                    if c in df_up.columns: df_up[c] = df_up[c].apply(lambda x: limpiar_moneda(x))
                
                hoja.append_rows(df_up.values.tolist())
                st.success("✅ Carga masiva exitosa."); st.rerun()
            except Exception as ex:
                st.error(f"Error: {ex}")

    # --- TABLA Y PDF ---
    st.divider()
    if not df_db.empty:
        st.subheader("📋 Consolidado Maestro")
        df_v = df_full[['SKU', 'PRODUCTO', 'COSTO USD', 'AMAZON', 'ENVIO', '% FEE', 'TIPO CAMBIO', 'C_MXN', 'FEE_$', 'IVA_R', 'ISR_R', 'NETO_R', 'UTIL_$', 'MARG_P']].copy()
        df_v.columns = ['SKU', 'PRODUCTO', 'COSTO USD', 'AMAZON', 'ENVIO', '% FEE', 'TC', 'C_MXN', 'F_$', 'IVA', 'ISR', 'NETO', 'UTILIDAD', 'MARGEN %']
        
        q_g = st.text_input("🔍 Filtro global:").upper()
        if q_g: df_v = df_v[df_v['PRODUCTO'].str.contains(q_g) | df_v['SKU'].astype(str).str.contains(q_g)]

        fmt = {"COSTO USD": "${:,.2f}", "AMAZON": "${:,.2f}", "ENVIO": "${:,.2f}", "TC": "${:,.2f}", "C_MXN": "${:,.2f}", "F_$": "${:,.2f}", "IVA": "${:,.2f}", "ISR": "${:,.2f}", "NETO": "${:,.2f}", "UTILIDAD": "${:,.2f}", "MARGEN %": "{:.2f}%", "% FEE": "{:.2f}%"}
        
        def semaforo(row):
            m = row['MARGEN %']
            idx = row.index.get_loc('MARGEN %')
            bg = '#551a1a' if m < 7 else ('#5e541e' if m < 9.99 else '#1a4d1a')
            s = [''] * len(row); s[idx] = f'background-color: {bg}; color: white; font-weight: bold;'
            return s

        st.dataframe(df_v.style.format(fmt).apply(semaforo, axis=1), use_container_width=True, height=500, hide_index=True)
        
        # BOTÓN REPORTE PDF
        if st.button("📄 Exportar a PDF"):
            pdf_bytes = crear_reporte_pdf(df_v)
            st.download_button("⬇️ Descargar Reporte de Precios", pdf_bytes, f"reporte_dacocel_{datetime.now().strftime('%Y%m%d')}.pdf", "application/pdf")
