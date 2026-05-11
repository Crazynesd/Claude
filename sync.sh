#!/bin/bash
# Sync knowledge filer fra Mac til server
# Brug: bash sync.sh

SERVER="root@187.124.17.73"
LOCAL="$HOME/Main Claude/ecom-agents/"
REMOTE="/root/knowledge/"

echo "Synkroniserer til serveren..."
rsync -avz -e "ssh -i ~/.ssh/id_ed25519" "$LOCAL" "$SERVER:$REMOTE"
echo ""
echo "Filer paa serveren:"
ssh -i ~/.ssh/id_ed25519 $SERVER "find /root/knowledge -name '*.md' | sort"
