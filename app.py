import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import io

# --- CONFIGURACIÓN DACOCEL ---
st.set_page_config(layout="wide", page_title="Dacocel - Gestión", page_icon="📱")

USUARIOS = {
    "admin": "amazon123", "dav": "ventas2026",
    "dax": "amazon2026", "cesar": "ventas789",
    "consulta": "lector2026"
}

def conectar():
    try:
        info = st.secrets["gcp_service_account"]
        creds = Credentials.from_service_account_info(info, scopes=["https://www.googleapis.com/auth/spreadsheets"])
        return gspread.authorize(creds).open_by_key("1mF-9Ayv95PJmk4v8PrIDHf2-lRnHFZd5WOxQ__cb3Ss").sheet1
    except:
        return None

def calcular_detallado(p_amz, c_usd, t_c, p_fee, env):
    try:
        p_amz, c_usd, t_c, p_fee, env = map(float, [p_amz, c_usd, t_c, p_fee, env])
        costo_mxn = c_usd * t_c
        dinero_fee = p_amz * (p_fee / 100)
        base_gravable = p_amz / 1.16
        ret_iva = base_gravable * 0.08
        ret_isr = base_gravable * 0.025
        neto = p_amz - dinero_fee - abs(env) - ret_iva - ret_isr
        utilidad = neto - costo_mxn
        margen = (utilidad / neto) * 100 if neto > 0 else 0
        return pd.Series([costo_mxn, dinero_fee, neto, utilidad, margen])
    except:
        return pd.Series([0, 0, 0, 0, 0])

# --- LÓGICA DE ACCESO ---
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
                df_raw[c] = pd.to_numeric(df_raw[c], errors='coerce').fillna(0.0)

    es_editor = st.session_state.user in ["admin", "dav", "dax", "cesar"]

    with st.sidebar:
        st.header(f"👤 {st.session_state.user.upper()}")
        if st.button("Cerrar Sesión"): st.session_state.auth = False; st.rerun()

    st.title("📱 Panel Maestro Dacocel")

    if not df_raw.empty:
        # --- PROCESAMIENTO DE DATOS ---
        res = df_raw.apply(lambda r: calcular_detallado(r['AMAZON'], r['COSTO USD'], r['TIPO CAMBIO'], r['% FEE'], r['ENVIO']), axis=1)
        res.columns = ['COSTO MXN', 'FEE $', 'NETO', 'UTILIDAD', 'MARGEN %']
        df_final = pd.concat([df_raw, res], axis=1)
        
        # Orden de columnas v3.1
        cols_v3 = ['SKU', 'PRODUCTO', 'COSTO USD', 'TIPO CAMBIO', 'AMAZON', 'ENVIO', '% FEE', 'FEE $', 'MARGEN %']
        
        # --- VISTA PRINCIPAL (Simulador con Costo y Amazon Editables) ---
        st.subheader("1. Inventario y Simulación")
        st.info("💡 Puedes editar directamente el **COSTO USD** y el **PRECIO AMAZON**. No olvides guardar los cambios.")
        
        edited_df = st.data_editor(
            df_final[cols_v3],
            column_config={
                "PRODUCTO": st.column_config.TextColumn(width="large", disabled=True),
                "COSTO USD": st.column_config.NumberColumn("COSTO USD", format="$%.2f"),
                "AMAZON": st.column_config.NumberColumn("PRECIO AMAZON", format="$%.2f"),
                "ENVIO": st.column_config.NumberColumn("ENVÍO", format="$%.2f", disabled=True),
                "% FEE": st.column_config.NumberColumn("% FEE", format="%.2f%%", disabled=True),
                "FEE $": st.column_config.NumberColumn("FEE $", format="$%.2f", disabled=True),
                "MARGEN %": st.column_config.NumberColumn("MARGEN %", format="%.2f%%", disabled=True),
                "SKU": st.column_config.TextColumn(disabled=True),
                "TIPO CAMBIO": st.column_config.NumberColumn("TIPO CAMBIO", disabled=True),
            },
            use_container_width=True, hide_index=True, key="editor_v31_dacocel"
        )

        if es_editor:
            if st.button("🚀 GUARDAR CAMBIOS (NUBE)"):
                with st.spinner("Actualizando Dacocel..."):
                    for i, row in edited_df.iterrows():
                        # Verificar si cambió el Precio Amazon (Col 4 -> D) o el Costo USD (Col 3 -> C)
                        if float(df_raw.at[i, 'AMAZON']) != float(row['AMAZON']):
                            ws.update_cell(i + 2, 4, float(row['AMAZON']))
                        if float(df_raw.at[i, 'COSTO USD']) != float(row['COSTO USD']):
                            ws.update_cell(i + 2, 3, float(row['COSTO USD']))
                    st.success("Cambios sincronizados correctamente."); st.rerun()

        st.divider()

        # --- SECCIÓN DE GESTIÓN ---
        if es_editor:
            st.subheader("2. Herramientas de Gestión")
            t1, t2, t3 = st.tabs(["➕ Nuevo Registro", "✏️ Editar Detallado", "📂 Carga Masiva"])
            
            with t1:
                with st.form("nuevo"):
                    sk = st.text_input("SKU").upper()
                    no = st.text_input("Nombre Modelo")
                    c1, c2 = st.columns(2)
                    cos = c1.number_input("Costo USD", format="%.2f")
                    tc = c2.number_input("TC", value=18.50)
                    fe = c1.number_input("% Fee", value=10.0)
                    env = c2.number_input("Envío", value=0.0)
                    if st.form_submit_button("Guardar en Dacocel"):
                        ws.append_row([sk if sk else f"D-{len(df_raw)+1}", no.upper(), cos, 0, env, fe, tc])
                        st.rerun()

            with t2:
                sel = st.selectbox("Elegir Producto", df_raw['SKU'].astype(str) + " - " + df_raw['PRODUCTO'])
                idx_sel = df_raw[df_raw['SKU'].astype(str) == sel.split(" - ")[0]].index[0]
                curr = df_raw.iloc[idx_sel]
                with st.form("editar"):
                    enom = st.text_input("Nombre", value=str(curr['PRODUCTO']))
                    ecos = st.number_input("Costo USD", value=float(curr['COSTO USD']))
                    epre = st.number_input("Precio Amazon", value=float(curr['AMAZON']))
                    etc = st.number_input("Tipo de Cambio", value=float(curr['TIPO CAMBIO']))
                    if st.form_submit_button("Actualizar Todo"):
                        ws.update(f'A{idx_sel+2}:G{idx_sel+2}', [[curr['SKU'], enom.upper(), ecos, epre, curr['ENVIO'], curr['% FEE'], etc]])
                        st.rerun()
                if st.button("🗑️ Eliminar Producto"): ws.delete_rows(int(idx_sel + 2)); st.rerun()

            with t3:
                st.info("Sección para actualización por lote.")
                f_bulk = st.file_uploader("Subir Inventario", type=['xlsx', 'csv'])
    else:
        st.warning("No hay datos en la base de Dacocel.")
