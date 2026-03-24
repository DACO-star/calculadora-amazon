import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import io

# --- CalcuAMZ v3.6 (MASTER FIX: SIMULACIÓN REAL) ---
st.set_page_config(layout="wide", page_title="CalcuAMZ v3.6", page_icon="📦")

USUARIOS = {"admin": "amazon123", "dav": "ventas2026", "dax": "amazon2026", "cesar": "ventas789", "consulta": "lector2026"}

def conectar():
    try:
        info = st.secrets["gcp_service_account"]
        creds = Credentials.from_service_account_info(info, scopes=["https://www.googleapis.com/auth/spreadsheets"])
        return gspread.authorize(creds).open_by_key("1mF-9Ayv95PJmk4v8PrIDHf2-lRnHFZd5WOxQ__cb3Ss").sheet1
    except: return None

def calcular_detallado(p_amz, c_usd, t_c, p_fee, env):
    try:
        p_amz, c_usd, t_c, p_fee, env = map(float, [p_amz, c_usd, t_c, p_fee, env])
        costo_mxn = c_usd * t_c
        base_gravable = p_amz / 1.16
        neto = p_amz - (p_amz * (p_fee/100)) - abs(env) - (base_gravable * 0.105) # IVA+ISR
        utilidad = neto - costo_mxn
        margen = (utilidad / neto * 100) if neto > 0 else 0
        return utilidad, margen
    except: return 0.0, 0.0

# --- INICIALIZACIÓN ---
if 'auth' not in st.session_state: st.session_state.auth = False

if not st.session_state.auth:
    st.title("🔐 Acceso CalcuAMZ v3.6")
    u = st.text_input("Usuario").lower().strip()
    p = st.text_input("Clave", type="password")
    if st.button("Ingresar"):
        if u in USUARIOS and USUARIOS[u] == p:
            st.session_state.auth = True; st.session_state.user = u; st.rerun()
else:
    ws = conectar()
    df_raw = pd.DataFrame() # Definimos df_raw vacío por defecto para evitar NameError
    
    if ws:
        try:
            df_raw = pd.DataFrame(ws.get_all_records())
            if not df_raw.empty:
                df_raw.columns = [str(c).upper().strip() for c in df_raw.columns]
                for c in ['COSTO USD', 'AMAZON', 'ENVIO', '% FEE', 'TIPO CAMBIO']:
                    if c in df_raw.columns:
                        df_raw[c] = pd.to_numeric(df_raw[c], errors='coerce').fillna(0.0)
        except: st.error("Error al leer datos de la nube.")

    es_editor = st.session_state.user in ["admin", "dav", "dax", "cesar"]

    st.title("📊 Panel Maestro sr.sicho")

    if not df_raw.empty:
        # --- SECCIÓN 1: SIMULADOR ---
        st.subheader("1. Simulador de Estrategia")
        st.info("💡 Cambia el precio en **AMAZON** y presiona **Enter**. El margen se actualizará solo en tu pantalla.")

        # Calculamos los valores iniciales
        calcs = df_raw.apply(lambda r: calcular_detallado(r['AMAZON'], r['COSTO USD'], r['TIPO CAMBIO'], r['% FEE'], r['ENVIO']), axis=1)
        df_raw['UTILIDAD'] = calcs.apply(lambda x: x[0])
        df_raw['MARGEN %'] = calcs.apply(lambda x: x[1])

        # El Editor: Al cambiar AMAZON, Streamlit recalcula todo el script
        edited_df = st.data_editor(
            df_raw[['SKU', 'PRODUCTO', 'COSTO USD', 'TIPO CAMBIO', 'AMAZON', 'UTILIDAD', 'MARGEN %', 'ENVIO', '% FEE']],
            column_config={
                "SKU": st.column_config.TextColumn(disabled=True),
                "PRODUCTO": st.column_config.TextColumn(disabled=True, width="large"),
                "AMAZON": st.column_config.NumberColumn("AMAZON", format="$%.2f"),
                "UTILIDAD": st.column_config.NumberColumn(disabled=True, format="$%.2f"),
                "MARGEN %": st.column_config.NumberColumn(disabled=True, format="%.2f%%"),
                "COSTO USD": st.column_config.NumberColumn(disabled=True, format="$%.2f"),
                "TIPO CAMBIO": st.column_config.NumberColumn(disabled=True),
            },
            use_container_width=True, hide_index=True, key="sim_v36"
        )

        # RECALCULO INSTANTÁNEO: Esta es la clave para que tu jefe vea el cambio
        # Si detectamos que los datos en el editor cambiaron, recalculamos las columnas de utilidad
        actualizado = edited_df.apply(lambda r: calcular_detallado(r['AMAZON'], r['COSTO USD'], r['TIPO CAMBIO'], r['% FEE'], r['ENVIO']), axis=1)
        edited_df['UTILIDAD'] = actualizado.apply(lambda x: x[0])
        edited_df['MARGEN %'] = actualizado.apply(lambda x: x[1])

        # Botón para sincronizar la nube con lo simulado
        if es_editor:
            if st.button("🚀 GUARDAR NUEVOS PRECIOS EN GOOGLE SHEETS"):
                with st.spinner("Sincronizando..."):
                    for i, row in edited_df.iterrows():
                        if float(df_raw.at[i, 'AMAZON']) != float(row['AMAZON']):
                            ws.update_cell(i + 2, 4, float(row['AMAZON']))
                    st.success("¡Base de datos actualizada!"); st.rerun()

        st.divider()

        # --- SECCIÓN 2: GESTIÓN (Tus pestañas) ---
        if es_editor:
            st.subheader("2. Gestión de Inventario")
            t1, t2, t3 = st.tabs(["➕ Nuevo", "✏️ Editar/Borrar", "📂 Bulk"])
            
            with t1:
                with st.form("f_nuevo"):
                    sk = st.text_input("SKU").upper()
                    no = st.text_input("Nombre")
                    c1, c2, c3 = st.columns(3)
                    cos = c1.number_input("Costo USD", format="%.2f")
                    tc = c2.number_input("TC", value=18.50)
                    fe = c3.number_input("% Fee", value=10.0)
                    if st.form_submit_button("Guardar"):
                        ws.append_row([sk if sk else f"A-{len(df_raw)+1}", no.upper(), cos, 0, 0, fe, tc])
                        st.rerun()
            
            with t2:
                sel = st.selectbox("Elegir SKU", df_raw['SKU'].astype(str) + " - " + df_raw['PRODUCTO'])
                idx_sel = df_raw[df_raw['SKU'].astype(str) == sel.split(" - ")[0]].index[0]
                curr = df_raw.iloc[idx_sel]
                with st.form("f_edit"):
                    enom = st.text_input("Nombre", value=str(curr['PRODUCTO']))
                    ecos = st.number_input("Costo USD", value=float(curr['COSTO USD']))
                    etc = st.number_input("TC", value=float(curr.get('TIPO CAMBIO', 18.0)))
                    epre = st.number_input("Precio Amazon", value=float(curr['AMAZON']))
                    if st.form_submit_button("Actualizar"):
                        ws.update(f'A{idx_sel+2}:G{idx_sel+2}', [[curr['SKU'], enom.upper(), ecos, epre, curr['ENVIO'], curr['% FEE'], etc]])
                        st.rerun()
    else:
        st.warning("No hay datos cargados en la base.")
