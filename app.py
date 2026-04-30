import streamlit as st
import sqlite3
import qrcode
from io import BytesIO
from pathlib import Path
from datetime import datetime, date
import pandas as pd
from PIL import Image, ImageDraw, ImageFont
import cv2
import numpy as np

# ======================================================
# CONFIGURACIÓN GENERAL
# ======================================================

st.set_page_config(
    page_title="Control de Tienda",
    page_icon="🛍️",
    layout="wide"
)

DB_PATH = "tienda.db"
UPLOAD_DIR = Path("fotos_productos")
UPLOAD_DIR.mkdir(exist_ok=True)

MARCAS = {
    "MRK": "Maison Rabih Kayrouz",
    "DCK": "Dice Kayek",
    "ITA": "Marca italiana por definir"
}

TIPOS = {
    "TP": "Top",
    "BT": "Bottom",
    "FL": "Full / Vestido",
    "AC": "Accesorio"
}

ESTADOS = [
    "Disponible",
    "Reservado",
    "Con clienta",
    "Vendido",
    "Inactivo"
]

COLECCIONES = [
    "Nueva colección",
    "Temporada pasada",
    "Sale / Liquidación",
    "Por definir"
]

FORMAS_PAGO = [
    "Efectivo",
    "Zelle",
    "Transferencia",
    "Pago móvil",
    "Tarjeta",
    "Otro",
    "Pendiente"
]

USERS = {
    "concha": "patrona",
    "moira": "asistonta",
    "jc": "master"
}

# ======================================================
# LOGIN
# ======================================================

def login():
    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False

    if not st.session_state.logged_in:
        st.title("Acceso a Control de Tienda")
        st.write("Ingresa tu usuario y clave para continuar.")

        user = st.text_input("Usuario").strip().lower()
        password = st.text_input("Clave", type="password")

        if st.button("Entrar"):
            if user in USERS and USERS[user] == password:
                st.session_state.logged_in = True
                st.session_state.user = user
                st.rerun()
            else:
                st.error("Usuario o clave incorrecta")

        st.stop()


def logout_button():
    with st.sidebar:
        st.caption(f"Usuario: {st.session_state.get('user', '')}")
        if st.button("Cerrar sesión"):
            st.session_state.logged_in = False
            st.session_state.user = None
            st.rerun()

# ======================================================
# BASE DE DATOS
# ======================================================

def conectar_db():
    return sqlite3.connect(DB_PATH, check_same_thread=False)


def inicializar_db():
    conn = conectar_db()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS productos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo TEXT UNIQUE NOT NULL,
            marca_codigo TEXT NOT NULL,
            marca_nombre TEXT NOT NULL,
            tipo_codigo TEXT NOT NULL,
            tipo_nombre TEXT NOT NULL,
            modelo TEXT NOT NULL,
            talla TEXT NOT NULL,
            numero_pieza TEXT NOT NULL,
            descripcion TEXT,
            color TEXT,
            coleccion TEXT,
            precio REAL,
            estado TEXT NOT NULL,
            foto_path TEXT,
            fecha_creacion TEXT NOT NULL,
            fecha_actualizacion TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS movimientos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            producto_codigo TEXT NOT NULL,
            tipo_movimiento TEXT NOT NULL,
            cliente TEXT,
            telefono TEXT,
            precio REAL,
            monto_pagado REAL,
            forma_pago TEXT,
            estado_pago TEXT,
            estado_entrega TEXT,
            observacion TEXT,
            usuario TEXT,
            fecha TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()


def obtener_productos():
    conn = conectar_db()
    df = pd.read_sql_query("SELECT * FROM productos ORDER BY fecha_creacion DESC", conn)
    conn.close()
    return df


def obtener_movimientos():
    conn = conectar_db()
    df = pd.read_sql_query("SELECT * FROM movimientos ORDER BY fecha DESC", conn)
    conn.close()
    return df


