import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import io

# --- CONFIGURACIÓN ---
st.set_page_config(layout="wide", page_title="Dacocel - Panel Maestro", page_icon="📱")

USUARIOS = {"admin": "amazon123", "dav": "ventas2026", "dax": "amazon2026", "cesar": "ventas789", "consulta": "lector2026"}

def conectar():
    try:
        info = st.secrets["gcp_service_account"]
        creds = Credentials.from_service_account_info(info, scopes=["https://www.googleapis.com/auth/spreadsheets"])
        return gspread.authorize(creds).open_by_key("1mF-9Ayv95PJmk4v8PrIDHf2-lRnHFZd5WOxQ__cb3Ss").sheet1
    except: return None

def calcular_margen_v4(row):
    """ Cálculo de margen con retenciones de ley para Dacocel """
    try:
        p_amz = float(row['AMAZON'])
        c_usd = float(row['COSTO USD'])
        t_c = float(row['TIPO CAMBIO'])
        p_fee = float(row['% FEE'])
        env = float(row['ENVIO'])
        
        costo_mxn = c_usd * t_c
        dinero_fee = p_amz * (p_fee / 100)
        base_gravable = p_amz / 1.16
        retenciones = base_gravable * 0.105 # IVA 8% + ISR 2.5%
        neto = p_amz - dinero_fee - abs(env) - retenciones
        utilidad = neto - costo_mxn
        return (utilidad / neto * 100) if neto > 0 else 0
    except: return 0.0

# --- LÓGICA DE SESIÓN ---
if 'auth' not in st.session_state: st.session_state.auth = False

if not st.session_state.auth:
    st.title("🔐 Acceso Dacocel")
    u = st.text_input("Usuario").lower().strip()
    p = st.text_input("Clave", type="password")
    if st.button("Ingresar"):
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
                if c in df_raw.columns:
                    df_raw[c] = pd.to_numeric(df_raw[c], errors='coerce').fillna(0.0)

    es_editor = st.session_state.user in ["admin", "dav", "dax", "cesar"]

    st.title("📱 Panel Maestro Dacocel")

    if not df_raw.empty:
        # --- 1. SIMULADOR (ORDEN ORIGINAL) ---
        st.subheader("1. Simulador de Precios Dacocel")
        
        # Calculamos margen inicial
        df_raw['MARGEN %'] = df_raw.apply(calcular_margen_v4, axis=1)

        # Orden de columnas solicitado (Margen al final)
        cols_final = ['SKU', 'PRODUCTO', 'COSTO USD', 'TIPO CAMBIO', 'AMAZON', 'ENVIO', '% FEE', 'MARGEN %']
        
        edited_df = st.data_editor(
            df_raw[cols_final],
            column_config={
                "PRODUCTO": st.column_config.TextColumn("PRODUCTO", width="large", disabled=True),
                "AMAZON": st.column_config.NumberColumn("AMAZON", format="$%.2f"),
                "MARGEN %": st.column_config.NumberColumn("MARGEN %", format="%.2f%%", disabled=True),
                "SKU": st.column_config.TextColumn(disabled=True),
                "COSTO USD": st.column_config.NumberColumn("COSTO USD", disabled=True, format="$%.2f"),
                "TIPO CAMBIO": st.column_config.NumberColumn("TC", disabled=True),
                "ENVIO": st.column_config.NumberColumn("ENVIO", disabled=True),
                "% FEE": st.column_config.NumberColumn("% FEE", disabled=True),
            },
            use_container_width=True, hide_index=True, key="editor_dacocel_v4"
        )

        # Actualización instantánea del margen al editar
        edited_df['MARGEN %'] = edited_df.apply(calcular_margen_v4, axis=1)

        if es_editor:
            if st.button("🚀 ACTUALIZAR PRECIOS EN NUBE"):
                for i, row in edited_df.iterrows():
                    if float(df_raw.at[i, 'AMAZON']) != float(row['AMAZON']):
                        ws.update_cell(i + 2, 4, float(row['AMAZON']))
                st.success("Inventario Dacocel actualizado."); st.rerun()

        st.divider()

        # --- 2. GESTIÓN (Tus Pestañas de Ecommerce Manager) ---
        if es_editor:
            st.subheader("2. Herramientas de Gestión")
            t1, t2, t3, t4 = st.tabs(["➕ Nuevo Registro", "✏️ Editar/Borrar", "📂 Carga Masiva", "📄 Reportes PDF"])
            
            with t1:
                with st.form("f_nuevo"):
                    sk = st.text_input("SKU").upper()
                    no = st.text_input("Nombre Modelo")
                    c1, c2, c3 = st.columns(3)
                    cos = c1.number_input("Costo USD", format="%.2f")
                    tc = c2.number_input("TC", value=18.50)
                    fe = c3.number_input("% Fee", value=10.0)
                    env = c1.number_input("Envío", value=0.0)
                    if st.form_submit_button("Guardar en Dacocel"):
                        ws.append_row([sk if sk else f"D-{len(df_raw)+1}", no.upper(), cos, 0, env, fe, tc])
                        st.rerun()
            
            with t2:
                sel = st.selectbox("Buscar Producto", df_raw['SKU'].astype(str) + " - " + df_raw['PRODUCTO'])
                idx_sel = df_raw[df_raw['SKU'].astype(str) == sel.split(" - ")[0]].index[0]
                curr = df_raw.iloc[idx_sel]
                with st.form("f_mod"):
                    enom = st.text_input("Nombre", value=str(curr['PRODUCTO']))
                    ecos = st.number_input("Costo USD", value=float(curr['COSTO USD']))
                    epre = st.number_input("Precio Amazon", value=float(curr['AMAZON']))
                    if st.form_submit_button("Actualizar Datos"):
                        ws.update(f'A{idx_sel+2}:G{idx_sel+2}', [[curr['SKU'], enom.upper(), ecos, epre, curr['ENVIO'], curr['% FEE'], curr['TIPO CAMBIO']]])
                        st.rerun()
                if st.button("🗑️ Eliminar Producto"): ws.delete_rows(int(idx_sel + 2)); st.rerun()

            with t3:
                st.info("Formato Bulk para Dacocel.")
                f_bulk = st.file_uploader("Excel/CSV", type=['xlsx', 'csv'])
                if st.button("Descargar Plantilla Actual"):
                    # Generar Excel rápido para descargar
                    pass

            with t4:
                st.write("Generación de estados de inventario.")
    else:
        st.warning("Sin conexión a la base de Dacocel.")
