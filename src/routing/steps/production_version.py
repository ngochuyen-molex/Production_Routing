"""pv phase: create / delete production versions in MM02."""
from routing.layouts import select as layouts
from routing.model.entities import ProductionVersion, Routing, next_version_number
from routing.model.enums import Action
from routing.model.result import StepResult
from routing.sap.screens import mm02
from routing.steps.base import Step


def routing_created_this_run(row):
    """CreateRouting is planned for this row and not skipped -> the key comes from the SAP screen."""
    return "CreateRouting" in row.plan.steps and "CreateRouting" not in row.plan.skip and not row.done("CreateRouting")


def target_routing(row, ctx):
    """The routing the row works on: from the routing phase, else Snowflake by key, else (routing
    created by this tool in an earlier run, not in Snowflake yet) rebuilt from its layout text."""
    if row.plan.target is not None:
        return row.plan.target
    if row.key is None:
        return None
    found = ctx.routings(row.request.material).get(row.key)
    if found is None and row.done("CreateRouting") and row.request.action is Action.CREATE:
        try:
            layout = layouts.layout_for(row.request)
            found = Routing(row.key, layouts.description(layout, row.request), "4")
        except ValueError:
            return None
    return found


class CreateProductionVersion(Step):
    """One version per wanted alt BOM that has none yet on the routing (ALL BOM = every active
    alt BOM; existing ones are skipped, so a partly done routing is completed, never duplicated)."""
    name, phase = "CreateProductionVersion", "pv"

    def applies(self, row):
        return row.request.action is Action.CREATE

    def plan(self, row, ctx):
        request, plan = row.request, row.plan
        choice = request.params.alt_bom
        active = ctx.alt_boms(request.material)
        wanted = active if choice.all else [choice.number]
        if not wanted:
            plan.skip[self.name] = "no active alt BOM"
            return
        if not choice.all and choice.number not in active:
            plan.warnings.append(f"alt BOM {choice.number} is not an active alt BOM ({active or 'none'})")

        routing = target_routing(row, ctx)
        if routing is None and not routing_created_this_run(row):
            plan.skip[self.name] = "no routing to attach the version to"
            return
        if routing is not None:
            if routing.is_trial:
                plan.skip[self.name] = f"trial routing {routing.key}, no production version"
                return
            versions = ctx.versions(request.material)
            plan.existing_versions = versions.on(routing.key)
            wanted = versions.missing(routing.key, wanted)
            if not wanted:
                plan.skip[self.name] = "versions exist: " + ", ".join(v.describe() for v in plan.existing_versions)
                return
            try:
                for alt_bom in wanted:
                    ProductionVersion.text_for(routing, alt_bom)
            except ValueError as error:
                plan.skip[self.name] = str(error)
                return
        plan.alt_boms = wanted

    def run(self, row, ctx):
        routing = target_routing(row, ctx) or Routing(row.key)
        if row.key is None or not routing.description:
            return StepResult.failed("routing key / description unknown (routing phase not done)")
        sap = ctx.sap
        mm02.open_versions(sap, row.request.material)
        on_screen = mm02.read_version_texts(sap)
        numbers = list(on_screen)
        by_text = {t.strip().upper(): v for v, t in on_screen.items() if t}
        created, existing, warnings = [], [], []
        for alt_bom in row.plan.alt_boms:
            text = ProductionVersion.text_for(routing, alt_bom)
            if text.strip().upper() in by_text:     # already in SAP (Snowflake behind) -> no duplicate
                existing.append(f"{by_text[text.strip().upper()]} (B{alt_bom})")
                continue
            version = next_version_number(numbers)
            warning = mm02.add_version(sap, version, text, row.key, alt_bom)
            numbers.append(version)
            created.append(f"{version} (B{alt_bom})")
            if warning:
                warnings.append(f"{version}: {warning}")
        message = mm02.close_and_save(sap, f"production versions of {row.request.material}")
        if not created:
            return StepResult.skipped("versions already in SAP: " + ", ".join(existing))
        text = ", ".join(created) + (f". Already in SAP: {', '.join(existing)}" if existing else "") \
            + (f". Check warning: {'; '.join(warnings)}" if warnings else "")
        return StepResult.done(f"{text}. {message}".strip(". "))


class DeleteProductionVersion(Step):
    """Delete the versions of the routing found by the routing phase (by version number, from
    Snowflake - not by text like UiPath)."""
    name, phase = "DeleteProductionVersion", "pv"

    def applies(self, row):
        return row.request.action is Action.DELETE

    def plan(self, row, ctx):
        if row.key is None:
            reason = row.plan.skip.get("InactivateRouting", "routing not found")
            row.plan.skip[self.name] = f"no routing ({reason})"
            return
        row.plan.existing_versions = ctx.versions(row.request.material).on(row.key)
        if not row.plan.existing_versions:
            row.plan.skip[self.name] = f"no production version on {row.key}"

    def run(self, row, ctx):
        sap = ctx.sap
        mm02.open_versions(sap, row.request.material)
        on_screen = set(mm02.read_versions(sap))
        deleted = []
        for version in row.plan.existing_versions:
            if version.version in on_screen:
                mm02.delete_version(sap, version.version, version.text)
                deleted.append(version.describe())
        if not deleted:
            mm02.close_and_save(sap, f"production versions of {row.request.material}")
            return StepResult.skipped("versions already gone in SAP")
        message = mm02.close_and_save(sap, f"production versions of {row.request.material}")
        return StepResult.done(f"deleted {', '.join(deleted)}. {message}".strip(". "))
