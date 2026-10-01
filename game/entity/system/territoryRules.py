def register_territory_rules(runner):
    context = runner.context

    def handle(entity, x, y, own, contest, severity):
        owner_id = context.territory.owner_at(x, y)
        owner = context.entities.get(owner_id) if owner_id is not None else None

        if owner is not None and owner is not entity:
            runner.events.emit("trespass", owner=owner, offender=entity, x=x, y=y, severity=severity)

            if contest > 0:
                context.territory.claim(x, y, entity.id, contest)
        else:
            context.territory.claim(x, y, entity.id, own)

    runner.events.on("tile_placed", lambda entity, x, y, **_: handle(entity, x, y, 1.0, 0.5, 1.0))
    runner.events.on("resource_taken", lambda entity, x, y, **_: handle(entity, x, y, 0.3, 0.0, 0.5))