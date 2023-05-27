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
          tornado
          requests
          pynvim
          intervaltree
          beautifulsoup4
        ]);
        remote = pkgs.runCommand "remote.vim" {} ''
            ${python}/bin/python3.10 ${./export.py} ${./.} airlatex > $out
        '';
      in
      {
        # A Nix environment with your specified packages
        devShell = pkgs.mkShell {
          buildInputs = [ pkgs.neovim python pkgs.sqlite ];
        };

        # let g:python3_host_prog = '/home/dylan/air/bin/python3'
        packages = rec {
          airlatex = pkgs.writeShellScriptBin "airlatex" ''
            PATH=$PATH:${pkgs.sqlite}/bin ${pkgs.neovim}/bin/nvim \
                -c "let g:python3_host_prog='${python}/bin/python3.10'" \
                -c "set runtimepath+=${./.}" \
                -c "source ${remote}" \
                -c AirLatex
          '';
          default = airlatex;
        };
      });
}

