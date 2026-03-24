import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

# --- CalcuAMZ ver 1.8 (Formato con Símbolos Correctos) ---
st.set_page_config(layout="wide", page_title="CalcuAMZ ver 1.8")

USUARIOS = {
    "admin": "amazon123", "dav": "ventas2026",
    "dax": "amazon2026", "cesar": "ventas789"
}
TIPO_CAMBIO = 18.00

def conectar():
    info = st.secrets["gcp_service_account"]
    creds = Credentials.from_service_account_info(info, scopes=["https://www.googleapis.com/auth/spreadsheets"])
    return gspread.authorize(creds).open_by_key("1mF-9Ayv95PJmk4v8PrIDHf2-lRnHFZd5WOxQ__cb3Ss").sheet1

def calcular_precio_sugerido(costo_usd, fee_pct, envio_fba):
    if costo_usd <= 0: return 0.0
    costo_mx = costo_usd * TIPO_CAMBIO
    tax_factor = (0.08 + 0.025) / 1.16
    divisor = 1 - (fee_pct/100) - tax_factor
    return ((costo_mx * 1.1112) + envio_fba) / divisor

def calcular_detallado(r):
    c_usd = float(r.get('COSTO USD', 0))
    p_amz = float(r.get('AMAZON', 0))
    p_fee = float(r.get('% FEE', 10.0))
    env = float(r.get('ENVIO', 0))
    
    costo_mxn = c_usd * TIPO_CAMBIO
    dinero_fee = p_amz * (p_fee / 100)
    base_gravable = p_amz / 1.16
    ret_iva = base_gravable * 0.08
    ret_isr = base_gravable * 0.025
    
    neto = p_amz - dinero_fee - abs(env) - ret_iva - ret_isr
    utilidad = neto - costo_mxn
    margen = (utilidad / neto) * 100 if neto > 0 else 0
    return pd.Series([costo_mxn, dinero_fee, ret_iva, ret_isr, neto, utilidad, margen])

if 'auth' not in st.session_state: 
    st.session_state.auth = False

if not st.session_state.auth:
    st.title("🔐 Acceso - CalcuAMZ")
    u = st.text_input("Usuario").lower().strip()
    p = st.text_input("Clave", type="password")
    if st.button("Ingresar"):
        if u in USUARIOS and USUARIOS[u] == p:
            st.session_state.auth = True; st.session_state.user = u
            st.rerun()
        else: st.error("Error de acceso")
