import streamlit as st
import sqlite3
import qrcode
from io import BytesIO
from pathlib import Path
from datetime import datetime, date
from zoneinfo import ZoneInfo
import pandas as pd
from PIL import Image, ImageDraw, ImageFont
import cv2
import numpy as np
import shutil
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage

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
    "NOVEDADES",
    "COLECCIÓN"
]

FORMAS_PAGO = [
    "Efectivo",
    "Transferencia",
    "Otro",
    "Pendiente"
]

USERS = {
    "concha": "patrona",
    "moira": "asistonta",
    "jc": "master",
    "info": "precios",
    "cliente": "2026"
}

CARACAS_TZ = ZoneInfo("America/Caracas")


def ahora_caracas():
    return datetime.now(CARACAS_TZ)


def ahora_caracas_str():
    return ahora_caracas().strftime("%Y-%m-%d %H:%M:%S")

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

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS clientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            telefono TEXT,
            notas TEXT,
            fecha_creacion TEXT NOT NULL,
            fecha_actualizacion TEXT NOT NULL,
            UNIQUE(nombre, telefono)
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


def obtener_clientes():
    conn = conectar_db()
    df = pd.read_sql_query("SELECT * FROM clientes ORDER BY nombre ASC", conn)
    conn.close()
    return df


def guardar_o_actualizar_cliente(nombre, telefono=None, notas=None):
    nombre = str(nombre or "").strip()
    telefono = str(telefono or "").strip()
    notas = str(notas or "").strip()

    if not nombre:
        return

    conn = conectar_db()
    cursor = conn.cursor()
    ahora = ahora_caracas_str()

    cursor.execute(
        "SELECT id, notas FROM clientes WHERE LOWER(nombre) = LOWER(?) AND IFNULL(telefono, '') = ?",
        (nombre, telefono)
    )
    existente = cursor.fetchone()

    if existente:
        cliente_id = existente[0]
        notas_actuales = existente[1] or ""
        notas_finales = notas_actuales

        if notas and notas not in notas_actuales:
            if notas_actuales:
                notas_finales = notas_actuales + " | " + notas
            else:
                notas_finales = notas

        cursor.execute(
            "UPDATE clientes SET notas = ?, fecha_actualizacion = ? WHERE id = ?",
            (notas_finales, ahora, cliente_id)
        )
    else:
        cursor.execute(
            """
            INSERT INTO clientes (nombre, telefono, notas, fecha_creacion, fecha_actualizacion)
            VALUES (?, ?, ?, ?, ?)
            """,
            (nombre, telefono, notas, ahora, ahora)
        )

    conn.commit()
    conn.close()


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
    ahora = ahora_caracas_str()
    cursor.execute(
        "UPDATE productos SET estado = ?, fecha_actualizacion = ? WHERE codigo = ?",
        (nuevo_estado, ahora, codigo)
    )
    conn.commit()
    conn.close()


def actualizar_producto_admin(codigo, descripcion, color, coleccion, precio, estado, foto_path=None):
    conn = conectar_db()
    cursor = conn.cursor()
    ahora = ahora_caracas_str()

    if foto_path:
        cursor.execute(
            """
            UPDATE productos
            SET descripcion = ?, color = ?, coleccion = ?, precio = ?, estado = ?, foto_path = ?, fecha_actualizacion = ?
            WHERE codigo = ?
            """,
            (descripcion, color, coleccion, precio, estado, foto_path, ahora, codigo)
        )
    else:
        cursor.execute(
            """
            UPDATE productos
            SET descripcion = ?, color = ?, coleccion = ?, precio = ?, estado = ?, fecha_actualizacion = ?
            WHERE codigo = ?
            """,
            (descripcion, color, coleccion, precio, estado, ahora, codigo)
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
    if cliente:
        guardar_o_actualizar_cliente(cliente, telefono)

    conn = conectar_db()
    cursor = conn.cursor()
    ahora = ahora_caracas_str()
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
# UTILIDADES DE FILTRO / REPORTES
# ======================================================

def filtrar_productos_avanzado(df, marca="Todas", tipo="Todos", talla="Todas", estado="Todos", coleccion="Todas", busqueda=""):
    df_filtrado = df.copy()

    if marca != "Todas":
        df_filtrado = df_filtrado[df_filtrado["marca_codigo"] == marca]
    if tipo != "Todos":
        df_filtrado = df_filtrado[df_filtrado["tipo_codigo"] == tipo]
    if talla != "Todas":
        df_filtrado = df_filtrado[df_filtrado["talla"].astype(str) == str(talla)]
    if estado != "Todos":
        df_filtrado = df_filtrado[df_filtrado["estado"] == estado]
    if coleccion != "Todas":
        df_filtrado = df_filtrado[df_filtrado["coleccion"] == coleccion]

    if busqueda:
        busqueda = busqueda.strip().lower()
        df_filtrado = df_filtrado[
            df_filtrado.apply(lambda row: busqueda in " ".join([
                str(row.get("codigo", "")),
                str(row.get("marca_codigo", "")),
                str(row.get("marca_nombre", "")),
                str(row.get("tipo_codigo", "")),
                str(row.get("tipo_nombre", "")),
                str(row.get("descripcion", "")),
                str(row.get("color", "")),
                str(row.get("talla", "")),
                str(row.get("estado", "")),
                str(row.get("coleccion", ""))
            ]).lower(), axis=1)
        ]

    return df_filtrado


def calcular_resumen_reporte(productos, movimientos, fecha_str):
    if movimientos.empty:
        mov_dia = movimientos
    else:
        mov_dia = movimientos[movimientos["fecha"].astype(str).str.startswith(fecha_str)]

    ventas_dia = mov_dia[mov_dia["tipo_movimiento"] == "Venta"] if not mov_dia.empty else mov_dia
    devoluciones_dia = mov_dia[mov_dia["tipo_movimiento"].isin(["Devolución / Disponible", "Devolución de venta"])] if not mov_dia.empty else mov_dia

    total_ventas_brutas = ventas_dia["precio"].fillna(0).sum() if not ventas_dia.empty else 0
    total_pagado_bruto = ventas_dia["monto_pagado"].fillna(0).sum() if not ventas_dia.empty else 0
    total_devoluciones = devoluciones_dia["precio"].fillna(0).sum() if not devoluciones_dia.empty else 0
    total_ventas_netas = total_ventas_brutas - total_devoluciones
    total_pendiente = total_ventas_netas - total_pagado_bruto

    con_clienta = productos[productos["estado"] == "Con clienta"] if not productos.empty else productos
    reservas = productos[productos["estado"] == "Reservado"] if not productos.empty else productos
    disponibles = productos[productos["estado"] == "Disponible"] if not productos.empty else productos
    vendidas = productos[productos["estado"] == "Vendido"] if not productos.empty else productos

    resumen = {
        "Ventas brutas del día": f"USD {total_ventas_brutas:,.2f}",
        "Devoluciones del día": f"USD {total_devoluciones:,.2f}",
        "Ventas netas del día": f"USD {total_ventas_netas:,.2f}",
        "Pagado registrado": f"USD {total_pagado_bruto:,.2f}",
        "Pendiente neto": f"USD {total_pendiente:,.2f}",
        "Piezas vendidas hoy": str(len(ventas_dia)),
        "Devoluciones hoy": str(len(devoluciones_dia)),
        "Piezas con clientas": str(len(con_clienta)),
        "Piezas reservadas": str(len(reservas)),
        "Piezas disponibles": str(len(disponibles)),
        "Piezas vendidas acumuladas": str(len(vendidas)),
    }

    return resumen, mov_dia, ventas_dia, devoluciones_dia, con_clienta, reservas, disponibles, vendidas

# ======================================================
# EXPORTACIONES PDF / EXCEL
# ======================================================

def dataframe_para_tabla(df, columnas):
    columnas_existentes = [c for c in columnas if c in df.columns]
    if df.empty or not columnas_existentes:
        return [["Sin registros"]]
    tabla = [columnas_existentes]
    for _, row in df[columnas_existentes].fillna("").iterrows():
        tabla.append([str(row[col]) for col in columnas_existentes])
    return tabla


def generar_pdf_reporte(fecha_str, tipo_reporte, resumen, ventas_dia, devoluciones_dia, con_clienta, reservas):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    styles = getSampleStyleSheet()
    story = []

    story.append(Paragraph(f"Reporte {tipo_reporte} - {fecha_str}", styles["Title"]))
    story.append(Paragraph(f"Generado: {ahora_caracas_str()}", styles["Normal"]))
    story.append(Spacer(1, 12))

    resumen_data = [["Concepto", "Valor"]] + [[k, v] for k, v in resumen.items()]
    tabla_resumen = Table(resumen_data, colWidths=[250, 200])
    tabla_resumen.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    story.append(tabla_resumen)
    story.append(Spacer(1, 18))

    secciones = [
        ("Ventas del día", ventas_dia, ["producto_codigo", "cliente", "telefono", "precio", "monto_pagado", "estado_pago", "estado_entrega", "fecha"]),
        ("Devoluciones del día", devoluciones_dia, ["producto_codigo", "cliente", "telefono", "precio", "observacion", "fecha"]),
        ("Piezas con clientas", con_clienta, ["codigo", "descripcion", "color", "talla", "precio", "estado"]),
        ("Reservas", reservas, ["codigo", "descripcion", "color", "talla", "precio", "estado"]),
    ]

    for titulo, df_sec, columnas in secciones:
        story.append(Paragraph(titulo, styles["Heading2"]))
        data = dataframe_para_tabla(df_sec, columnas)
        table = Table(data, repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
            ("GRID", (0, 0), (-1, -1), 0.35, colors.grey),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 7),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))
        story.append(table)
        story.append(Spacer(1, 16))

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()


