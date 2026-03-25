import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import io
from fpdf import FPDF
from datetime import datetime

# =================================================================
# CALCUAMZ v4.3.15 - SISTEMA PROFESIONAL CON BÚSQUEDA AVANZADA
# =================================================================
# Empresa: Dacocel | Usuario: sr.sicho
# Módulos: Auth, Motor Fiscal, Validaciones, CRUD con Buscador, PDF.
# =================================================================

st.set_page_config(
    layout="wide", 
    page_title="CalcuAMZ v4.3.15 | Dacocel Master", 
    page_icon="📦"
)

# --- 1. CONFIGURACIÓN DE INFRAESTRUCTURA (NUBE) ---
def obtener_conexion_sheets():
    """Establece el enlace seguro con la base de datos centralizada."""
    try:
        # Credenciales desde st.secrets para producción
        info_servicio = st.secrets["gcp_service_account"]
        alcances = ["https://www.googleapis.com/auth/spreadsheets"]
        credenciales = Credentials.from_service_account_info(info_servicio, scopes=alcances)
        
        cliente = gspread.authorize(credenciales)
        # ID de la hoja de cálculo de Dacocel
        id_sheet = "1mF-9Ayv95PJmk4v8PrIDHf2-lRnHFZd5WOxQ__cb3Ss"
        return cliente.open_by_key(id_sheet).sheet1
    except Exception as error_con:
        st.error(f"❌ Error crítico de conexión: {error_con}")
        return None

# --- 2. MOTOR DE CÁLCULO FINANCIERO (MÉXICO - AMAZON) ---
def parse_float(valor, default=0.0):
    """Limpia formatos de moneda y texto para habilitar cálculos."""
    try:
        if pd.isna(valor) or str(valor).strip() == "":
            return default
        limpio = str(valor).replace('$', '').replace(',', '').replace('%', '').strip()
        return float(limpio)
    except:
        return default

def motor_calculo_dacocel(fila):
    """
    Calcula el precio de venta para obtener un 10.00% de margen NETO.
    Considera comisiones de Amazon y retenciones fiscales del SAT.
    """
    try:
        # Variables de entrada
        c_usd = parse_float(fila.get('COSTO USD', 0))
        p_amazon_in = parse_float(fila.get('AMAZON', 0))
        fee_pct = parse_float(fila.get('% FEE', 4.0))
        envio_mxn = parse_float(fila.get('ENVIO', 80.0))
        tipo_cambio = parse_float(fila.get('TIPO CAMBIO', 18.00))
        
        # Cálculos base
        costo_mxn_total = c_usd * tipo_cambio
        fee_decimal = fee_pct / 100
        
        # Coeficiente de retención (ISR + IVA) / 1.16
        tasa_fiscal_ret = 0.09051724 
        
        # LÓGICA AUTO-PRICING (10.00% NETO)
        if p_amazon_in <= 0:
            # Objetivo: Utilidad = 10% del Neto Recibido
            neto_objetivo = costo_mxn_total / 0.90
            # Despeje de precio bruto
            precio_sugerido = (neto_objetivo + envio_mxn) / (1 - fee_decimal - tasa_fiscal_ret)
        else:
            precio_sugerido = p_amazon_in

        # Desglose de flujo
        monto_fee = precio_sugerido * fee_decimal
        base_fiscal = precio_sugerido / 1.16
        monto_ret_iva = base_fiscal * 0.08
        monto_ret_isr = base_fiscal * 0.025
        
        # El Neto Recibido es lo que entra a banco después de Amazon y SAT
        neto_final = precio_sugerido - monto_fee - envio_mxn - monto_ret_iva - monto_ret_isr
        utilidad_mxn = neto_final - costo_mxn_total
        margen_final = (utilidad_mxn / neto_final) * 100 if neto_final > 0 else 0
        
        return pd.Series([
            precio_sugerido, costo_mxn_total, monto_fee, 
            monto_ret_iva, monto_ret_isr, neto_final, 
            utilidad_mxn, margen_final
        ])
    except:
        return pd.Series([0.0] * 8)

# --- 3. GENERACIÓN DE REPORTES PDF ---
def generar_reporte_pdf(df_final):
    """Crea un documento PDF profesional para revisión de socios."""
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 15)
    pdf.cell(190, 10, "DACOCEL - REPORTE MAESTRO DE PRECIOS", ln=True, align='C')
    pdf.set_font("Arial", 'I', 9)
    pdf.cell(190, 7, f"Generado: {datetime.now().strftime('%d/%m/%Y %H:%M')}", ln=True, align='C')
    pdf.ln(10)
    
    # Encabezados
    pdf.set_fill_color(30, 30, 30); pdf.set_text_color(255, 255, 255)
    pdf.set_font("Arial", 'B', 9)
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