else:
    try:
        ws = conectar(); df_raw = pd.DataFrame(ws.get_all_records())
        if not df_raw.empty: df_raw.columns = [str(c).strip().upper() for c in df_raw.columns]
    except: st.error("Error de conexión"); st.stop()

    st.title("📦 Gestión de Inventario")
    t1, t2, t3 = st.tabs(["➕ Individual", "✏️ Editar / Borrar", "📂 Carga con Auto-Precio"])

    with t1:
        st.subheader("Asistente de Registro")
        sk_input = st.text_input("SKU (Vacío para automático)").strip().upper()
        with st.form("nuevo"):
            no = st.text_input("Nombre Producto")
            c1, c2 = st.columns(2)
            c_usd_in = c1.number_input("Costo USD", format="%.2f")
            fe_input = c2.number_input("% Fee Amazon", value=10.0)
            env_in = c1.number_input("Envío FBA (MXN)", value=0.0)
            
            pr_sug = calcular_precio_sugerido(c_usd_in, fe_input, env_in)
            pr = c2.number_input("Precio Final (Sugerido 10% margen)", value=float(pr_sug))
            
            if st.form_submit_button("Guardar"):
                if no:
                    f_sku = sk_input if sk_input else f"AUTO-{len(df_raw)+1:03d}"
                    ws.append_row([f_sku, no.upper(), c_usd_in, pr, env_in, fe_input])
                    st.success("¡Guardado!"); st.rerun()

    with t2:
        if not df_raw.empty:
            ops = df_raw['SKU'].astype(str) + " - " + df_raw['PRODUCTO'].astype(str)
            sel = st.selectbox("Seleccionar para editar", ops)
            sku_sel = sel.split(" - ")[0]
            idx = df_raw[df_raw['SKU'].astype(str) == sku_sel].index[0]
            curr = df_raw.iloc[idx]
            with st.form("edit"):
                enom = st.text_input("Nombre", value=str(curr['PRODUCTO']))
                ecos = st.number_input("Costo USD", value=float(curr['COSTO USD']))
                epre = st.number_input("Precio MXN", value=float(curr['AMAZON']))
                efee = st.number_input("% Fee", value=float(curr['% FEE']))
                eenv = st.number_input("Envío", value=float(curr['ENVIO']))
                if st.form_submit_button("Actualizar"):
                    ws.update(range_name=f'A{idx+2}:F{idx+2}', values=[[sku_sel, enom.upper(), ecos, epre, eenv, efee]])
                    st.rerun()
            if st.session_state.user in ["admin", "dav"] and st.button("🗑️ Eliminar"):
                ws.delete_rows(int(idx + 2)); st.rerun()

    with t3:
        st.subheader("Carga Masiva con Cálculo Automático")
        archivo = st.file_uploader("Subir Excel/CSV del proveedor", type=['xlsx', 'csv'])
        if archivo:
            df_b = pd.read_excel(archivo) if archivo.name.endswith('xlsx') else pd.read_csv(archivo)
            df_b.columns = [str(c).strip().upper() for c in df_b.columns]
            if all(c in df_b.columns for c in ['PRODUCTO', 'COSTO USD']):
                if 'SKU' not in df_b.columns: df_b['SKU'] = [f"B-{i+len(df_raw)+1:03d}" for i in range(len(df_b))]
                if 'ENVIO' not in df_b.columns: df_b['ENVIO'] = 0.0
                if '% FEE' not in df_b.columns: df_b['% FEE'] = 10.0
                df_b['AMAZON'] = df_b.apply(lambda r: calcular_precio_sugerido(r['COSTO USD'], r['% FEE'], r['ENVIO']), axis=1)
                st.write("Vista previa:")
                st.dataframe(df_b[['SKU', 'PRODUCTO', 'COSTO USD', 'AMAZON', 'ENVIO', '% FEE']].head())
                if st.button("🚀 Subir a Sheets"):
                    ws.append_rows(df_b[['SKU', 'PRODUCTO', 'COSTO USD', 'AMAZON', 'ENVIO', '% FEE']].values.tolist())
                    st.success("¡Cargado!"); st.rerun()

    st.divider()
    if not df_raw.empty:
        busqueda = st.text_input("🔍 Buscar SKU o Producto...", "").strip().upper()
        res = df_raw.apply(calcular_detallado, axis=1)
        res.columns = ['COSTO MXN', 'FEE $', 'RET IVA', 'RET ISR', 'NETO RECIBIDO', 'UTILIDAD', 'MARGEN %']
        df_f = pd.concat([df_raw, res], axis=1)
        
        if busqueda:
            df_f = df_f[df_f['SKU'].astype(str).str.contains(busqueda) | df_f['PRODUCTO'].astype(str).str.contains(busqueda)]
        
        m1, m2 = st.columns(2)
        m1.metric("Productos", len(df_f))
        m2.metric("Margen Promedio", f"{df_f['MARGEN %'].mean():.2f}%")
        
        # --- FORMATO CON SIGNOS RE-ACTIVADO ---
        cols_moneda = ['COSTO USD','AMAZON','ENVIO','COSTO MXN','FEE $','RET IVA','RET ISR','NETO RECIBIDO','UTILIDAD']
        cols_porcentaje = ['MARGEN %','% FEE']
        
        formato = {c: "${:,.2f}" for c in cols_moneda}
        formato.update({c: "{:.2f}%" for c in cols_porcentaje})
        
        st.dataframe(
            df_f.style.format(formato), 
            use_container_width=True, 
            height=500
        )
