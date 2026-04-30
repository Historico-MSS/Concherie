import streamlit as st
import sqlite3
import qrcode
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
from pathlib import Path
from datetime import datetime
import pandas as pd

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

    conn.commit()
    conn.close()


def obtener_productos():
    conn = conectar_db()
    df = pd.read_sql_query(
        "SELECT * FROM productos ORDER BY fecha_creacion DESC",
        conn
    )
    conn.close()
    return df


def generar_codigo(marca_codigo, tipo_codigo, modelo, talla):
    """
    Genera código tipo:
    MRK-TP-01-T46-#01
    """
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
            codigo,
            marca_codigo,
            marca_nombre,
            tipo_codigo,
            tipo_nombre,
            modelo,
            talla,
            numero_pieza,
            descripcion,
            color,
            coleccion,
            precio,
            estado,
            foto_path,
            fecha_creacion,
            fecha_actualizacion
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            data["codigo"],
            data["marca_codigo"],
            data["marca_nombre"],
            data["tipo_codigo"],
            data["tipo_nombre"],
            data["modelo"],
            data["talla"],
            data["numero_pieza"],
            data["descripcion"],
            data["color"],
            data["coleccion"],
            data["precio"],
            data["estado"],
            data["foto_path"],
            data["fecha_creacion"],
            data["fecha_actualizacion"]
        )
    )

    conn.commit()
    conn.close()


# ======================================================
# QR
# ======================================================

def generar_qr(codigo):
    qr = qrcode.make(codigo)
    buffer = BytesIO()
    qr.save(buffer, format="PNG")
    return buffer.getvalue()


def generar_etiqueta_qr(codigo):
    """
    Genera una etiqueta PNG con QR + código legible debajo.
    """
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=2,
    )
    qr.add_data(codigo)
    qr.make(fit=True)

    qr_img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    qr_img = qr_img.resize((320, 320))

    etiqueta_ancho = 420
    etiqueta_alto = 420
    etiqueta = Image.new("RGB", (etiqueta_ancho, etiqueta_alto), "white")

    x_qr = (etiqueta_ancho - qr_img.width) // 2
    etiqueta.paste(qr_img, (x_qr, 20))

    draw = ImageDraw.Draw(etiqueta)

    try:
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", 40)
    except Exception:
        font = ImageFont.load_default()

    bbox = draw.textbbox((0, 0), codigo, font=font)
    text_width = bbox[2] - bbox[0]
    x_text = (etiqueta_ancho - text_width) // 2
    draw.text((x_text, 352), codigo, fill="black", font=font)

    buffer = BytesIO()
    etiqueta.save(buffer, format="PNG")
    return buffer.getvalue()


# ======================================================
# INICIO APP
# ======================================================

inicializar_db()
login()
logout_button()

st.title("Control de Tienda")
st.caption("Versión inicial: creación de productos, foto, código automático, inventario por modelo y QR.")

