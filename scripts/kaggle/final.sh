#!/usr/bin/env bash
# Étape « final » : poids finaux et évaluation unique sur le jeu de test.
#
# Système retenu (docs/EVALUATION.md, « Décisions ») : SFT r16 lr 2e-4 puis DPO beta 0.1 lr 3e-5,
# servi avec les garde-fous (constantes, cohérence du critère cité), choisi AVANT de voir le test.
#
# cuda:0 — fusion des deux adaptateurs (fp32 sur CPU, contrôle sur GPU), puis évaluation des
#          poids fusionnés sur le test, puis sur le jeu de sécurité (doit redonner les réponses
#          des adaptateurs empilés) ; publication privée sur le Hub si tout a réussi.
# cuda:1 — SFT seul sur le test, pour mesurer l'apport du DPO (pas pour choisir).
# Environ 1 h. Les poids fusionnés (3,4 Go) ne sont pas copiés dans /kaggle/working.
set -uo pipefail
source scripts/kaggle/common.sh

SFT="hf://lcamara/triage-chsa-adapters/sft-r16-lr2e-4@8f0cbc488afe2dce1c12bb8952cd2507e3f38cae"
DPO="hf://lcamara/triage-chsa-adapters/dpo-b0.1-lr3e-5@eb4703b855fb29f4f5a4699e4e81acd6fb2bc7d6"
FINAL=outputs/final/triage-chsa-qwen3-1.7b
NAME=final
REPO=lcamara/triage-chsa-qwen3-1.7b

mkdir -p outputs/logs
rm -rf "$FINAL" outputs/eval/{final,sft-r16-lr2e-4}/test outputs/eval/final/safety

final() {
    "${PY[@]}" scripts/merge_final.py --out "$FINAL" --adapter "$SFT" --adapter "$DPO" &&
        cp "$FINAL/merge.json" outputs/logs/merge.json &&
        "${PY[@]}" scripts/evaluate.py --name "$NAME" --model "$FINAL" --split test --device cuda:0 &&
        "${PY[@]}" scripts/evaluate.py --name "$NAME" --model "$FINAL" --split safety --device cuda:0 &&
        "${PY[@]}" scripts/publish_model.py --dir "$FINAL" --repo "$REPO"
}

final > outputs/logs/final_gpu0.log 2>&1 &
gpu0=$!
"${PY[@]}" scripts/evaluate.py --name sft-r16-lr2e-4 --split test --device cuda:1 \
    --adapter "$SFT" > outputs/logs/final_gpu1.log 2>&1 &
gpu1=$!

status=0
wait_for "$gpu0" outputs/logs/final_gpu0.log || status=1
wait_for "$gpu1" outputs/logs/final_gpu1.log || status=1
save_outputs outputs/eval outputs/logs

grep -h -- "---- contrôles\|Publié\|Référence" outputs/logs/final_gpu0.log
for run in final/test sft-r16-lr2e-4/test final/safety; do
    summary="outputs/eval/$run/summary.md"
    echo "==== $run"
    [ -f "$summary" ] && cat "$summary"
done
exit "$status"
