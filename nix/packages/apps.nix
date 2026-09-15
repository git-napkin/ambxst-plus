# Applications: terminal, launcher, control panels
{ pkgs }:

with pkgs; [
  # Terminal
  kitty
  tmux

  # Launcher
  fuzzel

  # Control panels (pavucontrol/blueman dropped — in-shell Sound/Bluetooth panels cover them)
  networkmanagerapplet
  easyeffects
  gradia

  # Icons
  kdePackages.breeze-icons
  hicolor-icon-theme
]