def generar_codigo(marca_codigo, tipo_codigo, modelo, talla):
    conn = conectar_db()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT codigo FROM productos
        WHERE marca_codigo = ?
        AND tipo_codigo = ?
        AND modelo = ?
        AND talla = ?
        ORDER BY codigo ASC
        """,
        (marca_codigo, tipo_codigo, modelo, talla)
    )

    existentes = cursor.fetchall()
    conn.close()

    siguiente_numero = len(existentes) + 1
    numero_pieza = f"{siguiente_numero:02d}"
    codigo = f"{marca_codigo}-{tipo_codigo}-{modelo}-T{talla}-#{numero_pieza}"

    return codigo, numero_pieza


def guardar_producto(data):
    conn = conectar_db()
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO productos (
            codigo, marca_codigo, marca_nombre, tipo_codigo, tipo_nombre,
            modelo, talla, numero_pieza, descripcion, color, coleccion,
            precio, estado, foto_path, fecha_creacion, fecha_actualizacion
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            data["codigo"], data["marca_codigo"], data["marca_nombre"],
            data["tipo_codigo"], data["tipo_nombre"], data["modelo"],
            data["talla"], data["numero_pieza"], data["descripcion"],
            data["color"], data["coleccion"], data["precio"], data["estado"],
            data["foto_path"], data["fecha_creacion"], data["fecha_actualizacion"]
        )
    )

    conn.commit()
    conn.close()


def actualizar_estado_producto(codigo, nuevo_estado):
    conn = conectar_db()
    cursor = conn.cursor()
    ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute(
        "UPDATE productos SET estado = ?, fecha_actualizacion = ? WHERE codigo = ?",
        (nuevo_estado, ahora, codigo)
    )
    conn.commit()
    conn.close()


def registrar_movimiento(
    producto_codigo,
    tipo_movimiento,
    cliente=None,
    telefono=None,
    precio=None,
    monto_pagado=None,
    forma_pago=None,
    estado_pago=None,
    estado_entrega=None,
    observacion=None
):
    conn = conectar_db()
    cursor = conn.cursor()
    ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    usuario = st.session_state.get("user", "")

    cursor.execute(
        """
        INSERT INTO movimientos (
            producto_codigo, tipo_movimiento, cliente, telefono, precio,
            monto_pagado, forma_pago, estado_pago, estado_entrega,
            observacion, usuario, fecha
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            producto_codigo, tipo_movimiento, cliente, telefono, precio,
            monto_pagado, forma_pago, estado_pago, estado_entrega,
            observacion, usuario, ahora
        )
    )

    conn.commit()
    conn.close()

# ======================================================
# QR / ETIQUETA
# ======================================================

def generar_qr(codigo):
    qr = qrcode.make(codigo)
    buffer = BytesIO()
    qr.save(buffer, format="PNG")
    return buffer.getvalue()


def cargar_fuente_bold(size):
    rutas = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "DejaVuSans-Bold.ttf"
    ]
    for ruta in rutas:
        try:
            return ImageFont.truetype(ruta, size)
        except Exception:
            pass
    return ImageFont.load_default()


def dividir_codigo_etiqueta(codigo):
    partes = codigo.split("-")
    if len(partes) >= 5:
        linea_1 = "-".join(partes[:3])
        talla = partes[3].replace("T", "", 1)
        pieza = partes[4]
        linea_2 = f"T{talla}  {pieza}" if talla.isdigit() else f"{talla}  {pieza}"
        return linea_1, linea_2
    return codigo, ""


def generar_etiqueta_qr(codigo):
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=2,
    )
    qr.add_data(codigo)
    qr.make(fit=True)

    qr_img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    qr_img = qr_img.resize((340, 340))

    etiqueta_ancho = 500
    etiqueta_alto = 520
    etiqueta = Image.new("RGB", (etiqueta_ancho, etiqueta_alto), "white")

    x_qr = (etiqueta_ancho - qr_img.width) // 2
    etiqueta.paste(qr_img, (x_qr, 20))

    draw = ImageDraw.Draw(etiqueta)
    font_1 = cargar_fuente_bold(42)
    font_2 = cargar_fuente_bold(48)

    linea_1, linea_2 = dividir_codigo_etiqueta(codigo)

    bbox1 = draw.textbbox((0, 0), linea_1, font=font_1)
    x_text_1 = (etiqueta_ancho - (bbox1[2] - bbox1[0])) // 2
    draw.text((x_text_1, 370), linea_1, fill="black", font=font_1)

    if linea_2:
        bbox2 = draw.textbbox((0, 0), linea_2, font=font_2)
        x_text_2 = (etiqueta_ancho - (bbox2[2] - bbox2[0])) // 2
        draw.text((x_text_2, 425), linea_2, fill="black", font=font_2)

    buffer = BytesIO()
    etiqueta.save(buffer, format="PNG")
    return buffer.getvalue()


