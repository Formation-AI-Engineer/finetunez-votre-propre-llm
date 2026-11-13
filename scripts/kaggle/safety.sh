#!/usr/bin/env bash
# Étape « safety » : jeu de sécurité (configs/safety_cases.yaml, 40 cas rédigés à la main) pour
# le modèle de base, le SFT et le SFT + DPO retenus, avec les mêmes réglages de génération que la
# validation. Quelques minutes par modèle.
#
# cuda:0 — SFT, puis modèle de base ; cuda:1 — SFT + DPO.
# Adaptateurs téléchargés depuis le Hub privé, aux révisions publiées (docs/TACHES.md).
set -uo pipefail
source scripts/kaggle/common.sh

SFT="hf://lcamara/triage-chsa-adapters/sft-r16-lr2e-4@8f0cbc488afe2dce1c12bb8952cd2507e3f38cae"
DPO="hf://lcamara/triage-chsa-adapters/dpo-b0.1-lr3e-5@eb4703b855fb29f4f5a4699e4e81acd6fb2bc7d6"

mkdir -p outputs/logs
rm -rf outputs/eval/{base,sft-r16-lr2e-4,dpo-b0.1-lr3e-5}/safety

evaluate() {  # nom, carte, adaptateurs…
    local name=$1 gpu=$2
    shift 2
    local adapters=()
    for a in "$@"; do adapters+=(--adapter "$a"); done
    "${PY[@]}" scripts/evaluate.py --name "$name" --split safety --device "cuda:$gpu" "${adapters[@]}"
}

{ evaluate sft-r16-lr2e-4 0 "$SFT" && evaluate base 0; } > outputs/logs/safety_gpu0.log 2>&1 &
gpu0=$!
evaluate dpo-b0.1-lr3e-5 1 "$SFT" "$DPO" > outputs/logs/safety_gpu1.log 2>&1 &
gpu1=$!

status=0
wait_for "$gpu0" outputs/logs/safety_gpu0.log || status=1
wait_for "$gpu1" outputs/logs/safety_gpu1.log || status=1
save_outputs outputs/eval outputs/logs

for name in base sft-r16-lr2e-4 dpo-b0.1-lr3e-5; do
    summary="outputs/eval/$name/safety/summary.md"
    echo "==== $name"
    [ -f "$summary" ] && cat "$summary"
done
exit "$status"
