#!/bin/bash
# Sync knowledge files fra Mac til server
# Kør fra: ~/Downloads/wave-agent-v2/claude/
# Brug: bash sync.sh

SERVER="root@187.124.17.73"
LOCAL="$HOME/Main Claude/ecom-agents/"
REMOTE="/root/knowledge/"

echo "Synkroniserer knowledge-filer til serveren..."
echo "Fra: $LOCAL"
echo "Til: $SERVER:$REMOTE"
echo ""

rsync -avz --progress \
  --include='*/' \
  --include='_knowledge/**.md' \
  --include='_knowledge/**.txt' \
  --exclude='*' \
  -e "ssh -i ~/.ssh/id_ed25519" \
  "$LOCAL" \
  "$SERVER:$REMOTE"

echo ""
echo "Sync faerdig. Filer paa serveren:"
ssh -i ~/.ssh/id_ed25519 $SERVER "find /root/knowledge -name '*.md' | sort"
