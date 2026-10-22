---
name: flake-parts-modules
description: >-
  Author flake-parts modules that activate on inclusion. Use when adding
  or editing flake.nixosModules, flake.homeModules, or other flake-parts
  modules, or when a module is gated behind an enable option.
---

# Flake-parts modules

This rule applies specifically to flake-parts modules.

Modules shouldn't be gated behind .enable pattern, the inclusion of the module implies activation.

Importing `flake.*Modules.<name>` is the switch. Do not add `mkEnableOption`, `cfg.enable`, or `lib.mkIf cfg.enable` whose only job is to opt into that module. Hosts that want the behavior list the module. Hosts that do not, omit it.

`services.*.enable = true` inside the module is the upstream switch the module turns on. Settings on an imported module stay. A flag that selects a role inside an already-active module stays. An option that means "turn this module on" does not.

Inclusion:

```nix
{
  flake.nixosModules.printing = _: {
    services.printing.enable = true;
  };
}
```

Activation gate. Do not add:

```nix
options.example.enable = lib.mkEnableOption "example";
config = lib.mkIf config.example.enable { };
```