def generar_excel_reporte(fecha_str, resumen, ventas_dia, devoluciones_dia, con_clienta, reservas, movimientos):
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        pd.DataFrame(list(resumen.items()), columns=["Concepto", "Valor"]).to_excel(writer, sheet_name="Resumen", index=False)
        ventas_dia.to_excel(writer, sheet_name="Ventas del dia", index=False)
        devoluciones_dia.to_excel(writer, sheet_name="Devoluciones", index=False)
        con_clienta.to_excel(writer, sheet_name="Con clientas", index=False)
        reservas.to_excel(writer, sheet_name="Reservas", index=False)
        movimientos.to_excel(writer, sheet_name="Historial", index=False)
    buffer.seek(0)
    return buffer.getvalue()


def generar_pdf_disponibles_con_fotos(productos):
    disponibles = productos[productos["estado"] == "Disponible"].copy() if not productos.empty else productos

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    styles = getSampleStyleSheet()
    story = []

    story.append(Paragraph("Catálogo de piezas disponibles", styles["Title"]))
    story.append(Paragraph(f"Generado: {ahora_caracas_str()}", styles["Normal"]))
    story.append(Spacer(1, 12))

    if disponibles.empty:
        story.append(Paragraph("No hay piezas disponibles.", styles["Normal"]))
    else:
        for _, row in disponibles.iterrows():
            datos = []
            datos.append(["Código", str(row["codigo"])])
            datos.append(["Marca", str(row["marca_nombre"])])
            datos.append(["Tipo", str(row["tipo_nombre"])])
            datos.append(["Talla", str(row["talla"])])
            datos.append(["Color", str(row["color"] or "")])
            datos.append(["Colección", str(row["coleccion"] or "")])
            precio_txt = f"USD {row['precio']:,.2f}" if pd.notna(row["precio"]) else "Pendiente"
            datos.append(["Precio", precio_txt])
            datos.append(["Estado", str(row["estado"])])
            if row["descripcion"]:
                datos.append(["Descripción", str(row["descripcion"])])

            tabla_datos = Table(datos, colWidths=[80, 260])
            tabla_datos.setStyle(TableStyle([
                ("GRID", (0, 0), (-1, -1), 0.35, colors.grey),
                ("BACKGROUND", (0, 0), (0, -1), colors.whitesmoke),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]))

            foto_elemento = Paragraph("Sin foto", styles["Normal"])
            if row["foto_path"] and Path(row["foto_path"]).exists():
                try:
                    foto_elemento = RLImage(row["foto_path"], width=110, height=110)
                except Exception:
                    foto_elemento = Paragraph("Foto no disponible", styles["Normal"])

            ficha = Table([[foto_elemento, tabla_datos]], colWidths=[130, 350])
            ficha.setStyle(TableStyle([
                ("BOX", (0, 0), (-1, -1), 0.5, colors.lightgrey),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]))
            story.append(ficha)
            story.append(Spacer(1, 10))

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()

# ======================================================
# COMPONENTES DE PRODUCTO
# ======================================================

def mostrar_estado_visual(estado):
    colores = {
        "Disponible": "#16a34a",
        "Reservado": "#ca8a04",
        "Con clienta": "#ea580c",
        "Vendido": "#dc2626",
        "Inactivo": "#6b7280"
    }
    color = colores.get(estado, "#6b7280")
    st.markdown(
        f"""
        <span style="
            background-color:{color};
            color:white;
            padding:4px 10px;
            border-radius:999px;
            font-size:13px;
            font-weight:700;
            display:inline-block;
            margin:2px 0 8px 0;
            letter-spacing:0.3px;
        ">
            {estado.upper()}
        </span>
        """,
        unsafe_allow_html=True
    )


def badge_estado_html(estado):
    colores = {
        "Disponible": "#16a34a",
        "Reservado": "#ca8a04",
        "Con clienta": "#ea580c",
        "Vendido": "#dc2626",
        "Inactivo": "#6b7280"
    }
    color = colores.get(estado, "#6b7280")
    return f"""
        <span style="
            background-color:{color};
            color:white;
            padding:3px 8px;
            border-radius:999px;
            font-size:12px;
            font-weight:700;
            white-space:nowrap;
        ">{estado.upper()}</span>
    """


def obtener_otras_tallas_mismo_modelo(row):
    productos = obtener_productos()
    if productos.empty:
        return productos

    df_modelo = productos[
        (productos["marca_codigo"] == row["marca_codigo"]) &
        (productos["tipo_codigo"] == row["tipo_codigo"]) &
        (productos["modelo"] == row["modelo"])
    ].copy()

    return df_modelo


def mostrar_otras_tallas(row):
    df_modelo = obtener_otras_tallas_mismo_modelo(row)
    if df_modelo.empty:
        return

    modelo_codigo = f"{row['marca_codigo']}-{row['tipo_codigo']}-{row['modelo']}"
    st.markdown("#### Otras tallas / piezas del mismo modelo")
    st.caption(f"Modelo: {modelo_codigo}")

    columnas = ["codigo", "talla", "estado", "precio"]
    df_vista = df_modelo[columnas].sort_values(["talla", "codigo"])
    st.dataframe(df_vista, use_container_width=True, hide_index=True)


