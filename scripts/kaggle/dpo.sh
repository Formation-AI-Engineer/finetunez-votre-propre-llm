#!/usr/bin/env bash
# Étape « dpo » : deux runs DPO complets en parallèle, un par T4, puis l'évaluation de chacun
# (adaptateur SFT puis adaptateur DPO) sur la validation, mêmes réglages que pour le SFT.
#
# cuda:0 — configs/dpo.yaml tel quel ;
# cuda:1 — la même chose avec un taux d'apprentissage triple.
# Pour essayer d'autres variantes (beta, loss_type), changer RUNS ci-dessous.
set -uo pipefail
source scripts/kaggle/common.sh

RUNS=(
    "dpo-b0.1-lr1e-5|"
    "dpo-b0.1-lr3e-5|--set training.learning_rate=3e-5"
)

mkdir -p outputs/logs

train_and_evaluate() {
    local gpu=$1 name=$2 overrides=$3
    rm -rf "outputs/dpo/$name" "outputs/eval/$name"
    # shellcheck disable=SC2086  # surcharges séparées par des espaces, volontairement
    CUDA_VISIBLE_DEVICES=$gpu "${PY[@]}" scripts/train_dpo.py --name "$name" $overrides || return 1
    local sft
    sft=$("${PY[@]}" -c "import json, sys; print(json.load(open(sys.argv[1]))['sft_adapter'])" \
        "outputs/dpo/$name/run.json")
    "${PY[@]}" scripts/evaluate.py --name "$name" --device "cuda:$gpu" \
        --adapter "$sft" --adapter "outputs/dpo/$name/best"
}

pids=()
names=()
for gpu in 0 1; do
    IFS="|" read -r name overrides <<<"${RUNS[$gpu]}"
    train_and_evaluate "$gpu" "$name" "$overrides" > "outputs/logs/$name.log" 2>&1 &
    pids+=($!)
    names+=("$name")
done

status=0
for i in 0 1; do
    wait_for "${pids[$i]}" "outputs/logs/${names[$i]}.log" || status=1
done

# Adaptateurs retenus et journaux des runs ; pas les checkpoints intermédiaires.
for name in "${names[@]}"; do
    if [ -d /kaggle/working ] && [ -d "outputs/dpo/$name/best" ]; then
        mkdir -p "/kaggle/working/outputs/dpo/$name"
        cp -r "outputs/dpo/$name/best" "outputs/dpo/$name/run.json" "/kaggle/working/outputs/dpo/$name/"
    fi
done
save_outputs outputs/eval outputs/logs

for name in "${names[@]}"; do
    echo "==== $name"
    "${PY[@]}" scripts/kaggle/show_dpo_run.py "outputs/dpo/$name/run.json"
    summary="outputs/eval/$name/validation/summary.md"
    [ -f "$summary" ] && sed -n '1,/^## Exemples/p' "$summary"
done
exit "$status"
