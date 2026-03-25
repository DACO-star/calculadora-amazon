import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import io

# ==========================================
# CALCUAMZ v4.3.5 - TOTAL REPAIR & SYNC
# ==========================================

st.set_page_config(layout="wide", page_title="CalcuAMZ v4.3.5", page_icon="📦")

COLS_MAESTRAS = ['SKU', 'PRODUCTO', 'COSTO USD', 'AMAZON', 'ENVIO', '% FEE', 'TIPO CAMBIO']

# --- ESTILO ---
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
        # Convertimos todo a float forzosamente para evitar errores de cálculo
        c_usd = pd.to_numeric(r.get('COSTO USD', 0), errors='coerce') or 0.0
        p_amz = pd.to_numeric(r.get('AMAZON', 0), errors='coerce') or 0.0
        p_fee = pd.to_numeric(r.get('% FEE', 10.0), errors='coerce') or 10.0
        env = pd.to_numeric(r.get('ENVIO', 0), errors='coerce') or 0.0
        t_c = pd.to_numeric(r.get('TIPO CAMBIO', 18.50), errors='coerce') or 18.50
        
        costo_mxn = float(c_usd) * float(t_c)
        dinero_fee = float(p_amz) * (float(p_fee) / 100)
        base_grav = float(p_amz) / 1.16
        ret_iva, ret_isr = base_grav * 0.08, base_grav * 0.025
        neto = float(p_amz) - dinero_fee - abs(float(env)) - ret_iva - ret_isr
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
    u, p = st.text_input("Usuario").lower().strip(), st.text_input("Password", type="password")
    if st.button("Entrar"):
        if u in USUARIOS and USUARIOS[u] == p:
            st.session_state.auth, st.session_state.user = True, u
            st.rerun()
        else: st.error("Error")
