import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import io
from fpdf import FPDF
from datetime import datetime

# =================================================================
# CALCUAMZ v4.3.14 - SISTEMA DE CONTROL TOTAL (ANTI-DUPLICADOS)
# =================================================================
# Empresa: Dacocel | Usuario: sr.sicho
# Módulos: Auth, Motor Fiscal, Validaciones, CRUD, Bulk, PDF.
# =================================================================

st.set_page_config(
    layout="wide", 
    page_title="CalcuAMZ v4.3.14 | Dacocel Master", 
    page_icon="📦"
)

# --- 1. CONEXIÓN Y SEGURIDAD ---
def obtener_conexion_sheets():
    """Establece el enlace seguro con la base de datos en la nube."""
    try:
        # Se asume que los secretos de GCP están configurados en Streamlit Cloud
        info_servicio = st.secrets["gcp_service_account"]
        alcances = ["https://www.googleapis.com/auth/spreadsheets"]
        credenciales = Credentials.from_service_account_info(info_servicio, scopes=alcances)
        
        cliente = gspread.authorize(credenciales)
        # ID único de la hoja de cálculo de Dacocel
        id_sheet = "1mF-9Ayv95PJmk4v8PrIDHf2-lRnHFZd5WOxQ__cb3Ss"
        return cliente.open_by_key(id_sheet).sheet1
    except Exception as error_con:
        st.error(f"❌ Error de conexión con Google Sheets: {error_con}")
        return None

# --- 2. MOTOR DE CÁLCULO FINANCIERO (OBJETIVO 10% NETO) ---
def parse_float(valor, default=0.0):
    """Limpia caracteres especiales para permitir operaciones matemáticas."""
    try:
        if pd.isna(valor) or str(valor).strip() == "":
            return default
        limpio = str(valor).replace('$', '').replace(',', '').replace('%', '').strip()
        return float(limpio)
    except:
        return default

def motor_calculo_dacocel(fila):
    """
    Calcula el precio necesario para obtener un 10.00% de utilidad sobre el NETO.
    Fórmula ajustada para retenciones de plataformas digitales en México.
    """
    try:
        # Extracción de parámetros
        c_usd = parse_float(fila.get('COSTO USD', 0))
        p_amazon_in = parse_float(fila.get('AMAZON', 0))
        fee_pct = parse_float(fila.get('% FEE', 4.0))
        envio_mxn = parse_float(fila.get('ENVIO', 80.0))
        tipo_cambio = parse_float(fila.get('TIPO CAMBIO', 18.00))
        
        # Conversión base
        costo_mxn_total = c_usd * tipo_cambio
        fee_decimal = fee_pct / 100
        
        # Constante fiscal: Retención ISR (2.5%) + Retención IVA (8%) sobre base (Precio / 1.16)
        # Coeficiente simplificado: (0.08 + 0.025) / 1.16 = 0.09051724
        tasa_fiscal_ret = 0.09051724 
        
        # LÓGICA DE PRECIO AUTOMÁTICO (OBJETIVO 10.00% NETO)
        # Si el usuario pone 0 en Amazon, el sistema despeja el precio de venta.
        if p_amazon_in <= 0:
            # Para que Margen = 10%, el Costo debe ser el 90% de lo que entra neto.
            neto_objetivo = costo_mxn_total / 0.90
            # Despeje: Precio = (Neto + Envío) / (1 - Fee - Tasa Fiscal)
            precio_sugerido = (neto_objetivo + envio_mxn) / (1 - fee_decimal - tasa_fiscal_ret)
        else:
            precio_sugerido = p_amazon_in

        # Desglose de egresos
        monto_fee = precio_sugerido * fee_decimal
        base_para_impuestos = precio_sugerido / 1.16
        monto_ret_iva = base_para_impuestos * 0.08
        monto_ret_isr = base_para_impuestos * 0.025
        
        # Resultado final (Dinero real en cuenta bancaria)
        neto_recibido = precio_sugerido - monto_fee - envio_mxn - monto_ret_iva - monto_ret_isr
        utilidad_real = neto_recibido - costo_mxn_total
        
        # Margen calculado sobre el flujo neto (Neto Recibido)
        margen_porcentual = (utilidad_real / neto_recibido) * 100 if neto_recibido > 0 else 0
        
        return pd.Series([
            precio_sugerido, 
            costo_mxn_total, 
            monto_fee, 
            monto_ret_iva, 
            monto_ret_isr, 
            neto_recibido, 
            utilidad_real, 
            margen_porcentual
        ])
    except:
        return pd.Series([0.0] * 8)

