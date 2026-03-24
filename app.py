import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import io
from fpdf import FPDF

# --- CalcuAMZ v3.4 (MASTER: FIX EDICIÓN + TODAS LAS FUNCIONES) ---
st.set_page_config(layout="wide", page_title="CalcuAMZ v3.4", page_icon="📦")

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

def calcular_detallado_v3(p_amz, c_usd, t_c, p_fee, env):
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
        return utilidad, margen
    except:
        return 0.0, 0.0

def calcular_precio_sugerido(costo_usd, fee_pct, envio_fba, t_cambio):
    if costo_usd <= 0: return 0.0
    costo_mx = costo_usd * t_cambio
    tax_factor = (0.08 + 0.025) / 1.16
    divisor = 1 - (fee_pct/100) - tax_factor
    return ((costo_mx * 1.1112) + envio_fba) / divisor

# --- ACCESO ---
if 'auth' not in st.session_state: st.session_state.auth = False

if not st.session_state.auth:
    st.title("🔐 Acceso CalcuAMZ v3.4")
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
            # LIMPIEZA CRÍTICA DE DATOS
            cols_num = ['COSTO USD', 'AMAZON', 'ENVIO', '% FEE', 'TIPO CAMBIO']
            for c in cols_num:
                if c in df_raw.columns:
                    df_raw[c] = pd.to_numeric(df_raw[c], errors='coerce').fillna(0.0)

    es_editor = st.session_state.user in ["admin", "dav", "dax", "cesar"]

    with st.sidebar:
        st.header(f"👤 {st.session_state.user.upper()}")
        st.write("Versión 3.4 (Master)")
        if st.button("Cerrar Sesión"):
            st.session_state.auth = False; st.rerun()

    st.title("📊 Panel Integral sr.sicho")

    if not df_raw.empty:
        # --- SECCIÓN 1: EL SIMULADOR ---
        st.subheader("1. Simulador de Precios (Vista Jefe)")
        df_sim = df_raw.copy()
        cals = df_sim.apply(lambda r: calcular_detallado_v3(r['AMAZON'], r['COSTO USD'], r['TIPO CAMBIO'], r['% FEE'], r['ENVIO']), axis=1)
        df_sim['UTILIDAD'] = cals.apply(lambda x: x[0])
        df_sim['MARGEN %'] = cals.apply(lambda x: x[1])

        # Editor Blindado
        edited_df = st.data_editor(
            df_sim[['SKU', 'PRODUCTO', 'COSTO USD', 'TIPO CAMBIO', 'AMAZON', 'UTILIDAD', 'MARGEN %', 'ENVIO', '% FEE']],
            column_config={
                "SKU": st.column_config.TextColumn(disabled=True),
                "PRODUCTO": st.column_config.TextColumn(disabled=True, width="large"),
                "AMAZON": st.column_config.NumberColumn("AMAZON (Editable)", format="$%.2f"),
                "UTILIDAD": st.column_config.NumberColumn(disabled=True, format="$%.2f"),
                "MARGEN %": st.column_config.NumberColumn(disabled=True, format="%.2f%%"),
            },
            use_container_width=True, hide_index=True, height=400, key="master_editor_v34"
        )
        
        # Botón para guardar cambios del simulador
        if es_editor:
            if st.button("🚀 APLICAR CAMBIOS DE TABLA A NUBE"):
                for i, row in edited_df.iterrows():
                    if float(df_raw.at[i, 'AMAZON']) != float(row['AMAZON']):
                        ws.update_cell(i + 2, 4, float(row['AMAZON']))
                st.success("¡Datos sincronizados!"); st.rerun()
        
        st.divider()

        # --- SECCIÓN 2: GESTIÓN DE PRODUCTOS ---
        if es_editor:
            st.subheader("2. Gestión y Herramientas")
            t1, t2, t3 = st.tabs(["➕ Registro Individual", "✏️ Editar / Borrar", "📂 Carga Masiva (Bulk)"])
            
            with t1:
                with st.form("nuevo_form"):
                    sk = st.text_input("SKU").upper()
                    no = st.text_input("Nombre del Producto")
                    c1, c2, c3 = st.columns(3)
                    cos = c1.number_input("Costo USD", format="%.2f")
                    tc = c2.number_input("TC", value=18.50)
                    fe = c3.number_input("% Fee", value=10.0)
                    env = c1.number_input("Envío FBA", value=0.0)
                    if st.form_submit_button("💾 Guardar"):
                        ws.append_row([sk if sk else f"A-{len(df_raw)+1}", no.upper(), cos, 0, env, fe, tc])
                        st.rerun()
            
            with t2:
                sel = st.selectbox("Elegir para modificar", df_raw['SKU'].astype(str) + " - " + df_raw['PRODUCTO'])
                idx = df_raw[df_raw['SKU'].astype(str) == sel.split(" - ")[0]].index[0]
                curr = df_raw.iloc[idx]
                with st.form("edit_form"):
                    enom = st.text_input("Nombre", value=str(curr['PRODUCTO']))
                    ecos = st.number_input("Costo USD", value=float(curr['COSTO USD']))
                    etc = st.number_input("TC", value=float(curr.get('TIPO CAMBIO', 18.0)))
                    epre = st.number_input("Precio Amazon", value=float(curr['AMAZON']))
                    if st.form_submit_button("✅ Actualizar"):
                        ws.update(f'A{idx+2}:G{idx+2}', [[curr['SKU'], enom.upper(), ecos, epre, curr['ENVIO'], curr['% FEE'], etc]])
                        st.rerun()
                if st.button("🗑️ Eliminar Producto"):
                    ws.delete_rows(int(idx + 2)); st.rerun()

            with t3:
                tc_bulk = st.number_input("TC para Bulk", value=18.50)
                f_bulk = st.file_uploader("Subir Excel", type=['xlsx', 'csv'])
                if f_bulk and st.button("🚀 Cargar"):
                    db = pd.read_excel(f_bulk) if f_bulk.name.endswith('xlsx') else pd.read_csv(f_bulk)
                    db.columns = [str(c).upper().strip() for c in db.columns]
                    filas_bulk = []
                    for i, r in db.iterrows():
                        sku_b = str(r.get('SKU')) if not pd.isna(r.get('SKU')) else f"B-{len(df_raw)+i+1}"
                        precio_b = calcular_precio_sugerido(r['COSTO USD'], r.get('% FEE', 10), r.get('ENVIO', 0), tc_bulk)
                        filas_bulk.append([sku_b, str(r['PRODUCTO']).upper(), r['COSTO USD'], precio_b, r.get('ENVIO', 0), r.get('% FEE', 10), tc_bulk])
                    ws.append_rows(filas_bulk); st.rerun()
    else:
        st.warning("No hay datos en el Sheet.")
