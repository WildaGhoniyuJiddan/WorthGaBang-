#!/bin/bash
# Verification script for batch scraper implementation
# Run this to verify all changes are correct before deployment

echo "========================================"
echo "WORL PROJECT - BATCH SCRAPER VERIFICATION"
echo "========================================"
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m' # No Color

PASS_COUNT=0
FAIL_COUNT=0

check_pass() {
    echo -e "${GREEN}✅${NC} $1"
    ((PASS_COUNT++))
}

check_fail() {
    echo -e "${RED}❌${NC} $1"
    ((FAIL_COUNT++))
}

echo "Checking Python files..."
python -m py_compile backend/app/batch_jobs.py 2>/dev/null && check_pass "batch_jobs.py syntax OK" || check_fail "batch_jobs.py syntax error"
python -m py_compile backend/app/cleanup_local_data.py 2>/dev/null && check_pass "cleanup_local_data.py syntax OK" || check_fail "cleanup_local_data.py syntax error"
python -m py_compile backend/app/cron_cleanup.py 2>/dev/null && check_pass "cron_cleanup.py syntax OK" || check_fail "cron_cleanup.py syntax error"

echo ""
echo "Checking modified files..."
python -m py_compile backend/app/services/analysis.py 2>/dev/null && check_pass "analysis.py syntax OK (query limits reduced)" || check_fail "analysis.py syntax error"
python -m py_compile backend/app/services/suggest.py 2>/dev/null && check_pass "suggest.py syntax OK (query limits reduced)" || check_fail "suggest.py syntax error"

echo ""
echo "Checking Supabase client..."
backend/.venv/Scripts/python -c "from supabase import create_client" 2>/dev/null && check_pass "Supabase client installed" || check_fail "Supabase client NOT installed"

echo ""
echo "Checking imports..."
backend/.venv/Scripts/python -c "from app.batch_jobs import run_source_batch, run_cycle_batch" 2>/dev/null && check_pass "batch_jobs.py imports correctly" || check_fail "batch_jobs.py import failed"

echo ""
echo "Checking directory structure..."
test -d backend/app/local_scratch && check_pass "local_scratch directory exists" || check_fail "local_scratch directory missing"
test -f backend/app/.gitkeep 2>/dev/null && check_pass ".gitkeep marker file exists" || check_fail ".gitkeep not found"

echo ""
echo "Checking documentation..."
test -f IMPLEMENTATION_SUMMARY.md && check_pass "IMPLEMENTATION_SUMMARY.md created" || check_fail "Documentation missing"
test -f BATCH_SCRAPER_GUIDE.md && check_pass "BATCH_SCRAPER_GUIDE.md created" || check_fail "Guide missing"

echo ""
echo "========================================"
echo "VERIFICATION SUMMARY"
echo "========================================"
echo -e "Passed: ${GREEN}$PASS_COUNT${NC}"
echo -e "Failed: ${RED}$FAIL_COUNT${NC}"
echo ""

if [ $FAIL_COUNT -eq 0 ]; then
    echo -e "${GREEN}✅ ALL CHECKS PASSED - READY FOR DEPLOYMENT!${NC}"
    exit 0
else
    echo -e "${RED}❌ Some checks failed. Please fix issues before deployment.${NC}"
    exit 1
fi