else:
    # --- SIDEBAR ---
    with st.sidebar:
        try: st.image("500x500LOGODACO.png", width=150)
        except: st.subheader("📦 DACOCEL")
        st.divider()
        st.write(f"Usuario: **{st.session_state.user.upper()}**")
        if st.button("Cerrar Sesión"): st.session_state.auth = False; st.rerun()

    # --- DATOS ---
    ws = conectar()
    if ws is None: st.error("Error Sheets"); st.stop()
    
    raw_data = ws.get_all_values()
    
    if not raw_data or raw_data[0][0].upper() != 'SKU':
        # Si la hoja está mal (sin SKU en A1), la reseteamos con encabezados
        ws.insert_row(COLS_MAESTRAS, 1)
        st.warning("Encabezados corregidos. Recargando...")
        st.rerun()
    
    # Cargamos el DataFrame asegurando que la fila 1 son las columnas
    df_raw = pd.DataFrame(raw_data[1:], columns=raw_data[0])
    df_raw.columns = [str(c).upper().strip() for c in df_raw.columns]

    # Convertimos numéricos para evitar el error de float() en la línea 149
    for col in ['COSTO USD', 'AMAZON', 'ENVIO', '% FEE', 'TIPO CAMBIO']:
        df_raw[col] = pd.to_numeric(df_raw[col], errors='coerce').fillna(0.0)

    st.title("📊 Master Dashboard v4.3.5")

    df_full = pd.DataFrame()
    if not df_raw.empty:
        calc_res = df_raw.apply(calcular_detallado, axis=1)
        calc_res.columns = ['C_MX', 'F_$', 'IVA', 'ISR', 'NETO', 'UTIL', 'MARGEN']
        df_full = pd.concat([df_raw, calc_res], axis=1)
        m1, m2 = st.columns(2)
        m1.metric("Productos", len(df_raw))
        m2.metric("Margen Promedio", f"{df_full['MARGEN'].mean():.2f}%")
    
    st.divider()
    t1, t2, t3 = st.tabs(["➕ Nuevo", "✏️ Editar", "📂 Bulk"])

    with t1:
        with st.form("f_new"):
            st.subheader("Registrar Producto")
            sk_in = st.text_input("SKU (Prefijo M si vacío)").upper().strip()
            no_in = st.text_input("Nombre").upper().strip()
            c1, c2, c3, c4, c5 = st.columns(5)
            cos = c1.number_input("Costo USD", min_value=0.0)
            pre = c2.number_input("Precio AMZ", min_value=0.0)
            env_in = c3.number_input("Envío MXN", min_value=0.0)
            fee_in = c4.number_input("% Fee", value=10.0)
            tc_in = c5.number_input("TC", value=18.50)
            if st.form_submit_button("💾 Guardar"):
                if not no_in: st.error("Falta el nombre")
                else:
                    sk_f = sk_in if sk_in else f"M-{len(df_raw)+1}"
                    ws.append_row([sk_f, no_in, cos, pre, env_in, fee_in, tc_in])
                    st.rerun()

    with t2:
        if df_raw.empty: st.info("Nada que editar.")
        else:
            busq_ed = st.text_input("Filtrar para editar...").upper().strip()
            # Combinación segura de strings
            df_raw['COMBO'] = df_raw['SKU'].astype(str) + " - " + df_raw['PRODUCTO'].astype(str)
            op_f = [o for o in df_raw['COMBO'].tolist() if busq_ed in o] if busq_ed else df_raw['COMBO'].tolist()
            
            if op_f:
                sel = st.selectbox("Seleccionar:", op_f)
                idx_orig = df_raw[df_raw['COMBO'] == sel].index[0]
                curr_row = df_raw.iloc[idx_orig]
                
                with st.form("f_edit_main"):
                    enom = st.text_input("Nombre", value=str(curr_row['PRODUCTO']))
                    ce1, ce2, ce3, ce4, ce5 = st.columns(5)
                    ecos = ce1.number_input("Costo", value=float(curr_row['COSTO USD']))
                    epre = ce2.number_input("Precio", value=float(curr_row['AMAZON']))
                    eenv = ce3.number_input("Envío", value=float(curr_row['ENVIO']))
                    efee = ce4.number_input("Fee", value=float(curr_row['% FEE']))
                    etc = ce5.number_input("TC", value=float(curr_row['TIPO CAMBIO']))
                    
                    sub_col1, sub_col2 = st.columns(2)
                    if sub_col1.form_submit_button("✅ Actualizar"):
                        ws.update(f'A{idx_orig+2}:G{idx_orig+2}', [[str(curr_row['SKU']), enom.upper(), ecos, epre, eenv, efee, etc]])
                        st.rerun()
                    if sub_col2.form_submit_button("🗑️ Eliminar"):
                        ws.delete_rows(int(idx_orig + 2))
                        st.rerun()

    with t3:
        st.subheader("Carga Masiva")
        tc_bulk = st.number_input("Dólar para esta carga", value=18.50)
        modo = st.radio("Modo:", ["➕ Añadir", "🔄 Upsert (Sincronizar)"], horizontal=True)
        f_bulk = st.file_uploader("Subir Archivo", type=['xlsx', 'csv'])
        if f_bulk and st.button("🚀 Procesar Carga"):
            df_b = pd.read_excel(f_bulk) if f_bulk.name.endswith('xlsx') else pd.read_csv(f_bulk)
            df_b.columns = [str(c).upper().strip() for c in df_b.columns]
            df_b['TIPO CAMBIO'] = tc_bulk
            for c in COLS_MAESTRAS:
                if c not in df_b.columns: df_b[c] = ""
            df_b = df_b[COLS_MAESTRAS].fillna("")
            
            # Autogenerar M-SKUs
            count_base = len(df_raw)
            df_b['SKU'] = [str(r['SKU']) if str(r['SKU']).strip() != "" else f"M-{count_base+i+1}" for i, r in df_b.iterrows()]
            
            if modo == "➕ Añadir":
                ws.append_rows(df_b.values.tolist())
            else:
                # Sincronización
                df_act = df_raw.copy()
                df_act.set_index('PRODUCTO', inplace=True)
                df_b_proc = df_b.copy().set_index('PRODUCTO')
                df_act.update(df_b_proc)
                nuevos = df_b_proc[~df_b_proc.index.isin(df_act.index)]
                df_f = pd.concat([df_act, nuevos]).reset_index()
                df_f = df_f[COLS_MAESTRAS].fillna("")
                ws.clear()
                ws.update('A1', [COLS_MAESTRAS] + df_f.values.tolist())
            st.rerun()

    # --- TABLA FINAL ---
    if not df_full.empty:
        st.divider()
        busq = st.text_input("🔍 Filtro Maestro...").upper()
        df_viz = df_full.copy()
        df_viz.columns = ['SKU', 'PRODUCTO', 'C USD', 'AMZ', 'ENV', 'FEE', 'TC', 'C MXN', 'F $', 'IVA', 'ISR', 'NETO', 'UTIL', 'MARGEN %']
        if busq:
            df_viz = df_viz[df_viz['SKU'].astype(str).str.contains(busq) | df_viz['PRODUCTO'].astype(str).str.contains(busq)]
        
        fmt = {c: "${:,.2f}" for c in ['C USD', 'AMZ', 'ENV', 'TC', 'C MXN', 'F $', 'IVA', 'ISR', 'NETO', 'UTIL']}
        fmt.update({'MARGEN %': "{:.2f}%", 'FEE': "{:.2f}%"})
        st.dataframe(df_viz.style.format(fmt).apply(estilo_filas, axis=1), use_container_width=True, height=600, hide_index=True)
