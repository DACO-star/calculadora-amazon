import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import io

# ==========================================
# CALCUAMZ v4.2.7 - AUTO-PRICING & UNLOCKED FEE
# ==========================================

st.set_page_config(layout="wide", page_title="CalcuAMZ v4.2.7", page_icon="📦")

def conectar():
    try:
        info = st.secrets["gcp_service_account"]
        creds = Credentials.from_service_account_info(info, scopes=["https://www.googleapis.com/auth/spreadsheets"])
        return gspread.authorize(creds).open_by_key("1mF-9Ayv95PJmk4v8PrIDHf2-lRnHFZd5WOxQ__cb3Ss").sheet1
    except: return None

def calcular_detallado(r):
    try:
        # Limpieza de datos
        def to_f(val, default=0.0):
            try:
                v = str(val).replace('$', '').replace(',', '').strip()
                return float(v) if v != "" else default
            except: return default

        c_usd = to_f(r.get('COSTO USD', 0))
        p_amz_raw = to_f(r.get('AMAZON', 0)) # Si está vacío en el sheet, llega como 0
        p_fee = to_f(r.get('% FEE', 10.0))
        env = to_f(r.get('ENVIO', 0))
        t_c = to_f(r.get('TIPO CAMBIO', 18.00))
        
        costo_mxn = c_usd * t_c
        fee_decimal = p_fee / 100

        # --- LÓGICA DE CÁLCULO AUTOMÁTICO ---
        # Si el precio Amazon es 0 o está vacío, calculamos el sugerido para un margen del 10%
        if p_amz_raw <= 0:
            # Fórmula inversa considerando retenciones (IVA 8%, ISR 2.5% sobre base)
            # El divisor asegura que después de todos los gastos quede el 10% de margen neto
            divisor = (1 - fee_decimal - (0.105 / 1.16) - 0.10)
            p_amz = (costo_mxn + abs(env)) / divisor if divisor > 0 else 0
        else:
            p_amz = p_amz_raw

        dinero_fee = p_amz * fee_decimal
        base_grav = p_amz / 1.16
        ret_iva, ret_isr = base_grav * 0.08, base_grav * 0.025
        neto = p_amz - dinero_fee - abs(env) - ret_iva - ret_isr
        utilidad = neto - costo_mxn
        margen = (utilidad / neto) * 100 if neto > 0 else 0
        
        return pd.Series([p_amz, costo_mxn, dinero_fee, ret_iva, ret_isr, neto, utilidad, margen])
    except: return pd.Series([0,0,0,0,0,0,0,0])

def estilo_filas(row):
    estilos = [''] * len(row)
    if 'MARGEN %' in row.index:
        val = row['MARGEN %']
        idx = row.index.get_loc('MARGEN %')
        bg = '#551a1a' if val <= 6.0 else ('#5e541e' if val <= 8.0 else '#1a4d1a')
        estilos[idx] = f'background-color: {bg}; color: white; font-weight: bold;'
    return estilos

# --- ACCESO ---
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
    if ws is None: st.error("Error Sheets"); st.stop()
    
    registros = ws.get_all_records()
    if not registros:
        st.info("Base de datos vacía.")
        df_raw = pd.DataFrame()
    else:
        df_raw = pd.DataFrame(registros)
        df_raw.columns = [str(c).upper().strip() for c in df_raw.columns]
        
        # Aplicamos el cálculo que autocompleta los precios vacíos
        calc_res = df_raw.apply(calcular_detallado, axis=1)
        calc_res.columns = ['AMAZON_CALC', 'C_MX', 'F_$', 'IVA', 'ISR', 'NETO', 'UTIL', 'MARGEN']
        
        # Reemplazamos el Amazon original por el calculado si el original era 0
        df_full = pd.concat([df_raw, calc_res], axis=1)
        df_full['AMAZON'] = df_full['AMAZON_CALC']

        st.title("📊 Dacocel Master Dashboard v4.2.7")
        
        t1, t2, t3 = st.tabs(["➕ Nuevo", "✏️ Editar", "📂 Bulk"])
        
        with t1:
            with st.form("f_new"):
                st.subheader("Registrar Producto")
                sk_in = st.text_input("SKU").upper().strip()
                no_in = st.text_input("Nombre").upper().strip()
                c1, c2, c3, c4, c5 = st.columns(5)
                # ELIMINADO EL LÍMITE DE 10.0 EN FEE
                cos = c1.number_input("Costo USD", value=0.0)
                pre = c2.number_input("Precio AMZ (0 para auto)", value=0.0)
                env_in = c3.number_input("Envío MXN", value=80.0)
                fee_in = c4.number_input("% Fee", value=4.0, min_value=0.0, step=0.1) 
                tc_in = c5.number_input("TC", value=18.0)
                if st.form_submit_button("🚀 Guardar"):
                    if no_in:
                        ws.append_row([sk_in if sk_in else f"M-{len(df_raw)+1}", no_in, cos, pre, env_in, fee_in, tc_in])
                        st.rerun()

        with t2:
            opciones = (df_raw['SKU'].astype(str) + " - " + df_raw['PRODUCTO']).tolist()
            if opciones:
                sel = st.selectbox("Selecciona:", opciones)
                sku_sel = str(sel).split(" - ")[0]
                idx = df_raw[df_raw['SKU'].astype(str) == sku_sel].index[0]
                curr = df_raw.iloc[idx]
                with st.form("f_edit"):
                    enom = st.text_input("Nombre", value=str(curr.get('PRODUCTO', '')))
                    ce1, ce2, ce3, ce4, ce5 = st.columns(5)
                    ecos = ce1.number_input("Costo", value=float(curr.get('COSTO USD', 0)))
                    epre = ce2.number_input("Precio (0 = Auto)", value=float(curr.get('AMAZON', 0)))
                    eenv = ce3.number_input("Envío", value=float(curr.get('ENVIO', 80.0)))
                    efee = ce4.number_input("% Fee", value=float(curr.get('% FEE', 4.0)), min_value=0.0)
                    etc = ce5.number_input("TC", value=float(curr.get('TIPO CAMBIO', 18.0)))
                    if st.form_submit_button("💾 Actualizar"):
                        ws.update(f'A{idx+2}:G{idx+2}', [[sku_sel, enom.upper(), ecos, epre, eenv, efee, etc]])
                        st.rerun()

        st.divider()
        # --- TABLA FINAL ---
        df_final = df_full[['SKU', 'PRODUCTO', 'COSTO USD', 'AMAZON', 'ENVIO', '% FEE', 'TIPO CAMBIO', 'C_MX', 'F_$', 'IVA', 'ISR', 'NETO', 'UTIL', 'MARGEN']].copy()
        df_final.columns = ['SKU', 'PRODUCTO', 'COSTO USD', 'AMAZON', 'ENVIO', '% FEE', 'TC', 'C_MXN', 'F_$', 'IVA', 'ISR', 'NETO', 'UTILIDAD', 'MARGEN %']
        
        fmt = {c: "${:,.2f}" for c in ['COSTO USD', 'AMAZON', 'ENVIO', 'TC', 'C_MXN', 'F_$', 'IVA', 'ISR', 'NETO', 'UTILIDAD']}
        fmt.update({'MARGEN %': "{:.2f}%", '% FEE': "{:.2f}%"})
        
        st.write("### M - Listado Maestro (Precios Calculados)")
        st.dataframe(df_final.style.format(fmt).apply(estilo_filas, axis=1), use_container_width=True, height=800, hide_index=True)
