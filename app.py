import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import io
from fpdf import FPDF
from datetime import datetime

# =================================================================
# CALCUAMZ v4.3.12 - SISTEMA INTEGRAL DE GESTIÓN DAC0CEL
# =================================================================
# Desarrollado para: E-commerce Manager (sr.sicho)
# Objetivo: Control total de margen neto 10%, Bulk dinámico y PDF.
# =================================================================

st.set_page_config(
    layout="wide", 
    page_title="CalcuAMZ v4.3.12 | Dacocel", 
    page_icon="📦"
)

# --- 1. CONFIGURACIÓN DE CONEXIÓN (GOOGLE SHEETS) ---
def conectar_google_sheets():
    """Establece conexión con la base de datos central en la nube."""
    try:
        # Acceso a través de secretos de Streamlit para mayor seguridad
        gcp_info = st.secrets["gcp_service_account"]
        alcances = ["https://www.googleapis.com/auth/spreadsheets"]
        credenciales = Credentials.from_service_account_info(gcp_info, scopes=alcances)
        
        # ID de la hoja de cálculo proporcionado por el usuario
        client = gspread.authorize(credenciales)
        sheet_id = "1mF-9Ayv95PJmk4v8PrIDHf2-lRnHFZd5WOxQ__cb3Ss"
        return client.open_by_key(sheet_id).sheet1
    except Exception as error:
        st.error(f"⚠️ Error crítico de conexión: {error}")
        return None

# --- 2. FUNCIONES DE LIMPIEZA Y PROCESAMIENTO ---
def limpiar_valor_numerico(valor, valor_por_defecto=0.0):
    """Convierte entradas de texto o moneda a flotantes procesables."""
    try:
        if pd.isna(valor) or str(valor).strip() == "":
            return valor_por_defecto
        # Elimina símbolos comunes que rompen los cálculos
        limpio = str(valor).replace('$', '').replace(',', '').replace('%', '').strip()
        return float(limpio)
    except (ValueError, TypeError):
        return valor_por_defecto

def ejecutar_motor_calculo(fila):
    """
    FÓRMULA MAESTRA: Calcula el precio necesario para un margen NETO del 10%.
    Considera: Fee Amazon, Envío, Retenciones (IVA/ISR) y Costo USD/MXN.
    """
    try:
        # Extracción de variables desde la fila de datos
        costo_usd = limpiar_valor_numerico(fila.get('COSTO USD', 0))
        precio_amazon_manual = limpiar_valor_numerico(fila.get('AMAZON', 0))
        comision_fee_pct = limpiar_valor_numerico(fila.get('% FEE', 4.0))
        costo_envio = limpiar_valor_numerico(fila.get('ENVIO', 80.0))
        tc_aplicado = limpiar_valor_numerico(fila.get('TIPO CAMBIO', 18.00))
        
        # Conversión a moneda local
        costo_total_mxn = costo_usd * tc_aplicado
        fee_decimal = comision_fee_pct / 100
        
        # Constante fiscal de retención: (8% IVA + 2.5% ISR) / 1.16
        # Este valor representa el impacto real de las retenciones sobre el precio bruto.
        tasa_retencion_real = 0.09051724 
        
        # --- CÁLCULO DE PRECIO OBJETIVO (AUTO-PRICING) ---
        # Si el usuario ingresa 0, el sistema busca el 10% de margen NETO exacto.
        if precio_amazon_manual <= 0:
            # Para que Margen = 10%, el Costo debe ser el 90% del Neto Recibido.
            neto_necesario = costo_total_mxn / 0.90
            # Despeje: Precio = (Neto + Envío) / (1 - Fee - Retenciones)
            precio_final_amazon = (neto_necesario + costo_envio) / (1 - fee_decimal - tasa_retencion_real)
        else:
            precio_final_amazon = precio_amazon_manual

        # --- DESGLOSE DE RESULTADOS ---
        monto_fee = precio_final_amazon * fee_decimal
        monto_base_iva = precio_final_amazon / 1.16
        monto_ret_iva = monto_base_iva * 0.08
        monto_ret_isr = monto_base_iva * 0.025
        
        # Lo que realmente llega a la cuenta bancaria de Dacocel
        neto_final_recibido = precio_final_amazon - monto_fee - costo_envio - monto_ret_iva - monto_ret_isr
        ganancia_bruta = neto_final_recibido - costo_total_mxn
        
        # Margen calculado sobre el dinero real recibido (Neto)
        porcentaje_margen_neto = (ganancia_bruta / neto_final_recibido) * 100 if neto_final_recibido > 0 else 0
        
        return pd.Series([
            precio_final_amazon, 
            costo_total_mxn, 
            monto_fee, 
            monto_ret_iva, 
            monto_ret_isr, 
            neto_final_recibido, 
            ganancia_bruta, 
            porcentaje_margen_neto
        ])
    except Exception:
        return pd.Series([0.0] * 8)

