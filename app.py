import streamlit as st
import sqlite3
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

    La pieza #01, #02, etc. se calcula según misma marca, tipo, modelo y talla.
    """
    conn = conectar_db()
    cursor = conn.cursor()

    prefijo = f"{marca_codigo}-{tipo_codigo}-{modelo}-T{talla}-#"

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
    codigo = f"{prefijo}{numero_pieza}"

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
# INICIO APP
# ======================================================

inicializar_db()

st.title("Control de Tienda")
st.caption("Versión inicial: creación de productos, foto, código automático y listado general.")

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
                st.info("Este será el código que luego aparecerá debajo del QR.")

# ======================================================
# INVENTARIO
# ======================================================

elif menu == "Inventario":
    st.header("Inventario por modelo")

    df = obtener_productos()

    if df.empty:
        st.warning("Todavía no hay productos cargados.")
    else:
        # Crear código de modelo
        df["modelo_codigo"] = (
            df["marca_codigo"] + "-" + df["tipo_codigo"] + "-" + df["modelo"]
        )

        # Agrupar por modelo
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
        st.dataframe(agrupado, use_container_width=True, hide_index=True)

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
# QR GENERATION
# ======================================================

import qrcode
from io import BytesIO


def generar_qr(codigo):
    qr = qrcode.make(codigo)
    buffer = BytesIO()
    qr.save(buffer, format="PNG")
    return buffer.getvalue()

# ======================================================
# BUSCAR PRODUCTO
# ======================================================

elif menu == "Buscar producto":
    st.header("Buscar producto")

    df = obtener_productos()

    if df.empty:
        st.warning("Todavía no hay productos cargados.")
    else:
        busqueda = st.text_input(
            "Buscar por código, marca, tipo, descripción, color o talla",
            placeholder="Ej: MRK, TP, negro, T46, vestido..."
        ).strip().lower()

        if busqueda:
            df_filtrado = df[
                df.apply(
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
        else:
            df_filtrado = df

        st.write(f"Resultados: {len(df_filtrado)}")

        for _, row in df_filtrado.iterrows():
            with st.container(border=True):
                col_img, col_info = st.columns([1, 3])

                with col_img:
                    if row["foto_path"] and Path(row["foto_path"]).exists():
                        st.image(row["foto_path"], use_container_width=True)
                    else:
                        st.write("Sin foto")

                with col_info:
                    st.subheader(row["codigo"])

                    # Mostrar QR
                    qr_img = generar_qr(row["codigo"])
                    st.image(qr_img, caption="QR del producto", width=150)

                    st.download_button(
                        label="Descargar QR",
                        data=qr_img,
                        file_name=f"{row['codigo']}.png",
                        mime="image/png"
                    )
                    st.write(f"**Marca:** {row['marca_nombre']}")
                    st.write(f"**Tipo:** {row['tipo_nombre']}")
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
