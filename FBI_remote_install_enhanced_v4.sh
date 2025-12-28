#!/bin/bash
TARGET="$1"
if [ -z "$TARGET" ]; then
  TARGET="."
fi

echo
echo "=========================================================="
echo "  FBI Remote Install (Enhanced v4 - IP history picker)"
echo "=========================================================="
echo "Target : $TARGET"
echo
echo "Once running:"
echo "  R + Enter = re-send URLs"
echo "  Q + Enter = quit"
echo

python3 servefiles_enhanced_v4.py "$TARGET" --ack-wait 2 --retries 5 --retry-delay 1 --chunk-kb 256

echo
read -p "Press Enter to close..."
