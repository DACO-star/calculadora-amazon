import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import io

# --- CalcuAMZ v3.5 (SIMULACIÓN INSTANTÁNEA) ---
st.set_page_config(layout="wide", page_title="CalcuAMZ v3.5", page_icon="📈")

USUARIOS = {"admin": "amazon123", "dav": "ventas2026", "dax": "amazon2026", "cesar": "ventas789", "consulta": "lector2026"}

def conectar():
    try:
        info = st.secrets["gcp_service_account"]
        creds = Credentials.from_service_account_info(info, scopes=["https://www.googleapis.com/auth/spreadsheets"])
        return gspread.authorize(creds).open_by_key("1mF-9Ayv95PJmk4v8PrIDHf2-lRnHFZd5WOxQ__cb3Ss").sheet1
    except: return None

def calcular_en_caliente(df):
    """ Esta función fuerza el recálculo de todo el DataFrame """
    for i, r in df.iterrows():
        try:
            p_amz = float(r['AMAZON'])
            c_usd = float(r['COSTO USD'])
            t_c = float(r['TIPO CAMBIO'])
            p_fee = float(r['% FEE'])
            env = float(r['ENVIO'])
            
            costo_mxn = c_usd * t_c
            base_gravable = p_amz / 1.16
            neto = p_amz - (p_amz * (p_fee/100)) - abs(env) - (base_gravable * 0.08) - (base_gravable * 0.025)
            utilidad = neto - costo_mxn
            df.at[i, 'UTILIDAD'] = utilidad
            df.at[i, 'MARGEN %'] = (utilidad / neto * 100) if neto > 0 else 0
        except: continue
    return df

# --- ACCESO ---
if 'auth' not in st.session_state: st.session_state.auth = False

if not st.session_state.auth:
    st.title("🔐 Acceso CalcuAMZ v3.5")
    u = st.text_input("Usuario").lower().strip()
    p = st.text_input("Clave", type="password")
    if st.button("Entrar"):
        if u in USUARIOS and USUARIOS[u] == p:
            st.session_state.auth = True; st.session_state.user = u; st.rerun()
else:
    ws = conectar()
    if ws:
        df_raw = pd.DataFrame(ws.get_all_records())
        if not df_raw.empty:
            df_raw.columns = [str(c).upper().strip() for c in df_raw.columns]
            for c in ['COSTO USD', 'AMAZON', 'ENVIO', '% FEE', 'TIPO CAMBIO']:
                df_raw[c] = pd.to_numeric(df_raw[c], errors='coerce').fillna(0.0)

    es_editor = st.session_state.user in ["admin", "dav", "dax", "cesar"]

    st.title("📊 Simulador Maestro sr.sicho")

    if not df_raw.empty:
        # --- LOGICA DE SIMULACION ---
        st.subheader("1. Simulador Dinámico (Edita AMAZON y presiona ENTER)")
        
        # Pre-calculamos los valores actuales
        df_display = calcular_en_caliente(df_raw.copy())

        # El editor de datos
        # IMPORTANTE: Al terminar de editar una celda, presiona ENTER o haz clic fuera
        edited_df = st.data_editor(
            df_display[['SKU', 'PRODUCTO', 'COSTO USD', 'TIPO CAMBIO', 'AMAZON', 'UTILIDAD', 'MARGEN %', 'ENVIO', '% FEE']],
            column_config={
                "SKU": st.column_config.TextColumn(disabled=True),
                "PRODUCTO": st.column_config.TextColumn(disabled=True, width="large"),
                "AMAZON": st.column_config.NumberColumn("AMAZON", format="$%.2f"),
                "UTILIDAD": st.column_config.NumberColumn(disabled=True, format="$%.2f"),
                "MARGEN %": st.column_config.NumberColumn(disabled=True, format="%.2f%%"),
            },
            use_container_width=True, hide_index=True, key="sim_v35"
        )

        # TRIGGER DE ACTUALIZACIÓN: Aquí es donde ocurre la magia
        # Si el DataFrame editado es diferente al original, recalculamos y refrescamos
        if not edited_df.equals(df_display):
            st.session_state.df_simulado = calcular_en_caliente(edited_df)
            st.rerun() # Esto refresca la pantalla con los nuevos cálculos de margen

        if es_editor:
            if st.button("🚀 GUARDAR PRECIOS EDITADOS EN NUBE"):
                for i, row in edited_df.iterrows():
                    if float(df_raw.at[i, 'AMAZON']) != float(row['AMAZON']):
                        ws.update_cell(i + 2, 4, float(row['AMAZON']))
                st.success("Sincronizado con éxito."); st.rerun()

        st.divider()

        # --- SECCIÓN DE GESTIÓN (Tus herramientas) ---
        if es_editor:
            st.subheader("2. Gestión de Inventario")
            t1, t2, t3 = st.tabs(["➕ Nuevo", "✏️ Editar/Borrar", "📂 Bulk"])
            with t1:
                with st.form("f1"):
                    sk = st.text_input("SKU").upper()
                    no = st.text_input("Nombre")
                    c1, c2, c3 = st.columns(3)
                    cos = c1.number_input("Costo USD", format="%.2f")
                    tc = c2.number_input("TC", value=18.50)
                    fe = c3.number_input("% Fee", value=10.0)
                    if st.form_submit_button("Guardar"):
                        ws.append_row([sk if sk else f"A-{len(df_raw)+1}", no.upper(), cos, 0, 0, fe, tc])
                        st.rerun()
            # ... (Tus otras pestañas de la v3.4 siguen igual debajo) ...