# --- 3. GENERACIÓN DE REPORTES PDF ---
def generar_reporte_pdf(df_final):
    """Crea un documento PDF con los precios y márgenes actuales para socios."""
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 15)
    pdf.cell(190, 10, "DACOCEL - REPORTE MAESTRO DE PRECIOS", ln=True, align='C')
    pdf.set_font("Arial", 'I', 9)
    pdf.cell(190, 7, f"Generado: {datetime.now().strftime('%d/%m/%Y %H:%M')}", ln=True, align='C')
    pdf.ln(10)
    
    # Encabezado de la tabla
    pdf.set_fill_color(30, 30, 30); pdf.set_text_color(255, 255, 255)
    pdf.set_font("Arial", 'B', 9)
    pdf.cell(30, 8, " SKU", 1, 0, 'L', True)
    pdf.cell(90, 8, " PRODUCTO", 1, 0, 'L', True)
    pdf.cell(35, 8, " PRECIO AMZ", 1, 0, 'C', True)
    pdf.cell(35, 8, " MARGEN %", 1, 1, 'C', True)
    
    # Contenido de la tabla
    pdf.set_text_color(0, 0, 0); pdf.set_font("Arial", '', 8)
    for _, fila in df_final.iterrows():
        pdf.cell(30, 7, str(fila['SKU']), 1)
        pdf.cell(90, 7, str(fila['PRODUCTO'])[:50], 1)
        pdf.cell(35, 7, f"${fila['AMAZON']:,.2f}", 1, 0, 'R')
        pdf.cell(35, 7, f"{fila['MARGEN %']:.2f}%", 1, 1, 'R')
    
    return pdf.output(dest='S').encode('latin-1')

# --- 4. GESTIÓN DE ACCESO (LOGIN) ---
USUARIOS = {
    "admin": "amazon123", 
    "dav": "ventas2026", 
    "dax": "amazon2026", 
    "cesar": "ventas789"
}

if 'auth_status' not in st.session_state:
    st.session_state.auth_status = False

if not st.session_state.auth_status:
    st.title("🔐 Acceso CalcuAMZ v4.3.14")
    user_log = st.text_input("Usuario").lower().strip()
    pass_log = st.text_input("Password", type="password")
    if st.button("Entrar al Sistema"):
        if user_log in USUARIOS and USUARIOS[user_log] == pass_log:
            st.session_state.auth_status = True
            st.session_state.user_active = user_log
            st.rerun()
        else:
            st.error("Credenciales Inválidas")