def mostrar_ficha_producto_cliente(row):
    """
    Vista limitada para usuario cliente: no muestra historial, clientas, reportes ni acciones.
    """
    mostrar_estado_visual(row["estado"])

    with st.container(border=True):
        col_img, col_info = st.columns([1, 2])

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

            if pd.notna(row["precio"]):
                st.markdown(f"### Precio: USD {row['precio']:,.2f}")
            else:
                st.markdown("### Precio: pendiente")

            estado_publico = "Disponible" if row["estado"] == "Disponible" else "No disponible"
            st.write(f"**Disponibilidad:** {estado_publico}")

    mostrar_otras_tallas(row)


def pantalla_cliente_publico():
    st.title("Consulta de producto")
    st.write("Escanea el QR de la etiqueta para ver la información y precio de la pieza.")

    foto_qr = st.camera_input("Escanear QR")
    codigo_manual = st.text_input("O escribe el código manualmente", placeholder="Ej: MRK-TP-01-T46-#01").strip()

    codigo = None
    if foto_qr is not None:
        codigo = decodificar_qr_desde_imagen(foto_qr)
        if codigo:
            st.success(f"QR leído: {codigo}")
        else:
            st.error("No pude leer el QR. Intenta de frente, con buena luz y sin sombra.")

    if codigo_manual:
        codigo = codigo_manual

    if codigo:
        productos = obtener_productos()
        resultado = productos[productos["codigo"] == codigo] if not productos.empty else productos
        if resultado.empty:
            st.warning("No encontré esa pieza.")
        else:
            mostrar_ficha_producto_cliente(resultado.iloc[0])

    logout_button()

def mostrar_producto_compacto(row):
    """
    Tarjeta compacta para navegar resultados en Buscar producto.
    """
    with st.container(border=True):
        col_img, col_info, col_estado, col_accion = st.columns([0.8, 3.2, 1.2, 1])

        with col_img:
            if row["foto_path"] and Path(row["foto_path"]).exists():
                st.image(row["foto_path"], width=75)
            else:
                st.caption("Sin foto")

        with col_info:
            st.markdown(f"**{row['codigo']}**")
            descripcion = row["descripcion"] if row["descripcion"] else "Sin descripción"
            precio = f"USD {row['precio']:,.2f}" if pd.notna(row["precio"]) else "Precio pendiente"
            st.caption(f"{descripcion}")
            st.caption(f"{row['marca_codigo']} · {row['tipo_codigo']} · Talla {row['talla']} · {row['color'] or 'Sin color'} · {precio}")

        with col_estado:
            st.markdown(badge_estado_html(row["estado"]), unsafe_allow_html=True)

        with col_accion:
            if st.button("Ver", key=f"ver_detalle_{row['id']}"):
                st.session_state["detalle_producto_codigo"] = row["codigo"]
                st.rerun()


def mostrar_ficha_producto(row, mostrar_acciones=True):
    with st.container(border=True):
        mostrar_estado_visual(row["estado"])
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
                key=f"download_label_{row['id']}_{mostrar_acciones}_{row['codigo']}"
            )

        mostrar_otras_tallas(row)

        if mostrar_acciones:
            st.markdown("#### Acciones")
            tab1, tab2, tab3, tab4, tab5 = st.tabs(["Vender", "Clienta se la lleva", "Reservar", "Marcar devuelta", "Devolución de venta"])
            with tab1:
                formulario_venta(row)
            with tab2:
                formulario_con_clienta(row)
            with tab3:
                formulario_reserva(row)
            with tab4:
                formulario_devolucion(row)
            with tab5:
                formulario_devolucion_venta(row)


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
            registrar_movimiento(row["codigo"], "Venta", cliente, telefono, precio, monto_pagado, forma_pago, estado_pago, estado_entrega, observacion)
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
            registrar_movimiento(row["codigo"], "Con clienta", cliente=cliente, telefono=telefono, observacion=observacion)
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
            registrar_movimiento(row["codigo"], "Reserva", cliente=cliente, telefono=telefono, observacion=observacion)
            st.success("Reserva registrada correctamente.")
            st.rerun()


def formulario_devolucion(row):
    if row["estado"] not in ["Con clienta", "Reservado"]:
        st.info("Esta acción se usa principalmente para piezas con clienta o reservadas. No afecta ventas.")

    with st.form(f"devolucion_{row['id']}"):
        observacion = st.text_area("Observación", key=f"dev_obs_{row['id']}")
        submitted = st.form_submit_button("Marcar como disponible")

        if submitted:
            actualizar_estado_producto(row["codigo"], "Disponible")
            registrar_movimiento(row["codigo"], "Devolución / Disponible", observacion=observacion)
            st.success("Pieza marcada como disponible. Esta acción no cancela ninguna venta.")
            st.rerun()


def formulario_devolucion_venta(row):
    st.warning("Usa esta opción solo si una venta fue devuelta. Esto registra una devolución separada para que el reporte muestre venta bruta, devolución y venta neta.")
    with st.form(f"devolucion_venta_{row['id']}"):
        cliente = st.text_input("Cliente", key=f"devventa_cliente_{row['id']}")
        telefono = st.text_input("Teléfono", key=f"devventa_tel_{row['id']}")
        precio_default = float(row["precio"]) if pd.notna(row["precio"]) else 0.0
        monto_devuelto = st.number_input("Monto devuelto / valor de devolución", min_value=0.0, value=precio_default, step=1.0, key=f"devventa_monto_{row['id']}")
        observacion = st.text_area("Observación", key=f"devventa_obs_{row['id']}")
        volver_disponible = st.checkbox("Marcar pieza como disponible", value=True, key=f"devventa_disponible_{row['id']}")
        submitted = st.form_submit_button("Registrar devolución de venta")

        if submitted:
            if volver_disponible:
                actualizar_estado_producto(row["codigo"], "Disponible")
            registrar_movimiento(
                row["codigo"],
                "Devolución de venta",
                cliente=cliente,
                telefono=telefono,
                precio=monto_devuelto,
                monto_pagado=0,
                estado_pago="Devolución",
                observacion=observacion
            )
            st.success("Devolución de venta registrada. La venta original se mantiene en historial.")
            st.rerun()

# ======================================================
# INICIO APP
# ======================================================

inicializar_db()
login()

if st.session_state.get("user") == "cliente":
    pantalla_cliente_publico()
    st.stop()

logout_button()

st.title("Control de Tienda")
st.caption("Cuaderno digital para inventario, clientas, ventas, abonos, reservas y cierre del día.")

# Navegación por botones desde Inicio rápido
if "menu_actual" not in st.session_state:
    st.session_state["menu_actual"] = "Inicio rápido"

opciones_menu = [
    "Inicio rápido",
    "Cuaderno del día",
    "Nuevo producto",
    "Inventario",
    "Buscar pieza",
    "Escanear QR",
    "Clientes",
    "Piezas con clientas",
    "Reservas",
    "Ventas",
    "Reporte diario",
    "Reporte acumulado",
    "Historial",
    "Admin"
]

