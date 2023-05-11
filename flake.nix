{
  description = "AirLatex as Hermetic package";

  inputs.flake-utils.url = "github:numtide/flake-utils";
  inputs.nixpkgs.url = "github:NixOS/nixpkgs";

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = import nixpkgs {
          inherit system;
        };

        python = pkgs.python310.withPackages (ps: with ps; [
          # Python packages from PyPI
          keyring
          tornado
          requests
          pynvim
          intervaltree
        ]);
      in
      {
        # A Nix environment with your specified packages
        devShell = pkgs.mkShell {
          buildInputs = [ pkgs.neovim python pkgs.sqlite ];
        };

        # let g:python3_host_prog = '/home/dylan/air/bin/python3'
        packages = rec {
          airlatex = pkgs.writeShellScriptBin "airlatex" ''
            PATH=$PATH:${pkgs.sqlite}/bin ${pkgs.neovim}/bin/nvim -c "let g:python3_host_prog='${python}/bin/python3.10'" -c AirLatex
          '';
          default = airlatex;
        };
      });
}

