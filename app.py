import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import io
from fpdf import FPDF

# ==========================================
# CALCUAMZ v4.3.4 - MARGEN 10% EXACTO & FORMAT FIX
# ==========================================

st.set_page_config(layout="wide", page_title="CalcuAMZ v4.3.4", page_icon="📦")

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

        # FÓRMULA PARA MARGEN 10% NETO EXACTO
        # Neto = Precio - Fee - Envio - Ret_IVA - Ret_ISR
        # Ret_IVA = (Precio/1.16)*0.08 | Ret_ISR = (Precio/1.16)*0.025
        # Queremos que: (Neto - Costo) / Neto = 0.10
        if p_amz_orig <= 0:
            # Constante de retenciones: (0.08 + 0.025) / 1.16 = 0.090517
            # Divisor para margen 10% sobre neto:
            p_amz = (costo_mxn + env) / (0.90 * (1 - fee_dec - 0.090517))
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
        # Colores Dacocel: Rojo oscuro, Ámbar, Verde oscuro
        bg = '#551a1a' if val <= 6.0 else ('#5e541e' if val <= 9.9 else '#1a4d1a')
        estilos[idx] = f'background-color: {bg}; color: white; font-weight: bold;'
    return estilos

# --- SEGURIDAD ---
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
        
        # Aseguramos columnas base para evitar el error anterior
        for c in ['SKU', 'PRODUCTO', 'COSTO USD', 'AMAZON', 'ENVIO', '% FEE', 'TIPO CAMBIO']:
            if c not in df_raw.columns: df_raw[c] = 0.0 if c != 'PRODUCTO' else "S/N"

        # Calculamos valores dinámicos
        calc = df_raw.apply(calcular_detallado, axis=1)
        calc.columns = ['AMZ_CALC', 'C_MXN_VAL', 'F_VAL', 'IVA_VAL', 'ISR_VAL', 'NETO_VAL', 'UTIL_VAL', 'MARGEN_VAL']
        
        # Unimos y priorizamos el precio calculado si el original es 0
        df_full = pd.concat([df_raw, calc], axis=1)
        df_full['AMAZON'] = df_full.apply(lambda x: x['AMZ_CALC'] if clean(x['AMAZON']) <= 0 else clean(x['AMAZON']), axis=1)

        st.title("📊 Dacocel Master Dashboard v4.3.4")
        
        t1, t2, t3 = st.tabs(["➕ Nuevo", "✏️ Editar", "📂 Bulk"])

        with t1:
            with st.form("f_new"):
                st.subheader("Registrar Producto")
                sk, nom = st.text_input("SKU"), st.text_input("Nombre")
                c1, c2, c3, c4, c5 = st.columns(5)
                cos = c1.number_input("Costo USD", step=0.01)
                pre = c2.number_input("Precio AMZ (0=Auto)", step=0.01)
                env = c3.number_input("Envío MXN", value=80.0)
                fee = c4.number_input("% Fee", value=4.0)
                tc = c5.number_input("T. Cambio", value=18.0)
                if st.form_submit_button("🚀 Guardar"):
                    if nom: ws.append_row([sk, nom.upper(), cos, pre, env, fee, tc]); st.rerun()

        with t2:
            opcs = (df_full['SKU'].astype(str) + " - " + df_full['PRODUCTO']).tolist()
            sel = st.selectbox("Selecciona para editar:", opcs)
            sku_s = str(sel).split(" - ")[0]
            idx = df_full[df_full['SKU'].astype(str) == sku_s].index[0]
            curr = df_full.iloc[idx]
            with st.form("f_edit"):
                enom = st.text_input("Nombre", value=str(curr['PRODUCTO']))
                ce1, ce2, ce3, ce4, ce5 = st.columns(5)
                ecos = ce1.number_input("Costo USD", value=clean(curr['COSTO USD']), step=0.01)
                epre = ce2.number_input("Precio AMZ", value=clean(curr['AMAZON']), step=0.01)
                eenv = ce3.number_input("Envío", value=clean(curr['ENVIO']), step=0.01)
                efee = ce4.number_input("% Fee", value=clean(curr['% FEE']), step=0.01)
                etc = ce5.number_input("T. Cambio", value=clean(curr['TIPO CAMBIO']), step=0.01)
                if st.form_submit_button("💾 Actualizar"):
                    ws.update(f'A{idx+2}:G{idx+2}', [[sku_s, enom.upper(), ecos, epre, eenv, efee, etc]])
                    st.rerun()
            if st.button("🗑️ Eliminar"): ws.delete_rows(int(idx + 2)); st.rerun()

        with t3:
            st.subheader("Carga Masiva")
            plantilla = pd.DataFrame(columns=['SKU', 'PRODUCTO', 'COSTO USD', 'AMAZON', 'ENVIO', '% FEE', 'TIPO CAMBIO'])
            buf = io.BytesIO()
            with pd.ExcelWriter(buf, engine='xlsxwriter') as wr: plantilla.to_excel(wr, index=False)
            st.download_button("📥 Descargar Plantilla", buf.getvalue(), "plantilla_dacocel.xlsx")
            archivo = st.file_uploader("Subir archivo Excel", type=['xlsx'])
            if archivo and st.button("🚀 Procesar Carga"):
                df_b = pd.read_excel(archivo)
                ws.append_rows(df_b.values.tolist()); st.rerun()

        st.divider()
        # --- TABLA MAESTRA FINAL ---
        df_final = df_full[['SKU', 'PRODUCTO', 'COSTO USD', 'AMAZON', 'ENVIO', '% FEE', 'TIPO CAMBIO', 'C_MXN_VAL', 'F_VAL', 'IVA_VAL', 'ISR_VAL', 'NETO_VAL', 'UTIL_VAL', 'MARGEN_VAL']].copy()
        df_final.columns = ['SKU', 'PRODUCTO', 'COSTO USD', 'AMAZON', 'ENVIO', '% FEE', 'TC', 'C_MXN', 'F_$', 'IVA', 'ISR', 'NETO', 'UTILIDAD', 'MARGEN %']
        
        # Filtro de búsqueda
        busq = st.text_input("🔍 Filtro por Nombre o SKU...").upper()
        if busq: df_final = df_final[df_final['PRODUCTO'].str.contains(busq) | df_final['SKU'].astype(str).str.contains(busq)]

        # Definición estricta de formatos
        formateo = {
            "COSTO USD": "${:,.2f}", "AMAZON": "${:,.2f}", "ENVIO": "${:,.2f}", 
            "TC": "${:,.2f}", "C_MXN": "${:,.2f}", "F_$": "${:,.2f}", 
            "IVA": "${:,.2f}", "ISR": "${:,.2f}", "NETO": "${:,.2f}", 
            "UTILIDAD": "${:,.2f}", "MARGEN %": "{:.2f}%", "% FEE": "{:.2f}%"
        }

        # Renderizado final con estilo
        st.dataframe(
            df_final.style.format(formateo).apply(estilo_semaforo, axis=1), 
            use_container_width=True, 
            height=600, 
            hide_index=True
        )