menu_guardado = st.session_state.get("menu_actual", "Inicio rápido")
if menu_guardado not in opciones_menu:
    menu_guardado = "Inicio rápido"

menu = st.sidebar.radio(
    "Menú",
    opciones_menu,
    index=opciones_menu.index(menu_guardado)
)
st.session_state["menu_actual"] = menu

# ======================================================
# INICIO RÁPIDO
# ======================================================

if menu == "Inicio rápido":
    st.header("Inicio rápido")
    st.write("Elige qué quieres hacer ahora.")

    col1, col2 = st.columns(2)

    with col1:
        if st.button("Escanear pieza", use_container_width=True):
            st.session_state["menu_actual"] = "Escanear QR"
            st.rerun()

        if st.button("Buscar clienta", use_container_width=True):
            st.session_state["menu_actual"] = "Clientes"
            st.rerun()

        if st.button("Ver piezas con clientas", use_container_width=True):
            st.session_state["menu_actual"] = "Piezas con clientas"
            st.rerun()

    with col2:
        if st.button("Buscar pieza", use_container_width=True):
            st.session_state["menu_actual"] = "Buscar pieza"
            st.rerun()

        if st.button("Inventario", use_container_width=True):
            st.session_state["menu_actual"] = "Inventario"
            st.rerun()

        if st.button("Cierre del día", use_container_width=True):
            st.session_state["menu_actual"] = "Reporte diario"
            st.rerun()

    st.markdown("---")
    st.subheader("Resumen rápido de hoy")

    productos = obtener_productos()
    movimientos = obtener_movimientos()
    fecha_hoy = date.today().strftime("%Y-%m-%d")
    resumen, mov_dia, ventas_dia, devoluciones_dia, con_clienta, reservas, disponibles, vendidas = calcular_resumen_reporte(productos, movimientos, fecha_hoy)

    c1, c2, c3 = st.columns(3)
    c1.metric("Ventas netas hoy", resumen["Ventas netas del día"])
    c2.metric("Cobrado hoy", resumen["Pagado registrado"])
    c3.metric("Pendiente neto", resumen["Pendiente neto"])

    c4, c5, c6 = st.columns(3)
    c4.metric("Con clientas", resumen["Piezas con clientas"])
    c5.metric("Reservadas", resumen["Piezas reservadas"])
    c6.metric("Disponibles", resumen["Piezas disponibles"])

# ======================================================
# CUADERNO DEL DÍA
# ======================================================

elif menu == "Cuaderno del día":
    st.header("Cuaderno del día")
    st.write("Resumen simple de lo que ha pasado hoy en la tienda.")

    productos = obtener_productos()
    movimientos = obtener_movimientos()
    fecha_hoy = date.today().strftime("%Y-%m-%d")
    resumen, mov_dia, ventas_dia, devoluciones_dia, con_clienta, reservas, disponibles, vendidas = calcular_resumen_reporte(productos, movimientos, fecha_hoy)

    st.subheader("Números de hoy")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Ventas brutas", resumen["Ventas brutas del día"])
    c2.metric("Devoluciones", resumen["Devoluciones del día"])
    c3.metric("Ventas netas", resumen["Ventas netas del día"])
    c4.metric("Cobrado", resumen["Pagado registrado"])

    st.markdown("---")

    st.subheader("Ventas de hoy")
    if ventas_dia.empty:
        st.info("Aún no hay ventas registradas hoy.")
    else:
        for _, mov in ventas_dia.iterrows():
            with st.container(border=True):
                st.markdown(f"**{mov['cliente'] or 'Clienta no indicada'}**")
                st.write(f"Pieza: {mov['producto_codigo']}")
                st.write(f"Precio: USD {mov['precio'] or 0:,.2f} · Pagado: USD {mov['monto_pagado'] or 0:,.2f}")
                if mov['estado_pago']:
                    st.caption(f"Pago: {mov['estado_pago']}")
                if mov['observacion']:
                    st.caption(f"Nota: {mov['observacion']}")

    st.subheader("Piezas con clientas")
    if con_clienta.empty:
        st.info("No hay piezas con clientas en este momento.")
    else:
        for _, row in con_clienta.iterrows():
            with st.container(border=True):
                st.markdown(f"**{row['codigo']}**")
                st.write(f"{row['descripcion'] or 'Sin descripción'} · Talla {row['talla']} · USD {row['precio'] if pd.notna(row['precio']) else 'pendiente'}")

    st.subheader("Reservas activas")
    if reservas.empty:
        st.info("No hay reservas activas.")
    else:
        for _, row in reservas.iterrows():
            with st.container(border=True):
                st.markdown(f"**{row['codigo']}**")
                st.write(f"{row['descripcion'] or 'Sin descripción'} · Talla {row['talla']} · USD {row['precio'] if pd.notna(row['precio']) else 'pendiente'}")

# ======================================================
# NUEVO PRODUCTO
# ======================================================

elif menu == "Nuevo producto":
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

                ahora = ahora_caracas_str()
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
        colf1, colf2, colf3, colf4 = st.columns(4)
        tallas = ["Todas"] + sorted(df["talla"].dropna().astype(str).unique().tolist())
        with colf1:
            marca_filtro = st.selectbox("Marca", ["Todas"] + list(MARCAS.keys()), format_func=lambda x: "Todas" if x == "Todas" else f"{x} - {MARCAS[x]}")
        with colf2:
            tipo_filtro = st.selectbox("Tipo", ["Todos"] + list(TIPOS.keys()), format_func=lambda x: "Todos" if x == "Todos" else f"{x} - {TIPOS[x]}")
        with colf3:
            talla_filtro = st.selectbox("Talla", tallas)
        with colf4:
            estado_filtro = st.selectbox("Estado", ["Todos"] + ESTADOS)

        coleccion_filtro = st.selectbox("Colección", ["Todas"] + COLECCIONES)

        df_vista = filtrar_productos_avanzado(df, marca_filtro, tipo_filtro, talla_filtro, estado_filtro, coleccion_filtro)

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

        pdf_disponibles = generar_pdf_disponibles_con_fotos(df)
        col_desc1, col_desc2 = st.columns(2)
        with col_desc1:
            st.download_button(
                "Descargar inventario completo en CSV",
                data=df.to_csv(index=False).encode("utf-8"),
                file_name="inventario_tienda.csv",
                mime="text/csv"
            )
        with col_desc2:
            st.download_button(
                "Descargar catálogo PDF de disponibles con fotos",
                data=pdf_disponibles,
                file_name="catalogo_disponibles_con_fotos.pdf",
                mime="application/pdf"
            )

# ======================================================
# BUSCAR PRODUCTO
# ======================================================