menu = st.sidebar.radio(
    "Menú",
    [
        "Nuevo producto",
        "Inventario",
        "Buscar producto"
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
            marca_codigo = st.selectbox(
                "Marca",
                options=list(MARCAS.keys()),
                format_func=lambda x: f"{x} - {MARCAS[x]}"
            )

        with col2:
            tipo_codigo = st.selectbox(
                "Tipo",
                options=list(TIPOS.keys()),
                format_func=lambda x: f"{x} - {TIPOS[x]}"
            )

        with col3:
            modelo_num = st.number_input(
                "Modelo",
                min_value=1,
                max_value=99,
                value=1,
                step=1,
                help="Número del modelo dentro de esa marca y tipo. Ejemplo: 01, 02, 03."
            )

        col4, col5, col6 = st.columns(3)

        with col4:
            talla = st.text_input(
                "Talla",
                placeholder="Ej: 46, M, S, Única"
            ).strip().upper()

        with col5:
            color = st.text_input(
                "Color",
                placeholder="Ej: negro, blanco, azul"
            ).strip()

        with col6:
            coleccion = st.selectbox("Colección", COLECCIONES)

        descripcion = st.text_area(
            "Descripción corta",
            placeholder="Ej: Top negro con mangas, vestido largo estampado, pantalón blanco..."
        ).strip()

        precio_texto = st.text_input(
            "Precio de venta (opcional por ahora)",
            placeholder="Ej: 350"
        ).strip()

        foto = st.file_uploader(
            "Foto del producto",
            type=["jpg", "jpeg", "png"]
        )

        submitted = st.form_submit_button("Crear producto")

        if submitted:
            if not talla:
                st.error("Debes indicar la talla. Si no aplica, usa 'Única'.")
            else:
                modelo = f"{int(modelo_num):02d}"
                codigo, numero_pieza = generar_codigo(
                    marca_codigo=marca_codigo,
                    tipo_codigo=tipo_codigo,
                    modelo=modelo,
                    talla=talla
                )

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
                st.success(f"Producto creado correctamente: {codigo}")
                st.info("Este será el código que aparecerá debajo del QR.")

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

        agrupado = df.groupby("modelo_codigo").agg({
            "descripcion": "first",
            "color": "first",
            "coleccion": "first",
            "codigo": "count"
        }).reset_index()

        agrupado = agrupado.rename(columns={
            "codigo": "total_piezas"
        })

        st.subheader("Vista general")
        st.dataframe(
            agrupado,
            use_container_width=True,
            hide_index=True
        )

        st.markdown("---")
        st.subheader("Ver detalle por modelo")

        modelo_seleccionado = st.selectbox(
            "Selecciona un modelo",
            agrupado["modelo_codigo"].tolist()
        )

        df_modelo = df[df["modelo_codigo"] == modelo_seleccionado]

        st.write(f"Piezas del modelo {modelo_seleccionado}:")

        columnas_detalle = [
            "codigo",
            "talla",
            "estado",
            "precio",
            "fecha_creacion"
        ]

        st.dataframe(
            df_modelo[columnas_detalle],
            use_container_width=True,
            hide_index=True
        )

        st.download_button(
            "Descargar inventario completo en CSV",
            data=df.to_csv(index=False).encode("utf-8"),
            file_name="inventario_tienda.csv",
            mime="text/csv"
        )

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
            marca_filtro = st.selectbox(
                "Filtrar por marca",
                options=["Todas"] + list(MARCAS.keys()),
                format_func=lambda x: "Todas" if x == "Todas" else f"{x} - {MARCAS[x]}"
            )

        with col_filtro2:
            busqueda = st.text_input(
            "Buscar por código, marca, tipo, descripción, color o talla",
            placeholder="Ej: MRK, TP, negro, T46, vestido..."
        ).strip().lower()

        df_filtrado = df.copy()

        if marca_filtro != "Todas":
            df_filtrado = df_filtrado[df_filtrado["marca_codigo"] == marca_filtro]

        if busqueda:
            df_filtrado = df_filtrado[
                df_filtrado.apply(
                    lambda row: busqueda in " ".join([
                        str(row.get("codigo", "")),
                        str(row.get("marca_codigo", "")),
                        str(row.get("marca_nombre", "")),
                        str(row.get("tipo_codigo", "")),
                        str(row.get("tipo_nombre", "")),
                        str(row.get("descripcion", "")),
                        str(row.get("color", "")),
                        str(row.get("talla", "")),
                        str(row.get("estado", ""))
                    ]).lower(),
                    axis=1
                )
            ]
        
        st.write(f"Resultados: {len(df_filtrado)}")

        for _, row in df_filtrado.iterrows():
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
                    st.image(etiqueta_img, caption="Etiqueta QR", width=180)

                    st.download_button(
                        label="Descargar etiqueta",
                        data=etiqueta_img,
                        file_name=f"etiqueta_{row['codigo']}.png",
                        mime="image/png",
                        key=f"download_label_{row['id']}"
                    )
