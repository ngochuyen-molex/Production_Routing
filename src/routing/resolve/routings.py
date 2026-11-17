"""Snowflake rows -> entities (MaterialRoutings, MaterialVersions). The rules themselves live on
the entities (model/entities.py); this module only loads and converts."""
from collections import defaultdict

import pandas as pd

from routing.core.clean import from_sap_matnr
from routing.data import bom as bom_data
from routing.data import production_version as pv_data
from routing.data import routing as routing_data
from routing.model.entities import (MaterialRoutings, MaterialVersions, Operation, ProductionVersion,
                                    Routing, RoutingKey)


def _text(value):
    return "" if value is None or (not isinstance(value, str) and pd.isna(value)) else str(value).strip()


def _counter(value):
    return _text(value).removesuffix(".0").lstrip("0") or "0"


def load(conn, materials, plant):
    """{material: MaterialRoutings} with status and operations (planner)."""
    return routings_from_operations(routing_data.routing_operations(conn, materials, plant), materials)


def routings_from_operations(df, materials=()):
    """data.routing.routing_operations rows (one per operation) -> {material: MaterialRoutings}."""
    grouped = defaultdict(list)
    if not df.empty:
        df = df.assign(MATERIAL=df["MATNR"].map(from_sap_matnr), COUNTER=df["GROUP_COUNTER"].map(_counter))
        for (material, group, counter), ops in df.groupby(["MATERIAL", "ROUTING_GROUP", "COUNTER"], sort=True):
            first = ops.iloc[0]
            operations = tuple(
                Operation(number=_text(op.OPERATION_NUMBER), control_key=_text(op.CONTROL_KEY),
                          work_center=_text(op.WORK_CENTER),
                          base_quantity=None if pd.isna(op.BASE_QUANTITY) else float(op.BASE_QUANTITY))
                for op in ops.sort_values("OPERATION_NUMBER").itertuples() if _text(op.OPERATION_NUMBER))
            grouped[material].append(Routing(
                key=RoutingKey(material, _text(group), counter), description=_text(first.ROUTING_DESCRIPTION),
                status=_text(first.ROUTING_STATUS), deleted=_text(first.DELETION_FLAG) == "X",
                operations=operations))
    return _by_material(grouped, materials)


def routings_from_resources(df, materials=()):
    """data.routing.routings_with_resource rows (one per work center) -> {material: MaterialRoutings}.
    Operations carry only the work center (enough for Routing.matches)."""
    grouped = defaultdict(list)
    if not df.empty:
        df = df.assign(MATERIAL=df["MATNR"].map(from_sap_matnr), COUNTER=df["GROUP_COUNTER"].map(_counter))
        for (material, group, counter), rows in df.groupby(["MATERIAL", "ROUTING_GROUP", "COUNTER"], sort=False):
            first = rows.iloc[0]
            grouped[material].append(Routing(
                key=RoutingKey(material, _text(group), counter),
                description="" if first.ROUTING_DESCRIPTION is None else str(first.ROUTING_DESCRIPTION),
                deleted=_text(first.DELETION_FLAG) == "X",
                operations=tuple(Operation(number="", work_center=_text(wc)) for wc in rows["RESOURCE"])))
    return _by_material(grouped, materials)


def versions_from_frame(df, materials=()):
    """data.production_version.by_routing rows -> {material: MaterialVersions}."""
    grouped = defaultdict(list)
    for row in df.itertuples():
        alt_bom = _counter(row.ALT_BOM)
        if not alt_bom.isdigit():
            continue
        material = _text(row.MATERIAL)
        grouped[material].append(ProductionVersion(
            material=material, version=_text(row.PRODUCTION_VERSION),
            routing=RoutingKey(material, _text(row.ROUTING_GROUP), _counter(row.GROUP_COUNTER)),
            alt_bom=int(alt_bom), text=_text(row.DESCRIPTION), locked=_text(row.LOCK_STATUS) != ""))
    names = dict.fromkeys([*materials, *grouped])
    return {m: MaterialVersions(m, tuple(grouped.get(m, []))) for m in names}


def load_versions(conn, materials, plant):
    return versions_from_frame(pv_data.by_routing(conn, materials, plant), materials)


def load_alt_boms(conn, materials, plant):
    """{material: [active alt BOM numbers, sorted]} - the real numbers, not the count."""
    df = bom_data.alt_bom_numbers(conn, materials, plant)
    numbers = defaultdict(set)
    for row in df.itertuples():
        value = _counter(row.ALT_BOM)
        if value.isdigit():
            numbers[from_sap_matnr(row.MATNR)].add(int(value))
    return {m: sorted(numbers.get(m, ())) for m in dict.fromkeys([*materials, *numbers])}


def _by_material(grouped, materials):
    names = dict.fromkeys([*materials, *grouped])
    return {m: MaterialRoutings(m, tuple(grouped.get(m, []))) for m in names}
