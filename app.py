import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

# ==========================================
# CALCUAMZ v4.2.1 - RESTAURACIÓN ESTABLE
# ==========================================

st.set_page_config(layout="wide", page_title="CalcuAMZ v4.2.1", page_icon="📦")

# --- CONFIGURACIÓN DE COLUMNAS (Tal cual están en tu Sheets) ---
# Si en tu Excel la columna B es el nombre, aquí la llamamos PRODUCTO
COLS_MAESTRAS = ['SKU', 'PRODUCTO', 'COSTO USD', 'AMAZON', 'ENVIO', '% FEE', 'TIPO CAMBIO']

def conectar():
    try:
        info = st.secrets["gcp_service_account"]
        creds = Credentials.from_service_account_info(info, scopes=["https://www.googleapis.com/auth/spreadsheets"])
        # Tu ID de hoja actual
        return gspread.authorize(creds).open_by_key("1mF-9Ayv95PJmk4v8PrIDHf2-lRnHFZd5WOxQ__cb3Ss").sheet1
    except:
        return None

def calcular_resumen(r):
    try:
        # Lógica de cálculo original v4.2.1
        c_usd = float(r[2]) if r[2] else 0.0
        p_amz = float(r[3]) if r[3] else 0.0
        env = float(r[4]) if r[4] else 0.0
        fee_p = float(r[5]) if r[5] else 10.0
        tc = float(r[6]) if r[6] else 18.50

        costo_mxn = c_usd * tc
        comision = p_amz * (fee_p / 100)
        # Retenciones estándar (8% IVA, 2.5% ISR sobre base sin IVA)
        base_iva = p_amz / 1.16
        retenciones = base_iva * 0.105
        
        neto = p_amz - comision - env - retenciones
        utilidad = neto - costo_mxn
        margen = (utilidad / neto) * 100 if neto > 0 else 0
        return pd.Series([costo_mxn, neto, utilidad, margen])
    except:
        return pd.Series([0, 0, 0, 0])

# --- SEGURIDAD ---
USUARIOS = {"admin": "amazon123", "dav": "ventas2026", "dax": "amazon2026", "cesar": "ventas789"}
if 'auth' not in st.session_state: st.session_state.auth = False

if not st.session_state.auth:
    st.title("🔐 Acceso CalcuAMZ")
    u = st.text_input("Usuario").lower().strip()
    p = st.text_input("Password", type="password")
    if st.button("Entrar"):
        if u in USUARIOS and USUARIOS[u] == p:
            st.session_state.auth = True
            st.session_state.user = u
            st.rerun()
        else:
            st.error("Credenciales incorrectas")
else:
    # --- INTERFAZ PRINCIPAL ---
    ws = conectar()
    if ws:
        # IMPORTANTE: v4.2.1 asume que la fila 1 son encabezados
        datos = ws.get_all_values()
        if len(datos) > 1:
            df = pd.DataFrame(datos[1:], columns=COLS_MAESTRAS)
            
            # Procesar cálculos
            res = df.apply(calcular_resumen, axis=1)
            res.columns = ['COSTO_MXN', 'NETO_AMZ', 'UTILIDAD', 'MARGEN_%']
            df_final = pd.concat([df, res], axis=1)

            st.title(f"📊 Dashboard - {st.session_state.user.upper()}")
            
            # Métricas rápidas
            c1, c2, c3 = st.columns(3)
            c1.metric("Total SKUs", len(df_final))
            c2.metric("Margen Promedio", f"{df_final['MARGEN_%'].mean():.2f}%")
            c3.metric("TC Configurado", f"${float(datos[1][6]):.2f}")

            st.divider()

            # Pestañas simples
            t1, t2 = st.tabs(["📦 Inventario Actual", "➕ Nueva Carga"])

            with t1:
                st.subheader("Listado de Productos")
                # Buscador simple
                busqueda = st.text_input("Buscar por nombre o SKU...").upper()
                if busqueda:
                    df_viz = df_final[df_final['PRODUCTO'].str.contains(busqueda) | df_final['SKU'].str.contains(busqueda)]
                else:
                    df_viz = df_final

                st.dataframe(df_viz, use_container_width=True)

            with t2:
                st.info("Para subir nuevos productos, agrégalos directamente en la fila de abajo en tu Google Sheets.")
                if st.button("🔄 Refrescar Datos"):
                    st.rerun()
    else:
        st.error("No se pudo conectar con la base de datos de Google.")

    if st.sidebar.button("Cerrar Sesión"):
        st.session_state.auth = False
        st.rerun()
