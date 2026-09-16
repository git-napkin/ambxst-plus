# System tools and utilities
{ pkgs }:

let
  python = pkgs.python3.override {
    packageOverrides = import ./python-typesafe.nix { inherit pkgs; };
  };
  pythonEnv = python.withPackages (ps: [
    ps.cryptography
    ps.dbus-python
    ps.typesafe-sdk
  ]);
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
