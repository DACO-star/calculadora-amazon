import streamlit as st
import pandas as pd

# --- 1. CONFIGURACIÓN DE SEGURIDAD ---
USUARIOS_VALIDOS = {"admin": "amazon123", "socio": "ventas2026"}

# --- 2. LÓGICA DE CÁLCULO ---
TIPO_CAMBIO = 18.00

def calcular_valores(costo_usd, precio_amz, pct_fee, envio):
    costo_mxn = costo_usd * TIPO_CAMBIO
    dinero_fee = precio_amz * (pct_fee / 100)
    base_gravable = precio_amz / 1.16
    ret_iva = base_gravable * 0.08
    ret_isr = base_gravable * 0.025
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
    st.sidebar.title("Menú")
    if st.sidebar.button("Cerrar Sesión"):
        st.session_state.autenticado = False
        st.rerun()

    st.title("📦 Gestión de Inventario Amazon")
    
    # DATOS INICIALES CON SKU
    if 'datos' not in st.session_state or 'SKU' not in st.session_state.datos.columns:
        st.session_state.datos = pd.DataFrame([
            {"SKU": "ROKU-001", "PRODUCTO": "ROKU EXPRESS HD", "COSTO USD": 14.88, "AMAZON": 579.0, "ENVIO": 57.32, "% FEE": 10.0},
            {"SKU": "AIRP-001", "PRODUCTO": "AIRPODS 1A GEN", "COSTO USD": 60.0, "AMAZON": 1699.0, "ENVIO": 80.0, "% FEE": 10.0}
        ])

    # --- 4. ÁREA DE GESTIÓN (TABS) ---
    tab1, tab2 = st.tabs(["➕ Agregar Nuevo", "✏️ Editar Producto"])

    with tab1:
        st.subheader("Registrar nuevo producto")
        with st.form("form_nuevo"):
            c1, c2 = st.columns(2)
            sku_n = c1.text_input("SKU (Único)")
            nombre_n = c2.text_input("Nombre del Producto")
            costo_n = c1.number_input("Costo USD", min_value=0.0)
            precio_n = c2.number_input("Precio Amazon MXN", min_value=0.0)
            fee_n = c1.number_input("% Fee Amazon", value=10.0)
            envio_n = c2.number_input("Envío FBA MXN", min_value=0.0)
            
            if st.form_submit_button("Añadir a Inventario"):
                if sku_n and nombre_n:
                    nuevo = {"SKU": sku_n.upper(), "PRODUCTO": nombre_n.upper(), "COSTO USD": costo_n, "AMAZON": precio_n, "ENVIO": envio_n, "% FEE": fee_n}
                    st.session_state.datos = pd.concat([st.session_state.datos, pd.DataFrame([nuevo])], ignore_index=True)
                    st.success("Producto agregado")
                    st.rerun()
                else:
                    st.error("SKU y Nombre son obligatorios")

    with tab2:
        st.subheader("Actualizar información existente")
        opciones = st.session_state.datos['SKU'] + " - " + st.session_state.datos['PRODUCTO']
        seleccion = st.selectbox("Selecciona el producto a editar", opciones)
        
        if seleccion:
            sku_sel = seleccion.split(" - ")[0]
            datos_prod = st.session_state.datos[st.session_state.datos['SKU'] == sku_sel].iloc[0]
            
            with st.form("form_editar"):
                c1, c2 = st.columns(2)
                nuevo_nombre = c1.text_input("Editar Nombre", value=datos_prod['PRODUCTO'])
                nuevo_costo = c2.number_input("Editar Costo USD", value=float(datos_prod['COSTO USD']))
                nuevo_precio = c1.number_input("Editar Precio Amazon", value=float(datos_prod['AMAZON']))
                nuevo_fee = c2.number_input("Editar % Fee", value=float(datos_prod['% FEE']))
                nuevo_envio = c1.number_input("Editar Envío FBA", value=float(datos_prod['ENVIO']))
                
                if st.form_submit_button("Guardar Cambios"):
                    idx = st.session_state.datos[st.session_state.datos['SKU'] == sku_sel].index
                    st.session_state.datos.loc[idx, ['PRODUCTO', 'COSTO USD', 'AMAZON', '% FEE', 'ENVIO']] = [
                        nuevo_nombre.upper(), nuevo_costo, nuevo_precio, nuevo_fee, nuevo_envio
                    ]
                    st.success("Cambios guardados")
                    st.rerun()

    # --- 5. TABLA DE RESULTADOS ---
    st.divider()
    st.subheader("📊 Análisis de Rentabilidad")
    
    df = st.session_state.datos.copy()
    res = df.apply(lambda r: calcular_valores(r['COSTO USD'], r['AMAZON'], r['% FEE'], r['ENVIO']), axis=1)
    
    cols_res = ['COSTO MXN', 'DINERO FEE', 'BASE GRAV', 'RET IVA', 'RET ISR', 'QUEDAN', 'UTILIDAD', 'MARGEN %']
    df[cols_res] = pd.DataFrame(res.tolist(), index=df.index)

    # Formato
    moneda = ['COSTO USD', 'AMAZON', 'ENVIO', 'COSTO MXN', 'DINERO FEE', 'BASE GRAV', 'RET IVA', 'RET ISR', 'QUEDAN', 'UTILIDAD']
    estilo = {col: "${:,.2f}" for col in moneda}
    estilo["MARGEN %"] = "{:.2f}%"
    estilo["% FEE"] = "{:.1f}%"

    st.dataframe(df.style.format(estilo), use_container_width=True)