elif menu == "Buscar pieza":
    st.header("Buscar pieza")
    df = obtener_productos()

    if df.empty:
        st.warning("Todavía no hay productos cargados.")
    else:
        tallas = ["Todas"] + sorted(df["talla"].dropna().astype(str).unique().tolist())
        col1, col2, col3 = st.columns(3)
        with col1:
            marca_filtro = st.selectbox("Marca", ["Todas"] + list(MARCAS.keys()), format_func=lambda x: "Todas" if x == "Todas" else f"{x} - {MARCAS[x]}")
        with col2:
            tipo_filtro = st.selectbox("Tipo", ["Todos"] + list(TIPOS.keys()), format_func=lambda x: "Todos" if x == "Todos" else f"{x} - {TIPOS[x]}")
        with col3:
            talla_filtro = st.selectbox("Talla", tallas)

        col4, col5 = st.columns(2)
        with col4:
            estado_filtro = st.selectbox("Estado", ["Todos"] + ESTADOS)
        with col5:
            coleccion_filtro = st.selectbox("Colección", ["Todas"] + COLECCIONES)

        busqueda = st.text_input("Buscar por código, marca, tipo, descripción, color o talla", placeholder="Ej: MRK, TP, negro, T46, vestido...").strip().lower()

        df_filtrado = filtrar_productos_avanzado(df, marca_filtro, tipo_filtro, talla_filtro, estado_filtro, coleccion_filtro, busqueda)

        st.write(f"Resultados: {len(df_filtrado)}")

        vista = st.radio(
            "Vista",
            ["Compacta", "Detallada"],
            horizontal=True,
            index=0,
            help="La vista compacta es mejor para navegar. La detallada muestra toda la ficha de cada pieza."
        )

        if vista == "Compacta":
            if "detalle_producto_codigo" not in st.session_state:
                st.session_state["detalle_producto_codigo"] = None

            for _, row in df_filtrado.iterrows():
                mostrar_producto_compacto(row)

            if st.session_state.get("detalle_producto_codigo"):
                st.markdown("---")
                st.subheader("Detalle del producto")
                detalle = df[df["codigo"] == st.session_state["detalle_producto_codigo"]]

                if detalle.empty:
                    st.warning("La pieza seleccionada ya no aparece en el inventario.")
                    st.session_state["detalle_producto_codigo"] = None
                else:
                    if st.button("Cerrar detalle"):
                        st.session_state["detalle_producto_codigo"] = None
                        st.rerun()
                    mostrar_ficha_producto(detalle.iloc[0])
        else:
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
# CLIENTES
# ======================================================

elif menu == "Clientes":
    st.header("Clientes")
    st.write("Aquí puedes crear una clienta, entrar a su perfil y registrar piezas escaneando el QR con el teléfono.")

    productos = obtener_productos()
    movimientos = obtener_movimientos()
    clientes_df = obtener_clientes()

    tab_crear, tab_perfil = st.tabs(["Crear / actualizar clienta", "Perfil de clienta"])

    with tab_crear:
        st.subheader("Crear o actualizar clienta")
        with st.form("form_cliente"):
            nombre_cliente = st.text_input("Nombre de la clienta")
            telefono_cliente = st.text_input("Teléfono")
            notas_cliente = st.text_area("Notas")
            guardar_cliente = st.form_submit_button("Guardar clienta")

            if guardar_cliente:
                if not nombre_cliente.strip():
                    st.error("Debes indicar el nombre de la clienta.")
                else:
                    guardar_o_actualizar_cliente(nombre_cliente, telefono_cliente, notas_cliente)
                    st.success("Clienta guardada correctamente.")
                    st.rerun()

        st.subheader("Base de datos de clientas")
        clientes_df = obtener_clientes()
        if clientes_df.empty:
            st.info("Todavía no hay clientas registradas.")
        else:
            busqueda_cliente = st.text_input("Buscar en base de clientas", placeholder="Nombre o teléfono").strip().lower()
            vista_clientes = clientes_df.copy()
            if busqueda_cliente:
                vista_clientes = vista_clientes[
                    vista_clientes.apply(lambda row: busqueda_cliente in " ".join([
                        str(row.get("nombre", "")),
                        str(row.get("telefono", "")),
                        str(row.get("notas", ""))
                    ]).lower(), axis=1)
                ]
            st.dataframe(vista_clientes, use_container_width=True, hide_index=True)

    with tab_perfil:
        clientes_df = obtener_clientes()
        if clientes_df.empty:
            st.warning("Primero debes crear al menos una clienta.")
        else:
            clientes_df["display"] = clientes_df.apply(
                lambda r: f"{r['nombre']}" + (f" - {r['telefono']}" if pd.notna(r['telefono']) and str(r['telefono']).strip() else ""),
                axis=1
            )

            cliente_display = st.selectbox("Selecciona una clienta", clientes_df["display"].tolist())
            cliente_row = clientes_df[clientes_df["display"] == cliente_display].iloc[0]
            cliente_nombre = cliente_row["nombre"]
            cliente_telefono = cliente_row["telefono"] if pd.notna(cliente_row["telefono"]) else ""

            st.subheader(f"Perfil de clienta: {cliente_nombre}")
            if cliente_telefono:
                st.write(f"**Teléfono:** {cliente_telefono}")
            if pd.notna(cliente_row.get("notas", None)) and str(cliente_row.get("notas", "")).strip():
                st.write(f"**Notas:** {cliente_row['notas']}")

            mov_cliente = movimientos[
                movimientos["cliente"].astype(str).str.strip().str.lower() == str(cliente_nombre).strip().lower()
            ].copy() if not movimientos.empty else movimientos

            ventas_cliente = mov_cliente[mov_cliente["tipo_movimiento"] == "Venta"] if not mov_cliente.empty else mov_cliente
            devoluciones_cliente = mov_cliente[mov_cliente["tipo_movimiento"] == "Devolución de venta"] if not mov_cliente.empty else mov_cliente
            total_ventas = ventas_cliente["precio"].fillna(0).sum() if not ventas_cliente.empty else 0
            total_devoluciones = devoluciones_cliente["precio"].fillna(0).sum() if not devoluciones_cliente.empty else 0
            total_pagado = ventas_cliente["monto_pagado"].fillna(0).sum() if not ventas_cliente.empty else 0
            total_neto = total_ventas - total_devoluciones
            pendiente = total_neto - total_pagado

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Movimientos", len(mov_cliente))
            c2.metric("Ventas netas", f"USD {total_neto:,.2f}")
            c3.metric("Pagado", f"USD {total_pagado:,.2f}")
            c4.metric("Pendiente", f"USD {pendiente:,.2f}")

            st.markdown("---")
            st.subheader("Registrar pieza para esta clienta")
            st.write("Escanea el QR de la pieza o escribe el código manualmente.")

            col_scan, col_manual = st.columns(2)
            codigo_detectado = None

            with col_scan:
                foto_qr_cliente = st.camera_input("Escanear QR desde el perfil", key=f"qr_cliente_{cliente_row['id']}")
                if foto_qr_cliente is not None:
                    codigo_detectado = decodificar_qr_desde_imagen(foto_qr_cliente)
                    if codigo_detectado:
                        st.success(f"QR leído: {codigo_detectado}")
                    else:
                        st.error("No pude leer el QR. Intenta con mejor luz o más de frente.")

            with col_manual:
                codigo_manual = st.text_input("O escribe el código de la pieza", placeholder="Ej: MRK-TP-01-T46-#01", key=f"manual_cliente_{cliente_row['id']}").strip()
                if codigo_manual:
                    codigo_detectado = codigo_manual

            if codigo_detectado:
                producto_sel = productos[productos["codigo"] == codigo_detectado] if not productos.empty else productos
                if producto_sel.empty:
                    st.warning("Ese código no existe en el inventario.")
                else:
                    row = producto_sel.iloc[0]
                    mostrar_ficha_producto(row, mostrar_acciones=False)

                    st.markdown("#### Acción para esta clienta")
                    accion = st.selectbox(
                        "Qué quieres registrar",
                        ["Venta", "Clienta se la lleva", "Reserva", "Devolución / Disponible", "Devolución de venta"],
                        key=f"accion_cliente_{cliente_row['id']}_{row['id']}"
                    )

                    if accion == "Venta":
                        with st.form(f"venta_cliente_{cliente_row['id']}_{row['id']}"):
                            precio_default = float(row["precio"]) if pd.notna(row["precio"]) else 0.0
                            precio = st.number_input("Precio de venta", min_value=0.0, value=precio_default, step=1.0)
                            monto_pagado = st.number_input("Monto pagado", min_value=0.0, value=precio_default, step=1.0)
                            forma_pago = st.selectbox("Forma de pago", FORMAS_PAGO)
                            estado_pago = st.selectbox("Estado de pago", ["Pagado completo", "Pendiente", "Abonado"])
                            estado_entrega = st.selectbox("Entrega", ["Entregado", "Pendiente de entrega"])
                            observacion = st.text_area("Observación")
                            submitted = st.form_submit_button("Registrar venta a esta clienta")
                            if submitted:
                                actualizar_estado_producto(row["codigo"], "Vendido")
                                registrar_movimiento(row["codigo"], "Venta", cliente_nombre, cliente_telefono, precio, monto_pagado, forma_pago, estado_pago, estado_entrega, observacion)
                                st.success("Venta registrada en el perfil de la clienta.")
                                st.rerun()

                    elif accion == "Clienta se la lleva":
                        with st.form(f"con_clienta_perfil_{cliente_row['id']}_{row['id']}"):
                            observacion = st.text_area("Observación")
                            submitted = st.form_submit_button("Registrar como con clienta")
                            if submitted:
                                actualizar_estado_producto(row["codigo"], "Con clienta")
                                registrar_movimiento(row["codigo"], "Con clienta", cliente=cliente_nombre, telefono=cliente_telefono, observacion=observacion)
                                st.success("Pieza registrada como con clienta.")
                                st.rerun()

                    elif accion == "Reserva":
                        with st.form(f"reserva_perfil_{cliente_row['id']}_{row['id']}"):
                            observacion = st.text_area("Observación")
                            submitted = st.form_submit_button("Registrar reserva")
                            if submitted:
                                actualizar_estado_producto(row["codigo"], "Reservado")
                                registrar_movimiento(row["codigo"], "Reserva", cliente=cliente_nombre, telefono=cliente_telefono, observacion=observacion)
                                st.success("Reserva registrada en el perfil de la clienta.")
                                st.rerun()

                    elif accion == "Devolución / Disponible":
                        with st.form(f"dev_perfil_{cliente_row['id']}_{row['id']}"):
                            observacion = st.text_area("Observación")
                            submitted = st.form_submit_button("Marcar como disponible")
                            if submitted:
                                actualizar_estado_producto(row["codigo"], "Disponible")
                                registrar_movimiento(row["codigo"], "Devolución / Disponible", cliente=cliente_nombre, telefono=cliente_telefono, observacion=observacion)
                                st.success("Pieza marcada como disponible.")
                                st.rerun()

                    elif accion == "Devolución de venta":
                        with st.form(f"devventa_perfil_{cliente_row['id']}_{row['id']}"):
                            precio_default = float(row["precio"]) if pd.notna(row["precio"]) else 0.0
                            monto_devuelto = st.number_input("Monto devuelto / valor de devolución", min_value=0.0, value=precio_default, step=1.0)
                            observacion = st.text_area("Observación")
                            volver_disponible = st.checkbox("Marcar pieza como disponible", value=True)
                            submitted = st.form_submit_button("Registrar devolución de venta")
                            if submitted:
                                if volver_disponible:
                                    actualizar_estado_producto(row["codigo"], "Disponible")
                                registrar_movimiento(row["codigo"], "Devolución de venta", cliente=cliente_nombre, telefono=cliente_telefono, precio=monto_devuelto, monto_pagado=0, estado_pago="Devolución", observacion=observacion)
                                st.success("Devolución de venta registrada en el perfil de la clienta.")
                                st.rerun()

            st.markdown("---")
            st.subheader("Historial de esta clienta")
            if mov_cliente.empty:
                st.info("Esta clienta todavía no tiene movimientos.")
            else:
                columnas_cliente = ["fecha", "tipo_movimiento", "producto_codigo", "telefono", "precio", "monto_pagado", "estado_pago", "estado_entrega", "observacion"]
                st.dataframe(mov_cliente[columnas_cliente], use_container_width=True, hide_index=True)

                codigos_cliente = mov_cliente["producto_codigo"].dropna().unique().tolist()
                if codigos_cliente:
                    codigo_sel = st.selectbox("Ver detalle de una pieza del historial", codigos_cliente)
                    prod_sel = productos[productos["codigo"] == codigo_sel]
                    if prod_sel.empty:
                        st.warning("Esta pieza ya no aparece en el inventario de productos.")
                    else:
                        mostrar_ficha_producto(prod_sel.iloc[0], mostrar_acciones=False)

