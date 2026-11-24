{
  description = "chillpill-shell";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    home-manager.url = "github:nix-community/home-manager";
    qml-niri = {
      url = "github:imiric/qml-niri/main";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs = { self, nixpkgs, home-manager, qml-niri }:
    let
      system = "x86_64-linux";
      pkgs = nixpkgs.legacyPackages.${system};
      qmlNiri = qml-niri.packages.${system}.default;
    in {
      packages.${system}.default = pkgs.callPackage ./default.nix { qml-niri = qmlNiri; };

      homeManagerModules.default = { config, lib, pkgs, ... }@args:
        import ./modules/chillpill-shell.nix (args // { qml-niri = qmlNiri; });
    };
}
