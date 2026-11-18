"""components phase: allocate BOM components to the routing's operations (CA02).

Only some rows get it (architecture.md 4.1): Create, layout allocates components (not PLT, which
needs a new BOM), and `Assign Components` not "No". Delete / change rows never do.
"""
from routing.layouts import select as layouts
from routing.model.enums import Action, OperationRole
from routing.model.result import StepResult
from routing.sap.screens import ca02, components
from routing.steps.base import Step
from routing.steps.production_version import routing_created_this_run, target_routing
from routing.steps.routing import single_routing

# Operation per unassigned component (first match wins), from SAP_automation/change_bom/routing.py:
#   packaging                                       -> 0030
#   lubricant AND the 0030 work center is YMHI(-1)  -> 0030
#   everything else                                 -> 0020
DEFAULT_OPERATION = "0020"
PACKAGING_OPERATION = "0030"
PACKAGING_WORDS = ("carton", "sheet", "bag", "silica", "bubble", "box")
LUBRICANT_WORDS = ("lubricant",)
LUBRICANT_0030_WORK_CENTERS = ("YMHI", "YMHI-1")


def planned_operation(description, op_0030_work_center):
    """(operation, reason) for an unassigned component."""
    text = (description or "").lower()
    if any(word in text for word in PACKAGING_WORDS):
        return PACKAGING_OPERATION, "packaging"
    if any(word in text for word in LUBRICANT_WORDS) and \
            (op_0030_work_center or "").strip().upper() in LUBRICANT_0030_WORK_CENTERS:
        return PACKAGING_OPERATION, f"lubricant, op 0030 = {op_0030_work_center}"
    return DEFAULT_OPERATION, ""


class AllocateComponents(Step):
    name, phase = "AllocateComponents", "components"

    def applies(self, row):
        request = row.request
        if request.action is Action.ASSIGN:                 # existing routing (UiPath main_bom_assignment)
            return True
        return (request.action is Action.CREATE and request.params.assign_components
                and layouts.layout_for(request).allocate_components)

    def plan(self, row, ctx):
        request, plan = row.request, row.plan
        if request.action is Action.ASSIGN:
            target, reason = single_routing(row, ctx.routings(request.material))
            if target is not None and target.deleted:
                target, reason = None, f"routing inactive {target.key}"
            if target is None:
                plan.skip[self.name] = reason
                return
            row.key, plan.target = target.key, target
        if target_routing(row, ctx) is None and not routing_created_this_run(row):
            plan.skip[self.name] = "no routing to allocate components to"
            return
        active = ctx.alt_boms(request.material)
        choice = request.params.alt_bom
        alt_boms = active if choice.all else [choice.number]
        if not alt_boms:
            plan.skip[self.name] = "no active alt BOM"
            return
        if not choice.all and choice.number not in active:
            plan.skip[self.name] = (f"alt BOM {choice.number} not active "
                                    f"(active: {', '.join(map(str, active)) or 'none'})")
            return
        plan.component_alt_boms = alt_boms

    def run(self, row, ctx):
        if row.key is None:
            return StepResult.failed("routing key unknown (routing phase not done)")
        sap, material = ctx.sap, row.request.material
        routings = ctx.routings(material)
        routing = target_routing(row, ctx)
        # a routing created in this run is not in Snowflake yet: its group has one routing more
        size = routings.group_size(row.key.group) + (0 if routings.get(row.key) else 1)
        sorting_op = routing.operation(OperationRole.SORTING) if routing and routing.operations else None
        op_0030 = sorting_op.work_center if sorting_op else row.request.params.sorting

        parts, notes = [], []
        for alt_bom in row.plan.component_alt_boms:
            note = ca02.open_routing(sap, row.key, size, ctx.plant)
            components.open_allocation(sap, alt_bom, len(ctx.alt_boms(material)))
            # as SAP_automation assign_components: pass 1 = rows planned for 0030, pass 2 = every
            # row still unassigned -> 0020; the table is read again before each pass
            assigned = {}
            for operation in (PACKAGING_OPERATION, DEFAULT_OPERATION):
                rows, warning = components.unassigned_components(sap)
                picked = [r for r, description in rows
                          if operation == DEFAULT_OPERATION or planned_operation(description, op_0030)[0] == operation]
                if picked:
                    components.assign(sap, picked, operation)
                    assigned[operation] = len(picked)
            notes += [n for n in (note, warning) if n]
            ca02.save(sap, f"components {row.key} B{alt_bom}")     # also when nothing was assigned
            done = ", ".join(f"{op}: {n}" for op, n in assigned.items()) or "nothing unassigned"
            parts.append(f"B{alt_bom} {done}")
        return StepResult.done("; ".join(parts) + (f" ({'; '.join(dict.fromkeys(notes))})" if notes else ""))