def decodificar_qr_desde_imagen(uploaded_file):
    bytes_data = uploaded_file.getvalue()
    np_arr = np.frombuffer(bytes_data, np.uint8)
    img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

    detector = cv2.QRCodeDetector()
    data, bbox, _ = detector.detectAndDecode(img)

    if data:
        return data.strip()
    return None

# ======================================================
# COMPONENTES DE PRODUCTO
# ======================================================

def mostrar_ficha_producto(row, mostrar_acciones=True):
    with st.container(border=True):
        col_img, col_info, col_qr = st.columns([1, 3, 1])

        with col_img:
            if row["foto_path"] and Path(row["foto_path"]).exists():
                st.image(row["foto_path"], use_container_width=True)
            else:
                st.write("Sin foto")

        with col_info:
            st.subheader(row["codigo"])
            st.write(f"**Marca:** {row['marca_nombre']}")
            st.write(f"**Tipo:** {row['tipo_nombre']}")
            st.write(f"**Modelo:** {row['marca_codigo']}-{row['tipo_codigo']}-{row['modelo']}")
            st.write(f"**Talla:** {row['talla']}")
            st.write(f"**Color:** {row['color'] or 'No indicado'}")
            st.write(f"**Colección:** {row['coleccion']}")
            st.write(f"**Estado:** {row['estado']}")

            if pd.notna(row["precio"]):
                st.write(f"**Precio:** USD {row['precio']:,.2f}")
            else:
                st.write("**Precio:** pendiente")

            if row["descripcion"]:
                st.write(f"**Descripción:** {row['descripcion']}")

        with col_qr:
            etiqueta_img = generar_etiqueta_qr(row["codigo"])
            st.image(etiqueta_img, caption="Etiqueta QR", width=200)
            st.download_button(
                label="Descargar etiqueta",
                data=etiqueta_img,
                file_name=f"etiqueta_{row['codigo']}.png",
                mime="image/png",
                key=f"download_label_{row['id']}"
            )

        if mostrar_acciones:
            st.markdown("#### Acciones")
            tab1, tab2, tab3, tab4 = st.tabs([
                "Vender",
                "Clienta se la lleva",
                "Reservar",
                "Marcar devuelta"
            ])

            with tab1:
                formulario_venta(row)

            with tab2:
                formulario_con_clienta(row)

            with tab3:
                formulario_reserva(row)

            with tab4:
                formulario_devolucion(row)


def formulario_venta(row):
    if row["estado"] == "Vendido":
        st.warning("Esta pieza ya aparece como vendida.")
        return

    with st.form(f"venta_{row['id']}"):
        cliente = st.text_input("Cliente", key=f"venta_cliente_{row['id']}")
        telefono = st.text_input("Teléfono", key=f"venta_tel_{row['id']}")
        precio_default = float(row["precio"]) if pd.notna(row["precio"]) else 0.0
        precio = st.number_input("Precio de venta", min_value=0.0, value=precio_default, step=1.0, key=f"venta_precio_{row['id']}")
        monto_pagado = st.number_input("Monto pagado", min_value=0.0, value=precio_default, step=1.0, key=f"venta_pagado_{row['id']}")
        forma_pago = st.selectbox("Forma de pago", FORMAS_PAGO, key=f"venta_pago_{row['id']}")
        estado_pago = st.selectbox("Estado de pago", ["Pagado completo", "Pendiente", "Abonado"], key=f"venta_estado_pago_{row['id']}")
        estado_entrega = st.selectbox("Entrega", ["Entregado", "Pendiente de entrega"], key=f"venta_entrega_{row['id']}")
        observacion = st.text_area("Observación", key=f"venta_obs_{row['id']}")
        submitted = st.form_submit_button("Registrar venta")

        if submitted:
            actualizar_estado_producto(row["codigo"], "Vendido")
            registrar_movimiento(
                producto_codigo=row["codigo"],
                tipo_movimiento="Venta",
                cliente=cliente,
                telefono=telefono,
                precio=precio,
                monto_pagado=monto_pagado,
                forma_pago=forma_pago,
                estado_pago=estado_pago,
                estado_entrega=estado_entrega,
                observacion=observacion
            )
            st.success("Venta registrada correctamente.")
            st.rerun()


