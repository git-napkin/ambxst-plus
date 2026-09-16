{ pkgs ? import <nixpkgs> { } }:

let
  python = pkgs.python3.override {
    packageOverrides = import ./nix/packages/python-typesafe.nix { inherit pkgs; };
  };
  pythonEnv = python.withPackages (ps: [
    ps.cryptography
    ps.dbus-python
    ps.typesafe-sdk
  ]);
in
pkgs.mkShell {
  packages = with pkgs; [
    quickshell
    pythonEnv
    brightnessctl
    ddcutil
    grim
    slurp
    wl-clipboard
    wl-clip-persist
    imagemagick
    matugen
    power-profiles-daemon
    upower
    libnotify
    zbar
    zenity
    wtype
    ydotool
    wlsunset
    inetutils
    jq
    sqlite
    fprintd
    pam
    qt6.qtbase
    qt6.qtsvg
    qt6.qttools
    qt6.qtwayland
    qt6.qtdeclarative
    qt6.qtimageformats
    kdePackages.qtmultimedia
    kdePackages.qtshadertools
    kdePackages.syntax-highlighting
  ];

  shellHook = ''
    export QML2_IMPORT_PATH="${pkgs.qt6.qtdeclarative}/qml:$QML2_IMPORT_PATH"
    export QML_IMPORT_PATH="$QML2_IMPORT_PATH"
    echo "Ambxst[+] dev environment loaded."
  '';
}
