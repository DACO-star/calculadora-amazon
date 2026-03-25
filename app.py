import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import io

# ==========================================
# CALCUAMZ v4.3.10 - CÓDIGO COMPLETO (NO COMPACTO)
# ==========================================

st.set_page_config(layout="wide", page_title="CalcuAMZ v4.3.10", page_icon="📦")

def conectar():
    try:
        # Uso de st.secrets para conexión segura con Google Cloud Platform
        info = st.secrets["gcp_service_account"]
        creds = Credentials.from_service_account_info(info, scopes=["https://www.googleapis.com/auth/spreadsheets"])
        # Conexión directa a la hoja de cálculo de Dacocel
        return gspread.authorize(creds).open_by_key("1mF-9Ayv95PJmk4v8PrIDHf2-lRnHFZd5WOxQ__cb3Ss").sheet1
    except Exception as e:
        st.error(f"Error de conexión: {e}")
        return None

def clean(val, def_val=0.0):
    """Limpia strings con símbolos de moneda para convertirlos a flotantes operativos."""
    try:
        if pd.isna(val) or str(val).strip() == "": return def_val
        v = str(val).replace('$', '').replace(',', '').strip()
        return float(v)
    except:
        return def_val

def calcular_detallado(r):
    """
    Calcula la corrida financiera completa.
    Si AMAZON es 0, calcula el precio para obtener exactamente 10% de margen neto.
    """
    try:
        c_usd = clean(r.get('COSTO USD', 0))
        p_amz_input = clean(r.get('AMAZON', 0))
        p_fee_pct = clean(r.get('% FEE', 4.0))
        env = clean(r.get('ENVIO', 80.0))
        t_c = clean(r.get('TIPO CAMBIO', 18.00))
        
        costo_mxn = c_usd * t_c
        fee_dec = p_fee_pct / 100
        
        # Constante de retenciones mexicanas para plataformas digitales (ISR + IVA)
        # (0.08 + 0.025) / 1.16 = 0.09051724
        const_ret = 0.09051724 
        
        # LÓGICA DE AUTO-PRECIO PARA MARGEN 10.00% NETO
        # El Neto debe ser el 111.11% del Costo para que el Margen sea 10% (1350/13500)
        if p_amz_input <= 0:
            neto_objetivo = costo_mxn / 0.90
            p_amz = (neto_objetivo + env) / (1 - fee_dec - const_ret)
        else:
            p_amz = p_amz_input

        # Desglose de salida
        dinero_fee = p_amz * fee_dec
        base_gravable = p_amz / 1.16
        ret_iva = base_gravable * 0.08
        ret_isr = base_gravable * 0.025
        
        neto_recibido = p_amz - dinero_fee - env - ret_iva - ret_isr
        utilidad = neto_recibido - costo_mxn
        
        # Margen calculado sobre el Neto Recibido
        margen = (utilidad / neto_recibido) * 100 if neto_recibido > 0 else 0
        
        return pd.Series([p_amz, costo_mxn, dinero_fee, ret_iva, ret_isr, neto_recibido, utilidad, margen])
    except:
        return pd.Series([0.0]*8)

def estilo_semaforo(row):
    """Aplica colores Dacocel según el margen neto obtenido."""
    estilos = [''] * len(row)
    if 'MARGEN %' in row.index:
        val = row['MARGEN %']
        idx = row.index.get_loc('MARGEN %')
        # Rojo: <7% | Ámbar: 7-9.9% | Verde: >=10%
        bg = '#551a1a' if val < 7.0 else ('#5e541e' if val < 9.99 else '#1a4d1a')
        estilos[idx] = f'background-color: {bg}; color: white; font-weight: bold;'
    return estilos

# --- SISTEMA DE AUTENTICACIÓN ---
USUARIOS = {
    "admin": "amazon123", 
    "dav": "ventas2026", 
    "dax": "amazon2026", 
    "cesar": "ventas789"
}

if 'auth' not in st.session_state:
    st.session_state.auth = False

