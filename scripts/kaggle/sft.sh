#!/usr/bin/env bash
# Étape « sft » : deux runs SFT complets en parallèle, un par T4, puis l'évaluation de chacun sur
# la validation (même script et mêmes réglages que la mesure de référence).
#
# cuda:0 — configs/sft.yaml tel quel ;
# cuda:1 — la même chose avec un taux d'apprentissage divisé par deux.
# Pour essayer d'autres variantes, changer RUNS ci-dessous (nom et surcharges --set).
# Les adaptateurs retenus, les journaux et les résumés sont copiés dans /kaggle/working.
set -uo pipefail
source scripts/kaggle/common.sh

RUNS=(
    "sft-r16-lr2e-4|"
    "sft-r16-lr1e-4|--set training.learning_rate=1e-4"
)

mkdir -p outputs/logs

train_and_evaluate() {
    local gpu=$1 name=$2 overrides=$3
    # Pas de reste d'un lancement précédent de la même session (checkpoints, résumés).
    rm -rf "outputs/sft/$name" "outputs/eval/$name"
    # shellcheck disable=SC2086  # surcharges séparées par des espaces, volontairement
    CUDA_VISIBLE_DEVICES=$gpu "${PY[@]}" scripts/train_sft.py --name "$name" $overrides &&
        "${PY[@]}" scripts/evaluate.py --name "$name" --adapter "outputs/sft/$name/best" \
            --device "cuda:$gpu"
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
    if [ -d /kaggle/working ] && [ -d "outputs/sft/$name/best" ]; then
        mkdir -p "/kaggle/working/outputs/sft/$name"
        cp -r "outputs/sft/$name/best" "outputs/sft/$name/run.json" "/kaggle/working/outputs/sft/$name/"
    fi
done
save_outputs outputs/eval outputs/logs

for name in "${names[@]}"; do
    echo "==== $name"
    "${PY[@]}" - "$name" <<'EOF'
import json
import sys
from pathlib import Path

run = Path(f"outputs/sft/{sys.argv[1]}/run.json")
if run.exists():
    r = json.loads(run.read_text())
    print(f"{r['steps']} pas en {r['minutes']} min, {r['peak_gpu_memory_gib']} Gio ; perte "
          f"d'entraînement {r['first_train_loss']:.3f} -> {r['last_train_loss']:.3f} ; meilleure "
          f"perte de validation {r['best_eval_loss']:.4f} ({r['best_checkpoint']})")
    print("pertes de validation :", [round(x, 4) for x in r["eval_losses"]])
EOF
    summary="outputs/eval/$name/validation/summary.md"
    [ -f "$summary" ] && sed -n '1,/^## Exemples/p' "$summary" && grep "^Réponses coupées" "$summary"
done
exit "$status"
