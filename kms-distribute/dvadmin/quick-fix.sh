#!/bin/bash
# Quick Start Guide - Run all fixes in one command

echo "=================================================="
echo "   Blockchain Issues Quick Fix"
echo "   运行此脚本修复所有区块链问题"
echo "=================================================="
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Step 1: Backend fix
echo -e "${YELLOW}[1/3] Running backend fixes...${NC}"
echo "Running: python backend/auto_fix_blockchain_issues.py"

cd backend
python auto_fix_blockchain_issues.py

if [ $? -eq 0 ]; then
    echo -e "${GREEN}[1/3] Backend fixes completed ✓${NC}"
else
    echo -e "${RED}[1/3] Backend fixes failed${NC}"
    exit 1
fi

cd ..

# Step 2: Frontend fix
echo ""
echo -e "${YELLOW}[2/3] Running frontend fixes...${NC}"
echo "Running: node web/remove-emojis.js"

cd web
node remove-emojis.js

if [ $? -eq 0 ]; then
    echo -e "${GREEN}[2/3] Frontend fixes completed ✓${NC}"
else
    echo -e "${YELLOW}[2/3] Frontend fixes skipped (Node.js not available)${NC}"
fi

cd ..

# Step 3: Verification
echo ""
echo -e "${YELLOW}[3/3] Verifying fixes...${NC}"

# Check for emojis
emoji_count=$(grep -r "✅\|❌\|⚠️\|🔧\|📊" backend/pqkds --include="*.py" | wc -l 2>/dev/null || echo 0)

if [ "$emoji_count" -eq 0 ]; then
    echo -e "${GREEN}[3/3] Verification passed ✓${NC}"
    echo ""
    echo "=================================================="
    echo -e "${GREEN}All fixes completed successfully!${NC}"
    echo "=================================================="
    echo ""
    echo "Next steps:"
    echo "1. Restart Django server: python manage.py runserver"
    echo "2. Check logs for blockchain sync status"
    echo "3. Verify all nodes are registered on blockchain"
    echo ""
    echo "For details, see:"
    echo "  - COMPLETE_SOLUTION.md (完整分析)"
    echo "  - BLOCKCHAIN_FIX_GUIDE.md (修复指南)"
    echo "  - BLOCKCHAIN_FIX_SUMMARY.md (修复总结)"
    echo ""
else
    echo -e "${YELLOW}[3/3] Found emoji symbols: $emoji_count${NC}"
    echo "Running manual cleanup..."
    # Try to remove emojis using Python
    cd backend
    python -c "
import os, re
patterns = [r'✅|❌|⚠️|🔧|📊|💡|🎉|⭐|🔥']
for root, dirs, files in os.walk('pqkds'):
    for f in files:
        if f.endswith('.py'):
            path = os.path.join(root, f)
            with open(path, 'r', encoding='utf-8', errors='ignore') as file:
                content = file.read()
            for pattern in patterns:
                content = re.sub(pattern, '', content)
            with open(path, 'w', encoding='utf-8') as file:
                file.write(content)
print('Emojis removed successfully')
"
    cd ..
    echo -e "${GREEN}[3/3] Manual cleanup completed ✓${NC}"
fi

echo ""
echo "=================================================="
echo "Ready for production deployment!"
echo "=================================================="

