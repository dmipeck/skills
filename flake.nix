{
  description = "skills";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-parts.url = "github:hercules-ci/flake-parts";
  };

  outputs =
    inputs@{ flake-parts, ... }:
    flake-parts.lib.mkFlake { inherit inputs; } {
      systems = [
        "x86_64-linux"
        "aarch64-linux"
        "x86_64-darwin"
        "aarch64-darwin"
      ];

      perSystem =
        { pkgs, ... }:
        let
          tools = with pkgs; [
            pre-commit
            gitleaks
            nixfmt
            editorconfig-checker
            # Nix
            statix
            deadnix
            nixd
            # skills-lock (npx skills check)
            nodejs
          ];
        in
        {
          devShells.default = pkgs.mkShell {
            packages = tools;
            shellHook = ''
              pre-commit install --hook-type pre-commit --hook-type \
                commit-msg --overwrite
            '';
          };
        };
    };
}
