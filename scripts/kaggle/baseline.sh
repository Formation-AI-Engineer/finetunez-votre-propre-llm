#!/usr/bin/env bash
# Étape « baseline » : mesure de référence de Qwen3-1.7B-Base sur le jeu de validation.
#
# Deux runs en parallèle, un par T4 : zero-shot (base) et few-shot (base-fewshot).
# Environ 10 minutes. Résumés affichés à la fin et copiés dans /kaggle/working/outputs/eval.
set -uo pipefail
source scripts/kaggle/common.sh

mkdir -p outputs/logs
"${PY[@]}" scripts/evaluate.py --name base --device cuda:0 \
    > outputs/logs/eval_base.log 2>&1 &
base=$!
"${PY[@]}" scripts/evaluate.py --name base-fewshot --few-shot --batch-size 8 --device cuda:1 \
    > outputs/logs/eval_fewshot.log 2>&1 &
fewshot=$!

status=0
wait_for "$base" outputs/logs/eval_base.log || status=1
wait_for "$fewshot" outputs/logs/eval_fewshot.log || status=1

save_outputs outputs/eval outputs/logs
for name in base base-fewshot; do
    summary="outputs/eval/$name/validation/summary.md"
    [ -f "$summary" ] && cat "$summary"
done
exit "$status"
