import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import io
from fpdf import FPDF
from datetime import datetime
import numpy as np

# =================================================================
# CALCUAMZ v5.1 - FIX DE CARGA MASIVA (SERIALIZACIÓN JSON)
# =================================================================
# Empresa: Dacocel | Usuario: sr.sicho
# Solución: Limpieza de NaNs y valores nulos antes de append_rows.
# =================================================================

st.set_page_config(
    layout="wide", 
    page_title="CalcuAMZ v5.1 | Dacocel Master", 
    page_icon="📦"
)

# --- 1. CONEXIÓN A BASE DE DATOS (GOOGLE SHEETS) ---
def conectar_base_datos():
    """Establece conexión segura con la hoja de cálculo central."""
    try:
        info_gcp = st.secrets["gcp_service_account"]
        scopes = ["https://www.googleapis.com/auth/spreadsheets"]
        creds = Credentials.from_service_account_info(info_gcp, scopes=scopes)
        client = gspread.authorize(creds)
        sheet_id = "1mF-9Ayv95PJmk4v8PrIDHf2-lRnHFZd5WOxQ__cb3Ss"
        return client.open_by_key(sheet_id).sheet1
    except Exception as e:
        st.error(f"❌ Error de enlace con la nube: {e}")
        return None

# --- 2. MOTOR FINANCIERO (LÓGICA DE NEGOCIO) ---
def limpiar_moneda(valor, por_defecto=0.0):
    """Limpia strings de moneda para cálculos flotantes."""
    try:
        if pd.isna(valor) or str(valor).strip() == "":
            return por_defecto
        limpio = str(valor).replace('$', '').replace(',', '').replace('%', '').strip()
        return float(limpio)
    except:
        return por_defecto

def motor_fiscal_dacocel(fila):
    """Calcula el precio para MARGEN NETO 10.00% con retenciones MX."""
    try:
        c_usd = limpiar_moneda(fila.get('COSTO USD', 0))
        p_amz_manual = limpiar_moneda(fila.get('AMAZON', 0))
        fee_pct = limpiar_moneda(fila.get('% FEE', 4.0))
        envio_mxn = limpiar_moneda(fila.get('ENVIO', 80.0))
        tc_hoy = limpiar_moneda(fila.get('TIPO CAMBIO', 18.00))
        
        costo_mxn_total = c_usd * tc_hoy
        fee_dec = fee_pct / 100
        retencion_mx = 0.09051724 
        
        if p_amz_manual <= 0:
            neto_objetivo = costo_mxn_total / 0.90
            p_sugerido = (neto_objetivo + envio_mxn) / (1 - fee_dec - retencion_mx)
        else:
            p_sugerido = p_amz_manual

        monto_fee = p_sugerido * fee_dec
        base_sat = p_sugerido / 1.16
        m_iva, m_isr = base_sat * 0.08, base_sat * 0.025
        neto_final = p_sugerido - monto_fee - envio_mxn - m_iva - m_isr
        utilidad_mxn = neto_final - costo_mxn_total
        margen_pct = (utilidad_mxn / neto_final) * 100 if neto_final > 0 else 0
        
        return pd.Series([p_sugerido, costo_mxn_total, monto_fee, m_iva, m_isr, neto_final, utilidad_mxn, margen_pct])
    except:
        return pd.Series([0.0] * 8)

# --- 3. EXPORTACIÓN PDF ---
def crear_pdf_listado(df_final):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 15)
    pdf.cell(190, 10, "DACOCEL - REPORTE v5.1", ln=True, align='C')
    pdf.ln(10)
    pdf.set_fill_color(30, 30, 30); pdf.set_text_color(255, 255, 255)
    pdf.cell(30, 8, " SKU", 1, 0, 'L', True)
    pdf.cell(90, 8, " PRODUCTO", 1, 0, 'L', True)
    pdf.cell(35, 8, " PRECIO AMZ", 1, 0, 'C', True)
    pdf.cell(35, 8, " MARGEN %", 1, 1, 'C', True)
    pdf.set_text_color(0, 0, 0); pdf.set_font("Arial", '', 8)
    for _, r in df_final.iterrows():
        pdf.cell(30, 7, str(r['SKU']), 1)
        pdf.cell(90, 7, str(r['PRODUCTO'])[:50], 1)
        pdf.cell(35, 7, f"${r['AMAZON']:,.2f}", 1, 0, 'R')
        pdf.cell(35, 7, f"{r['MARGEN %']:.2f}%", 1, 1, 'R')
    return pdf.output(dest='S').encode('latin-1')