# --- 3. GENERACIÓN DE REPORTES (PDF) ---
def generar_pdf_precios(dataframe_maestro):
    """Crea un documento PDF profesional con los precios actuales."""
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(200, 10, txt="DACOCEL - LISTADO MAESTRO DE PRECIOS", ln=True, align='C')
    pdf.set_font("Arial", size=10)
    pdf.cell(200, 10, txt=f"Fecha de reporte: {datetime.now().strftime('%Y-%m-%d %H:%M')}", ln=True, align='C')
    pdf.ln(10)
    
    # Cabeceras
    pdf.set_fill_color(30, 30, 30)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(30, 10, "SKU", 1, 0, 'C', True)
    pdf.cell(90, 10, "PRODUCTO", 1, 0, 'C', True)
    pdf.cell(35, 10, "PRECIO AMZ", 1, 0, 'C', True)
    pdf.cell(35, 10, "MARGEN %", 1, 1, 'C', True)
    
    # Filas
    pdf.set_text_color(0, 0, 0)
    for i, row in dataframe_maestro.iterrows():
        pdf.cell(30, 8, str(row['SKU']), 1)
        pdf.cell(90, 8, str(row['PRODUCTO'])[:45], 1)
        pdf.cell(35, 8, f"${row['AMAZON']:,.2f}", 1, 0, 'R')
        pdf.cell(35, 8, f"{row['MARGEN %']:.2f}%", 1, 1, 'R')
    
    return pdf.output(dest='S').encode('latin-1')

# --- 4. DISEÑO VISUAL Y ESTILOS ---
def aplicar_formato_semaforo(fila_completa):
    """Define el color de fondo de la celda de margen basado en rentabilidad."""
    estilos_celda = [''] * len(fila_completa)
    if 'MARGEN %' in fila_completa.index:
        valor_margen = fila_completa['MARGEN %']
        indice_columna = fila_completa.index.get_loc('MARGEN %')
        
        # Escala Dacocel: Rojo (Peligro) | Amarillo (Aceptable) | Verde (Objetivo 10%)
        if valor_margen < 7.0:
            color_hex = '#551a1a' # Rojo oscuro
        elif valor_margen < 9.99:
            color_hex = '#5e541e' # Ámbar/Mostaza
        else:
            color_hex = '#1a4d1a' # Verde bosque
            
        estilos_celda[indice_columna] = f'background-color: {color_hex}; color: white; font-weight: bold;'
    return estilos_celda

# --- 5. LÓGICA DE ACCESO (LOGIN) ---
USUARIOS_AUTORIZADOS = {
    "admin": "amazon123", 
    "dav": "ventas2026", 
    "dax": "amazon2026", 
    "cesar": "ventas789"
}

if 'autenticado' not in st.session_state:
    st.session_state.autenticado = False

if not st.session_state.autenticado:
    st.title("🔐 Acceso al Sistema Dacocel")
    with st.container():
        user_input = st.text_input("Usuario (Mánager)").lower().strip()
        pass_input = st.text_input("Contraseña de Acceso", type="password")
        if st.button("Ingresar al Dashboard"):
            if user_input in USUARIOS_AUTORIZADOS and USUARIOS_AUTORIZADOS[user_input] == pass_input:
                st.session_state.autenticado = True
                st.session_state.user_actual = user_input
                st.rerun()
            else:
                st.error("⚠️ Credenciales no reconocidas por el sistema.")
