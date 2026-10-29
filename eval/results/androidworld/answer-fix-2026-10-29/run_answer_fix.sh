#!/bin/zsh
# The answer-rule fix (androidworld b630d3f), measured offline once Meta's API answers: real-app cases, AndroidWorld's
# question steps, and the irreversible-step safety replays. About $4 at standard prices.
set -u
cd /private/tmp/claude-501/-Users-sanjeevvarma-Desktop-Envoy/ac29808f-24a8-4c21-a4dc-a5afb3cedcad/scratchpad/fix5
PY=/private/tmp/claude-501/-Users-sanjeevvarma-Desktop-Envoy/ac29808f-24a8-4c21-a4dc-a5afb3cedcad/scratchpad/next/backend/.venv/bin/python
export EXTRA=/private/tmp/claude-501/-Users-sanjeevvarma-Desktop-Envoy/ac29808f-24a8-4c21-a4dc-a5afb3cedcad/scratchpad/fix5/answer_fix_variants.json
$PY realapp_ab.py main main 8 realapp_main_8.json > realapp_main_8.log 2>&1 &
$PY realapp_ab.py next cur,no742,nof93,open,fix,fix_plan,fix_scope,fix_noformat 8 realapp_dry_8.json > realapp_dry_8.log 2>&1 &
$PY aw_answer_ab.py 5 aw_answer_5.json cur,fix,fix_scope,fix_noformat,fix_noformat_adapter > aw_answer_5.log 2>&1 &
wait
ONLY=cur,fix,fix_scope,fix_noformat $PY safety_label_ab.py 5 safety_label3_5.json > safety_label3_5.log 2>&1 &
ONLY=cur,fix,fix_scope,fix_noformat $PY irrev_open_ab.py 5 irrev_open3_5.json 10 > irrev_open3_5.log 2>&1 &
wait
$PY realapp_sum.py realapp_main_8.json realapp_dry_8.json > realapp_summary.txt 2>&1
tail -3 realapp_main_8.log realapp_dry_8.log aw_answer_5.log | grep -h "cost"
echo ALL DONE
