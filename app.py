import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import io

# ==========================================
# CALCUAMZ v4.3.7 - PRECIO OBJETIVO 10% NETO
# ==========================================

st.set_page_config(layout="wide", page_title="CalcuAMZ v4.3.7", page_icon="📦")

def conectar():
    try:
        info = st.secrets["gcp_service_account"]
        creds = Credentials.from_service_account_info(info, scopes=["https://www.googleapis.com/auth/spreadsheets"])
        return gspread.authorize(creds).open_by_key("1mF-9Ayv95PJmk4v8PrIDHf2-lRnHFZd5WOxQ__cb3Ss").sheet1
    except: return None

def clean(val, def_val=0.0):
    try:
        if pd.isna(val) or str(val).strip() == "": return def_val
        v = str(val).replace('$', '').replace(',', '').strip()
        return float(v)
    except: return def_val

def calcular_detallado(r):
    try:
        c_usd = clean(r.get('COSTO USD', 0))
        p_amz_orig = clean(r.get('AMAZON', 0))
        p_fee_pct = clean(r.get('% FEE', 4.0))
        env = clean(r.get('ENVIO', 80.0))
        t_c = clean(r.get('TIPO CAMBIO', 18.00))
        
        costo_mxn = c_usd * t_c
        fee_dec = p_fee_pct / 100
        
        # --- NUEVA LÓGICA DE DESPEJE PARA 10% DE MARGEN NETO ---
        # Definición: Margen = (Neto - Costo) / Neto = 0.10
        # Por lo tanto: Costo = Neto * 0.90  =>  Neto = Costo / 0.90
        # Neto = Precio * (1 - Fee - (0.105/1.16)) - Envio
        # Precio = ( (Costo / 0.90) + Envio ) / (1 - Fee - 0.090517)
        
        const_ret = 0.09051724  # (0.08 + 0.025) / 1.16
        
        if p_amz_orig <= 0:
            objetivo_neto = costo_mxn / 0.90
            p_amz = (objetivo_neto + env) / (1 - fee_dec - const_ret)
        else:
            p_amz = p_amz_orig

        dinero_fee = p_amz * fee_dec
        base_grav = p_amz / 1.16
        ret_iva, ret_isr = base_grav * 0.08, base_grav * 0.025
        neto = p_amz - dinero_fee - env - ret_iva - ret_isr
        utilidad = neto - costo_mxn
        margen = (utilidad / neto) * 100 if neto > 0 else 0
        
        return pd.Series([p_amz, costo_mxn, dinero_fee, ret_iva, ret_isr, neto, utilidad, margen])
    except: return pd.Series([0.0]*8)

def estilo_semaforo(row):
    estilos = [''] * len(row)
    if 'MARGEN %' in row.index:
        val = row['MARGEN %']
        idx = row.index.get_loc('MARGEN %')
        # Ajuste de semáforo: Verde solo si es >= 10%
        bg = '#551a1a' if val <= 6.0 else ('#5e541e' if val < 9.99 else '#1a4d1a')
        estilos[idx] = f'background-color: {bg}; color: white; font-weight: bold;'
    return estilos

# --- LOGIN ---
USUARIOS = {"admin": "amazon123", "dav": "ventas2026", "dax": "amazon2026", "cesar": "ventas789"}
if 'auth' not in st.session_state: st.session_state.auth = False

if not st.session_state.auth:
    st.title("🔐 Acceso CalcuAMZ")
    u = st.text_input("Usuario").lower().strip()
    p = st.text_input("Password", type="password")
    if st.button("Entrar"):
        if u in USUARIOS and USUARIOS[u] == p:
            st.session_state.auth, st.session_state.user = True, u; st.rerun()
