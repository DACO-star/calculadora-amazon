import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import io
from fpdf import FPDF

# --- CONFIGURACIÓN DACOCEL ---
st.set_page_config(layout="wide", page_title="Dacocel - Gestión", page_icon="📱")

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
        dinero_fee = p_amz * (p_fee / 100)
        base_gravable = p_amz / 1.16
        retenciones = base_gravable * 0.105 # IVA 8% + ISR 2.5%
        neto = p_amz - dinero_fee - abs(env) - retenciones
        utilidad = neto - costo_mxn
        margen = (utilidad / neto) * 100 if neto > 0 else 0
        return pd.Series([costo_mxn, dinero_fee, neto, utilidad, margen])
    except: return pd.Series([0, 0, 0, 0, 0])

def color_margen(val):
    if val > 10: color = '#1a4d1a' # Verde
    elif val > 5: color = '#5e541e' # Amarillo
    else: color = '#551a1a' # Rojo
    return f'background-color: {color}; color: white'

# --- ACCESO ---
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
        df_raw = pd.DataFrame(ws.get_all_records())
        if not df_raw.empty:
            df_raw.columns = [str(c).upper().strip() for c in df_raw.columns]
            for c in ['COSTO USD', 'AMAZON', 'ENVIO', '% FEE', 'TIPO CAMBIO']:
                df_raw[c] = pd.to_numeric(df_raw[c], errors='coerce').fillna(0.0)

    es_editor = st.session_state.user in ["admin", "dav", "dax", "cesar"]

    st.title("📱 Panel Maestro Dacocel")

    if not df_raw.empty:
        # --- PROCESAMIENTO ---
        res = df_raw.apply(lambda r: calcular_detallado(r['AMAZON'], r['COSTO USD'], r['TIPO CAMBIO'], r['% FEE'], r['ENVIO']), axis=1)
        res.columns = ['COSTO MXN', 'FEE $', 'NETO', 'UTILIDAD', 'MARGEN %']
        df_final = pd.concat([df_raw, res], axis=1)
        cols_v3 = ['SKU', 'PRODUCTO', 'COSTO USD', 'TIPO CAMBIO', 'AMAZON', 'ENVIO', '% FEE', 'MARGEN %']

        # --- 1. SIMULADOR CON SEMÁFORO ---
        st.subheader("1. Inventario y Simulación")
        # Mostramos la tabla con colores para el jefe
        st.dataframe(
            df_final[cols_v3].style.applymap(color_margen, subset=['MARGEN %']).format({
                "COSTO USD": "${:.2f}", "AMAZON": "${:.2f}", "ENVIO": "${:.2f}", 
                "MARGEN %": "{:.2f}%", "% FEE": "{:.2f}%"
            }), use_container_width=True, hide_index=True
        )

        # Editor para cambios rápidos
        st.write("🔧 **Edición Rápida de Valores:**")
        edited_df = st.data_editor(
            df_final[cols_v3],
            column_config={
                "PRODUCTO": st.column_config.TextColumn(disabled=True),
                "SKU": st.column_config.TextColumn(disabled=True),
                "MARGEN %": st.column_config.NumberColumn(disabled=True, format="%.2f%%"),
            },
            use_container_width=True, hide_index=True, key="editor_v33"
        )

        if es_editor and st.button("🚀 GUARDAR TODO EN NUBE"):
            for i, row in edited_df.iterrows():
                # Actualizamos las 5 columnas editables en el Sheet (C, D, E, F, G)
                ws.update(f'C{i+2}:G{i+2}', [[row['COSTO USD'], row['AMAZON'], row['ENVIO'], row['% FEE'], row['TIPO CAMBIO']]])
            st.success("Dacocel Actualizado."); st.rerun()

        st.divider()

        # --- 2. GESTIÓN POR PESTAÑAS ---
        if es_editor:
            st.subheader("2. Herramientas de Gestión")
            t1, t2, t3, t4 = st.tabs(["➕ Nuevo", "✏️ Borrar", "📂 Carga Masiva", "📄 Reportes"])
            
            with t1:
                with st.form("n"):
                    sk = st.text_input("SKU").upper()
                    no = st.text_input("Nombre")
                    c1, c2 = st.columns(2)
                    cos = c1.number_input("Costo USD")
                    pre = c2.number_input("Precio Amazon")
                    if st.form_submit_button("Registrar"):
                        ws.append_row([sk, no.upper(), cos, pre, 0, 10, 18.5])
                        st.rerun()
            
            with t2:
                sel = st.selectbox("Elegir para eliminar", df_raw['SKU'] + " - " + df_raw['PRODUCTO'])
                if st.button("🗑️ Confirmar Eliminación"):
                    idx = df_raw[df_raw['SKU'] == sel.split(" - ")[0]].index[0]
                    ws.delete_rows(int(idx + 2)); st.rerun()

            with t3:
                st.write("### Sistema Bulk")
                if st.button("⬇️ Descargar Plantilla Excel"):
                    plantilla = pd.DataFrame(columns=['SKU', 'PRODUCTO', 'COSTO USD', 'AMAZON', 'ENVIO', '% FEE', 'TIPO CAMBIO'])
                    buf = io.BytesIO()
                    with pd.ExcelWriter(buf) as w: plantilla.to_excel(w, index=False)
                    st.download_button("Click para descargar", buf.getvalue(), "plantilla_dacocel.xlsx")
                f = st.file_uploader("Subir archivo lleno", type=['xlsx'])

            with t4:
                if st.button("📄 Generar Reporte PDF de Inventario"):
                    pdf = FPDF()
                    pdf.add_page()
                    pdf.set_font("Arial", 'B', 16)
                    pdf.cell(190, 10, "REPORTE DE INVENTARIO DACOCEL", 0, 1, 'C')
                    pdf.set_font("Arial", size=10)
                    for i, r in df_final.iterrows():
                        pdf.cell(190, 8, f"{r['SKU']} - {r['PRODUCTO']} | Margen: {r['MARGEN %']:.2f}%", 0, 1)
                    st.download_button("Descargar PDF", pdf.output(dest='S'), "Reporte_Dacocel.pdf")
