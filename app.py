import streamlit as st
import pandas as pd

# --- 1. CONFIGURACIÓN DE SEGURIDAD ---
USUARIOS_VALIDOS = {"admin": "amazon123", "socio": "ventas2026"}

# --- 2. LÓGICA DE CÁLCULO ---
TIPO_CAMBIO = 18.00

def calcular_valores(costo_usd, precio_amz, pct_fee, envio):
    costo_mxn = costo_usd * TIPO_CAMBIO
    
    # Calculamos el Fee en dinero basado en el % seleccionado
    dinero_fee = precio_amz * (pct_fee / 100)
    
    # BASE GRAVABLE (Precio Final / 1.16)
    base_gravable = precio_amz / 1.16
    
    # Retenciones sobre la Base
    ret_iva = base_gravable * 0.08
    ret_isr = base_gravable * 0.025
    
    # QUEDAN (Lo que deposita Amazon)
    quedan = precio_amz - dinero_fee - abs(envio) - ret_iva - ret_isr
    
    utilidad = quedan - costo_mxn
    margen_retorno = (utilidad / quedan) * 100 if quedan > 0 else 0
    
    return costo_mxn, dinero_fee, base_gravable, ret_iva, ret_isr, quedan, utilidad, margen_retorno

# --- 3. INICIO DE SESIÓN ---
if 'autenticado' not in st.session_state:
    st.session_state.autenticado = False

if not st.session_state.autenticado:
    st.title("🔐 Sistema de Proveedores")
    usuario = st.text_input("Usuario")
    clave = st.text_input("Contraseña", type="password")
    if st.button("Ingresar"):
        if usuario in USUARIOS_VALIDOS and USUARIOS_VALIDOS[usuario] == clave:
            st.session_state.autenticado = True
            st.rerun()
        else:
            st.error("Error de acceso")
else:
    # --- 4. PANEL LATERAL (CONFIGURACIÓN GLOBAL) ---
    st.sidebar.title("⚙️ Configuración")
    # Aquí puedes cambiar el % de Fee para todos los cálculos
    fee_global = st.sidebar.slider("Porcentaje de Fee Amazon", 0.0, 20.0, 10.0, step=0.5)
    
    if st.sidebar.button("Cerrar Sesión"):
        st.session_state.autenticado = False
        st.rerun()

    st.title("📦 Panel de Productos")
    
    if 'datos' not in st.session_state:
        st.session_state.datos = pd.DataFrame([
            {"PRODUCTO": "ROKU EXPRESS HD", "COSTO USD": 14.88, "AMAZON": 579.0, "ENVIO": 57.32},
            {"PRODUCTO": "AIRPODS 1A GEN", "COSTO USD": 60.0, "AMAZON": 1699.0, "ENVIO": 80.0}
        ])

    # Formulario para agregar/editar
    with st.expander("➕ Agregar o Editar Producto"):
        col1, col2 = st.columns(2)
        with col1:
            nombre = st.text_input("Nombre")
            c_usd = st.number_input("Costo USD", min_value=0.0)
        with col2:
            p_amz = st.number_input("Precio Venta MXN", min_value=0.0)
            e_amz = st.number_input("Envío FBA MXN", min_value=0.0)
        
        if st.button("Guardar Producto"):
            nuevo = {"PRODUCTO": nombre.upper(), "COSTO USD": c_usd, "AMAZON": p_amz, "ENVIO": e_amz}
            st.session_state.datos = st.session_state.datos[st.session_state.datos.PRODUCTO != nombre.upper()]
            st.session_state.datos = pd.concat([st.session_state.datos, pd.DataFrame([nuevo])], ignore_index=True)
            st.success("Actualizado")

    # --- 5. TABLA FINAL CON FORMATO ---
    st.subheader(f"📊 Análisis con Fee del {fee_global}%")
    
    df = st.session_state.datos.copy()
    # Aplicar la función usando el fee_global de la barra lateral
    res = df.apply(lambda r: calcular_valores(r['COSTO USD'], r['AMAZON'], fee_global, r['ENVIO']), axis=1)
    
    cols_res = ['COSTO MXN', 'FEE AMZ', 'BASE GRAV', 'RET IVA', 'RET ISR', 'QUEDAN', 'UTILIDAD', 'MARGEN %']
    df[cols_res] = pd.DataFrame(res.tolist(), index=df.index)

    # Formato profesional
    moneda = ['COSTO USD', 'AMAZON', 'ENVIO', 'COSTO MXN', 'FEE AMZ', 'BASE GRAV', 'RET IVA', 'RET ISR', 'QUEDAN', 'UTILIDAD']
    estilo = {col: "${:,.2f}" for col in moneda}
    estilo["MARGEN %"] = "{:.2f}%"

    st.dataframe(df.style.format(estilo))
