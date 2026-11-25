"""Routing phase: create (CA01) and inactivate (CA02) routings."""
from routing.layouts import select as layouts
from routing.layouts.catalog import MACHINE_NAME
from routing.model.entities import Routing, RoutingKey, is_trial_resource
from routing.model.enums import Action
from routing.model.result import StepResult
from routing.sap import elements as el
from routing.sap.screens import ca01, ca02, operations
from routing.sap.session import SapError
from routing.steps.base import Step

CREATE_STATUS = "4"         # production / released (README.md Background, decisions)


def matching_routings(row, routings):
    """Routings the row means: the given group / counter, else the shared rule of
    checks/routing_condition (Routing.matches: resource = work center, tool / sorting in the text)."""
    request = row.request
    if request.key:
        found = routings.get(request.key)
        return [found] if found else []
    sorting = getattr(request.params, "sorting", "")
    return routings.matching(request.resource, request.tool, sorting)


def single_routing(row, routings):
    """(routing, None) when the row means exactly one routing, else (None, reason to skip).
    Several active matches are never guessed (PLT has no tool to tell them apart)."""
    candidates = matching_routings(row, routings)
    active = [r for r in candidates if not r.deleted]
    if len(active) > 1:
        keys = ", ".join(str(r.key) for r in active)
        return None, f"{len(active)} routings match ({keys}), fill group / group counter"
    target = active[0] if active else (candidates[0] if candidates else None)
    if target is None:
        return None, "routing not found"
    return target, None


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

        needs_sorting = bool(request.params.sorting)
        shape = "with a YMHI sorting step" if needs_sorting else "without a YMHI sorting step"
        kind = "trial routing" if is_trial_resource(request.resource) else "normal (not TRIAL) routing"
        if request.copy_from:                            # the user's choice in COPY_FROM_GROUP / _GC
            source = routings.get(request.copy_from)
            if source is None or not source.can_be_copied_for(request.resource):
                plan.skip[self.name] = (f"COPY_FROM {request.copy_from} "
                                        + ("not found" if source is None
                                           else f"must be a {kind}, status 4, not flagged"))
                return
            if source.has_sorting != needs_sorting:      # rows would shift: never copy the wrong shape
                plan.skip[self.name] = f"COPY_FROM {request.copy_from} must be a routing {shape}"
                return
        else:
            source = routings.copy_source(fits=lambda r: not layouts.check_copy_source(layout, r),
                                          resource=request.resource, needs_sorting=needs_sorting,
                                          sorting=request.params.sorting)
            if source is None:
                plan.skip[self.name] = (f"no {kind} of this material to copy from {shape} "
                                        "(status 4, not flagged)")
                return
        plan.copy_from = source
        if ("YMHI" in source.description.upper()) != source.has_sorting:
            plan.warnings.append(f"copy source {source.key}: name and operations disagree about YMHI "
                                 f"('{source.description}'); the operations were used")
        plan.warnings.extend(layouts.check_copy_source(layout, source))
        if not layout.verified:
            plan.warnings.append(f"layout {layout.id} not verified on SAP yet")

    def run(self, row, ctx):
        request, plan, sap = row.request, row.plan, ctx.sap
        layout = layouts.LAYOUTS[plan.layout]
        source = plan.copy_from.key

        ca01.start(sap, request.material, ctx.plant)
        ca01.choose_target_group(sap, source.group)
        note = ca01.choose_copy_source(sap, source, len(ctx.routings(request.material).routings), ctx.plant)
        # BOM popup while copying: the row's alt BOM, for ALL BOM the first active one
        ca01.choose_alt_bom(sap, request.params.alt_bom.number or next(iter(ctx.alt_boms(request.material)), 1))
        text = layouts.description(layout, request)
        group, counter = ca01.fill_header(sap, text, CREATE_STATUS)
        ca01.open_operations(sap)                # fills a missing setup (1 H) if SAP asks

        values = layouts.operation_values(layout, request)
        for value in values:
            if value.work_center:
                operations.set_work_center(sap, value.row, value.work_center)
        sap.enter()
        # SAP may ask for the setup here too (row 2 of add_routing_test, STP 5051070099, 2026-11-19)
        operations.fill_missing_setups(sap)
        sap.raise_on_error("work centers")
        if not sap.exists(el.OPERATION_TABLE):
            raise SapError(f"Operation overview not shown after the work centers ({sap.where()})")
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
        row.plan.target = Routing(row.key, text, CREATE_STATUS)
        text_done = f"{row.key} copied from {source}" + (f" ({note})" if note else "")
        return StepResult.done(f"{text_done}. {message}" if message else text_done)


class InactivateRouting(Step):
    """CA02: open the routing by group + counter, Header: deletion flag + status 1, save."""
    name, phase = "InactivateRouting", "routing"

    def applies(self, row):
        return row.request.action is Action.DELETE

    def plan(self, row, ctx):
        target, reason = single_routing(row, ctx.routings(row.request.material))
        if target is None:
            row.plan.skip[self.name] = reason
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
