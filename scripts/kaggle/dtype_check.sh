#!/usr/bin/env bash
# Étape « dtype_check » : le fp16 dégrade-t-il Qwen3-1.7B-Base ?
#
# Qwen3 a été entraîné en bf16, que le T4 ne gère pas. Le même échantillon (30 questions par
# tâche) est évalué en fp16 sur cuda:0 et en fp32 sur cuda:1, en zero-shot puis en few-shot.
# Des réponses dégénérées (« .waitKey » en boucle) en fp16 seulement désigneraient un débordement
# numérique. Environ 10 minutes, le fp32 étant le plus lent.
set -uo pipefail
source scripts/kaggle/common.sh

mkdir -p outputs/logs
run_dtype() {
    local dtype=$1 device=$2
    "${PY[@]}" scripts/evaluate.py --name "check-$dtype" --dtype "$dtype" --device "$device" \
        --limit 30 &&
        "${PY[@]}" scripts/evaluate.py --name "check-$dtype-fewshot" --few-shot --batch-size 8 \
            --dtype "$dtype" --device "$device" --limit 30
}
run_dtype fp16 cuda:0 > outputs/logs/check_fp16.log 2>&1 &
fp16=$!
run_dtype fp32 cuda:1 > outputs/logs/check_fp32.log 2>&1 &
fp32=$!

status=0
wait_for "$fp16" outputs/logs/check_fp16.log || status=1
wait_for "$fp32" outputs/logs/check_fp32.log || status=1

save_outputs outputs/eval outputs/logs
for name in check-fp16 check-fp32 check-fp16-fewshot check-fp32-fewshot; do
    summary="outputs/eval/$name/validation/summary.md"
    [ -f "$summary" ] && cat "$summary"
done
exit "$status"
