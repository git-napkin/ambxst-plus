# System tools and utilities
{ pkgs }:

let
  pythonEnv = pkgs.python3.withPackages (ps:
    let
      jevPkgs = import ./python-typesafe.nix {
        inherit pkgs;
        pythonPackages = ps;
      };
    in [
      ps.cryptography
      ps.dbus-python
      jevPkgs.typesafe-sdk
    ]
  );
in
with pkgs; [
  brightnessctl
  curl
  ddcutil
  fontconfig
  glib
  grim
  imagemagick
  jq

  libnotify
  matugen
  pythonEnv
  power-profiles-daemon
  slurp
  sqlite
  upower
  wl-clip-persist
  wl-clipboard
  wlsunset
  wtype
  ydotool
  at-spi2-core
  xdg-utils
  zbar
  zenity
  inetutils
  adw-gtk3

   # Fingerprint authentication
   fprintd
   pam
  ]
