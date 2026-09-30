def register_reactions(runner):
    context = runner.context

    def offend(owner, offender, severity):
        context.needs.increase(owner, "safety", severity * 0.2)
        grudges = owner.components.setdefault("grudges", {})
        grudges[offender.id] = grudges.get(offender.id, 0.0) + severity

    def on_tile_placed(entity, x, y, **_):
        owner_id = context.territory.owner_at(x, y)
        owner = context.entities.get(owner_id) if owner_id is not None else None

        if owner is not None and owner is not entity:
            offend(owner, entity, 1.0)
            context.territory.claim(x, y, entity.id, 0.5)
        else:
            context.territory.claim(x, y, entity.id, 1.0)

    def on_resource_taken(entity, x, y, **_):
        owner_id = context.territory.owner_at(x, y)
        owner = context.entities.get(owner_id) if owner_id is not None else None

        if owner is not None and owner is not entity:
            offend(owner, entity, 0.5)
        else:
            context.territory.claim(x, y, entity.id, 0.3)

    runner.events.on("tile_placed", on_tile_placed)
    runner.events.on("resource_taken", on_resource_taken)