# ======================================================
# PIEZAS CON CLIENTAS
# ======================================================

elif menu == "Piezas con clientas":
    st.header("Piezas con clientas")
    productos = obtener_productos()
    movimientos = obtener_movimientos()
    df = productos[productos["estado"] == "Con clienta"]

    cliente_filtro = st.text_input("Filtrar por cliente", placeholder="Nombre o teléfono").strip().lower()

    if df.empty:
        st.success("No hay piezas registradas como con clienta.")
    else:
        for _, row in df.iterrows():
            ult = movimientos[(movimientos["producto_codigo"] == row["codigo"]) & (movimientos["tipo_movimiento"] == "Con clienta")]
            if not ult.empty:
                ultimo = ult.iloc[0]
                texto_cliente = f"{ultimo['cliente'] or ''} {ultimo['telefono'] or ''}".lower()
                if cliente_filtro and cliente_filtro not in texto_cliente:
                    continue
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

    cliente_filtro = st.text_input("Filtrar por cliente", placeholder="Nombre o teléfono").strip().lower()

    if df.empty:
        st.success("No hay piezas reservadas.")
    else:
        for _, row in df.iterrows():
            ult = movimientos[(movimientos["producto_codigo"] == row["codigo"]) & (movimientos["tipo_movimiento"] == "Reserva")]
            if not ult.empty:
                ultimo = ult.iloc[0]
                texto_cliente = f"{ultimo['cliente'] or ''} {ultimo['telefono'] or ''}".lower()
                if cliente_filtro and cliente_filtro not in texto_cliente:
                    continue
                st.write(f"**Cliente:** {ultimo['cliente'] or 'No indicado'} | **Teléfono:** {ultimo['telefono'] or 'No indicado'} | **Fecha:** {ultimo['fecha']}")
            mostrar_ficha_producto(row)

# ======================================================
# VENTAS
# ======================================================

