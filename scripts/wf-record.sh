#!/usr/bin/env bash
set -euo pipefail

OUTPUT=""
MODE="screen"
GEOMETRY=""
MONITOR=""
AUDIO_OUTPUT=false
AUDIO_INPUT=false

# Convert gpu-screen-recorder WxH+X+Y into wf-recorder "x,y WxH".
to_wf_geometry() {
  local raw="$1"
  if [[ "$raw" == *","* ]]; then
    printf '%s\n' "$raw"
    return
  fi
  if [[ "$raw" =~ ^([0-9]+)x([0-9]+)\+(-?[0-9]+)\+(-?[0-9]+)$ ]]; then
    printf '%s,%s %sx%s\n' "${BASH_REMATCH[3]}" "${BASH_REMATCH[4]}" "${BASH_REMATCH[1]}" "${BASH_REMATCH[2]}"
    return
  fi
  printf '%s\n' "$raw"
}

while [[ $# -gt 0 ]]; do
  case $1 in
    -o|--output)
      OUTPUT="$2"
      shift 2
      ;;
    -m|--mode)
      MODE="$2"
      shift 2
      ;;
    -g|--geometry)
      GEOMETRY="$2"
      shift 2
      ;;
    --monitor)
      MONITOR="$2"
      shift 2
      ;;
    --audio-output)
      AUDIO_OUTPUT=true
      shift
      ;;
    --audio-input)
      AUDIO_INPUT=true
      shift
      ;;
    *)
      echo "Unknown argument: $1"
      exit 1
      ;;
  esac
done

if [ -z "$OUTPUT" ]; then
    echo "Error: Output file required"
    exit 1
fi

if ! command -v wf-recorder >/dev/null 2>&1; then
    echo "Error: wf-recorder is not installed"
    exit 1
fi

CMD=(wf-recorder -f "$OUTPUT" -r 60 -y)

if [ "$MODE" = "region" ]; then
    if [ -z "$GEOMETRY" ]; then
        echo "Error: Geometry required for region mode"
        exit 1
    fi
    CMD+=(-g "$(to_wf_geometry "$GEOMETRY")")
elif [ -n "$MONITOR" ]; then
    CMD+=(-o "$MONITOR")
fi

AUDIO_SOURCE=""
MODULE_IDS=""

cleanup() {
    if [ -n "$MODULE_IDS" ]; then
        for id in $MODULE_IDS; do
            pactl unload-module "$id" || true
        done
    fi
}
trap cleanup EXIT

if [ "$AUDIO_OUTPUT" = true ] && [ "$AUDIO_INPUT" = true ]; then
    SINK_NAME="ambxst+_record_sink_$$"

    MOD_SINK=$(pactl load-module module-null-sink media.class=Audio/Sink sink_name="$SINK_NAME" channel_map=stereo)
    MODULE_IDS="$MOD_SINK"

    DEFAULT_SINK=$(pactl get-default-sink)
    DEFAULT_SOURCE=$(pactl get-default-source)

    MOD_L1=$(pactl load-module module-loopback source="$DEFAULT_SINK.monitor" sink="$SINK_NAME")
    MODULE_IDS="$MODULE_IDS $MOD_L1"

    MOD_L2=$(pactl load-module module-loopback source="$DEFAULT_SOURCE" sink="$SINK_NAME")
    MODULE_IDS="$MODULE_IDS $MOD_L2"

    AUDIO_SOURCE="$SINK_NAME.monitor"

elif [ "$AUDIO_OUTPUT" = true ]; then
    DEFAULT_SINK=$(pactl get-default-sink)
    AUDIO_SOURCE="$DEFAULT_SINK.monitor"

elif [ "$AUDIO_INPUT" = true ]; then
    DEFAULT_SOURCE=$(pactl get-default-source)
    AUDIO_SOURCE="$DEFAULT_SOURCE"
fi

if [ -n "$AUDIO_SOURCE" ]; then
    CMD+=(-a "$AUDIO_SOURCE")
fi

echo "Starting recording..."
echo "Command: ${CMD[*]}"

"${CMD[@]}"
