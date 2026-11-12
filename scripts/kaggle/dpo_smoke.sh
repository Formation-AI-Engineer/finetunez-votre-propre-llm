#!/usr/bin/env bash
# Étape « dpo_smoke » : contrôles rapides du script DPO avant les runs complets (environ 20 min).
#
# cuda:0 — sur-apprentissage volontaire : 64 paires, 8 époques, sans validation. La justesse des
#          récompenses (rewards/accuracies) doit monter vers 1 et la marge (rewards/margins)
#          s'écarter de 0. Puis 20 questions par tâche avec SFT + DPO : réponses terminées (pas
#          de réponse coupée) et au format appris.
# cuda:1 — réglages réels sur 30 pas : durée par pas, mémoire, métriques de validation des deux
#          jeux ; run interrompu après le checkpoint du pas 15 puis repris (--resume).
set -uo pipefail
source scripts/kaggle/common.sh

mkdir -p outputs/logs
# Pas de reste d'un lancement précédent de la même session (voir sft_smoke.sh).
rm -rf outputs/dpo/smoke-dpo-overfit outputs/dpo/smoke-dpo-real outputs/eval/smoke-dpo-overfit

sft_of() {  # adaptateur SFT utilisé par un run DPO, lu dans son journal
    "${PY[@]}" -c "import json, sys; print(json.load(open(sys.argv[1]))['sft_adapter'])" \
        "outputs/dpo/$1/run.json"
}

overfit() {
    CUDA_VISIBLE_DEVICES=0 "${PY[@]}" scripts/train_dpo.py --name smoke-dpo-overfit --limit 64 \
        --set training.num_train_epochs=8 --set training.eval_strategy=no \
        --set training.learning_rate=5e-5 --set training.lr_scheduler_type=constant \
        --set training.warmup_steps=0 --set training.logging_steps=4 &&
        "${PY[@]}" scripts/evaluate.py --name smoke-dpo-overfit --limit 20 --device cuda:0 \
            --adapter "$(sft_of smoke-dpo-overfit)" --adapter outputs/dpo/smoke-dpo-overfit/best
}

real() {
    local dir=outputs/dpo/smoke-dpo-real
    local args=(scripts/train_dpo.py --name smoke-dpo-real --set training.max_steps=30
        --set training.eval_steps=15)
    CUDA_VISIBLE_DEVICES=1 "${PY[@]}" "${args[@]}" &
    local pid=$!
    until [ -f "$dir/checkpoint-15/trainer_state.json" ] || ! kill -0 "$pid" 2>/dev/null; do
        sleep 5
    done
    if ! kill -0 "$pid" 2>/dev/null; then
        echo "Le run s'est arrêté avant le checkpoint du pas 15."
        return 1
    fi
    sleep 5
    pkill -TERM -f -- "train_dpo.py --name smoke-dpo-real"
    wait "$pid" 2>/dev/null
    while pgrep -f -- "train_dpo.py --name smoke-dpo-real" >/dev/null; do sleep 2; done
    echo "Interrompu après le checkpoint 15 ; reprise."
    CUDA_VISIBLE_DEVICES=1 "${PY[@]}" "${args[@]}" --resume
}

overfit > outputs/logs/dpo_smoke_overfit.log 2>&1 &
overfit_pid=$!
real > outputs/logs/dpo_smoke_real.log 2>&1 &
real_pid=$!

status=0
wait_for "$overfit_pid" outputs/logs/dpo_smoke_overfit.log || status=1
wait_for "$real_pid" outputs/logs/dpo_smoke_real.log || status=1

save_outputs outputs/eval outputs/logs
for run in smoke-dpo-overfit smoke-dpo-real; do
    if [ -f "outputs/dpo/$run/run.json" ] && [ -d /kaggle/working ]; then
        mkdir -p "/kaggle/working/outputs/dpo/$run"
        cp "outputs/dpo/$run/run.json" "/kaggle/working/outputs/dpo/$run/"
    fi
done

echo "==== Sur-apprentissage (cuda:0)"
grep -E "^---- (contrôles|fusion)|trainable params|paires d'entraînement" \
    outputs/logs/dpo_smoke_overfit.log
"${PY[@]}" scripts/kaggle/show_dpo_run.py outputs/dpo/smoke-dpo-overfit/run.json
# Résumé complet : avec des réponses illisibles, la ligne des réponses coupées vient après les
# exemples, que la sélection jusqu'à « ## Exemples » laissait de côté.
cat outputs/eval/smoke-dpo-overfit/validation/summary.md 2>/dev/null

echo "==== Réglages réels, 30 pas avec reprise (cuda:1)"
grep -E "^Reprise|Interrompu|s'est arrêté" outputs/logs/dpo_smoke_real.log
"${PY[@]}" scripts/kaggle/show_dpo_run.py outputs/dpo/smoke-dpo-real/run.json
exit "$status"
