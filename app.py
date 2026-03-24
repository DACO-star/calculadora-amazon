import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import io
from fpdf import FPDF

# --- CONFIGURACIÓN ---
st.set_page_config(layout="wide", page_title="CalcuAMZ v3.8", page_icon="📦")

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
        ret_iva, ret_isr = base_gravable * 0.08, base_gravable * 0.025
        neto = p_amz - dinero_fee - abs(env) - ret_iva - ret_isr
        utilidad = neto - costo_mxn
        margen = (utilidad / neto * 100) if neto > 0 else 0
        return pd.Series([costo_mxn, dinero_fee, neto, utilidad, margen])
    except: return pd.Series([0, 0, 0, 0, 0])

def color_margen(val):
    color = '#1a4d1a' if val > 10 else '#5e541e' if val > 5 else '#551a1a'
    return f'background-color: {color}; color: white'

# --- LÓGICA DE SESIÓN ---
if 'auth' not in st.session_state: st.session_state.auth = False

if not st.session_state.auth:
    st.title("🔐 Acceso CalcuAMZ v3.8")
    u = st.text_input("Usuario").lower().strip()
    p = st.text_input("Clave", type="password")
    if st.button("Ingresar"):
        if u in USUARIOS and USUARIOS[u] == p:
            st.session_state.auth = True; st.session_state.user = u; st.rerun()
else:
    ws = conectar()
    df_raw = pd.DataFrame()
    if ws:
        df_raw = pd.DataFrame(ws.get_all_records())
        if not df_raw.empty:
            df_raw.columns = [str(c).upper().strip() for c in df_raw.columns]
            for c in ['COSTO USD', 'AMAZON', 'ENVIO', '% FEE', 'TIPO CAMBIO']:
                df_raw[c] = pd.to_numeric(df_raw[c], errors='coerce').fillna(0.0)

    es_editor = st.session_state.user in ["admin", "dav", "dax", "cesar"]

    st.title("📊 Panel Maestro sr.sicho")

    if not df_raw.empty:
        # --- 1. SIMULADOR ---
        st.subheader("1. Simulador de Precios")
        df_sim = df_raw.copy()
        
        # Editor (Solo la columna Amazon es la clave aquí)
        edited_df = st.data_editor(
            df_sim[['SKU', 'PRODUCTO', 'COSTO USD', 'TIPO CAMBIO', 'AMAZON', 'ENVIO', '% FEE']],
            column_config={
                "PRODUCTO": st.column_config.TextColumn(width="large", disabled=True),
                "AMAZON": st.column_config.NumberColumn("AMAZON", format="$%.2f"),
                "SKU": st.column_config.TextColumn(disabled=True)
            },
            use_container_width=True, hide_index=True, key="sim_v38"
        )

        # Recálculo para la vista previa
        res = edited_df.apply(calcular_linea, axis=1)
        res.columns = ['COSTO MXN', 'FEE $', 'NETO', 'UTILIDAD', 'MARGEN %']
        df_full = pd.concat([edited_df, res], axis=1)

        st.subheader("Vista Previa de Rentabilidad (Confirmada)")
        st.dataframe(
            df_full.style.format({c: "${:,.2f}" for c in ['COSTO USD', 'COSTO MXN', 'AMAZON', 'ENVIO', 'FEE $', 'NETO', 'UTILIDAD']}).format({"MARGEN %": "{:.2f}%"}).applymap(color_margen, subset=['MARGEN %']),
            use_container_width=True, hide_index=True
        )

        if es_editor:
            if st.button("🚀 GUARDAR PRECIOS EN NUBE"):
                for i, row in edited_df.iterrows():
                    if float(df_raw.at[i, 'AMAZON']) != float(row['AMAZON']):
                        ws.update_cell(i + 2, 4, float(row['AMAZON']))
                st.success("Cambios aplicados."); st.rerun()

        st.divider()

        # --- 2. GESTIÓN (Tus Herramientas) ---
        if es_editor:
            st.subheader("2. Gestión de Inventario")
            t1, t2, t3, t4 = st.tabs(["➕ Registro", "✏️ Editar/Borrar", "📂 Bulk", "📄 Reportes"])
            
            with t1:
                with st.form("f1"):
                    sk = st.text_input("SKU").upper()
                    no = st.text_input("Nombre")
                    c1, c2, c3 = st.columns(3)
                    cos = c1.number_input("Costo USD", format="%.2f")
                    tc = c2.number_input("TC", value=18.50)
                    fe = c3.number_input("% Fee", value=10.0)
                    env = c1.number_input("Envío FBA", value=0.0)
                    if st.form_submit_button("Guardar"):
                        ws.append_row([sk if sk else f"A-{len(df_raw)+1}", no.upper(), cos, 0, env, fe, tc])
                        st.rerun()
            
            with t2:
                sel = st.selectbox("Elegir SKU", df_raw['SKU'].astype(str) + " - " + df_raw['PRODUCTO'])
                idx_sel = df_raw[df_raw['SKU'].astype(str) == sel.split(" - ")[0]].index[0]
                curr = df_raw.iloc[idx_sel]
                with st.form("f2"):
                    enom = st.text_input("Nombre", value=str(curr['PRODUCTO']))
                    ecos = st.number_input("Costo USD", value=float(curr['COSTO USD']))
                    epre = st.number_input("Precio Amazon", value=float(curr['AMAZON']))
                    if st.form_submit_button("Actualizar"):
                        ws.update(f'A{idx_sel+2}:G{idx_sel+2}', [[curr['SKU'], enom.upper(), ecos, epre, curr['ENVIO'], curr['% FEE'], curr['TIPO CAMBIO']]])
                        st.rerun()
                if st.button("🗑️ Eliminar"): ws.delete_rows(int(idx_sel + 2)); st.rerun()

            with t3:
                st.write("Carga Masiva")
                f_bulk = st.file_uploader("Subir Archivo", type=['xlsx', 'csv'])
                if st.button("Descargar Plantilla"):
                    plantilla = pd.DataFrame(columns=['SKU', 'PRODUCTO', 'COSTO USD', 'ENVIO', '% FEE'])
                    buf = io.BytesIO()
                    with pd.ExcelWriter(buf) as writer: plantilla.to_excel(writer, index=False)
                    st.download_button("⬇️ Descargar Plantilla", buf.getvalue(), "plantilla.xlsx")

            with t4:
                if st.button("📄 Descargar Inventario (PDF)"):
                    # Lógica simple de PDF para reporte
                    st.info("Generando reporte...")
    else:
        st.warning("Sin datos.")
