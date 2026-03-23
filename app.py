import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

# --- 1. CONFIGURACIÓN DE SEGURIDAD (USUARIOS) ---
USUARIOS_VALIDOS = {"admin": "amazon123", "socio": "ventas2026"}

# --- 2. CONEXIÓN A GOOGLE SHEETS ---
def conectar_google_sheets():
    # Cargamos las credenciales desde los Secrets de Streamlit
    info_claves = st.secrets["gcp_service_account"]
    scope = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials.from_service_account_info(info_claves, scopes=scope)
    cliente = gspread.authorize(creds)
    
    # ID de tu hoja de cálculo
    sheet_id = "1mF-9Ayv95PJmk4v8PrIDHf2-lRnHFZd5WOxQ__cb3Ss"
    sheet = cliente.open_by_key(sheet_id).sheet1
    return sheet

# --- 3. LÓGICA DE CÁLCULO ---
TIPO_CAMBIO = 18.00

def calcular_valores(costo_usd, precio_amz, pct_fee, envio):
    costo_mxn = costo_usd * TIPO_CAMBIO
    dinero_fee = precio_amz * (pct_fee / 100)
    base_gravable = precio_amz / 1.16
    ret_iva = base_gravable * 0.08
    ret_isr = base_gravable * 0.025
    quedan = precio_amz - dinero_fee - abs(envio) - ret_iva - ret_isr
    utilidad = quedan - costo_mxn
    margen_retorno = (utilidad / quedan) * 100 if quedan > 0 else 0
    return costo_mxn, dinero_fee, base_gravable, ret_iva, ret_isr, quedan, utilidad, margen_retorno

# --- 4. INICIO DE SESIÓN ---
if 'autenticado' not in st.session_state:
    st.session_state.autenticado = False

if not st.session_state.autenticado:
    st.title("🔐 Sistema de Inventario Real-Time")
    usuario = st.text_input("Usuario")
    clave = st.text_input("Contraseña", type="password")
    if st.button("Ingresar"):
        if usuario in USUARIOS_VALIDOS and USUARIOS_VALIDOS[usuario] == clave:
            st.session_state.autenticado = True
            st.rerun()
        else:
            st.error("Acceso denegado")
else:
    # --- 5. CARGA DE DATOS DESDE GOOGLE SHEETS ---
    try:
        gsheet = conectar_google_sheets()
        # Traemos todos los registros del Excel
        data = gsheet.get_all_records()
        df_base = pd.DataFrame(data)
    except Exception as e:
        st.error(f"Error al conectar con Google Sheets: {e}")
        st.stop()

    st.sidebar.title("Menú")
    if st.sidebar.button("Cerrar Sesión"):
        st.session_state.autenticado = False
        st.rerun()

    st.title("📦 Panel de Productos Amazon")

    # --- 6. GESTIÓN DE PRODUCTOS (TABS) ---
    tab1, tab2 = st.tabs(["➕ Agregar Nuevo", "✏️ Editar Existente"])

    with tab1:
        with st.form("nuevo_prod"):
            c1, c2 = st.columns(2)
            sku_n = c1.text_input("SKU")
            nombre_n = c2.text_input("Nombre")
            costo_n = c1.number_input("Costo USD", min_value=0.0)
            precio_n = c2.number_input("Precio Amazon MXN", min_value=0.0)
            fee_n = c1.number_input("% Fee", value=10.0)
            envio_n = c2.number_input("Envío FBA MXN", min_value=0.0)
            
            if st.form_submit_button("Guardar en Google Sheets"):
                if sku_n and nombre_n:
                    # Añadir fila al final del Excel
                    gsheet.append_row([sku_n.upper(), nombre_n.upper(), costo_n, precio_n, envio_n, fee_n])
                    st.success("¡Producto guardado en la nube!")
                    st.rerun()

    with tab2:
        if not df_base.empty:
            opciones = df_base['SKU'] + " - " + df_base['PRODUCTO']
            seleccion = st.selectbox("Selecciona para editar", opciones)
            sku_sel = seleccion.split(" - ")[0]
            prod_actual = df_base[df_base['SKU'] == sku_sel].iloc[0]

            with st.form("edit_prod"):
                c1, c2 = st.columns(2)
                enombre = c1.text_input("Nombre", value=prod_actual['PRODUCTO'])
                ecosto = c2.number_input("Costo USD", value=float(prod_actual['COSTO USD']))
                eprecio = c1.number_input("Precio Amazon", value=float(prod_actual['AMAZON']))
                efee = c2.number_input("% Fee", value=float(prod_actual['% FEE']))
                eenvio = c1.number_input("Envío FBA", value=float(prod_actual['ENVIO']))
                
                if st.form_submit_button("Actualizar en Google Sheets"):
                    # Buscar la fila en el Excel (sumamos 2 porque gspread empieza en 1 y la fila 1 son encabezados)
                    fila_idx = df_base[df_base['SKU'] == sku_sel].index[0] + 2
                    gsheet.update(range_name=f'A{fila_idx}:F{fila_idx}', 
                                 values=[[sku_sel, enombre.upper(), ecosto, eprecio, eenvio, efee]])
                    st.success("¡Datos actualizados en la nube!")
                    st.rerun()

    # --- 7. TABLA DE ANÁLISIS ---
    st.divider()
    st.subheader("📊 Análisis de Rentabilidad")
    
    if not df_base.empty:
        df_analisis = df_base.copy()
        # Aplicamos cálculos
        res = df_analisis.apply(lambda r: calcular_valores(r['COSTO USD'], r['AMAZON'], r['% FEE'], r['ENVIO']), axis=1)
        cols_res = ['COSTO MXN', 'DINERO FEE', 'BASE GRAV', 'RET IVA', 'RET ISR', 'QUEDAN', 'UTILIDAD', 'MARGEN %']
        df_analisis[cols_res] = pd.DataFrame(res.tolist(), index=df_analisis.index)

        # Formato
        moneda = ['COSTO USD', 'AMAZON', 'ENVIO', 'COSTO MXN', 'DINERO FEE', 'BASE GRAV', 'RET IVA', 'RET ISR', 'QUEDAN', 'UTILIDAD']
        fmt = {col: "${:,.2f}" for col in moneda}
        fmt["MARGEN %"] = "{:.2f}%"
        fmt["% FEE"] = "{:.1f}%"
        st.dataframe(df_analisis.style.format(fmt), use_container_width=True)
    else:
        st.info("La base de datos está vacía.")
