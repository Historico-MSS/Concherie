from __future__ import annotations

from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Optional

import pandas as pd
import streamlit as st

APP_TITLE = "Inventario Concha"
LOCAL_INVENTORY = Path("inventario_local.csv")
LOCAL_SALES = Path("ventas_local.csv")
LOCAL_MOVEMENTS = Path("movimientos_local.csv")
INITIAL_INVENTORY = Path("inventario_inicial.csv")

INVENTORY_COLUMNS = [
    "id",
    "codigo",
    "producto",
    "cantidad",
    "precio_unitario",
    "activo",
    "fecha_creacion",
    "fecha_actualizacion",
]

SALES_COLUMNS = [
    "fecha",
    "id",
    "codigo",
    "producto",
    "cantidad_vendida",
    "precio_unitario",
    "total",
    "metodo_pago",
    "nota",
]

MOVEMENT_COLUMNS = [
    "fecha",
    "id",
    "codigo",
    "producto",
    "tipo_movimiento",
    "cantidad_anterior",
    "cantidad_nueva",
    "precio_anterior",
    "precio_nuevo",
    "nota",
]


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def normalize_inventory(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    rename_map = {
        "Código": "codigo",
        "Codigo": "codigo",
        "Producto": "producto",
        "Cantidad": "cantidad",
        "Precio unitario": "precio_unitario",
        "Precio Unitario": "precio_unitario",
    }
    df = df.rename(columns=rename_map)

    for col in ["codigo", "producto"]:
        if col not in df.columns:
            df[col] = ""
        df[col] = df[col].fillna("").astype(str).str.strip()

    if "cantidad" not in df.columns:
        df["cantidad"] = 0
    if "precio_unitario" not in df.columns:
        df["precio_unitario"] = 0

    df["cantidad"] = pd.to_numeric(df["cantidad"], errors="coerce").fillna(0).astype(int)
    df["precio_unitario"] = pd.to_numeric(df["precio_unitario"], errors="coerce").fillna(0).astype(float)

    if "id" not in df.columns:
        df.insert(0, "id", [f"P{i+1:04d}" for i in range(len(df))])
    else:
        df["id"] = df["id"].fillna("").astype(str)
        missing = df["id"].str.strip().eq("")
        df.loc[missing, "id"] = [f"P{i+1:04d}" for i in range(missing.sum())]

    if "activo" not in df.columns:
        df["activo"] = True
    else:
        df["activo"] = df["activo"].astype(str).str.lower().isin(["true", "1", "sí", "si", "yes", "x"])

    if "fecha_creacion" not in df.columns:
        df["fecha_creacion"] = now_str()
    if "fecha_actualizacion" not in df.columns:
        df["fecha_actualizacion"] = now_str()

    return df[INVENTORY_COLUMNS]


@st.cache_resource(show_spinner=False)
def get_google_client():
    try:
        import gspread
        from google.oauth2.service_account import Credentials

        if "google" not in st.secrets:
            return None
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        creds = Credentials.from_service_account_info(dict(st.secrets["google"]), scopes=scopes)
        return gspread.authorize(creds)
    except Exception as exc:
        st.warning(f"No se pudo conectar con Google Sheets. Usando modo local. Detalle: {exc}")
        return None


def get_sheet_config() -> dict:
    sheets = st.secrets.get("sheets", {}) if hasattr(st, "secrets") else {}
    return {
        "spreadsheet_name": sheets.get("spreadsheet_name", "Inventario Concha"),
        "inventory_worksheet": sheets.get("inventory_worksheet", "inventario"),
        "sales_worksheet": sheets.get("sales_worksheet", "ventas"),
        "movements_worksheet": sheets.get("movements_worksheet", "movimientos"),
    }


def open_or_create_worksheet(client, spreadsheet_name: str, worksheet_name: str, columns: list[str]):
    try:
        spreadsheet = client.open(spreadsheet_name)
    except Exception:
        spreadsheet = client.create(spreadsheet_name)
        st.info("Creé el Google Sheet. Recuerda compartirlo con quien necesite verlo.")

    try:
        ws = spreadsheet.worksheet(worksheet_name)
    except Exception:
        ws = spreadsheet.add_worksheet(title=worksheet_name, rows=1000, cols=max(20, len(columns)))
        ws.update([columns])
    values = ws.get_all_values()
    if not values:
        ws.update([columns])
    return ws


def read_ws(client, worksheet_name: str, columns: list[str]) -> pd.DataFrame:
    cfg = get_sheet_config()
    ws = open_or_create_worksheet(client, cfg["spreadsheet_name"], worksheet_name, columns)
    records = ws.get_all_records()
    if not records:
        return pd.DataFrame(columns=columns)
    return pd.DataFrame(records)


def write_ws(client, worksheet_name: str, df: pd.DataFrame, columns: list[str]) -> None:
    cfg = get_sheet_config()
    ws = open_or_create_worksheet(client, cfg["spreadsheet_name"], worksheet_name, columns)
    out = df.copy()
    for col in columns:
        if col not in out.columns:
            out[col] = ""
    out = out[columns].fillna("")
    ws.clear()
    ws.update([columns] + out.astype(str).values.tolist())


def read_local(path: Path, columns: list[str]) -> pd.DataFrame:
    if path.exists():
        return pd.read_csv(path)
    return pd.DataFrame(columns=columns)


def write_local(path: Path, df: pd.DataFrame) -> None:
    df.to_csv(path, index=False)


def load_inventory(client) -> pd.DataFrame:
    if client:
        df = read_ws(client, get_sheet_config()["inventory_worksheet"], INVENTORY_COLUMNS)
        if df.empty and INITIAL_INVENTORY.exists():
            df = normalize_inventory(pd.read_csv(INITIAL_INVENTORY))
            save_inventory(client, df)
        return normalize_inventory(df)

    if LOCAL_INVENTORY.exists():
        return normalize_inventory(pd.read_csv(LOCAL_INVENTORY))
    if INITIAL_INVENTORY.exists():
        df = normalize_inventory(pd.read_csv(INITIAL_INVENTORY))
        write_local(LOCAL_INVENTORY, df)
        return df
    return pd.DataFrame(columns=INVENTORY_COLUMNS)


def save_inventory(client, df: pd.DataFrame) -> None:
    df = normalize_inventory(df)
    if client:
        write_ws(client, get_sheet_config()["inventory_worksheet"], df, INVENTORY_COLUMNS)
    else:
        write_local(LOCAL_INVENTORY, df)


def load_table(client, kind: str) -> pd.DataFrame:
    if kind == "ventas":
        columns, local, worksheet = SALES_COLUMNS, LOCAL_SALES, get_sheet_config()["sales_worksheet"]
    else:
        columns, local, worksheet = MOVEMENT_COLUMNS, LOCAL_MOVEMENTS, get_sheet_config()["movements_worksheet"]

    if client:
        return read_ws(client, worksheet, columns)
    return read_local(local, columns)


def append_table(client, kind: str, row: dict) -> None:
    df = load_table(client, kind)
    df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    if kind == "ventas":
        columns, local, worksheet = SALES_COLUMNS, LOCAL_SALES, get_sheet_config()["sales_worksheet"]
    else:
        columns, local, worksheet = MOVEMENT_COLUMNS, LOCAL_MOVEMENTS, get_sheet_config()["movements_worksheet"]

    if client:
        write_ws(client, worksheet, df, columns)
    else:
        write_local(local, df)


def to_excel_bytes(inventory: pd.DataFrame, sales: pd.DataFrame, movements: pd.DataFrame) -> bytes:
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        inventory.to_excel(writer, sheet_name="inventario", index=False)
        sales.to_excel(writer, sheet_name="ventas", index=False)
        movements.to_excel(writer, sheet_name="movimientos", index=False)
    return output.getvalue()


def main():
    st.set_page_config(page_title=APP_TITLE, page_icon="🛍️", layout="wide")
    st.title("🛍️ Inventario Concha")
    st.caption("Inventario persistente con Google Sheets. Si no hay credenciales, usa modo local como respaldo.")

    client = get_google_client()
    storage_label = "Google Sheets" if client else "archivo local CSV"
    st.sidebar.success(f"Guardando en: {storage_label}")

    inventory = load_inventory(client)
    sales = load_table(client, "ventas")
    movements = load_table(client, "movimientos")

    tab_inv, tab_add, tab_sale, tab_export = st.tabs([
        "Inventario",
        "Agregar / editar pieza",
        "Registrar venta",
        "Exportar / respaldo",
    ])

    with tab_inv:
        st.subheader("Inventario actual")
        query = st.text_input("Buscar pieza", placeholder="Código, producto, color...")
        visible = inventory[inventory["activo"] == True].copy()
        if query:
            q = query.lower()
            visible = visible[
                visible["codigo"].str.lower().str.contains(q, na=False)
                | visible["producto"].str.lower().str.contains(q, na=False)
            ]
        visible["valor_total"] = visible["cantidad"] * visible["precio_unitario"]
        st.metric("Piezas disponibles", int(visible["cantidad"].sum()) if not visible.empty else 0)
        st.metric("Valor inventario visible", f"${visible['valor_total'].sum():,.2f}" if not visible.empty else "$0.00")
        st.dataframe(visible, use_container_width=True, hide_index=True)

    with tab_add:
        st.subheader("Agregar o editar pieza")
        ids = ["Nueva pieza"] + inventory["id"].tolist()
        selected_id = st.selectbox("Selecciona una pieza existente o crea una nueva", ids)

        if selected_id == "Nueva pieza":
            current = {"id": f"P{len(inventory)+1:04d}", "codigo": "", "producto": "", "cantidad": 0, "precio_unitario": 0.0, "activo": True}
        else:
            current = inventory[inventory["id"] == selected_id].iloc[0].to_dict()

        with st.form("product_form"):
            codigo = st.text_input("Código", value=str(current.get("codigo", "")))
            producto = st.text_input("Producto", value=str(current.get("producto", "")))
            cantidad = st.number_input("Cantidad", min_value=0, step=1, value=int(current.get("cantidad", 0)))
            precio = st.number_input("Precio unitario", min_value=0.0, step=10.0, value=float(current.get("precio_unitario", 0)))
            activo = st.checkbox("Activo / disponible", value=bool(current.get("activo", True)))
            nota = st.text_input("Nota del cambio", value="")
            submitted = st.form_submit_button("Guardar pieza")

        if submitted:
            before_qty = int(current.get("cantidad", 0)) if selected_id != "Nueva pieza" else 0
            before_price = float(current.get("precio_unitario", 0)) if selected_id != "Nueva pieza" else 0
            if selected_id == "Nueva pieza":
                new_row = {
                    "id": current["id"],
                    "codigo": codigo,
                    "producto": producto,
                    "cantidad": cantidad,
                    "precio_unitario": precio,
                    "activo": activo,
                    "fecha_creacion": now_str(),
                    "fecha_actualizacion": now_str(),
                }
                inventory = pd.concat([inventory, pd.DataFrame([new_row])], ignore_index=True)
                movement_type = "alta"
            else:
                idx = inventory.index[inventory["id"] == selected_id][0]
                inventory.loc[idx, ["codigo", "producto", "cantidad", "precio_unitario", "activo", "fecha_actualizacion"]] = [
                    codigo, producto, cantidad, precio, activo, now_str()
                ]
                movement_type = "edición"

            save_inventory(client, inventory)
            append_table(client, "movimientos", {
                "fecha": now_str(),
                "id": current["id"],
                "codigo": codigo,
                "producto": producto,
                "tipo_movimiento": movement_type,
                "cantidad_anterior": before_qty,
                "cantidad_nueva": cantidad,
                "precio_anterior": before_price,
                "precio_nuevo": precio,
                "nota": nota,
            })
            st.success("Pieza guardada correctamente.")
            st.rerun()

    with tab_sale:
        st.subheader("Registrar venta")
        available = inventory[(inventory["activo"] == True) & (inventory["cantidad"] > 0)].copy()
        if available.empty:
            st.info("No hay piezas disponibles para vender.")
        else:
            available["label"] = available["codigo"] + " — " + available["producto"] + " — disp: " + available["cantidad"].astype(str)
            selected_label = st.selectbox("Pieza vendida", available["label"].tolist())
            row = available[available["label"] == selected_label].iloc[0]
            with st.form("sale_form"):
                qty = st.number_input("Cantidad vendida", min_value=1, max_value=int(row["cantidad"]), step=1, value=1)
                price = st.number_input("Precio unitario de venta", min_value=0.0, step=10.0, value=float(row["precio_unitario"]))
                metodo = st.selectbox("Método de pago", ["Efectivo", "Transferencia", "Zelle", "Otro"])
                nota = st.text_input("Nota", value="")
                sold = st.form_submit_button("Guardar venta")
            if sold:
                idx = inventory.index[inventory["id"] == row["id"]][0]
                old_qty = int(inventory.loc[idx, "cantidad"])
                new_qty = old_qty - qty
                inventory.loc[idx, "cantidad"] = new_qty
                inventory.loc[idx, "fecha_actualizacion"] = now_str()
                save_inventory(client, inventory)
                append_table(client, "ventas", {
                    "fecha": now_str(),
                    "id": row["id"],
                    "codigo": row["codigo"],
                    "producto": row["producto"],
                    "cantidad_vendida": qty,
                    "precio_unitario": price,
                    "total": qty * price,
                    "metodo_pago": metodo,
                    "nota": nota,
                })
                append_table(client, "movimientos", {
                    "fecha": now_str(),
                    "id": row["id"],
                    "codigo": row["codigo"],
                    "producto": row["producto"],
                    "tipo_movimiento": "venta",
                    "cantidad_anterior": old_qty,
                    "cantidad_nueva": new_qty,
                    "precio_anterior": row["precio_unitario"],
                    "precio_nuevo": price,
                    "nota": nota,
                })
                st.success("Venta registrada y cantidad actualizada.")
                st.rerun()

    with tab_export:
        st.subheader("Exportar respaldo")
        excel_bytes = to_excel_bytes(inventory, sales, movements)
        st.download_button(
            "Descargar respaldo Excel",
            data=excel_bytes,
            file_name=f"respaldo_inventario_concha_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        st.write("Ventas")
        st.dataframe(sales, use_container_width=True, hide_index=True)
        st.write("Movimientos")
        st.dataframe(movements, use_container_width=True, hide_index=True)


if __name__ == "__main__":
    main()
