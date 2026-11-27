"""Checks that must pass before the UiPath routing automation runs:
1. routing condition (does the routing already exist?)  -> SKIP / SKIP_REASON
2. alt BOM count                                        -> ALT_BOM_COUNT

ARCHIVED 2026-11-27: UiPath is no longer used for routing (`routing run` replaces it). Was
src/routing/pipelines/pre_uipath.py; restore it there (git mv) to use it again. The two checks
still run on their own: `routing check routing-condition FILE`, `routing check alt-bom FILE`.
"""
from routing.checks.alt_bom import check_alt_bom_count
from routing.checks.routing_condition import check_routing_exists, summary
from routing.core.config import PLANT
from routing.core.db import snowflake_session
from routing.core.excel import read_input, write_output


def pre_uipath_checks(df, conn=None, plant=PLANT):
    with snowflake_session(conn) as c:
        df = check_routing_exists(df, conn=c, plant=plant)
        df = check_alt_bom_count(df, conn=c, plant=plant)
    return df


def run(input_path, output_path=None, plant=PLANT):
    df = pre_uipath_checks(read_input(input_path), plant=plant)
    saved = write_output(df, output_path or input_path)
    print(f"Done. {len(df)} rows processed. Saved to: {saved}")
    print(summary(df))
    print(f"  Materials without active alt BOM: {(df['ALT_BOM_COUNT'] == 0).sum()}")
    return df