def formulario_con_clienta(row):
    if row["estado"] == "Vendido":
        st.warning("Esta pieza está vendida. No puede marcarse con clienta.")
        return

    with st.form(f"clienta_{row['id']}"):
        cliente = st.text_input("Nombre de la clienta", key=f"clienta_nombre_{row['id']}")
        telefono = st.text_input("Teléfono", key=f"clienta_tel_{row['id']}")
        observacion = st.text_area("Observación", key=f"clienta_obs_{row['id']}")
        submitted = st.form_submit_button("Registrar como con clienta")

        if submitted:
            actualizar_estado_producto(row["codigo"], "Con clienta")
            registrar_movimiento(
                producto_codigo=row["codigo"],
                tipo_movimiento="Con clienta",
                cliente=cliente,
                telefono=telefono,
                observacion=observacion
            )
            st.success("Pieza registrada como con clienta.")
            st.rerun()


def formulario_reserva(row):
    if row["estado"] == "Vendido":
        st.warning("Esta pieza está vendida. No puede reservarse.")
        return

    with st.form(f"reserva_{row['id']}"):
        cliente = st.text_input("Cliente", key=f"reserva_cliente_{row['id']}")
        telefono = st.text_input("Teléfono", key=f"reserva_tel_{row['id']}")
        observacion = st.text_area("Observación", key=f"reserva_obs_{row['id']}")
        submitted = st.form_submit_button("Registrar reserva")

        if submitted:
            actualizar_estado_producto(row["codigo"], "Reservado")
            registrar_movimiento(
                producto_codigo=row["codigo"],
                tipo_movimiento="Reserva",
                cliente=cliente,
                telefono=telefono,
                observacion=observacion
            )
            st.success("Reserva registrada correctamente.")
            st.rerun()


def formulario_devolucion(row):
    if row["estado"] not in ["Con clienta", "Reservado"]:
        st.info("Esta acción se usa principalmente para piezas con clienta o reservadas.")

    with st.form(f"devolucion_{row['id']}"):
        observacion = st.text_area("Observación", key=f"dev_obs_{row['id']}")
        submitted = st.form_submit_button("Marcar como disponible")

        if submitted:
            actualizar_estado_producto(row["codigo"], "Disponible")
            registrar_movimiento(
                producto_codigo=row["codigo"],
                tipo_movimiento="Devolución / Disponible",
                observacion=observacion
            )
            st.success("Pieza marcada como disponible.")
            st.rerun()

# ======================================================
# INICIO APP
# ======================================================

inicializar_db()
login()
logout_button()

st.title("Control de Tienda")
st.caption("Sistema interno para inventario, QR, ventas, reservas, piezas con clientas y reporte diario.")

menu = st.sidebar.radio(
    "Menú",
    [
        "Nuevo producto",
        "Inventario",
        "Buscar producto",
        "Escanear QR",
        "Piezas con clientas",
        "Reservas",
        "Ventas",
        "Reporte diario",
        "Historial"
    ]
)

# ======================================================
# NUEVO PRODUCTO
# ======================================================

