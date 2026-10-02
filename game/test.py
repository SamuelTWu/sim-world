from .entity.entity import Entity, Vec3, StatusEffect
from .entity.system.needSystem import Need
from .entity.system.memorySystem import Memory
from .entity.system.relationshipSystem import Relationship


def assert_equal(actual, expected, label):
    if actual != expected:
        raise AssertionError(f"{label}: expected {expected!r}, got {actual!r}")


def test_complete_serialization():
    entity = Entity(
        id=42,
        position=Vec3(12.5, 24.75, 1.0),
        sprite_id="worker",
        name="worker",
        kind="pixel",
        blueprint_name="worker",
        owner=7,
        alive=True,
        visible=True,
        age=18.5,
        health=7.5,
        max_health=10.0,
        energy=3.25,
        max_energy=5.0,
        home=Vec3(8.0, 16.0, 0.0),
        task_score=0.73,
        traits={
            "roam": {"speed": 1.5, "reach": 120.0, "candidates": 4},
            "react": {"rules": [{"on": "timer", "do": "signal"}]},
        },
        props={
            "max_speed": 1.5,
            "mass": 2.0,
            "flammable": 0.25,
        },
        tags={"worker", "friendly"},
        inventory={
            "wood": 12.0,
            "food": 3.5,
        },
        statuses=[
            StatusEffect("slow", 4.0, 0.5, source=9, age=1.25),
        ],
        needs={
            "hunger": Need("hunger", value=0.65, rate=0.1, minimum=0.0, maximum=1.0),
            "safety": Need("safety", value=0.2, rate=-0.05, minimum=0.0, maximum=1.0),
        },
        components={
            "heading": 1.25,
            "grudges": {9: 2.5},
            "react_state": {
                0: {"clock": 1.5, "ready": 20.0},
            },
        },
    )

    memory = Memory(
        type="seen_enemy",
        data={"entity_id": 9, "distance": 32.5},
        strength=0.8,
        importance=0.6,
        age=2.0,
    )

    relationship = Relationship(
        source=42,
        target=9,
        trust=0.25,
        fear=0.8,
        affection=0.1,
        resentment=0.4,
        familiarity=0.7,
    )

    entity_data = entity.to_dict()
    restored = Entity.from_dict(entity_data)

    assert_equal(restored.to_dict(), entity_data, "Entity serialization")

    memory_data = memory.to_dict()
    restored_memory = Memory.from_dict(memory_data)

    assert_equal(restored_memory.to_dict(), memory_data, "Memory serialization")

    relationship_data = relationship.to_dict()
    restored_relationship = Relationship.from_dict(relationship_data)

    assert_equal(restored_relationship.to_dict(), relationship_data, "Relationship serialization")

    assert_equal(restored.id, 42, "Entity ID")
    assert_equal(restored.owner, 7, "Entity owner")
    assert_equal(restored.position.to_dict(), {"x": 12.5, "y": 24.75, "z": 1.0}, "Entity position")
    assert_equal(restored.home.to_dict(), {"x": 8.0, "y": 16.0, "z": 0.0}, "Entity home")
    assert_equal(restored.tags, {"worker", "friendly"}, "Entity tags")
    assert_equal(restored.needs["hunger"].value, 0.65, "Need value")
    assert_equal(restored.statuses[0].source, 9, "Status source")
    assert_equal(restored.components["grudges"], {9: 2.5}, "Component state")

    print("PASS: Complete persistent-state serialization round-trip")


def main():
    print("Starting")
    test_complete_serialization()
    print("All tests passed")


if __name__ == "__main__":
    main()