# --- 4. GESTIÓN DE SEGURIDAD (AUTH) ---
USUARIOS = {
    "admin": "amazon123", 
    "dav": "ventas2026", 
    "dax": "amazon2026", 
    "cesar": "ventas789"
}

if 'auth_active' not in st.session_state:
    st.session_state.auth_active = False

if not st.session_state.auth_active:
    st.title("🔐 Acceso CalcuAMZ v4.3.15")
    u_log = st.text_input("Usuario").lower().strip()
    p_log = st.text_input("Contraseña", type="password")
    if st.button("Iniciar Sesión"):
        if u_log in USUARIOS and USUARIOS[u_log] == p_log:
            st.session_state.auth_active = True
            st.session_state.user_now = u_log
            st.rerun()
        else:
            st.error("Credenciales Incorrectas")
else:
    # --- APLICACIÓN PRINCIPAL ---
    hoja_datos = obtener_conexion_sheets()
    registros = hoja_datos.get_all_records() if hoja_datos else []
    df_db = pd.DataFrame(registros) if registros else pd.DataFrame()

    if not df_db.empty:
        # Normalizar cabeceras a mayúsculas
        df_db.columns = [str(c).upper().strip() for c in df_db.columns]
        # Ejecutar cálculos
        res_calc = df_db.apply(motor_calculo_dacocel, axis=1)
        res_calc.columns = ['AMZ_P', 'C_MXN', 'FEE_$', 'IVA_R', 'ISR_R', 'NETO_R', 'UTIL_$', 'MARG_P']
        df_full = pd.concat([df_db, res_calc], axis=1)
        # Reemplazar ceros por sugeridos
        df_full['AMAZON'] = df_full.apply(lambda x: x['AMZ_P'] if parse_float(x['AMAZON']) <= 0 else x['AMAZON'], axis=1)

    st.title("📊 Dacocel Master Dashboard v4.3.15")
    st.sidebar.info(f"Sesión: {st.session_state.user_now.upper()}")
    if st.sidebar.button("Log Out"):
        st.session_state.auth_active = False
        st.rerun()

    tab_add, tab_edit, tab_bulk = st.tabs(["➕ Nuevo Producto", "✏️ Gestión de Inventario", "📂 Carga Masiva"])

    # --- MÓDULO: AGREGAR (VALIDACIÓN DOBLE) ---
    with tab_add:
        with st.form("form_alta_dacocel"):
            st.subheader("Entrada de Nuevo Stock")
            col_h1, col_h2 = st.columns(2)
            new_sku = col_h1.text_input("SKU").strip()
            new_nom = col_h2.text_input("Nombre").upper().strip()
            
            c1, c2, c3, c4, c5 = st.columns(5)
            n_cos, n_pre, n_env, n_fee, n_tc = c1.number_input("Costo USD"), c2.number_input("Precio AMZ"), c3.number_input("Envío", 80.0), c4.number_input("% Fee", 4.0), c5.number_input("TC", 18.0)
            
            if st.form_submit_button("🚀 Registrar Producto"):
                if not new_sku or not new_nom:
                    st.error("Error: SKU y Nombre requeridos.")
                else:
                    # Chequeo preventivo de duplicados
                    dup_s = not df_db.empty and str(new_sku) in df_db['SKU'].astype(str).values
                    dup_n = not df_db.empty and str(new_nom) in df_db['PRODUCTO'].astype(str).values
                    if dup_s or dup_n:
                        st.warning(f"⚠️ El producto ya existe ({'SKU' if dup_s else 'Nombre'}).")
                    else:
                        hoja_datos.append_row([new_sku, new_nom, n_cos, n_pre, n_env, n_fee, n_tc])
                        st.success("✅ Guardado."); st.rerun()

    # --- MÓDULO: EDITAR / BORRAR (CON BARRA BUSCADORA) ---
    with tab_edit:
        if not df_db.empty:
            st.subheader("Búsqueda y Edición de Registro")
            
            # --- BARRA BUSCADORA PARA EL EDITOR ---
            query_edit = st.text_input("🔍 Escribe SKU o Nombre para buscar en el editor:").upper()
            
            # Filtrar la lista de opciones dinámicamente
            opciones_full = (df_full['SKU'].astype(str) + " - " + df_full['PRODUCTO']).tolist()
            if query_edit:
                opciones_filtradas = [opt for opt in opciones_full if query_edit in opt]
            else:
                opciones_filtradas = opciones_full
            
            if opciones_filtradas:
                seleccion = st.selectbox("Selecciona el producto exacto:", opciones_filtradas)
                
                sku_edit = str(seleccion).split(" - ")[0]
                idx_found = df_full[df_full['SKU'].astype(str) == sku_edit].index[0]
                d_act = df_full.iloc[idx_found]
                
                with st.form("form_update_dacocel"):
                    u_nom = st.text_input("Nombre Producto", value=str(d_act['PRODUCTO']))
                    ce1, ce2, ce3, ce4, ce5 = st.columns(5)
                    u_cos = ce1.number_input("Costo USD", value=parse_float(d_act['COSTO USD']))
                    u_pre = ce2.number_input("Precio AMZ", value=parse_float(d_act['AMAZON']))
                    u_env = ce3.number_input("Envío", value=parse_float(d_act['ENVIO']))
                    u_fee = ce4.number_input("% Fee", value=parse_float(d_act['% FEE']))
                    u_tc = ce5.number_input("TC", value=parse_float(d_act['TIPO CAMBIO']))
                    
                    if st.form_submit_button("✅ Sincronizar Cambios"):
                        hoja_datos.update(f'A{idx_found+2}:G{idx_found+2}', [[sku_edit, u_nom.upper(), u_cos, u_pre, u_env, u_fee, u_tc]])
                        st.success("Base de datos actualizada."); st.rerun()
                
                if st.button("🗑️ ELIMINAR ESTE PRODUCTO"):
                    hoja_datos.delete_rows(int(idx_found + 2))
                    st.warning("Registro borrado."); st.rerun()
            else:
                st.warning("No se encontraron coincidencias para la búsqueda.")
        else:
            st.info("No hay datos para gestionar.")

    # --- MÓDULO: CARGA MASIVA ---
    with tab_bulk:
        st.subheader("Operaciones Bulk")
        tc_p = st.number_input("TC para hoy:", value=18.0)
        df_p = pd.DataFrame({'SKU':['SKU-1'],'PRODUCTO':['NOMBRE'],'COSTO USD':[0.0],'AMAZON':[0.0],'ENVIO':[80.0],'% FEE':[4.0],'TIPO CAMBIO':[tc_p]})
        buf = io.BytesIO()
        with pd.ExcelWriter(buf) as wr: df_p.to_excel(wr, index=False)
        st.download_button(f"📥 Plantilla (TC {tc_p})", buf.getvalue(), "plantilla.xlsx")
        
        st.divider()
        file_up = st.file_uploader("Subir Archivo:", type=['xlsx'])
        if file_up and st.button("🚀 Procesar Bulk"):
            hoja_datos.append_rows(pd.read_excel(file_up).values.tolist())
            st.success("Importación exitosa."); st.rerun()

    # --- LISTADO MAESTRO VISUAL ---
    st.divider()
    if not df_db.empty:
        st.subheader("📋 Consolidado Maestro de Operaciones")
        df_vis = df_full[['SKU', 'PRODUCTO', 'COSTO USD', 'AMAZON', 'ENVIO', '% FEE', 'TIPO CAMBIO', 'C_MXN', 'FEE_$', 'IVA_R', 'ISR_R', 'NETO_R', 'UTIL_$', 'MARG_P']].copy()
        df_vis.columns = ['SKU', 'PRODUCTO', 'COSTO USD', 'AMAZON', 'ENVIO', '% FEE', 'TC', 'C_MXN', 'F_$', 'IVA', 'ISR', 'NETO', 'UTILIDAD', 'MARGEN %']
        
        # Filtro Global
        f_search = st.text_input("🔍 Filtro global de tabla:").upper()
        if f_search:
            df_vis = df_vis[df_vis['PRODUCTO'].str.contains(f_search) | df_vis['SKU'].astype(str).str.contains(f_search)]

        fmt_c = {"COSTO USD": "${:,.2f}", "AMAZON": "${:,.2f}", "ENVIO": "${:,.2f}", "TC": "${:,.2f}", "C_MXN": "${:,.2f}", "F_$": "${:,.2f}", "IVA": "${:,.2f}", "ISR": "${:,.2f}", "NETO": "${:,.2f}", "UTILIDAD": "${:,.2f}", "MARGEN %": "{:.2f}%", "% FEE": "{:.2f}%"}
        
        def semaforo(row):
            styles = [''] * len(row)
            m = row['MARGEN %']
            idx = row.index.get_loc('MARGEN %')
            bg = '#551a1a' if m < 7 else ('#5e541e' if m < 9.99 else '#1a4d1a')
            styles[idx] = f'background-color: {bg}; color: white; font-weight: bold;'
            return styles

        st.dataframe(df_vis.style.format(fmt_c).apply(semaforo, axis=1), use_container_width=True, height=600, hide_index=True)
        
        if st.button("📄 Generar PDF"):
            pdf_b = generar_reporte_pdf(df_vis)
            st.download_button("⬇️ Bajar Reporte", pdf_b, "reporte_precios.pdf", "application/pdf")
