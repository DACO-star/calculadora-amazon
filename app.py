import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import io

# ==========================================
# CALCUAMZ v4.2.9 - COLUMNS SAFETY NET
# ==========================================

st.set_page_config(layout="wide", page_title="CalcuAMZ v4.2.9", page_icon="📦")

# --- CONFIGURACIÓN DE COLUMNAS MAESTRAS ---
COLS_MAESTRAS = ['SKU', 'PRODUCTO', 'COSTO USD', 'AMAZON', 'ENVIO', '% FEE', 'TIPO CAMBIO']

# --- ESTILO VISUAL ---
st.markdown("""
    <style>
    .stApp { background-color: #0e1117; }
    .stMetric { background-color: #1e2130; padding: 20px; border-radius: 12px; border-left: 5px solid #a65d00; }
    div[data-testid="stForm"] { background-color: #161b22; border: 1px solid #30363d; border-radius: 15px; padding: 25px; }
    </style>
    """, unsafe_allow_html=True)

def conectar():
    try:
        info = st.secrets["gcp_service_account"]
        creds = Credentials.from_service_account_info(info, scopes=["https://www.googleapis.com/auth/spreadsheets"])
        return gspread.authorize(creds).open_by_key("1mF-9Ayv95PJmk4v8PrIDHf2-lRnHFZd5WOxQ__cb3Ss").sheet1
    except: return None

def calcular_detallado(r):
    try:
        c_usd = float(r.get('COSTO USD', 0))
        p_amz = float(r.get('AMAZON', 0))
        p_fee = float(r.get('% FEE', 10.0))
        env = float(r.get('ENVIO', 0))
        t_c = float(r.get('TIPO CAMBIO', 18.50))
        costo_mxn = c_usd * t_c
        dinero_fee = p_amz * (p_fee / 100)
        base_grav = p_amz / 1.16
        ret_iva, ret_isr = base_grav * 0.08, base_grav * 0.025
        neto = p_amz - dinero_fee - abs(env) - ret_iva - ret_isr
        utilidad = neto - costo_mxn
        margen = (utilidad / neto) * 100 if neto > 0 else 0
        return pd.Series([costo_mxn, dinero_fee, ret_iva, ret_isr, neto, utilidad, margen])
    except: return pd.Series([0,0,0,0,0,0,0])

def estilo_filas(row):
    estilos = [''] * len(row)
    if 'MARGEN %' in row.index:
        val = row['MARGEN %']
        idx = row.index.get_loc('MARGEN %')
        bg = '#551a1a' if val <= 6.0 else ('#5e541e' if val <= 8.0 else '#1a4d1a')
        estilos[idx] = f'background-color: {bg}; color: white; font-weight: bold;'
    return estilos

# --- SEGURIDAD ---
USUARIOS = {"admin": "amazon123", "dav": "ventas2026", "dax": "amazon2026", "cesar": "ventas789"}
if 'auth' not in st.session_state: st.session_state.auth = False

if not st.session_state.auth:
    st.title("🔐 Acceso CalcuAMZ")
    c1, c2 = st.columns(2)
    u, p = c1.text_input("Usuario").lower().strip(), c2.text_input("Password", type="password")
    if st.button("Entrar"):
        if u in USUARIOS and USUARIOS[u] == p:
            st.session_state.auth, st.session_state.user = True, u
            st.rerun()
        else: st.error("Error de acceso")
