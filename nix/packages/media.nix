# Media packages: video, audio, players
{ pkgs }:

with pkgs; [
  gpu-screen-recorder
  wf-recorder
  mpvpaper

  ffmpeg
  x264
  playerctl

  # Audio
  pipewire
  wireplumber
]