else:
    # --- INICIO DE INTERFAZ PRINCIPAL ---
    hoja_trabajo = conectar_google_sheets()
    datos_crudos = hoja_trabajo.get_all_records() if hoja_trabajo else []
    df_global = pd.DataFrame(datos_crudos) if datos_crudos else pd.DataFrame()

    if not df_global.empty:
        # Limpieza de nombres de columnas (Todo a mayúsculas y sin espacios)
        df_global.columns = [str(c).upper().strip() for c in df_global.columns]
        
        # Procesamiento masivo de cálculos financieros
        resultados_motor = df_global.apply(ejecutar_motor_calculo, axis=1)
        resultados_motor.columns = [
            'AMZ_CALC', 'COSTO_MXN_VAL', 'FEE_VAL', 
            'IVA_VAL', 'ISR_VAL', 'NETO_VAL', 
            'UTIL_VAL', 'MARGEN_VAL'
        ]
        
        # Consolidación de datos calculados con datos originales
        df_maestro = pd.concat([df_global, resultados_motor], axis=1)
        # Reemplazar ceros por el precio autocalculado
        df_maestro['AMAZON'] = df_maestro.apply(
            lambda x: x['AMZ_CALC'] if limpiar_valor_numerico(x['AMAZON']) <= 0 else x['AMAZON'], 
            axis=1
        )

    st.title("📊 Master Dashboard v4.3.12 | Dacocel")
    st.sidebar.write(f"Conectado como: **{st.session_state.user_actual.upper()}**")
    if st.sidebar.button("Cerrar Sesión"):
        st.session_state.autenticado = False
        st.rerun()

    # --- NAVEGACIÓN POR MÓDULOS ---
    tab_nuevo, tab_gestion, tab_bulk = st.tabs([
        "➕ Registrar Producto", 
        "✏️ Gestión de Inventario", 
        "📂 Operaciones Masivas"
    ])

    # MODULO 1: AGREGAR NUEVO (CON VALIDACIÓN DE DUPLICADOS)
    with tab_nuevo:
        with st.form("form_alta"):
            st.subheader("Entrada de Nuevo Stock")
            c_header_1, c_header_2 = st.columns(2)
            sku_input = c_header_1.text_input("SKU del Producto (Código Único)").strip()
            nom_input = c_header_2.text_input("Nombre / Descripción Comercial").upper()
            
            c1, c2, c3, c4, c5 = st.columns(5)
            f_costo = c1.number_input("Costo (USD)", min_value=0.0, format="%.2f")
            f_precio = c2.number_input("Precio Amazon (0 = Auto-Precio 10%)", min_value=0.0)
            f_envio = c3.number_input("Costo Envío (MXN)", value=80.0)
            f_fee = c4.number_input("% Comisión Fee", value=4.0)
            f_tc = c5.number_input("Tipo de Cambio Hoy", value=18.0)
            
            if st.form_submit_button("🚀 Registrar en Base de Datos"):
                if not sku_input or not nom_input:
                    st.error("Faltan datos obligatorios (SKU o Nombre).")
                elif not df_global.empty and str(sku_input) in df_global['SKU'].astype(str).values:
                    st.warning(f"⚠️ El SKU '{sku_input}' ya existe. Usa el módulo de edición.")
                else:
                    hoja_trabajo.append_row([sku_input, nom_input, f_costo, f_precio, f_envio, f_fee, f_tc])
                    st.success("✅ Registro guardado exitosamente.")
                    st.rerun()

    # MODULO 2: EDITAR / ELIMINAR (GESTIÓN INDIVIDUAL)
    with tab_gestion:
        if not df_global.empty:
            st.subheader("Editor de Atributos")
            lista_busqueda = (df_maestro['SKU'].astype(str) + " - " + df_maestro['PRODUCTO']).tolist()
            item_seleccionado = st.selectbox("Seleccione un producto para modificar:", lista_busqueda)
            
            sku_edit = str(item_seleccionado).split(" - ")[0]
            indice_real = df_maestro[df_maestro['SKU'].astype(str) == sku_edit].index[0]
            data_actual = df_maestro.iloc[indice_real]
            
            with st.form("form_edicion_pro"):
                e_nombre = st.text_input("Nombre Producto", value=str(data_actual['PRODUCTO']))
                ce1, ce2, ce3, ce4, ce5 = st.columns(5)
                e_costo = ce1.number_input("Costo USD", value=limpiar_valor_numerico(data_actual['COSTO USD']))
                e_precio = ce2.number_input("Precio AMZ", value=limpiar_valor_numerico(data_actual['AMAZON']))
                e_envio = ce3.number_input("Envío", value=limpiar_valor_numerico(data_actual['ENVIO']))
                e_fee = ce4.number_input("% Fee", value=limpiar_valor_numerico(data_actual['% FEE']))
                e_tc = ce5.number_input("TC", value=limpiar_valor_numerico(data_actual['TIPO CAMBIO']))
                
                if st.form_submit_button("💾 Guardar Cambios"):
                    # Actualización de rango específico en Google Sheets (Fila = Indice + 2 por cabecera y base 1)
                    rango = f'A{indice_real+2}:G{indice_real+2}'
                    hoja_trabajo.update(rango, [[sku_edit, e_nombre.upper(), e_costo, e_precio, e_envio, e_fee, e_tc]])
                    st.success("Sincronización completa.")
                    st.rerun()
            
            if st.button("🗑️ ELIMINAR PRODUCTO PERMANENTEMENTE"):
                hoja_trabajo.delete_rows(int(indice_real + 2))
                st.warning("Producto borrado de la base de datos.")
                st.rerun()
        else:
            st.info("La base de datos está vacía.")

    # MODULO 3: BULK (CARGA MASIVA CON TC VARIABLE)
    with tab_bulk:
        st.subheader("Carga Masiva de Inventario")
        col_bulk_1, col_bulk_2 = st.columns([2, 1])
        tc_bulk_dia = col_bulk_1.number_input("Definir Tipo de Cambio para la Plantilla:", value=18.0, step=0.01)
        
        # Generar DataFrame de ejemplo para la plantilla
        df_descarga = pd.DataFrame({
            'SKU': ['IP-16-PRO'], 
            'PRODUCTO': ['IPHONE 16 PRO 128GB RENOVADO'], 
            'COSTO USD': [675.0], 
            'AMAZON': [0.0], 
            'ENVIO': [80.0], 
            '% FEE': [4.0], 
            'TIPO CAMBIO': [tc_bulk_dia]
        })
        
        memoria_archivo = io.BytesIO()
        with pd.ExcelWriter(memoria_archivo, engine='xlsxwriter') as writer:
            df_descarga.to_excel(writer, index=False)
        
        st.download_button(
            label=f"📥 Descargar Plantilla Bulk (TC: {tc_bulk_dia})",
            data=memoria_archivo.getvalue(),
            file_name=f"plantilla_dacocel_TC_{tc_bulk_dia}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        
        st.divider()
        archivo_subido = st.file_uploader("Subir Excel completado (Dacocel Format):", type=['xlsx'])
        if archivo_subido and st.button("🚀 Procesar e Importar"):
            try:
                df_importado = pd.read_excel(archivo_subido)
                hoja_trabajo.append_rows(df_importado.values.tolist())
                st.success("Importación masiva exitosa.")
                st.rerun()
            except Exception as e:
                st.error(f"Fallo en la lectura del archivo: {e}")

    # --- 6. VISUALIZACIÓN DE TABLA MAESTRA ---
    st.divider()
    if not df_global.empty:
        st.subheader("📋 Consolidado Maestro de Operaciones")
        
        # Selección y renombrado de columnas para reporte visual
        df_visual = df_maestro[[
            'SKU', 'PRODUCTO', 'COSTO USD', 'AMAZON', 'ENVIO', '% FEE', 
            'TIPO CAMBIO', 'COSTO_MXN_VAL', 'FEE_VAL', 'IVA_VAL', 
            'ISR_VAL', 'NETO_VAL', 'UTIL_VAL', 'MARGEN_VAL'
        ]].copy()
        
        df_visual.columns = [
            'SKU', 'PRODUCTO', 'COSTO USD', 'AMAZON', 'ENVIO', '% FEE', 
            'TC', 'C_MXN', 'F_$', 'IVA', 'ISR', 'NETO', 'UTILIDAD', 'MARGEN %'
        ]
        
        # Buscador en tiempo real
        query = st.text_input("🔍 Filtrar tabla (SKU o Nombre):").upper()
        if query:
            df_visual = df_visual[df_visual['PRODUCTO'].str.contains(query) | df_visual['SKU'].astype(str).str.contains(query)]

        # Configuración de formatos de moneda y porcentaje
        diccionario_formatos = {
            "COSTO USD": "${:,.2f}", "AMAZON": "${:,.2f}", "ENVIO": "${:,.2f}", "TC": "${:,.2f}", 
            "C_MXN": "${:,.2f}", "F_$": "${:,.2f}", "IVA": "${:,.2f}", "ISR": "${:,.2f}", 
            "NETO": "${:,.2f}", "UTILIDAD": "${:,.2f}", "MARGEN %": "{:.2f}%", "% FEE": "{:.2f}%"
        }
        
        # Renderizado de Tabla Interactiva
        st.dataframe(
            df_visual.style.format(diccionario_formatos).apply(aplicar_formato_semaforo, axis=1), 
            use_container_width=True, 
            height=650, 
            hide_index=True
        )
        
        # Botón para descargar PDF
        if st.button("📄 Generar Reporte PDF para Socios"):
            datos_pdf = generar_pdf_precios(df_visual)
            st.download_button(
                label="⬇️ Descargar Reporte PDF",
                data=datos_pdf,
                file_name=f"Reporte_Dacocel_{datetime.now().strftime('%Y%m%d')}.pdf",
                mime="application/pdf"
            )
