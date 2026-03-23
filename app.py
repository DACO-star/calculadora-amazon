import streamlit as st
import pandas as pd

# --- 1. CONFIGURACIÓN DE SEGURIDAD ---
USUARIOS_VALIDOS = {"admin": "amazon123", "socio": "ventas2026"}

# --- 2. LÓGICA DE CÁLCULO ---
TIPO_CAMBIO = 18.00

def calcular_valores(costo_usd, precio_amz, pct_fee, envio):
    costo_mxn = costo_usd * TIPO_CAMBIO
    
    # El Fee se calcula usando el % específico de este producto
    dinero_fee = precio_amz * (pct_fee / 100)
    
    # BASE GRAVABLE (Precio Final / 1.16)
    base_gravable = precio_amz / 1.16
    
    # Retenciones sobre la Base (8% IVA y 2.5% ISR)
    ret_iva = base_gravable * 0.08
    ret_isr = base_gravable * 0.025
    
    # QUEDAN (Lo que deposita Amazon)
    quedan = precio_amz - dinero_fee - abs(envio) - ret_iva - ret_isr
    
    utilidad = quedan - costo_mxn
    
    # Margen sobre lo que queda (Tu fórmula)
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
    # --- 4. PANEL DE CONTROL ---
    st.sidebar.title("Menú")
    if st.sidebar.button("Cerrar Sesión"):
        st.session_state.autenticado = False
        st.rerun()

    st.title("📦 Panel de Productos Amazon")
    
    # Base de datos temporal con columna '% FEE'
    if 'datos' not in st.session_state:
        st.session_state.datos = pd.DataFrame([
            {"PRODUCTO": "ROKU EXPRESS HD", "COSTO USD": 14.88, "AMAZON": 579.0, "ENVIO": 57.32, "% FEE": 10.0},
            {"PRODUCTO": "AIRPODS 1A GEN", "COSTO USD": 60.0, "AMAZON": 1699.0, "ENVIO": 80.0, "% FEE": 10.0}
        ])

    # Formulario para agregar/editar
    with st.expander("➕ Agregar o Editar Producto"):
        col1, col2 = st.columns(2)
        with col1:
            nombre = st.text_input("Nombre del Producto")
            c_usd = st.number_input("Costo USD (Proveedor)", min_value=0.0)
            p_fee = st.number_input("% de Fee Amazon (ej. 10 o 15)", min_value=0.0, max_value=100.0, value=10.0)
        with col2:
            p_amz = st.number_input("Precio Venta Amazon MXN", min_value=0.0)
            e_amz = st.number_input("Envío FBA MXN", min_value=0.0)
        
        if st.button("Guardar en Lista"):
            if nombre:
                nuevo = {
                    "PRODUCTO": nombre.upper(), 
                    "COSTO USD": c_usd, 
                    "AMAZON": p_amz, 
                    "ENVIO": e_amz, 
                    "% FEE": p_fee
                }
                # Actualizar si ya existe o agregar nuevo
                st.session_state.datos = st.session_state.datos[st.session_state.datos.PRODUCTO != nombre.upper()]
                st.session_state.datos = pd.concat([st.session_state.datos, pd.DataFrame([nuevo])], ignore_index=True)
                st.success(f"✅ {nombre.upper()} guardado correctamente.")
            else:
                st.warning("Escribe el nombre del producto.")

    # --- 5. TABLA DE RESULTADOS ---
    st.subheader("📊 Análisis de Rentabilidad")
    
    df = st.session_state.datos.copy()
    
    # Aplicar cálculos usando el % FEE individual de cada fila
    res = df.apply(lambda r: calcular_valores(r['COSTO USD'], r['AMAZON'], r['% FEE'], r['ENVIO']), axis=1)
    
    cols_res = ['COSTO MXN', 'DINERO FEE', 'BASE GRAV', 'RET IVA', 'RET ISR', 'QUEDAN', 'UTILIDAD', 'MARGEN %']
    df[cols_res] = pd
