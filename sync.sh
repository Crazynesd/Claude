#!/bin/bash
# Sync knowledge files fra Mac til server
rsync -avz -e "ssh -i ~/.ssh/id_ed25519" \
  ~/Main\ Claude/ecom-agents/ \
  root@187.124.17.73:/root/knowledge/
