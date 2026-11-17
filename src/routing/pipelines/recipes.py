"""The only place that decides which steps a row gets (docs/architecture.md 4, 6.5)."""
from routing.model.enums import PHASES, Action
from routing.steps.components import AllocateComponents
from routing.steps.production_version import CreateProductionVersion, DeleteProductionVersion
from routing.steps.routing import CreateRouting, InactivateRouting

# Action -> steps; run in phase order (routing -> components -> pv -> opc). opc steps come next.
RECIPES = {
    Action.CREATE: [CreateRouting(), AllocateComponents(), CreateProductionVersion()],
    Action.DELETE: [InactivateRouting(), DeleteProductionVersion()],
}


def all_steps(recipes=RECIPES):
    seen = {}
    for steps in recipes.values():
        for step in steps:
            seen.setdefault(step.name, step)
    return list(seen.values())


def steps_for(row, phases=PHASES, recipes=RECIPES):
    """Steps of the row's action, in phase order, limited to `phases` and Step.applies()."""
    steps = [s for s in recipes.get(row.request.action, []) if s.phase in phases and s.applies(row)]
    return sorted(steps, key=lambda s: PHASES.index(s.phase))


def earlier_failed(row, step, recipes=RECIPES):
    """True when a step of an earlier phase of this row failed (now or in a previous run)."""
    for other in recipes.get(row.request.action, []):
        if PHASES.index(other.phase) >= PHASES.index(step.phase) or not other.applies(row):
            continue
        result = row.results.get(other.name)
        if result is not None and result.status.value == "Failed":
            return True
    return False
