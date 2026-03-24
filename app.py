import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

# --- CalcuAMZ v3.7 (RESTORE: COLORES + ORDEN + CÁLCULO) ---
st.set_page_config(layout="wide", page_title="CalcuAMZ v3.7", page_icon="📦")

USUARIOS = {"admin": "amazon123", "dav": "ventas2026", "dax": "amazon2026", "cesar": "ventas789", "consulta": "lector2026"}

def conectar():
    try:
        info = st.secrets["gcp_service_account"]
        creds = Credentials.from_service_account_info(info, scopes=["https://www.googleapis.com/auth/spreadsheets"])
        return gspread.authorize(creds).open_by_key("1mF-9Ayv95PJmk4v8PrIDHf2-lRnHFZd5WOxQ__cb3Ss").sheet1
    except: return None

def calcular_linea(row):
    try:
        p_amz = float(row['AMAZON'])
        c_usd = float(row['COSTO USD'])
        t_c = float(row['TIPO CAMBIO'])
        p_fee = float(row['% FEE'])
        env = float(row['ENVIO'])
        
        costo_mxn = c_usd * t_c
        dinero_fee = p_amz * (p_fee / 100)
        base_gravable = p_amz / 1.16
        ret_iva = base_gravable * 0.08
        ret_isr = base_gravable * 0.025
        neto = p_amz - dinero_fee - abs(env) - ret_iva - ret_isr
        utilidad = neto - costo_mxn
        margen = (utilidad / neto * 100) if neto > 0 else 0
        return pd.Series([costo_mxn, dinero_fee, neto, utilidad, margen])
    except:
        return pd.Series([0, 0, 0, 0, 0])

def color_margen(val):
    color = '#1a4d1a' if val > 8 else '#5e541e' if val > 6 else '#551a1a'
    return f'background-color: {color}; color: white'

# --- INICIALIZACIÓN ---
if 'auth' not in st.session_state: st.session_state.auth = False

if not st.session_state.auth:
    st.title("🔐 Acceso CalcuAMZ v3.7")
    u = st.text_input("Usuario").lower().strip()
    p = st.text_input("Clave", type="password")
    if st.button("Entrar"):
        if u in USUARIOS and USUARIOS[u] == p:
            st.session_state.auth = True; st.session_state.user = u; st.rerun()
else:
    ws = conectar()
    df_raw = pd.DataFrame()
    
    if ws:
        data = ws.get_all_records()
        df_raw = pd.DataFrame(data)
        if not df_raw.empty:
            df_raw.columns = [str(c).upper().strip() for c in df_raw.columns]
            for c in ['COSTO USD', 'AMAZON', 'ENVIO', '% FEE', 'TIPO CAMBIO']:
                df_raw[c] = pd.to_numeric(df_raw[c], errors='coerce').fillna(0.0)

    es_editor = st.session_state.user in ["admin", "dav", "dax", "cesar"]

    st.title("📊 Simulador sr.sicho v3.7")

    if not df_raw.empty:
        # 1. PREPARACIÓN DE DATOS (ORDEN ORIGINAL)
        df_sim = df_raw.copy()
        res = df_sim.apply(calcular_linea, axis=1)
        res.columns = ['COSTO MXN', 'FEE $', 'NETO', 'UTILIDAD', 'MARGEN %']
        df_final = pd.concat([df_sim, res], axis=1)
        
        # Reordenar columnas como la v3.0
        cols_orden = ['SKU', 'PRODUCTO', 'COSTO USD', 'TIPO CAMBIO', 'COSTO MXN', 'AMAZON', 'ENVIO', '% FEE', 'FEE $', 'NETO', 'UTILIDAD', 'MARGEN %']
        df_final = df_final[cols_orden]

        st.info("💡 Edita el precio en **AMAZON** y presiona **Enter**. El color y el margen cambiarán automáticamente.")

        # 2. EL EDITOR CON FORMATO
        edited_df = st.data_editor(
            df_final,
            column_config={
                "AMAZON": st.column_config.NumberColumn("AMAZON", format="$%.2f", required=True),
                "MARGEN %": st.column_config.NumberColumn("MARGEN %", format="%.2f%%", disabled=True),
                "UTILIDAD": st.column_config.NumberColumn("UTILIDAD", format="$%.2f", disabled=True),
                "COSTO MXN": st.column_config.NumberColumn("COSTO MXN", format="$%.2f", disabled=True),
                "PRODUCTO": st.column_config.TextColumn(width="large", disabled=True),
                "SKU": st.column_config.TextColumn(disabled=True),
            },
            use_container_width=True, hide_index=True, key="editor_v37"
        )

        # 3. RECALCULO DINÁMICO + ESTILOS
        # Aplicamos el cálculo de nuevo sobre lo editado para que el usuario lo vea
        new_res = edited_df.apply(calcular_linea, axis=1)
        edited_df[['COSTO MXN', 'FEE $', 'NETO', 'UTILIDAD', 'MARGEN %']] = new_res
        
        # Mostramos una versión estilizada (solo lectura) justo debajo o refrescamos
        # Para que el jefe vea los colores, usamos st.dataframe con style
        st.subheader("Vista Previa de Rentabilidad (Confirmada)")
        
        # Formato de moneda y colores
        moneda = {c: "${:,.2f}" for c in ['COSTO USD', 'COSTO MXN', 'AMAZON', 'ENVIO', 'FEE $', 'NETO', 'UTILIDAD']}
        
        st.dataframe(
            edited_df.style.format(moneda).format({"MARGEN %": "{:.2f}%"}).applymap(color_margen, subset=['MARGEN %']),
            use_container_width=True, hide_index=True
        )

        if es_editor:
            if st.button("🚀 GUARDAR PRECIOS EN NUBE"):
                for i, row in edited_df.iterrows():
                    if float(df_raw.at[i, 'AMAZON']) != float(row['AMAZON']):
                        ws.update_cell(i + 2, 4, float(row['AMAZON']))
                st.success("Sincronizado."); st.rerun()

        st.divider()
        # Aquí abajo puedes pegar tus pestañas de Gestión (Nuevo/Editar) de la v3.3
