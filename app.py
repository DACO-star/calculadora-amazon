import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import io

# ==========================================
# CALCUAMZ v4.3.9 - FULL MODULES RESTORED
# ==========================================

st.set_page_config(layout="wide", page_title="CalcuAMZ v4.3.9", page_icon="📦")

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
        p_amz_input = clean(r.get('AMAZON', 0))
        p_fee_pct = clean(r.get('% FEE', 4.0))
        env = clean(r.get('ENVIO', 80.0))
        t_c = clean(r.get('TIPO CAMBIO', 18.00))
        
        costo_mxn = c_usd * t_c
        fee_dec = p_fee_pct / 100
        const_ret = 0.09051724  # (0.08 + 0.025) / 1.16
        
        # LÓGICA AUTO-PRECIO PARA 10.00% NETO
        if p_amz_input <= 0:
            neto_objetivo = costo_mxn / 0.90
            p_amz = (neto_objetivo + env) / (1 - fee_dec - const_ret)
        else:
            p_amz = p_amz_input

        dinero_fee = p_amz * fee_dec
        base_grav = p_amz / 1.16
        ret_iva, ret_isr = base_grav * 0.08, base_grav * 0.025
        neto_recibido = p_amz - dinero_fee - env - ret_iva - ret_isr
        utilidad = neto_recibido - costo_mxn
        margen = (utilidad / neto_recibido) * 100 if neto_recibido > 0 else 0
        
        return pd.Series([p_amz, costo_mxn, dinero_fee, ret_iva, ret_isr, neto_recibido, utilidad, margen])
    except: return pd.Series([0.0]*8)

def estilo_semaforo(row):
    estilos = [''] * len(row)
    if 'MARGEN %' in row.index:
        val = row['MARGEN %']
        idx = row.index.get_loc('MARGEN %')
        bg = '#551a1a' if val < 7.0 else ('#5e541e' if val < 9.99 else '#1a4d1a')
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
        calc = df_raw.apply(calcular_detallado, axis=1)
        calc.columns = ['AMZ_P', 'C_MXN_V', 'FEE_V', 'IVA_V', 'ISR_V', 'NETO_V', 'UTIL_V', 'MARG_V']
        df_full = pd.concat([df_raw, calc], axis=1)

    st.title("📊 Dacocel Master Dashboard v4.3.9")
    
    t1, t2, t3 = st.tabs(["➕ Agregar Nuevo", "✏️ Editar / Eliminar", "📂 Carga Masiva (Bulk)"])

    with t1:
        with st.form("nuevo_pro"):
            st.subheader("Registrar Nuevo Producto")
            f1, f2 = st.columns(2)
            sk = f1.text_input("SKU (Único)")
            nom = f2.text_input("Nombre del Producto")
            c1, c2, c3, c4, c5 = st.columns(5)
            cos = c1.number_input("Costo USD", min_value=0.0, step=0.01)
            pre = c2.number_input("Precio Amazon (0 = Auto)", min_value=0.0, step=0.01)
            env = c3.number_input("Envío MXN", value=80.0)
            fee = c4.number_input("% Fee", value=4.0)
            tc = c5.number_input("Tipo Cambio", value=18.0)
            if st.form_submit_button("🚀 Guardar en Google Sheets"):
                if nom and sk:
                    ws.append_row([sk, nom.upper(), cos, pre, env, fee, tc])
                    st.success(f"Producto {sk} guardado.")
                    st.rerun()

    with t2:
        if not df_raw.empty:
            st.subheader("Gestión de Inventario")
            opciones = (df_full['SKU'].astype(str) + " - " + df_full['PRODUCTO']).tolist()
            seleccion = st.selectbox("Busca el producto a modificar:", opciones)
            sku_edit = str(seleccion).split(" - ")[0]
            idx_row = df_full[df_full['SKU'].astype(str) == sku_edit].index[0]
            curr_item = df_full.iloc[idx_row]
            
            with st.form("edit_pro"):
                enom = st.text_input("Editar Nombre", value=str(curr_item['PRODUCTO']))
                ce1, ce2, ce3, ce4, ce5 = st.columns(5)
                ecos = ce1.number_input("Costo USD", value=clean(curr_item['COSTO USD']))
                epre = ce2.number_input("Precio AMZ", value=clean(curr_item['AMAZON']))
                eenv = ce3.number_input("Envío", value=clean(curr_item['ENVIO']))
                efee = ce4.number_input("% Fee", value=clean(curr_item['% FEE']))
                etc = ce5.number_input("Tipo Cambio", value=clean(curr_item['TIPO CAMBIO']))
                
                col_btn1, col_btn2 = st.columns([1, 4])
                if col_btn1.form_submit_button("💾 Actualizar"):
                    ws.update(f'A{idx_row+2}:G{idx_row+2}', [[sku_edit, enom.upper(), ecos, epre, eenv, efee, etc]])
                    st.rerun()
            
            if st.button("🗑️ Eliminar Producto Definitivamente"):
                ws.delete_rows(int(idx_row + 2))
                st.warning("Producto eliminado.")
                st.rerun()

    with t3:
        st.subheader("Plantilla con Tipo de Cambio Dinámico")
        tc_bulk = st.number_input("Define el TC para la plantilla de hoy:", value=18.0, step=0.01)
        plantilla = pd.DataFrame({
            'SKU': ['M-X'], 'PRODUCTO': ['IPHONE...'], 'COSTO USD': [0.0], 
            'AMAZON': [0], 'ENVIO': [80.0], '% FEE': [4.0], 'TIPO CAMBIO': [tc_bulk]
        })
        buf = io.BytesIO()
        with pd.ExcelWriter(buf) as wr: plantilla.to_excel(wr, index=False)
        st.download_button(f"📥 Descargar Plantilla (TC {tc_bulk})", buf.getvalue(), f"plantilla_dacocel_tc_{tc_bulk}.xlsx")
        
        st.divider()
        archivo_bulk = st.file_uploader("Subir archivo Excel completado", type=['xlsx'])
        if archivo_bulk and st.button("🚀 Iniciar Carga Masiva"):
            df_bulk_up = pd.read_excel(archivo_bulk)
            ws.append_rows(df_bulk_up.values.tolist())
            st.success("Carga masiva completada.")
            st.rerun()

    st.divider()
    if not df_raw.empty:
        st.subheader("📋 Listado Maestro de Precios")
        df_final = df_full[['SKU', 'PRODUCTO', 'COSTO USD', 'AMZ_P', 'ENVIO', '% FEE', 'TIPO CAMBIO', 'C_MXN_V', 'FEE_V', 'IVA_V', 'ISR_V', 'NETO_V', 'UTIL_V', 'MARG_V']].copy()
        df_final.columns = ['SKU', 'PRODUCTO', 'COSTO USD', 'AMAZON', 'ENVIO', '% FEE', 'TC', 'C_MXN', 'F_$', 'IVA', 'ISR', 'NETO', 'UTILIDAD', 'MARGEN %']
        
        formateo = {
            "COSTO USD": "${:,.2f}", "AMAZON": "${:,.2f}", "ENVIO": "${:,.2f}", "TC": "${:,.2f}", 
            "C_MXN": "${:,.2f}", "F_$": "${:,.2f}", "IVA": "${:,.2f}", "ISR": "${:,.2f}", 
            "NETO": "${:,.2f}", "UTILIDAD": "${:,.2f}", "MARGEN %": "{:.2f}%", "% FEE": "{:.2f}%"
        }
        st.dataframe(df_final.style.format(formateo).apply(estilo_semaforo, axis=1), use_container_width=True, height=500, hide_index=True)
