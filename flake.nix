{
  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs/nixos-unstable";
  };

  outputs = {
    nixpkgs,
    flake-utils,
    ...
  }:
    flake-utils.lib.eachDefaultSystem (system: let
      pkgs = import nixpkgs {inherit system;};
    in {
      devShells.default = pkgs.mkShell {
        shellHook = ''
          export LD_LIBRARY_PATH=${pkgs.lib.makeLibraryPath (with pkgs; [
            libGL
            libz
            glib
            stdenv.cc.cc
          ])}
        '';
        packages = with pkgs; [
          uv
          tesseract
        ];
      };
    });
}
