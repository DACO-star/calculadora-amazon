import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import io

# --- CalcuAMZ v3.2 (Fix: File Edit Error) ---
st.set_page_config(layout="wide", page_title="CalcuAMZ v3.2", page_icon="📈")

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
    except Exception as e:
        st.error(f"Error de conexión: {e}")
        return None

def calcular_margen_dinamico(p_amz, c_usd, t_c, p_fee, env):
    """ Función central de cálculo para evitar discrepancias """
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

# --- LÓGICA DE ACCESO ---
if 'auth' not in st.session_state: st.session_state.auth = False

if not st.session_state.auth:
    st.title("🔐 Acceso CalcuAMZ v3.2")
    u = st.text_input("Usuario").lower().strip()
    p = st.text_input("Contraseña", type="password")
    if st.button("Entrar"):
        if u in USUARIOS and USUARIOS[u] == p:
            st.session_state.auth = True; st.session_state.user = u; st.rerun()
else:
    ws = conectar()
    if ws:
        # Traemos datos y limpiamos nombres de columnas
        data = ws.get_all_records()
        df_raw = pd.DataFrame(data)
        if not df_raw.empty:
            df_raw.columns = [str(c).upper().strip() for c in df_raw.columns]
            
            # Aseguramos tipos de datos numéricos para evitar el error de edición
            cols_num = ['COSTO USD', 'AMAZON', 'ENVIO', '% FEE', 'TIPO CAMBIO']
            for col in cols_num:
                if col in df_raw.columns:
                    df_raw[col] = pd.to_numeric(df_raw[col], errors='coerce').fillna(0.0)

    es_editor = st.session_state.user in ["admin", "dav", "dax", "cesar"]

    with st.sidebar:
        st.header(f"👤 {st.session_state.user.upper()}")
        st.write("---")
        if st.button("Cerrar Sesión"):
            st.session_state.auth = False; st.rerun()

    st.title("📊 Simulador de Precios sr.sicho")
    st.info("💡 Modifica la columna **AMAZON** para ver el margen real al instante.")

    if not df_raw.empty:
        # 1. Preparar el DataFrame con cálculos actuales
        df_sim = df_raw.copy()
        calcs = df_sim.apply(lambda r: calcular_margen_dinamico(r['AMAZON'], r['COSTO USD'], r['TIPO CAMBIO'], r['% FEE'], r['ENVIO']), axis=1)
        df_sim['UTILIDAD'] = calcs.apply(lambda x: x[0])
        df_sim['MARGEN %'] = calcs.apply(lambda x: x[1])

        # 2. Configuración de columnas del Editor
        config = {
            "SKU": st.column_config.TextColumn("SKU", disabled=True),
            "PRODUCTO": st.column_config.TextColumn("PRODUCTO", disabled=True, width="large"),
            "AMAZON": st.column_config.NumberColumn("AMAZON (Simular)", format="$%.2f", min_value=0.0, help="Escribe el nuevo precio aquí"),
            "UTILIDAD": st.column_config.NumberColumn("UTILIDAD", format="$%.2f", disabled=True),
            "MARGEN %": st.column_config.NumberColumn("MARGEN %", format="%.2f%%", disabled=True),
            "COSTO USD": st.column_config.NumberColumn("COSTO USD", disabled=True, format="$%.2f"),
            "TIPO CAMBIO": st.column_config.NumberColumn("TC", disabled=True),
        }

        # 3. Mostrar el Editor (Aquí es donde ocurría el error, ahora está blindado)
        edited_df = st.data_editor(
            df_sim[['SKU', 'PRODUCTO', 'COSTO USD', 'TIPO CAMBIO', 'AMAZON', 'UTILIDAD', 'MARGEN %', 'ENVIO', '% FEE']],
            column_config=config,
            use_container_width=True,
            hide_index=True,
            height=800,
            key="simulador_editor" # Key fija para mantener consistencia
        )

        # 4. Recalcular Márgenes en tiempo real sobre lo editado
        final_calcs = edited_df.apply(lambda r: calcular_margen_dinamico(r['AMAZON'], r['COSTO USD'], r['TIPO CAMBIO'], r['% FEE'], r['ENVIO']), axis=1)
        edited_df['UTILIDAD'] = final_calcs.apply(lambda x: x[0])
        edited_df['MARGEN %'] = final_calcs.apply(lambda x: x[1])

        # 5. Botón de Guardado (Solo para Editores)
        if es_editor:
            col_save, col_spacer = st.columns([1, 4])
            if col_save.button("🚀 APLICAR PRECIOS A NUBE"):
                with st.spinner("Actualizando Google Sheets..."):
                    # Solo actualizamos si hubo cambios
                    for i, row in edited_df.iterrows():
                        precio_original = float(df_raw.at[i, 'AMAZON'])
                        precio_nuevo = float(row['AMAZON'])
                        
                        if precio_original != precio_nuevo:
                            # Columna AMAZON es la 4 en el Sheet (D)
                            ws.update_cell(i + 2, 4, precio_nuevo)
                    
                    st.success("¡Precios oficiales actualizados!")
                    st.rerun()

        # Acordeón para Registro y Bulk
        if es_editor:
            with st.expander("⚙️ Gestión de Inventario (Registro y Carga Masiva)"):
                st.write("Usa esta sección para añadir nuevos productos.")
                # (Aquí incluirías los formularios de la v3.0 si los necesitas operativos)

    else:
        st.warning("No hay datos disponibles.")
