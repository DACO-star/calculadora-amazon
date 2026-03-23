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

def calcular_valores(r):
    # Usamos .get para evitar el KeyError si falta una columna
    c_usd = float(r.get('COSTO USD', 0))
    p_amz = float(r.get('AMAZON', 0))
    p_fee = float(r.get('% FEE', 0))
    env = float(r.get('ENVIO', 0))

    costo_mxn = c_usd * TIPO_CAMBIO
    dinero_fee = p_amz * (p_fee / 100)
    base_gravable = p_amz / 1.16
    ret_iva = base_gravable * 0.08
    ret_isr = base_gravable * 0.025
    quedan = p_amz - dinero_fee - abs(env) - ret_iva - ret_isr
    utilidad = quedan - costo_mxn
    margen = (utilidad / quedan) * 100 if quedan > 0 else 0
    return pd.Series([costo_mxn, dinero_fee, base_gravable, ret_iva, ret_isr, quedan, utilidad, margen])

# --- 4. INICIO DE SESIÓN ---
if 'autenticado' not in st.session_state:
    st.session_state.autenticado = False

if not st.session_state.autenticado:
    st.title("🔐 Acceso")
    u = st.text_input("Usuario")
    p = st.text_input("Contraseña", type="password")
    if st.button("Ingresar"):
        if u in USUARIOS_VALIDOS and USUARIOS_VALIDOS[u] == p:
            st.session_state.autenticado = True
            st.rerun()
        else: st.error("Error")
else:
    # --- 5. CARGA Y LIMPIEZA ---
    try:
        gsheet = conectar_google_sheets()
        df_base = pd.DataFrame(gsheet.get_all_records())
        
        if not df_base.empty:
            # LIMPIEZA ANT-ERROR: Quitamos espacios y pasamos a mayúsculas los títulos
            df_base.columns = [str(c).strip().upper() for c in df_base.columns]
            
            # Aseguramos que las columnas necesarias existan
            cols_necesarias = ['SKU', 'PRODUCTO', 'COSTO USD', 'AMAZON', 'ENVIO', '% FEE']
            for col in cols_necesarias:
                if col not in df_base.columns:
                    st.error(f"⚠️ Falta la columna '{col}' en tu Excel.")
                    st.stop()
    except Exception as e:
        st.error(f"Error de conexión: {e}")
        st.stop()

    st.title("📦 Calculadora Amazon")

    tab1, tab2 = st.tabs(["➕ Agregar", "✏️ Editar / Borrar"])

    with tab1:
        with st.form("nuevo"):
            c1, c2 = st.columns(2)
            sku_n = c1.text_input("SKU")
            nom_n = c2.text_input("Nombre")
            # El prefix funcionará si actualizaste el requirements.txt
            costo_n = c1.number_input("Costo USD", format="%.2f", step=1.0, prefix="$")
            precio_n = c2.number_input("Precio Amazon MXN", format="%.2f", step=10.0, prefix="$")
            fee_n = c1.number_input("% Fee", value=10.0, step=0.1)
            envio_n = c2.number_input("Envío FBA MXN", format="%.2f", step=5.0, prefix="$")
            
            if st.form_submit_button("Guardar"):
                if sku_n and nom_n:
                    gsheet.append_row([sku_n.upper(), nom_n.upper(), costo_n, precio_n, envio_n, fee_n])
                    st.success("Guardado")
                    st.rerun()

    with tab2:
        if not df_base.empty:
            opciones = df_base['SKU'] + " - " + df_base['PRODUCTO']
            sel = st.selectbox("Producto", opciones)
            sku_s = sel.split(" - ")[0]
            idx_df = df_base[df_base['SKU'] == sku_s].index[0]
            prod = df_base.iloc[idx_df]

            with st.form("edit"):
                c1, c2 = st.columns(2)
                enom = c1.text_input("Nombre", value=str(prod['PRODUCTO']))
                ecos = c2.number_input("Costo USD", value=float(prod['COSTO USD']), format="%.2f", prefix="$")
                epre = c1.number_input("Precio Amazon", value=float(prod['AMAZON']), format="%.2f", prefix="$")
                efee = c2.number_input("% Fee", value=float(prod['% FEE']), step=0.1)
                eenv = c1.number_input("Envío FBA", value=float(prod['ENVIO']), format="%.2f", prefix="$")
                if st.form_submit_button("Actualizar"):
                    gsheet.update(range_name=f'A{idx_df+2}:F{idx_df+2}', 
                                 values=[[sku_s, enom.upper(), ecos, epre, eenv, efee]])
                    st.success("Actualizado")
                    st.rerun()
            
            if st.button(f"🗑️ Eliminar {sku_s}", use_container_width=True):
                gsheet.delete_rows(int(idx_df + 2))
                st.rerun()

    # --- 6. TABLA FINAL ---
    st.divider()
    if not df_base.empty:
        # Aplicamos el cálculo fila por fila
        df_res = df_base.apply(calcular_valores, axis=1)
        df_res.columns = ['COSTO MXN', 'FEE $', 'BASE GRAV', 'RET IVA', 'RET ISR', 'NETO', 'UTILIDAD', 'MARGEN %']
        df_final = pd.concat([df_base, df_res], axis=1)
        
        # Formato visual
        moneda = ['COSTO USD', 'AMAZON', 'ENVIO', 'COSTO MXN', 'FEE $', 'BASE GRAV', 'RET IVA', 'RET ISR', 'NETO', 'UTILIDAD']
        st.dataframe(df_final.style.format({c: "${:,.2f}" for c in moneda} | {"MARGEN %": "{:.2f}%", "% FEE": "{:.1f}%"}), use_container_width=True)
