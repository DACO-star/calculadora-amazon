import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

# --- 1. CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(layout="wide", page_title="Calculadora Amazon Pro")

# --- LISTA DE USUARIOS ACTUALIZADA ---
USUARIOS = {
    "admin": "amazon123", 
    "dav": "ventas2026",
    "dax": "amazon2026",
    "cesar": "ventas789"
}

TIPO_CAMBIO = 18.00

def conectar():
    info = st.secrets["gcp_service_account"]
    scope = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials.from_service_account_info(info, scopes=scope)
    return gspread.authorize(creds).open_by_key("1mF-9Ayv95PJmk4v8PrIDHf2-lRnHFZd5WOxQ__cb3Ss").sheet1

def calcular_detallado(r):
    c_usd = float(r.get('COSTO USD', 0))
    p_amz = float(r.get('AMAZON', 0))
    p_fee = float(r.get('% FEE', 0))
    env = float(r.get('ENVIO', 0))
    costo_mxn = c_usd * TIPO_CAMBIO
    dinero_fee = p_amz * (p_fee / 100)
    base_gravable = p_amz / 1.16
    ret_iva = base_gravable * 0.08
    ret_isr = base_gravable * 0.025
    neto = p_amz - dinero_fee - abs(env) - ret_iva - ret_isr
    utilidad = neto - costo_mxn
    margen = (utilidad / neto) * 100 if neto > 0 else 0
    return pd.Series([costo_mxn, dinero_fee, ret_iva, ret_isr, neto, utilidad, margen])

# --- 2. LÓGICA DE LOGIN ---
if 'auth' not in st.session_state: 
    st.session_state.auth = False
    st.session_state.user = ""

if not st.session_state.auth:
    st.title("🔐 Acceso al Sistema")
    u = st.text_input("Usuario").lower().strip()
    p = st.text_input("Clave", type="password")
    if st.button("Ingresar"):
        if u in USUARIOS and USUARIOS[u] == p:
            st.session_state.auth = True
            st.session_state.user = u
            st.rerun()
        else:
            st.error("Usuario o clave incorrectos")
else:
    # --- BARRA LATERAL ---
    with st.sidebar:
        st.write(f"👤 Usuario: **{st.session_state.user.upper()}**")
        if st.button("Cerrar Sesión"):
            st.session_state.auth = False
            st.session_state.user = ""
            st.rerun()
    
    # --- 3. DATOS ---
    try:
        ws = conectar()
        df_raw = pd.DataFrame(ws.get_all_records())
        if not df_raw.empty:
            df_raw.columns = [str(c).strip().upper() for c in df_raw.columns]
    except Exception as e:
        st.error(f"Error de conexión: {e}")
        st.stop()

    st.title("📦 Gestión de Inventario y Rentabilidad")
    
    t1, t2 = st.tabs(["➕ Agregar Producto", "✏️ Editar / Borrar"])

    with t1:
        with st.form("nuevo"):
            c1, c2, c3 = st.columns(3)
            sk = c1.text_input("SKU")
            no = c2.text_input("Nombre Producto")
            co = c3.number_input("Costo USD", format="%.2f")
            pr = c1.number_input("Precio Amazon MXN", format="%.2f")
            fe = c2.number_input("% Fee", value=10.0)
            en = c3.number_input("Envío FBA MXN", format="%.2f")
            if st.form_submit_button("Guardar en Nube"):
                if sk and no:
                    ws.append_row([sk.upper(), no.upper(), co, pr, en, fe])
                    st.success("¡Guardado!")
                    st.rerun()

    with t2:
        if not df_raw.empty:
            ops = df_raw['SKU'].astype(str) + " - " + df_raw['PRODUCTO'].astype(str)
            sel = st.selectbox("Selecciona para modificar", ops)
            sku_sel = sel.split(" - ")[0]
            idx = df_raw[df_raw['SKU'].astype(str) == sku_sel].index[0]
            curr = df_raw.iloc[idx]

            with st.form("edit"):
                col_e1, col_e2 = st.columns(2)
                enom = col_e1.text_input("Nombre", value=str(curr['PRODUCTO']))
                ecos = col_e2.number_input("Costo USD", value=float(curr['COSTO USD']), format="%.2f")
                epre = col_e1.number_input("Precio Amazon MXN", value=float(curr['AMAZON']), format="%.2f")
                efee = col_e2.number_input("% Fee", value=float(curr['% FEE']))
                eenv = col_e1.number_input("Envío FBA", value=float(curr['ENVIO']), format="%.2f")
                if st.form_submit_button("Actualizar Datos"):
                    ws.update(range_name=f'A{idx+2}:F{idx+2}', 
                             values=[[sku_sel, enom.upper(), ecos, epre, eenv, efee]])
                    st.success("¡Actualizado!")
                    st.rerun()
            
            # Solo admin y dav pueden borrar
            if st.session_state.user in ["admin", "dav"]:
                if st.button("🗑️ Eliminar Producto"):
                    ws.delete_rows(int(idx + 2))
                    st.rerun()

    # --- 4. BUSCADOR Y TABLA ---
    st.divider()
    st.subheader("📊 Análisis de Rentabilidad")
    
    if not df_raw.empty:
        # Buscador
        busqueda = st.text_input("🔍 Buscar por SKU o Nombre", "").strip().upper()
        
        # Cálculos
        res = df_raw.apply(calcular_detallado, axis=1)
        res.columns = ['COSTO MXN', 'FEE $', 'RET IVA', 'RET ISR', 'NETO RECIBIDO', 'UTILIDAD', 'MARGEN %']
        df_final = pd.concat([df_raw, res], axis=1)
        
        # Filtro de búsqueda
        if busqueda:
            mask = df_final['SKU'].astype(str).str.contains(busqueda) | \
                   df_final['PRODUCTO'].astype(str).str.contains(busqueda)
            df_mostrar = df_final[mask]
        else:
            df_mostrar = df_final

        # Resumen rápido sobre la tabla
        c1, c2, c3 = st.columns(3)
        c1.metric("Productos encontrados", len(df_mostrar))
        c2.metric("Utilidad Total (Filtro)", f"${df_mostrar['UTILIDAD'].sum():,.2f}")
        c3.metric("Margen Promedio", f"{df_mostrar['MARGEN %'].mean():,.2f}%")

        # Visualización de tabla
        money_cols = ['COSTO USD','AMAZON','ENVIO','COSTO MXN','FEE $','RET IVA','RET ISR','NETO RECIBIDO','UTILIDAD']
        st.dataframe(
            df_mostrar.style.format({c: "${:,.2f}" for c in money_cols} | {"MARGEN %": "{:.2f}%"}),
            use_container_width=True,
            height=600
        )
    else:
        st.info("No hay datos para mostrar.")
