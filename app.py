import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import io
from fpdf import FPDF

# --- CalcuAMZ v2.3.2 (Amazon Brand Style) ---
st.set_page_config(layout="wide", page_title="CalcuAMZ v2.3.2")

USUARIOS = {
    "admin": "amazon123", "dav": "ventas2026",
    "dax": "amazon2026", "cesar": "ventas789"
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

# --- LÓGICA DE COLORES ---
def estilo_filas(row):
    estilos = [''] * len(row)
    
    # 1. Estilo para la columna AMAZON (Naranja Amazon)
    if 'AMAZON' in row.index:
        idx_amz = row.index.get_loc('AMAZON')
        estilos[idx_amz] = 'background-color: #FF9900; color: black; font-weight: bold;'
    
    # 2. Estilo para la columna MARGEN % (Semáforo)
    if 'MARGEN %' in row.index:
        val = row['MARGEN %']
        idx_margen = row.index.get_loc('MARGEN %')
        color_letra = 'color: #ff4b4b;' if val < 0 else 'color: white;'
        
        if val <= 6.0:
            bg = 'background-color: #551a1a;' # Rojo tenue
        elif 6.1 <= val <= 8.0:
            bg = 'background-color: #5e541e;' # Amarillo tenue
        else:
            bg = 'background-color: #1a4d1a;' # Verde tenue
        
        estilos[idx_margen] = f'{color_letra} {bg}'
        
    return estilos

if 'auth' not in st.session_state: st.session_state.auth = False

if not st.session_state.auth:
    st.title("🔐 Acceso - CalcuAMZ")
    u = st.text_input("Usuario").lower().strip()
    p = st.text_input("Clave", type="password")
    if st.button("Ingresar"):
        if u in USUARIOS and USUARIOS[u] == p:
            st.session_state.auth = True; st.session_state.user = u; st.rerun()
        else: st.error("Error")
else:
    try:
        ws = conectar(); df_raw = pd.DataFrame(ws.get_all_records())
        if not df_raw.empty: df_raw.columns = [str(c).strip().upper() for c in df_raw.columns]
    except: st.error("Error conexión"); st.stop()

    with st.sidebar:
        st.header("💵 Dólar Hoy")
        dolar_actual = st.number_input("Tipo de Cambio para NUEVAS cargas", value=18.00, step=0.01)

    st.title("📦 Gestión v2.3.2 (Amazon Edition)")
    t1, t2, t3 = st.tabs(["➕ Individual", "✏️ Editar / Borrar", "📂 Carga Masiva"])

    with t1:
        with st.form("nuevo"):
            sk = st.text_input("SKU").strip().upper()
            no = st.text_input("Nombre")
            c1, c2 = st.columns(2)
            cos = c1.number_input("Costo USD", format="%.2f")
            fee = c2.number_input("% Fee", value=10.0)
            env = c1.number_input("Envío FBA", value=0.0)
            pr = c2.number_input("Precio Venta", value=float(calcular_precio_sugerido(cos, fee, env, dolar_actual)))
            if st.form_submit_button("Guardar"):
                ws.append_row([sk if sk else f"A-{len(df_raw)+1}", no.upper(), cos, pr, env, fee, dolar_actual])
                st.rerun()

    with t2:
        if not df_raw.empty:
            sel = st.selectbox("Editar", df_raw['SKU'].astype(str) + " - " + df_raw['PRODUCTO'])
            idx = df_raw[df_raw['SKU'].astype(str) == sel.split(" - ")[0]].index[0]
            curr = df_raw.iloc[idx]
            with st.form("edit"):
                enom = st.text_input("Nombre", value=str(curr['PRODUCTO']))
                ecos = st.number_input("Costo USD", value=float(curr['COSTO USD']))
                epre = st.number_input("Precio MXN", value=float(curr['AMAZON']))
                etc = st.number_input("Dólar de esta compra", value=float(curr.get('TIPO CAMBIO', 18.0)))
                if st.form_submit_button("Actualizar"):
                    ws.update(range_name=f'A{idx+2}:G{idx+2}', values=[[curr['SKU'], enom.upper(), ecos, epre, curr['ENVIO'], curr['% FEE'], etc]])
                    st.rerun()
            if st.session_state.user in ["admin", "dav"] and st.button("🗑️ Eliminar"):
                ws.delete_rows(int(idx + 2)); st.rerun()

    with t3:
        st.subheader("Subida Masiva")
        arc = st.file_uploader("Archivo", type=['xlsx', 'csv'])
        if arc:
            df_b = pd.read_excel(arc) if arc.name.endswith('xlsx') else pd.read_csv(arc)
            df_b.columns = [str(c).strip().upper() for c in df_b.columns]
            df_b['AMAZON'] = df_b.apply(lambda r: calcular_precio_sugerido(r['COSTO USD'], r.get('% FEE', 10), r.get('ENVIO', 0), dolar_actual), axis=1)
            if st.button("🚀 Subir todo"):
                filas = [[str(f['SKU']), f['PRODUCTO'].upper(), f['COSTO USD'], f['AMAZON'], f.get('ENVIO', 0), f.get('% FEE', 10), dolar_actual] for _, f in df_b.iterrows()]
                ws.append_rows(filas); st.rerun()

    st.divider()
    if not df_raw.empty:
        bus = st.text_input("🔍 Buscar").strip().upper()
        res = df_raw.apply(calcular_detallado, axis=1)
        res.columns = ['COSTO MXN', 'FEE $', 'RET IVA', 'RET ISR', 'NETO RECIBIDO', 'UTILIDAD', 'MARGEN %']
        df_f = pd.concat([df_raw, res], axis=1)
        
        orden_cols = ['SKU', 'PRODUCTO', 'COSTO USD', 'TIPO CAMBIO', 'COSTO MXN', 'AMAZON', 'ENVIO', '% FEE', 'FEE $', 'RET IVA', 'RET ISR', 'NETO RECIBIDO', 'UTILIDAD', 'MARGEN %']
        df_f = df_f[[c for c in orden_cols if c in df_f.columns]]
        
        if bus: df_f = df_f[df_f['SKU'].astype(str).str.contains(bus) | df_f['PRODUCTO'].astype(str).str.contains(bus)]
        
        moneda = ['COSTO USD', 'TIPO CAMBIO', 'COSTO MXN', 'AMAZON', 'ENVIO', 'FEE $', 'RET IVA', 'RET ISR', 'NETO RECIBIDO', 'UTILIDAD']
        formato = {c: "${:,.2f}" for c in moneda}
        formato.update({'MARGEN %': "{:.2f}%", '% FEE': "{:.2f}%"})
        
        st.dataframe(
            df_f.style.format(formato, na_rep="-").apply(estilo_filas, axis=1), 
            use_container_width=True, height=600, hide_index=True
        )