elif menu == "Ventas":
    st.header("Ventas")
    movimientos = obtener_movimientos()
    ventas = movimientos[movimientos["tipo_movimiento"] == "Venta"]
    devoluciones = movimientos[movimientos["tipo_movimiento"] == "Devolución de venta"]

    if ventas.empty and devoluciones.empty:
        st.warning("Todavía no hay ventas registradas.")
    else:
        cliente_filtro = st.text_input("Filtrar ventas por cliente", placeholder="Nombre o teléfono").strip().lower()
        ventas_vista = ventas.copy()
        devoluciones_vista = devoluciones.copy()
        if cliente_filtro:
            ventas_vista = ventas_vista[ventas_vista.apply(lambda row: cliente_filtro in " ".join([str(row.get("cliente", "")), str(row.get("telefono", ""))]).lower(), axis=1)]
            devoluciones_vista = devoluciones_vista[devoluciones_vista.apply(lambda row: cliente_filtro in " ".join([str(row.get("cliente", "")), str(row.get("telefono", ""))]).lower(), axis=1)]

        total_ventas_brutas = ventas_vista["precio"].fillna(0).sum() if not ventas_vista.empty else 0
        total_devoluciones = devoluciones_vista["precio"].fillna(0).sum() if not devoluciones_vista.empty else 0
        total_neto = total_ventas_brutas - total_devoluciones
        total_pagado = ventas_vista["monto_pagado"].fillna(0).sum() if not ventas_vista.empty else 0
        pendiente = total_neto - total_pagado

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Ventas brutas", f"USD {total_ventas_brutas:,.2f}")
        c2.metric("Devoluciones", f"USD {total_devoluciones:,.2f}")
        c3.metric("Ventas netas", f"USD {total_neto:,.2f}")
        c4.metric("Pendiente neto", f"USD {pendiente:,.2f}")

        st.subheader("Ventas")
        st.dataframe(ventas_vista, use_container_width=True, hide_index=True)
        st.subheader("Devoluciones de venta")
        st.dataframe(devoluciones_vista, use_container_width=True, hide_index=True)

# ======================================================
# REPORTE DIARIO
# ======================================================