if menu == "Nuevo producto":
    st.header("Nuevo producto")
    st.write("Carga una pieza nueva. El sistema generará el código automáticamente.")

    with st.form("form_nuevo_producto", clear_on_submit=True):
        col1, col2, col3 = st.columns(3)

        with col1:
            marca_codigo = st.selectbox("Marca", options=list(MARCAS.keys()), format_func=lambda x: f"{x} - {MARCAS[x]}")
        with col2:
            tipo_codigo = st.selectbox("Tipo", options=list(TIPOS.keys()), format_func=lambda x: f"{x} - {TIPOS[x]}")
        with col3:
            modelo_num = st.number_input("Modelo", min_value=1, max_value=99, value=1, step=1)

        col4, col5, col6 = st.columns(3)
        with col4:
            talla = st.text_input("Talla", placeholder="Ej: 46, M, S, Única").strip().upper()
        with col5:
            color = st.text_input("Color", placeholder="Ej: negro, blanco, azul").strip()
        with col6:
            coleccion = st.selectbox("Colección", COLECCIONES)

        descripcion = st.text_area("Descripción corta", placeholder="Ej: Top negro con mangas...").strip()
        precio_texto = st.text_input("Precio de venta (opcional por ahora)", placeholder="Ej: 350").strip()
        foto = st.file_uploader("Foto del producto", type=["jpg", "jpeg", "png"])

        submitted = st.form_submit_button("Crear producto")

        if submitted:
            if not talla:
                st.error("Debes indicar la talla. Si no aplica, usa 'Única'.")
            else:
                modelo = f"{int(modelo_num):02d}"
                codigo, numero_pieza = generar_codigo(marca_codigo, tipo_codigo, modelo, talla)

                foto_path = None
                if foto is not None:
                    extension = Path(foto.name).suffix.lower()
                    foto_path = str(UPLOAD_DIR / f"{codigo}{extension}")
                    with open(foto_path, "wb") as f:
                        f.write(foto.getbuffer())

                precio = None
                if precio_texto:
                    try:
                        precio = float(precio_texto.replace("$", "").replace(",", ""))
                    except ValueError:
                        st.error("El precio debe ser un número. Ejemplo: 350")
                        st.stop()

                ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                data = {
                    "codigo": codigo,
                    "marca_codigo": marca_codigo,
                    "marca_nombre": MARCAS[marca_codigo],
                    "tipo_codigo": tipo_codigo,
                    "tipo_nombre": TIPOS[tipo_codigo],
                    "modelo": modelo,
                    "talla": talla,
                    "numero_pieza": numero_pieza,
                    "descripcion": descripcion,
                    "color": color,
                    "coleccion": coleccion,
                    "precio": precio,
                    "estado": "Disponible",
                    "foto_path": foto_path,
                    "fecha_creacion": ahora,
                    "fecha_actualizacion": ahora
                }

                guardar_producto(data)
                registrar_movimiento(codigo, "Creación de producto", precio=precio, observacion="Producto creado")
                st.success(f"Producto creado correctamente: {codigo}")

# ======================================================
# INVENTARIO
# ======================================================

elif menu == "Inventario":
    st.header("Inventario por modelo")
    df = obtener_productos()

    if df.empty:
        st.warning("Todavía no hay productos cargados.")
    else:
        df["modelo_codigo"] = df["marca_codigo"] + "-" + df["tipo_codigo"] + "-" + df["modelo"]

        colf1, colf2 = st.columns(2)
        with colf1:
            marca_filtro = st.selectbox("Filtrar por marca", ["Todas"] + list(MARCAS.keys()), format_func=lambda x: "Todas" if x == "Todas" else f"{x} - {MARCAS[x]}")
        with colf2:
            estado_filtro = st.selectbox("Filtrar por estado", ["Todos"] + ESTADOS)

        df_vista = df.copy()
        if marca_filtro != "Todas":
            df_vista = df_vista[df_vista["marca_codigo"] == marca_filtro]
        if estado_filtro != "Todos":
            df_vista = df_vista[df_vista["estado"] == estado_filtro]

        agrupado = df_vista.groupby("modelo_codigo").agg({
            "descripcion": "first",
            "color": "first",
            "coleccion": "first",
            "codigo": "count"
        }).reset_index().rename(columns={"codigo": "total_piezas"})

        st.subheader("Vista general")
        st.dataframe(agrupado, use_container_width=True, hide_index=True)

        st.markdown("---")
        st.subheader("Ver detalle por modelo")

        if not agrupado.empty:
            modelo_seleccionado = st.selectbox("Selecciona un modelo", agrupado["modelo_codigo"].tolist())
            df_modelo = df_vista[df_vista["modelo_codigo"] == modelo_seleccionado]
            st.dataframe(df_modelo[["codigo", "talla", "estado", "precio", "fecha_creacion"]], use_container_width=True, hide_index=True)

        st.download_button("Descargar inventario completo en CSV", data=df.to_csv(index=False).encode("utf-8"), file_name="inventario_tienda.csv", mime="text/csv")

# ======================================================
# BUSCAR PRODUCTO
# ======================================================

