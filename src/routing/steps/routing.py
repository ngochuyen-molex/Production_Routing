"""Routing phase: create (CA01) and inactivate (CA02) routings."""
from routing.layouts import select as layouts
from routing.layouts.catalog import MACHINE_NAME
from routing.model.entities import Routing, RoutingKey
from routing.model.enums import Action
from routing.model.result import StepResult
from routing.sap.screens import ca01, ca02, operations
from routing.steps.base import Step

CREATE_STATUS = "4"         # production / released (python_migration.md 5)


def matching_routings(row, routings):
    """Routings the row means: the given group / counter, else the shared rule of
    checks/routing_condition (Routing.matches: resource = work center, tool / sorting in the text)."""
    request = row.request
    if request.key:
        found = routings.get(request.key)
        return [found] if found else []
    sorting = getattr(request.params, "sorting", "")
    return routings.matching(request.resource, request.tool, sorting)


class CreateRouting(Step):
    """CA01: copy a routing of the same material, type the layout's values, status 4, save."""
    name, phase = "CreateRouting", "routing"

    def applies(self, row):
        return row.request.action is Action.CREATE

    def plan(self, row, ctx):
        request, plan = row.request, row.plan
        routings = ctx.routings(request.material)

        existing = next(iter(matching_routings(row, routings)), None)
        if existing is not None:
            row.key, plan.target = existing.key, existing    # later phases use the existing routing
            plan.skip[self.name] = (f"routing inactive {existing.key}, untick the deletion flag"
                                    if existing.deleted else f"routing already exists {existing.key}")
            return

        layout = layouts.layout_for(request)
        plan.layout = layout.id
        missing = layouts.missing_inputs(layout, request)
        if missing:
            plan.skip[self.name] = f"missing {', '.join(missing)} for layout {layout.id}"
            return
        try:
            layouts.description(layout, request)
        except ValueError as error:
            plan.skip[self.name] = str(error)
            return

        if request.copy_from:                            # the user's choice in COPY_FROM_GROUP / _GC
            source = routings.get(request.copy_from)
            if source is None or not source.can_be_copied:
                plan.skip[self.name] = (f"COPY_FROM {request.copy_from} "
                                        + ("not found" if source is None else "is not status 4 / is flagged / is TRIAL"))
                return
        else:
            source = routings.copy_source(fits=lambda r: not layouts.check_copy_source(layout, r),
                                          resource=request.resource, needs_sorting=bool(request.params.sorting))
            if source is None:
                plan.skip[self.name] = "no routing of this material to copy from (status 4, not flagged, not TRIAL)"
                return
        plan.copy_from = source
        plan.warnings.extend(layouts.check_copy_source(layout, source))
        if not layout.verified:
            plan.warnings.append(f"layout {layout.id} not verified on SAP yet")

    def run(self, row, ctx):
        request, plan, sap = row.request, row.plan, ctx.sap
        layout = layouts.LAYOUTS[plan.layout]
        source = plan.copy_from.key

        ca01.start(sap, request.material, ctx.plant)
        ca01.choose_target_group(sap, source.group)
        ca01.choose_copy_source(sap, source, ctx.plant)
        ca01.choose_alt_bom(sap, request.params.alt_bom.number or 1)
        group, counter = ca01.fill_header(sap, layouts.description(layout, request), CREATE_STATUS)
        ca01.open_operations(sap)

        values = layouts.operation_values(layout, request)
        for value in values:
            if value.work_center:
                operations.set_work_center(sap, value.row, value.work_center)
        sap.enter()
        sap.raise_on_error("work centers")
        for value in values:
            if value.base_quantity is not None:
                operations.set_base_quantity(sap, value.row, value.base_quantity)
        for value in values:
            if value.details:
                details = [(field, operations.machine_name(sap, value.row) if v == MACHINE_NAME else v)
                           for field, v in value.details]
                operations.set_details(sap, value.row, details)

        message = ca02.save(sap, f"routing {group}/{counter}")
        row.key = RoutingKey(request.material, group, counter)
        # not in Snowflake yet: later phases (components, pv) use this in-memory routing
        row.plan.target = Routing(row.key, layouts.description(layout, request), CREATE_STATUS)
        return StepResult.done(f"{row.key} copied from {source}. {message}".strip())


class InactivateRouting(Step):
    """CA02: open the routing by group + counter, Header: deletion flag + status 1, save."""
    name, phase = "InactivateRouting", "routing"

    def applies(self, row):
        return row.request.action is Action.DELETE

    def plan(self, row, ctx):
        candidates = matching_routings(row, ctx.routings(row.request.material))
        active = [r for r in candidates if not r.deleted]
        if len(active) > 1:
            # e.g. PLT has no tool to tell routings apart: never guess which one to delete
            keys = ", ".join(str(r.key) for r in active)
            row.plan.skip[self.name] = f"{len(active)} routings match ({keys}), fill group / group counter"
            return
        target = active[0] if active else (candidates[0] if candidates else None)
        if target is None:
            row.plan.skip[self.name] = "routing not found"
            return
        row.key, row.plan.target = target.key, target
        if target.deleted:
            row.plan.skip[self.name] = f"already inactive {target.key}"

    def run(self, row, ctx):
        sap, key = ctx.sap, row.key
        size = ctx.routings(key.material).group_size(key.group)
        note = ca02.open_routing(sap, key, size, ctx.plant)
        ca02.open_header_details(sap)
        ca02.set_inactive(sap)
        message = ca02.save(sap, f"routing {key}")
        return StepResult.done(f"{key} inactive" + (f" ({note})" if note else "")
                               + (f". {message}" if message else ""))
