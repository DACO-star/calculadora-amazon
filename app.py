import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import io
from fpdf import FPDF

# ==========================================
# CALCUAMZ v3.0 - MASTER EDITION (SR.SICHO)
# ==========================================

st.set_page_config(layout="wide", page_title="CalcuAMZ v3.0", page_icon="📦")

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

def calcular_detallado(r):
    try:
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
    except:
        return pd.Series([0,0,0,0,0,0,0])

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
    st.title("🔐 Acceso CalcuAMZ v3.0")
    c1, c2 = st.columns(2)
    u = c1.text_input("Usuario").lower().strip()
    p = c2.text_input("Contraseña", type="password")
    if st.button("Ingresar"):
        if u in USUARIOS and USUARIOS[u] == p:
            st.session_state.auth = True; st.session_state.user = u; st.rerun()
else:
    ws = conectar()
    if ws is None:
        st.error("Error de conexión"); st.stop()
    
    data = ws.get_all_records()
    df_raw = pd.DataFrame(data)
    if not df_raw.empty:
        df_raw.columns = [str(c).strip().upper() for c in df_raw.columns]

    es_editor = st.session_state.user in ["admin", "dav", "dax", "cesar"]

    with st.sidebar:
        st.title("🛠️ Opciones")
        st.write(f"Usuario: {st.session_state.user.upper()}")
        if st.button("Cerrar Sesión"):
            st.session_state.auth = False; st.rerun()

    st.title("📦 Panel de Control v3.0")

    # --- SECCIÓN DE GESTIÓN (TABS) ---
    if es_editor:
        t1, t2, t3 = st.tabs(["➕ Nuevo", "✏️ Editar / Borrar", "📂 Bulk"])
        
        with t1:
            with st.form("f_nuevo"):
                sk = st.text_input("SKU").upper()
                no = st.text_input("Nombre")
                c1, c2, c3 = st.columns(3)
                cos = c1.number_input("Costo USD", format="%.2f")
                pre = c2.number_input("Precio Amazon", format="%.2f")
                tc = c3.number_input("TC", value=18.50)
                if st.form_submit_button("Guardar"):
                    ws.append_row([sk, no.upper(), cos, pre, 0, 10, tc])
                    st.rerun()

        with t2:
            if not df_raw.empty:
                sel = st.selectbox("Producto a editar", df_raw['SKU'].astype(str) + " - " + df_raw['PRODUCTO'])
                idx = df_raw[df_raw['SKU'].astype(str) == sel.split(" - ")[0]].index[0]
                curr = df_raw.iloc[idx]
                with st.form("f_editar"):
                    enom = st.text_input("Nombre", value=str(curr['PRODUCTO']))
                    ce1, ce2, ce3, ce4 = st.columns(4)
                    ecos = ce1.number_input("Costo USD", value=float(curr['COSTO USD']))
                    epre = ce2.number_input("Precio Amazon", value=float(curr['AMAZON']))
                    efee = ce3.number_input("% Fee", value=float(curr.get('% FEE', 10.0)))
                    etc = ce4.number_input("TC", value=float(curr.get('TIPO CAMBIO', 18.0)))
                    if st.form_submit_button("Actualizar Datos"):
                        ws.update(f'A{idx+2}:G{idx+2}', [[curr['SKU'], enom.upper(), ecos, epre, curr['ENVIO'], efee, etc]])
                        st.rerun()
                if st.button("🗑️ Eliminar"):
                    ws.delete_rows(int(idx + 2)); st.rerun()

        with t3:
            st.write("Carga masiva habilitada.")

    st.divider()

    # --- TABLA PRINCIPAL (SIEMPRE VISIBLE) ---
    if not df_raw.empty:
        busq = st.text_input("🔍 Buscar SKU o Producto...").upper()
        
        calc = df_raw.apply(calcular_detallado, axis=1)
        calc.columns = ['COSTO MXN', 'FEE $', 'RET IVA', 'RET ISR', 'NETO', 'UTILIDAD', 'MARGEN %']
        df_f = pd.concat([df_raw, calc], axis=1)
        
        if busq:
            df_f = df_f[df_f['SKU'].astype(str).str.contains(busq) | df_f['PRODUCTO'].astype(str).str.contains(busq)]

        # Formato de moneda y porcentaje
        mon_cols = ['COSTO USD', 'TIPO CAMBIO', 'COSTO MXN', 'AMAZON', 'ENVIO', 'FEE $', 'RET IVA', 'RET ISR', 'NETO', 'UTILIDAD']
        fmt = {c: "${:,.2f}" for c in mon_cols}
        fmt.update({'MARGEN %': "{:.2f}%", '% FEE': "{:.2f}%"})

        st.dataframe(
            df_f.style.format(fmt, na_rep="-").apply(estilo_filas, axis=1),
            use_container_width=True, height=800, hide_index=True
        )