elif menu == "Buscar producto":
    st.header("Buscar producto")
    df = obtener_productos()

    if df.empty:
        st.warning("Todavía no hay productos cargados.")
    else:
        col_filtro1, col_filtro2 = st.columns([1, 2])
        with col_filtro1:
            marca_filtro = st.selectbox("Filtrar por marca", ["Todas"] + list(MARCAS.keys()), format_func=lambda x: "Todas" if x == "Todas" else f"{x} - {MARCAS[x]}")
        with col_filtro2:
            busqueda = st.text_input("Buscar por código, marca, tipo, descripción, color o talla", placeholder="Ej: MRK, TP, negro, T46, vestido...").strip().lower()

        df_filtrado = df.copy()
        if marca_filtro != "Todas":
            df_filtrado = df_filtrado[df_filtrado["marca_codigo"] == marca_filtro]

        if busqueda:
            df_filtrado = df_filtrado[
                df_filtrado.apply(lambda row: busqueda in " ".join([
                    str(row.get("codigo", "")), str(row.get("marca_codigo", "")), str(row.get("marca_nombre", "")),
                    str(row.get("tipo_codigo", "")), str(row.get("tipo_nombre", "")), str(row.get("descripcion", "")),
                    str(row.get("color", "")), str(row.get("talla", "")), str(row.get("estado", ""))
                ]).lower(), axis=1)
            ]

        st.write(f"Resultados: {len(df_filtrado)}")
        for _, row in df_filtrado.iterrows():
            mostrar_ficha_producto(row)

# ======================================================
# ESCANEAR QR
# ======================================================

elif menu == "Escanear QR":
    st.header("Escanear QR")
    st.write("Desde el iPhone, toca el botón de cámara, toma la foto del QR y la app buscará el producto.")

    foto_qr = st.camera_input("Tomar foto del QR")

    if foto_qr is not None:
        codigo_leido = decodificar_qr_desde_imagen(foto_qr)

        if codigo_leido:
            st.success(f"QR leído: {codigo_leido}")
            df = obtener_productos()
            resultado = df[df["codigo"] == codigo_leido]

            if resultado.empty:
                st.warning("El código fue leído, pero no existe en el inventario.")
            else:
                mostrar_ficha_producto(resultado.iloc[0])
        else:
            st.error("No pude leer el QR. Intenta tomar la foto más de frente, con buena luz y sin sombra.")

# ======================================================
# PIEZAS CON CLIENTAS
# ======================================================

elif menu == "Piezas con clientas":
    st.header("Piezas con clientas")
    productos = obtener_productos()
    movimientos = obtener_movimientos()

    df = productos[productos["estado"] == "Con clienta"]

    if df.empty:
        st.success("No hay piezas registradas como con clienta.")
    else:
        for _, row in df.iterrows():
            ult = movimientos[(movimientos["producto_codigo"] == row["codigo"]) & (movimientos["tipo_movimiento"] == "Con clienta")]
            if not ult.empty:
                ultimo = ult.iloc[0]
                st.write(f"**Clienta:** {ultimo['cliente'] or 'No indicado'} | **Teléfono:** {ultimo['telefono'] or 'No indicado'} | **Fecha:** {ultimo['fecha']}")
            mostrar_ficha_producto(row)

# ======================================================
# RESERVAS
# ======================================================

elif menu == "Reservas":
    st.header("Reservas")
    productos = obtener_productos()
    movimientos = obtener_movimientos()

    df = productos[productos["estado"] == "Reservado"]

    if df.empty:
        st.success("No hay piezas reservadas.")
    else:
        for _, row in df.iterrows():
            ult = movimientos[(movimientos["producto_codigo"] == row["codigo"]) & (movimientos["tipo_movimiento"] == "Reserva")]
            if not ult.empty:
                ultimo = ult.iloc[0]
                st.write(f"**Cliente:** {ultimo['cliente'] or 'No indicado'} | **Teléfono:** {ultimo['telefono'] or 'No indicado'} | **Fecha:** {ultimo['fecha']}")
            mostrar_ficha_producto(row)

# ======================================================
# VENTAS
# ======================================================

elif menu == "Ventas":
    st.header("Ventas")
    movimientos = obtener_movimientos()
    ventas = movimientos[movimientos["tipo_movimiento"] == "Venta"]

    if ventas.empty:
        st.warning("Todavía no hay ventas registradas.")
    else:
        total_ventas = ventas["precio"].fillna(0).sum()
        total_pagado = ventas["monto_pagado"].fillna(0).sum()
        pendiente = total_ventas - total_pagado

        c1, c2, c3 = st.columns(3)
        c1.metric("Ventas registradas", f"USD {total_ventas:,.2f}")
        c2.metric("Pagado", f"USD {total_pagado:,.2f}")
        c3.metric("Pendiente", f"USD {pendiente:,.2f}")

        st.dataframe(ventas, use_container_width=True, hide_index=True)

# ======================================================
# REPORTE DIARIO
# ======================================================