else:
    # --- SIDEBAR ---
    with st.sidebar:
        col_l1, col_l2, col_l3 = st.columns([0.5, 2, 0.5])
        with col_l2:
            try: st.image("500x500LOGODACO.png", width=150)
            except: st.subheader("📦 DACOCEL")
        st.divider()
        st.write(f"Usuario: **{st.session_state.user.upper()}**")
        if st.button("Cerrar Sesión", use_container_width=True):
            st.session_state.auth = False
            st.rerun()

    # --- DATOS (Malla de Seguridad) ---
    ws = conectar()
    if ws is None: st.error("Error de conexión con Sheets"); st.stop()
    
    registros = ws.get_all_records()
    if not registros:
        # Si la hoja está vacía, creamos un DF con las columnas correctas
        df_raw = pd.DataFrame(columns=COLS_MAESTRAS)
    else:
        df_raw = pd.DataFrame(registros)
        df_raw.columns = [str(c).upper().strip() for c in df_raw.columns]
        # Aseguramos que todas las columnas necesarias existan
        for c in COLS_MAESTRAS:
            if c not in df_raw.columns: df_raw[c] = 0

    st.title("📊 Master Dashboard v4.2.9")

    # Cálculos si hay datos
    df_full = pd.DataFrame()
    if not df_raw.empty:
        calc_res = df_raw.apply(calcular_detallado, axis=1)
        calc_res.columns = ['C_MX', 'F_$', 'IVA', 'ISR', 'NETO', 'UTIL', 'MARGEN']
        df_full = pd.concat([df_raw, calc_res], axis=1)
        m1, m2 = st.columns(2)
        m1.metric("Productos", len(df_raw))
        m2.metric("Margen Promedio", f"{df_full['MARGEN'].mean():.2f}%")
    
    st.divider()

    # --- TABS ---
    t1, t2, t3 = st.tabs(["➕ Nuevo", "✏️ Editar", "📂 Bulk"])

    with t1:
        with st.form("f_new"):
            st.subheader("Nuevo Producto")
            sk_in = st.text_input("SKU (M- si vacío)").upper().strip()
            no_in = st.text_input("Nombre (Obligatorio)").upper().strip()
            c1, c2, c3, c4, c5 = st.columns(5)
            cos = c1.number_input("Costo USD", value=0.0)
            pre = c2.number_input("Precio AMZ", value=0.0)
            env_in = c3.number_input("Envío MXN", value=0.0)
            fee_in = c4.number_input("% Fee", value=10.0)
            tc_in = c5.number_input("TC", value=18.50)
            if st.form_submit_button("🚀 Guardar"):
                if not no_in: st.error("Falta el nombre")
                else:
                    sk_f = sk_in if sk_in else f"M-{len(df_raw)+1}"
                    ws.append_row([sk_f, no_in, cos, pre, env_in, fee_in, tc_in])
                    st.success("Guardado!"); st.rerun()

    with t2:
        if df_raw.empty:
            st.info("Nada que editar aún.")
        else:
            busq_ed = st.text_input("Filtrar para editar...").upper().strip()
            # PROTECCIÓN: Solo intentamos armar opciones si las columnas existen
            opciones = (df_raw['SKU'].astype(str) + " - " + df_raw['PRODUCTO']).tolist()
            opciones_f = [o for o in opciones if busq_ed in str(o).upper()] if busq_ed else opciones
            
            if opciones_f:
                sel = st.selectbox("Seleccionar:", opciones_f)
                sku_sel = str(sel).split(" - ")[0]
                idx = df_raw[df_raw['SKU'].astype(str) == sku_sel].index[0]
                curr = df_raw.iloc[idx]
                with st.form("f_edit"):
                    enom = st.text_input("Nombre", value=str(curr['PRODUCTO']))
                    ce1, ce2, ce3, ce4, ce5 = st.columns(5)
                    ecos = ce1.number_input("Costo USD", value=float(curr['COSTO USD']))
                    epre = ce2.number_input("Precio AMZ", value=float(curr['AMAZON']))
                    eenv = ce3.number_input("Envío", value=float(curr.get('ENVIO', 0)))
                    efee = ce4.number_input("% Fee", value=float(curr.get('% FEE', 10)))
                    etc = ce5.number_input("TC", value=float(curr.get('TIPO CAMBIO', 18.50)))
                    if st.form_submit_button("💾 Actualizar"):
                        ws.update(f'A{idx+2}:G{idx+2}', [[sku_sel, enom.upper(), ecos, epre, eenv, efee, etc]])
                        st.success("Actualizado!"); st.rerun()
                if st.button("🗑️ Eliminar"): ws.delete_rows(int(idx + 2)); st.rerun()

    with t3:
        st.subheader("Sincronización Bulk")
        tc_bulk = st.number_input("Dólar Carga", value=18.50)
        modo = st.radio("Modo:", ["➕ Añadir", "🔄 Sincronizar (Nombre)"], horizontal=True)
        f_bulk = st.file_uploader("Excel/CSV", type=['xlsx', 'csv'])
        if f_bulk and st.button("🚀 Iniciar"):
            df_b = pd.read_excel(f_bulk) if f_bulk.name.endswith('xlsx') else pd.read_csv(f_bulk)
            df_b.columns = [str(c).upper().strip() for c in df_b.columns]
            df_b['TIPO CAMBIO'] = tc_bulk
            for c in COLS_MAESTRAS: 
                if c not in df_b.columns: df_b[c] = ""
            df_b = df_b[COLS_MAESTRAS].fillna("")
            
            # Autogenerar SKUs M-
            count = len(df_raw)
            df_b['SKU'] = [str(r['SKU']) if str(r['SKU']).strip() != "" else f"M-{count+i+1}" for i, r in df_b.iterrows()]
            
            if modo == "➕ Añadir":
                ws.append_rows(df_b.values.tolist())
            else:
                if df_raw.empty:
                    ws.update('A1', [COLS_MAESTRAS] + df_b.values.tolist())
                else:
                    df_act = df_raw.copy()
                    df_act['PRODUCTO'] = df_act['PRODUCTO'].astype(str).str.upper().str.strip()
                    df_b['PRODUCTO'] = df_b['PRODUCTO'].astype(str).str.upper().str.strip()
                    df_act.set_index('PRODUCTO', inplace=True); df_b.set_index('PRODUCTO', inplace=True)
                    df_act.update(df_b)
                    nuevos = df_b[~df_b.index.isin(df_act.index)]
                    df_final = pd.concat([df_act, nuevos]).reset_index()
                    df_final = df_final[COLS_MAESTRAS].fillna("")
                    ws.clear()
                    ws.update('A1', [COLS_MAESTRAS] + df_final.values.tolist())
            st.success("¡Operación exitosa!"); st.rerun()

    # --- VISTA TABLA ---
    if not df_full.empty:
        st.divider()
        busq = st.text_input("🔍 Filtro Maestro (SKU o Nombre)...").upper()
        df_viz = df_full.copy()
        df_viz.columns = ['SKU', 'PRODUCTO', 'COSTO USD', 'AMAZON', 'ENVIO', '% FEE', 'TC', 'C_MXN', 'F_$', 'IVA', 'ISR', 'NETO', 'UTILIDAD', 'MARGEN %']
        if busq: df_viz = df_viz[df_viz['SKU'].astype(str).str.contains(busq) | df_viz['PRODUCTO'].astype(str).str.contains(busq)]
        
        fmt = {c: "${:,.2f}" for c in ['COSTO USD', 'AMAZON', 'ENVIO', 'TC', 'C_MXN', 'F_$', 'IVA', 'ISR', 'NETO', 'UTILIDAD']}
        fmt.update({'MARGEN %': "{:.2f}%", '% FEE': "{:.2f}%"})
        st.dataframe(df_viz.style.format(fmt).apply(estilo_filas, axis=1), use_container_width=True, height=800, hide_index=True)
