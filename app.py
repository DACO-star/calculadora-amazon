import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import io
from fpdf import FPDF

# --- CalcuAMZ v2.5 (Modo Lector + Tabla 50 Filas) ---
st.set_page_config(layout="wide", page_title="CalcuAMZ v2.5")

# Agregamos el usuario de consulta
USUARIOS = {
    "admin": "amazon123", "dav": "ventas2026",
    "dax": "amazon2026", "cesar": "ventas789",
    "consulta": "lector2026" # <--- Nuevo usuario
}

def conectar():
    info = st.secrets["gcp_service_account"]
    creds = Credentials.from_service_account_info(info, scopes=["https://www.googleapis.com/auth/spreadsheets"])
    return gspread.authorize(creds).open_by_key("1mF-9Ayv95PJmk4v8PrIDHf2-lRnHFZd5WOxQ__cb3Ss").sheet1

def calcular_precio_sugerido(costo_usd, fee_pct, envio_fba, t_cambio):
    if costo_usd <= 0: return 0.0
    costo_mx = costo_usd * t_cambio
    tax_factor = (0.08 + 0.025) / 1.16
    divisor = 1 - (fee_pct/100) - tax_factor
    return ((costo_mx * 1.1112) + envio_fba) / divisor

def calcular_detallado(r):
    c_usd = float(r.get('COSTO USD', 0))
    p_amz = float(r.get('AMAZON', 0))
    p_fee = float(r.get('% FEE', 10.0))
    env = float(r.get('ENVIO', 0))
    t_c = float(r.get('TIPO CAMBIO', 18.00))
    costo_mxn = c_usd * t_c
    dinero_fee = p_amz * (p_fee / 100)
    base_gravable = p_amz / 1.16
    ret_iva = base_gravable * 0.08
    ret_isr = base_gravable * 0.025
    neto = p_amz - dinero_fee - abs(env) - ret_iva - ret_isr
    utilidad = neto - costo_mxn
    margen = (utilidad / neto) * 100 if neto > 0 else 0
    return pd.Series([costo_mxn, dinero_fee, ret_iva, ret_isr, neto, utilidad, margen])

def estilo_filas(row):
    estilos = [''] * len(row)
    if 'AMAZON' in row.index:
        idx_amz = row.index.get_loc('AMAZON')
        estilos[idx_amz] = 'background-color: #a65d00; color: white; font-weight: bold;'
    if 'MARGEN %' in row.index:
        val = row['MARGEN %']
        idx_margen = row.index.get_loc('MARGEN %')
        color_letra = 'color: #ff4b4b;' if val < 0 else 'color: white;'
        if val <= 6.0: bg = 'background-color: #551a1a;'
        elif 6.1 <= val <= 8.0: bg = 'background-color: #5e541e;'
        else: bg = 'background-color: #1a4d1a;'
        estilos[idx_margen] = f'{color_letra} {bg}'
    return estilos

# --- INICIO DE APP ---
if 'auth' not in st.session_state: st.session_state.auth = False

if not st.session_state.auth:
    st.title("🔐 Acceso - CalcuAMZ")
    u = st.text_input("Usuario").lower().strip()
    p = st.text_input("Clave", type="password")
    if st.button("Ingresar"):
        if u in USUARIOS and USUARIOS[u] == p:
            st.session_state.auth = True; st.session_state.user = u; st.rerun()
        else: st.error("Acceso denegado")
else:
    try:
        ws = conectar(); df_raw = pd.DataFrame(ws.get_all_records())
        if not df_raw.empty: df_raw.columns = [str(c).strip().upper() for c in df_raw.columns]
    except: st.error("Error de conexión"); st.stop()

    # VISIBILIDAD DE HERRAMIENTAS
    es_editor = st.session_state.user in ["admin", "dav", "dax", "cesar"]

    with st.sidebar:
        st.header(f"👤 {st.session_state.user.upper()}")
        if es_editor:
            dolar_actual = st.number_input("T.C. para nuevas cargas", value=18.00, step=0.01)
        st.divider()
        if st.button("Cerrar Sesión"):
            st.session_state.auth = False; st.rerun()

    st.title("📦 Panel de Consulta de Precios")

    # Si es editor, mostramos las pestañas de gestión. Si es consulta, no mostramos nada aquí.
    if es_editor:
        t1, t2, t3 = st.tabs(["➕ Registro", "✏️ Editar / Borrar", "📂 Carga Masiva"])
        with t1:
            with st.form("nuevo"):
                sk = st.text_input("SKU").strip().upper()
                no = st.text_input("Nombre")
                c1, c2 = st.columns(2)
                cos = c1.number_input("Costo USD", format="%.2f")
                fee = c2.number_input("% Fee Amazon", value=10.0)
                env = c1.number_input("Envío FBA", value=0.0)
                pr = c2.number_input("Precio Venta", value=float(calcular_precio_sugerido(cos, fee, env, dolar_actual)))
                if st.form_submit_button("Guardar"):
                    ws.append_row([sk if sk else f"A-{len(df_raw)+1}", no.upper(), cos, pr, env, fee, dolar_actual])
                    st.rerun()
        # (Las pestañas t2 y t3 mantienen su lógica anterior...)
    else:
        st.info("💡 Modo de solo lectura activado. Utiliza el buscador para consultar precios.")

    st.divider()
    
    if not df_raw.empty:
        # Buscador siempre visible para todos
        busqueda = st.text_input("🔍 Buscar Producto (SKU o Nombre)").strip().upper()
        
        res = df_raw.apply(calcular_detallado, axis=1)
        res.columns = ['COSTO MXN', 'FEE $', 'RET IVA', 'RET ISR', 'NETO RECIBIDO', 'UTILIDAD', 'MARGEN %']
        df_f = pd.concat([df_raw, res], axis=1)
        
        orden = ['SKU', 'PRODUCTO', 'COSTO USD', 'TIPO CAMBIO', 'COSTO MXN', 'AMAZON', 'ENVIO', '% FEE', 'FEE $', 'RET IVA', 'RET ISR', 'NETO RECIBIDO', 'UTILIDAD', 'MARGEN %']
        df_f = df_f[[c for c in orden if c in df_f.columns]]
        
        if busqueda: 
            df_f = df_f[df_f['SKU'].astype(str).str.contains(busqueda) | df_f['PRODUCTO'].astype(str).str.contains(busqueda)]
        
        # Formatos
        moneda = ['COSTO USD', 'TIPO CAMBIO', 'COSTO MXN', 'AMAZON', 'ENVIO', 'FEE $', 'RET IVA', 'RET ISR', 'NETO RECIBIDO', 'UTILIDAD']
        formato = {c: "${:,.2f}" for c in moneda}
        formato.update({'MARGEN %': "{:.2f}%", '% FEE': "{:.2f}%"})
        
        # TABLA EXPANDIDA (height=1200 para ~50 filas)
        st.dataframe(
            df_f.style.format(formato, na_rep="-").apply(estilo_filas, axis=1), 
            use_container_width=True, 
            height=1200, 
            hide_index=True
        )
