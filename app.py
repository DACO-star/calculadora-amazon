import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

# --- 1. CONFIGURACIÓN DE SEGURIDAD ---
USUARIOS_VALIDOS = {"admin": "amazon123", "socio": "ventas2026"}

# --- 2. CONEXIÓN A GOOGLE SHEETS ---
def conectar_google_sheets():
    info_claves = st.secrets["gcp_service_account"]
    scope = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials.from_service_account_info(info_claves, scopes=scope)
    cliente = gspread.authorize(creds)
    sheet_id = "1mF-9Ayv95PJmk4v8PrIDHf2-lRnHFZd5WOxQ__cb3Ss"
    sheet = cliente.open_by_key(sheet_id).sheet1
    return sheet

# --- 3. LÓGICA DE CÁLCULO ---
TIPO_CAMBIO = 18.00

def calcular_valores(costo_usd, precio_amz, pct_fee, envio):
    # Aseguramos que los valores sean números antes de calcular
    costo_usd = float(costo_usd)
    precio_amz = float(precio_amz)
    pct_fee = float(pct_fee)
    envio = float(envio)

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
    st.title("🔐 Acceso al Sistema")
    usuario = st.text_input("Usuario")
    clave = st.text_input("Contraseña", type="password")
    if st.button("Ingresar"):
        if usuario in USUARIOS_VALIDOS and USUARIOS_VALIDOS[usuario] == clave:
            st.session_state.autenticado = True
            st.rerun()
        else:
            st.error("Error de acceso")
else:
    # --- 5. CARGA Y LIMPIEZA DE DATOS ---
    try:
        gsheet = conectar_google_sheets()
        data = gsheet.get_all_records()
        df_base = pd.DataFrame(data)
        
        if not df_base.empty:
            # PARCHE DE SEGURIDAD: Convertir SKU y Producto a Texto, y el resto a Números
            df_base['SKU'] = df_base['SKU'].astype(str)
            df_base['PRODUCTO'] = df_base['PRODUCTO'].astype(str)
            cols_num = ['COSTO USD', 'AMAZON', 'ENVIO', '% FEE']
            for col in cols_num:
                df_base[col] = pd.to_numeric(df_base[col], errors='coerce').fillna(0)
    except Exception as e:
        st.error(f"Error de conexión: {e}")
        st.stop()

    st.sidebar.title("Menú")
    if st.sidebar.button("Cerrar Sesión"):
        st.session_state.autenticado = False
        st.rerun()

    st.title("📦 Inventario Amazon")

    # --- 6. GESTIÓN (TABS) ---
    tab1, tab2 = st.tabs(["➕ Agregar", "✏️ Editar"])

    with tab1:
        with st.form("nuevo"):
            c1, c2 = st.columns(2)
            sku_n = c1.text_input("SKU")
            nombre_n = c2.text_input("Nombre")
            costo_n = c1.number_input("Costo USD", min_value=0.0, format="%.2f")
            precio_n = c2.number_input("Precio Amazon MXN", min_value=0.0, format="%.2f")
            fee_n = c1.number_input("% Fee", value=10.0, format="%.1f")
            envio_n = c2.number_input("Envío FBA MXN", min_value=0.0, format="%.2f")
            
            if st.form_submit_button("Guardar"):
                if sku_n and nombre_n:
                    gsheet.append_row([sku_n.upper(), nombre_n.upper(), costo_n, precio_n, envio_n, fee_n])
                    st.success("Guardado en Google Sheets")
                    st.rerun()

    with tab2:
        if not df_base.empty:
            opciones = df_base['SKU'] + " - " + df_base['PRODUCTO']
            seleccion = st.selectbox("Seleccionar producto", opciones)
            sku_sel = seleccion.split(" - ")[0]
            prod = df_base[df_base['SKU'] == sku_sel].iloc[0]

            with st.form("editar"):
                c1, c2 = st.columns(2)
                enombre = c1.text_input("Nombre", value=str(prod['PRODUCTO']))
                ecosto = c2.number_input("Costo USD", value=float(prod['COSTO USD']))
                eprecio = c1.number_input("Precio Amazon", value=float(prod['AMAZON']))
                efee = c2.number_input("% Fee", value=float(prod['% FEE']))
                eenvio = c1.number_input("Envío FBA", value=float(prod['ENVIO']))
                
                if st.form_submit_button("Actualizar"):
                    fila = df_base[df_base['SKU'] == sku_sel].index[0] + 2
                    gsheet.update(range_name=f'A{fila}:F{fila}', 
                                 values=[[sku_sel, enombre.upper(), ecosto, eprecio, eenvio, efee]])
                    st.success("Actualizado")
                    st.rerun()

    # --- 7. TABLA ---
    st.divider()
    if not df_base.empty:
        df_calc = df_base.copy()
        res = df_calc.apply(lambda r: calcular_valores(r['COSTO USD'], r['AMAZON'], r['% FEE'], r['ENVIO']), axis=1)
        cols_res = ['COSTO MXN', 'DINERO FEE', 'BASE GRAV', 'RET IVA', 'RET ISR', 'QUEDAN', 'UTILIDAD', 'MARGEN %']
        df_calc[cols_res] = pd.DataFrame(res.tolist(), index=df_calc.index)

        fmt = {col: "${:,.2f}" for col in ['COSTO USD', 'AMAZON', 'ENVIO', 'COSTO MXN', 'DINERO FEE', 'BASE GRAV', 'RET IVA', 'RET ISR', 'QUEDAN', 'UTILIDAD']}
        fmt["MARGEN %"] = "{:.2f}%"; fmt["% FEE"] = "{:.1f}%"
        st.dataframe(df_calc.style.format(fmt), use_container_width=True)
