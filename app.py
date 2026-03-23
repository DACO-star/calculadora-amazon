import streamlit as st
import pandas as pd

# --- 1. CONFIGURACIÓN DE SEGURIDAD (USUARIOS) ---
# En una app real, esto iría en una base de datos segura.
USUARIOS_VALIDOS = {"admin": "amazon123", "socio": "ventas2026"}

# --- 2. LÓGICA DE CÁLCULO (Tu fórmula exacta) ---
TIPO_CAMBIO = 18.00

def calcular_valores(costo_usd, precio_amz, fee, envio):
    costo_mxn = costo_usd * TIPO_CAMBIO
    base_gravable = precio_amz / 1.16
    ret_iva = base_gravable * 0.08
    ret_isr = base_gravable * 0.025
    quedan = precio_amz - abs(fee) - abs(envio) - ret_iva - ret_isr
    utilidad = quedan - costo_mxn
    margen_venta = (utilidad / precio_amz) * 100 if precio_amz != 0 else 0
    margen_retorno = (utilidad / quedan) * 100 if quedan != 0 else 0
    return costo_mxn, base_gravable, ret_iva, ret_isr, quedan, utilidad, margen_retorno

# --- 3. INICIO DE SESIÓN ---
if 'autenticado' not in st.session_state:
    st.session_state.autenticado = False

if not st.session_state.autenticado:
    st.title("🔐 Acceso al Sistema de Proveedores")
    usuario = st.text_input("Usuario")
    clave = st.text_input("Contraseña", type="password")
    if st.button("Ingresar"):
        if usuario in USUARIOS_VALIDOS and USUARIOS_VALIDOS[usuario] == clave:
            st.session_state.autenticado = True
            st.rerun()
        else:
            st.error("Usuario o contraseña incorrectos")
else:
    # --- 4. APLICACIÓN PRINCIPAL (Una vez logueado) ---
    st.sidebar.title(f"Bienvenido")
    if st.sidebar.button("Cerrar Sesión"):
        st.session_state.autenticado = False
        st.rerun()

    st.title("📦 Panel de Control de Productos Amazon")
    
    # Datos iniciales (Simulando una base de datos)
    if 'datos' not in st.session_state:
        st.session_state.datos = pd.DataFrame([
            {"PRODUCTO": "ROKU EXPRESS HD", "COSTO USD": 14.88, "AMAZON": 579.0, "FEE": 80.0, "ENVIO": 57.32},
            {"PRODUCTO": "AIRPODS 1A GEN", "COSTO USD": 60.0, "AMAZON": 1699.0, "FEE": 168.2, "ENVIO": 80.0}
        ])

    # Sección para actualizar precios
    st.subheader("🔄 Actualizar o Agregar Producto")
    with st.expander("Abrir formulario de edición"):
        nombre = st.text_input("Nombre del Producto")
        c_usd = st.number_input("Costo USD", min_value=0.0, step=0.1)
        p_amz = st.number_input("Precio Amazon MXN", min_value=0.0, step=1.0)
        f_amz = st.number_input("Fee Amazon", min_value=0.0, step=1.0)
        e_amz = st.number_input("Envío FBA", min_value=0.0, step=1.0)
        
        if st.button("Guardar / Actualizar"):
            nuevo_item = {"PRODUCTO": nombre.upper(), "COSTO USD": c_usd, "AMAZON": p_amz, "FEE": f_amz, "ENVIO": e_amz}
            # Si el producto ya existe, lo actualiza; si no, lo agrega
            st.session_state.datos = st.session_state.datos[st.session_state.datos.PRODUCTO != nombre.upper()]
            st.session_state.datos = pd.concat([st.session_state.datos, pd.DataFrame([nuevo_item])], ignore_index=True)
            st.success("¡Datos actualizados!")

    # --- 5. TABLA DE RESULTADOS EN TIEMPO REAL ---
    st.subheader("📊 Análisis de Rentabilidad")
    
    # Aplicamos los cálculos a la tabla
    df = st.session_state.datos.copy()
    resultados = df.apply(lambda r: calcular_valores(r['COSTO USD'], r['AMAZON'], r['FEE'], r['ENVIO']), axis=1)
    
    # Desglosamos los resultados en columnas
    res_cols = ['COSTO MXN', 'BASE GRAV', 'RET IVA', 'RET ISR', 'QUEDAN', 'UTILIDAD', 'MARGEN %']
    df[res_cols] = pd.DataFrame(resultados.tolist(), index=df.index)

    # Mostrar la tabla con formato bonito
    st.dataframe(df.style.format({
        "COSTO MXN": "${:,.2f}", "AMAZON": "${:,.2f}", "QUEDAN": "${:,.2f}", 
        "UTILIDAD": "${:,.2f}", "MARGEN %": "{:.2f}%"
    }))
