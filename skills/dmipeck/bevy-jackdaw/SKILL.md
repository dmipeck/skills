---
name: bevy-jackdaw
description: >-
  Jackdaw scene rules for Bevy. Applies when editing .bsn files or
  loading scenes with Jackdaw.
---

# Bevy Jackdaw

**Design data** is hierarchy, which components an entity has, default field
values, relationships, and asset paths. **Behavior** is systems, queries, and
simulation. Call this design data. Do not call it data-oriented.

Design data lives in a `.bsn` file whenever the app can load one. `bsn!`
holds only a value a file cannot express. A refactor that finds design data
in Rust moves it into `.bsn`. Do not add a `.bsn` file nothing loads. Behavior
stays in Rust. Field values in `.bsn` override `#[require]` defaults.

If a `.bsn` loader is already registered, leave it alone. If none is, add
`jackdaw_runtime` and point the user at the Jackdaw editor to author the
scene. Do not launch the editor. Register `JackdawPlugin` after
`DefaultPlugins` (tuple order below is that order) and spawn a
`JackdawSceneRoot`:

```rust
App::new()
    .add_plugins((DefaultPlugins, jackdaw_runtime::JackdawPlugin))
    .add_systems(Startup, setup)
    .run();

fn setup(mut commands: Commands, assets: Res<AssetServer>) {
    commands.spawn(JackdawSceneRoot(assets.load("scene.bsn")));
}
```

Use the `jackdaw_runtime` release that matches the app's Bevy version.
