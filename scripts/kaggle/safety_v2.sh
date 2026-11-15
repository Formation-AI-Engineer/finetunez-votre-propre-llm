#!/usr/bin/env bash
# Étape « safety_v2 » : second jeu de sécurité (configs/safety_cases_v2.yaml, 29 cas neufs,
# rédigés avant les drapeaux rouges sur le texte), pour le système retenu et pour le SFT seul.
# Les réponses servent ensuite à mesurer les drapeaux rouges sans GPU (scripts/guard_report.py).
# Quelques minutes. cuda:0 — SFT + DPO ; cuda:1 — SFT.
set -uo pipefail
source scripts/kaggle/common.sh

SFT="hf://lcamara/triage-chsa-adapters/sft-r16-lr2e-4@8f0cbc488afe2dce1c12bb8952cd2507e3f38cae"
DPO="hf://lcamara/triage-chsa-adapters/dpo-b0.1-lr3e-5@eb4703b855fb29f4f5a4699e4e81acd6fb2bc7d6"

mkdir -p outputs/logs
rm -rf outputs/eval/{sft-r16-lr2e-4,dpo-b0.1-lr3e-5}/safety_v2

"${PY[@]}" scripts/evaluate.py --name dpo-b0.1-lr3e-5 --split safety_v2 --device cuda:0 \
    --adapter "$SFT" --adapter "$DPO" > outputs/logs/safety_v2_gpu0.log 2>&1 &
gpu0=$!
"${PY[@]}" scripts/evaluate.py --name sft-r16-lr2e-4 --split safety_v2 --device cuda:1 \
    --adapter "$SFT" > outputs/logs/safety_v2_gpu1.log 2>&1 &
gpu1=$!

status=0
wait_for "$gpu0" outputs/logs/safety_v2_gpu0.log || status=1
wait_for "$gpu1" outputs/logs/safety_v2_gpu1.log || status=1
save_outputs outputs/eval outputs/logs

for name in dpo-b0.1-lr3e-5 sft-r16-lr2e-4; do
    summary="outputs/eval/$name/safety_v2/summary.md"
    echo "==== $name"
    [ -f "$summary" ] && cat "$summary"
done
exit "$status"
