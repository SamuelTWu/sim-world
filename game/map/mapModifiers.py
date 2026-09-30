MODIFIERS = {
    "scale": (1.0, lambda a, b: a * b),
    "offset": (0.0, lambda a, b: a + b),
    "contrast": (1.0, lambda a, b: a * b),
    "bias": (0.0, lambda a, b: a + b),
}

def resolve_modifiers(map_object, tag_modifiers):
    result = {name: default for name, (default, _) in MODIFIERS.items()}

    for tag in ["all", *sorted(map_object.tags), map_object.name]:
        for name, value in tag_modifiers.get(tag, {}).items():
            result[name] = MODIFIERS[name][1](result[name], value)

    return result

def apply_post_modifiers(map_object, modifiers):
    contrast, bias = modifiers["contrast"], modifiers["bias"]

    if contrast == 1.0 and bias == 0.0:
        return

    for y in range(map_object.height):
        for x in range(map_object.width):
            map_object.set(x, y, max(0.0, min(1.0, 0.5 + (map_object.get(x, y) - 0.5) * contrast + bias)))