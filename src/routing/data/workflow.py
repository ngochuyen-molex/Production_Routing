"""OpCenter (SQL Server) workflow queries."""
import pandas as pd

from routing.core.db import mssql_conn

STEP_COLUMNS = [
    "MaterialKey", "WorkflowName", "WorkflowRevision", "ERPRouteRevision", "Status",
    "WorkflowDescription", "StepName", "Xlocation", "Ylocation", "RouteStepId",
    "RouteStepName", "Sequence", "ERPRouteName", "ToSpec", "IsLastStep",
]


def fetch_workflow_steps(workflow_names):
    """Steps of the current revision of each workflow, in sequence order (one row per step)."""
    if not workflow_names:
        return pd.DataFrame(columns=STEP_COLUMNS)

    placeholders = ",".join(["?"] * len(workflow_names))
    query = f"""
SELECT
    LEFT(wfb.WorkflowName, CHARINDEX('-', wfb.WorkflowName + '-') - 1) AS MaterialKey,
    wfb.WorkflowName,
    wf.WorkflowRevision,
    erp.ERPRouteRevision,
    erp.Status,
    wf.Description AS WorkflowDescription,
    ws.WorkflowStepName AS StepName,
    ws.Xlocation,
    ws.Ylocation,
    ws.RouteStepId,
    rs.Name AS RouteStepName,
    ws.Sequence,
    erb.ERPRouteName,
    LEAD(ws.WorkflowStepName) OVER (
        PARTITION BY wfb.WorkflowName
        ORDER BY ws.Sequence
    ) AS ToSpec,
    ws.IsLastStep
FROM [STDS].[EXCRSCh].Workflow wf
INNER JOIN [STDS].[EXCRSCh].WorkflowBase wfb WITH (NOLOCK)
    ON wf.WorkflowId = wfb.RevOfRcdId
LEFT JOIN [STDS].[EXCRSCh].WorkflowStep ws WITH (NOLOCK)
    ON ws.WorkflowId = wf.WorkflowId
LEFT JOIN [STDS].[EXCRSCh].RouteStep rs WITH (NOLOCK)
    ON rs.RouteStepId = ws.RouteStepId
LEFT JOIN [STDS].[EXCRSCh].ERPRoute erp WITH (NOLOCK)
    ON erp.ERPRouteId = CASE
        WHEN wf.ERPRouteId = '0000000000000000' THEN (
            SELECT eb.RevOfRcdId
            FROM [STDS].[EXCRSCh].ERPRouteBase eb
            WHERE eb.ERPRouteBaseId = wf.ERPRouteBaseId
        )
        ELSE wf.ERPRouteId
    END
LEFT JOIN [STDS].[EXCRSCh].ERPRouteBase erb WITH (NOLOCK)
    ON erb.ERPRouteBaseId = erp.ERPRouteBaseId
WHERE wfb.WorkflowName IN ({placeholders})
ORDER BY wfb.WorkflowName, ws.Sequence;
    """

    with mssql_conn() as conn:
        return pd.read_sql(query, conn, params=list(workflow_names))
