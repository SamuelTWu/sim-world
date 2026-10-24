class Roster:
    def __init__(self):
        self.thinkers = {}
        self.needy = {}
        self.statused = {}
        self.snapped = {}
        self.owned = {}
        self.members = {}
        self.asleep = {}
        self.cache = None
        self.rebuilds = 0

    @staticmethod
    def reasons(entity):
        return (
            bool(entity.traits) or entity.task is not None,
            bool(entity.needs),
            bool(entity.statuses),
            entity.has_prop("snap_to_grid") and entity.prop("snap_to_grid") > 0,
            entity.owner is not None,
        )

    def sync(self, entity):
        if not entity.alive:
            self.drop(entity)
            return

        entity_id = entity.id
        thinks, needs, statuses, snaps, owned = self.reasons(entity)

        for group, present in ((self.thinkers, thinks), (self.needy, needs), (self.statused, statuses), (self.snapped, snaps), (self.owned, owned)):
            if present:
                if entity_id not in group:
                    group[entity_id] = entity
            elif entity_id in group:
                del group[entity_id]

        capable = thinks or needs or statuses or snaps or owned
        known = entity_id in self.members

        if capable and not known:
            self.members[entity_id] = entity

            if entity_id not in self.asleep:
                self.cache = None
        elif not capable and known:
            del self.members[entity_id]
            self.asleep.pop(entity_id, None)
            self.cache = None

    def drop(self, entity):
        entity_id = entity.id

        for group in (self.thinkers, self.needy, self.statused, self.snapped, self.owned, self.members):
            group.pop(entity_id, None)

        self.asleep.pop(entity_id, None)
        self.cache = None

    def sleep(self, entity):
        if entity.id in self.members and entity.id not in self.asleep:
            self.asleep[entity.id] = entity
            self.cache = None

    def wake(self, entity):
        if self.asleep.pop(entity.id, None) is not None:
            self.cache = None

    def visits(self, entity):
        return entity.id in self.members

    def is_asleep(self, entity):
        return entity.id in self.asleep

    def active_list(self):
        if self.cache is None:
            members, asleep = self.members, self.asleep
            self.cache = [members[entity_id] for entity_id in sorted(members) if entity_id not in asleep]
            self.rebuilds += 1

        return self.cache

    def ids(self, name):
        return sorted(getattr(self, name))

    def counts(self):
        return {"capable": len(self.members), "awake": len(self.members) - len(self.asleep), "asleep": len(self.asleep), "thinkers": len(self.thinkers), "needy": len(self.needy), "statused": len(self.statused)}