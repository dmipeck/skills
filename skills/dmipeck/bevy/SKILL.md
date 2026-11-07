---
name: bevy
description: >-
  Bevy development rules. Applies when writing or reviewing Bevy code.
---

# Bevy

Apply these rules when writing or reviewing Bevy code. Ordinary Bevy API
knowledge is assumed. Scene files are `bevy-jackdaw`.

## Components

This is the cheat book rule. Split a component when systems access its fields
independently. Keep fields together when every reader uses them together
(`Transform`).

```rust
#[derive(Component)]
struct Health(u32);

#[derive(Component)]
struct Velocity(Vec3);
```

Movement reads `Transform` and `Velocity`. Damage reads `Health`. Health stays
off `Velocity`. Leave a struct whole while every reader uses all of it. Add a
shared component for a second entity kind only once that kind exists.

A marker component (`Player`, `Enemy`) selects entities. It carries no data.
A new variant of behavior is a marker plus its own system, not a `kind` enum
or `bool` with a branch inside one system.

When a component is meaningless without another, require it. Values supplied
at spawn override those defaults. Do not require pieces for a later feature.

```rust
#[derive(Component)]
#[require(Health)]
struct Enemy;
```

## Resources

Engine resources (`Time`, `Assets`, input) stay as Bevy provides them.

A true singleton, such as the screen or the local player, may be a resource.
Keep it thin. Point it at components when that is the natural home of the
data. A resource may hold its own value. `Screen(Entity)` is not mandatory.

When a resource overreaches, break it up. Extract any element that can live
on an entity or in a component. Inventory selection is the local player's
component. The screen resource keeps the dimensions. A new resource needs its
reason in the commit or PR message. That message is the refactor plan. Do not
put the plan in a code comment.

```rust
#[derive(Resource)]
struct Screen {
    width: f32,
    height: f32,
}

#[derive(Component)]
struct SelectedSlot(usize);
```

## Systems

A system has one job and takes only the data that job uses. Structural
changes in a normal system, including a rare despawn, go through `Commands`.
An exclusive `&mut World` system is for bulk structural work (map load, save)
or for running another schedule.

Physics, AI, gameplay movement, and gameplay spawn or despawn run in
`FixedUpdate`. Camera, animation, UI, and VFX run in `Update`. Sample
simulation input in `PreUpdate` and store it for `FixedUpdate` to read.
`just_pressed` updates once per frame, so it is unreliable inside
`FixedUpdate`.

App flow (menu, loading, pause, mode) is `States` with `in_state`, `OnEnter`,
and `OnExit`. Configure a system set on both `Update` and `FixedUpdate` when
both schedules need it. Per-entity mode is a marker component. `States` does
not hold game data. Do not start a system with `if app_mode == ...` on a
resource.

## Change detection

Filter reaction systems with `Changed` or `Added`. A helper takes `&T` unless
it writes. A `&mut T` parameter marks the component changed even when the
function writes nothing. When a write would store the same value and another
system reacts, compare first.

## Messages and observers

Sequence-sensitive work (gameplay, simulation) communicates with `Message`
(`MessageWriter` / `MessageReader`). Systems read messages at their place in
the schedule.

```rust
#[derive(Message)]
struct Damage {
    target: Entity,
    amount: u32,
}

fn hit(mut damage: MessageWriter<Damage>, hurt: Query<Entity, With<Hurt>>) {
    for target in &hurt {
        damage.write(Damage { target, amount: 1 });
    }
}

fn apply(mut damage: MessageReader<Damage>, mut health: Query<&mut Health>) {
    for Damage { target, amount } in damage.read() {
        let Ok(mut hp) = health.get_mut(target) else {
            continue;
        };
        hp.0 = hp.0.saturating_sub(*amount);
    }
}
```

An observer in sequence-sensitive code is design glue. It writes a `Message`,
or updates a local binding authored for that interaction. The simulation
stays in the system that reads the `Message`.

UI and other work that does not care about order may use observers liberally.
Those observers may contain the reaction.

`Event` is the observer trigger. It is not the channel between systems.