else:
    # --- INTERFAZ PRINCIPAL ---
    hoja_datos = obtener_conexion_sheets()
    registros = hoja_datos.get_all_records() if hoja_datos else []
    df_db = pd.DataFrame(registros) if registros else pd.DataFrame()

    if not df_db.empty:
        # Normalización de cabeceras
        df_db.columns = [str(c).upper().strip() for c in df_db.columns]
        # Procesamiento del motor de cálculo
        calc_res = df_db.apply(motor_calculo_dacocel, axis=1)
        calc_res.columns = ['AMZ_P', 'COSTO_MXN', 'FEE_$', 'IVA_R', 'ISR_R', 'NETO_R', 'UTIL_$', 'MARG_P']
        df_full = pd.concat([df_db, calc_res], axis=1)
        # Aplicar el precio calculado si el original es 0
        df_full['AMAZON'] = df_full.apply(lambda x: x['AMZ_P'] if parse_float(x['AMAZON']) <= 0 else x['AMAZON'], axis=1)

    st.title("📊 Dacocel Master Dashboard v4.3.14")
    st.sidebar.info(f"Sesión activa: {st.session_state.user_active.upper()}")
    if st.sidebar.button("Log Out"):
        st.session_state.auth_status = False
        st.rerun()

    tab_add, tab_edit, tab_bulk = st.tabs(["➕ Agregar Producto", "✏️ Editar / Borrar", "📂 Carga Masiva"])

    # --- MÓDULO: AGREGAR (VALIDACIÓN DOBLE SKU + NOMBRE) ---
    with tab_add:
        with st.form("new_entry_form"):
            st.subheader("Nuevo Registro de Inventario")
            f1, f2 = st.columns(2)
            n_sku = f1.text_input("SKU del Producto").strip()
            n_nom = f2.text_input("Nombre Completo").upper().strip()
            
            c1, c2, c3, c4, c5 = st.columns(5)
            n_cos = c1.number_input("Costo USD", format="%.2f")
            n_pre = c2.number_input("Precio AMZ (0 = Auto)", format="%.2f")
            n_env = c3.number_input("Envío MXN", value=80.0)
            n_fee = c4.number_input("% Comisión Fee", value=4.0)
            n_tc = c5.number_input("Tipo Cambio", value=18.0)
            
            if st.form_submit_button("🚀 Guardar Producto"):
                if not n_sku or not n_nom:
                    st.error("❌ El SKU y el Nombre son requeridos.")
                else:
                    # CHEQUEO DE DUPLICADOS EN AMBOS CAMPOS
                    existe_sku = not df_db.empty and str(n_sku) in df_db['SKU'].astype(str).values
                    existe_nom = not df_db.empty and str(n_nom) in df_db['PRODUCTO'].astype(str).values
                    
                    if existe_sku or existe_nom:
                        campo = "SKU" if existe_sku else "NOMBRE"
                        st.warning(f"⚠️ ATENCIÓN: Ya existe un registro con ese {campo}.")
                        # Mostrar referencia del producto existente
                        ref = df_db[df_db['SKU'].astype(str) == n_sku] if existe_sku else df_db[df_db['PRODUCTO'] == n_nom]
                        st.write("Datos del registro existente:")
                        st.json(ref.iloc[0].to_dict())
                    else:
                        hoja_datos.append_row([n_sku, n_nom, n_cos, n_pre, n_env, n_fee, n_tc])
                        st.success("✅ Producto agregado correctamente.")
                        st.rerun()

    # --- MÓDULO: EDITAR / ELIMINAR ---
    with tab_edit:
        if not df_db.empty:
            st.subheader("Gestión de Registro Individual")
            selector = (df_full['SKU'].astype(str) + " - " + df_full['PRODUCTO']).tolist()
            item_choice = st.selectbox("Seleccione un producto para modificar:", selector)
            
            sku_target = str(item_choice).split(" - ")[0]
            idx_row = df_full[df_full['SKU'].astype(str) == sku_target].index[0]
            data_now = df_full.iloc[idx_row]
            
            with st.form("edit_entry_form"):
                e_nom = st.text_input("Nombre", value=str(data_now['PRODUCTO']))
                ce1, ce2, ce3, ce4, ce5 = st.columns(5)
                e_cos = ce1.number_input("Costo USD", value=parse_float(data_now['COSTO USD']))
                e_pre = ce2.number_input("Precio AMZ", value=parse_float(data_now['AMAZON']))
                e_env = ce3.number_input("Envío", value=parse_float(data_now['ENVIO']))
                e_fee = ce4.number_input("% Fee", value=parse_float(data_now['% FEE']))
                e_tc = ce5.number_input("TC", value=parse_float(data_now['TIPO CAMBIO']))
                
                if st.form_submit_button("✅ Actualizar en Nube"):
                    # +2 compensa el índice base 0 y la fila de cabecera de Sheets
                    hoja_datos.update(f'A{idx_row+2}:G{idx_row+2}', [[sku_target, e_nom.upper(), e_cos, e_pre, e_env, e_fee, e_tc]])
                    st.success("Sincronización Exitosa.")
                    st.rerun()
            
            if st.button("🗑️ ELIMINAR REGISTRO DEFINITIVAMENTE"):
                hoja_datos.delete_rows(int(idx_row + 2))
                st.warning("Producto eliminado de la base de datos.")
                st.rerun()
        else:
            st.info("No hay datos registrados aún.")

    # --- MÓDULO: CARGA MASIVA (BULK) ---
    with tab_bulk:
        st.subheader("Operaciones Bulk con TC Variable")
        tc_plantilla = st.number_input("Define el TC para la plantilla de hoy:", value=18.0, step=0.01)
        
        # Plantilla dinámica
        df_p = pd.DataFrame({
            'SKU': ['IPH-X'], 'PRODUCTO': ['NOMBRE PRODUCTO'], 'COSTO USD': [0.0], 
            'AMAZON': [0.0], 'ENVIO': [80.0], '% FEE': [4.0], 'TIPO CAMBIO': [tc_plantilla]
        })
        
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine='xlsxwriter') as wr: df_p.to_excel(wr, index=False)
        st.download_button(f"📥 Descargar Plantilla TC {tc_plantilla}", buf.getvalue(), "plantilla_dacocel.xlsx")
        
        st.divider()
        archivo_up = st.file_uploader("Subir Excel (Formato Dacocel):", type=['xlsx'])
        if archivo_up and st.button("🚀 Iniciar Carga Masiva"):
            try:
                df_u = pd.read_excel(archivo_up)
                hoja_datos.append_rows(df_u.values.tolist())
                st.success("Datos importados con éxito.")
                st.rerun()
            except Exception as e_bulk:
                st.error(f"Error en el proceso masivo: {e_bulk}")

    # --- VISUALIZACIÓN MAESTRA Y REPORTES ---
    st.divider()
    if not df_db.empty:
        st.subheader("📋 Inventario Maestro de Precios y Rentabilidad")
        
        # Selección y orden final de columnas
        df_vis = df_full[[
            'SKU', 'PRODUCTO', 'COSTO USD', 'AMAZON', 'ENVIO', '% FEE', 
            'TIPO CAMBIO', 'COSTO_MXN', 'FEE_$', 'IVA_R', 'ISR_R', 'NETO_R', 'UTIL_$', 'MARG_P'
        ]].copy()
        
        df_vis.columns = [
            'SKU', 'PRODUCTO', 'COSTO USD', 'AMAZON', 'ENVIO', '% FEE', 
            'TC', 'C_MXN', 'F_$', 'IVA', 'ISR', 'NETO', 'UTILIDAD', 'MARGEN %'
        ]
        
        # Buscador Dinámico
        q_search = st.text_input("🔍 Filtro rápido (Nombre o SKU):").upper()
        if q_search:
            df_vis = df_vis[df_vis['PRODUCTO'].str.contains(q_search) | df_vis['SKU'].astype(str).str.contains(q_search)]

        # Diccionario de formato para la tabla
        fmt_table = {
            "COSTO USD": "${:,.2f}", "AMAZON": "${:,.2f}", "ENVIO": "${:,.2f}", "TC": "${:,.2f}", 
            "C_MXN": "${:,.2f}", "F_$": "${:,.2f}", "IVA": "${:,.2f}", "ISR": "${:,.2f}", 
            "NETO": "${:,.2f}", "UTILIDAD": "${:,.2f}", "MARGEN %": "{:.2f}%", "% FEE": "{:.2f}%"
        }
        
        def apply_semaforo(row):
            """Colores basados en el objetivo del 10.00%"""
            stls = [''] * len(row)
            if 'MARGEN %' in row.index:
                val = row['MARGEN %']
                idx = row.index.get_loc('MARGEN %')
                # Rojo (<7) | Ámbar (7-9.9) | Verde (>=10)
                bg = '#551a1a' if val < 7.0 else ('#5e541e' if val < 9.99 else '#1a4d1a')
                stls[idx] = f'background-color: {bg}; color: white; font-weight: bold;'
            return stls

        st.dataframe(
            df_vis.style.format(fmt_table).apply(apply_semaforo, axis=1), 
            use_container_width=True, 
            height=600, 
            hide_index=True
        )
        
        # BOTÓN PARA PDF
        if st.button("📄 Exportar Listado a PDF"):
            pdf_data = generar_reporte_pdf(df_vis)
            st.download_button(
                label="⬇️ Descargar Reporte PDF",
                data=pdf_data,
                file_name=f"Reporte_Dacocel_{datetime.now().strftime('%Y%m%d')}.pdf",
                mime="application/pdf"
            )