elif menu == "Reporte diario":
    st.header("Reporte diario")
    fecha_reporte = st.date_input("Fecha del reporte", value=date.today())
    fecha_str = fecha_reporte.strftime("%Y-%m-%d")

    productos = obtener_productos()
    movimientos = obtener_movimientos()
    mov_dia = movimientos[movimientos["fecha"].str.startswith(fecha_str)] if not movimientos.empty else movimientos

    ventas_dia = mov_dia[mov_dia["tipo_movimiento"] == "Venta"] if not mov_dia.empty else mov_dia
    total_ventas = ventas_dia["precio"].fillna(0).sum() if not ventas_dia.empty else 0
    total_pagado = ventas_dia["monto_pagado"].fillna(0).sum() if not ventas_dia.empty else 0
    total_pendiente = total_ventas - total_pagado

    con_clienta = productos[productos["estado"] == "Con clienta"]
    reservas = productos[productos["estado"] == "Reservado"]
    disponibles = productos[productos["estado"] == "Disponible"]
    vendidas = productos[productos["estado"] == "Vendido"]

    st.subheader("Resumen")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Ventas del día", f"USD {total_ventas:,.2f}")
    c2.metric("Pagado", f"USD {total_pagado:,.2f}")
    c3.metric("Pendiente", f"USD {total_pendiente:,.2f}")
    c4.metric("Piezas vendidas hoy", len(ventas_dia))

    c5, c6, c7 = st.columns(3)
    c5.metric("Con clientas", len(con_clienta))
    c6.metric("Reservadas", len(reservas))
    c7.metric("Disponibles", len(disponibles))

    reporte_texto = f"""
REPORTE DIARIO - {fecha_str}

RESUMEN
Ventas del día: USD {total_ventas:,.2f}
Pagado: USD {total_pagado:,.2f}
Pendiente: USD {total_pendiente:,.2f}
Piezas vendidas hoy: {len(ventas_dia)}
Piezas con clientas: {len(con_clienta)}
Piezas reservadas: {len(reservas)}
Piezas disponibles: {len(disponibles)}
Piezas vendidas acumuladas: {len(vendidas)}

"""

    st.subheader("Ventas del día")
    if ventas_dia.empty:
        st.info("No hay ventas registradas en esta fecha.")
    else:
        st.dataframe(ventas_dia, use_container_width=True, hide_index=True)
        reporte_texto += "VENTAS DEL DÍA\n" + ventas_dia.to_string(index=False) + "\n\n"

    st.subheader("Piezas con clientas")
    if con_clienta.empty:
        st.info("No hay piezas con clientas.")
    else:
        st.dataframe(con_clienta[["codigo", "descripcion", "color", "talla", "precio", "estado"]], use_container_width=True, hide_index=True)
        reporte_texto += "PIEZAS CON CLIENTAS\n" + con_clienta[["codigo", "descripcion", "color", "talla", "precio", "estado"]].to_string(index=False) + "\n\n"

    st.subheader("Reservas")
    if reservas.empty:
        st.info("No hay reservas activas.")
    else:
        st.dataframe(reservas[["codigo", "descripcion", "color", "talla", "precio", "estado"]], use_container_width=True, hide_index=True)
        reporte_texto += "RESERVAS\n" + reservas[["codigo", "descripcion", "color", "talla", "precio", "estado"]].to_string(index=False) + "\n\n"

    st.download_button(
        "Descargar reporte del día en TXT",
        data=reporte_texto.encode("utf-8"),
        file_name=f"reporte_diario_{fecha_str}.txt",
        mime="text/plain"
    )

# ======================================================
# HISTORIAL
# ======================================================

elif menu == "Historial":
    st.header("Historial de movimientos")
    movimientos = obtener_movimientos()

    if movimientos.empty:
        st.warning("Todavía no hay movimientos registrados.")
    else:
        tipo_filtro = st.selectbox("Filtrar por tipo", ["Todos"] + sorted(movimientos["tipo_movimiento"].dropna().unique().tolist()))
        df_mov = movimientos.copy()
        if tipo_filtro != "Todos":
            df_mov = df_mov[df_mov["tipo_movimiento"] == tipo_filtro]

        st.dataframe(df_mov, use_container_width=True, hide_index=True)
        st.download_button("Descargar historial en CSV", data=movimientos.to_csv(index=False).encode("utf-8"), file_name="historial_movimientos.csv", mime="text/csv")