elif menu == "Reporte diario":
    st.header("Reporte diario")
    st.write("Puedes generar un reporte parcial en cualquier momento del día o un reporte final al cierre. Ambos son descargables en PDF y Excel.")

    col_fecha, col_tipo = st.columns(2)
    with col_fecha:
        fecha_reporte = st.date_input("Fecha del reporte", value=date.today())
    with col_tipo:
        tipo_reporte = st.selectbox("Tipo de reporte", ["Parcial", "Final"])

    fecha_str = fecha_reporte.strftime("%Y-%m-%d")

    productos = obtener_productos()
    movimientos = obtener_movimientos()
    resumen, mov_dia, ventas_dia, devoluciones_dia, con_clienta, reservas, disponibles, vendidas = calcular_resumen_reporte(productos, movimientos, fecha_str)

    st.subheader("Resumen")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Ventas brutas", resumen["Ventas brutas del día"])
    c2.metric("Devoluciones", resumen["Devoluciones del día"])
    c3.metric("Ventas netas", resumen["Ventas netas del día"])
    c4.metric("Pendiente neto", resumen["Pendiente neto"])

    c5, c6, c7, c8 = st.columns(4)
    c5.metric("Piezas vendidas hoy", resumen["Piezas vendidas hoy"])
    c6.metric("Devoluciones hoy", resumen["Devoluciones hoy"])
    c7.metric("Con clientas", resumen["Piezas con clientas"])
    c8.metric("Reservadas", resumen["Piezas reservadas"])

    st.subheader("Ventas del día")
    if ventas_dia.empty:
        st.info("No hay ventas registradas en esta fecha.")
    else:
        st.dataframe(ventas_dia, use_container_width=True, hide_index=True)

    st.subheader("Devoluciones del día")
    if devoluciones_dia.empty:
        st.info("No hay devoluciones registradas en esta fecha.")
    else:
        st.dataframe(devoluciones_dia, use_container_width=True, hide_index=True)

    st.subheader("Piezas con clientas")
    if con_clienta.empty:
        st.info("No hay piezas con clientas.")
    else:
        st.dataframe(con_clienta[["codigo", "descripcion", "color", "talla", "precio", "estado"]], use_container_width=True, hide_index=True)

    st.subheader("Reservas")
    if reservas.empty:
        st.info("No hay reservas activas.")
    else:
        st.dataframe(reservas[["codigo", "descripcion", "color", "talla", "precio", "estado"]], use_container_width=True, hide_index=True)

    pdf_bytes = generar_pdf_reporte(fecha_str, tipo_reporte, resumen, ventas_dia, devoluciones_dia, con_clienta, reservas)
    excel_bytes = generar_excel_reporte(fecha_str, resumen, ventas_dia, devoluciones_dia, con_clienta, reservas, mov_dia)

    nombre_tipo = tipo_reporte.lower()
    col_pdf, col_excel = st.columns(2)
    with col_pdf:
        st.download_button(
            f"Descargar reporte {nombre_tipo} en PDF",
            data=pdf_bytes,
            file_name=f"reporte_{nombre_tipo}_{fecha_str}.pdf",
            mime="application/pdf"
        )
    with col_excel:
        st.download_button(
            f"Descargar reporte {nombre_tipo} en Excel",
            data=excel_bytes,
            file_name=f"reporte_{nombre_tipo}_{fecha_str}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

# ======================================================
# REPORTE ACUMULADO
# ======================================================

elif menu == "Reporte acumulado":
    st.header("Reporte acumulado")
    st.write("Genera un reporte por rango de fechas. Sirve para ver acumulados de temporada o de varios días.")

    col_inicio, col_fin = st.columns(2)
    with col_inicio:
        fecha_inicio = st.date_input("Desde", value=date.today(), key="acumulado_desde")
    with col_fin:
        fecha_fin = st.date_input("Hasta", value=date.today(), key="acumulado_hasta")

    if fecha_fin < fecha_inicio:
        st.error("La fecha final no puede ser anterior a la fecha inicial.")
    else:
        productos = obtener_productos()
        movimientos = obtener_movimientos()

        inicio_str = fecha_inicio.strftime("%Y-%m-%d")
        fin_str = fecha_fin.strftime("%Y-%m-%d")

        if movimientos.empty:
            mov_rango = movimientos
        else:
            fechas_mov = pd.to_datetime(movimientos["fecha"], errors="coerce")
            mov_rango = movimientos[(fechas_mov.dt.date >= fecha_inicio) & (fechas_mov.dt.date <= fecha_fin)].copy()

        ventas_rango = mov_rango[mov_rango["tipo_movimiento"] == "Venta"] if not mov_rango.empty else mov_rango
        devoluciones_rango = mov_rango[mov_rango["tipo_movimiento"] == "Devolución de venta"] if not mov_rango.empty else mov_rango

        total_ventas_brutas = ventas_rango["precio"].fillna(0).sum() if not ventas_rango.empty else 0
        total_devoluciones = devoluciones_rango["precio"].fillna(0).sum() if not devoluciones_rango.empty else 0
        total_ventas_netas = total_ventas_brutas - total_devoluciones
        total_pagado = ventas_rango["monto_pagado"].fillna(0).sum() if not ventas_rango.empty else 0
        pendiente = total_ventas_netas - total_pagado

        con_clienta = productos[productos["estado"] == "Con clienta"] if not productos.empty else productos
        reservas = productos[productos["estado"] == "Reservado"] if not productos.empty else productos

        resumen = {
            "Rango": f"{inicio_str} a {fin_str}",
            "Ventas brutas": f"USD {total_ventas_brutas:,.2f}",
            "Devoluciones": f"USD {total_devoluciones:,.2f}",
            "Ventas netas": f"USD {total_ventas_netas:,.2f}",
            "Pagado registrado": f"USD {total_pagado:,.2f}",
            "Pendiente neto": f"USD {pendiente:,.2f}",
            "Piezas vendidas": str(len(ventas_rango)),
            "Devoluciones": str(len(devoluciones_rango)),
            "Piezas con clientas actuales": str(len(con_clienta)),
            "Reservas actuales": str(len(reservas)),
        }

        st.subheader("Resumen acumulado")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Ventas brutas", f"USD {total_ventas_brutas:,.2f}")
        c2.metric("Devoluciones", f"USD {total_devoluciones:,.2f}")
        c3.metric("Ventas netas", f"USD {total_ventas_netas:,.2f}")
        c4.metric("Pendiente", f"USD {pendiente:,.2f}")

        st.subheader("Ventas del rango")
        st.dataframe(ventas_rango, use_container_width=True, hide_index=True)

        st.subheader("Devoluciones del rango")
        st.dataframe(devoluciones_rango, use_container_width=True, hide_index=True)

        pdf_bytes = generar_pdf_reporte(
            f"{inicio_str}_a_{fin_str}",
            "Acumulado",
            resumen,
            ventas_rango,
            devoluciones_rango,
            con_clienta,
            reservas
        )
        excel_bytes = generar_excel_reporte(
            f"{inicio_str}_a_{fin_str}",
            resumen,
            ventas_rango,
            devoluciones_rango,
            con_clienta,
            reservas,
            mov_rango
        )

        col_pdf, col_excel = st.columns(2)
        with col_pdf:
            st.download_button(
                "Descargar acumulado en PDF",
                data=pdf_bytes,
                file_name=f"reporte_acumulado_{inicio_str}_a_{fin_str}.pdf",
                mime="application/pdf"
            )
        with col_excel:
            st.download_button(
                "Descargar acumulado en Excel",
                data=excel_bytes,
                file_name=f"reporte_acumulado_{inicio_str}_a_{fin_str}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

# ======================================================
# ADMIN
# ======================================================

elif menu == "Admin":
    if st.session_state.get("user") != "jc":
        st.error("No tienes acceso a esta sección.")
        st.stop()

    st.header("Admin")
    st.warning("Esta sección es solo para JC. Úsala únicamente para ajustes, correcciones o antes de cargar el inventario real.")

    tab_modificar, tab_reset = st.tabs(["Modificar piezas", "Resetear datos de prueba"])

    with tab_modificar:
        st.subheader("Modificar piezas")
        productos = obtener_productos()

        if productos.empty:
            st.info("Todavía no hay piezas cargadas.")
        else:
            busqueda_admin = st.text_input("Buscar pieza para modificar", placeholder="Código, marca, descripción, talla...").strip().lower()
            productos_vista = productos.copy()

            if busqueda_admin:
                productos_vista = productos_vista[
                    productos_vista.apply(lambda row: busqueda_admin in " ".join([
                        str(row.get("codigo", "")),
                        str(row.get("marca_codigo", "")),
                        str(row.get("marca_nombre", "")),
                        str(row.get("tipo_codigo", "")),
                        str(row.get("tipo_nombre", "")),
                        str(row.get("descripcion", "")),
                        str(row.get("color", "")),
                        str(row.get("talla", "")),
                        str(row.get("estado", "")),
                        str(row.get("coleccion", ""))
                    ]).lower(), axis=1)
                ]

            if productos_vista.empty:
                st.warning("No encontré piezas con ese criterio.")
            else:
                codigo_sel = st.selectbox("Selecciona la pieza", productos_vista["codigo"].tolist())
                row = productos[productos["codigo"] == codigo_sel].iloc[0]

                st.caption("Por seguridad, desde aquí no se cambia el código, marca, tipo, modelo ni talla. Solo datos editables de operación.")
                mostrar_ficha_producto(row, mostrar_acciones=False)

                with st.form(f"admin_editar_{row['id']}"):
                    descripcion = st.text_area("Descripción", value=row["descripcion"] or "")
                    color = st.text_input("Color", value=row["color"] or "")
                    coleccion_actual = row["coleccion"] if row["coleccion"] in COLECCIONES else COLECCIONES[0]
                    coleccion = st.selectbox("Colección", COLECCIONES, index=COLECCIONES.index(coleccion_actual))
                    precio_actual = float(row["precio"]) if pd.notna(row["precio"]) else 0.0
                    precio = st.number_input("Precio", min_value=0.0, value=precio_actual, step=1.0)
                    estado_actual = row["estado"] if row["estado"] in ESTADOS else "Disponible"
                    estado = st.selectbox("Estado", ESTADOS, index=ESTADOS.index(estado_actual))
                    nueva_foto = st.file_uploader("Reemplazar foto (opcional)", type=["jpg", "jpeg", "png"])
                    observacion = st.text_area("Nota de corrección / motivo", placeholder="Ej: corrección de precio, cambio de foto...")

                    guardar_cambios = st.form_submit_button("Guardar cambios")

                    if guardar_cambios:
                        foto_path = None
                        if nueva_foto is not None:
                            extension = Path(nueva_foto.name).suffix.lower()
                            foto_path = str(UPLOAD_DIR / f"{row['codigo']}{extension}")
                            with open(foto_path, "wb") as f:
                                f.write(nueva_foto.getbuffer())

                        actualizar_producto_admin(row["codigo"], descripcion, color, coleccion, precio, estado, foto_path)
                        registrar_movimiento(
                            producto_codigo=row["codigo"],
                            tipo_movimiento="Corrección admin",
                            precio=precio,
                            observacion=observacion or "Corrección de datos de pieza"
                        )
                        st.success("Pieza modificada correctamente.")
                        st.rerun()

    with tab_reset:
        st.subheader("Resetear datos de prueba")
        st.write("Esto borra productos, clientas, movimientos, ventas, reservas, piezas con clientas y fotos cargadas.")

        confirmacion = st.text_input("Para confirmar, escribe exactamente: RESET")
        segunda_confirmacion = st.checkbox("Entiendo que esto borrará todos los datos actuales de la app")

        if st.button("Resetear app"):
            if confirmacion != "RESET" or not segunda_confirmacion:
                st.error("Debes escribir RESET y marcar la confirmación para continuar.")
            else:
                conn = conectar_db()
                conn.close()

                db_file = Path(DB_PATH)
                if db_file.exists():
                    db_file.unlink()

                if UPLOAD_DIR.exists():
                    shutil.rmtree(UPLOAD_DIR)
                UPLOAD_DIR.mkdir(exist_ok=True)

                inicializar_db()
                st.success("La app fue reseteada correctamente. Ya puedes cargar datos reales desde cero.")
                st.rerun()

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
        cliente_filtro = st.text_input("Filtrar por cliente", placeholder="Nombre o teléfono").strip().lower()
        df_mov = movimientos.copy()
        if tipo_filtro != "Todos":
            df_mov = df_mov[df_mov["tipo_movimiento"] == tipo_filtro]
        if cliente_filtro:
            df_mov = df_mov[df_mov.apply(lambda row: cliente_filtro in " ".join([str(row.get("cliente", "")), str(row.get("telefono", ""))]).lower(), axis=1)]

        st.dataframe(df_mov, use_container_width=True, hide_index=True)
        st.download_button("Descargar historial en CSV", data=movimientos.to_csv(index=False).encode("utf-8"), file_name="historial_movimientos.csv", mime="text/csv")
