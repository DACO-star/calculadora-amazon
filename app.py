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
    c_usd = float(costo_usd)
    p_amz = float(precio_amz)
    p_fee = float(pct_fee)
    env = float(envio)

    costo_mxn = c_usd * TIPO_CAMBIO
    dinero_fee = p_amz * (p_fee / 100)
    base_gravable = p_amz / 1.16
    ret_iva = base_gravable * 0.08
    ret_isr = base_gravable * 0.025
    quedan = p_amz - dinero_fee - abs(env) - ret_iva - ret_isr
    utilidad = quedan - costo_mxn
    margen = (utilidad / quedan) * 100 if quedan > 0 else 0
    return costo_mxn, dinero_fee, base_gravable, ret_iva, ret_isr, quedan, utilidad, margen

# --- 4. LOGIN ---
if 'autenticado' not in st.session_state:
    st.session_state.autenticado = False

if not st.session_state.autenticado:
    st.title("🔐 Acceso al Sistema")
    u = st.text_input("Usuario")
    p = st.text_input("Contraseña", type="password")
    if st.button("Ingresar"):
        if u in USUARIOS_VALIDOS and USUARIOS_VALIDOS[u] == p:
            st.session_state.autenticado = True
            st.rerun()
        else:
            st.error("Credenciales incorrectas")
else:
    # --- 5. DATOS ---
    try:
        gsheet = conectar_google_sheets()
        df_base = pd.DataFrame(gsheet.get_all_records())
        if not df_base.empty:
            df_base['SKU'] = df_base['SKU'].astype(str)
            df_base['PRODUCTO'] = df_base['PRODUCTO'].astype(str)
            for c in ['COSTO USD', 'AMAZON', 'ENVIO', '% FEE']:
                df_base[c] = pd.to_numeric(df_base[c], errors='coerce').fillna(0)
    except Exception as e:
        st.error(f"Error: {e}")
        st.stop()

    st.title("📦 Gestión de Inventario")

    tab1, tab2 = st.tabs(["➕ Agregar Producto", "✏️ Editar / Borrar"])

    with tab1:
        with st.form("nuevo"):
            c1, c2 = st.columns(2)
            sku_n = c1.text_input("SKU")
            nom_n = c2.text_input("Nombre")
            # El prefijo "$" ahora funcionará por la actualización de versión
            costo_n = c1.number_input("Costo USD", format="%.2f", step=1.0, prefix="$")
            precio_n = c2.number_input("Precio Amazon MXN", format="%.2f", step=10.0, prefix="$")
            fee_n = c1.number_input("% Fee", value=10.0, step=0.1)
            envio_n = c2.number_input("Envío FBA MXN", format="%.2f", step=5.0, prefix="$")
            
            if st.form_submit_button("Guardar en Nube"):
                if sku_n and nom_n:
                    gsheet.append_row([sku_n.upper(), nom_n.upper(), costo_n, precio_n, envio_n, fee_n])
                    st.success("¡Listo!")
                    st.rerun()

    with tab2:
        if not df_base.empty:
            opciones = df_base['SKU'] + " - " + df_base['PRODUCTO']
            sel = st.selectbox("Seleccionar producto", opciones)
            sku_s = sel.split(" - ")[0]
            prod = df_base[df_base['SKU'] == sku_s].iloc[0]

            with st.form("editar"):
                c1, c2 = st.columns(2)
                enom = c1.text_input("Nombre", value=str(prod['PRODUCTO']))
                ecos = c2.number_input("Costo USD", value=float(prod['COSTO USD']), format="%.2f", step=1.0, prefix="$")
                epre = c1.number_input("Precio Amazon", value=float(prod['AMAZON']), format="%.2f", step=10.0, prefix="$")
                efee = c2.number_input("% Fee", value=float(prod['% FEE']), step=0.1)
                eenv = c1.number_input("Envío FBA", value=float(prod['ENVIO']), format="%.2f", step=5.0, prefix="$")
                
                if st.form_submit_button("Actualizar"):
                    idx = df_base[df_base['SKU'] == sku_s].index[0] + 2
                    gsheet.update(range_name=f'A{idx}:F{idx}', 
                                 values=[[sku_s, enom.upper(), ecos, epre, eenv, efee]])
                    st.success("Actualizado")
                    st.rerun()
            
            # --- SECCIÓN DE BORRADO ---
            st.warning("⚠️ Zona de Peligro")
            if st.button(f"🗑️ Eliminar permanentemente {sku_s}", use_container_width=True):
                idx = df_base[df_base['SKU'] == sku_s].index[0] + 2
                gsheet.delete_rows(idx)
                st.success("Producto eliminado del Excel")
                st.rerun()

    # --- TABLA FINAL ---
    st.divider()
    if not df_base.empty:
        df_c = df_base.copy()
        res = df_c.apply(lambda r: calcular_valores(r['COSTO USD'], r['AMAZON'], r['% FEE'], r['ENVIO']), axis=1)
        cols = ['COSTO MXN', 'DINERO FEE', 'BASE GRAV', 'RET IVA', 'RET ISR', 'QUEDAN', 'UTILIDAD', 'MARGEN %']
        df_c[cols] = pd.DataFrame(res.tolist(), index=df_c.index)
        
        mon = ['COSTO USD', 'AMAZON', 'ENVIO', 'COSTO MXN', 'DINERO FEE', 'BASE GRAV', 'RET IVA', 'RET ISR', 'QUEDAN', 'UTILIDAD']
        st.dataframe(df_c.style.format({c: "${:,.2f}" for c in mon} | {"MARGEN %": "{:.2f}%", "% FEE": "{:.1f}%"}), use_container_width=True)