# --- 4. ACCESO ---
LOGIN_DATA = {"admin": "amazon123", "dav": "ventas2026", "dax": "amazon2026", "cesar": "ventas789"}
if 'auth_v5' not in st.session_state: st.session_state.auth_v5 = False

if not st.session_state.auth_v5:
    st.title("🔐 Acceso CalcuAMZ v5.1")
    u_in = st.text_input("Usuario")
    p_in = st.text_input("Contraseña", type="password")
    if st.button("Entrar"):
        if u_in.lower() in LOGIN_DATA and LOGIN_DATA[u_in.lower()] == p_in:
            st.session_state.auth_v5 = True
            st.session_state.current_user = u_in
            st.rerun()
else:
    ws = conectar_base_datos()
    data_raw = ws.get_all_records() if ws else []
    df_base = pd.DataFrame(data_raw) if data_raw else pd.DataFrame()

    if not df_base.empty:
        df_base.columns = [str(c).upper().strip() for c in df_base.columns]
        res_full = df_base.apply(motor_fiscal_dacocel, axis=1)
        res_full.columns = ['AMZ_P', 'C_MXN', 'FEE_$', 'IVA_R', 'ISR_R', 'NETO_R', 'UTIL_$', 'MARG_P']
        df_full = pd.concat([df_base, res_full], axis=1)
        df_full['AMAZON'] = df_full.apply(lambda x: x['AMZ_P'] if limpiar_moneda(x['AMAZON']) <= 0 else x['AMAZON'], axis=1)

    st.title("📊 Dacocel Master Dashboard v5.1")
    
    t_add, t_edit, t_bulk = st.tabs(["➕ Agregar", "✏️ Gestión", "📂 Bulk"])

    with t_add:
        with st.form("form_nuevo"):
            st.subheader("Alta de Producto")
            c_h1, c_h2 = st.columns(2)
            s_sku = c_h1.text_input("SKU").strip()
            s_nom = c_h2.text_input("Nombre").upper().strip()
            c1, c2, c3, c4, c5 = st.columns(5)
            s_cos, s_pre, s_env, s_fee, s_tc = c1.number_input("Costo USD"), c2.number_input("Precio Amazon"), c3.number_input("Envío", 80.0), c4.number_input("% Fee", 4.0), c5.number_input("TC", 18.0)
            if st.form_submit_button("💾 Guardar"):
                if not s_sku or not s_nom: st.error("Faltan datos.")
                else:
                    ws.append_row([s_sku, s_nom, s_cos, s_pre, s_env, s_fee, s_tc])
                    st.success("✅ Guardado."); st.rerun()

    with t_edit:
        if not df_base.empty:
            busqueda_edit = st.text_input("🔍 Buscar SKU o Nombre:").upper()
            opciones = (df_full['SKU'].astype(str) + " - " + df_full['PRODUCTO']).tolist()
            opciones_f = [o for o in opciones if busqueda_edit in o] if busqueda_edit else opciones
            if opciones_f:
                sel = st.selectbox("Seleccione:", opciones_f)
                target = str(sel).split(" - ")[0]
                idx_sel = df_full[df_full['SKU'].astype(str) == target].index[0]
                d_val = df_full.iloc[idx_sel]
                with st.form("form_edit"):
                    u_nom = st.text_input("Nombre", value=str(d_val['PRODUCTO']))
                    ce1, ce2, ce3, ce4, ce5 = st.columns(5)
                    u_cos, u_pre, u_env, u_fee, u_tc = ce1.number_input("Costo USD", value=limpiar_moneda(d_val['COSTO USD'])), ce2.number_input("Precio Amazon", value=limpiar_moneda(d_val['AMAZON'])), ce3.number_input("Envío", value=limpiar_moneda(d_val['ENVIO'])), ce4.number_input("% Fee", value=limpiar_moneda(d_val['% FEE'])), ce5.number_input("TC", value=limpiar_moneda(d_val['TIPO CAMBIO']))
                    if st.form_submit_button("✅ Sincronizar"):
                        ws.update(f'A{idx_sel+2}:G{idx_sel+2}', [[target, u_nom.upper(), u_cos, u_pre, u_env, u_fee, u_tc]])
                        st.success("Ok."); st.rerun()
                if st.button("🗑️ Eliminar"): ws.delete_rows(int(idx_sel + 2)); st.rerun()

    with t_bulk:
        st.subheader("Carga por Lotes (v5.1 Fix)")
        up_file = st.file_uploader("Subir Excel:", type=['xlsx'])
        if up_file and st.button("🚀 Ejecutar Carga Segura"):
            try:
                # 1. Leer Excel
                df_bulk = pd.read_excel(up_file)
                # 2. Limpiar NaNs (Causantes del InvalidJSONError)
                # Reemplazamos NaNs por strings vacíos o ceros según corresponda
                df_bulk = df_bulk.replace({np.nan: '', None: ''})
                
                # 3. Asegurar que las columnas numéricas sean tratadas como tales
                # Si vienen como strings formateados en Excel, los limpiamos
                for col in ['COSTO USD', 'AMAZON', 'ENVIO', '% FEE', 'TIPO CAMBIO']:
                    if col in df_bulk.columns:
                        df_bulk[col] = df_bulk[col].apply(lambda x: limpiar_moneda(x))

                # 4. Convertir a lista y subir
                lista_datos = df_bulk.values.tolist()
                ws.append_rows(lista_datos)
                st.success(f"✅ Se han cargado {len(lista_datos)} registros exitosamente.")
                st.rerun()
            except Exception as ex:
                st.error(f"Error en carga: {ex}")

    st.divider()
    if not df_base.empty:
        df_v = df_full[['SKU', 'PRODUCTO', 'COSTO USD', 'AMAZON', 'ENVIO', '% FEE', 'TIPO CAMBIO', 'C_MXN', 'FEE_$', 'IVA_R', 'ISR_R', 'NETO_R', 'UTIL_$', 'MARG_P']].copy()
        df_v.columns = ['SKU', 'PRODUCTO', 'COSTO USD', 'AMAZON', 'ENVIO', '% FEE', 'TC', 'C_MXN', 'F_$', 'IVA', 'ISR', 'NETO', 'UTILIDAD', 'MARGEN %']
        q_g = st.text_input("🔍 Filtro global:").upper()
        if q_g: df_v = df_v[df_v['PRODUCTO'].str.contains(q_g) | df_v['SKU'].astype(str).str.contains(q_g)]
        fmt = {"COSTO USD": "${:,.2f}", "AMAZON": "${:,.2f}", "ENVIO": "${:,.2f}", "TC": "${:,.2f}", "C_MXN": "${:,.2f}", "F_$": "${:,.2f}", "IVA": "${:,.2f}", "ISR": "${:,.2f}", "NETO": "${:,.2f}", "UTILIDAD": "${:,.2f}", "MARGEN %": "{:.2f}%", "% FEE": "{:.2f}%"}
        def estilo(row):
            m = row['MARGEN %']
            idx = row.index.get_loc('MARGEN %')
            bg = '#551a1a' if m < 7 else ('#5e541e' if m < 9.99 else '#1a4d1a')
            res = [''] * len(row); res[idx] = f'background-color: {bg}; color: white; font-weight: bold;'
            return res
        st.dataframe(df_v.style.format(fmt).apply(estilo, axis=1), use_container_width=True, height=500, hide_index=True)
        if st.button("📄 PDF"):
            st.download_button("Bajar PDF", crear_pdf_listado(df_v), "reporte.pdf", "application/pdf")