if not st.session_state.auth:
    st.title("🔐 Acceso CalcuAMZ")
    u = st.text_input("Usuario").lower().strip()
    p = st.text_input("Password", type="password")
    if st.button("Entrar"):
        if u in USUARIOS and USUARIOS[u] == p:
            st.session_state.auth = True
            st.session_state.user = u
            st.rerun()
        else:
            st.error("Credenciales incorrectas")
else:
    # --- INICIO DE APLICACIÓN AUTORIZADA ---
    ws = conectar()
    data = ws.get_all_records() if ws else []
    df_raw = pd.DataFrame(data) if data else pd.DataFrame()

    if not df_raw.empty:
        # Estandarización de columnas
        df_raw.columns = [str(c).upper().strip() for c in df_raw.columns]
        
        # Asegurar existencia de columnas críticas
        cols_necesarias = ['SKU', 'PRODUCTO', 'COSTO USD', 'AMAZON', 'ENVIO', '% FEE', 'TIPO CAMBIO']
        for c in cols_necesarias:
            if c not in df_raw.columns:
                df_raw[c] = 0.0 if c != 'PRODUCTO' else "SIN NOMBRE"

        # Aplicar cálculos
        calc = df_raw.apply(calcular_detallado, axis=1)
        calc.columns = ['AMZ_P', 'C_MXN_V', 'FEE_V', 'IVA_V', 'ISR_V', 'NETO_V', 'UTIL_V', 'MARG_V']
        df_full = pd.concat([df_raw, calc], axis=1)

    st.title("📊 Dacocel Master Dashboard v4.3.10")
    
    # --- NAVEGACIÓN POR TABS ---
    t1, t2, t3 = st.tabs(["➕ Agregar Producto", "✏️ Editar / Eliminar", "📂 Carga Masiva (Bulk)"])

    # TAB 1: AGREGAR NUEVO PRODUCTO
    with t1:
        with st.form("form_nuevo"):
            st.subheader("Registrar en Inventario")
            col_a, col_b = st.columns(2)
            new_sku = col_a.text_input("SKU Único")
            new_nom = col_b.text_input("Nombre del Producto")
            
            c1, c2, c3, c4, c5 = st.columns(5)
            new_cos = c1.number_input("Costo USD", min_value=0.0, step=0.01)
            new_pre = c2.number_input("Precio Amazon (0 = Auto)", min_value=0.0, step=0.01)
            new_env = c3.number_input("Envío MXN", value=80.0)
            new_fee = c4.number_input("% Fee", value=4.0)
            new_tc = c5.number_input("T. Cambio", value=18.0)
            
            if st.form_submit_button("💾 Guardar Producto"):
                if new_sku and new_nom:
                    ws.append_row([new_sku, new_nom.upper(), new_cos, new_pre, new_env, new_fee, new_tc])
                    st.success(f"Producto {new_sku} agregado exitosamente.")
                    st.rerun()
                else:
                    st.error("SKU y Nombre son obligatorios.")

    # TAB 2: EDITAR O ELIMINAR EXISTENTE
    with t2:
        if not df_raw.empty:
            st.subheader("Modificar Producto Existente")
            lista_opciones = (df_full['SKU'].astype(str) + " - " + df_full['PRODUCTO']).tolist()
            seleccionado = st.selectbox("Busca por SKU o Nombre:", lista_opciones)
            
            sku_target = str(seleccionado).split(" - ")[0]
            indice_fila = df_full[df_full['SKU'].astype(str) == sku_target].index[0]
            datos_actuales = df_full.iloc[indice_fila]
            
            with st.form("form_edicion"):
                edit_nom = st.text_input("Nombre", value=str(datos_actuales['PRODUCTO']))
                ce1, ce2, ce3, ce4, ce5 = st.columns(5)
                edit_cos = ce1.number_input("Costo USD", value=clean(datos_actuales['COSTO USD']), step=0.01)
                edit_pre = ce2.number_input("Precio Amazon", value=clean(datos_actuales['AMAZON']), step=0.01)
                edit_env = ce3.number_input("Envío", value=clean(datos_actuales['ENVIO']), step=1.0)
                edit_fee = ce4.number_input("% Fee", value=clean(datos_actuales['% FEE']), step=0.1)
                edit_tc = ce5.number_input("T. Cambio", value=clean(datos_actuales['TIPO CAMBIO']), step=0.01)
                
                if st.form_submit_button("✅ Aplicar Cambios"):
                    ws.update(f'A{indice_fila+2}:G{indice_fila+2}', [[sku_target, edit_nom.upper(), edit_cos, edit_pre, edit_env, edit_fee, edit_tc]])
                    st.success("Cambios sincronizados con la nube.")
                    st.rerun()
            
            if st.button("❌ Eliminar Permanentemente"):
                ws.delete_rows(int(indice_fila + 2))
                st.warning(f"Producto {sku_target} eliminado.")
                st.rerun()
        else:
            st.info("No hay datos para editar.")

    # TAB 3: CARGA MASIVA (BULK)
    with t3:
        st.subheader("Gestión Masiva de Precios")
        tc_bulk_input = st.number_input("Define el TC para esta carga:", value=18.0, step=0.01)
        
        # Generación de la plantilla dinámica con el TC actual
        df_plantilla = pd.DataFrame({
            'SKU': ['M-EJEMPLO'], 
            'PRODUCTO': ['NOMBRE PRODUCTO'], 
            'COSTO USD': [0.0], 
            'AMAZON': [0.0], 
            'ENVIO': [80.0], 
            '% FEE': [4.0], 
            'TIPO CAMBIO': [tc_bulk_input]
        })
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df_plantilla.to_excel(writer, index=False)
        
        st.download_button(
            label=f"📥 Descargar Plantilla (TC: {tc_bulk_input})",
            data=output.getvalue(),
            file_name=f"plantilla_dacocel_tc_{tc_bulk_input}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        
        st.divider()
        archivo_excel = st.file_uploader("Sube tu Excel completado:", type=['xlsx'])
        if archivo_excel and st.button("🚀 Iniciar Carga a la Nube"):
            try:
                df_subida = pd.read_excel(archivo_excel)
                ws.append_rows(df_subida.values.tolist())
                st.success("Carga masiva finalizada correctamente.")
                st.rerun()
            except Exception as e:
                st.error(f"Error al procesar el archivo: {e}")

    # --- LISTADO MAESTRO (VISUALIZACIÓN FINAL) ---
    st.divider()
    if not df_raw.empty:
        st.subheader("📋 Consolidado de Precios y Márgenes")
        
        # Selección y orden de columnas finales
        df_final = df_full[[
            'SKU', 'PRODUCTO', 'COSTO USD', 'AMZ_P', 'ENVIO', '% FEE', 
            'TIPO CAMBIO', 'C_MXN_V', 'FEE_V', 'IVA_V', 'ISR_V', 'NETO_V', 'UTIL_V', 'MARG_V'
        ]].copy()
        
        df_final.columns = [
            'SKU', 'PRODUCTO', 'COSTO USD', 'AMAZON', 'ENVIO', '% FEE', 
            'TC', 'C_MXN', 'F_$', 'IVA', 'ISR', 'NETO', 'UTILIDAD', 'MARGEN %'
        ]
        
        # Diccionario de formatos visuales
        formateo_final = {
            "COSTO USD": "${:,.2f}", "AMAZON": "${:,.2f}", "ENVIO": "${:,.2f}", "TC": "${:,.2f}", 
            "C_MXN": "${:,.2f}", "F_$": "${:,.2f}", "IVA": "${:,.2f}", "ISR": "${:,.2f}", 
            "NETO": "${:,.2f}", "UTILIDAD": "${:,.2f}", "MARGEN %": "{:.2f}%", "% FEE": "{:.2f}%"
        }
        
        # Filtro de búsqueda rápida
        busqueda = st.text_input("🔍 Filtrar listado por nombre o SKU:").upper()
        if busqueda:
            df_final = df_final[df_final['PRODUCTO'].str.contains(busqueda) | df_final['SKU'].astype(str).str.contains(busqueda)]

        # Renderizado de la tabla con estilos
        st.dataframe(
            df_final.style.format(formateo_final).apply(estilo_semaforo, axis=1), 
            use_container_width=True, 
            height=600, 
            hide_index=True
        )
