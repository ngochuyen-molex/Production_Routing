"""The interface every step follows, and the shared resources of one run."""
from routing.core.config import PLANT
from routing.core.db import snowflake_conn
from routing.resolve import routings as routing_resolve


class Context:
    """Shared resources of one run. Snowflake and SAP are opened only when first used."""

    def __init__(self, plant=PLANT, dry_run=False, slow=False, sf=None, sap=None):
        self.plant, self.dry_run, self.slow = plant, dry_run, slow
        self._sf, self._sap = sf, sap
        self._owns_sf = sf is None
        self._routings, self._versions, self._alt_boms = {}, {}, {}

    @property
    def sf(self):
        if self._sf is None:
            self._sf = snowflake_conn()
        return self._sf

    @property
    def sap(self):
        if self.dry_run:
            raise RuntimeError("dry run: SAP must not be used")
        if self._sap is None:
            from routing.sap.session import SapSession
            self._sap = SapSession.connect(slow=self.slow)
        return self._sap

    def load_routings(self, materials):
        """Read all routings of these materials from Snowflake in one go (planner)."""
        missing = [m for m in dict.fromkeys(materials) if m not in self._routings]
        if missing:
            self._routings.update(routing_resolve.load(self.sf, missing, self.plant))

    def routings(self, material):
        """MaterialRoutings of one material."""
        self.load_routings([material])
        return self._routings[material]

    def versions(self, material):
        """MaterialVersions of one material (production versions still in SAP)."""
        if material not in self._versions:
            self._versions.update(routing_resolve.load_versions(self.sf, [material], self.plant))
        return self._versions[material]

    def alt_boms(self, material):
        """Active alternative BOM numbers of one material, e.g. [1, 2, 3]."""
        if material not in self._alt_boms:
            self._alt_boms.update(routing_resolve.load_alt_boms(self.sf, [material], self.plant))
        return self._alt_boms[material]

    def close(self):
        if self._owns_sf and self._sf is not None:
            self._sf.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


class Step:
    name = ""           # also the result column: RESULT_<name>
    phase = ""          # "routing" | "components" | "pv" | "opc"

    def applies(self, row):
        """Does this step belong to the row at all?"""
        return True

    def plan(self, row, ctx):
        """Snowflake only: fill row.plan; put a reason in row.plan.skip[self.name] to skip. No SAP."""

    def run(self, row, ctx):
        """Do the work; return a StepResult. Raise on errors (the runner records them)."""
        raise NotImplementedError