else:
    ws = conectar()
    data = ws.get_all_records() if ws else []
    df_raw = pd.DataFrame(data) if data else pd.DataFrame()

    if not df_raw.empty:
        df_raw.columns = [str(c).upper().strip() for c in df_raw.columns]
        calc = df_raw.apply(calcular_detallado, axis=1)
        calc.columns = ['AMZ_C', 'C_MX_V', 'F_V', 'IVA_V', 'ISR_V', 'NETO_V', 'UTIL_V', 'MARG_V']
        df_full = pd.concat([df_raw, calc], axis=1)
        df_full['AMAZON'] = df_full.apply(lambda x: x['AMZ_C'] if clean(x['AMAZON']) <= 0 else clean(x['AMAZON']), axis=1)

    st.title("📊 Dacocel Master Dashboard v4.3.7")
    
    t1, t2, t3 = st.tabs(["➕ Nuevo", "✏️ Editar", "📂 Bulk (Plantilla Dinámica)"])

    with t1:
        with st.form("f_new"):
            st.subheader("Registrar Producto")
            sk, nom = st.text_input("SKU"), st.text_input("Nombre")
            c1, c2, c3, c4, c5 = st.columns(5)
            cos, pre, env, fee, tc = c1.number_input("Costo USD"), c2.number_input("Precio AMZ (0=Auto)"), c3.number_input("Envío", 80.0), c4.number_input("% Fee", 4.0), c5.number_input("TC", 18.0)
            if st.form_submit_button("🚀 Guardar"):
                if nom: ws.append_row([sk, nom.upper(), cos, pre, env, fee, tc]); st.rerun()

    with t2:
        if not df_raw.empty:
            opcs = (df_full['SKU'].astype(str) + " - " + df_full['PRODUCTO']).tolist()
            sel = st.selectbox("Seleccionar:", opcs)
            sku_s = str(sel).split(" - ")[0]
            idx = df_full[df_full['SKU'].astype(str) == sku_s].index[0]
            curr = df_full.iloc[idx]
            with st.form("f_edit"):
                enom = st.text_input("Nombre", value=str(curr['PRODUCTO']))
                ce1, ce2, ce3, ce4, ce5 = st.columns(5)
                ecos, epre, eenv, efee, etc = ce1.number_input("Costo USD", value=clean(curr['COSTO USD'])), ce2.number_input("Precio AMZ", value=clean(curr['AMAZON'])), ce3.number_input("Envío", value=clean(curr['ENVIO'])), ce4.number_input("% Fee", value=clean(curr['% FEE'])), ce5.number_input("TC", value=clean(curr['TIPO CAMBIO']))
                if st.form_submit_button("💾 Actualizar"):
                    ws.update(f'A{idx+2}:G{idx+2}', [[sku_s, enom.upper(), ecos, epre, eenv, efee, etc]])
                    st.rerun()

    with t3:
        st.subheader("Carga Masiva con TC Dinámico")
        # Aquí eliges el TC que quieres que lleve la plantilla
        tc_plantilla = st.number_input("Tipo de Cambio para la descarga:", value=18.0, step=0.01)
        
        # Plantilla con el TC seleccionado por el usuario
        plantilla = pd.DataFrame({
            'SKU': ['M-X'], 'PRODUCTO': ['NOMBRE'], 'COSTO USD': [0.0], 
            'AMAZON': [0], 'ENVIO': [80.0], '% FEE': [4.0], 'TIPO CAMBIO': [tc_plantilla]
        })
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine='xlsxwriter') as wr: plantilla.to_excel(wr, index=False)
        st.download_button(f"📥 Bajar Plantilla (TC: {tc_plantilla})", buf.getvalue(), f"plantilla_tc_{tc_plantilla}.xlsx")
        
        st.divider()
        archivo = st.file_uploader("Subir Excel", type=['xlsx'])
        if archivo and st.button("🚀 Procesar Bulk"):
            df_b = pd.read_excel(archivo)
            ws.append_rows(df_b.values.tolist()); st.rerun()

    st.divider()
    if not df_raw.empty:
        df_final = df_full[['SKU', 'PRODUCTO', 'COSTO USD', 'AMAZON', 'ENVIO', '% FEE', 'TIPO CAMBIO', 'C_MX_V', 'F_V', 'IVA_V', 'ISR_V', 'NETO_V', 'UTIL_V', 'MARG_V']].copy()
        df_final.columns = ['SKU', 'PRODUCTO', 'COSTO USD', 'AMAZON', 'ENVIO', '% FEE', 'TC', 'C_MXN', 'F_$', 'IVA', 'ISR', 'NETO', 'UTILIDAD', 'MARGEN %']
        
        formateo = {
            "COSTO USD": "${:,.2f}", "AMAZON": "${:,.2f}", "ENVIO": "${:,.2f}", "TC": "${:,.2f}", 
            "C_MXN": "${:,.2f}", "F_$": "${:,.2f}", "IVA": "${:,.2f}", "ISR": "${:,.2f}", 
            "NETO": "${:,.2f}", "UTILIDAD": "${:,.2f}", "MARGEN %": "{:.2f}%", "% FEE": "{:.2f}%"
        }
        st.dataframe(df_final.style.format(formateo).apply(estilo_semaforo, axis=1), use_container_width=True, height=600, hide_index=True)
